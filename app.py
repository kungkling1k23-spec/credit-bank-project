import os
import json
import uuid
import csv
import io
import urllib.request
import re
from datetime import datetime, timedelta, timezone
from markupsafe import escape
from flask import Flask, render_template, request, redirect, url_for, session, flash, get_flashed_messages, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'credit_bank_is_rmutto_production_key_2026')

from analytics import analytics_bp
app.register_blueprint(analytics_bp)

db_url = os.environ.get('DATABASE_URL')
if db_url:
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///credit_bank.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)

def get_thailand_time():
    """ดึงเวลาปัจจุบันในโซนเวลาประเทศไทย (UTC+7)"""
    tz_th = timezone(timedelta(hours=7))
    return datetime.now(tz_th).strftime('%Y-%m-%d %H:%M')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(20), unique=True, nullable=True)
    prefix = db.Column(db.String(20), default="นาย")
    fullname = db.Column(db.String(100), nullable=False)
    id_card = db.Column(db.String(20), unique=True, nullable=False)
    dob = db.Column(db.String(20), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    faculty = db.Column(db.String(200), default='คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ')
    major = db.Column(db.String(200), default='สาขาวิชาระบบสารสนเทศ')
    address = db.Column(db.Text, nullable=True)
    id_card_img = db.Column(db.String(200), nullable=True)
    profile_img = db.Column(db.String(200), default="default_profile.png")
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')

class Course(db.Model):
    __tablename__ = 'course'

    course_code = db.Column(db.String(50), primary_key=True)
    course_name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    institution = db.Column(db.String(100))
    online_lesson = db.Column(db.Text)
    hours = db.Column(db.Integer)
    credits = db.Column(db.Integer)

    lessons = db.relationship('CourseLesson', backref='course', lazy=True)

class CourseLesson(db.Model):
    __tablename__ = 'course_lesson'

    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(50), db.ForeignKey('course.course_code'), nullable=False)
    lesson_name = db.Column(db.String(255), nullable=False)
    hours = db.Column(db.Integer, default=0)

class CreditRequest(db.Model):
    __tablename__ = 'credit_request'

    id = db.Column(db.Integer, primary_key=True)
    req_code = db.Column(db.String(50), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='credit_requests')
    course_code = db.Column(db.String(50))
    course_name = db.Column(db.String(255))
    category = db.Column(db.String(100))
    institution = db.Column(db.String(100))
    credits = db.Column(db.Integer)
    
    faculty = db.Column(db.String(200), default='คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ')
    major = db.Column(db.String(200), default='สาขาวิชาระบบสารสนเทศ')

    id_card_img = db.Column(db.String(500))
    doc_img = db.Column(db.Text, nullable=True)
    doc_img2 = db.Column(db.Text, nullable=True)
    doc_img3 = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Pending')
    reject_reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    date_submitted = db.Column(db.String(50), default=get_thailand_time)

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS faculty VARCHAR(200) DEFAULT \'คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ\';'))
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS major VARCHAR(200) DEFAULT \'สาขาวิชาระบบสารสนเทศ\';'))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS faculty VARCHAR(200);"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS major VARCHAR(200);"))
            conn.commit()
    except Exception:
        pass

    try:
        # 1. บัญชี Super Admin เดิม (Admin_rmutto)
        main_admin = User.query.filter((User.username == 'Admin_rmutto') | (User.username == 'admin')).first()
        if not main_admin:
            main_admin = User(
                member_id='ADM001',
                prefix='นาย',
                fullname='ผู้ดูแลระบบหลัก',
                id_card='0000000000000',
                username='Admin_rmutto',
                password=generate_password_hash('rmutto2026'),
                role='superadmin',
                phone="081-000-0000",
                email="admin@rmutto.ac.th"
            )
            db.session.add(main_admin)

        # 2. บัญชี Admin ใหม่ (Admin-999 / รหัสผ่าน 16092547)
        admin_999 = User.query.filter_by(username='Admin-999').first()
        if not admin_999:
            admin_999 = User(
                member_id='ADM999',
                prefix='นาย',
                fullname='เจ้าหน้าที่ดูแลรายวิชา',
                id_card='9999999999999',
                username='Admin-999',
                password=generate_password_hash('16092547'),
                role='admin',
                phone="081-000-0001",
                email="admin999@rmutto.ac.th"
            )
            db.session.add(admin_999)

        # บันทึกทั้ง 2 บัญชีลงฐานข้อมูล
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        if Course.query.count() == 0:
            sample_courses = [
                Course(
                    course_code='CS101',
                    course_name='Introduction to Computer Science',
                    credits=3,
                    category='หมวดวิชาแกน',
                    institution='ThaiMOOC',
                    hours=45,
                    description='แนวคิดพื้นฐานเกี่ยวกับวิทยาการคอมพิวเตอร์ อัลกอรึทึม และการแก้ปัญหาเบื้องต้น'
                ),
                Course(
                    course_code='GEN201',
                    course_name='Modern Thai Society and Culture',
                    credits=2,
                    category='หมวดวิชาศึกษาทั่วไป',
                    institution='ChulaMOOC',
                    hours=30,
                    description='ศึกษาบริบททางสังคมและวัฒนธรรมไทยร่วมสมัยและการปรับตัวในยุคดิจิทัล'
                ),
                Course(
                    course_code='ART102',
                    course_name='Creative Design and Thinking',
                    credits=3,
                    category='หมวดวิชาเลือก',
                    institution='ThaiMOOC',
                    hours=45,
                    description='กระบวนการคิดเชิงออกแบบและการสร้างสรรค์ผลงานศิลปะร่วมสมัย'
                )
            ]
            db.session.add_all(sample_courses)
            db.session.commit()
    except Exception:
        db.session.rollback()

def generate_member_id():
    try:
        last_user = User.query.filter(User.member_id.like('IS%')).order_by(User.id.desc()).first()
        if not last_user or not last_user.member_id: return "IS69001"
        raw_num = last_user.member_id.replace("IS", "")
        return f"IS{int(raw_num) + 1:05d}"
    except Exception:
        return f"IS69{uuid.uuid4().hex[:3].upper()}"

def generate_next_officer_code():
    last_officer = User.query.filter(
        User.role.in_(['admin', 'officer', 'superadmin']),
        User.member_id.like('rmutto%')
    ).order_by(User.id.desc()).first()

    if last_officer and last_officer.member_id and last_officer.member_id.startswith('rmutto'):
        try:
            current_num = int(last_officer.member_id.replace('rmutto', ''))
            next_num = current_num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1

    return f"rmutto{next_num:03d}"

def format_address(house_no, moo, soi, subdistrict, district, province, postal_code):
    parts = []
    if house_no: parts.append(f"บ้านเลขที่ {house_no.strip()}")
    if moo: parts.append(f"หมู่ {moo.strip()}")
    if soi: parts.append(f"ซอย {soi.strip()}")
    if subdistrict: parts.append(f"ต.{subdistrict.strip()}")
    if district: parts.append(f"อ.{district.strip()}")
    if province: parts.append(f"จ.{province.strip()}")
    if postal_code: parts.append(f"{postal_code.strip()}")
    return " ".join(parts)

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/180MQL9RadQfhO0uN-L3hQGYiRhDPYvzJ/export?format=csv"
IS_THAIMOOC_COURSES = [{"code": "15-02-002", "name": "คุณภาพการใช้ชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ชีวิตและการสร้างคุณค่า", "การคิดสร้างสรรค์ เพื่อการพัฒนาตนเอง"], "hours_list": ["2 ชม.", "2 ชม."], "total_hours": "4 ชม.", "credits": 3}]

def get_courses():
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        csv_data = response.read().decode('utf-8-sig') 
        reader = csv.DictReader(io.StringIO(csv_data))
        courses_dict = {}
        current_code = None
        
        for row in reader:
            code = row.get('รหัสวิชา', '').strip()
            if code: current_code = code
            if not current_code: continue
                
            name = row.get('ชื่อวิชา', '').strip()
            group = row.get('หมวดวิชา', '').strip()
            provider = row.get('ระบบ', '').strip()
            mooc_name = row.get('บทเรียนออนไลน์', '').strip()
            hours_raw = row.get('ชั่วโมงเรียน', '').strip()
            credits_raw = row.get('หน่วยกิต', '').strip()
            
            if current_code not in courses_dict:
                try: credits_val = int(credits_raw)
                except Exception: credits_val = 3
                courses_dict[current_code] = {"code": current_code, "name": name, "group": group, "provider": provider if provider else "ThaiMOOC", "credits": credits_val, "mooc_list": [], "hours_list": [], "total_num_hours": 0.0}
            else:
                if not courses_dict[current_code]["name"] and name: courses_dict[current_code]["name"] = name
                if not courses_dict[current_code]["group"] and group: courses_dict[current_code]["group"] = group
                if not courses_dict[current_code]["provider"] and provider: courses_dict[current_code]["provider"] = provider

            if mooc_name or hours_raw:
                nums = re.findall(r'\d+(?:\.\d+)?', hours_raw)
                if nums: courses_dict[current_code]["total_num_hours"] += float(nums[0])
                
                clean_mooc = re.sub(r'\(\s*\d+(?:\.\d+)?\s*(?:ชม\.|ชั่วโมง)\s*\)', '', mooc_name).strip()
                if not clean_mooc: clean_mooc = mooc_name

                for m in clean_mooc.split('\n'):
                    if m.strip(): 
                        courses_dict[current_code]["mooc_list"].append(m.strip())
                        courses_dict[current_code]["hours_list"].append(hours_raw if hours_raw else "ระบุในใบประกาศ")

        courses = []
        for data in courses_dict.values():
            th = data["total_num_hours"]
            if th > 0: data["total_hours"] = f"{int(th) if th.is_integer() else round(th, 2)} ชม."
            else: data["total_hours"] = "ไม่ระบุ"
            courses.append(data)
        if courses: return courses
        return IS_THAIMOOC_COURSES
    except Exception:
        return IS_THAIMOOC_COURSES

def render_layout(content, active_page=''):
    def is_active(page_name):
        return "bg-sky-200 text-sky-900 font-extrabold shadow-sm border border-sky-300" if active_page == page_name else "text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 font-medium"

    messages = get_flashed_messages(with_categories=True)
    flash_html = "".join([f'<div class="p-4 mb-4 text-sm rounded-2xl font-semibold shadow-sm flex items-center justify-between border transition-all {"bg-rose-50 text-rose-700 border-rose-200" if category in ["error", "danger"] else "bg-emerald-50 text-emerald-800 border-emerald-200"}"><div class="flex items-center gap-2"><i class="fa-solid {"fa-circle-exclamation text-rose-500" if category in ["error", "danger"] else "fa-circle-check text-emerald-500"} text-lg"></i><span>{escape(message)}</span></div><button onclick="this.parentElement.remove()" class="text-xs font-bold px-2 py-1 hover:bg-black/5 rounded-lg">✕</button></div>' for category, message in messages]) if messages else ""

    user_role = session.get('role', '')
    manage_admin_menu = ""
    if user_role == 'superadmin':
        manage_admin_menu = f"""
        <a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group mt-2 {is_active('manage_admins')}"><i class="fa-solid fa-user-shield text-lg w-6 text-center text-sky-600"></i><span class="nav-text font-bold">จัดการเจ้าหน้าที่</span></a>
        """

    sidebar_html = f"""
    <aside id="sidebar" class="sidebar-expanded sidebar-transition bg-sky-100 text-slate-700 h-screen flex flex-col fixed md:sticky top-0 z-40 shadow-xl border-r border-sky-200 hidden md:flex shrink-0 w-full md:w-auto">
        <div class="p-4 flex flex-col border-b border-sky-200 bg-sky-200/40 shrink-0">
            <a href="/" class="flex items-center justify-center overflow-hidden py-2 px-2 group">
                <img src="/static/images/logo.png" alt="Logo" class="w-full max-h-20 object-contain logo-img-full transition-transform group-hover:scale-105" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x80?text=IS+RMUTTO';">
                <div class="logo-img-small hidden"><div class="w-11 h-11 bg-gradient-to-tr from-sky-500 to-blue-600 text-white rounded-2xl flex items-center justify-center font-black text-xl shadow-md">IS</div></div>
            </a>
            <div class="mt-3 pt-2 border-t border-sky-200/60 hidden md:flex justify-center"><button id="sidebar-toggle" class="w-full py-1.5 px-3 rounded-xl bg-sky-200 hover:bg-sky-300 text-sky-800 flex items-center justify-center gap-2 transition-all group border border-sky-300/50"><i class="fa-solid fa-chevron-left text-xs toggle-icon transition-transform duration-300"></i><span class="nav-text text-xs font-bold text-sky-800">ย่อแถบเมนู</span></button></div>
        </div>

        <div class="flex-grow p-4 space-y-1.5 overflow-y-auto">
            <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-2">เมนูหลัก</p>
            <a href="/" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('home')}"><i class="fa-solid fa-house text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หน้าแรก</span></a>

            {f'''
                {f"""
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/analytics" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('admin_analytics')}"><i class="fa-solid fa-chart-line text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">รายงานวิเคราะห์สถิติ</span></a>
                    <a href="/admin/students" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('admin_students')}"><i class="fa-solid fa-users text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">รายชื่อนักศึกษา</span></a>
                    <a href="/admin/requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('admin_requests')}"><i class="fa-solid fa-file-signature text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ตรวจสอบคำร้อง</span></a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หลักสูตรทั้งหมด</span></a>
                    {manage_admin_menu}
                """ if user_role in ['admin', 'superadmin'] else f"""
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('available_courses')}"><i class="fa-solid fa-magnifying-glass text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ค้นหารายวิชา (Search)</span></a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หลักสูตรทั้งหมด</span></a>
                    <a href="/submit_credit" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('submit_credit')}"><i class="fa-solid fa-file-circle-plus text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ยื่นคำขอเทียบโอน</span></a>
                    <a href="/credits" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('credits')}"><i class="fa-solid fa-graduation-cap text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หน่วยกิตสะสม</span></a>
                    <a href="/history" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('history')}"><i class="fa-solid fa-clock-rotate-left text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ประวัติคำร้องเทียบโอน</span></a>
                """}
            ''' if session.get('user_id') else f"""
                <div class="pt-4 space-y-2">
                    <a href="/login" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group border border-sky-200 {is_active('login')}"><i class="fa-solid fa-right-to-bracket text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">เข้าสู่ระบบ</span></a>
                    <a href="/register" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold transition-all text-sm group shadow-md shadow-sky-400/30"><i class="fa-solid fa-user-plus text-lg w-6 text-center text-sky-100"></i><span class="nav-text">ลงทะเบียนนักศึกษา</span></a>
                </div>
            """}
        </div>

        {f'''
            <div class="p-4 border-t border-sky-200 bg-sky-200/40 shrink-0">
                <a href="/profile" class="flex items-center gap-3 p-2 rounded-2xl transition-all group border {'border-sky-300 bg-sky-200/80' if active_page == 'profile' else 'border-transparent hover:bg-sky-200/60'}">
                    <div class="w-9 h-9 rounded-xl bg-sky-200 text-sky-700 font-bold flex items-center justify-center shrink-0"><i class="fa-regular fa-user"></i></div>
                    <div class="flex flex-col min-w-0 nav-text"><span class="text-xs font-bold text-slate-800 truncate">{escape(session.get('fullname', 'ผู้ใช้งาน'))}</span><span class="text-[10px] text-sky-700 capitalize font-medium">{'เจ้าหน้าที่' if session.get('role') in ['admin', 'superadmin'] else 'นักศึกษา'}</span></div>
                </a>
                <a href="/logout" class="mt-2 flex items-center gap-3 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl transition-all"><i class="fa-solid fa-arrow-right-from-bracket text-sm w-6 text-center"></i><span class="nav-text">ออกจากระบบ</span></a>
            </div>
        ''' if session.get('user_id') else ''}
    </aside>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ธนาคารหน่วยกิต IS RMUTTO</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body {{ font-family: 'Sarabun', sans-serif; background-color: #f0f9ff; }}
            .sidebar-transition {{ transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
            .sidebar-expanded {{ width: 270px; }}
            .sidebar-collapsed {{ width: 85px; }}
            .sidebar-collapsed .nav-text, .sidebar-collapsed .logo-img-full, .sidebar-collapsed .section-title {{ display: none; }}
            .sidebar-collapsed .logo-img-small {{ display: block !important; }}
            .sidebar-collapsed .toggle-icon {{ transform: rotate(180deg); }}
        </style>
    </head>
    <body class="bg-sky-50/50 min-h-screen text-slate-800 antialiased flex flex-col md:flex-row">
        <div class="md:hidden bg-sky-100 text-slate-800 p-3 flex justify-between items-center sticky top-0 z-50 border-b border-sky-200 shadow-md">
            <a href="/" class="flex items-center gap-2 px-2 py-1"><img src="/static/images/logo.png" alt="Logo" class="h-10 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS';"></a>
            <button id="mobile-toggle" class="p-2 text-sky-800 hover:text-sky-950 focus:outline-none"><i class="fa-solid fa-bars text-xl"></i></button>
        </div>
        {sidebar_html}
        <div class="flex-grow flex flex-col min-h-screen min-w-0">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full mt-6">{flash_html}</div>
            <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">{content}</main>
        </div>
        <script>
            const sidebar = document.getElementById('sidebar');
            const sidebarToggle = document.getElementById('sidebar-toggle');
            const mobileToggle = document.getElementById('mobile-toggle');
            if (sidebarToggle && sidebar) {{
                sidebarToggle.addEventListener('click', () => {{ sidebar.classList.toggle('sidebar-expanded'); sidebar.classList.toggle('sidebar-collapsed'); }});
            }}
            if (mobileToggle && sidebar) {{ mobileToggle.addEventListener('click', () => sidebar.classList.toggle('hidden')); }}
        </script>
    </body>
    </html>
    """

@app.route('/')
def home():
    if not session.get('user_id'):
        landing_content = """
        <div class="max-w-6xl mx-auto space-y-16 py-4">
            <div class="relative overflow-hidden bg-gradient-to-br from-slate-900 via-sky-950 to-indigo-950 rounded-[2.5rem] p-8 sm:p-12 text-white shadow-2xl border border-sky-500/20">
                <div class="absolute -top-24 -left-24 w-96 h-96 bg-sky-500/20 rounded-full blur-3xl pointer-events-none"></div>
                <div class="absolute -bottom-24 -right-24 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none"></div>

                <div class="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                    <div class="lg:col-span-7 space-y-6">
                        <div>
                            <span class="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md border border-white/20 text-sky-200 text-xs px-4 py-1.5 rounded-full font-extrabold uppercase tracking-wider">
                                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                                ระบบธนาคารหน่วยกิตดิจิทัล (Credit Bank System)
                            </span>
                        </div>

                        <div class="space-y-3">
                            <h1 class="text-3xl sm:text-4xl lg:text-5xl font-black text-white leading-relaxed tracking-tight">
                                สะสมหน่วยกิตง่ายๆ
                            </h1>
                            <p class="text-2xl sm:text-3xl lg:text-4xl font-black text-sky-300 leading-relaxed tracking-tight">
                                เชื่อมโลกการเรียนรู้สู่อนาคต
                            </p>
                        </div>

                        <p class="text-slate-300 text-sm sm:text-base leading-relaxed font-medium pt-1 max-w-xl">
                            สาขาวิชาระบบสารสนเทศ มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก (RMUTTO)<br>
                            ระบบเทียบโอนคอร์สเรียนออนไลน์ ThaiMOOC & ChulaMOOC สะดวก รวดเร็ว โปร่งใส ตรวจสอบได้ตลอด 24 ชั่วโมง
                        </p>

                        <div class="pt-3 flex flex-wrap gap-3">
                            <button onclick="openLoginModal('student')" class="bg-gradient-to-r from-sky-400 to-blue-600 hover:from-sky-500 hover:to-blue-700 text-white font-extrabold px-6 py-3.5 rounded-2xl shadow-lg hover:shadow-sky-500/30 transition-all duration-300 text-sm flex items-center gap-2">
                                <i class="fa-solid fa-graduation-cap text-lg"></i> เข้าสู่ระบบนักศึกษา
                            </button>
                            <button onclick="openLoginModal('admin')" class="bg-white/10 hover:bg-white/20 text-white font-extrabold px-6 py-3.5 rounded-2xl backdrop-blur-md border border-white/20 transition-all duration-300 text-sm flex items-center gap-2">
                                <i class="fa-solid fa-shield-halved text-sky-400"></i> เข้าสู่ระบบเจ้าหน้าที่
                            </button>
                            <a href="/register" class="bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-bold px-6 py-3.5 rounded-2xl transition-all duration-300 text-sm flex items-center gap-2">
                                <i class="fa-solid fa-user-plus"></i> สมัครสมาชิกใหม่
                            </a>
                        </div>
                    </div>

                    <div class="lg:col-span-5 flex justify-center">
                        <div class="bg-white/10 backdrop-blur-xl p-6 rounded-3xl border border-white/20 shadow-2xl space-y-4 w-full max-w-sm hover:scale-105 transition-transform duration-500">
                            <div class="flex items-center justify-between border-b border-white/10 pb-3">
                                <div class="flex items-center gap-2">
                                    <div class="w-8 h-8 rounded-xl bg-sky-500/30 flex items-center justify-center text-sky-300"><i class="fa-solid fa-bolt"></i></div>
                                    <span class="text-xs font-black text-slate-200">สถิติระบบเรียลไทม์</span>
                                </div>
                                <span class="text-[10px] bg-emerald-500/20 text-emerald-300 font-bold px-2 py-0.5 rounded-full">Active</span>
                            </div>

                            <div class="grid grid-cols-2 gap-3">
                                <div class="bg-white/5 p-4 rounded-2xl border border-white/10 text-center">
                                    <p class="text-2xl font-black text-sky-300">120+</p>
                                    <p class="text-[10px] text-slate-300 font-medium">หน่วยกิตที่รองรับ</p>
                                </div>
                                <div class="bg-white/5 p-4 rounded-2xl border border-white/10 text-center">
                                    <p class="text-2xl font-black text-emerald-300">100%</p>
                                    <p class="text-[10px] text-slate-300 font-medium">ยื่นเรื่องออนไลน์</p>
                                </div>
                            </div>

                            <div class="bg-sky-500/10 p-3 rounded-2xl border border-sky-400/20 flex items-center gap-3">
                                <i class="fa-solid fa-circle-check text-sky-400 text-xl"></i>
                                <p class="text-xs text-slate-200 font-medium">อนุมัติและปรับสมุดสะสมหน่วยกิตอัตโนมัติ</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="space-y-6">
                <div class="text-center max-w-2xl mx-auto space-y-2">
                    <h2 class="text-2xl sm:text-3xl font-black text-slate-900">เลือกช่องทางเข้าใช้งานระบบ</h2>
                    <p class="text-slate-500 text-xs sm:text-sm font-medium">ออกแบบเพื่อการใช้งานที่สะดวก รวดเร็ว เหมาะสมสำหรับทั้งนักศึกษาและเจ้าหน้าที่</p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="group bg-white p-8 rounded-[2rem] border border-sky-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                        <div class="space-y-4">
                            <div class="w-14 h-14 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-2xl font-black group-hover:scale-110 transition-transform">
                                <i class="fa-solid fa-graduation-cap"></i>
                            </div>
                            <div>
                                <span class="bg-sky-50 text-sky-700 text-[10px] font-black uppercase px-2.5 py-1 rounded-md">Student Portal</span>
                                <h3 class="text-xl font-black text-slate-900 mt-1">บริการสำหรับนักศึกษา</h3>
                                <p class="text-slate-500 text-xs mt-1 leading-relaxed">ค้นหารายวิชา ยื่นหลักฐานใบประกาศนียบัตร และติดตามผลสะสมหน่วยกิต</p>
                            </div>

                            <ul class="space-y-2 text-xs text-slate-600 font-medium pt-2">
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-sky-500"></i> ค้นหารายวิชาเทียบโอน ThaiMOOC / ChulaMOOC</li>
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-sky-500"></i> ระบบยื่นคำขอเทียบโอนพร้อมแนบรูปภาพสะดวก</li>
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-sky-500"></i> ดูหลอดความก้าวหน้าสะสมหน่วยกิตสู่เป้าหมาย 120 หน่วยกิต</li>
                            </ul>
                        </div>

                        <div class="pt-6 border-t border-slate-100 mt-6 flex gap-3">
                            <button onclick="openLoginModal('student')" class="flex-grow bg-slate-900 hover:bg-black text-white font-extrabold py-3.5 rounded-2xl transition text-xs text-center shadow-md">
                                เข้าสู่ระบบนักศึกษา <i class="fa-solid fa-arrow-right ml-1"></i>
                            </button>
                            <a href="/register" class="bg-sky-50 hover:bg-sky-100 text-sky-700 font-bold px-4 py-3.5 rounded-2xl transition text-xs">
                                ลงทะเบียน
                            </a>
                        </div>
                    </div>

                    <div class="group bg-white p-8 rounded-[2rem] border border-indigo-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                        <div class="space-y-4">
                            <div class="w-14 h-14 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center text-2xl font-black group-hover:scale-110 transition-transform">
                                <i class="fa-solid fa-shield-halved"></i>
                            </div>
                            <div>
                                <span class="bg-indigo-50 text-indigo-700 text-[10px] font-black uppercase px-2.5 py-1 rounded-md">Officer Command Center</span>
                                <h3 class="text-xl font-black text-slate-900 mt-1">บริการสำหรับเจ้าหน้าที่</h3>
                                <p class="text-slate-500 text-xs mt-1 leading-relaxed">ศูนย์ควบคุมตรวจสอบคำร้อง อนุมัติหน่วยกิต และเรียกดูสถิติภาพรวม</p>
                            </div>

                            <ul class="space-y-2 text-xs text-slate-600 font-medium pt-2">
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-indigo-500"></i> ตรวจสอบพิจารณาคำร้องพร้อมพรีวิวรูปด่วนผ่าน Modal</li>
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-indigo-500"></i> เรียกดูสรุปสถิตินักศึกษา คำร้อง และการเทียบโอนรายวิชา</li>
                                <li class="flex items-center gap-2"><i class="fa-solid fa-check text-indigo-500"></i> ส่งออกรายงานสรุปประจำเดือนเป็นไฟล์ CSV / Excel</li>
                            </ul>
                        </div>

                        <div class="pt-6 border-t border-slate-100 mt-6">
                            <button onclick="openLoginModal('admin')" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold py-3.5 rounded-2xl transition text-xs text-center shadow-md">
                                เข้าสู่ระบบเจ้าหน้าที่ <i class="fa-solid fa-lock ml-1"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-slate-900 rounded-[2.5rem] p-8 sm:p-12 text-white space-y-8 relative overflow-hidden">
                <div class="text-center max-w-2xl mx-auto space-y-2 relative z-10">
                    <span class="text-sky-400 font-black text-xs uppercase tracking-wider">Simple Workflow</span>
                    <h2 class="text-2xl sm:text-3xl font-black">ขั้นตอนการเทียบโอนหน่วยกิตง่ายๆ</h2>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
                    <div class="bg-white/5 p-6 rounded-3xl border border-white/10 hover:bg-white/10 transition">
                        <div class="w-10 h-10 rounded-2xl bg-sky-500/20 text-sky-300 font-black flex items-center justify-center mb-4 text-base">1</div>
                        <h4 class="font-bold text-sm mb-1">ค้นหารายวิชา</h4>
                        <p class="text-xs text-slate-400 leading-relaxed">เลือกวิชาตามหลักสูตร IS ที่เปิดให้เทียบโอนผ่าน ThaiMOOC/ChulaMOOC</p>
                    </div>

                    <div class="bg-white/5 p-6 rounded-3xl border border-white/10 hover:bg-white/10 transition">
                        <div class="w-10 h-10 rounded-2xl bg-sky-500/20 text-sky-300 font-black flex items-center justify-center mb-4 text-base">2</div>
                        <h4 class="font-bold text-sm mb-1">แนบรูปใบประกาศ</h4>
                        <p class="text-xs text-slate-400 leading-relaxed">อัปโหลดรูปหลักฐานการผ่านคอร์สออนไลน์เข้าสู่ระบบ</p>
                    </div>

                    <div class="bg-white/5 p-6 rounded-3xl border border-white/10 hover:bg-white/10 transition">
                        <div class="w-10 h-10 rounded-2xl bg-amber-500/20 text-amber-300 font-black flex items-center justify-center mb-4 text-base">3</div>
                        <h4 class="font-bold text-sm mb-1">เจ้าหน้าที่ตรวจสอบ</h4>
                        <p class="text-xs text-slate-400 leading-relaxed">เจ้าหน้าที่พิจารณาความถูกต้องของเอกสารหลักฐาน</p>
                    </div>

                    <div class="bg-white/5 p-6 rounded-3xl border border-white/10 hover:bg-white/10 transition">
                        <div class="w-10 h-10 rounded-2xl bg-emerald-500/20 text-emerald-300 font-black flex items-center justify-center mb-4 text-base">4</div>
                        <h4 class="font-bold text-sm mb-1">สะสมหน่วยกิต</h4>
                        <p class="text-xs text-slate-400 leading-relaxed">อนุมัติหน่วยกิตสะสมเข้าสู่บัญชีนักศึกษาทันที</p>
                    </div>
                </div>
            </div>
        </div>

        <div id="quickLoginModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4 transition-opacity">
            <div class="bg-white rounded-3xl max-w-md w-full p-8 shadow-2xl relative border border-slate-100 space-y-6">
                <button onclick="closeLoginModal()" class="absolute top-5 right-5 text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center transition">
                    <i class="fa-solid fa-xmark"></i>
                </button>

                <div class="text-center space-y-2">
                    <div id="modal_role_icon" class="w-14 h-14 mx-auto rounded-2xl flex items-center justify-center text-2xl bg-sky-100 text-sky-600">
                        <i class="fa-solid fa-lock"></i>
                    </div>
                    <h3 class="text-xl font-black text-slate-900" id="modal_login_title">เข้าสู่ระบบ</h3>
                    <p class="text-xs text-slate-400 font-medium">กรุณากรอก Username หรือ เลขบัตรประชาชน</p>
                </div>

                <div class="flex bg-slate-100 p-1 rounded-2xl text-xs font-bold">
                    <button type="button" onclick="switchLoginRole('student')" id="tab_login_student" class="flex-1 py-2 rounded-xl text-slate-600 transition">🎓 นักศึกษา</button>
                    <button type="button" onclick="switchLoginRole('admin')" id="tab_login_admin" class="flex-1 py-2 rounded-xl text-slate-600 transition">🛡️ เจ้าหน้าที่</button>
                </div>

                <form method="POST" action="/login" class="space-y-4 text-left">
                    <input type="hidden" name="login_role" id="input_login_role" value="student">
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase mb-1">Username / เลขบัตรประชาชน</label>
                        <input type="text" name="username" required placeholder="กรอกชื่อผู้ใช้ หรือ เลขบัตรประชาชน" class="w-full border border-slate-200 rounded-xl p-3 text-sm bg-slate-50 outline-none focus:border-sky-400">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase mb-1">รหัสผ่าน</label>
                        <input type="password" name="password" required placeholder="••••••••" class="w-full border border-slate-200 rounded-xl p-3 text-sm bg-slate-50 outline-none focus:border-sky-400">
                    </div>
                    <button type="submit" id="modal_submit_btn" class="w-full bg-slate-900 hover:bg-black text-white font-extrabold py-3.5 rounded-xl shadow-md transition text-xs">
                        เข้าสู่ระบบนักศึกษา
                    </button>
                </form>
            </div>
        </div>

        <script>
        function openLoginModal(role) {
            switchLoginRole(role);
            document.getElementById('quickLoginModal').classList.remove('hidden');
        }

        function closeLoginModal() {
            document.getElementById('quickLoginModal').classList.add('hidden');
        }

        function switchLoginRole(role) {
            document.getElementById('input_login_role').value = role;
            const studentTab = document.getElementById('tab_login_student');
            const adminTab = document.getElementById('tab_login_admin');
            const iconElem = document.getElementById('modal_role_icon');
            const titleElem = document.getElementById('modal_login_title');
            const submitBtn = document.getElementById('modal_submit_btn');

            if (role === 'student') {
                studentTab.className = 'flex-1 py-2 rounded-xl bg-white text-sky-700 shadow-sm font-extrabold';
                adminTab.className = 'flex-1 py-2 rounded-xl text-slate-500 font-bold';
                iconElem.className = 'w-14 h-14 mx-auto rounded-2xl flex items-center justify-center text-2xl bg-sky-100 text-sky-600';
                iconElem.innerHTML = '<i class="fa-solid fa-graduation-cap"></i>';
                titleElem.innerText = 'เข้าสู่ระบบนักศึกษา';
                submitBtn.className = 'w-full bg-sky-600 hover:bg-sky-700 text-white font-extrabold py-3.5 rounded-xl shadow-md transition text-xs';
                submitBtn.innerText = 'เข้าสู่ระบบนักศึกษา';
            } else {
                adminTab.className = 'flex-1 py-2 rounded-xl bg-white text-indigo-700 shadow-sm font-extrabold';
                studentTab.className = 'flex-1 py-2 rounded-xl text-slate-500 font-bold';
                iconElem.className = 'w-14 h-14 mx-auto rounded-2xl flex items-center justify-center text-2xl bg-indigo-100 text-indigo-600';
                iconElem.innerHTML = '<i class="fa-solid fa-shield-halved"></i>';
                titleElem.innerText = 'เข้าสู่ระบบเจ้าหน้าที่';
                submitBtn.className = 'w-full bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold py-3.5 rounded-xl shadow-md transition text-xs';
                submitBtn.innerText = 'เข้าสู่ระบบเจ้าหน้าที่';
            }
        }
        </script>
        """
        return render_layout(landing_content, active_page='home')

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    # 1. ฝั่งเจ้าหน้าที่ (Officer / Admin Dashboard)
    if user.role in ['admin', 'superadmin']:
        try:
            all_db_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
            pending_reqs = [r for r in all_db_requests if r.status == 'Pending']
            pending_count = len(pending_reqs)
            
            students = User.query.filter_by(role='student').order_by(User.id.desc()).all()
            total_students = len(students)
            
            approved_reqs = [r for r in all_db_requests if r.status == 'Approved']
            approved_count = len(approved_reqs)
            
            revision_count = sum(1 for r in all_db_requests if r.status in ['Needs_Revision', 'Need_Edit'])
            total_approved_credits = sum(r.credits for r in approved_reqs if r.credits)
        except Exception:
            all_db_requests, pending_reqs, pending_count, students, total_students, approved_reqs, approved_count, revision_count, total_approved_credits = [], [], 0, [], 0, [], 0, 0, 0

        all_requests_list = [{
            'id': r.id,
            'req_code': getattr(r, 'req_code', f'TR{r.id:04d}'),
            'student_name': r.user.fullname if getattr(r, 'user', None) else '-',
            'student_code': r.user.member_id if getattr(r, 'user', None) else '-',
            'course_name': getattr(r, 'course_name', '-'),
            'credits': getattr(r, 'credits', 0),
            'date': getattr(r, 'date_submitted', '-'),
            'status': getattr(r, 'status', 'Pending')
        } for r in all_db_requests]

        pending_list = [r for r in all_requests_list if r['status'] == 'Pending']

        students_list = []
        for s in students:
            app_credits = sum(r.credits for r in CreditRequest.query.filter_by(user_id=s.id, status='Approved').all() if r.credits)
            students_list.append({
                'member_id': s.member_id or '-',
                'fullname': s.fullname,
                'phone': s.phone or '-',
                'email': s.email or '-',
                'credits': app_credits
            })

        approved_list = [r for r in all_requests_list if r['status'] == 'Approved']

        from collections import defaultdict
        course_map = defaultdict(lambda: {'count': 0, 'total_credits': 0, 'unit_credits': 0})
        for r in approved_reqs:
            c_name = r.course_name
            cred = r.credits or 0
            course_map[c_name]['count'] += 1
            course_map[c_name]['total_credits'] += cred
            course_map[c_name]['unit_credits'] = cred

        credits_summary_list = [{
            'course_name': name,
            'unit_credits': data['unit_credits'],
            'approved_count': data['count'],
            'total_credits': data['total_credits']
        } for name, data in course_map.items()]

        admin_summary_json = json.dumps({
            'all_requests': all_requests_list,
            'pending': pending_list,
            'students': students_list,
            'approved': approved_list,
            'credits': credits_summary_list
        }, ensure_ascii=False)

        current_month_str = get_thailand_time()[:7] # YYYY-MM

        html_part = f"""
        <div class="max-w-6xl mx-auto space-y-8">
            <div class="relative overflow-hidden bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-8 text-white shadow-xl">
                <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                    <div>
                        <div class="flex items-center gap-2 mb-2">
                            <span class="bg-amber-400/20 border border-amber-400/30 text-amber-300 text-xs px-3 py-1 rounded-full font-extrabold uppercase tracking-wider">
                                <i class="fa-solid fa-shield-halved mr-1"></i> Officer Command Center
                            </span>
                        </div>
                        <h1 class="text-3xl font-black">ยินดีต้อนรับ, {escape(user.fullname)} 👋</h1>
                        <p class="text-slate-300 text-sm mt-1">ระบบบริหารจัดการธนาคารหน่วยกิต (Credit Bank) สาขาวิชาระบบสารสนเทศ</p>
                    </div>

                </div>
                <div class="absolute -right-10 -bottom-10 w-56 h-56 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div onclick="openStatSummaryModal('pending')" class="cursor-pointer group bg-white p-6 rounded-3xl border border-amber-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-3">
                        <div class="w-12 h-12 bg-amber-100 text-amber-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-clock-rotate-left"></i>
                        </div>
                        <span class="relative flex h-3 w-3">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                        </span>
                    </div>
                    <p class="text-3xl font-black text-slate-800">{pending_count}</p>
                    <p class="text-xs font-bold text-amber-700 mt-1">คำร้องรอตรวจสอบด่วน <i class="fa-solid fa-magnifying-glass-plus text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>

                <div onclick="openStatSummaryModal('students')" class="cursor-pointer group bg-white p-6 rounded-3xl border border-sky-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-3">
                        <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-users"></i>
                        </div>
                        <i class="fa-solid fa-ellipsis text-xs text-slate-300 group-hover:text-sky-500 transition-colors"></i>
                    </div>
                    <p class="text-3xl font-black text-slate-800">{total_students}</p>
                    <p class="text-xs font-bold text-sky-700 mt-1">นักศึกษาในระบบทั้งหมด <i class="fa-solid fa-magnifying-glass-plus text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>

                <div onclick="openStatSummaryModal('approved')" class="cursor-pointer group bg-white p-6 rounded-3xl border border-emerald-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-3">
                        <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-circle-check"></i>
                        </div>
                        <i class="fa-solid fa-ellipsis text-xs text-slate-300 group-hover:text-emerald-500 transition-colors"></i>
                    </div>
                    <p class="text-3xl font-black text-slate-800">{approved_count}</p>
                    <p class="text-xs font-bold text-emerald-700 mt-1">รายการที่อนุมัติแล้ว <i class="fa-solid fa-magnifying-glass-plus text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>

                <div onclick="openStatSummaryModal('credits')" class="cursor-pointer group bg-white p-6 rounded-3xl border border-indigo-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-3">
                        <div class="w-12 h-12 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-award"></i>
                        </div>
                        <i class="fa-solid fa-ellipsis text-xs text-slate-300 group-hover:text-indigo-500 transition-colors"></i>
                    </div>
                    <p class="text-3xl font-black text-slate-800">{total_approved_credits}</p>
                    <p class="text-xs font-bold text-indigo-700 mt-1">หน่วยกิตสะสมรวมทั้งสาขา <i class="fa-solid fa-magnifying-glass-plus text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
                <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                    <h3 class="text-base font-black text-slate-800 mb-1">ภาพรวมสถานะคำร้องเทียบโอน</h3>
                    <p class="text-xs text-slate-400 mb-4">คลิกที่แท่งกราฟเพื่อกรองรายการด้านขวา</p>
                    <div class="h-60 relative cursor-pointer">
                        <canvas id="adminStatusChart"></canvas>
                    </div>
                </div>

                <div class="lg:col-span-2 bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-100 pb-4">
                        <div>
                            <h3 class="text-lg font-black text-slate-800" id="admin_table_title">คำร้องเร่งด่วนที่รอตรวจสอบ</h3>
                            <p class="text-xs text-slate-400" id="admin_table_subtitle">สามารถกดดูด่วนเพื่อตรวจสอบหลักฐานได้ทันที</p>
                        </div>
                        <button onclick="renderAdminTableByStatus('Pending')" class="text-xs font-bold text-sky-600 hover:text-sky-800 transition">
                            <i class="fa-solid fa-rotate-left mr-1"></i> รีเซ็ตตัวกรอง
                        </button>
                    </div>

                    <div class="overflow-x-auto max-h-[420px] overflow-y-auto pr-2">
                        <table class="w-full text-sm text-left">
                            <thead class="text-xs text-slate-400 font-extrabold uppercase bg-slate-50 rounded-xl">
                                <tr>
                                    <th class="px-4 py-3 rounded-l-xl">นักศึกษา</th>
                                    <th class="px-4 py-3">วิชาที่ขอเทียบโอน</th>
                                    <th class="px-4 py-3 text-center">หน่วยกิต</th>
                                    <th class="px-4 py-3 text-right rounded-r-xl">พิจารณา</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100" id="admin_pending_tbody">
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- Export CSV Modal -->
        <div id="exportCsvModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4 transition-opacity">
            <div class="bg-white rounded-3xl max-w-md w-full p-6 sm:p-8 shadow-2xl space-y-6 relative border border-slate-100">
                <button onclick="closeExportModal()" class="absolute top-5 right-5 text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center transition">
                    <i class="fa-solid fa-xmark"></i>
                </button>

                <div class="flex items-center gap-3 border-b border-slate-100 pb-4">
                    <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center text-xl font-black">
                        <i class="fa-solid fa-file-excel"></i>
                    </div>
                    <div>
                        <h3 class="text-lg font-black text-slate-800">ส่งออกรายงานประจำเดือน</h3>
                        <p class="text-xs font-bold text-slate-400">เลือกเดือนและปีที่ต้องการดาวน์โหลด</p>
                    </div>
                </div>

                <div class="space-y-4">
                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-2">เลือกเดือน / ปี</label>
                        <input type="month" id="export_month_select" value="{current_month_str}" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-emerald-500 font-bold">
                    </div>

                    <div class="bg-emerald-50 border border-emerald-200 p-3.5 rounded-2xl text-xs text-emerald-800 font-medium">
                        <i class="fa-solid fa-circle-info mr-1 text-emerald-600"></i> ระบบจะนำเสนอเฉพาะข้อมูลคำร้องที่มีการยื่นภายในเดือนที่เลือกเท่านั้น
                    </div>
                </div>

                <div class="pt-4 border-t border-slate-100 flex gap-3">
                    <button type="button" onclick="closeExportModal()" class="w-1/3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold py-3 rounded-2xl text-xs transition">ยกเลิก</button>
                    <button type="button" onclick="downloadSelectedMonthCSV()" class="w-2/3 bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold py-3 rounded-2xl shadow-md text-xs transition flex items-center justify-center gap-2">
                        <i class="fa-solid fa-download"></i> ดาวน์โหลด CSV
                    </button>
                </div>
            </div>
        </div>

        <div id="statSummaryModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4 transition-opacity">
            <div class="bg-white rounded-3xl max-w-3xl w-full p-6 sm:p-8 shadow-2xl space-y-6 relative border border-slate-100 max-h-[85vh] flex flex-col">
                <div class="flex justify-between items-center border-b border-slate-100 pb-4 shrink-0">
                    <div class="flex items-center gap-3">
                        <div id="modal_header_icon" class="w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-black bg-sky-100 text-sky-600">
                            <i class="fa-solid fa-list"></i>
                        </div>
                        <div>
                            <h3 class="text-lg font-black text-slate-800" id="modal_summary_title">สรุปข้อมูล</h3>
                            <p class="text-xs font-bold text-slate-400" id="modal_summary_subtitle">รายละเอียดการ์ดสรุปสถิติ</p>
                        </div>
                    </div>
                    <button onclick="closeStatSummaryModal()" class="text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center transition">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>

                <div class="overflow-y-auto flex-grow" id="modal_summary_content"></div>

                <div class="pt-4 border-t border-slate-100 flex justify-end shrink-0">
                    <button onclick="closeStatSummaryModal()" class="bg-slate-900 hover:bg-black text-white font-bold px-6 py-2.5 rounded-xl text-xs transition">ปิดหน้าต่าง</button>
                </div>
            </div>
        </div>
        """

        js_template = """
        <script>
        const summaryData = __ADMIN_SUMMARY_JSON__;

        function openExportModal() {
            document.getElementById('exportCsvModal').classList.remove('hidden');
        }

        function closeExportModal() {
            document.getElementById('exportCsvModal').classList.add('hidden');
        }

        function downloadSelectedMonthCSV() {
            const selectedMonth = document.getElementById('export_month_select').value;
            if (!selectedMonth) {
                alert('กรุณาเลือกเดือนก่อนดาวน์โหลด');
                return;
            }
            window.location.href = '/admin/export_csv?month=' + selectedMonth;
            closeExportModal();
        }

        function openStatSummaryModal(type) {
            const modal = document.getElementById('statSummaryModal');
            const titleElem = document.getElementById('modal_summary_title');
            const subtitleElem = document.getElementById('modal_summary_subtitle');
            const iconElem = document.getElementById('modal_header_icon');
            const contentElem = document.getElementById('modal_summary_content');

            if (type === 'pending') {
                titleElem.innerText = 'รายการคำร้องรอตรวจสอบด่วน';
                subtitleElem.innerText = 'รวมทั้งสิ้น ' + summaryData.pending.length + ' รายการ';
                iconElem.className = 'w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-black bg-amber-100 text-amber-600';
                iconElem.innerHTML = '<i class="fa-solid fa-clock-rotate-left"></i>';

                let rows = '';
                summaryData.pending.forEach(item => {
                    rows += `
                    <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
                        <td class="py-3 px-3 font-mono font-bold text-sky-600">${item.req_code}</td>
                        <td class="py-3 px-3 font-bold text-slate-800">${item.student_name}<br><span class="text-[10px] text-slate-400 font-normal">(${item.student_code})</span></td>
                        <td class="py-3 px-3 font-medium text-slate-700">${item.course_name}</td>
                        <td class="py-3 px-3 text-slate-400">${item.date}</td>
                        <td class="py-3 px-3 text-right">
                            <a href="/admin/review/${item.id}" class="bg-amber-50 hover:bg-amber-100 text-amber-700 text-[11px] font-bold px-3 py-1.5 rounded-xl border border-amber-200 transition inline-block">ตรวจเอกสาร</a>
                        </td>
                    </tr>`;
                });

                contentElem.innerHTML = `
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase tracking-wider sticky top-0">
                        <tr><th class="py-2.5 px-3">รหัสคำร้อง</th><th class="py-2.5 px-3">นักศึกษา</th><th class="py-2.5 px-3">วิชาที่ยื่น</th><th class="py-2.5 px-3">วันที่ยื่น</th><th class="py-2.5 px-3 text-right">จัดการ</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">${rows || '<tr><td colspan="5" class="py-8 text-center text-xs text-slate-400">ไม่มีคำร้องรอดำเนินการ</td></tr>'}</tbody>
                </table>`;

            } else if (type === 'students') {
                titleElem.innerText = 'สรุปรายชื่อนักศึกษาในระบบ';
                subtitleElem.innerText = 'รวมทั้งสิ้น ' + summaryData.students.length + ' คน';
                iconElem.className = 'w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-black bg-sky-100 text-sky-600';
                iconElem.innerHTML = '<i class="fa-solid fa-users"></i>';

                let rows = '';
                summaryData.students.forEach((item, index) => {
                    rows += `
                    <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
                        <td class="py-3 px-3 font-mono font-bold text-slate-400">${index + 1}</td>
                        <td class="py-3 px-3 font-mono font-bold text-sky-600">${item.member_id}</td>
                        <td class="py-3 px-3 font-bold text-slate-800">${item.fullname}</td>
                        <td class="py-3 px-3 text-slate-500">${item.phone}<br><span class="text-[10px] text-slate-400">${item.email}</span></td>
                        <td class="py-3 px-3 text-center font-black text-emerald-600">${item.credits} หน่วยกิต</td>
                    </tr>`;
                });

                contentElem.innerHTML = `
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase tracking-wider sticky top-0">
                        <tr><th class="py-2.5 px-3">#</th><th class="py-2.5 px-3">รหัสนักศึกษา</th><th class="py-2.5 px-3">ชื่อ-นามสกุล</th><th class="py-2.5 px-3">การติดต่อ</th><th class="py-2.5 px-3 text-center">หน่วยกิตสะสม</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">${rows || '<tr><td colspan="5" class="py-8 text-center text-xs text-slate-400">ยังไม่มีข้อมูลนักศึกษา</td></tr>'}</tbody>
                </table>`;

            } else if (type === 'approved') {
                titleElem.innerText = 'สรุปรายการที่อนุมัติแล้ว';
                subtitleElem.innerText = 'รวมทั้งสิ้น ' + summaryData.approved.length + ' รายการ';
                iconElem.className = 'w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-black bg-emerald-100 text-emerald-600';
                iconElem.innerHTML = '<i class="fa-solid fa-circle-check"></i>';

                let rows = '';
                summaryData.approved.forEach(item => {
                    rows += `
                    <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
                        <td class="py-3 px-3 font-mono font-bold text-sky-600">${item.req_code}</td>
                        <td class="py-3 px-3 font-bold text-slate-800">${item.student_name}</td>
                        <td class="py-3 px-3 font-medium text-slate-700">${item.course_name}</td>
                        <td class="py-3 px-3 text-center font-black text-emerald-600">${item.credits}</td>
                        <td class="py-3 px-3 text-slate-500 font-medium">${item.approved_by || 'เจ้าหน้าที่'}</td>
                    </tr>`;
                });

                contentElem.innerHTML = `
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase tracking-wider sticky top-0">
                        <tr><th class="py-2.5 px-3">รหัสคำร้อง</th><th class="py-2.5 px-3">นักศึกษา</th><th class="py-2.5 px-3">วิชาที่อนุมัติ</th><th class="py-2.5 px-3 text-center">หน่วยกิต</th><th class="py-2.5 px-3">ผู้อนุมัติ</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">${rows || '<tr><td colspan="5" class="py-8 text-center text-xs text-slate-400">ยังไม่มีรายการที่อนุมัติแล้ว</td></tr>'}</tbody>
                </table>`;

            } else if (type === 'credits') {
                titleElem.innerText = 'สรุปการเทียบโอนหน่วยกิตแยกตามรายวิชา';
                subtitleElem.innerText = 'แสดงจำนวนหน่วยกิตอนุมัติรวมแยกตามวิชา';
                iconElem.className = 'w-10 h-10 rounded-2xl flex items-center justify-center text-lg font-black bg-indigo-100 text-indigo-600';
                iconElem.innerHTML = '<i class="fa-solid fa-award"></i>';

                let rows = '';
                summaryData.credits.forEach(item => {
                    rows += `
                    <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
                        <td class="py-3 px-3 font-extrabold text-slate-800">${item.course_name}</td>
                        <td class="py-3 px-3 text-center font-bold text-slate-600">${item.unit_credits} หน่วยกิต</td>
                        <td class="py-3 px-3 text-center font-bold text-sky-600">${item.approved_count} คน</td>
                        <td class="py-3 px-3 text-center font-black text-indigo-600">${item.total_credits} หน่วยกิต</td>
                    </tr>`;
                });

                contentElem.innerHTML = `
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase tracking-wider sticky top-0">
                        <tr><th class="py-2.5 px-3">ชื่อรายวิชา</th><th class="py-2.5 px-3 text-center">หน่วยกิต/วิชา</th><th class="py-2.5 px-3 text-center">อนุมัติแล้ว (คน)</th><th class="py-2.5 px-3 text-center">หน่วยกิตรวมทั้งสาขา</th></tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">${rows || '<tr><td colspan="4" class="py-8 text-center text-xs text-slate-400">ยังไม่มีข้อมูลการอนุมัติหน่วยกิต</td></tr>'}</tbody>
                </table>`;
            }

            modal.classList.remove('hidden');
        }

        function closeStatSummaryModal() {
            document.getElementById('statSummaryModal').classList.add('hidden');
        }

        function renderAdminTableByStatus(targetStatus) {
            const tbody = document.getElementById('admin_pending_tbody');
            const titleElem = document.getElementById('admin_table_title');
            const subtitleElem = document.getElementById('admin_table_subtitle');
            if(!tbody) return;
            tbody.innerHTML = '';

            const statusTitles = {
                'Pending': 'คำร้องเร่งด่วนที่รอตรวจสอบ',
                'Approved': 'รายการคำร้องที่อนุมัติแล้ว',
                'Needs_Revision': 'รายการคำร้องที่ส่งกลับให้แก้ไข'
            };
            const statusSubtitles = {
                'Pending': 'สามารถกดตรวจเอกสารเพื่อพิจารณาหลักฐานได้ทันที',
                'Approved': 'คำร้องที่ได้รับการอนุมัติเรียบร้อยแล้ว',
                'Needs_Revision': 'คำร้องที่อยู่นะหว่างรอนักศึกษาแก้ไขหลักฐาน'
            };

            titleElem.innerText = statusTitles[targetStatus] || 'รายการคำร้อง';
            subtitleElem.innerText = statusSubtitles[targetStatus] || 'กรองข้อมูลตามกราฟสถานะ';

            const filteredRequests = summaryData.all_requests.filter(r => {
                if (targetStatus === 'Needs_Revision') {
                    return r.status === 'Needs_Revision' || r.status === 'Need_Edit';
                }
                return r.status === targetStatus;
            });

            if (filteredRequests.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-xs font-bold text-slate-400"><i class="fa-solid fa-folder-open text-2xl mb-2 text-slate-300 block"></i>ไม่พบคำร้องในสถานะ "${statusTitles[targetStatus] || targetStatus}"</td></tr>`;
                return;
            }

            filteredRequests.forEach(item => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-slate-50 transition';
                
                let btnHtml = '';
                if (item.status === 'Pending') {
                    btnHtml = `<a href="/admin/review/${item.id}" class="bg-amber-50 hover:bg-amber-100 text-amber-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1 border border-amber-200"><i class="fa-solid fa-pen-to-square"></i> ตรวจ</a>`;
                } else if (item.status === 'Approved') {
                    btnHtml = `<a href="/admin/review/${item.id}" class="bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1 border border-emerald-200"><i class="fa-solid fa-eye"></i> รายละเอียด</a>`;
                } else {
                    btnHtml = `<a href="/admin/review/${item.id}" class="bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1 border border-indigo-200"><i class="fa-solid fa-clock-rotate-left"></i> ดูการแก้</a>`;
                }

                tr.innerHTML = `
                    <td class="px-4 py-3.5">
                        <p class="font-bold text-slate-800 text-xs">${item.student_name}</p>
                        <p class="text-[10px] text-slate-400 font-mono">${item.student_code}</p>
                    </td>
                    <td class="px-4 py-3.5 font-bold text-slate-700 text-xs">${item.course_name}</td>
                    <td class="px-4 py-3.5 text-center font-black text-sky-600 text-xs">${item.credits}</td>
                    <td class="px-4 py-3.5 text-right">${btnHtml}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        document.addEventListener("DOMContentLoaded", function() {
            renderAdminTableByStatus('Pending');

            const chartCanvas = document.getElementById('adminStatusChart');
            if (chartCanvas) {
                const ctx = chartCanvas.getContext('2d');
                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: ['รอตรวจสอบ', 'อนุมัติแล้ว', 'ส่งกลับให้แก้ไข'],
                        datasets: [{
                            label: 'จำนวนคำร้อง',
                            data: [__PENDING__, __APPROVED__, __REVISION__],
                            backgroundColor: ['#f59e0b', '#10b981', '#6366f1'],
                            borderRadius: 12
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const index = elements[0].index;
                                const statusMap = ['Pending', 'Approved', 'Needs_Revision'];
                                renderAdminTableByStatus(statusMap[index]);
                            }
                        }
                    }
                });
            }
        });
        </script>
        """

        js_code = js_template.replace('__ADMIN_SUMMARY_JSON__', admin_summary_json)\
                             .replace('__PENDING__', str(pending_count))\
                             .replace('__APPROVED__', str(approved_count))\
                             .replace('__REVISION__', str(revision_count))

        admin_content = html_part + js_code
        return render_layout(admin_content, active_page='home')

# 2. ฝั่งนักศึกษา (Student Dashboard)
    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).order_by(CreditRequest.id.desc()).all()
    except Exception:
        user_requests = []

    pending_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Pending')
    approved_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Approved')
    revision_count = sum(1 for r in user_requests if getattr(r, 'status', '') in ['Needs_Revision', 'Need_Edit'])
    need_edit_count = revision_count

    approved_credits = sum(getattr(r, 'credits', 0) or 0 for r in user_requests if getattr(r, 'status', '') == 'Approved')
    target_credits = 120
    credit_percent = min(100, round((approved_credits / target_credits) * 100, 1))

    req_list_json = []
    for r in user_requests:
        req_list_json.append({
            'id': r.id,
            'req_code': r.req_code or f'TR{r.id:04d}',
            'course_name': r.course_name or '-',
            'credits': r.credits or 0,
            'status': r.status or 'Pending',
            'reject_reason': r.reject_reason or '-',
            'doc_img': r.doc_img or '',
            'doc_img2': r.doc_img2 or '',
            'doc_img3': r.doc_img3 or '',
            'date_submitted': r.date_submitted or '-'
        })
    req_json_str = json.dumps(req_list_json, ensure_ascii=False)

    edit_banner_html = ""
    if need_edit_count > 0:
        edit_banner_html = f'''
        <div class="bg-indigo-50 border border-indigo-200 p-4 rounded-2xl flex items-center justify-between gap-4 mb-4">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0 font-bold">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                </div>
                <div>
                    <p class="text-xs font-black text-indigo-950">แจ้งเตือนคำร้องต้องแก้ไข</p>
                    <p class="text-[11px] font-bold text-indigo-700">คุณมี {need_edit_count} รายการคำร้องที่เจ้าหน้าที่ส่งกลับให้แก้ไขหลักฐานเพิ่มเติม</p>
                </div>
            </div>
            <button onclick="filterByStatus('Needs_Revision')" class="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-4 py-2 rounded-xl text-xs transition shrink-0 shadow-sm">
                คลิกแก้ไขด่วน <i class="fa-solid fa-arrow-right ml-1"></i>
            </button>
        </div>
        '''

    html_part = f"""
    <div class="max-w-6xl mx-auto space-y-8">
        <div class="relative overflow-hidden bg-gradient-to-r from-sky-600 via-indigo-600 to-slate-900 rounded-3xl p-8 text-white shadow-xl">
            <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                    <span class="bg-white/20 backdrop-blur-md text-sky-100 text-xs px-3 py-1 rounded-full font-bold uppercase tracking-wider">Student Portal</span>
                    <h1 class="text-3xl font-black mt-2">ยินดีต้อนรับ, {escape(user.prefix or '')}{escape(user.fullname)} 👋</h1>
                    <p class="text-sky-100/80 text-sm mt-1">รหัสนักศึกษา: {escape(user.member_id or '-')} | ระบบธนาคารหน่วยกิต (Credit Bank) IS RMUTTO</p>
                </div>
                <a href="/submit_credit" class="group bg-white hover:bg-sky-50 text-sky-700 font-extrabold px-6 py-3.5 rounded-2xl shadow-lg hover:shadow-xl transition-all duration-300 flex items-center gap-2 text-sm shrink-0">
                    <i class="fa-solid fa-circle-plus text-sky-600 group-hover:rotate-90 transition-transform duration-300"></i>
                    ยื่นคำขอเทียบโอนใหม่
                </a>
            </div>
            <div class="absolute -right-10 -bottom-10 w-48 h-48 bg-white/10 rounded-full blur-2xl pointer-events-none"></div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-center mb-3">
                        <span class="text-xs font-black uppercase tracking-wider text-slate-400">หน่วยกิตที่เทียบโอนสำเร็จ</span>
                        <span class="bg-emerald-50 text-emerald-600 text-xs font-bold px-2.5 py-1 rounded-lg"><i class="fa-solid fa-award"></i> อนุมัติแล้ว</span>
                    </div>
                    <div class="flex items-baseline gap-2">
                        <span class="text-4xl font-black text-slate-800">{approved_credits}</span>
                        <span class="text-sm font-bold text-slate-400">/ {target_credits} หน่วยกิต</span>
                    </div>
                </div>

                <div class="mt-6 space-y-2">
                    <div class="flex justify-between text-xs font-bold">
                        <span class="text-slate-500">ความก้าวหน้าตามเป้าหมาย</span>
                        <span class="text-sky-600">{credit_percent}%</span>
                    </div>
                    <div class="w-full bg-slate-100 h-3 rounded-full overflow-hidden p-0.5">
                        <div class="bg-gradient-to-r from-sky-500 to-emerald-500 h-full rounded-full transition-all duration-1000" style="width: {credit_percent}%"></div>
                    </div>
                </div>
            </div>

            <div class="lg:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div onclick="filterByStatus('Pending')" class="cursor-pointer group bg-white hover:bg-amber-50/50 p-6 rounded-3xl border border-amber-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-4">
                        <div class="w-12 h-12 bg-amber-100 text-amber-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-hourglass-half"></i>
                        </div>
                        <span class="relative flex h-3 w-3">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                        </span>
                    </div>
                    <p class="text-2xl font-black text-slate-800">{pending_count}</p>
                    <p class="text-xs font-bold text-amber-700 mt-1">รอดำเนินการ <i class="fa-solid fa-arrow-right text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>

                <div onclick="filterByStatus('Approved')" class="cursor-pointer group bg-white hover:bg-emerald-50/50 p-6 rounded-3xl border border-emerald-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-4">
                        <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-circle-check"></i>
                        </div>
                        <i class="fa-solid fa-chevron-right text-xs text-slate-300 group-hover:text-emerald-500 transition-colors"></i>
                    </div>
                    <p class="text-2xl font-black text-slate-800">{approved_count}</p>
                    <p class="text-xs font-bold text-emerald-700 mt-1">อนุมัติเรียบร้อย <i class="fa-solid fa-arrow-right text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>

                <div onclick="filterByStatus('Needs_Revision')" class="cursor-pointer group bg-white hover:bg-indigo-50/50 p-6 rounded-3xl border border-indigo-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
                    <div class="flex justify-between items-center mb-4">
                        <div class="w-12 h-12 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center text-xl font-black group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </div>
                        <i class="fa-solid fa-chevron-right text-xs text-slate-300 group-hover:text-indigo-500 transition-colors"></i>
                    </div>
                    <p class="text-2xl font-black text-slate-800">{need_edit_count}</p>
                    <p class="text-xs font-bold text-indigo-700 mt-1">ต้องแก้ไขหลักฐาน <i class="fa-solid fa-arrow-right text-[10px] ml-1 opacity-0 group-hover:opacity-100 transition-opacity"></i></p>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col items-center justify-center">
                <h3 class="text-base font-black text-slate-800 mb-1 w-full text-left">สัดส่วนสถานะคำร้อง</h3>
                <p class="text-xs text-slate-400 mb-4 w-full text-left">สามารถคลิกชิ้นส่วนกราฟเพื่อกรองตารางได้</p>
                <div class="w-48 h-48 relative">
                    <canvas id="studentChart"></canvas>
                    <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <span class="text-2xl font-black text-slate-800">{len(user_requests)}</span>
                        <span class="text-[10px] font-bold text-slate-400">คำร้องทั้งหมด</span>
                    </div>
                </div>
                <div class="flex flex-wrap items-center justify-center gap-3 mt-4 text-[11px] font-bold border-t border-slate-100 pt-3 w-full">
                    <span class="flex items-center gap-1.5 text-amber-600"><span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span> รอดำเนินการ</span>
                    <span class="flex items-center gap-1.5 text-emerald-600"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> อนุมัติแล้ว</span>
                    <span class="flex items-center gap-1.5 text-indigo-600"><span class="w-2.5 h-2.5 rounded-full bg-indigo-500"></span> ต้องแก้ไข</span>
                </div>
            </div>

            <div class="lg:col-span-2 space-y-4">
                {edit_banner_html}

                <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-100 pb-4">
                        <div>
                            <h3 class="text-lg font-black text-slate-800">รายการคำร้องเทียบโอน</h3>
                            <p class="text-xs text-slate-400" id="filter_status_label">แสดงคำร้องทั้งหมด</p>
                        </div>

                        <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
                            <div class="relative min-w-[200px]">
                                <i class="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs"></i>
                                <input type="text" id="student_search_input" onkeyup="handleStudentSearch()" placeholder="ค้นหาชื่อวิชา / รหัสคำร้อง..." class="w-full pl-8 pr-3 py-1.5 text-xs font-bold text-slate-700 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:border-sky-400">
                            </div>

                            <div class="flex flex-wrap gap-1.5 bg-slate-100 p-1 rounded-2xl text-xs font-bold shrink-0">
                                <button onclick="filterByStatus('ALL')" id="btn-tab-ALL" class="tab-btn px-3 py-1.5 rounded-xl bg-slate-900 text-white shadow-sm">ทั้งหมด</button>
                                <button onclick="filterByStatus('Pending')" id="btn-tab-Pending" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">รอดำเนินการ</button>
                                <button onclick="filterByStatus('Approved')" id="btn-tab-Approved" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">อนุมัติแล้ว</button>
                                <button onclick="filterByStatus('Needs_Revision')" id="btn-tab-Needs_Revision" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">ต้องแก้ไข</button>
                            </div>
                        </div>
                    </div>

                    <div class="overflow-x-auto max-h-[420px] overflow-y-auto pr-1">
                        <table class="w-full text-sm text-left border-separate border-spacing-0">
                            <thead class="text-xs text-slate-400 font-extrabold uppercase bg-slate-50 sticky top-0 z-10 shadow-sm">
                                <tr>
                                    <th class="px-4 py-3 rounded-l-xl bg-slate-50">รหัสคำร้อง</th>
                                    <th class="px-4 py-3 bg-slate-50">ชื่อวิชาที่ขอเทียบโอน</th>
                                    <th class="px-4 py-3 text-center bg-slate-50">หน่วยกิต</th>
                                    <th class="px-4 py-3 text-center bg-slate-50">วันที่ยื่น</th>
                                    <th class="px-4 py-3 text-center bg-slate-50">สถานะ</th>
                                    <th class="px-4 py-3 text-right rounded-r-xl bg-slate-50">จัดการ</th>
                                </tr>
                            </thead>
                            <tbody id="requests_tbody" class="divide-y divide-slate-100">
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div id="quickViewModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4 transition-opacity">
        <div class="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-6 relative border border-slate-100">
            <button onclick="closeQuickView()" class="absolute top-5 right-5 text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center transition">
                <i class="fa-solid fa-xmark"></i>
            </button>

            <div class="flex items-center gap-3 border-b border-slate-100 pb-4">
                <div class="p-3 bg-sky-100 text-sky-600 rounded-2xl"><i class="fa-solid fa-file-invoice text-xl"></i></div>
                <div>
                    <h3 class="text-lg font-black text-slate-800" id="modal_course_name">-</h3>
                    <p class="text-xs font-bold text-slate-400" id="modal_credits_text">-</p>
                </div>
            </div>

            <div class="space-y-2">
                <label class="text-xs font-black uppercase text-slate-400">สถานะคำร้องปัจจุบัน</label>
                <div id="modal_status_badge"></div>
                <p id="modal_reject_reason_box" class="hidden text-xs text-rose-600 bg-rose-50 p-3 rounded-xl border border-rose-100 font-bold mt-2"></p>
            </div>

            <div class="space-y-2">
                <label class="text-xs font-black uppercase text-slate-400">รูปหลักฐานใบประกาศแนบ</label>
                <div id="modal_images_container" class="grid grid-cols-3 gap-2"></div>
            </div>

            <div class="pt-4 border-t border-slate-100 flex gap-3">
                <button onclick="closeQuickView()" class="w-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold py-3 rounded-2xl text-xs transition">ปิดหน้าต่าง</button>
                <a id="modal_action_btn" href="#" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3 rounded-2xl text-xs text-center transition flex items-center justify-center gap-2">
                    <i class="fa-solid fa-pen-to-square"></i> แก้ไขคำร้องนี้
                </a>
            </div>
        </div>
    </div>
    """

    js_template = """
    <script>
    let requestsData = [];
    try {
        requestsData = __REQUESTS_JSON__;
    } catch(e) {
        console.error("JSON parse error:", e);
    }

    let currentFilter = 'ALL';
    let searchQuery = '';

    function handleStudentSearch() {
        const inputElem = document.getElementById('student_search_input');
        if (inputElem) {
            searchQuery = inputElem.value.toLowerCase().trim();
        }
        renderTable();
    }

    function renderTable() {
        const tbody = document.getElementById('requests_tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const filtered = requestsData.filter(r => {
            let matchStatus = true;
            if (currentFilter === 'Pending') matchStatus = (r.status === 'Pending');
            else if (currentFilter === 'Approved') matchStatus = (r.status === 'Approved');
            else if (currentFilter === 'Needs_Revision') matchStatus = (r.status === 'Needs_Revision' || r.status === 'Need_Edit');

            let matchSearch = true;
            if (searchQuery) {
                const courseName = (r.course_name || '').toLowerCase();
                const reqCode = (r.req_code || '').toLowerCase();
                matchSearch = courseName.includes(searchQuery) || reqCode.includes(searchQuery);
            }

            return matchStatus && matchSearch;
        });

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-xs font-bold text-slate-400"><i class="fa-solid fa-folder-open text-2xl mb-2 block"></i>ไม่พบรายการคำร้องที่ตรงกับเงื่อนไข</td></tr>`;
            return;
        }

        filtered.forEach(item => {
            let badgeHtml = '';
            if (item.status === 'Pending') {
                badgeHtml = `<span class="bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span> รอดำเนินการ</span>`;
            } else if (item.status === 'Approved') {
                badgeHtml = `<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5 whitespace-nowrap"><i class="fa-solid fa-check text-[10px]"></i> อนุมัติแล้ว</span>`;
            } else {
                badgeHtml = `<span class="bg-indigo-50 text-indigo-700 border border-indigo-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5 whitespace-nowrap"><i class="fa-solid fa-pen-to-square text-[10px]"></i> ให้แก้ไข</span>`;
            }

            const tr = document.createElement('tr');
            tr.className = 'hover:bg-slate-50/80 transition';
            tr.innerHTML = `
                <td class="px-4 py-4 font-mono font-bold text-sky-600 text-xs whitespace-nowrap">${item.req_code || '-'}</td>
                <td class="px-4 py-4 font-bold text-slate-800">${item.course_name || '-'}</td>
                <td class="px-4 py-4 text-center font-bold text-slate-600 text-xs whitespace-nowrap">${item.credits || 0}</td>
                <td class="px-4 py-4 text-center text-xs text-slate-400 font-medium whitespace-nowrap">${item.date_submitted || '-'}</td>
                <td class="px-4 py-4 text-center whitespace-nowrap">${badgeHtml}</td>
                <td class="px-4 py-4 text-right whitespace-nowrap">
                    <button onclick="openQuickView(${item.id})" class="bg-sky-50 hover:bg-sky-100 text-sky-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1.5 whitespace-nowrap shrink-0">
                        <i class="fa-solid fa-eye text-[11px]"></i> รายละเอียด
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    function filterByStatus(status) {
        currentFilter = status;
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.className = 'tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800';
        });
        const activeBtn = document.getElementById('btn-tab-' + status);
        if(activeBtn) {
            activeBtn.className = 'tab-btn px-3 py-1.5 rounded-xl bg-slate-900 text-white shadow-sm';
        }

        const labelMap = {
            'ALL': 'แสดงคำร้องทั้งหมด',
            'Pending': 'แสดงเฉพาะคำร้องที่ รอดำเนินการ',
            'Approved': 'แสดงเฉพาะคำร้องที่ อนุมัติแล้ว',
            'Needs_Revision': 'แสดงเฉพาะคำร้องที่ ต้องแก้ไขหลักฐาน'
        };
        const labelElem = document.getElementById('filter_status_label');
        if(labelElem) labelElem.innerText = labelMap[status] || '';

        renderTable();
    }

    function openQuickView(id) {
        const item = requestsData.find(r => r.id === id);
        if (!item) return;

        document.getElementById('modal_course_name').innerText = item.course_name || '-';
        document.getElementById('modal_credits_text').innerText = 'จำนวน: ' + (item.credits || 0) + ' หน่วยกิต';

        const badgeContainer = document.getElementById('modal_status_badge');
        const reasonBox = document.getElementById('modal_reject_reason_box');
        const actionBtn = document.getElementById('modal_action_btn');

        if (item.status === 'Pending') {
            badgeContainer.innerHTML = `<span class="bg-amber-100 text-amber-800 text-xs font-extrabold px-3 py-1.5 rounded-xl">⏳ อยู่ระหว่างการตรวจสอบของเจ้าหน้าที่</span>`;
            reasonBox.classList.add('hidden');
            actionBtn.classList.add('hidden');
        } else if (item.status === 'Approved') {
            badgeContainer.innerHTML = `<span class="bg-emerald-100 text-emerald-800 text-xs font-extrabold px-3 py-1.5 rounded-xl">✅ คำร้องได้รับการอนุมัติเรียบร้อยแล้ว</span>`;
            reasonBox.classList.add('hidden');
            actionBtn.classList.add('hidden');
        } else {
            badgeContainer.innerHTML = `<span class="bg-indigo-100 text-indigo-800 text-xs font-extrabold px-3 py-1.5 rounded-xl">⚠️ ให้แก้ไขหลักฐานเพิ่มเติม</span>`;
            reasonBox.innerText = 'รายละเอียดการแก้ไข: ' + (item.reject_reason || '-');
            reasonBox.classList.remove('hidden');
            actionBtn.href = '/student/edit_request/' + item.id;
            actionBtn.classList.remove('hidden');
        }

        const imgBox = document.getElementById('modal_images_container');
        imgBox.innerHTML = '';
        [item.doc_img, item.doc_img2, item.doc_img3].forEach(img => {
            if (img) {
                imgBox.innerHTML += `<a href="/static/uploads/${img}" target="_blank"><img src="/static/uploads/${img}" class="h-20 w-full object-cover rounded-xl border border-slate-200 hover:opacity-80 transition"></a>`;
            }
        });

        document.getElementById('quickViewModal').classList.remove('hidden');
    }

    function closeQuickView() {
        document.getElementById('quickViewModal').classList.add('hidden');
    }

    document.addEventListener("DOMContentLoaded", function() {
        try {
            renderTable();
        } catch (e) {
            console.error("renderTable error:", e);
        }

        try {
            const pendingCount = requestsData.filter(r => r.status === 'Pending').length;
            const approvedCount = requestsData.filter(r => r.status === 'Approved').length;
            const needEditCount = requestsData.filter(r => r.status === 'Needs_Revision' || r.status === 'Need_Edit').length;

            const chartCanvas = document.getElementById('studentChart');
            if (chartCanvas && typeof Chart !== 'undefined') {
                const ctx = chartCanvas.getContext('2d');
                new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: ['รอดำเนินการ', 'อนุมัติแล้ว', 'ต้องแก้ไข'],
                        datasets: [{
                            data: [pendingCount, approvedCount, needEditCount],
                            backgroundColor: ['#f59e0b', '#10b981', '#6366f1'],
                            borderWidth: 0,
                            hoverOffset: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        cutout: '75%',
                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const index = elements[0].index;
                                const statusMap = ['Pending', 'Approved', 'Needs_Revision'];
                                filterByStatus(statusMap[index]);
                            }
                        }
                    }
                });
            }
        } catch (e) {
            console.error("Chart build error:", e);
        }
    });
    </script>
    """

    js_code = js_template.replace('__REQUESTS_JSON__', req_json_str)
    student_content = html_part + js_code

    return render_layout(student_content, active_page='home')

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))
    course_data = get_courses()
    search_query = request.args.get('search', '').strip().lower()
    selected_provider = request.args.get('provider', '').strip()

    is_searched = bool(search_query or selected_provider)
    filtered_courses = []
    
    if is_searched:
        filtered_courses = course_data
        if selected_provider and selected_provider != "ทั้งหมด":
            filtered_courses = [c for c in filtered_courses if c['provider'] == selected_provider]
        if search_query:
            filtered_courses = [c for c in filtered_courses if search_query in c['name'].lower() or search_query in c['code'].lower() or any(search_query in m.lower() for m in c['mooc_list'])]

    try:
        approved_reqs = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
        approved_courses = [r.course_name for r in approved_reqs]
    except Exception: approved_courses = []

    cards = ""
    for c in filtered_courses:
        badge_prov = "bg-sky-100 text-sky-700 border-sky-200" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-700 border-amber-200"
        
        mooc_items = ""
        for idx_m, m in enumerate(c['mooc_list']):
            mooc_items += f'''
            <div class="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-slate-50 last:border-0 text-xs">
                <div class="flex items-start gap-1.5 text-slate-700 font-medium"><i class="fa-solid fa-check text-sky-400 mt-0.5"></i> <span>{escape(m)}</span></div>
            </div>
            '''
        
        if c['name'] in approved_courses:
            btn = '<div class="text-center w-full bg-emerald-50 text-emerald-600 font-bold py-2.5 rounded-xl text-xs border border-emerald-200"><i class="fa-solid fa-check-circle"></i> เทียบโอนแล้ว</div>'
        else:
            btn = f'<a href="/submit_credit?selected_courses={c["code"]}" class="block text-center w-full bg-slate-900 hover:bg-black text-white font-bold py-2.5 rounded-xl text-xs transition">เลือกวิชานี้</a>'

        cards += f"""
        <div class="bg-white rounded-3xl border border-sky-100 p-6 shadow-sm hover:shadow-md transition card-hover flex flex-col h-full">
            <div class="flex justify-between items-start mb-4">
                <span class="font-mono text-[10px] font-black bg-slate-100 text-slate-500 px-2.5 py-1 rounded-lg tracking-widest">{escape(c['code'])}</span>
                <span class="px-2.5 py-1 rounded-lg text-[10px] font-black border {badge_prov} uppercase">{escape(c['provider'])}</span>
            </div>
            <h3 class="text-lg font-black text-slate-900 leading-snug mb-2">{escape(c['name'])}</h3>
            <div class="mb-4 flex items-center justify-between bg-slate-50 p-2 rounded-xl border border-slate-100 text-xs">
                <span class="font-bold text-slate-500">รวมชั่วโมงเรียน:</span>
                <span class="font-black text-sky-600">{escape(c['total_hours'])}</span>
            </div>
            <div class="mb-5 flex-grow">
                <p class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">บทเรียนออนไลน์ย่อย</p>
                <div>{mooc_items}</div>
            </div>
            <div class="mt-auto border-t border-sky-50 pt-4 flex items-center justify-between gap-3">
                <div class="text-center shrink-0">
                    <p class="text-[10px] font-bold text-slate-400 uppercase">ได้หน่วยกิต</p>
                    <p class="text-lg font-black text-sky-600">{c['credits']}</p>
                </div>
                <div class="flex-grow">{btn}</div>
            </div>
        </div>
        """

    result_display = ""
    if not is_searched:
        result_display = '<div class="py-20 text-center bg-white rounded-3xl border border-dashed border-sky-200"><i class="fa-solid fa-magnifying-glass text-4xl text-sky-300 mb-3 block"></i><p class="text-slate-500 font-bold">กรุณากรอกคำค้นหาด้านบน เพื่อแสดงรายวิชาที่เปิดให้เทียบโอน</p></div>'
    elif is_searched and not filtered_courses:
        result_display = '<div class="py-16 text-center bg-white rounded-3xl border border-rose-200 shadow-sm"><i class="fa-regular fa-face-frown-open text-4xl text-rose-400 mb-3 block"></i><p class="text-slate-800 font-black text-lg mb-1">ไม่พบรายวิชาที่ค้นหา</p><p class="text-slate-500 text-xs">ลองเปลี่ยนคำค้นหา หรือตรวจสอบรหัสวิชาใหม่อีกครั้ง</p></div>'
    else:
        result_display = f'<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">{cards}</div>'

    content = f"""
    <div class="mb-10 text-center max-w-2xl mx-auto">
        <h2 class="text-3xl font-black text-slate-900 mb-3">ค้นหารายวิชาเทียบโอน</h2>
        <p class="text-slate-500 text-sm font-medium">กรุณาพิมพ์ชื่อรายวิชา รหัสวิชา หรือคำค้นหา เพื่อแสดงรายการวิชา</p>
    </div>

    <form method="GET" action="/available_courses" class="max-w-3xl mx-auto bg-white p-3 rounded-[2rem] border border-sky-200 shadow-lg mb-12 flex flex-col sm:flex-row gap-2">
        <div class="flex-grow relative flex items-center">
            <i class="fa-solid fa-magnifying-glass absolute left-5 text-slate-400 text-lg"></i>
            <input type="text" name="search" value="{escape(search_query)}" placeholder="ค้นหา เช่น 'การเขียนโปรแกรม' หรือ '15-02-002'" class="w-full pl-12 pr-4 py-4 text-sm font-bold text-slate-800 bg-transparent outline-none placeholder-slate-400">
        </div>
        <div class="shrink-0 w-full sm:w-48 border-t sm:border-t-0 sm:border-l border-sky-100">
            <select name="provider" class="w-full h-full py-4 px-4 bg-transparent text-sm font-bold text-slate-600 outline-none cursor-pointer">
                <option value="ทั้งหมด" {'selected' if selected_provider=='ทั้งหมด' or not selected_provider else ''}>ทุกระบบ (All)</option>
                <option value="ThaiMOOC" {'selected' if selected_provider=='ThaiMOOC' else ''}>เฉพาะ ThaiMOOC</option>
                <option value="ChulaMOOC" {'selected' if selected_provider=='ChulaMOOC' else ''}>เฉพาะ ChulaMOOC</option>
            </select>
        </div>
        <button type="submit" class="w-full sm:w-auto bg-gradient-to-r from-sky-500 to-blue-600 text-white font-black px-8 py-4 rounded-full hover:shadow-md transition">ค้นหา</button>
    </form>

    {result_display}
    """
    return render_layout(content, active_page='available_courses')

@app.route('/all_courses')
def all_courses():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    try:
        courses_list = Course.query.order_by(Course.course_code.asc()).all()

        rows = ""
        for idx, c in enumerate(courses_list, start=1):
            rows += f"""
            <tr class="hover:bg-slate-50 transition border-b border-slate-100 text-xs">
                <td class="py-3 px-4 font-mono text-slate-400">{idx}</td>
                <td class="py-3 px-4 font-mono font-bold text-sky-600">{escape(c.course_code)}</td>
                <td class="py-3 px-4 font-bold text-slate-800">{escape(c.course_name)}</td>
                <td class="py-3 px-4 text-slate-500">{escape(c.category or '-')}</td>
                <td class="py-3 px-4 text-slate-500">{escape(c.institution or '-')}</td>
                <td class="py-3 px-4 text-center font-bold text-slate-700">{c.credits or 0}</td>
            </tr>
            """

        content = f"""
        <div class="max-w-6xl mx-auto space-y-6">
            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex justify-between items-center">
                <div>
                    <h1 class="text-2xl font-black text-slate-800">รายวิชาเทียบโอนทั้งหมด</h1>
                    <p class="text-xs text-slate-400 mt-1">รวมวิชาในระบบทั้งหมด {len(courses_list)} วิชา</p>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm overflow-x-auto">
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-xs font-black text-slate-400 uppercase">
                        <tr>
                            <th class="py-3 px-4">#</th>
                            <th class="py-3 px-4">รหัสวิชา</th>
                            <th class="py-3 px-4">ชื่อวิชา</th>
                            <th class="py-3 px-4">หมวดวิชา</th>
                            <th class="py-3 px-4">สถาบัน/ระบบ</th>
                            <th class="py-3 px-4 text-center">หน่วยกิต</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">{rows}</tbody>
                </table>
            </div>
        </div>
        """
        return render_layout(content, active_page='all_courses')
    except Exception as e:
        return f"<div style='padding:20px; color:red;'><h3>Database Query Error:</h3><p>{escape(str(e))}</p></div>"

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    user_id = session['user_id']
    msg = ""

    user_info = db.session.get(User, user_id)
    user_faculty = getattr(user_info, 'faculty', 'คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ') or 'คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ'
    user_major = getattr(user_info, 'major', 'สาขาวิชาระบบสารสนเทศ') or 'สาขาวิชาระบบสารสนเทศ'

    try:
        if request.method == 'POST':
            selected_courses = request.form.getlist('selected_courses')
            
            if not selected_courses:
                msg = """
                <div class="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold mb-4">
                    ❌ กรุณาเลือกรายวิชาอย่างน้อย 1 วิชาเพื่อยื่นเทียบโอน
                </div>
                """
            else:
                success_count = 0
                upload_folder = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)

                for course_code in selected_courses:
                    course_info = db.session.get(Course, course_code)
                    if not course_info:
                        continue

                    uploaded_filenames = []
                    lessons = course_info.lessons if hasattr(course_info, 'lessons') and course_info.lessons else []

                    if lessons:
                        for lesson in lessons:
                            file_key = f'file_{course_code}_{lesson.id}'
                            file = request.files.get(file_key)
                            if file and file.filename != '' and allowed_file(file.filename):
                                filename = secure_filename(f"{course_code}_{lesson.id}_{file.filename}")
                                file.save(os.path.join(upload_folder, filename))
                                uploaded_filenames.append(filename)
                    else:
                        file_key = f'file_{course_code}_default'
                        file = request.files.get(file_key)
                        if file and file.filename != '' and allowed_file(file.filename):
                            filename = secure_filename(f"{course_code}_default_{file.filename}")
                            file.save(os.path.join(upload_folder, filename))
                            uploaded_filenames.append(filename)

                    if uploaded_filenames:
                        saved_str = ",".join(uploaded_filenames)
                        doc1 = uploaded_filenames[0] if len(uploaded_filenames) > 0 else None
                        doc2 = uploaded_filenames[1] if len(uploaded_filenames) > 1 else None
                        doc3 = uploaded_filenames[2] if len(uploaded_filenames) > 2 else None

                        existing_req = CreditRequest.query.filter_by(user_id=user_id, course_code=course_code).first()

                        now_th = get_thailand_time()
                        if existing_req:
                            existing_req.id_card_img = saved_str
                            existing_req.doc_img = doc1
                            existing_req.doc_img2 = doc2
                            existing_req.doc_img3 = doc3
                            if hasattr(existing_req, 'course_name'): existing_req.course_name = course_info.course_name
                            if hasattr(existing_req, 'category'): existing_req.category = course_info.category or ''
                            if hasattr(existing_req, 'institution'): existing_req.institution = course_info.institution or ''
                            if hasattr(existing_req, 'credits'): existing_req.credits = course_info.credits or 0
                            if hasattr(existing_req, 'faculty'): existing_req.faculty = user_faculty
                            if hasattr(existing_req, 'major'): existing_req.major = user_major
                            existing_req.status = 'Pending'
                            existing_req.date_submitted = now_th
                        else:
                            generated_req_code = f"TR{uuid.uuid4().hex[:6].upper()}"
                            req_data = {
                                'req_code': generated_req_code,
                                'user_id': user_id,
                                'course_code': course_code,
                                'id_card_img': saved_str,
                                'doc_img': doc1,
                                'doc_img2': doc2,
                                'doc_img3': doc3,
                                'status': 'Pending',
                                'faculty': user_faculty,
                                'major': user_major,
                                'date_submitted': now_th
                            }
                            if hasattr(CreditRequest, 'course_name'): req_data['course_name'] = course_info.course_name or ''
                            if hasattr(CreditRequest, 'category'): req_data['category'] = course_info.category or ''
                            if hasattr(CreditRequest, 'institution'): req_data['institution'] = course_info.institution or ''
                            if hasattr(CreditRequest, 'credits'): req_data['credits'] = course_info.credits or 0

                            new_req = CreditRequest(**req_data)
                            db.session.add(new_req)

                        success_count += 1

                db.session.commit()
                msg = f"""
                <div class="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-bold mb-4">
                    ✅ ยื่นคำขอเทียบโอนสำเร็จรวม {success_count} รายวิชา เรียบร้อยแล้ว
                </div>
                """

        courses = Course.query.order_by(Course.course_code.asc()).all()
        user_requests = CreditRequest.query.filter_by(user_id=user_id).all()
        existing_requests = {req.course_code: req for req in user_requests if hasattr(req, 'course_code')}

        courses_data = []
        table_rows = ""

        for idx, c in enumerate(courses, start=1):
            req = existing_requests.get(c.course_code)
            lessons = c.lessons if hasattr(c, 'lessons') and c.lessons else []
            
            lessons_json = [{'id': l.id, 'name': l.lesson_name, 'hours': l.hours} for l in lessons]
            courses_data.append({
                'code': c.course_code,
                'name': c.course_name,
                'category': c.category or '-',
                'credits': c.credits or 0,
                'lessons': lessons_json
            })

            lesson_count = len(lessons)
            lesson_list_html = ""
            if lessons:
                lessons_items = "".join([f"<li class='text-[11px] text-slate-500'>• {escape(l.lesson_name)} ({l.hours} ชม.)</li>" for l in lessons])
                lesson_list_html = f"<ul class='mt-1 space-y-0.5'>{lessons_items}</ul>"

            if req:
                status_val = req.status or 'Pending'
                status_badge = f'<span class="px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full font-bold text-xs">ยื่นแล้ว ({escape(status_val)})</span>'
                img_str = req.id_card_img or ''
                imgs = img_str.split(",") if img_str else []
                img_links = " ".join([f'<a href="/static/uploads/{escape(img.strip())}" target="_blank" class="text-sky-600 underline font-bold text-xs">รูปที่ {i+1}</a>' for i, img in enumerate(imgs) if img.strip()]) if imgs else "ไม่มีรูป"
                action_area = f'<div class="text-xs text-slate-500">หลักฐานที่แนบไว้: {img_links}</div>'
                checkbox_html = '<input type="checkbox" disabled class="w-4 h-4 rounded text-slate-300 cursor-not-allowed">'
            else:
                status_badge = '<span class="px-3 py-1 bg-slate-100 text-slate-400 rounded-full font-bold text-xs">ยังไม่ได้ยื่น</span>'
                action_area = f"""
                <div class="p-3 bg-slate-50 rounded-2xl border border-slate-100">
                    <div class="text-[11px] font-bold text-slate-700">บทเรียนที่ต้องเรียน ({lesson_count} บท):</div>
                    {lesson_list_html if lesson_count > 0 else '<span class="text-[11px] text-slate-400">ไม่มีบทเรียนย่อย</span>'}
                </div>
                """
                checkbox_html = f'<input type="checkbox" value="{escape(c.course_code)}" onchange="toggleCourseSelection(\'{escape(c.course_code)}\')" class="course-select-cb w-4 h-4 text-sky-600 rounded border-slate-300 focus:ring-sky-500 cursor-pointer">'

            table_rows += f"""
            <tr class="border-b border-slate-100 hover:bg-slate-50/50 transition" id="row-{escape(c.course_code)}">
                <td class="py-4 px-4 text-center">{checkbox_html}</td>
                <td class="py-4 px-4 font-mono text-slate-400 text-xs">{idx}</td>
                <td class="py-4 px-4 font-mono font-bold text-sky-600 text-xs">{escape(c.course_code)}</td>
                <td class="py-4 px-4 font-bold text-slate-800 text-xs">
                    <div>{escape(c.course_name)}</div>
                    <div class="text-[11px] text-slate-400 font-normal">{escape(c.category or '-')} | {c.credits or 0} หน่วยกิต</div>
                </td>
                <td class="py-4 px-4">{status_badge}</td>
                <td class="py-4 px-4">{action_area}</td>
            </tr>
            """

        content = f"""
        <div class="max-w-6xl mx-auto space-y-6">
            {msg}

            <div id="step-1-container" class="bg-white p-8 rounded-3xl border border-slate-100 shadow-sm space-y-6 relative">
                <div class="sticky top-4 z-30 bg-white/95 backdrop-blur-md p-5 rounded-2xl border border-slate-200 shadow-md flex justify-between items-center transition-all">
                    <div>
                        <h1 class="text-xl font-black text-slate-800">1. เลือกรายวิชาที่ต้องการเทียบโอน</h1>
                        <p class="text-xs text-slate-400 mt-0.5">ติ๊กเลือกรายวิชาที่ต้องการยื่น แล้วกดปุ่มดำเนินการแนบหลักฐาน</p>
                    </div>
                    <button id="btn-to-step2" onclick="goToStep2()" disabled class="bg-slate-200 text-slate-400 font-bold py-2.5 px-6 rounded-2xl text-xs transition shadow-sm cursor-not-allowed">
                        ถัดไป: แนบหลักฐาน (<span id="selected-count">0</span> วิชา)
                    </button>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left">
                        <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase">
                            <tr>
                                <th class="py-3 px-4 text-center">เลือก</th>
                                <th class="py-3 px-4">#</th>
                                <th class="py-3 px-4">รหัสวิชา</th>
                                <th class="py-3 px-4">ชื่อวิชา / หมวด / หน่วยกิต</th>
                                <th class="py-3 px-4">สถานะ</th>
                                <th class="py-3 px-4">บทเรียนย่อย</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <form id="step-2-form" method="POST" action="/submit_credit" enctype="multipart/form-data" class="hidden space-y-6">
                <div class="bg-white p-8 rounded-3xl border border-slate-100 shadow-sm space-y-6">
                    <div class="flex justify-between items-center border-b border-slate-100 pb-4">
                        <div>
                            <h1 class="text-2xl font-black text-slate-800">2. แนบรูปภาพหลักฐานตามบทเรียน</h1>
                            <p class="text-xs text-slate-400 mt-1">อัปโหลดรูปภาพหลักฐานให้ตรงตามชื่อบทเรียนของแต่ละวิชา</p>
                        </div>
                        <button type="button" onclick="goToStep1()" class="text-xs font-bold text-slate-500 hover:text-slate-800 bg-slate-100 py-2 px-4 rounded-xl">
                            ← ย้อนกลับไปเลือกวิชาเพิ่ม
                        </button>
                    </div>

                    <div id="upload-cards-container" class="space-y-6"></div>

                    <div class="pt-4 border-t border-slate-100 flex justify-end gap-3">
                        <button type="button" onclick="goToStep1()" class="bg-slate-100 text-slate-600 font-bold py-3 px-6 rounded-2xl text-xs hover:bg-slate-200 transition">
                            ยกเลิก
                        </button>
                        <button type="submit" class="bg-sky-600 hover:bg-sky-700 text-white font-bold py-3 px-8 rounded-2xl text-xs transition shadow-md">
                            ยื่นคำขอเทียบโอนทั้งหมด
                        </button>
                    </div>
                </div>
            </form>
        </div>

        <script>
            const allCoursesData = {json.dumps(courses_data)};
            let selectedCourseCodes = new Set();

            function toggleCourseSelection(code) {{
                if (selectedCourseCodes.has(code)) {{
                    selectedCourseCodes.delete(code);
                }} else {{
                    selectedCourseCodes.add(code);
                }}
                updateStep1UI();
            }}

            function updateStep1UI() {{
                const count = selectedCourseCodes.size;
                document.getElementById('selected-count').innerText = count;
                const btn = document.getElementById('btn-to-step2');
                if (count > 0) {{
                    btn.disabled = false;
                    btn.className = "bg-sky-600 hover:bg-sky-700 text-white font-bold py-2.5 px-6 rounded-2xl text-xs transition shadow-md cursor-pointer";
                }} else {{
                    btn.disabled = true;
                    btn.className = "bg-slate-200 text-slate-400 font-bold py-2.5 px-6 rounded-2xl text-xs transition shadow-sm cursor-not-allowed";
                }}
            }}

            function removeCourse(code) {{
                selectedCourseCodes.delete(code);
                const cb = document.querySelector(`.course-select-cb[value="${{code}}"]`);
                if (cb) cb.checked = false;
                
                updateStep1UI();
                renderUploadCards();

                if (selectedCourseCodes.size === 0) {{
                    goToStep1();
                }}
            }}

            function previewImage(input, previewId) {{
                const previewImg = document.getElementById(previewId);
                if (input.files && input.files[0]) {{
                    const reader = new FileReader();
                    reader.onload = function(e) {{
                        previewImg.src = e.target.result;
                        previewImg.classList.remove('hidden');
                    }}
                    reader.readAsDataURL(input.files[0]);
                }} else {{
                    previewImg.src = '';
                    previewImg.classList.add('hidden');
                }}
            }}

            function renderUploadCards() {{
                const container = document.getElementById('upload-cards-container');
                container.innerHTML = '';

                selectedCourseCodes.forEach(code => {{
                    const course = allCoursesData.find(c => c.code === code);
                    if (!course) return;

                    let lessonsHTML = '';
                    if (course.lessons && course.lessons.length > 0) {{
                        course.lessons.forEach((l, idx) => {{
                            const previewId = `prev_${{course.code}}_${{l.id}}`;
                            lessonsHTML += `
                                <div class="p-4 bg-slate-50 rounded-2xl border border-slate-100 space-y-3">
                                    <label class="block text-xs font-bold text-slate-700">
                                        📌 บทเรียนที่ ${{idx + 1}}: ${{l.name}} (${{l.hours}} ชม.)
                                    </label>
                                    <input type="file" name="file_${{course.code}}_${{l.id}}" accept="image/*" required
                                        onchange="previewImage(this, '${{previewId}}')"
                                        class="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer">
                                    <div class="mt-2">
                                        <img id="${{previewId}}" src="" alt="ตัวอย่างหลักฐาน" class="hidden max-h-48 rounded-xl border border-slate-200 shadow-sm object-contain bg-white p-1">
                                    </div>
                                </div>
                            `;
                        }});
                    }} else {{
                        const previewId = `prev_${{course.code}}_default`;
                        lessonsHTML = `
                            <div class="p-4 bg-slate-50 rounded-2xl border border-slate-100 space-y-3">
                                <label class="block text-xs font-bold text-slate-700">📌 หลักฐานการเรียน (วิชานี้ไม่มีบทเรียนย่อย):</label>
                                <input type="file" name="file_${{course.code}}_default" accept="image/*" required
                                    onchange="previewImage(this, '${{previewId}}')"
                                    class="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer">
                                <div class="mt-2">
                                    <img id="${{previewId}}" src="" alt="ตัวอย่างหลักฐาน" class="hidden max-h-48 rounded-xl border border-slate-200 shadow-sm object-contain bg-white p-1">
                                </div>
                            </div>
                        `;
                    }}

                    const cardHTML = `
                        <div class="p-6 rounded-3xl border border-slate-200 bg-white space-y-4 shadow-sm relative">
                            <input type="hidden" name="selected_courses" value="${{course.code}}">
                            
                            <div class="flex justify-between items-start border-b border-slate-100 pb-3">
                                <div>
                                    <span class="font-mono text-xs font-bold text-sky-600">${{course.code}}</span>
                                    <h3 class="text-sm font-bold text-slate-800">${{course.name}}</h3>
                                    <p class="text-[11px] text-slate-400">${{course.category}} | ${{course.credits}} หน่วยกิต</p>
                                </div>
                                <button type="button" onclick="removeCourse('${{course.code}}')" class="text-xs font-bold text-rose-500 hover:text-rose-700 bg-rose-50 py-1.5 px-3 rounded-xl hover:bg-rose-100 transition">
                                    🗑️ ลบวิชานี้ออก
                                </button>
                            </div>

                            <div class="space-y-3">
                                ${{lessonsHTML}}
                            </div>
                        </div>
                    `;
                    container.innerHTML += cardHTML;
                }});
            }}

            function goToStep2() {{
                if (selectedCourseCodes.size === 0) return;
                renderUploadCards();
                document.getElementById('step-1-container').classList.add('hidden');
                document.getElementById('step-2-form').classList.remove('hidden');
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}

            function goToStep1() {{
                document.getElementById('step-2-form').classList.add('hidden');
                document.getElementById('step-1-container').classList.remove('hidden');
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        </script>
        """
        return render_layout(content, active_page='submit_credit')

    except Exception as e:
        db.session.rollback()
        return f"<div style='padding:20px; color:red;'><h3>System Error:</h3><p>{escape(str(e))}</p></div>"

@app.route('/history')
def student_history():
    if not session.get('user_id'): 
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    requests = CreditRequest.query.filter_by(user_id=user.id).order_by(CreditRequest.id.desc()).all()

    pending_count = sum(1 for r in requests if r.status == 'Pending')
    approved_count = sum(1 for r in requests if r.status == 'Approved')
    revision_count = sum(1 for r in requests if r.status in ['Needs_Revision', 'Need_Edit'])

    requests_json = json.dumps([{
        'id': r.id,
        'req_code': getattr(r, 'req_code', f'TR{r.id:04d}'),
        'course_name': r.course_name,
        'credits': r.credits,
        'status': r.status,
        'reject_reason': getattr(r, 'reject_reason', '') or '-',
        'date_submitted': getattr(r, 'date_submitted', '-')
    } for r in requests], ensure_ascii=False)

    content = f"""
    <div class="max-w-6xl mx-auto space-y-6">
        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <h1 class="text-2xl font-black text-slate-800">ประวัติการยื่นขอเทียบโอนหน่วยกิต</h1>
                <p class="text-xs text-slate-400 mt-1">ตรวจสอบสถานะและประวัติคำร้องทั้งหมดของคุณ</p>
            </div>
            <a href="/submit_credit" class="bg-sky-600 hover:bg-sky-700 text-white font-extrabold px-5 py-2.5 rounded-2xl text-xs transition flex items-center gap-2">
                <i class="fa-solid fa-plus"></i> ยื่นคำขอใหม่
            </a>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div onclick="filterHistory('ALL')" class="cursor-pointer bg-white p-5 rounded-2xl border border-slate-200 shadow-sm hover:border-slate-400 transition">
                <p class="text-xs font-extrabold text-slate-400 uppercase">ทั้งหมด</p>
                <p class="text-2xl font-black text-slate-800 mt-1">{len(requests)}</p>
            </div>
            <div onclick="filterHistory('Pending')" class="cursor-pointer bg-white p-5 rounded-2xl border border-amber-200 shadow-sm hover:bg-amber-50/50 transition">
                <p class="text-xs font-extrabold text-amber-600 uppercase">⏳ รอดำเนินการ</p>
                <p class="text-2xl font-black text-amber-700 mt-1">{pending_count}</p>
            </div>
            <div onclick="filterHistory('Approved')" class="cursor-pointer bg-white p-5 rounded-2xl border border-emerald-200 shadow-sm hover:bg-emerald-50/50 transition">
                <p class="text-xs font-extrabold text-emerald-600 uppercase">✅ อนุมัติแล้ว</p>
                <p class="text-2xl font-black text-emerald-700 mt-1">{approved_count}</p>
            </div>
            <div onclick="filterHistory('Revision')" class="cursor-pointer bg-white p-5 rounded-2xl border border-indigo-200 shadow-sm hover:bg-indigo-50/50 transition">
                <p class="text-xs font-extrabold text-indigo-600 uppercase">⚠️ ต้องแก้ไขหลักฐาน</p>
                <p class="text-2xl font-black text-indigo-700 mt-1">{revision_count}</p>
            </div>
        </div>

        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
            <div class="flex flex-wrap gap-2 border-b border-slate-100 pb-4">
                <button onclick="filterHistory('ALL')" id="tab-ALL" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 text-white">ทั้งหมด ({len(requests)})</button>
                <button onclick="filterHistory('Pending')" id="tab-Pending" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:bg-slate-100">รอดำเนินการ ({pending_count})</button>
                <button onclick="filterHistory('Approved')" id="tab-Approved" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:bg-slate-100">อนุมัติแล้ว ({approved_count})</button>
                <button onclick="filterHistory('Revision')" id="tab-Revision" class="tab-btn px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:bg-slate-100">ต้องแก้ไข ({revision_count})</button>
            </div>

            <div class="overflow-x-auto max-h-[420px] overflow-y-auto pr-2">
                <table class="w-full text-sm text-left">
                    <thead class="text-xs text-slate-400 font-extrabold uppercase bg-slate-50 rounded-xl">
                        <tr>
                            <th class="px-4 py-3 rounded-l-xl">รหัสคำร้อง</th>
                            <th class="px-4 py-3">รายวิชาที่ยื่นเทียบโอน</th>
                            <th class="px-4 py-3 text-center">หน่วยกิต</th>
                            <th class="px-4 py-3 text-center">วันที่ยื่น</th>
                            <th class="px-4 py-3 text-center">สถานะ</th>
                            <th class="px-4 py-3 text-right rounded-r-xl">การจัดการ</th>
                        </tr>
                    </thead>
                    <tbody id="history_tbody" class="divide-y divide-slate-100"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
    const historyData = {requests_json};

    function filterHistory(status) {{
        const tbody = document.getElementById('history_tbody');
        tbody.innerHTML = '';

        document.querySelectorAll('.tab-btn').forEach(b => {{
            b.className = 'tab-btn px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:bg-slate-100';
        }});
        const activeTab = document.getElementById('tab-' + status);
        if(activeTab) activeTab.className = 'tab-btn px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 text-white';

        const filtered = historyData.filter(r => {{
            if (status === 'ALL') return true;
            if (status === 'Pending') return r.status === 'Pending';
            if (status === 'Approved') return r.status === 'Approved';
            if (status === 'Revision') return r.status === 'Needs_Revision' || r.status === 'Need_Edit';
            return true;
        }});

        if (filtered.length === 0) {{
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-xs font-bold text-slate-400">ไม่พบคำร้องในสถานะนี้</td></tr>`;
            return;
        }}

        filtered.forEach(item => {{
            let badge = '';
            if (item.status === 'Pending') {{
                badge = `<span class="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-bold px-2.5 py-1 rounded-full">⏳ รอดำเนินการ</span>`;
            }} else if (item.status === 'Approved') {{
                badge = `<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold px-2.5 py-1 rounded-full">✅ อนุมัติแล้ว</span>`;
            }} else {{
                badge = `<span class="bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-bold px-2.5 py-1 rounded-full">⚠️ ให้แก้ไข</span>`;
            }}

            const tr = document.createElement('tr');
            tr.className = 'hover:bg-slate-50 transition';
            tr.innerHTML = `
                <td class="px-4 py-3.5 font-mono font-bold text-sky-600 text-xs">${{item.req_code}}</td>
                <td class="px-4 py-3.5 font-bold text-slate-800">${{item.course_name}}</td>
                <td class="px-4 py-3.5 text-center font-bold text-slate-600">${{item.credits}}</td>
                <td class="px-4 py-3.5 text-center text-xs text-slate-400 font-medium">${{item.date_submitted}}</td>
                <td class="px-4 py-3.5 text-center">${{badge}}</td>
                <td class="px-4 py-3.5 text-right">
                    ${{item.status !== 'Approved' && item.status !== 'Pending' ? 
                        `<a href="/student/edit_request/${{item.id}}" class="bg-indigo-50 text-indigo-600 font-bold px-3 py-1.5 rounded-xl text-xs hover:bg-indigo-100 transition">แก้ไขหลักฐาน</a>` : 
                        `<span class="text-xs text-slate-300">-</span>`
                    }}
                </td>
            `;
            tbody.appendChild(tr);
        }});
    }}

    document.addEventListener('DOMContentLoaded', () => filterHistory('ALL'));
    </script>
    """
    return render_layout(content, active_page='history')

@app.route('/student/edit_request/<int:req_id>', methods=['GET', 'POST'])
def student_edit_request(req_id):
    if 'user_id' not in session: 
        return redirect(url_for('login'))
        
    req = CreditRequest.query.get_or_404(req_id)
    if req.user_id != session['user_id']: 
        return redirect(url_for('student_history'))

    existing_imgs = []
    if getattr(req, 'doc_img', None): existing_imgs.append(req.doc_img)
    if getattr(req, 'doc_img2', None): existing_imgs.append(req.doc_img2)
    if getattr(req, 'doc_img3', None): existing_imgs.append(req.doc_img3)
    
    if not existing_imgs and getattr(req, 'id_card_img', None):
        existing_imgs = [img.strip() for img in req.id_card_img.split(',') if img.strip()]

    if request.method == 'POST':
        try:
            upload_folder = os.path.join(app.root_path, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            
            new_imgs = list(existing_imgs)

            for i in range(3):
                file_key = f'cert_file_{i}'
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename != '' and allowed_file(file.filename):
                        ext = file.filename.rsplit('.', 1)[1].lower()
                        filename = secure_filename(f"cert_{req.id}_{i+1}_{uuid.uuid4().hex[:6]}.{ext}")
                        file.save(os.path.join(upload_folder, filename))
                        
                        if i < len(new_imgs):
                            new_imgs[i] = filename
                        else:
                            new_imgs.append(filename)

            req.doc_img = new_imgs[0] if len(new_imgs) > 0 else None
            req.doc_img2 = new_imgs[1] if len(new_imgs) > 1 else None
            req.doc_img3 = new_imgs[2] if len(new_imgs) > 2 else None
            req.id_card_img = ",".join(new_imgs) if new_imgs else None

            req.status = 'Pending'
            req.reject_reason = None
            req.date_submitted = get_thailand_time()
            db.session.commit()
            
            flash('✅ อัปเดตหลักฐานและส่งกลับให้เจ้าหน้าที่ตรวจสอบเรียบร้อยแล้ว', 'success')
            return redirect(url_for('student_history'))

        except Exception as e:
            db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {str(e)}', 'error')
            return redirect(url_for('student_edit_request', req_id=req_id))

    course_data_list = get_courses()
    matched_course = next((c for c in course_data_list if c['name'] == req.course_name or c['code'] == req.course_code), None)
    mooc_names = matched_course['mooc_list'] if matched_course else []

    def get_mooc_title(index):
        if index < len(mooc_names):
            return f"หลักฐานที่ {index+1} : {mooc_names[index]}"
        return f"หลักฐานที่ {index+1}"

    ev_html = ""
    display_count = max(len(existing_imgs), 1)
    
    for idx in range(display_count):
        img_filename = existing_imgs[idx] if idx < len(existing_imgs) else None
        title = get_mooc_title(idx)
        
        img_tag = f'<img id="preview-img-{idx}" src="/static/uploads/{escape(img_filename)}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain bg-white p-1 border border-slate-200">' if img_filename else f'<img id="preview-img-{idx}" src="" class="hidden max-h-40 rounded-xl mb-3 shadow-sm object-contain bg-white p-1 border border-slate-200">'
        
        ev_html += f"""
        <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 space-y-2">
            <p class="text-sm font-bold text-sky-700">{escape(title)}</p>
            <div>{img_tag}</div>
            <input type="file" name="cert_file_{idx}" accept="image/*" onchange="previewImage(event, 'preview-img-{idx}')" class="w-full text-xs font-medium file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-sky-600 file:text-white hover:file:bg-sky-700 cursor-pointer">
        </div>
        """

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl space-y-6">
        <div>
            <h3 class="text-2xl font-black text-slate-900 mb-1">แก้ไขหลักฐานคำร้อง</h3>
            <p class="text-sm font-bold text-sky-600">{escape(req.course_name)} ({escape(getattr(req, 'course_code', '-') or '-')})</p>
        </div>

        <div class="bg-rose-50 border border-rose-200 p-4 rounded-2xl">
            <p class="text-xs font-bold text-rose-500 uppercase">เหตุผลที่ต้องแก้ไขจากเจ้าหน้าที่:</p>
            <p class="text-sm font-extrabold text-rose-700 mt-0.5">{escape(getattr(req, 'reject_reason', '') or "กรุณาตรวจสอบและอัปโหลดรูปภาพหลักฐานที่ชัดเจนใหม่อีกครั้ง")}</p>
        </div>

        <form method="POST" enctype="multipart/form-data" class="space-y-6">
            <div class="space-y-4">
                {ev_html}
            </div>
            
            <div class="flex gap-3 pt-2">
                <a href="/history" class="w-1/3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold py-3.5 rounded-2xl text-xs text-center transition flex items-center justify-center">ยกเลิก</a>
                <button type="submit" class="w-2/3 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white font-extrabold py-3.5 rounded-2xl shadow-md text-xs transition">บันทึกและส่งให้เจ้าหน้าที่ตรวจสอบอีกครั้ง</button>
            </div>
        </form>
    </div>

    <script>
        function previewImage(event, imgId) {{
            const input = event.target;
            const preview = document.getElementById(imgId);
            if (input.files && input.files[0]) {{
                const reader = new FileReader();
                reader.onload = function(e) {{
                    preview.src = e.target.result;
                    preview.classList.remove('hidden');
                }};
                reader.readAsDataURL(input.files[0]);
            }}
        }}
    </script>
    """
    
    return render_layout(content, active_page='history')

@app.route('/credits')
def credits():
    if 'user_id' not in session: return redirect(url_for('login'))
    try: approved_requests = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
    except Exception: approved_requests = []

    total_approved = sum(getattr(r, 'credits', 0) or 0 for r in approved_requests)
    rows = ""
    for r in approved_requests:
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-extrabold text-slate-900">{escape(getattr(r, 'course_name', '-'))}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{escape(getattr(r, 'institution', '-'))}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{escape(getattr(r, 'approved_by', 'เจ้าหน้าที่') or 'เจ้าหน้าที่')}</td>
        </tr>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-black text-slate-900">💳 หน่วยกิตสะสมสาขา IS ({total_approved} หน่วยกิต)</h2></div>
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <table class="w-full text-left min-w-[600px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider"><tr><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">ผู้อนุมัติ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-12 text-center text-slate-400 text-sm">ยังไม่มีรายการหน่วยกิตที่ได้รับการอนุมัติ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_layout(content, active_page='credits')

@app.route('/admin/requests')
def admin_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    
    status_filter = request.args.get('status', '').strip()
    
    try:
        query = CreditRequest.query
        if status_filter:
            query = query.filter_by(status=status_filter)
        all_requests = query.order_by(CreditRequest.id.desc()).all()
    except Exception: 
        all_requests = []

    rows = ""
    for r in all_requests:
        status_val = getattr(r, 'status', 'Pending')
        if status_val == 'Pending':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอตรวจ</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="bg-gradient-to-r from-sky-500 to-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:from-sky-600 hover:to-blue-700 inline-block shadow-sm">พิจารณาคำร้อง</a>'
        elif status_val == 'Approved':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ดูรายละเอียด</a>'
        else:
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800">ส่งกลับให้แก้</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ตรวจสอบการแก้ไข</a>'

        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'

        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-mono font-bold text-sky-600">{escape(getattr(r, 'req_code', f'TR{r.id:04d}'))}</td>
            <td class="py-4 px-4 font-bold text-slate-900">{escape(student_name)}<br><span class="text-xs text-sky-600 font-semibold">({escape(student_code)})</span></td>
            <td class="py-4 px-4 text-slate-700 font-medium">{escape(getattr(r, 'course_name', '-'))}</td>
            <td class="py-4 px-4 text-slate-500 text-xs font-medium">{escape(getattr(r, 'date_submitted', '-'))}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{action_col}</td>
        </tr>
        """
        
    filter_label = "ทั้งหมด"
    if status_filter == 'Approved': filter_label = "อนุมัติแล้ว"
    elif status_filter == 'Pending': filter_label = "รอดำเนินการ"
    elif status_filter in ['Needs_Revision', 'Need_Edit']: filter_label = "ส่งกลับให้แก้ไข"

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto space-y-6">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
                <h3 class="text-xl font-black text-slate-900">รายการคำร้องเทียบโอนทั้งหมด (สาขาวิชาระบบสารสนเทศ)</h3>
                <p class="text-xs text-slate-400 mt-1">กำลังแสดงหมวด: <span class="font-bold text-sky-600">{escape(filter_label)}</span></p>
            </div>
            <div class="flex flex-wrap gap-2 text-xs font-bold">
                <a href="/admin/requests" class="px-3 py-2 rounded-xl border {'bg-slate-900 text-white' if not status_filter else 'bg-slate-50 text-slate-600'}">ทั้งหมด</a>
                <a href="/admin/requests?status=Pending" class="px-3 py-2 rounded-xl border {'bg-amber-500 text-white' if status_filter=='Pending' else 'bg-amber-50 text-amber-700 border-amber-200'}">รอดำเนินการ</a>
                <a href="/admin/requests?status=Approved" class="px-3 py-2 rounded-xl border {'bg-emerald-600 text-white' if status_filter=='Approved' else 'bg-emerald-50 text-emerald-700 border-emerald-200'}">อนุมัติแล้ว</a>
            </div>
        </div>
        
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">ชื่อนักศึกษา</th><th class="py-3 px-4">วิชาที่ขอเทียบโอน</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400">ไม่มีคำร้องในรายการนี้</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_layout(content, active_page='admin_requests')

@app.route('/admin/review/<int:req_id>', methods=['GET', 'POST'])
def admin_review(req_id):
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    if request.method == 'POST':
        action = request.form.get('action')
        admin_user = db.session.get(User, session['user_id'])
        if action == 'approve':
            req.status = 'Approved'
            req.approved_by = admin_user.fullname if admin_user else 'เจ้าหน้าที่'
            db.session.commit()
            flash('อนุมัติผ่านเรียบร้อย', 'success')
            return redirect(url_for('admin_requests'))
        elif action == 'reject':
            req.status = 'Rejected'
            req.reject_reason = request.form.get('reject_reason', '-')
            req.approved_by = admin_user.fullname if admin_user else 'เจ้าหน้าที่'
            db.session.commit()
            flash('ปฏิเสธคำร้องเรียบร้อย', 'success')
            return redirect(url_for('admin_requests'))
        elif action == 'revision':
            req.status = 'Needs_Revision'
            req.reject_reason = request.form.get('reject_reason', 'กรุณาแก้ไขรูปหลักฐานให้ถูกต้อง')
            req.approved_by = admin_user.fullname if admin_user else 'เจ้าหน้าที่'
            db.session.commit()
            flash('ส่งกลับให้นักศึกษาแก้ไขหลักฐานเรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin_requests'))

    course_data_list = get_courses()
    matched_course = next((c for c in course_data_list if c['name'] == req.course_name), None)
    mooc_names = matched_course['mooc_list'] if matched_course else []

    def get_mooc_title(index, default_title):
        if index < len(mooc_names): return f"{default_title} : {mooc_names[index]}"
        return default_title

    evidence_html = ""
    if getattr(req, 'doc_img', None):
        title = get_mooc_title(0, "หลักฐานที่ 1")
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{escape(title)}</span><a href="/static/uploads/{escape(req.doc_img)}" target="_blank"><img src="/static/uploads/{escape(req.doc_img)}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'
    if getattr(req, 'doc_img2', None):
        title = get_mooc_title(1, "หลักฐานที่ 2")
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{escape(title)}</span><a href="/static/uploads/{escape(req.doc_img2)}" target="_blank"><img src="/static/uploads/{escape(req.doc_img2)}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'
    if getattr(req, 'doc_img3', None):
        title = get_mooc_title(2, "หลักฐานที่ 3")
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{escape(title)}</span><a href="/static/uploads/{escape(req.doc_img3)}" target="_blank"><img src="/static/uploads/{escape(req.doc_img3)}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'

    student = req.user
    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <div class="flex justify-between items-center mb-6">
            <h3 class="text-xl font-black text-slate-900">พิจารณาคำร้อง: {escape(req.course_name)}</h3>
            <span class="bg-slate-100 text-slate-600 px-3 py-1 rounded-lg text-xs font-bold">{escape(getattr(req, 'req_code', f'TR{req.id:04d}'))}</span>
        </div>

        <div class="bg-sky-50/50 p-6 rounded-2xl border border-sky-100 mb-6 flex gap-8 text-sm">
            <div><p class="text-xs font-bold text-slate-400 mb-1">นักศึกษา</p><p class="font-bold">{escape(student.fullname) if student else '-'}</p></div>
            <div><p class="text-xs font-bold text-slate-400 mb-1">ระบบ</p><p class="font-bold">{escape(getattr(req, 'institution', '-'))}</p></div>
            <div><p class="text-xs font-bold text-slate-400 mb-1">หน่วยกิต</p><p class="font-bold text-sky-600">{getattr(req, 'credits', 0)}</p></div>
        </div>

        <h4 class="font-black text-slate-800 mb-3"><i class="fa-solid fa-images text-sky-500 mr-2"></i> ตรวจสอบหลักฐาน</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {evidence_html if evidence_html else '<p class="text-xs text-slate-400">ไม่มีรูปภาพ</p>'}
        </div>

        <form method="POST" class="border-t border-slate-100 pt-6 space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 mb-2">ระบุเหตุผล / ข้อเสนอแนะ (กรณีไม่อนุมัติ หรือ ส่งกลับให้แก้ไข)</label>
                <textarea name="reject_reason" placeholder="เช่น รูปภาพไม่ชัดเจน กรุณาอัปโหลดใหม่" class="w-full border border-slate-200 rounded-xl p-3 text-sm bg-slate-50 outline-none focus:border-sky-300"></textarea>
            </div>
            <div class="flex justify-end gap-3">
                <button type="submit" name="action" value="revision" class="px-6 py-3 bg-indigo-100 text-indigo-700 hover:bg-indigo-600 hover:text-white font-bold rounded-xl text-sm transition">ส่งกลับให้แก้ไขรูป</button>
                <button type="submit" name="action" value="approve" class="px-8 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl text-sm shadow-md transition">✅ อนุมัติผ่าน</button>
            </div>
        </form>
    </div>
    """
    return render_layout(content, active_page='admin_requests')

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user: return redirect(url_for('login'))
    display_title = "เจ้าหน้าที่" if user.role in ['admin', 'superadmin'] else f"{user.prefix or ''} {user.fullname}"
    
    edit_btn_html = ""
    if user.role not in ['admin', 'superadmin']:
        edit_btn_html = '<a href="/request_edit_profile" class="absolute top-6 right-6 bg-sky-100 hover:bg-sky-200 text-sky-700 px-4 py-2 rounded-xl text-xs font-bold transition-all"><i class="fa-solid fa-pen mr-1"></i> แก้ไขข้อมูล</a>'

    content = f"""
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl relative">
        {edit_btn_html}
        <h3 class="text-2xl font-black text-slate-900 mb-1">{escape(display_title)}</h3>
        <p class="text-sm font-bold text-sky-600 mb-1">รหัสนักศึกษา: {escape(user.member_id or '-')}</p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5 bg-sky-50/50 p-6 rounded-2xl border border-sky-100 text-sm mt-6">
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ชื่อ-สกุล</span> <span class="font-bold text-slate-800">{escape(user.fullname)}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เลขบัตรประชาชน</span> <span class="font-bold text-slate-800">{escape(user.id_card or '-')}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เบอร์โทรศัพท์</span> <span class="font-bold text-slate-800">{escape(user.phone or '-')}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">อีเมล</span> <span class="font-bold text-slate-800">{escape(user.email or '-')}</span></div>
            <div class="md:col-span-2"><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ที่อยู่</span> <span class="font-bold text-slate-800">{escape(user.address or '-')}</span></div>
        </div>
    </div>
    """
    return render_layout(content, active_page='profile')

@app.route('/request_edit_profile', methods=['GET', 'POST'])
def request_edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        user.prefix = request.form.get('prefix')
        user.fullname = request.form.get('fullname')
        user.phone = request.form.get('phone')
        user.email = request.form.get('email')
        
        house_no = request.form.get('house_no', '')
        moo = request.form.get('moo', '')
        soi = request.form.get('soi', '')
        subdistrict = request.form.get('subdistrict', '')
        district = request.form.get('district', '')
        province = request.form.get('province', '')
        postal_code = request.form.get('postal_code', '')

        new_addr = format_address(house_no, moo, soi, subdistrict, district, province, postal_code)
        if new_addr: user.address = new_addr
        
        db.session.commit()
        flash('✅ บันทึกข้อมูลส่วนตัวและที่อยู่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('profile'))

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">แก้ไขข้อมูลส่วนตัวและที่อยู่</h3>
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">คำนำหน้า</label>
                <select name="prefix" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50">
                    <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                    <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                    <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                </select></div>
                <div class="col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">ชื่อ-นามสกุล</label><input type="text" name="fullname" value="{escape(user.fullname)}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">เบอร์โทรศัพท์</label><input type="tel" name="phone" value="{escape(user.phone or '')}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">อีเมล</label><input type="email" name="email" value="{escape(user.email or '')}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-4">บันทึกการเปลี่ยนแปลง</button>
        </form>
    </div>
    """
    return render_layout(content, active_page='profile')

@app.route('/admin/students')
def admin_students():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    try: students = User.query.filter_by(role='student').order_by(User.id.desc()).all()
    except Exception: students = []

    rows = ""
    for s in students:
        try: approved_credits = sum(r.credits for r in CreditRequest.query.filter_by(user_id=s.id, status='Approved').all() if r.credits)
        except Exception: approved_credits = 0
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-bold text-sky-600 font-mono">{escape(s.member_id or '-')}<br><span class="text-xs text-slate-400 font-normal">({escape(s.id_card or '-')})</span></td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{escape(s.prefix or '')} {escape(s.fullname)}<br><span class="text-xs text-slate-500 font-normal">สาขาวิชาระบบสารสนเทศ</span></td>
            <td class="py-4 px-4 text-xs text-slate-600 font-medium">{escape(s.phone or '-')}<br>{escape(s.email or '-')}</td>
            <td class="py-4 px-4 font-black text-center"><span class="bg-sky-50 text-sky-700 px-3 py-1 rounded-full text-xs font-bold border border-sky-100">{approved_credits} หน่วยกิต</span></td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายชื่อนักศึกษาสาขาวิชาระบบสารสนเทศ</h3>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสนักศึกษา</th><th class="py-3 px-4">ชื่อ-นามสกุล</th><th class="py-3 px-4">ติดต่อ</th><th class="py-3 px-4 text-center">หน่วยกิตสะสม</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-12 text-center text-slate-400">ยังไม่มีนักศึกษา</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_layout(content, active_page='admin_students')

@app.route('/admin/manage_admins', methods=['GET', 'POST'])
def manage_admins():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    
    current_user = db.session.get(User, session['user_id'])
    if not current_user or current_user.role not in ['admin', 'superadmin']:
        flash('ไม่มีสิทธิ์เข้าถึงส่วนงานนี้', 'error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        prefix = request.form.get('prefix', '').strip()
        username_input = request.form.get('username', '').strip()
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()

        existing_user = User.query.filter((User.username == username_input) | (User.id_card == username_input)).first()
        if existing_user:
            flash('เลขบัตรประชาชน / Username นี้มีอยู่ในระบบแล้ว', 'error')
            return redirect(url_for('manage_admins'))

        auto_officer_code = generate_next_officer_code()
        hashed_password = generate_password_hash(auto_officer_code)

        new_officer = User(
            prefix=prefix,
            username=username_input,
            id_card=username_input,
            password=hashed_password,
            fullname=fullname,
            email=email,
            phone=phone,
            address=address,
            role='admin',
            member_id=auto_officer_code
        )

        try:
            db.session.add(new_officer)
            db.session.commit()
            flash(f'เพิ่มเจ้าหน้าที่สำเร็จ! Username (เลขบัตร): {username_input} | รหัสพนักงาน/รหัสผ่านเริ่มต้น: {auto_officer_code}', 'success')
        except Exception:
            db.session.rollback()
            flash('เกิดข้อผิดพลาดในการบันทึกข้อมูล', 'error')

        return redirect(url_for('manage_admins'))

    next_auto_password = generate_next_officer_code()
    officers = User.query.filter(User.role.in_(['admin', 'superadmin'])).order_by(User.id.asc()).all()

    officers_rows = ""
    for idx, off in enumerate(officers, start=1):
        pfx = f"{off.prefix} " if getattr(off, 'prefix', None) else ""
        officers_rows += f"""
        <tr class="hover:bg-slate-50 transition border-b border-slate-100 text-xs">
            <td class="py-3 px-4 font-mono font-bold text-slate-400">{idx}</td>
            <td class="py-3 px-4 font-mono font-black text-indigo-600 bg-indigo-50/50 rounded-xl">{escape(off.member_id or off.username)}</td>
            <td class="py-3 px-4 font-bold text-slate-800">{escape(pfx)}{escape(off.fullname)}</td>
            <td class="py-3 px-4 font-mono text-slate-500">{escape(off.username)}</td>
            <td class="py-3 px-4 text-slate-500">{escape(off.phone or '-')}</td>
            <td class="py-3 px-4 text-slate-500 max-w-xs truncate">{escape(getattr(off, 'address', '-') or '-')}</td>
            <td class="py-3 px-4"><span class="bg-slate-100 text-slate-700 text-[10px] font-extrabold px-2.5 py-1 rounded-full uppercase">{escape(off.role)}</span></td>
        </tr>
        """

    content = f"""
    <div class="max-w-6xl mx-auto space-y-8">
        <div class="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-8 text-white shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <span class="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs px-3 py-1 rounded-full font-black uppercase">Admin Management</span>
                <h1 class="text-2xl font-black mt-2">จัดการข้อมูลเจ้าหน้าที่ & สิทธิ์การใช้งาน</h1>
                <p class="text-xs text-slate-300 mt-1">กรอกข้อมูลเจ้าหน้าที่ พร้อมระบุคำนำหน้าชื่อ และที่อยู่</p>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div class="lg:col-span-5 bg-white p-6 sm:p-8 rounded-3xl border border-slate-100 shadow-sm space-y-5">
                <div class="flex items-center gap-3 border-b border-slate-100 pb-4">
                    <div class="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center font-black text-lg">
                        <i class="fa-solid fa-user-plus"></i>
                    </div>
                    <div>
                        <h3 class="text-base font-black text-slate-800">ลงทะเบียนเจ้าหน้าที่ใหม่</h3>
                        <p class="text-xs font-bold text-slate-400">กรอกข้อมูลส่วนตัว + รหัสพนักงานเจนออโต้</p>
                    </div>
                </div>

                <form method="POST" class="space-y-4">
                    <div class="grid grid-cols-3 gap-3">
                        <div>
                            <label class="block text-xs font-black uppercase text-slate-400 mb-1">คำนำหน้า <span class="text-rose-500">*</span></label>
                            <select name="prefix" required class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500 font-bold">
                                <option value="นาย">นาย</option>
                                <option value="นาง">นาง</option>
                                <option value="นางสาว">นางสาว</option>
                            </select>
                        </div>
                        <div class="col-span-2">
                            <label class="block text-xs font-black uppercase text-slate-400 mb-1">ชื่อ-นามสกุล <span class="text-rose-500">*</span></label>
                            <input type="text" name="fullname" required placeholder="สมชาย ใจดี" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500">
                        </div>
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-400 mb-1">เลขบัตรประชาชน (Username) <span class="text-rose-500">*</span></label>
                        <input type="text" name="username" required placeholder="กรอกเลขบัตรประชาชน 13 หลัก" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500 font-mono font-bold">
                        <p class="text-[10px] text-slate-400 mt-1">* ใช้สำหรับเข้าสู่ระบบในช่อง Username / เลขบัตรประชาชน</p>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-black uppercase text-slate-400 mb-1">อีเมล</label>
                            <input type="email" name="email" placeholder="officer@rmutto.ac.th" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500">
                        </div>
                        <div>
                            <label class="block text-xs font-black uppercase text-slate-400 mb-1">เบอร์โทรศัพท์</label>
                            <input type="text" name="phone" placeholder="0812345678" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500">
                        </div>
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-400 mb-1">ที่อยู่ปัจจุบัน</label>
                        <textarea name="address" rows="2" placeholder="กรอกที่อยู่ปัจจุบัน" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-indigo-500 resize-none"></textarea>
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-400 mb-1">รหัสพนักงาน / รหัสผ่านออโต้</label>
                        <input type="text" value="{escape(next_auto_password)}" disabled class="w-full border border-indigo-100 bg-indigo-50/50 text-indigo-700 font-mono font-black rounded-2xl p-3.5 text-sm cursor-not-allowed">
                        <p class="text-[10px] text-slate-400 mt-1">* รหัสจะถูกบันทึกลงคอลัมน์ member_id และใช้เป็นรหัสผ่านเริ่มต้นในการล็อกอิน</p>
                    </div>

                    <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold py-4 rounded-2xl shadow-lg transition text-xs flex items-center justify-center gap-2">
                        <i class="fa-solid fa-save"></i> บันทึกข้อมูลเจ้าหน้าที่
                    </button>
                </form>
            </div>

            <div class="lg:col-span-7 bg-white p-6 sm:p-8 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                <div class="flex justify-between items-center border-b border-slate-100 pb-4">
                    <div>
                        <h3 class="text-base font-black text-slate-800">รายชื่อเจ้าหน้าที่ในระบบ</h3>
                        <p class="text-xs text-slate-400">รวมทั้งหมด {len(officers)} ท่าน</p>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left">
                        <thead class="bg-slate-50 text-[11px] font-black text-slate-400 uppercase tracking-wider">
                            <tr>
                                <th class="py-3 px-4">#</th>
                                <th class="py-3 px-4">รหัสพนักงาน</th>
                                <th class="py-3 px-4">ชื่อ-นามสกุล</th>
                                <th class="py-3 px-4">เลขบัตรประชาชน</th>
                                <th class="py-3 px-4">เบอร์โทร</th>
                                <th class="py-3 px-4">ที่อยู่</th>
                                <th class="py-3 px-4">สิทธิ์</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">{officers_rows}</tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    """
    return render_layout(content, active_page='manage_admins')

@app.route('/admin/manage_admin_detail/<int:admin_id>', methods=['GET', 'POST'])
def manage_admin_detail(admin_id):
    if session.get('role') != 'superadmin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
        return redirect(url_for('home'))
    
    target_admin = User.query.get_or_404(admin_id)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update':
            target_admin.fullname = request.form.get('fullname')
            target_admin.phone = request.form.get('phone')
            target_admin.email = request.form.get('email')
            target_admin.role = request.form.get('role')
            db.session.commit()
            flash('อัปเดตข้อมูลเจ้าหน้าที่เรียบร้อยแล้ว', 'success')
            return redirect(url_for('manage_admins'))
        elif action == 'delete':
            if target_admin.id == session['user_id']:
                flash('ไม่สามารถลบบัญชีตัวเองได้', 'error')
            else:
                db.session.delete(target_admin)
                db.session.commit()
                flash('ลบบัญชีเจ้าหน้าที่เรียบร้อยแล้ว', 'success')
                return redirect(url_for('manage_admins'))

    content = f"""
    <div class="max-w-xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <div class="flex justify-between items-center mb-6">
            <h3 class="text-xl font-black text-slate-900">รายละเอียดเจ้าหน้าที่: {escape(target_admin.fullname)}</h3>
            <a href="/admin/manage_admins" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ย้อนกลับ</a>
        </div>
        <form method="POST" class="space-y-4">
            <div><label class="block text-xs font-bold text-slate-700 mb-1">ชื่อ-นามสกุล</label><input type="text" name="fullname" value="{escape(target_admin.fullname)}" required class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
            <div><label class="block text-xs font-bold text-slate-700 mb-1">เบอร์โทรศัพท์</label><input type="text" name="phone" value="{escape(target_admin.phone or '')}" class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
            <div><label class="block text-xs font-bold text-slate-700 mb-1">อีเมล</label><input type="email" name="email" value="{escape(target_admin.email or '')}" class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
            <div><label class="block text-xs font-bold text-slate-700 mb-1">ระดับสิทธิ์</label><select name="role" class="w-full border rounded-xl p-3 text-sm bg-sky-50"><option value="admin" {'selected' if target_admin.role=='admin' else ''}>เจ้าหน้าที่ทั่วไป</option><option value="superadmin" {'selected' if target_admin.role=='superadmin' else ''}>ผู้ดูแลหลัก (Super Admin)</option></select></div>
            <div class="flex gap-3 pt-4">
                <button type="submit" name="action" value="update" class="flex-grow bg-sky-600 hover:bg-sky-700 text-white font-bold py-3 rounded-xl text-sm">บันทึกการแก้ไข</button>
                <button type="submit" name="action" value="delete" onclick="return confirm('ยืนยันการลบบัญชีนี้?')" class="bg-rose-100 hover:bg-rose-600 hover:text-white text-rose-700 font-bold px-6 py-3 rounded-xl text-sm transition">ลบบัญชี</button>
            </div>
        </form>
    </div>
    """
    return render_layout(content, active_page='manage_admins')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        prefix = request.form.get('prefix', 'นาย')
        fullname = request.form.get('fullname', '').strip()
        id_card = request.form.get('id_card', '').strip()
        dob = request.form.get('dob', '')
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_address = format_address(request.form.get('house_no'), request.form.get('moo'), request.form.get('soi'), request.form.get('subdistrict'), request.form.get('district'), request.form.get('province'), request.form.get('postal_code'))

        if User.query.filter_by(id_card=id_card).first():
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนแล้ว', 'error')
            return redirect(url_for('register'))

        new_member_id = generate_member_id()
        new_user = User(
            member_id=new_member_id, prefix=prefix, fullname=fullname, id_card=id_card, dob=dob, phone=phone, email=email, address=full_address, id_card_img="default_id_card.png", username=username, password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f'สมัครสมาชิกเรียบร้อย! รหัสนักศึกษาของคุณคือ: {new_member_id}', 'success')
        return redirect(url_for('login'))

    content = """
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h2 class="text-2xl font-black text-slate-900 text-center mb-8">ลงทะเบียนนักศึกษาสาขาวิชาระบบสารสนเทศ</h2>
        <form method="POST" class="space-y-5">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">คำนำหน้า</label><select name="prefix" class="w-full border rounded-2xl p-3 text-sm bg-sky-50"><option value="นาย">นาย</option><option value="นาง">นาง</option><option value="นางสาว">นางสาว</option></select></div>
                <div class="md:col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">ชื่อ-นามสกุล *</label><input type="text" name="fullname" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">เลขบัตรประชาชน (13 หลัก) *</label><input type="text" name="id_card" maxlength="13" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">วันเกิด *</label><input type="date" name="dob" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">เบอร์โทร *</label><input type="tel" name="phone" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">อีเมล *</label><input type="email" name="email" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
            </div>
            <div class="border-t pt-4">
                <label class="block text-xs font-bold text-sky-700 uppercase mb-3">ที่อยู่</label>
                <div class="grid grid-cols-3 gap-3 mb-3">
                    <div><input type="text" name="house_no" placeholder="บ้านเลขที่" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                    <div><input type="text" name="moo" placeholder="หมู่" class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                    <div><input type="text" name="soi" placeholder="ซอย/ถนน" class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                </div>
                <div class="grid grid-cols-4 gap-3">
                    <div><input type="text" name="subdistrict" placeholder="ตำบล" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                    <div><input type="text" name="district" placeholder="อำเภอ" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                    <div><input type="text" name="province" placeholder="จังหวัด" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                    <div><input type="text" name="postal_code" placeholder="รหัสไปรษณีย์" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                </div>
            </div>
            <div class="grid grid-cols-2 gap-3 border-t pt-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">Username *</label><input type="text" name="username" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">Password *</label><input type="password" name="password" required class="w-full border rounded-2xl p-3 text-sm bg-sky-50"></div>
            </div>
            <button type="submit" class="w-full bg-sky-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-4">ยืนยันการลงทะเบียน</button>
        </form>
    </div>
    """
    return render_layout(content, active_page='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('username', '').strip()
        password_input = request.form.get('password', '').strip()
        user = User.query.filter((User.username == login_input) | (User.id_card == login_input)).first()
        if user and check_password_hash(user.password, password_input):
            session['user_id'] = user.id
            session['fullname'] = user.fullname
            session['role'] = user.role
            session['member_id'] = user.member_id
            if  user.username == 'Admin-999':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('home'))
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')

    role_param = request.args.get('role', 'student')
    is_admin_mode = role_param in ['admin', 'officer']

    content = f"""
    <div class="max-w-md mx-auto my-8 bg-white p-8 sm:p-10 rounded-[2.5rem] shadow-2xl text-center border border-sky-100 relative overflow-hidden">
        <div class="w-16 h-16 {'bg-indigo-100 text-indigo-600' if is_admin_mode else 'bg-sky-100 text-sky-600'} rounded-2xl flex items-center justify-center text-2xl mx-auto mb-4 font-black">
            <i class="fa-solid {'fa-shield-halved' if is_admin_mode else 'fa-graduation-cap'}"></i>
        </div>

        <h2 class="text-2xl font-black text-slate-900 mb-1">{'เข้าสู่ระบบเจ้าหน้าที่' if is_admin_mode else 'เข้าสู่ระบบนักศึกษา'}</h2>
        <p class="text-xs text-slate-400 font-medium mb-6">ระบบธนาคารหน่วยกิต (Credit Bank) IS RMUTTO</p>

        <form method="POST" class="space-y-4 text-left">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">Username / เลขบัตรประชาชน</label>
                <input type="text" name="username" required placeholder="กรอกชื่อผู้ใช้ หรือ เลขบัตรประชาชน" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-sky-400">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">รหัสผ่าน</label>
                <input type="password" name="password" required placeholder="••••••••" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm bg-slate-50 outline-none focus:border-sky-400">
            </div>
            <button type="submit" class="w-full {'bg-indigo-600 hover:bg-indigo-700' if is_admin_mode else 'bg-sky-600 hover:bg-sky-700'} text-white font-extrabold py-4 rounded-2xl shadow-lg hover:shadow-xl transition-all duration-300 text-sm mt-4">
                เข้าสู่ระบบ
            </button>
        </form>

        <div class="mt-6 pt-6 border-t border-slate-100 flex justify-between items-center text-xs font-bold">
            <a href="/login?role={'student' if is_admin_mode else 'admin'}" class="text-slate-500 hover:text-slate-800">
                สลับเป็น{'สิทธิ์นักศึกษา' if is_admin_mode else 'สิทธิ์เจ้าหน้าที่'}
            </a>
            <a href="/register" class="text-sky-600 hover:underline">
                ลงทะเบียนนักศึกษาใหม่
            </a>
        </div>
    </div>
    """
    return render_layout(content, active_page='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/secret_clear_all_requests', methods=['POST'])
def secret_clear_all_requests():
    if session.get('role') != 'superadmin': 
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้", 403
        
    try:
        deleted_count = db.session.query(CreditRequest).delete()
        db.session.commit()
        flash(f'ลบข้อมูลคำร้องบนระบบออนไลน์สำเร็จทั้งหมด {deleted_count} รายการ!', 'success')
        return redirect(url_for('admin_requests'))
    except Exception as e:
        db.session.rollback()
        return f"เกิดข้อผิดพลาด: {escape(str(e))}"

@app.route('/admin/export_csv')
def admin_export_csv():
    if session.get('role') not in ['admin', 'superadmin']:
        return redirect(url_for('login'))
        
    selected_month = request.args.get('month', '').strip() # e.g. "2026-10"
    
    query = CreditRequest.query
    if selected_month:
        query = query.filter(CreditRequest.date_submitted.like(f"{selected_month}%"))
        
    requests = query.order_by(CreditRequest.id.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['รหัสคำร้อง', 'รหัสนักศึกษา', 'ชื่อ-นามสกุล', 'วิชาที่ขอเทียบโอน', 'หน่วยกิต', 'วันที่ยื่น', 'สถานะ', 'ผู้อนุมัติ'])
    
    status_map = {
        'Pending': 'รอดำเนินการ',
        'Approved': 'อนุมัติแล้ว',
        'Needs_Revision': 'ส่งกลับให้แก้ไข',
        'Need_Edit': 'ส่งกลับให้แก้ไข',
        'Rejected': 'ปฏิเสธ'
    }

    for r in requests:
        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'
        st_text = status_map.get(r.status, 'รอดำเนินการ')
        
        writer.writerow([
            getattr(r, 'req_code', f'TR{r.id:04d}'),
            student_code,
            student_name,
            getattr(r, 'course_name', '-'),
            getattr(r, 'credits', 0),
            getattr(r, 'date_submitted', '-'),
            st_text,
            getattr(r, 'approved_by', '-') or '-'
        ])
    
    csv_data = "\ufeff" + output.getvalue()
    filename_str = f"Credit_Bank_Report_{selected_month if selected_month else 'All'}.csv"
    
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename={filename_str}"}
    )

# =========================================================
# ROUTE สำหรับระบบเจ้าหน้าที่ (ADMIN CONTROLLERS)
# =========================================================
@app.route('/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    # ตรวจสอบ Username และ Password ตามที่กำหนด
    if username == 'Admin-999' and password == '16092547':
        session['admin_logged_in'] = True
        session['fullname'] = 'เจ้าหน้าที่ (Admin-999)'
        return redirect(url_for('admin_panel'))
    else:
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'error')
        return redirect(url_for('admin_panel'))
    
# =========================================================
# 1. หน้าแผงควบคุมรายวิชา
# =========================================================
@app.route('/admin_panel')
def admin_panel():
    try:
        courses = Course.query.order_by(Course.id.desc()).all()
    except Exception:
        courses = []
    return render_template('admin.html', courses=courses)

# =========================================================
# 2. เพิ่มรายวิชาใหม่ (Add)
# =========================================================
@app.route('/admin/course/add', methods=['POST'])
def admin_add_course():
    try:
        code = request.form.get('course_code', '').strip().upper()
        name = request.form.get('course_name', '').strip()
        credits = int(request.form.get('credits', 3))
        category = request.form.get('category', 'หมวดวิชาศึกษาทั่วไป')
        institution = request.form.get('institution', 'ThaiMOOC')
        hours = int(request.form.get('hours', 45))
        description = request.form.get('description', '').strip()

        if code and name:
            new_course = Course(
                course_code=code,
                course_name=name,
                credits=credits,
                category=category,
                institution=institution,
                hours=hours,
                description=description
            )
            db.session.add(new_course)
            db.session.commit()
    except Exception:
        db.session.rollback()

    return redirect(url_for('admin_panel'))

# =========================================================
# 3. แก้ไขรายวิชา (Edit)
# =========================================================
@app.route('/admin/course/edit', methods=['POST'])
def admin_edit_course():
    try:
        course_id = request.form.get('course_id')
        code = request.form.get('course_code', '').strip().upper()
        name = request.form.get('course_name', '').strip()
        credits = int(request.form.get('credits', 3))
        category = request.form.get('category', 'หมวดวิชาศึกษาทั่วไป')
        institution = request.form.get('institution', 'ThaiMOOC')
        hours = int(request.form.get('hours', 45))
        description = request.form.get('description', '').strip()

        course = Course.query.get(course_id)
        if course:
            if hasattr(course, 'course_code'): course.course_code = code
            if hasattr(course, 'code'): course.code = code
            if hasattr(course, 'course_name'): course.course_name = name
            if hasattr(course, 'name'): course.name = name
            
            course.credits = credits
            course.category = category
            if hasattr(course, 'institution'): course.institution = institution
            if hasattr(course, 'hours'): course.hours = hours
            if hasattr(course, 'description'): course.description = description

            db.session.commit()
    except Exception:
        db.session.rollback()

    return redirect(url_for('admin_panel'))

# =========================================================
# 4. ลบรายวิชา (Delete)
# =========================================================
@app.route('/admin/course/delete', methods=['POST'])
def admin_delete_course():
    try:
        course_id = request.form.get('course_id')
        if course_id:
            course = Course.query.get(course_id)
            if not course:
                course = Course.query.filter_by(course_code=course_id).first()
            if not course and hasattr(Course, 'code'):
                course = Course.query.filter_by(code=course_id).first()

            if course:
                db.session.delete(course)
                db.session.commit()
    except Exception:
        db.session.rollback()

    return redirect(url_for('admin_panel'))

@app.route('/admin/request/action', methods=['POST'])
def admin_handle_request():
    """อนุมัติ หรือ ปฏิเสธคำร้องเทียบโอน"""
    req_id = request.form.get('req_id')
    action = request.form.get('action')
    
    if 'CreditRequest' in globals() and req_id:
        req_item = CreditRequest.query.get(req_id)
        if req_item:
            if action == 'approve':
                req_item.status = 'Approved'
            elif action == 'reject':
                req_item.status = 'Rejected'
            db.session.commit()
            
    return redirect(url_for('admin_panel'))


if __name__ == '__main__':
    app.run(debug=True)