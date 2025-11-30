"""
Скрипт показа учетных данных всех преподавателей
"""
from app import app
from models import db, User

with app.app_context():
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    print("\n" + "="*70)
    print("УЧЕТНЫЕ ДАННЫЕ ПРЕПОДАВАТЕЛЕЙ")
    print("="*70)
    print(f"\nВсего преподавателей: {len(teachers)}\n")
    
    for i, teacher in enumerate(teachers, 1):
        circles_count = len(teacher.circles)
        circles_names = ", ".join([c.name for c in teacher.circles[:2]])
        if circles_count > 2:
            circles_names += f" и еще {circles_count - 2}"
        
        print(f"{i:2}. {teacher.full_name}")
        print(f"    Логин:   {teacher.username}")
        print(f"    Пароль:  12345")
        print(f"    Кружков: {circles_count}")
        if circles_names:
            print(f"    Кружки:  {circles_names}")
        print()
    
    print("="*70)
    print("\nВСЕ ПРЕПОДАВАТЕЛИ ИМЕЮТ ПАРОЛЬ: 12345")
    print("АДМИН: логин 'admin', пароль 'admin'")
    print("="*70)

