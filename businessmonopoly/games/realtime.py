# games/realtime.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Game, GamePlayer

def get_game_update_data(game_id):
    game = Game.objects.get(id=game_id)
    players = (GamePlayer.objects
               .filter(game=game, is_active=True)
               .select_related("user"))

    return {
        "players": [
            {
                "id": p.id,
                "username": p.user.username,
                "money": p.money,
                "influence": p.influence,
                "role": p.get_role_display(),
                "role_id": p.role,
                "special_role": p.special_role,
                "is_observer": p.is_observer,
                "is_active": p.is_active,
            }
            for p in players
        ],
        "is_voting": game.is_voting,
        "paused": game.is_paused(),
        "election_remaining": game.election_remaining_seconds() if game.is_voting else 0,
    }

def send_game_update(game_id):
    channel_layer = get_channel_layer()
    data = get_game_update_data(game_id)
    async_to_sync(channel_layer.group_send)(
        f"game_{game_id}",
        {"type": "game_update", "data": data}
    )

def notify_group(group_type: str, game_id):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(f"game_{game_id}", {"type": group_type})


def send_personal_message(user_id, message: str, level: str = "info", extra_data=None):
    level = level.lower()
    if level not in {"info", "success", "warning", "error"}:
        level = "info"

    payload = {
        "type": "personal_message",
        "message": {
            "type": "personal",
            "message": message,
            "level": level,
        }
    }

    if extra_data:
        payload["message"]["data"] = extra_data

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            payload
        )
    except Exception as e:
        print(f"[WebSocket] Ошибка отправки личного сообщения: {e}")


def broadcast_personal_to_game(
    game_id,
    message: str,
    level: str = "info",
    extra_data=None,
    include_observers: bool = True,
    active_only: bool = True,   # <-- новое: по умолчанию только активным
):
    qs = GamePlayer.objects.filter(game_id=game_id)
    if active_only:
        qs = qs.filter(is_active=True)
    if not include_observers:
        qs = qs.filter(is_observer=False)

    user_ids = qs.values_list("user_id", flat=True).distinct()
    for uid in user_ids:
        send_personal_message(uid, message, level=level, extra_data=extra_data)

