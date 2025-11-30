"""
Production версия приложения
"""
from app import app

if __name__ == '__main__':
    # Production настройки
    app.config['DEBUG'] = False
    
    # Запуск с логированием
    print("="*70)
    print("  СИСТЕМА УЧЕТА ПОСЕЩАЕМОСТИ - PRODUCTION MODE")
    print("="*70)
    print(f"Host: 0.0.0.0")
    print(f"Port: 5004")
    print(f"Public URL: http://85.92.110.85:5004")
    print("="*70)
    
    app.run(
        debug=False,
        host='0.0.0.0',
        port=5004,
        threaded=True
    )

