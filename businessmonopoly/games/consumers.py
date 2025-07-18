import json
from channels.generic.websocket import AsyncWebsocketConsumer

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'

        # Проверка авторизации
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

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
