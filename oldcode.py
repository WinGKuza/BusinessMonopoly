from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
api = Api(app, version='1.0', title='BusinessMonopoly API', description='API для управления пользователями и играми')
# Конфигурация
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/monopoly_project'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'your-super-secret-key'  # Замените на реальный секретный ключ!
app.config['RATELIMIT_DEFAULT'] = '100 per minute'  # Лимит по умолчанию

# Инициализация
db = SQLAlchemy(app)

# Инициализация Limiter с правильными параметрами
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://"  # Храним лимиты в памяти (для продакшена используйте Redis)
)

# Применяем лимиты к API
@api.route('/users')
class Users(Resource):
    decorators = [limiter.limit("60/minute")]

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "password_hash": self.password_hash
        }

class Game(db.Model):
    __tablename__ = 'games'
    game_id = db.Column(db.Integer, primary_key=True)
    game_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    money = db.Column(db.BigInteger, default=0)
    keys = db.Column(db.Integer, default=0)
    role = db.Column(db.Integer, default=2)

    def to_dict(self):
        return {
            "game_id": self.game_id,
            "game_name": self.game_name,
            "user_id": self.user_id,
            "money": self.money,
            "keys": self.keys,
            "role": self.role
        }

user_model = api.model('User', {
    'username': fields.String(required=True, description='Имя пользователя'),
    'email': fields.String(required=True, description='Email пользователя'),
    'password_hash': fields.String(required=True, description='Хэш пароля')
})

game_model = api.model('Game', {
    'game_name': fields.String(required=True, description='Название игры'),
    'user_id': fields.Integer(required=True, description='ID пользователя'),
    'money': fields.Integer(default=0, description='Деньги в игре'),
    'keys': fields.Integer(default=0, description='Ключи в игре'),
    'role': fields.Integer(default=2, description='Роль пользователя в игре')
})

@api.route('/users')
class Users(Resource):
    @api.doc('get_users')
    def get(self):
        users = User.query.all()
        users_list = [user.to_dict() for user in users]
        return jsonify(users_list)

    @api.doc('create_user')
    @api.expect(user_model)
    def post(self):
        data = request.get_json()
        username = data['username']
        email = data['email']
        password_hash = data['password_hash']

        if User.query.filter_by(username=username).first():
            return {"error": "Пользователь с таким именем уже существует"}, 400
        if User.query.filter_by(email=email).first():
            return {"error": "Пользователь с таким email уже существует"}, 400

        new_user = User(username=username, email=email, password_hash=password_hash)
        db.session.add(new_user)
        db.session.commit()
        return {'message': 'User created successfully', 'user': new_user.to_dict()}, 201

@api.route('/games')
class Games(Resource):
    @api.doc('get_games')
    def get(self):
        games = Game.query.all()
        games_list = [game.to_dict() for game in games]
        return jsonify(games_list)

    @api.doc('create_game')
    @api.expect(game_model)
    def post(self):
        data = request.get_json()
        game_name = data['game_name']
        user_id = data['user_id']
        money = data.get('money', 0)
        keys = data.get('keys', 0)
        role = data.get('role', 2)

        if not User.query.get(user_id):
            return {"error": f"Пользователь с user_id={user_id} не найден"}, 400

        new_game = Game(game_name=game_name, user_id=user_id, money=money, keys=keys, role=role)
        db.session.add(new_game)
        db.session.commit()
        return {'message': 'Game created successfully', 'game': new_game.to_dict()}, 201

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}