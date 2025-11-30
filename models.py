from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Пользователи системы (админ и преподаватели)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' или 'teacher'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с кружками (для преподавателей)
    circles = db.relationship('Circle', backref='teacher', lazy=True)
    
    def is_admin(self):
        return self.role == 'admin'


class Circle(db.Model):
    """Кружки"""
    __tablename__ = 'circles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    direction = db.Column(db.String(200))  # направление
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь со студентами
    students = db.relationship('Student', backref='circle', lazy=True)


class Student(db.Model):
    """Ученики"""
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    iin = db.Column(db.String(12))  # ИИН
    gender = db.Column(db.String(10))  # пол
    address = db.Column(db.Text)
    school = db.Column(db.String(200))  # с какой школы
    grade = db.Column(db.String(20))  # класс
    direction = db.Column(db.String(200))  # направление
    circle_id = db.Column(db.Integer, db.ForeignKey('circles.id'))
    group_number = db.Column(db.String(20))  # номер группы в кружке
    
    # Данные заявителя
    applicant_name = db.Column(db.String(200))
    applicant_iin = db.Column(db.String(12))
    applicant_login = db.Column(db.String(100))
    applicant_phone = db.Column(db.String(20))
    application_date = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с посещениями
    attendances = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')


class Schedule(db.Model):
    """Расписание занятий кружков"""
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    circle_id = db.Column(db.Integer, db.ForeignKey('circles.id'), nullable=False)
    day_of_week = db.Column(db.String(20))  # День недели на казахском
    group_number = db.Column(db.String(10))  # Номер группы
    time_slot = db.Column(db.String(50))  # Время занятий
    room = db.Column(db.String(20))  # Кабинет
    floor = db.Column(db.String(20))  # Этаж
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    circle = db.relationship('Circle', backref='schedules')


class Attendance(db.Model):
    """Посещения"""
    __tablename__ = 'attendances'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    circle_id = db.Column(db.Integer, db.ForeignKey('circles.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'present', 'absent', 'excused'
    note = db.Column(db.Text)
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    circle = db.relationship('Circle', backref='attendances')
    marker = db.relationship('User', backref='marked_attendances')
    
    # Уникальное ограничение: один студент - одна дата
    __table_args__ = (db.UniqueConstraint('student_id', 'date', name='_student_date_uc'),)

