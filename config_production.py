"""
Production конфигурация для сервера
"""

# Настройки для production
DEBUG = False
HOST = '0.0.0.0'  # Слушать на всех интерфейсах
PORT = 5004
SECRET_KEY = 'cit-production-secret-key-change-me-2024'

# База данных
DATABASE_URI = 'sqlite:///attendance.db'

# Безопасность
SESSION_COOKIE_SECURE = False  # Установить True если используете HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

