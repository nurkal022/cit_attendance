"""
Скрипт для генерации демонстрационных данных посещаемости
с 1 сентября по 24 октября 2024
"""
import random
from datetime import date, timedelta
from app import app, db
from models import Student, Circle, Attendance, User

def generate_demo_attendance():
    """Генерация рандомной посещаемости для демонстрации"""
    
    print("Начинаем генерацию демонстрационных данных посещаемости...")
    
    with app.app_context():
        # Удаляем старые записи посещений
        Attendance.query.delete()
        db.session.commit()
        print("Старые записи посещаемости удалены")
        
        # Получаем все кружки
        circles = Circle.query.all()
        print(f"Найдено кружков: {len(circles)}")
        
        # Период: 1 сентября - 24 октября 2025 (текущий учебный год)
        start_date = date(2025, 9, 1)
        end_date = date(2025, 10, 24)
        
        total_generated = 0
        
        for circle in circles:
            students = Student.query.filter_by(circle_id=circle.id).all()
            if not students:
                continue
            
            print(f"\nОбрабатываем кружок: {circle.name}")
            print(f"  Студентов: {len(students)}")
            
            # Определяем рандомную посещаемость для этого кружка (60-100%)
            base_attendance_rate = random.uniform(0.6, 1.0)
            print(f"  Базовая посещаемость: {base_attendance_rate * 100:.1f}%")
            
            # Получаем преподавателя (для marked_by)
            teacher_id = circle.teacher_id if circle.teacher_id else None
            
            # Проходим по каждому дню
            current_date = start_date
            days_count = 0
            
            while current_date <= end_date:
                # Пропускаем воскресенья (день 6 в Python)
                if current_date.weekday() == 6:
                    current_date += timedelta(days=1)
                    continue
                
                days_count += 1
                
                # Для каждого студента определяем, пришел ли он
                for student in students:
                    # Добавляем небольшую рандомность (±10%)
                    attendance_rate = base_attendance_rate + random.uniform(-0.1, 0.1)
                    attendance_rate = max(0.5, min(1.0, attendance_rate))  # Ограничиваем 50-100%
                    
                    # Определяем статус
                    rand_val = random.random()
                    if rand_val < attendance_rate:
                        status = 'present'
                    elif rand_val < attendance_rate + 0.05:  # 5% уважительных
                        status = 'excused'
                    else:
                        status = 'absent'
                    
                    # Создаем запись посещения
                    attendance = Attendance(
                        student_id=student.id,
                        circle_id=circle.id,
                        date=current_date,
                        status=status,
                        marked_by=teacher_id
                    )
                    db.session.add(attendance)
                    total_generated += 1
                
                # Коммитим после каждого дня для оптимизации
                if days_count % 5 == 0:
                    db.session.commit()
                
                current_date += timedelta(days=1)
            
            db.session.commit()
            print(f"  Обработано дней: {days_count}")
        
        print(f"\n✅ Генерация завершена!")
        print(f"Всего создано записей посещаемости: {total_generated}")
        
        # Статистика
        total_present = Attendance.query.filter_by(status='present').count()
        total_absent = Attendance.query.filter_by(status='absent').count()
        total_excused = Attendance.query.filter_by(status='excused').count()
        total = total_present + total_absent + total_excused
        
        if total > 0:
            print(f"\nСтатистика:")
            print(f"  Присутствовали: {total_present} ({total_present/total*100:.1f}%)")
            print(f"  Отсутствовали: {total_absent} ({total_absent/total*100:.1f}%)")
            print(f"  Уважительная: {total_excused} ({total_excused/total*100:.1f}%)")
            print(f"  Общая посещаемость: {(total_present+total_excused)/total*100:.1f}%")


if __name__ == '__main__':
    response = input("Это удалит ВСЕ существующие записи посещаемости и создаст новые демо-данные. Продолжить? (yes/no): ")
    if response.lower() in ['yes', 'y', 'да', 'д']:
        generate_demo_attendance()
    else:
        print("Отменено")

