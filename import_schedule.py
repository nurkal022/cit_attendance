"""
Скрипт импорта расписания кружков и учителей из Excel файла
"""
import pandas as pd
from app import app
from models import db, User, Circle, Schedule
from werkzeug.security import generate_password_hash
import re


def normalize_phone(phone):
    """Нормализует телефонный номер"""
    if pd.isna(phone):
        return None
    # Преобразуем в строку и убираем все нецифровые символы
    phone_str = str(int(phone)) if isinstance(phone, float) else str(phone)
    phone_str = re.sub(r'\D', '', phone_str)
    # Оставляем последние 10 цифр
    return phone_str[-10:] if len(phone_str) >= 10 else phone_str


def clean_teacher_name(full_name):
    """Очищает имя преподавателя от префиксов и лишних символов"""
    name = str(full_name).strip()
    
    # Удаляем префиксы в скобках и кавычках в начале
    prefixes_to_remove = [
        r'\(жеке сабақ\)\s*',
        r'АҚЫЛЫ\s+ағылшын тілі үйірмесі\s+',
        r'АҚЫЛЫ\s+',
        r'«[^»]+»\s+үйірмесі\s+',  # Включая "үйірмесі" после кавычек
        r'«[^»]+»\s+',
        r'"[^"]+"\s+',
        r'Lego Spike Robotics\s+',
    ]
    
    for prefix in prefixes_to_remove:
        name = re.sub(prefix, '', name, flags=re.IGNORECASE)
    
    # Удаляем телефоны в конце
    name = re.sub(r'\s+\d{4}\s+\d{3}-\d{2}-\d{2}$', '', name)
    
    return name.strip()


def transliterate_to_latin(text):
    """Транслитерация казахского/русского в латиницу"""
    # Полная таблица транслитерации
    cyrillic_to_latin = {
        # Русские буквы
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        
        # Казахские специфичные буквы
        'ә': 'a', 'і': 'i', 'ң': 'n', 'ғ': 'g', 'ү': 'u', 'ұ': 'u', 'қ': 'k', 'ө': 'o', 'һ': 'h',
        
        # Заглавные
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
        
        'Ә': 'A', 'І': 'I', 'Ң': 'N', 'Ғ': 'G', 'Ү': 'U', 'Ұ': 'U', 'Қ': 'K', 'Ө': 'O', 'Һ': 'H',
    }
    
    result = []
    for char in text:
        result.append(cyrillic_to_latin.get(char, char))
    
    return ''.join(result)


def create_username(full_name):
    """Создает username из полного имени на латинице"""
    # Очищаем имя от префиксов
    clean_name = clean_teacher_name(full_name)
    
    # Берем первое слово (фамилию)
    parts = clean_name.strip().split()
    if not parts:
        return 'teacher'
    
    surname = parts[0]
    
    # Транслитерируем в латиницу
    username = transliterate_to_latin(surname).lower()
    
    # Убираем все нелатинские символы и оставляем только буквы
    username = re.sub(r'[^a-z]', '', username)
    
    if not username:
        return 'teacher'
    
    return username


def import_schedule(excel_file):
    """Импортирует расписание из Excel файла"""
    print(f"Читаю файл {excel_file}...")
    df = pd.read_excel(excel_file)
    
    print(f"\nВсего записей в файле: {len(df)}")
    print(f"Колонки: {df.columns.tolist()}\n")
    
    with app.app_context():
        # Очищаем старые данные
        print("Очищаю старые данные...")
        Schedule.query.delete()
        Circle.query.delete()
        User.query.filter_by(role='teacher').delete()
        db.session.commit()
        
        # Собираем уникальных учителей
        teachers_data = df[['Имя преподавателя', 'Телефон преподавателя']].drop_duplicates()
        teachers_data = teachers_data.dropna(subset=['Имя преподавателя'])
        
        print(f"\nНайдено уникальных преподавателей: {len(teachers_data)}")
        
        # Создаем учителей
        teacher_map = {}  # {имя: user_id}
        
        for idx, row in teachers_data.iterrows():
            original_name = str(row['Имя преподавателя']).strip()
            clean_name = clean_teacher_name(original_name)
            phone = normalize_phone(row['Телефон преподавателя'])
            
            # Создаем username
            base_username = create_username(original_name)
            username = base_username
            counter = 1
            
            # Проверяем уникальность username
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            # Создаем учителя
            teacher = User(
                username=username,
                password=generate_password_hash('12345'),  # Дефолтный пароль
                full_name=clean_name,  # Используем очищенное имя
                role='teacher'
            )
            db.session.add(teacher)
            db.session.flush()  # Получаем ID
            
            # Используем original_name для маппинга, т.к. в Excel оригинальное имя
            teacher_map[original_name] = teacher.id
            print(f"✓ Создан учитель: {clean_name} (логин: {username}, пароль: 12345)")
        
        db.session.commit()
        print(f"\nСоздано учителей: {len(teacher_map)}")
        
        # Собираем уникальные кружки
        circles_data = df.groupby(['Название кружка', 'Имя преподавателя']).first().reset_index()
        
        print(f"\nНайдено уникальных кружков: {len(circles_data)}")
        
        circle_map = {}  # {(название, учитель): circle_id}
        
        for idx, row in circles_data.iterrows():
            circle_name = str(row['Название кружка']).strip()
            teacher_name = str(row['Имя преподавателя']).strip()
            
            teacher_id = teacher_map.get(teacher_name)
            
            # Создаем кружок
            circle = Circle(
                name=circle_name,
                direction='',  # Можно добавить позже
                teacher_id=teacher_id
            )
            db.session.add(circle)
            db.session.flush()  # Получаем ID
            
            circle_map[(circle_name, teacher_name)] = circle.id
            print(f"✓ Создан кружок: {circle_name} (преподаватель: {teacher_name})")
        
        db.session.commit()
        print(f"\nСоздано кружков: {len(circle_map)}")
        
        # Импортируем расписание
        print(f"\nИмпортирую расписание...")
        schedule_count = 0
        
        for idx, row in df.iterrows():
            circle_name = str(row['Название кружка']).strip()
            teacher_name = str(row['Имя преподавателя']).strip()
            
            circle_id = circle_map.get((circle_name, teacher_name))
            if not circle_id:
                print(f"! Пропуск строки {idx}: кружок не найден")
                continue
            
            day_of_week = str(row['День недели']).strip() if pd.notna(row['День недели']) else None
            group_number = str(row['Группа']).strip() if pd.notna(row['Группа']) else None
            time_slot = str(row['Время занятий']).strip() if pd.notna(row['Время занятий']) else None
            room = str(row['Кабинет']).strip() if pd.notna(row['Кабинет']) else None
            floor = str(row['Этаж']).strip() if pd.notna(row['Этаж']) else None
            
            # Создаем запись расписания
            schedule = Schedule(
                circle_id=circle_id,
                day_of_week=day_of_week,
                group_number=group_number,
                time_slot=time_slot,
                room=room,
                floor=floor
            )
            db.session.add(schedule)
            schedule_count += 1
            
            if (idx + 1) % 50 == 0:
                print(f"  Обработано {idx + 1} записей...")
        
        db.session.commit()
        print(f"\n✓ Создано записей расписания: {schedule_count}")
        
        # Итоговая статистика
        print("\n" + "="*50)
        print("ИТОГО:")
        print(f"  Преподавателей: {len(teacher_map)}")
        print(f"  Кружков: {len(circle_map)}")
        print(f"  Записей расписания: {schedule_count}")
        print("="*50)
        
        # Показываем первых 5 учителей с их данными
        print("\nПримеры созданных учителей:")
        teachers = User.query.filter_by(role='teacher').limit(5).all()
        for t in teachers:
            circles_count = len(t.circles)
            print(f"  - {t.full_name} (логин: {t.username}, кружков: {circles_count})")


if __name__ == '__main__':
    import_schedule('Расписание_кружков.xlsx')

