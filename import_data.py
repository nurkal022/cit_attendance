"""
Скрипт для импорта данных из Excel файла
"""
import pandas as pd
from datetime import datetime
from app import app, db
from models import Student, Circle, User
from werkzeug.security import generate_password_hash


def import_students_from_excel(filepath):
    """Импорт студентов из Excel файла"""
    
    print("Начинаем импорт данных...")
    
    # Читаем Excel файл
    df = pd.read_excel(filepath)
    
    print(f"Найдено {len(df)} записей")
    print(f"Колонки: {df.columns.tolist()}")
    
    with app.app_context():
        # Создаем админа по умолчанию
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                full_name='Администратор',
                role='admin'
            )
            db.session.add(admin)
            print("Создан админ: admin / admin123")
        
        # Словарь для хранения кружков
        circles_dict = {}
        teachers_dict = {}
        
        imported_count = 0
        
        for index, row in df.iterrows():
            try:
                # Получаем название кружка
                circle_name = str(row.get('НАИМЕНОВАНИЕ КРУЖКА', '')).strip()
                direction = str(row.get('ПО КАКОМУ НАПРАВЛЕНИЮ', '')).strip()
                
                if not circle_name or circle_name == 'nan':
                    print(f"Пропускаем строку {index + 1}: нет названия кружка")
                    continue
                
                # Создаем кружок если его нет
                if circle_name not in circles_dict:
                    # Проверяем существует ли кружок в БД
                    circle = Circle.query.filter_by(name=circle_name).first()
                    if not circle:
                        # Создаем преподавателя для кружка с уникальным именем
                        # Используем счетчик в словаре
                        teacher_num = len(teachers_dict) + 1
                        teacher_username = f"teacher_{teacher_num}"
                        
                        # Проверяем уникальность
                        while User.query.filter_by(username=teacher_username).first():
                            teacher_num += 1
                            teacher_username = f"teacher_{teacher_num}"
                        
                        teacher = User(
                            username=teacher_username,
                            password=generate_password_hash('teacher123'),
                            full_name=f'Преподаватель кружка "{circle_name[:50]}"',
                            role='teacher'
                        )
                        db.session.add(teacher)
                        db.session.flush()  # Получаем ID
                        teachers_dict[teacher_username] = teacher
                        
                        circle = Circle(
                            name=circle_name,
                            direction=direction,
                            teacher_id=teacher.id
                        )
                        db.session.add(circle)
                        db.session.flush()
                        
                        print(f"Создан кружок: {circle_name}, преподаватель: {teacher_username} / teacher123")
                    
                    circles_dict[circle_name] = circle
                else:
                    circle = circles_dict[circle_name]
                
                # Создаем студента
                full_name = str(row.get('ФИО', '')).strip()
                if not full_name or full_name == 'nan':
                    print(f"Пропускаем строку {index + 1}: нет ФИО")
                    continue
                
                # Парсим дату подачи
                application_date = None
                if 'Дата подачи' in row and pd.notna(row['Дата подачи']):
                    try:
                        application_date = pd.to_datetime(row['Дата подачи'])
                    except:
                        pass
                
                student = Student(
                    full_name=full_name,
                    iin=str(row.get('ИИН', '')).strip() if pd.notna(row.get('ИИН')) else None,
                    gender=str(row.get('ПОЛ', '')).strip() if pd.notna(row.get('ПОЛ')) else None,
                    address=str(row.get('АДРЕС', '')).strip() if pd.notna(row.get('АДРЕС')) else None,
                    school=str(row.get('С КАКОЙ ШКОЛЫ', '')).strip() if pd.notna(row.get('С КАКОЙ ШКОЛЫ')) else None,
                    grade=str(row.get('В КАКОМ КЛАССЕ ОБУЧАЕТСЯ', '')).strip() if pd.notna(row.get('В КАКОМ КЛАССЕ ОБУЧАЕТСЯ')) else None,
                    direction=direction,
                    circle_id=circle.id,
                    applicant_name=str(row.get('ФИО заявителя', '')).strip() if pd.notna(row.get('ФИО заявителя')) else None,
                    applicant_iin=str(row.get('ИИН заявителя', '')).strip() if pd.notna(row.get('ИИН заявителя')) else None,
                    applicant_login=str(row.get('Логин', '')).strip() if pd.notna(row.get('Логин')) else None,
                    applicant_phone=str(row.get('ТЕЛЕФОН заявителя', '')).strip() if pd.notna(row.get('ТЕЛЕФОН заявителя')) else None,
                    application_date=application_date
                )
                
                db.session.add(student)
                imported_count += 1
                
                if imported_count % 50 == 0:
                    print(f"Импортировано {imported_count} студентов...")
                
            except Exception as e:
                print(f"Ошибка при обработке строки {index + 1}: {e}")
                db.session.rollback()  # Откатываем транзакцию
                continue
        
        # Сохраняем все изменения
        db.session.commit()
        print(f"\nИмпорт завершен! Всего импортировано: {imported_count} студентов")
        print(f"Кружков создано: {len(circles_dict)}")
        
        # Выводим информацию о созданных аккаунтах
        print("\n=== ДАННЫЕ ДЛЯ ВХОДА ===")
        print("Администратор: admin / admin123")
        print("\nПреподаватели:")
        teachers = User.query.filter_by(role='teacher').all()
        for teacher in teachers:
            circles = Circle.query.filter_by(teacher_id=teacher.id).all()
            circle_names = [c.name for c in circles]
            print(f"  {teacher.username} / teacher123 - {', '.join(circle_names)}")


if __name__ == '__main__':
    import_students_from_excel('/Users/nurlykhan/pets/cit_log/export.xlsx')

