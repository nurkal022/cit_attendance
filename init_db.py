"""
Скрипт инициализации базы данных
"""
from app import app
from models import db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Создаем все таблицы
    db.create_all()
    print("✓ Все таблицы созданы")
    
    # Проверяем, есть ли админ
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin'),
            full_name='Администратор',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("✓ Создан пользователь admin (пароль: admin)")
    else:
        print("✓ Админ уже существует")

