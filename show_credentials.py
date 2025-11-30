"""
Скрипт для отображения логинов и паролей преподавателей по кружкам
"""
from app import app, db
from models import Circle, User


def show_credentials():
    """Показать таблицу с кружками и учетными данными"""
    
    with app.app_context():
        print("\n" + "="*100)
        print("  УЧЕТНЫЕ ДАННЫЕ ПРЕПОДАВАТЕЛЕЙ ПО КРУЖКАМ")
        print("="*100 + "\n")
        
        # Получаем все кружки с преподавателями
        circles = Circle.query.order_by(Circle.name).all()
        
        # Группируем по преподавателям
        teacher_circles = {}
        for circle in circles:
            if circle.teacher:
                teacher_id = circle.teacher.id
                if teacher_id not in teacher_circles:
                    teacher_circles[teacher_id] = {
                        'teacher': circle.teacher,
                        'circles': []
                    }
                teacher_circles[teacher_id]['circles'].append(circle.name)
        
        # Выводим таблицу
        print(f"{'№':<5} {'ЛОГИН':<15} {'ПАРОЛЬ':<15} {'КРУЖОК'}")
        print("-"*100)
        
        counter = 1
        for teacher_id, data in sorted(teacher_circles.items(), key=lambda x: x[1]['teacher'].username):
            teacher = data['teacher']
            circles_list = data['circles']
            
            # Первая строка с логином/паролем
            print(f"{counter:<5} {teacher.username:<15} teacher123      {circles_list[0]}")
            
            # Остальные кружки этого преподавателя
            for circle_name in circles_list[1:]:
                print(f"{'':5} {'':15} {'':15} {circle_name}")
            
            print("-"*100)
            counter += 1
        
        print(f"\nВсего преподавателей: {len(teacher_circles)}")
        print(f"Всего кружков: {len(circles)}")
        print("\n⚠️  ВСЕ ПАРОЛИ: teacher123\n")
        
        # Сохраняем в файл
        with open('CREDENTIALS.txt', 'w', encoding='utf-8') as f:
            f.write("="*100 + "\n")
            f.write("  УЧЕТНЫЕ ДАННЫЕ ПРЕПОДАВАТЕЛЕЙ ПО КРУЖКАМ\n")
            f.write("="*100 + "\n\n")
            
            f.write(f"{'№':<5} {'ЛОГИН':<15} {'ПАРОЛЬ':<15} {'КРУЖОК'}\n")
            f.write("-"*100 + "\n")
            
            counter = 1
            for teacher_id, data in sorted(teacher_circles.items(), key=lambda x: x[1]['teacher'].username):
                teacher = data['teacher']
                circles_list = data['circles']
                
                f.write(f"{counter:<5} {teacher.username:<15} teacher123      {circles_list[0]}\n")
                
                for circle_name in circles_list[1:]:
                    f.write(f"{'':5} {'':15} {'':15} {circle_name}\n")
                
                f.write("-"*100 + "\n")
                counter += 1
            
            f.write(f"\nВсего преподавателей: {len(teacher_circles)}\n")
            f.write(f"Всего кружков: {len(circles)}\n")
            f.write("\n⚠️  ВСЕ ПАРОЛИ: teacher123\n")
            f.write("\n\nАДМИНИСТРАТОР:\n")
            f.write("Логин: admin\n")
            f.write("Пароль: admin123\n")
        
        print("✅ Данные сохранены в файл CREDENTIALS.txt\n")


if __name__ == '__main__':
    show_credentials()

