"""
Скрипт импорта учеников из Excel файла
Связывает учеников с кружками по полям "Кружок (по расписанию)" и "Группа (по расписанию)"
"""
import pandas as pd
from app import app
from models import db, Circle, Student, Schedule
from datetime import datetime
from sqlalchemy import func
import re


def normalize_circle_name(name):
    """Нормализует название кружка для поиска"""
    if pd.isna(name):
        return None
    name = str(name).strip()
    # Убираем лишние пробелы (нормализуем все пробелы до одного)
    name = re.sub(r'\s+', ' ', name)
    # Убираем пробелы в начале и конце
    name = name.strip()
    return name


def find_circle_by_name(circle_name):
    """Находит кружок по названию (с учетом возможных различий)"""
    if not circle_name:
        return None
    
    normalized_search = normalize_circle_name(circle_name)
    
    # Сначала пробуем точное совпадение
    circle = Circle.query.filter_by(name=circle_name).first()
    if circle:
        return circle
    
    # Поиск по нормализованному названию
    all_circles = Circle.query.all()
    for c in all_circles:
        normalized_db = normalize_circle_name(c.name)
        if normalized_db == normalized_search:
            return c
    
    # Поиск по частичному совпадению (нормализованное)
    matching_circles = []
    for c in all_circles:
        normalized_db = normalize_circle_name(c.name)
        if normalized_search in normalized_db or normalized_db in normalized_search:
            matching_circles.append(c)
    
    if len(matching_circles) == 1:
        return matching_circles[0]
    
    # Если несколько совпадений, берем самое точное
    if matching_circles:
        # Сортируем по длине совпадения (берем самое короткое - более точное)
        best_match = min(matching_circles, key=lambda c: len(normalize_circle_name(c.name)))
        return best_match
    
    return None


def parse_date(date_str):
    """Парсит дату из строки"""
    if pd.isna(date_str):
        return None
    
    if isinstance(date_str, datetime):
        return date_str.date()
    
    if isinstance(date_str, str):
        try:
            # Пробуем разные форматы
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except:
                    continue
        except:
            pass
    
    return None


def normalize_phone(phone):
    """Нормализует телефонный номер"""
    if pd.isna(phone):
        return None
    phone_str = str(phone).strip()
    # Убираем все нецифровые символы кроме +
    phone_str = re.sub(r'[^\d+]', '', phone_str)
    return phone_str if phone_str else None


def import_students(excel_file):
    """Импортирует учеников из Excel файла"""
    print(f"Читаю файл {excel_file}...")
    df = pd.read_excel(excel_file)
    
    print(f"\nВсего записей в файле: {len(df)}")
    
    # Фильтруем только записи с заполненным "Кружок (по расписанию)"
    df_valid = df[df['Кружок (по расписанию)'].notna()].copy()
    print(f"Записей с заполненным кружком: {len(df_valid)}")
    print(f"Записей без кружка (пропустим): {len(df) - len(df_valid)}\n")
    
    with app.app_context():
        # Статистика
        stats = {
            'imported': 0,
            'skipped_no_circle': 0,
            'skipped_duplicate': 0,
            'errors': 0,
            'circles_not_found': set()
        }
        
        # Словарь для отслеживания дубливания дубликатов
        existing_students = {}
        for student in Student.query.all():
            key = (student.iin, student.full_name)
            existing_students[key] = student
        
        print("Начинаю импорт...\n")
        
        for idx, row in df_valid.iterrows():
            try:
                # Основные данные ученика
                full_name = str(row['ФИО']).strip() if pd.notna(row['ФИО']) else None
                iin = str(row['ИИН']).strip() if pd.notna(row['ИИН']) else None
                
                if not full_name:
                    stats['skipped_no_circle'] += 1
                    continue
                
                # Проверка на дубликат
                key = (iin, full_name)
                if key in existing_students:
                    # Обновляем существующего студента (если нужно)
                    student = existing_students[key]
                    # Проверяем, нужно ли обновить кружок
                    circle_name = normalize_circle_name(row['Кружок (по расписанию)'])
                    circle = find_circle_by_name(circle_name)
                    if circle and student.circle_id != circle.id:
                        # Обновляем кружок
                        student.circle_id = circle.id
                        db.session.commit()
                        print(f"✓ Обновлен кружок для: {full_name[:50]}")
                    else:
                        stats['skipped_duplicate'] += 1
                    continue
                
                # Находим кружок
                circle_name = normalize_circle_name(row['Кружок (по расписанию)'])
                circle = find_circle_by_name(circle_name)
                
                if not circle:
                    stats['circles_not_found'].add(circle_name)
                    stats['skipped_no_circle'] += 1
                    if len(stats['circles_not_found']) <= 5:
                        print(f"! Кружок не найден: {circle_name}")
                    continue
                
                # Создаем студента
                student = Student(
                    full_name=full_name,
                    iin=iin if iin else None,
                    gender=str(row['ПОЛ']).strip() if pd.notna(row['ПОЛ']) else None,
                    address=str(row['АДРЕС']).strip() if pd.notna(row['АДРЕС']) else None,
                    school=str(row['С КАКОЙ ШКОЛЫ']).strip() if pd.notna(row['С КАКОЙ ШКОЛЫ']) else None,
                    grade=str(row['В КАКОМ КЛАССЕ ОБУЧАЕТСЯ']).strip() if pd.notna(row['В КАКОМ КЛАССЕ ОБУЧАЕТСЯ']) else None,
                    direction=str(row['ПО КАКОМУ НАПРАВЛЕНИЮ']).strip() if pd.notna(row['ПО КАКОМУ НАПРАВЛЕНИЮ']) else None,
                    circle_id=circle.id,
                    # Данные заявителя
                    applicant_name=str(row['ФИО заявителя']).strip() if pd.notna(row['ФИО заявителя']) else None,
                    applicant_iin=str(row['ИИН заявителя']).strip() if pd.notna(row['ИИН заявителя']) else None,
                    applicant_login=str(row['Логин']).strip() if pd.notna(row['Логин']) else None,
                    applicant_phone=normalize_phone(row['ТЕЛЕФОН заявителя']),
                    application_date=parse_date(row['Дата подачи'])
                )
                
                db.session.add(student)
                existing_students[key] = student
                stats['imported'] += 1
                
                if stats['imported'] % 50 == 0:
                    db.session.commit()
                    print(f"  Обработано {stats['imported']} учеников...")
                
            except Exception as e:
                stats['errors'] += 1
                print(f"! Ошибка в строке {idx}: {e}")
                continue
        
        # Финальный коммит
        db.session.commit()
        
        # Итоговая статистика
        print("\n" + "="*70)
        print("ИТОГО ИМПОРТА:")
        print("="*70)
        print(f"  ✓ Импортировано новых учеников: {stats['imported']}")
        print(f"  ⊘ Пропущено дубликатов: {stats['skipped_duplicate']}")
        print(f"  ⊘ Пропущено без кружка: {stats['skipped_no_circle']}")
        print(f"  ✗ Ошибок: {stats['errors']}")
        
        if stats['circles_not_found']:
            print(f"\n  ⚠ Кружки не найдены ({len(stats['circles_not_found'])}):")
            for circle_name in list(stats['circles_not_found'])[:10]:
                print(f"     - {circle_name}")
            if len(stats['circles_not_found']) > 10:
                print(f"     ... и еще {len(stats['circles_not_found']) - 10}")
        
        print("="*70)
        
        # Статистика по кружкам
        print("\nСТАТИСТИКА ПО КРУЖКАМ:")
        circles_stats = db.session.query(
            Circle.name,
            func.count(Student.id).label('students_count')
        ).join(Student).group_by(Circle.id, Circle.name).order_by(
            func.count(Student.id).desc()
        ).limit(10).all()
        
        for circle_name, count in circles_stats:
            print(f"  {circle_name[:50]:50} - {count} учеников")


if __name__ == '__main__':
    import_students('export_ученики_под_расписание.xlsx')

