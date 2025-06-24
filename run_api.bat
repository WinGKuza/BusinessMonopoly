@echo off
cd /d C:\Users\danil\PycharmProjects\BusinessMonopoly

REM Активируем виртуальное окружение
call .venv\Scripts\activate.bat

REM Запускаем Flask API
python main.py --host=0.0.0.0 --port=5000
