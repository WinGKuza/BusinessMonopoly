# games/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from django.db import transaction, models
from .models import Game
from .views import send_game_update
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = get_task_logger(__name__)

def _notify(group_type, game_id):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(f"game_{game_id}", {"type": group_type})

@shared_task(name="games.tasks.check_and_finish_elections")
def check_and_finish_elections():
    now = timezone.now()
    touched = 0

    # 1) старт выборов где пора
    to_start = Game.objects.filter(is_voting=False, last_election_time__lte=now - models.F('election_interval'))
    for g in to_start:
        with transaction.atomic():
            game = Game.objects.select_for_update().get(pk=g.pk)
            if game.is_voting:
                continue
            game.start_election()         # залогирует в модели
        try:
            send_game_update(game.id)
            _notify("voting_started", game.id)
        except Exception:
            pass
        logger.info("[ELECTION] started game=%s", game.id)
        touched += 1

    # 2) завершение активных где время вышло
    active = Game.objects.filter(is_voting=True)
    for g in active:
        remaining = g.election_remaining_seconds()
        if remaining > 0:
            continue
        with transaction.atomic():
            game = Game.objects.select_for_update().get(pk=g.pk)
            if not game.is_voting:
                continue
            game.end_election()           # залогирует в модели
        try:
            send_game_update(game.id)
            _notify("voting_ended", game.id)
        except Exception:
            pass
        logger.info("[ELECTION] ended   game=%s", game.id)
        touched += 1

    logger.debug("[ELECTION] tick checked=%d touched=%d", Game.objects.count(), touched)
