# games/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django.db import transaction, models
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Game, VoteSession
from .realtime import send_game_update

logger = get_task_logger(__name__)


def _notify(group_type: str, game_id: int):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"game_{game_id}", {"type": group_type}
    )


@shared_task(name="games.tasks.check_and_finish_elections")
def check_and_finish_elections():
    now = timezone.now()
    touched = 0

    # 1) Старт выборов там, где пора по интервалу
    to_start = Game.objects.filter(
        is_voting=False,
        last_election_time__lte=now - models.F("election_interval"),
    )
    for g in to_start:
        with transaction.atomic():
            game = Game.objects.select_for_update().get(pk=g.pk)
            if game.is_voting:
                continue
            game.start_election()  # внутри твоя логика старта
        try:
            send_game_update(game.id)
            _notify("voting_started", game.id)
        except Exception:
            pass
        logger.info("[ELECTION] started game=%s", game.id)
        touched += 1

        # 2) Завершение истёкших
        active = Game.objects.filter(is_voting=True)
        for g in active:
            # быстрый предфильтр (может быть устаревшим)
            if g.election_remaining_seconds() > 0:
                continue

            did_timeout_close = False  # << флаг, реально ли закрыли как таймаут

            with transaction.atomic():
                game = Game.objects.select_for_update().get(pk=g.pk)
                if not game.is_voting:
                    # уже закрыли где-то ещё — уходим и НИЧЕГО больше не шлём
                    continue

                # считаем актуальные "ожидаемых" и "полученных"
                session = (VoteSession.objects
                           .select_for_update()
                           .filter(game=game, kind=VoteSession.KIND_ELECTION, is_active=True)
                           .first())

                expected = game._eligible_voters_qs().count()
                got = session.voters_count() if session else 0

                if got < expected:
                    # не все проголосовали — это правильный таймаут → рестартим раунд
                    game.end_election(force_result="timeout")
                    did_timeout_close = True
                else:
                    # все проголосовали — завершаем нормально, пусть выберется победитель/ничья
                    game.end_election()

            # уведомления — только если реально был таймаут
            if did_timeout_close:
                try:
                    send_game_update(game.id)
                    _notify("voting_ended", game.id)
                    _notify("voting_started", game.id)
                except Exception:
                    pass
                logger.info("[ELECTION] ended by TIMEOUT game=%s", game.id)
                touched += 1

        logger.debug("[ELECTION] tick checked=%d touched=%d", Game.objects.count(), touched)


@shared_task(name="games.tasks.maybe_close_early")
def maybe_close_early(game_id):
    from .models import Game, VoteSession, GamePlayer
    game = Game.objects.get(pk=game_id)

    session = VoteSession.objects.filter(game=game, is_active=True, kind="election").first()
    if not session:
        return

    expected = GamePlayer.objects.filter(game=game, is_active=True, is_observer=False).count()
    got = session.voters_count()

    # Закрываем досрочно только если проголосовали ВСЕ
    if got < expected or expected == 0:
        return

    # Все проголосовали — пусть стандартная логика подбора победителя/ничьей отработает единообразно
    game.end_election()
