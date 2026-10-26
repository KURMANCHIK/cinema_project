@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py generate_fixtures
python manage.py runserver
