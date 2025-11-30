"""
Скрипт показа всех учетных данных пользователей системы
"""
from app import app
from models import db, User

with app.app_context():
    # Получаем всех пользователей
    admins = User.query.filter_by(role='admin').order_by(User.username).all()
    teachers = User.query.filter_by(role='teacher').order_by(User.full_name).all()
    
    print("\n" + "="*70)
    print("УЧЕТНЫЕ ДАННЫЕ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ СИСТЕМЫ")
    print("="*70)
    
    # Администраторы
    print(f"\n👑 АДМИНИСТРАТОРЫ ({len(admins)}):")
    print("-" * 70)
    for admin in admins:
        print(f"  Логин:   {admin.username}")
        print(f"  Пароль:  admin")
        print(f"  ФИО:     {admin.full_name}")
        print()
    
    # Преподаватели
    print(f"\n👨‍🏫 ПРЕПОДАВАТЕЛИ ({len(teachers)}):")
    print("-" * 70)
    for i, teacher in enumerate(teachers, 1):
        circles_count = len(teacher.circles)
        circles_names = ", ".join([c.name[:30] for c in teacher.circles[:2]])
        if circles_count > 2:
            circles_names += f" и еще {circles_count - 2}"
        
        print(f"{i:3}. {teacher.full_name}")
        print(f"     Логин:   {teacher.username}")
        print(f"     Пароль:  12345")
        print(f"     Кружков: {circles_count}")
        if circles_names:
            print(f"     Кружки:  {circles_names}")
        print()
    
    print("="*70)
    print("\n📋 ИТОГО:")
    print(f"   Администраторов: {len(admins)}")
    print(f"   Преподавателей:  {len(teachers)}")
    print(f"   Всего:           {len(admins) + len(teachers)}")
    print("\n" + "="*70)
    print("\n💡 ПРИМЕЧАНИЕ:")
    print("   • Администраторы имеют пароль: admin")
    print("   • Все преподаватели имеют пароль: 12345")
    print("="*70 + "\n")

