import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .views import get_game_update_data

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'
        self.user_group_name = f"user_{self.scope['user'].id}"

        # Проверка авторизации
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.accept()

        data = await sync_to_async(get_game_update_data)(self.game_id)
        await self.channel_layer.send(self.channel_name, {
            "type": "game_update",
            "data": data,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return  # Неверный формат — игнорируем

        msg_type = data.get("type")

        # Обработка чата
        if msg_type == "chat":
            message = data.get("message")
            if message:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message,
                        'username': self.scope['user'].username,
                    }
                )

        # Обработка команд (расширяемый механизм)
        elif msg_type == "command":
            command = data.get("command", "unknown")
            if command == "refresh":
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'game_update',
                        'data': {
                            'message': f"Команда '{command}' от {self.scope['user'].username}",
                        }
                    }
                )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat',
            'message': event['message'],
            'username': event['username'],
        }))

    async def game_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update',
            'data': event['data'],
        }))

    async def voting_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'voting_started'
        }))

    async def voting_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'voting_ended'
        }))

    async def personal_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "personal",
            "message": event["message"],
            "level": event.get("level", "info"),
        }))

    async def game_deleted(self, event):
        await self.send(text_data=json.dumps({
            "type": "game_deleted",
            "name": event.get("name"),
            "redirect": event.get("redirect"),
        }))