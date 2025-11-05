# games/services/votes.py
from django.db import transaction, models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from .models import VoteSession, VoteOption, VoteBallot, GamePlayer

class VoteService:
    @staticmethod
    @transaction.atomic
    def start_election_for_game(game, started_at=None, **meta) -> VoteSession:
        """
        Создаёт VoteSession + VoteOption по активным кандидатам (все активные не-наблюдатели),
        исключая самих себя пользователь потом проверит на фронте, но и на бэке тоже проверим при голосовании.
        """
        # Если уже есть активная сессия — ничего не делаем
        if VoteSession.objects.filter(game=game, kind=VoteSession.KIND_ELECTION, is_active=True).exists():
            return VoteSession.objects.filter(game=game, kind='election', is_active=True).latest('started_at')

        session = VoteSession.objects.create(
            game=game,
            kind=VoteSession.KIND_ELECTION,
            question="Кого выбираем правителем?",
            started_at=started_at or timezone.now(),
            is_active=True,
            meta={
                "no_self_vote": True,
                "tie_policy": "random",
                "duration_sec": int(game.election_duration.total_seconds()),
                **meta
            },
        )

        ct = ContentType.objects.get_for_model(GamePlayer)
        candidates_qs = (GamePlayer.objects
                         .filter(game=game, is_active=True, is_observer=False))
        VoteOption.objects.bulk_create([
            VoteOption(session=session, label=gp.user.username, content_type=ct, object_id=gp.pk)
            for gp in candidates_qs
        ])

        return session

    @staticmethod
    @transaction.atomic
    def cast_vote(game, voter_user, candidate_gp_id: int):
        """
        Принимаем candidate_id (как у тебя во фронте), находим соответствующую VoteOption
        текущей активной сессии и сохраняем бюллетень.
        """
        try:
            session = VoteSession.objects.select_for_update().get(
                game=game, kind=VoteSession.KIND_ELECTION, is_active=True
            )
        except VoteSession.DoesNotExist:
            raise ValueError("Нет активной сессии голосования")

        try:
            option = (VoteOption.objects
                      .select_related('session')
                      .get(session=session, content_type__model='gameplayer', object_id=candidate_gp_id))
        except VoteOption.DoesNotExist:
            raise ValueError("Кандидат не найден в текущем голосовании")

        # базовые проверки
        gp_self = GamePlayer.objects.get(game=game, user=voter_user)
        if gp_self.is_observer:
            raise ValueError("Наблюдатель не может голосовать")
        if session.meta.get("no_self_vote") and option.object_id == gp_self.id:
            raise ValueError("Нельзя голосовать за себя")

        # один бюллетень на пользователя, разрешаем менять голос
        VoteBallot.objects.update_or_create(
            session=session, voter=voter_user, defaults={"option": option}
        )

        from .tasks import maybe_close_early
        maybe_close_early.delay(str(game.id))

    @staticmethod
    @transaction.atomic
    def maybe_finish_if_due(game):
        """
        Закрыть голосование по таймеру. Возвращает (winner_gp или None)
        """
        try:
            session = VoteSession.objects.select_for_update().get(
                game=game, kind=VoteSession.KIND_ELECTION, is_active=True
            )
        except VoteSession.DoesNotExist:
            return None

        # дедлайн из meta либо из модели Game
        duration_sec = session.meta.get("duration_sec")
        if duration_sec is None:
            duration_sec = int(game.election_duration.total_seconds())

        # учитываем твои паузы через методы Game
        if game.election_remaining_seconds() > 0:
            return None  # ещё рано

        session.meta = {**(session.meta or {}), "last_result": "timeout"}
        session.save(update_fields=["meta"])
        game.end_election()
        return None

    @staticmethod
    @transaction.atomic
    def finish_force(game):
        """Принудительное завершение (например, при досрочном голосовании всеми)."""
        try:
            session = VoteSession.objects.select_for_update().get(
                game=game, kind=VoteSession.KIND_ELECTION, is_active=True
            )
        except VoteSession.DoesNotExist:
            return None
        return VoteService._finish_and_pick_winner(session)

    @staticmethod
    def _finish_and_pick_winner(session: VoteSession):
        if not session.is_active:
            return None

        # закрываем
        session.is_active = False
        session.ends_at = timezone.now()
        session.save(update_fields=['is_active', 'ends_at'])

        # подсчёт
        tally = (VoteBallot.objects
                 .filter(session=session)
                 .values('option_id')
                 .annotate(count=models.Count('id'))
                 .order_by('-count', 'option_id'))

        if not tally:
            return None

        top = tally[0]['count']
        winners = [row['option_id'] for row in tally if row['count'] == top]

        if len(winners) > 1:
            # НИЧЬЯ → помечаем и выходим без победителя
            session.meta = {**(session.meta or {}), "last_result": "tie"}
            session.save(update_fields=["meta"])
            return None

        # победитель один
        winner_option_id = winners[0]
        winner_option = VoteOption.objects.get(pk=winner_option_id)

        session.meta = {**(session.meta or {}), "last_result": "winner", "winner_option_id": winner_option_id}
        session.save(update_fields=["meta"])

        return winner_option.target
