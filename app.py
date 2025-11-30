"""
Flask приложение для системы учета посещаемости
Центр инновационного творчества школьников
"""
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date, timedelta
from sqlalchemy import func, extract, case
import calendar
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

from models import db, User, Circle, Student, Attendance, Schedule

# Русские названия месяцев
MONTH_NAMES_RU = {
    1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
    5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
    9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cit-attendance-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Flask-Login настройка
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===== АУТЕНТИФИКАЦИЯ =====

@app.route('/')
def index():
    """Главная страница - О нашем центре"""
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('teacher_dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Неверный логин или пароль', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Выход"""
    logout_user()
    return redirect(url_for('login'))


# ===== АДМИН ПАНЕЛЬ =====

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Админ дашборд с статистикой (оптимизированный)"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Общая статистика (оптимизированные запросы)
    total_students = db.session.query(func.count(Student.id)).scalar()
    total_circles = db.session.query(func.count(Circle.id)).scalar()
    total_teachers = db.session.query(func.count(User.id)).filter(User.role == 'teacher').scalar()
    
    # Статистика посещаемости за текущий месяц
    today = date.today()
    first_day = today.replace(day=1)
    
    # Оптимизированный запрос со счетчиками
    month_stats = db.session.query(
        func.count(Attendance.id).label('total'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present'),
        func.sum(case((Attendance.status == 'absent', 1), else_=0)).label('absent'),
        func.sum(case((Attendance.status == 'excused', 1), else_=0)).label('excused')
    ).filter(Attendance.date >= first_day).first()
    
    total_marks = month_stats.total or 0
    present_count = int(month_stats.present or 0)
    absent_count = int(month_stats.absent or 0)
    excused_count = int(month_stats.excused or 0)
    
    attendance_rate = round((present_count / total_marks * 100) if total_marks > 0 else 0, 1)
    
    # Данные для линейного графика (последние 30 дней)
    days_back = 30
    date_from = today - timedelta(days=days_back)
    
    daily_stats = db.session.query(
        Attendance.date,
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present'),
        func.sum(case((Attendance.status == 'absent', 1), else_=0)).label('absent')
    ).filter(
        Attendance.date >= date_from
    ).group_by(Attendance.date).order_by(Attendance.date).all()
    
    chart_labels = [stat.date.strftime('%d.%m') for stat in daily_stats]
    chart_present = [int(stat.present) for stat in daily_stats]
    chart_absent = [int(stat.absent) for stat in daily_stats]
    
    # ТОП-5 кружков по посещаемости
    top_circles = db.session.query(
        Circle.name,
        func.count(Attendance.id).label('total'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present')
    ).join(Attendance, Attendance.circle_id == Circle.id)\
     .filter(Attendance.date >= first_day)\
     .group_by(Circle.id, Circle.name)\
     .having(func.count(Attendance.id) > 10)\
     .order_by((func.cast(func.sum(case((Attendance.status == 'present', 1), else_=0)), db.Float) / func.count(Attendance.id)).desc())\
     .limit(5).all()
    
    top_circle_names = [c.name[:30] for c in top_circles]
    top_circle_rates = [round((int(c.present) / c.total * 100) if c.total > 0 else 0, 1) for c in top_circles]
    
    # Статистика по направлениям
    direction_stats = db.session.query(
        Circle.direction,
        func.count(Student.id).label('students')
    ).join(Student, Student.circle_id == Circle.id)\
     .filter(Circle.direction.isnot(None), Circle.direction != '')\
     .group_by(Circle.direction)\
     .order_by(func.count(Student.id).desc())\
     .limit(10).all()
    
    direction_labels = [d.direction[:20] if d.direction else 'Другое' for d in direction_stats]
    direction_values = [d.students for d in direction_stats]
    
    return render_template('admin/dashboard.html',
                         total_students=total_students,
                         total_circles=total_circles,
                         total_teachers=total_teachers,
                         attendance_rate=attendance_rate,
                         present_count=present_count,
                         absent_count=absent_count,
                         excused_count=excused_count,
                         total_marks=total_marks,
                         chart_labels=chart_labels,
                         chart_present=chart_present,
                         chart_absent=chart_absent,
                         top_circle_names=top_circle_names,
                         top_circle_rates=top_circle_rates,
                         direction_labels=direction_labels,
                         direction_values=direction_values)


@app.route('/admin/teachers')
@login_required
def admin_teachers():
    """Управление преподавателями"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    teachers = User.query.filter_by(role='teacher').all()
    return render_template('admin/teachers.html', teachers=teachers)


@app.route('/admin/teachers/add', methods=['POST'])
@login_required
def admin_add_teacher():
    """Добавить преподавателя"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    username = request.form.get('username')
    password = request.form.get('password')
    full_name = request.form.get('full_name')
    
    if User.query.filter_by(username=username).first():
        flash('Пользователь с таким логином уже существует', 'error')
        return redirect(url_for('admin_teachers'))
    
    teacher = User(
        username=username,
        password=generate_password_hash(password),
        plain_password=password,
        full_name=full_name,
        role='teacher'
    )
    
    db.session.add(teacher)
    db.session.commit()
    
    flash(f'Преподаватель {username} успешно добавлен', 'success')
    return redirect(url_for('admin_teachers'))


@app.route('/admin/teachers/<int:teacher_id>/delete', methods=['POST'])
@login_required
def admin_delete_teacher(teacher_id):
    """Удалить преподавателя"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    teacher = User.query.get_or_404(teacher_id)
    
    if teacher.role != 'teacher':
        flash('Нельзя удалить этого пользователя', 'error')
        return redirect(url_for('admin_teachers'))
    
    # Обнуляем teacher_id у всех кружков
    Circle.query.filter_by(teacher_id=teacher_id).update({'teacher_id': None})
    
    db.session.delete(teacher)
    db.session.commit()
    
    flash('Преподаватель удален', 'success')
    return redirect(url_for('admin_teachers'))


@app.route('/admin/teachers/<int:teacher_id>/reset-password', methods=['POST'])
@login_required
def admin_reset_password(teacher_id):
    """Сбросить пароль преподавателя"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    teacher = User.query.get_or_404(teacher_id)
    new_password = request.form.get('new_password')
    
    teacher.password = generate_password_hash(new_password)
    teacher.plain_password = new_password
    db.session.commit()
    
    flash(f'Пароль для {teacher.username} изменен', 'success')
    return redirect(url_for('admin_teachers'))


@app.route('/admin/circles')
@login_required
def admin_circles():
    """Управление кружками"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    circles = Circle.query.all()
    teachers = User.query.filter_by(role='teacher').all()
    return render_template('admin/circles.html', circles=circles, teachers=teachers)


@app.route('/admin/circles/add', methods=['POST'])
@login_required
def admin_add_circle():
    """Добавить кружок"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    name = request.form.get('name')
    direction = request.form.get('direction')
    teacher_id = request.form.get('teacher_id')
    
    circle = Circle(
        name=name,
        direction=direction,
        teacher_id=int(teacher_id) if teacher_id else None
    )
    
    db.session.add(circle)
    db.session.commit()
    
    flash(f'Кружок "{name}" успешно добавлен', 'success')
    return redirect(url_for('admin_circles'))


@app.route('/admin/circles/<int:circle_id>/edit', methods=['POST'])
@login_required
def admin_edit_circle(circle_id):
    """Редактировать кружок"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    circle = Circle.query.get_or_404(circle_id)
    
    circle.name = request.form.get('name')
    circle.direction = request.form.get('direction')
    teacher_id = request.form.get('teacher_id')
    circle.teacher_id = int(teacher_id) if teacher_id else None
    
    db.session.commit()
    
    flash(f'Кружок "{circle.name}" обновлен', 'success')
    return redirect(url_for('admin_circles'))


@app.route('/admin/circles/<int:circle_id>/delete', methods=['POST'])
@login_required
def admin_delete_circle(circle_id):
    """Удалить кружок"""
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    
    circle = Circle.query.get_or_404(circle_id)
    
    # Удаляем всех студентов кружка
    Student.query.filter_by(circle_id=circle_id).delete()
    
    db.session.delete(circle)
    db.session.commit()
    
    flash('Кружок удален', 'success')
    return redirect(url_for('admin_circles'))


@app.route('/admin/students')
@login_required
def admin_students():
    """Список всех студентов"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    circle_id = request.args.get('circle_id', type=int)
    
    if circle_id:
        students = Student.query.filter_by(circle_id=circle_id).all()
        circle = Circle.query.get(circle_id)
    else:
        students = Student.query.all()
        circle = None
    
    circles = Circle.query.all()
    
    return render_template('admin/students.html', students=students, circles=circles, selected_circle=circle)


@app.route('/admin/schedule')
@login_required
def admin_schedule():
    """Расписание всех кружков - отдельная таблица для каждого кружка"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    # Дни недели на казахском
    days_order = ['Дүйсенбі', 'Сейсенбі', 'Сәрсенбі', 'Бейсенбі', 'Жұма', 'Сенбі']
    
    # Получаем все кружки с расписанием
    circles = Circle.query.order_by(Circle.name).all()
    
    # Функция парсинга времени
    def parse_time(time_str):
        """Парсит время из строки типа '9:00-10:20' или '8:30 -10:00'"""
        if not time_str:
            return (0, 0)
        time_part = time_str.split('-')[0].strip()
        try:
            parts = time_part.replace(' ', '').split(':')
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
        except:
            pass
        return (0, 0)
    
    # Группируем расписание по кружкам
    circles_schedules = []
    
    for circle in circles:
        schedules = Schedule.query.filter_by(circle_id=circle.id).all()
        
        if not schedules:
            continue
        
        # Группируем по дням и времени
        schedule_dict = {}
        for schedule in schedules:
            day = schedule.day_of_week
            if not day:
                continue
                
            if day not in schedule_dict:
                schedule_dict[day] = {}
            
            time_slot = schedule.time_slot or ''
            if time_slot not in schedule_dict[day]:
                schedule_dict[day][time_slot] = []
            
            schedule_dict[day][time_slot].append({
                'group': schedule.group_number or '',
                'room': schedule.room or '',
                'floor': schedule.floor or '',
                'time': time_slot,
            })
        
        # Получаем все временные слоты для этого кружка
        all_times = set()
        for day_schedules in schedule_dict.values():
            all_times.update(day_schedules.keys())
        
        sorted_times = sorted(all_times, key=parse_time)
        
        circles_schedules.append({
            'circle': circle,
            'schedule_dict': schedule_dict,
            'sorted_times': sorted_times,
            'teacher': circle.teacher.full_name if circle.teacher else 'Не назначен'
        })
    
    return render_template('admin/schedule.html',
                         circles_schedules=circles_schedules,
                         days_order=days_order)


@app.route('/admin/schedule/export-pdf')
@login_required
def admin_schedule_export_pdf():
    """Экспорт расписания кружков в PDF"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    # Регистрируем шрифт с поддержкой кириллицы
    font_name = 'Helvetica'  # По умолчанию
    font_name_bold = 'Helvetica-Bold'
    
    try:
        # Пробуем использовать Arial Unicode MS (если доступен)
        arial_unicode_paths = [
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            '/Library/Fonts/Arial Unicode.ttf',
            '/System/Library/Fonts/Arial Unicode.ttf',
        ]
        
        font_registered = False
        for font_path in arial_unicode_paths:
            try:
                if os.path.exists(font_path):
                    # Регистрируем обычный и жирный варианты
                    pdfmetrics.registerFont(TTFont('ArialUnicode', font_path))
                    pdfmetrics.registerFont(TTFont('ArialUnicode-Bold', font_path))
                    font_registered = True
                    font_name = 'ArialUnicode'
                    font_name_bold = 'ArialUnicode-Bold'
                    break
            except Exception as e:
                continue
        
    except Exception as e:
        # В случае ошибки используем стандартный шрифт
        pass
    
    # Дни недели на казахском
    days_order = ['Дүйсенбі', 'Сейсенбі', 'Сәрсенбі', 'Бейсенбі', 'Жұма', 'Сенбі']
    
    # Получаем все кружки с расписанием (та же логика что и в admin_schedule)
    circles = Circle.query.order_by(Circle.name).all()
    
    def parse_time(time_str):
        if not time_str:
            return (0, 0)
        time_part = time_str.split('-')[0].strip()
        try:
            parts = time_part.replace(' ', '').split(':')
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
        except:
            pass
        return (0, 0)
    
    circles_schedules = []
    for circle in circles:
        schedules = Schedule.query.filter_by(circle_id=circle.id).all()
        if not schedules:
            continue
        
        schedule_dict = {}
        for schedule in schedules:
            day = schedule.day_of_week
            if not day:
                continue
            if day not in schedule_dict:
                schedule_dict[day] = {}
            time_slot = schedule.time_slot or ''
            if time_slot not in schedule_dict[day]:
                schedule_dict[day][time_slot] = []
            schedule_dict[day][time_slot].append({
                'group': schedule.group_number or '',
                'room': schedule.room or '',
                'floor': schedule.floor or '',
                'time': time_slot,
            })
        
        all_times = set()
        for day_schedules in schedule_dict.values():
            all_times.update(day_schedules.keys())
        sorted_times = sorted(all_times, key=parse_time)
        
        circles_schedules.append({
            'circle': circle,
            'schedule_dict': schedule_dict,
            'sorted_times': sorted_times,
            'teacher': circle.teacher.full_name if circle.teacher else 'Не назначен'
        })
    
    # Создаем PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                           rightMargin=15*mm, leftMargin=15*mm,
                           topMargin=15*mm, bottomMargin=15*mm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Используем зарегистрированные имена шрифтов
    font_name_normal = font_name
    
    # Стили с поддержкой кириллицы
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name_bold,
        fontSize=18,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=8,
        alignment=1,  # CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=font_name_bold,
        fontSize=14,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=4,
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name_normal,
        fontSize=10,
    )
    
    # Заголовок документа
    story.append(Paragraph("Расписание кружков", title_style))
    story.append(Paragraph(f"Дата экспорта: {datetime.now().strftime('%d.%m.%Y %H:%M')}", normal_style))
    story.append(Spacer(1, 8*mm))
    
    # Для каждого кружка создаем таблицу
    for circle_data in circles_schedules:
        circle = circle_data['circle']
        schedule_dict = circle_data['schedule_dict']
        sorted_times = circle_data['sorted_times']
        teacher = circle_data['teacher']
        
        # Заголовок кружка
        circle_title = f"{circle.name}"
        if circle.direction:
            circle_title += f" ({circle.direction})"
        story.append(Paragraph(circle_title, heading_style))
        story.append(Paragraph(f"<b>Преподаватель:</b> {teacher}", normal_style))
        story.append(Spacer(1, 6*mm))
        
        if sorted_times:
            # Создаем стили для ячеек таблицы с поддержкой кириллицы
            cell_style_normal = ParagraphStyle(
                'CellNormal',
                fontName=font_name_normal,
                fontSize=7,
                leading=8,
                alignment=1,  # CENTER
            )
            
            cell_style_bold = ParagraphStyle(
                'CellBold',
                fontName=font_name_bold,
                fontSize=7,
                leading=8,
                alignment=1,  # CENTER
            )
            
            cell_style_time = ParagraphStyle(
                'CellTime',
                fontName=font_name_bold,
                fontSize=8,
                leading=10,
                alignment=1,  # CENTER
            )
            
            # Заголовок таблицы с Paragraph для кириллицы
            header_row = [Paragraph('<b>Время</b>', cell_style_time)]
            for day in days_order:
                header_row.append(Paragraph(f'<b>{day}</b>', cell_style_bold))
            table_data = [header_row]
            
            # Данные таблицы
            for time_slot in sorted_times:
                row = [Paragraph(time_slot, cell_style_time)]
                for day in days_order:
                    if day in schedule_dict and time_slot in schedule_dict[day]:
                        cell_parts = []
                        for item in schedule_dict[day][time_slot]:
                            parts = []
                            if item['group']:
                                parts.append(f"<b>Гр. {item['group']}</b>")
                            if item['room']:
                                room_info = f"Каб. {item['room']}"
                                if item['floor']:
                                    room_info += f"<br/>({item['floor']})"
                                parts.append(room_info)
                            cell_parts.append("<br/>".join(parts))
                        cell_text = "<br/><br/>".join(cell_parts)
                        row.append(Paragraph(cell_text, cell_style_normal))
                    else:
                        row.append(Paragraph("—", cell_style_normal))
                table_data.append(row)
            
            # Создаем таблицу с улучшенным дизайном
            table = Table(table_data, colWidths=[28*mm] + [32*mm] * len(days_order))
            table.setStyle(TableStyle([
                # Заголовок таблицы
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 0), (-1, 0), 12),
                # Данные таблицы
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#0d6efd')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                # Выделение колонки времени
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#e7f3ff')),
                ('LINEAFTER', (0, 0), (0, -1), 1.5, colors.HexColor('#0d6efd')),
            ]))
            
            story.append(table)
        else:
            story.append(Paragraph("Расписание не заполнено", normal_style))
        
        story.append(Spacer(1, 10*mm))
        
        # Разрыв страницы между кружками (кроме последнего)
        if circle_data != circles_schedules[-1]:
            story.append(PageBreak())
    
    # Строим PDF
    doc.build(story)
    
    # Возвращаем PDF как ответ
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=raspisanie_kruzhkov_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    
    return response


@app.route('/admin/attendance/export-pdf')
@login_required
def admin_attendance_export_pdf():
    """Экспорт посещаемости кружка в PDF"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    # Получаем параметры
    circle_id = request.args.get('circle_id', type=int)
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    
    if not circle_id:
        flash('Кружок не выбран', 'error')
        return redirect(url_for('admin_attendance'))
    
    circle = Circle.query.get_or_404(circle_id)
    
    # Получаем расписание кружка
    schedules = Schedule.query.filter_by(circle_id=circle_id).all()
    
    # Определяем дни недели, когда есть занятия
    schedule_days = set()
    day_mapping = {
        'Дүйсенбі': 0,
        'Сейсенбі': 1,
        'Сәрсенбі': 2,
        'Бейсенбі': 3,
        'Жұма': 4,
        'Сенбі': 5,
    }
    
    for schedule in schedules:
        if schedule.day_of_week and schedule.day_of_week in day_mapping:
            schedule_days.add(day_mapping[schedule.day_of_week])
    
    # Получаем данные за месяц
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Генерируем только дни с занятиями
    dates_to_show = []
    current_date = first_day
    while current_date <= last_day:
        if current_date.weekday() in schedule_days:
            dates_to_show.append(current_date)
        current_date += timedelta(days=1)
    
    students = Student.query.filter_by(circle_id=circle_id).order_by(Student.full_name).all()
    
    # Получаем все посещения за месяц
    attendances = Attendance.query.filter(
        Attendance.circle_id == circle_id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).all()
    
    # Группируем по студентам и датам
    attendance_dict = {}
    for a in attendances:
        if a.student_id not in attendance_dict:
            attendance_dict[a.student_id] = {}
        attendance_dict[a.student_id][a.date] = a
    
    # Русские названия дней недели
    weekdays_ru = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среда',
        3: 'Четверг',
        4: 'Пятница',
        5: 'Суббота',
        6: 'Воскресенье'
    }
    
    # Регистрируем шрифт с поддержкой кириллицы
    font_name = 'Helvetica'
    font_name_bold = 'Helvetica-Bold'
    
    try:
        arial_unicode_paths = [
            '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
            '/Library/Fonts/Arial Unicode.ttf',
            '/System/Library/Fonts/Arial Unicode.ttf',
        ]
        
        font_registered = False
        for font_path in arial_unicode_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('ArialUnicode', font_path))
                    pdfmetrics.registerFont(TTFont('ArialUnicode-Bold', font_path))
                    font_registered = True
                    font_name = 'ArialUnicode'
                    font_name_bold = 'ArialUnicode-Bold'
                    break
            except Exception as e:
                continue
    except Exception as e:
        pass
    
    # Создаем PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                           rightMargin=10*mm, leftMargin=10*mm,
                           topMargin=15*mm, bottomMargin=15*mm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Стили
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name_bold,
        fontSize=16,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=6,
        alignment=1,
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
    )
    
    cell_style = ParagraphStyle(
        'CellStyle',
        fontName=font_name,
        fontSize=7,
        leading=8,
        alignment=1,
    )
    
    cell_style_bold = ParagraphStyle(
        'CellBold',
        fontName=font_name_bold,
        fontSize=8,
        leading=9,
        alignment=1,
    )
    
    # Заголовок
    story.append(Paragraph(f"Журнал посещаемости", title_style))
    story.append(Paragraph(f"Кружок: {circle.name}", normal_style))
    story.append(Paragraph(f"{MONTH_NAMES_RU[month]} {year}", normal_style))
    story.append(Spacer(1, 6*mm))
    
    if students and dates_to_show:
        # Заголовок таблицы
        header_row = [Paragraph('<b>ФИО</b>', cell_style_bold)]
        for day_date in dates_to_show:
            header_text = f"<b>{day_date.strftime('%d')}</b><br/>{weekdays_ru[day_date.weekday()][:3]}"
            header_row.append(Paragraph(header_text, cell_style_bold))
        header_row.append(Paragraph('<b>Всего</b>', cell_style_bold))
        header_row.append(Paragraph('<b>%</b>', cell_style_bold))
        
        table_data = [header_row]
        
        # Данные студентов
        for student in students:
            present_count = 0
            total_count = 0
            
            # Подсчитываем статистику
            for day_date in dates_to_show:
                if student.id in attendance_dict and day_date in attendance_dict[student.id]:
                    total_count += 1
                    if attendance_dict[student.id][day_date].status == 'present':
                        present_count += 1
            
            # Строка студента
            student_name = student.full_name
            if student.grade:
                student_name += f" ({student.grade})"
            row = [Paragraph(student_name, cell_style)]
            
            # Ячейки посещаемости
            for day_date in dates_to_show:
                if student.id in attendance_dict and day_date in attendance_dict[student.id]:
                    att = attendance_dict[student.id][day_date]
                    if att.status == 'present':
                        row.append(Paragraph('✓', cell_style))
                    elif att.status == 'absent':
                        row.append(Paragraph('✗', cell_style))
                    elif att.status == 'excused':
                        row.append(Paragraph('У', cell_style))
                    else:
                        row.append(Paragraph('-', cell_style))
                else:
                    row.append(Paragraph('-', cell_style))
            
            # Итоги
            row.append(Paragraph(f"{present_count}/{total_count}", cell_style_bold))
            if total_count > 0:
                percentage = round((present_count / total_count * 100), 1)
                row.append(Paragraph(f"{percentage}%", cell_style_bold))
            else:
                row.append(Paragraph('-', cell_style))
            
            table_data.append(row)
        
        # Создаем таблицу
        col_widths = [60*mm] + [15*mm] * len(dates_to_show) + [20*mm, 15*mm]
        table = Table(table_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6efd')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#0d6efd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # ФИО слева
        ]))
        
        story.append(table)
        
        # Легенда
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("✓ - Присутствовал, ✗ - Отсутствовал, У - Уважительная", normal_style))
    else:
        story.append(Paragraph("Нет данных для отображения", normal_style))
    
    # Строим PDF
    doc.build(story)
    
    # Возвращаем PDF
    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    # Используем только латинские символы в имени файла
    safe_circle_name = f"circle_{circle_id}"
    response.headers['Content-Disposition'] = f'attachment; filename=attendance_{safe_circle_name}_{year}_{month:02d}.pdf'
    
    return response


@app.route('/admin/attendance')
@login_required
def admin_attendance():
    """Журнал посещаемости всех кружков для админа"""
    if not current_user.is_admin():
        flash('Доступ запрещен', 'error')
        return redirect(url_for('index'))
    
    # Получаем параметры
    circle_id = request.args.get('circle_id', type=int)
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    
    circles = Circle.query.all()
    
    if circle_id:
        circle = Circle.query.get_or_404(circle_id)
    else:
        # Если кружок не выбран, берем первый
        circle = circles[0] if circles else None
        if circle:
            circle_id = circle.id
    
    if not circle:
        flash('Нет доступных кружков', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Получаем расписание кружка
    schedules = Schedule.query.filter_by(circle_id=circle_id).all()
    
    # Определяем дни недели, когда есть занятия
    schedule_days = set()
    day_mapping = {
        'Дүйсенбі': 0,  # Понедельник
        'Сейсенбі': 1,  # Вторник
        'Сәрсенбі': 2,  # Среда
        'Бейсенбі': 3,  # Четверг
        'Жұма': 4,      # Пятница
        'Сенбі': 5,     # Суббота
    }
    
    for schedule in schedules:
        if schedule.day_of_week and schedule.day_of_week in day_mapping:
            schedule_days.add(day_mapping[schedule.day_of_week])
    
    # Получаем данные за месяц
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    # Генерируем только дни с занятиями
    dates_to_show = []
    current_date = first_day
    while current_date <= last_day:
        if current_date.weekday() in schedule_days:
            dates_to_show.append(current_date)
        current_date += timedelta(days=1)
    
    students = Student.query.filter_by(circle_id=circle_id).order_by(Student.full_name).all()
    
    # Получаем все посещения за месяц
    attendances = Attendance.query.filter(
        Attendance.circle_id == circle_id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).all()
    
    # Группируем по студентам и датам
    attendance_dict = {}
    for a in attendances:
        if a.student_id not in attendance_dict:
            attendance_dict[a.student_id] = {}
        attendance_dict[a.student_id][a.date] = a
    
    # Русские названия дней недели
    weekdays_ru = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среда',
        3: 'Четверг',
        4: 'Пятница',
        5: 'Суббота',
        6: 'Воскресенье'
    }
    
    return render_template('admin/attendance.html',
                         circle=circle,
                         circles=circles,
                         students=students,
                         attendance_dict=attendance_dict,
                         year=year,
                         month=month,
                         dates_to_show=dates_to_show,
                         weekdays_ru=weekdays_ru,
                         month_name_ru=MONTH_NAMES_RU[month],
                         today=date.today())


# ===== ПРЕПОДАВАТЕЛЬ =====

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    """Дашборд преподавателя"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Получаем кружки преподавателя
    circles = Circle.query.filter_by(teacher_id=current_user.id).all()
    
    # Статистика
    total_students = sum(len(circle.students) for circle in circles)
    
    today = date.today()
    first_day = today.replace(day=1)
    
    # Посещаемость за месяц
    circle_ids = [c.id for c in circles]
    attendances_this_month = Attendance.query.filter(
        Attendance.circle_id.in_(circle_ids),
        Attendance.date >= first_day
    ).all()
    
    present_count = sum(1 for a in attendances_this_month if a.status == 'present')
    total_marks = len(attendances_this_month)
    attendance_rate = round((present_count / total_marks * 100) if total_marks > 0 else 0, 1)
    
    return render_template('teacher/dashboard.html',
                         circles=circles,
                         total_students=total_students,
                         attendance_rate=attendance_rate,
                         present_count=present_count,
                         total_marks=total_marks)


@app.route('/teacher/circle/<int:circle_id>')
@login_required
def teacher_circle(circle_id):
    """Страница кружка с возможностью отметки посещаемости (режимы: день, неделя, месяц)"""
    circle = Circle.query.get_or_404(circle_id)
    
    # Проверяем права доступа
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Получаем параметры
    view_mode = request.args.get('mode', 'day')  # day, week, month
    date_str = request.args.get('date')
    schedule_id = request.args.get('schedule_id', type=int)  # ID конкретного занятия
    
    if date_str:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        selected_date = date.today()
    
    # Получаем расписание кружка
    schedules = Schedule.query.filter_by(circle_id=circle_id).order_by(
        Schedule.day_of_week, Schedule.time_slot
    ).all()
    
    # Определяем дни недели, когда есть занятия
    schedule_days = set()
    day_mapping = {
        'Дүйсенбі': 0,  # Понедельник
        'Сейсенбі': 1,  # Вторник
        'Сәрсенбі': 2,  # Среда
        'Бейсенбі': 3,  # Четверг
        'Жұма': 4,      # Пятница
        'Сенбі': 5,     # Суббота
    }
    
    # Группируем расписание по дням недели
    schedule_by_day = {}
    for schedule in schedules:
        if schedule.day_of_week and schedule.day_of_week in day_mapping:
            day_num = day_mapping[schedule.day_of_week]
            schedule_days.add(day_num)
            if day_num not in schedule_by_day:
                schedule_by_day[day_num] = []
            schedule_by_day[day_num].append(schedule)
    
    # Определяем текущее занятие (по дню недели и времени)
    current_schedule = None
    if not schedule_id and selected_date == date.today():
        today_weekday = date.today().weekday()
        current_time = datetime.now().time()
        
        if today_weekday in schedule_by_day:
            # Находим ближайшее занятие к текущему времени
            closest_schedule = None
            min_time_diff = float('inf')
            
            for sched in schedule_by_day[today_weekday]:
                if sched.time_slot:
                    try:
                        time_start_str = sched.time_slot.split('-')[0].strip()
                        time_parts = time_start_str.replace(' ', '').split(':')
                        if len(time_parts) == 2:
                            sched_time = datetime.strptime(f"{time_parts[0]}:{time_parts[1]}", "%H:%M").time()
                            # Вычисляем разницу во времени
                            time_diff = abs((datetime.combine(date.today(), current_time) - 
                                           datetime.combine(date.today(), sched_time)).total_seconds())
                            # Если занятие в пределах 3 часов от текущего времени
                            if time_diff < 10800 and time_diff < min_time_diff:
                                min_time_diff = time_diff
                                closest_schedule = sched
                    except:
                        pass
            
            if closest_schedule:
                current_schedule = closest_schedule
    
    # Если выбран конкретный schedule_id
    selected_schedule = None
    if schedule_id:
        selected_schedule = Schedule.query.get(schedule_id)
        if selected_schedule and selected_schedule.circle_id != circle_id:
            selected_schedule = None
    
    # Если не выбран, используем текущее
    if not selected_schedule and current_schedule:
        selected_schedule = current_schedule
    
    # Фильтруем студентов по группе, если выбрано занятие с группой
    if selected_schedule and selected_schedule.group_number:
        students = Student.query.filter_by(
            circle_id=circle_id, 
            group_number=selected_schedule.group_number
        ).order_by(Student.full_name).all()
    else:
        students = Student.query.filter_by(circle_id=circle_id).order_by(Student.full_name).all()
    
    # Генерируем даты в зависимости от режима
    dates_to_show = []
    
    if view_mode == 'day':
        dates_to_show = [selected_date]
    elif view_mode == 'week':
        # Находим начало недели (понедельник)
        days_since_monday = selected_date.weekday()
        week_start = selected_date - timedelta(days=days_since_monday)
        # Показываем только дни с занятиями в этой неделе
        for i in range(7):
            check_date = week_start + timedelta(days=i)
            if check_date.weekday() in schedule_days:
                dates_to_show.append(check_date)
    elif view_mode == 'month':
        # Показываем все дни месяца, когда есть занятия
        year = selected_date.year
        month = selected_date.month
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        
        current_date = first_day
        while current_date <= last_day:
            if current_date.weekday() in schedule_days:
                dates_to_show.append(current_date)
            current_date += timedelta(days=1)
    
    # Получаем посещаемость для всех дат
    attendances_dict = {}
    if dates_to_show:
        attendances_list = Attendance.query.filter(
            Attendance.circle_id == circle_id,
            Attendance.date.in_(dates_to_show)
        ).all()
        
        for a in attendances_list:
            if a.date not in attendances_dict:
                attendances_dict[a.date] = {}
            attendances_dict[a.date][a.student_id] = a
    
    # Вычисляем навигационные даты для шаблона
    nav_dates = {}
    if view_mode == 'week':
        if dates_to_show:
            nav_dates['prev'] = (dates_to_show[0] - timedelta(days=7)).strftime('%Y-%m-%d')
            nav_dates['next'] = (dates_to_show[-1] + timedelta(days=1)).strftime('%Y-%m-%d')
            nav_dates['week_start'] = dates_to_show[0]
            nav_dates['week_end'] = dates_to_show[-1]
    elif view_mode == 'month':
        # Предыдущий месяц
        if selected_date.month == 1:
            prev_month = date(selected_date.year - 1, 12, 1)
        else:
            prev_month = date(selected_date.year, selected_date.month - 1, 1)
        nav_dates['prev'] = prev_month.strftime('%Y-%m-%d')
        
        # Следующий месяц
        if selected_date.month == 12:
            next_month = date(selected_date.year + 1, 1, 1)
        else:
            next_month = date(selected_date.year, selected_date.month + 1, 1)
        nav_dates['next'] = next_month.strftime('%Y-%m-%d')
    
    # Русские названия дней недели
    weekdays_ru = {
        0: 'Понедельник',
        1: 'Вторник',
        2: 'Среда',
        3: 'Четверг',
        4: 'Пятница',
        5: 'Суббота',
        6: 'Воскресенье'
    }
    
    # Русские названия месяцев
    months_ru = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    # Группируем расписание для отображения
    schedule_grouped = {}
    days_order = ['Дүйсенбі', 'Сейсенбі', 'Сәрсенбі', 'Бейсенбі', 'Жұма', 'Сенбі']
    for day_name in days_order:
        if day_name in day_mapping:
            day_num = day_mapping[day_name]
            if day_num in schedule_by_day:
                schedule_grouped[day_name] = schedule_by_day[day_num]
    
    return render_template('teacher/circle.html',
                         circle=circle,
                         students=students,
                         attendances_dict=attendances_dict,
                         dates_to_show=dates_to_show,
                         selected_date=selected_date,
                         view_mode=view_mode,
                         schedule_days=schedule_days,
                         nav_dates=nav_dates,
                         weekdays_ru=weekdays_ru,
                         months_ru=months_ru,
                         today=date.today(),
                         schedules=schedules,
                         schedule_grouped=schedule_grouped,
                         selected_schedule=selected_schedule,
                         current_schedule=current_schedule,
                         days_order=days_order)


@app.route('/teacher/mark-attendance', methods=['POST'])
@login_required
def mark_attendance():
    """Отметить посещаемость"""
    data = request.get_json()
    
    student_id = data.get('student_id')
    circle_id = data.get('circle_id')
    date_str = data.get('date')
    status = data.get('status')
    note = data.get('note', '')
    
    # Валидация данных
    if not student_id or not circle_id or not date_str or not status:
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Invalid date format: {e}'}), 400
    
    # Проверяем права
    circle = Circle.query.get_or_404(circle_id)
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Ищем существующую запись
    attendance = Attendance.query.filter_by(
        student_id=student_id,
        date=attendance_date
    ).first()
    
    if attendance:
        # Обновляем
        attendance.status = status
        attendance.note = note
        attendance.marked_by = current_user.id
    else:
        # Создаем новую
        attendance = Attendance(
            student_id=student_id,
            circle_id=circle_id,
            date=attendance_date,
            status=status,
            note=note,
            marked_by=current_user.id
        )
        db.session.add(attendance)
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/teacher/attendance-history/<int:circle_id>')
@login_required
def attendance_history(circle_id):
    """История посещаемости кружка"""
    circle = Circle.query.get_or_404(circle_id)
    
    # Проверяем права
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Получаем месяц и год из параметров
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)
    
    # Получаем данные за месяц
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    students = Student.query.filter_by(circle_id=circle_id).order_by(Student.full_name).all()
    
    # Получаем все посещения за месяц
    attendances = Attendance.query.filter(
        Attendance.circle_id == circle_id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).all()
    
    # Группируем по студентам и датам
    attendance_dict = {}
    for a in attendances:
        if a.student_id not in attendance_dict:
            attendance_dict[a.student_id] = {}
        attendance_dict[a.student_id][a.date.day] = a
    
    # Получаем дни месяца
    days_in_month = calendar.monthrange(year, month)[1]
    
    return render_template('teacher/attendance_history.html',
                         circle=circle,
                         students=students,
                         attendance_dict=attendance_dict,
                         year=year,
                         month=month,
                         days_in_month=days_in_month,
                         month_name_ru=MONTH_NAMES_RU[month])


@app.route('/teacher/students/<int:circle_id>')
@login_required
def teacher_students(circle_id):
    """Страница управления учениками кружка"""
    circle = Circle.query.get_or_404(circle_id)
    
    # Проверяем права
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Получаем группы из расписания
    groups = list(set(s.group_number for s in circle.schedules if s.group_number))
    groups.sort()
    
    # Фильтр по группе
    group_filter = request.args.get('group', '')
    
    if group_filter:
        students = Student.query.filter_by(circle_id=circle_id, group_number=group_filter).order_by(Student.full_name).all()
    else:
        students = Student.query.filter_by(circle_id=circle_id).order_by(Student.full_name).all()
    
    return render_template('teacher/students.html',
                         circle=circle,
                         students=students,
                         groups=groups,
                         group_filter=group_filter)


@app.route('/teacher/student/<int:student_id>', methods=['GET', 'POST'])
@login_required
def teacher_edit_student(student_id):
    """Редактирование ученика"""
    student = Student.query.get_or_404(student_id)
    circle = student.circle
    
    # Проверяем права
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Получаем группы из расписания
    groups = list(set(s.group_number for s in circle.schedules if s.group_number))
    groups.sort()
    
    if request.method == 'POST':
        student.full_name = request.form.get('full_name', student.full_name)
        student.iin = request.form.get('iin', student.iin)
        student.gender = request.form.get('gender', student.gender)
        student.school = request.form.get('school', student.school)
        student.grade = request.form.get('grade', student.grade)
        student.group_number = request.form.get('group_number', student.group_number)
        student.applicant_phone = request.form.get('applicant_phone', student.applicant_phone)
        
        db.session.commit()
        flash('Данные ученика обновлены', 'success')
        return redirect(url_for('teacher_students', circle_id=circle.id))
    
    return render_template('teacher/edit_student.html',
                         student=student,
                         circle=circle,
                         groups=groups)


@app.route('/teacher/student/add/<int:circle_id>', methods=['GET', 'POST'])
@login_required
def teacher_add_student(circle_id):
    """Добавление нового ученика"""
    circle = Circle.query.get_or_404(circle_id)
    
    # Проверяем права
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    # Получаем группы из расписания
    groups = list(set(s.group_number for s in circle.schedules if s.group_number))
    groups.sort()
    
    if request.method == 'POST':
        student = Student(
            full_name=request.form.get('full_name', ''),
            iin=request.form.get('iin', ''),
            gender=request.form.get('gender', ''),
            school=request.form.get('school', ''),
            grade=request.form.get('grade', ''),
            group_number=request.form.get('group_number', ''),
            applicant_phone=request.form.get('applicant_phone', ''),
            circle_id=circle_id
        )
        db.session.add(student)
        db.session.commit()
        flash('Ученик добавлен', 'success')
        return redirect(url_for('teacher_students', circle_id=circle_id))
    
    return render_template('teacher/edit_student.html',
                         student=None,
                         circle=circle,
                         groups=groups)


@app.route('/teacher/student/delete/<int:student_id>', methods=['POST'])
@login_required
def teacher_delete_student(student_id):
    """Удаление ученика"""
    student = Student.query.get_or_404(student_id)
    circle = student.circle
    
    # Проверяем права
    if not current_user.is_admin() and circle.teacher_id != current_user.id:
        flash('Доступ запрещен', 'error')
        return redirect(url_for('teacher_dashboard'))
    
    db.session.delete(student)
    db.session.commit()
    flash('Ученик удален', 'success')
    return redirect(url_for('teacher_students', circle_id=circle.id))


@app.route('/teacher/change-password', methods=['GET', 'POST'])
@login_required
def teacher_change_password():
    """Смена пароля преподавателем"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Проверяем текущий пароль
        if not check_password_hash(current_user.password, current_password):
            flash('Неверный текущий пароль', 'error')
            return redirect(url_for('teacher_change_password'))
        
        # Проверяем совпадение паролей
        if new_password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('teacher_change_password'))
        
        # Проверяем длину
        if len(new_password) < 4:
            flash('Пароль должен быть минимум 4 символа', 'error')
            return redirect(url_for('teacher_change_password'))
        
        # Меняем пароль
        current_user.password = generate_password_hash(new_password)
        current_user.plain_password = new_password  # Сохраняем для админа
        db.session.commit()
        
        flash('Пароль успешно изменен', 'success')
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('teacher/change_password.html')


# ===== СОЗДАНИЕ БД =====

def init_db():
    """Инициализация БД"""
    with app.app_context():
        db.create_all()
        print("База данных создана!")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5004)

