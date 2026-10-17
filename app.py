import os
import json
import uuid
import csv
import io
import urllib.request
import re
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'credit_bank_is_rmutto_production_key_2026'

db_url = os.environ.get('DATABASE_URL')
if db_url:
    # บังคับให้เชื่อมต่อฐานข้อมูลด้วย psycopg2
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///credit_bank.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)

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
    address = db.Column(db.Text, nullable=True)
    id_card_img = db.Column(db.String(200), nullable=True)
    profile_img = db.Column(db.String(200), default="default_profile.png")
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')

class CreditRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    req_code = db.Column(db.String(20), default="TR2569001")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="ThaiMOOC")
    faculty = db.Column(db.String(100), default="คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ")
    major = db.Column(db.String(100), default="สาขาวิชาระบบสารสนเทศ")
    date_submitted = db.Column(db.String(20), default="2026-08-26")
    doc_img = db.Column(db.String(200), nullable=True)
    doc_img2 = db.Column(db.String(200), nullable=True)
    doc_img3 = db.Column(db.String(200), nullable=True)
    evidence_data = db.Column(db.Text, nullable=True) # เก็บไว้กัน error เวลาอ่านฐานข้อมูลเก่า
    status = db.Column(db.String(20), default='Pending') 
    reject_reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    user = db.relationship('User', backref=db.backref('credits_list', lazy=True))

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS doc_img TEXT;"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS doc_img2 TEXT;"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS doc_img3 TEXT;"))
            conn.commit()
    except Exception:
        pass

    try:
        main_admin = User.query.filter((User.username == 'Admin_rmutto') | (User.username == 'admin')).first()
        if not main_admin:
            main_admin = User(
                member_id='ADM001', prefix='นาย', fullname='ผู้ดูแลระบบหลัก (Super Admin)', 
                id_card='0000000000000', username='Admin_rmutto', password=generate_password_hash('rmutto2026'), 
                role='superadmin', phone="081-000-0000", email="admin@rmutto.ac.th"
            )
            db.session.add(main_admin)
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
                except: credits_val = 3
                courses_dict[current_code] = {"code": current_code, "name": name, "group": group, "provider": provider if provider else "ThaiMOOC", "credits": credits_val, "mooc_list": [], "hours_list": [], "total_num_hours": 0.0}
            else:
                if not courses_dict[current_code]["name"] and name: courses_dict[current_code]["name"] = name
                if not courses_dict[current_code]["group"] and group: courses_dict[current_code]["group"] = group
                if not courses_dict[current_code]["provider"] and provider: courses_dict[current_code]["provider"] = provider

            if mooc_name or hours_raw:
                nums = re.findall(r'\d+(?:\.\d+)?', hours_raw)
                if nums: courses_dict[current_code]["total_num_hours"] += float(nums[0])
                
                clean_mooc = mooc_name
                for n in nums:
                    clean_mooc = clean_mooc.replace(f"({n} ชม.)", "").replace(f"({n} ชั่วโมง)", "").replace(n, "").strip()
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
    flash_html = "".join([f'<div class="p-4 mb-4 text-sm rounded-2xl font-semibold shadow-sm flex items-center justify-between border transition-all {"bg-rose-50 text-rose-700 border-rose-200" if category in ["error", "danger"] else "bg-emerald-50 text-emerald-800 border-emerald-200"}"><div class="flex items-center gap-2"><i class="fa-solid {"fa-circle-exclamation text-rose-500" if category in ["error", "danger"] else "fa-circle-check text-emerald-500"} text-lg"></i><span>{message}</span></div><button onclick="this.parentElement.remove()" class="text-xs font-bold px-2 py-1 hover:bg-black/5 rounded-lg">✕</button></div>' for category, message in messages]) if messages else ""

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
                    <div class="flex flex-col min-w-0 nav-text"><span class="text-xs font-bold text-slate-800 truncate">{session.get('fullname', 'ผู้ใช้งาน')}</span><span class="text-[10px] text-sky-700 capitalize font-medium">{'เจ้าหน้าที่' if session.get('role') in ['admin', 'superadmin'] else 'นักศึกษา'}</span></div>
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
    # -------------------------------------------------------------
    # 🌟 กรณีที่ยังไม่ได้เข้าสู่ระบบ: แสดงหน้า Landing Page ต้อนรับสุดพรีเมียม
    # -------------------------------------------------------------
    if not session.get('user_id'):
        landing_content = """
        <div class="max-w-6xl mx-auto space-y-16 py-4">
            <!-- 🚀 Hero Banner Section -->
            <div class="relative overflow-hidden bg-gradient-to-br from-slate-900 via-sky-950 to-indigo-950 rounded-[2.5rem] p-8 sm:p-12 text-white shadow-2xl border border-sky-500/20">
                <!-- Ambient Glow Background Effects -->
                <div class="absolute -top-24 -left-24 w-96 h-96 bg-sky-500/20 rounded-full blur-3xl pointer-events-none"></div>
                <div class="absolute -bottom-24 -right-24 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none"></div>

                <div class="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                    <div class="lg:col-span-7 space-y-6">
                        <div class="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md border border-white/20 text-sky-200 text-xs px-4 py-1.5 rounded-full font-extrabold uppercase tracking-wider">
                            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            ระบบธนาคารหน่วยกิตดิจิทัล (Credit Bank System)
                        </div>
                        <h1 class="text-3xl sm:text-5xl font-black leading-tight tracking-tight">
                            สะสมหน่วยกิตง่ายๆ <br>
                            <span class="bg-gradient-to-r from-sky-300 via-indigo-200 to-emerald-300 bg-clip-text text-transparent">เชื่อมโลกการเรียนรู้สู่อนาคต</span>
                        </h1>
                        <p class="text-slate-300 text-sm sm:text-base leading-relaxed font-medium">
                            สาขาวิชาระบบสารสนเทศ มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก (RMUTTO) <br>
                            ระบบเทียบโอนคอร์สเรียนออนไลน์ ThaiMOOC & ChulaMOOC สะดวก รวดเร็ว โปร่งใส ตรวจสอบได้ตลอด 24 ชั่วโมง
                        </p>

                        <div class="pt-2 flex flex-wrap gap-3">
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

                    <!-- Hero Visual Card -->
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

            <!-- 🎯 Portal Selector Section (แบ่งแยก 2 ฝั่งชัดเจน) -->
            <div class="space-y-6">
                <div class="text-center max-w-2xl mx-auto space-y-2">
                    <h2 class="text-2xl sm:text-3xl font-black text-slate-900">เลือกช่องทางเข้าใช้งานระบบ</h2>
                    <p class="text-slate-500 text-xs sm:text-sm font-medium">ออกแบบเพื่อการใช้งานที่สะดวก รวดเร็ว เหมาะสมสำหรับทั้งนักศึกษาและเจ้าหน้าที่</p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <!-- 🎓 ฝั่งนักศึกษา -->
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

                    <!-- 🛡️ ฝั่งเจ้าหน้าที่ -->
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

            <!-- 🔄 How It Works Section (ขั้นตอนง่ายๆ 4 สเต็ป) -->
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

        <!-- 🔓 Pop-up Modal สลับเข้าสู่ระบบด่วน (Quick Login Modal) -->
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

                <!-- Tab สลับสิทธิ์ -->
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

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    # =============================================================
    # 1. ฝั่งเจ้าหน้าที่ (Officer / Admin Dashboard)
    # =============================================================
    if user.role in ['admin', 'superadmin']:
        try:
            pending_reqs = CreditRequest.query.filter_by(status='Pending').order_by(CreditRequest.id.asc()).all()
            pending_count = len(pending_reqs)
            
            students = User.query.filter_by(role='student').order_by(User.id.desc()).all()
            total_students = len(students)
            
            approved_reqs = CreditRequest.query.filter_by(status='Approved').order_by(CreditRequest.id.desc()).all()
            approved_count = len(approved_reqs)
            
            revision_count = CreditRequest.query.filter_by(status='Needs_Revision').count()
            total_approved_credits = sum(r.credits for r in approved_reqs)
        except Exception:
            pending_reqs, pending_count, students, total_students, approved_reqs, approved_count, revision_count, total_approved_credits = [], 0, [], 0, [], 0, 0, 0

        pending_list = [{
            'id': r.id,
            'req_code': getattr(r, 'req_code', 'TR001'),
            'student_name': r.user.fullname if getattr(r, 'user', None) else '-',
            'student_code': r.user.member_id if getattr(r, 'user', None) else '-',
            'course_name': getattr(r, 'course_name', '-'),
            'credits': getattr(r, 'credits', 0),
            'date': getattr(r, 'date_submitted', '-')
        } for r in pending_reqs]

        students_list = []
        for s in students:
            app_credits = sum(r.credits for r in CreditRequest.query.filter_by(user_id=s.id, status='Approved').all())
            students_list.append({
                'member_id': s.member_id or '-',
                'fullname': s.fullname,
                'phone': s.phone or '-',
                'email': s.email or '-',
                'credits': app_credits
            })

        approved_list = [{
            'req_code': getattr(r, 'req_code', 'TR001'),
            'student_name': r.user.fullname if getattr(r, 'user', None) else '-',
            'course_name': getattr(r, 'course_name', '-'),
            'credits': getattr(r, 'credits', 0),
            'approved_by': getattr(r, 'approved_by', 'เจ้าหน้าที่') or 'เจ้าหน้าที่',
            'date': getattr(r, 'date_submitted', '-')
        } for r in approved_reqs]

        from collections import defaultdict
        course_map = defaultdict(lambda: {'count': 0, 'total_credits': 0, 'unit_credits': 0})
        for r in approved_reqs:
            c_name = r.course_name
            course_map[c_name]['count'] += 1
            course_map[c_name]['total_credits'] += r.credits
            course_map[c_name]['unit_credits'] = r.credits

        credits_summary_list = [{
            'course_name': name,
            'unit_credits': data['unit_credits'],
            'approved_count': data['count'],
            'total_credits': data['total_credits']
        } for name, data in course_map.items()]

        admin_summary_json = json.dumps({
            'pending': pending_list,
            'students': students_list,
            'approved': approved_list,
            'credits': credits_summary_list
        }, ensure_ascii=False)

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
                        <h1 class="text-3xl font-black">ยินดีต้อนรับ, {user.fullname} 👋</h1>
                        <p class="text-slate-300 text-sm mt-1">ระบบบริหารจัดการธนาคารหน่วยกิต (Credit Bank) สาขาวิชาระบบสารสนเทศ</p>
                    </div>
                    <div class="flex flex-wrap gap-2 shrink-0">
                        <a href="/admin/export_csv" class="bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold px-5 py-3 rounded-2xl shadow-lg transition text-xs flex items-center gap-2">
                            <i class="fa-solid fa-file-excel"></i> ออกรายงานประจำเดือน (CSV)
                        </a>
                        <a href="/admin/requests" class="bg-sky-500 hover:bg-sky-600 text-white font-extrabold px-5 py-3 rounded-2xl shadow-lg transition text-xs flex items-center gap-2">
                            <i class="fa-solid fa-file-signature"></i> ตรวจสอบคำร้องทั้งหมด ({pending_count})
                        </a>
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
                    <p class="text-xs text-slate-400 mb-6">จำแนกตามขั้นตอนการพิจารณา</p>
                    <div class="h-60 relative">
                        <canvas id="adminStatusChart"></canvas>
                    </div>
                </div>

                <div class="lg:col-span-2 bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                    <div class="flex justify-between items-center border-b border-slate-100 pb-4">
                        <div>
                            <h3 class="text-lg font-black text-slate-800">คำร้องเร่งด่วนที่รอตรวจสอบ</h3>
                            <p class="text-xs text-slate-400">สามารถกดดูด่วนเพื่อตรวจสอบหลักฐานได้ทันที</p>
                        </div>
                        <a href="/admin/requests" class="text-xs font-bold text-sky-600 hover:text-sky-800 transition">ดูทั้งหมด ({pending_count}) <i class="fa-solid fa-arrow-right"></i></a>
                    </div>

                    <div class="overflow-x-auto">
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
                        <td class="py-3 px-3 text-slate-500 font-medium">${item.approved_by}</td>
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

        function renderAdminPendingTable() {
            const tbody = document.getElementById('admin_pending_tbody');
            if(!tbody) return;
            tbody.innerHTML = '';

            if (summaryData.pending.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-xs font-bold text-slate-400"><i class="fa-solid fa-circle-check text-2xl mb-2 text-emerald-400 block"></i>ไม่มีคำร้องรอดำเนินการในขณะนี้</td></tr>`;
                return;
            }

            summaryData.pending.slice(0, 5).forEach(item => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-slate-50 transition';
                tr.innerHTML = `
                    <td class="px-4 py-3.5">
                        <p class="font-bold text-slate-800 text-xs">${item.student_name}</p>
                        <p class="text-[10px] text-slate-400 font-mono">${item.student_code}</p>
                    </td>
                    <td class="px-4 py-3.5 font-bold text-slate-700 text-xs">${item.course_name}</td>
                    <td class="px-4 py-3.5 text-center font-black text-sky-600 text-xs">${item.credits}</td>
                    <td class="px-4 py-3.5 text-right">
                        <a href="/admin/review/${item.id}" class="bg-amber-50 hover:bg-amber-100 text-amber-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1 border border-amber-200">
                            <i class="fa-solid fa-pen-to-square"></i> ตรวจ
                        </a>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        document.addEventListener("DOMContentLoaded", function() {
            renderAdminPendingTable();

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
                        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
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

    # =============================================================
    # 2. ฝั่งนักศึกษา (Student Dashboard)
    # =============================================================
    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).order_by(CreditRequest.id.desc()).all()
    except Exception:
        user_requests = []

    pending_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Pending')
    approved_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Approved')
    revision_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Needs_Revision')
    need_edit_count = revision_count

    approved_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') == 'Approved')
    target_credits = 120
    credit_percent = min(100, round((approved_credits / target_credits) * 100, 1))

    req_list_json = []
    for r in user_requests:
        req_list_json.append({
            'id': r.id,
            'req_code': getattr(r, 'req_code', '-'),
            'course_name': getattr(r, 'course_name', '-'),
            'credits': getattr(r, 'credits', 0),
            'status': getattr(r, 'status', 'Pending'),
            'reject_reason': getattr(r, 'reject_reason', '-') or '-',
            'doc_img': getattr(r, 'doc_img', None),
            'doc_img2': getattr(r, 'doc_img2', None),
            'doc_img3': getattr(r, 'doc_img3', None),
            'date_submitted': getattr(r, 'date_submitted', '-')
        })
    req_json_str = json.dumps(req_list_json, ensure_ascii=False)

    html_part = f"""
    <div class="max-w-6xl mx-auto space-y-8">
        <div class="relative overflow-hidden bg-gradient-to-r from-sky-600 via-indigo-600 to-slate-900 rounded-3xl p-8 text-white shadow-xl">
            <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                    <span class="bg-white/20 backdrop-blur-md text-sky-100 text-xs px-3 py-1 rounded-full font-bold uppercase tracking-wider">Student Portal</span>
                    <h1 class="text-3xl font-black mt-2">ยินดีต้อนรับ, {user.prefix or ''}{user.fullname} 👋</h1>
                    <p class="text-sky-100/80 text-sm mt-1">รหัสนักศึกษา: {user.member_id or '-'} | ระบบธนาคารหน่วยกิต (Credit Bank) IS RMUTTO</p>
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

                <div onclick="filterByStatus('Need_Edit')" class="cursor-pointer group bg-white hover:bg-indigo-50/50 p-6 rounded-3xl border border-indigo-100 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-300">
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
                <h3 class="text-base font-black text-slate-800 mb-2 w-full text-left">สัดส่วนสถานะคำร้อง</h3>
                <p class="text-xs text-slate-400 mb-6 w-full text-left">สามารถคลิกชิ้นส่วนกราฟเพื่อกรองตารางได้</p>
                <div class="w-48 h-48 relative">
                    <canvas id="studentChart"></canvas>
                </div>
            </div>

            <div class="lg:col-span-2 bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-100 pb-4">
                    <div>
                        <h3 class="text-lg font-black text-slate-800">รายการคำร้องเทียบโอน</h3>
                        <p class="text-xs text-slate-400" id="filter_status_label">แสดงคำร้องทั้งหมด</p>
                    </div>

                    <div class="flex flex-wrap gap-1.5 bg-slate-100 p-1 rounded-2xl text-xs font-bold">
                        <button onclick="filterByStatus('ALL')" id="btn-tab-ALL" class="tab-btn px-3 py-1.5 rounded-xl bg-slate-900 text-white shadow-sm">ทั้งหมด</button>
                        <button onclick="filterByStatus('Pending')" id="btn-tab-Pending" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">รอดำเนินการ</button>
                        <button onclick="filterByStatus('Approved')" id="btn-tab-Approved" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">อนุมัติแล้ว</button>
                        <button onclick="filterByStatus('Need_Edit')" id="btn-tab-Need_Edit" class="tab-btn px-3 py-1.5 rounded-xl text-slate-500 hover:text-slate-800">ต้องแก้ไข</button>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-sm text-left">
                        <thead class="text-xs text-slate-400 font-extrabold uppercase bg-slate-50 rounded-xl">
                            <tr>
                                <th class="px-4 py-3 rounded-l-xl">ชื่อวิชาที่ขอเทียบโอน</th>
                                <th class="px-4 py-3 text-center">หน่วยกิต</th>
                                <th class="px-4 py-3 text-center">สถานะ</th>
                                <th class="px-4 py-3 text-right rounded-r-xl">จัดการ</th>
                            </tr>
                        </thead>
                        <tbody id="requests_tbody" class="divide-y divide-slate-100">
                        </tbody>
                    </table>
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
    const requestsData = __REQUESTS_JSON__;
    let currentFilter = 'ALL';

    function renderTable() {
        const tbody = document.getElementById('requests_tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const filtered = requestsData.filter(r => {
            if (currentFilter === 'ALL') return true;
            if (currentFilter === 'Pending') return r.status === 'Pending';
            if (currentFilter === 'Approved') return r.status === 'Approved';
            if (currentFilter === 'Need_Edit') return r.status !== 'Pending' && r.status !== 'Approved';
            return true;
        });

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-xs font-bold text-slate-400"><i class="fa-solid fa-folder-open text-2xl mb-2 block"></i>ไม่พบรายการคำร้องในหมวดนี้</td></tr>`;
            return;
        }

        filtered.forEach(item => {
            let badgeHtml = '';
            if (item.status === 'Pending') {
                badgeHtml = `<span class="bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span> รอดำเนินการ</span>`;
            } else if (item.status === 'Approved') {
                badgeHtml = `<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"><i class="fa-solid fa-check text-[10px]"></i> อนุมัติแล้ว</span>`;
            } else {
                badgeHtml = `<span class="bg-indigo-50 text-indigo-700 border border-indigo-200 text-[11px] font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"><i class="fa-solid fa-pen-to-square text-[10px]"></i> ให้แก้ไข</span>`;
            }

            const tr = document.createElement('tr');
            tr.className = 'hover:bg-slate-50/80 transition';
            tr.innerHTML = `
                <td class="px-4 py-4 font-bold text-slate-800">${item.course_name}</td>
                <td class="px-4 py-4 text-center font-bold text-slate-600">${item.credits}</td>
                <td class="px-4 py-4 text-center">${badgeHtml}</td>
                <td class="px-4 py-4 text-right">
                    <button onclick="openQuickView(${item.id})" class="bg-sky-50 hover:bg-sky-100 text-sky-700 text-xs font-bold px-3 py-1.5 rounded-xl transition inline-flex items-center gap-1">
                        <i class="fa-solid fa-eye"></i> รายละเอียด
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
            'Need_Edit': 'แสดงเฉพาะคำร้องที่ ต้องแก้ไขหลักฐาน'
        };
        const labelElem = document.getElementById('filter_status_label');
        if(labelElem) labelElem.innerText = labelMap[status] || '';

        renderTable();
    }

    function openQuickView(id) {
        const item = requestsData.find(r => r.id === id);
        if (!item) return;

        document.getElementById('modal_course_name').innerText = item.course_name;
        document.getElementById('modal_credits_text').innerText = 'จำนวน: ' + item.credits + ' หน่วยกิต';

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
        renderTable();

        const pendingCount = requestsData.filter(r => r.status === 'Pending').length;
        const approvedCount = requestsData.filter(r => r.status === 'Approved').length;
        const needEditCount = requestsData.filter(r => r.status !== 'Pending' && r.status !== 'Approved').length;

        const chartCanvas = document.getElementById('studentChart');
        if (chartCanvas) {
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
                            const statusMap = ['Pending', 'Approved', 'Need_Edit'];
                            filterByStatus(statusMap[index]);
                        }
                    }
                }
            });
        }
    });
    </script>
    """

    js_code = js_template.replace('__REQUESTS_JSON__', req_json_str)
    student_content = html_part + js_code

    return render_layout(student_content, active_page='home')


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
    except: approved_courses = []

    cards = ""
    for c in filtered_courses:
        badge_prov = "bg-sky-100 text-sky-700 border-sky-200" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-700 border-amber-200"
        
        mooc_items = ""
        for idx_m, m in enumerate(c['mooc_list']):
            mooc_items += f'''
            <div class="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-slate-50 last:border-0 text-xs">
                <div class="flex items-start gap-1.5 text-slate-700 font-medium"><i class="fa-solid fa-check text-sky-400 mt-0.5"></i> <span>{m}</span></div>
            </div>
            '''
        
        if c['name'] in approved_courses:
            btn = '<div class="text-center w-full bg-emerald-50 text-emerald-600 font-bold py-2.5 rounded-xl text-xs border border-emerald-200"><i class="fa-solid fa-check-circle"></i> เทียบโอนแล้ว</div>'
        else:
            btn = f'<a href="/submit_credit?selected_courses={c["code"]}" class="block text-center w-full bg-slate-900 hover:bg-black text-white font-bold py-2.5 rounded-xl text-xs transition">เลือกวิชานี้</a>'

        cards += f"""
        <div class="bg-white rounded-3xl border border-sky-100 p-6 shadow-sm hover:shadow-md transition card-hover flex flex-col h-full">
            <div class="flex justify-between items-start mb-4">
                <span class="font-mono text-[10px] font-black bg-slate-100 text-slate-500 px-2.5 py-1 rounded-lg tracking-widest">{c['code']}</span>
                <span class="px-2.5 py-1 rounded-lg text-[10px] font-black border {badge_prov} uppercase">{c['provider']}</span>
            </div>
            <h3 class="text-lg font-black text-slate-900 leading-snug mb-2">{c['name']}</h3>
            <div class="mb-4 flex items-center justify-between bg-slate-50 p-2 rounded-xl border border-slate-100 text-xs">
                <span class="font-bold text-slate-500">รวมชั่วโมงเรียน:</span>
                <span class="font-black text-sky-600">{c['total_hours']}</span>
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
            <input type="text" name="search" value="{search_query}" placeholder="ค้นหา เช่น 'การเขียนโปรแกรม' หรือ '15-02-002'" class="w-full pl-12 pr-4 py-4 text-sm font-bold text-slate-800 bg-transparent outline-none placeholder-slate-400">
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
    if 'user_id' not in session: return redirect(url_for('login'))
    
    course_data = get_courses()
    total_courses_count = len(course_data)
    try:
        approved_reqs = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
        approved_courses = [r.course_name for r in approved_reqs]
    except Exception: approved_courses = []

    rows = ""
    for idx, c in enumerate(course_data, 1):
        mooc_items = ""
        for idx_m, m in enumerate(c['mooc_list']):
            mooc_items += f'<div class="py-1 border-b border-slate-100 last:border-0">- {m}</div>'

        prov_badge = f'<span class="px-2 py-0.5 rounded text-[10px] font-bold {"bg-sky-100 text-sky-700" if c["provider"] == "ThaiMOOC" else "bg-amber-100 text-amber-700"} border border-slate-100">{c["provider"]}</span>'
        
        # ปรับปรุง: ถ้าอนุมัติแล้วโชว์ป้ายเขียว ถ้ายังไม่ผ่านให้โชว์เครื่องหมายขีด - (ไม่มีปุ่มเลือกเทียบโอน)
        if c['name'] in approved_courses: 
            status_display = '<span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 inline-flex items-center gap-1"><i class="fa-solid fa-circle-check text-emerald-500"></i> เทียบโอนเรียบร้อย</span>'
        else: 
            status_display = '<span class="text-slate-400 font-medium text-xs">-</span>'

        rows += f"""
        <tr class="border-b border-slate-100 hover:bg-slate-50 text-xs align-top">
            <td class="py-3 px-4 font-mono font-bold text-slate-400">{idx}</td>
            <td class="py-3 px-4 font-mono font-bold text-sky-700">{c['code']}</td>
            <td class="py-3 px-4 font-extrabold text-slate-800">{c['name']}<br><span class="text-[10px] text-slate-400 font-medium">{c['group']}</span></td>
            <td class="py-3 px-4">{prov_badge}</td>
            <td class="py-3 px-4 font-medium text-slate-600"><div class="space-y-1">{mooc_items}</div></td>
            <td class="py-3 px-4 font-black text-sky-700 whitespace-nowrap">{c['total_hours']}</td>
            <td class="py-3 px-4 text-center font-black text-slate-800">{c['credits']}</td>
            <td class="py-3 px-4 text-center">{status_display}</td>
        </tr>
        """

    content = f"""
    <div class="mb-6 flex justify-between items-end">
        <div>
            <h2 class="text-2xl font-black text-slate-900">หลักสูตรทั้งหมด <span class="text-sm font-bold text-sky-600 bg-sky-50 px-3 py-1 rounded-xl border border-sky-100 ml-2">รวมทั้งสิ้น {total_courses_count} รายวิชา</span></h2>
            <p class="text-slate-500 text-sm font-medium mt-1">แสดงรายวิชาทั้งหมดที่รองรับการเทียบโอนในระบบธนาคารหน่วยกิต</p>
        </div>
        <a href="/available_courses" class="text-xs font-bold bg-white border border-sky-200 text-sky-600 px-4 py-2 rounded-xl hover:bg-sky-50 shadow-sm"><i class="fa-solid fa-magnifying-glass mr-1"></i> ค้นหารายวิชา (Grid)</a>
    </div>

    <div class="bg-white rounded-3xl border border-sky-100 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left min-w-[950px]">
                <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-black text-slate-500 uppercase tracking-wider">
                    <tr><th class="py-4 px-4 w-10">#</th><th class="py-4 px-4">รหัสวิชา</th><th class="py-4 px-4">ชื่อวิชาหลักสูตร IS</th><th class="py-4 px-4">ระบบ</th><th class="py-4 px-4">ใบเกียรติบัตรย่อยที่ต้องใช้</th><th class="py-4 px-4">รวมชั่วโมง</th><th class="py-4 px-4 text-center">หน่วยกิต</th><th class="py-4 px-4 text-center">สถานะ</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
    """
    return render_layout(content, active_page='all_courses')

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads'))
    os.makedirs(upload_folder, exist_ok=True)
    
    if request.method == 'POST':
        selected_codes = request.form.getlist('selected_courses')
        courses_data = get_courses()
        course_dict = {c['code']: c for c in courses_data}

        for code in selected_codes:
            if code in course_dict:
                c_info = course_dict[code]
                doc_imgs = []
                for idx in range(len(c_info['mooc_list'])):
                    file_key = f'cert_file_{code}_{idx}'
                    if file_key in request.files:
                        file = request.files[file_key]
                        if file and file.filename != '' and allowed_file(file.filename):
                            ext = file.filename.rsplit('.', 1)[1].lower()
                            filename = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                            file.save(os.path.join(upload_folder, filename))
                            doc_imgs.append(filename)
                
                if doc_imgs:
                    new_req = CreditRequest(
                        user_id=user.id,
                        course_name=c_info['name'],
                        credits=c_info['credits'],
                        institution="ThaiMOOC",
                        doc_img=doc_imgs[0] if len(doc_imgs) > 0 else None,
                        doc_img2=doc_imgs[1] if len(doc_imgs) > 1 else None,
                        doc_img3=doc_imgs[2] if len(doc_imgs) > 2 else None,
                        status='Pending'
                    )
                    db.session.add(new_req)
        
        db.session.commit()
        flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    # GET Request: เช็กว่ามีส่ง selected_courses มาใน URL หรือไม่
    selected_from_url = request.args.get('selected_courses', '').strip()

    courses_data = get_courses()
    user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).all()
    submitted_course_names = [r.course_name for r in user_requests]

    std_rows = ""
    for c in courses_data:
        already = c['name'] in submitted_course_names
        if already:
            cb_html = '<span class="bg-amber-100 text-amber-700 text-xs px-2.5 py-1 rounded-lg font-bold inline-block">ยื่นแล้ว</span>'
        else:
            is_checked = 'checked' if c['code'] == selected_from_url else ''
            cb_html = f'<input type="checkbox" name="selected_courses" value="{c["code"]}" {is_checked} class="course-checkbox w-4 h-4 text-sky-600 rounded cursor-pointer">'

        moocs_html = "<br>".join([f'<span class="text-slate-600">• {m}</span>' for m in c['mooc_list']])
        
        std_rows += f"""
        <tr class="hover:bg-slate-50/80 transition border-b border-slate-100">
            <td class="px-6 py-4 text-center">{cb_html}</td>
            <td class="px-6 py-4 font-mono font-bold text-sky-700 text-xs">{c['code']}</td>
            <td class="px-6 py-4 font-bold text-slate-800">{c['name']} <span class="text-xs text-slate-400 font-normal">({c['credits']} หน่วยกิต)</span></td>
            <td class="px-6 py-4 text-xs leading-relaxed">{moocs_html}</td>
        </tr>
        """

    courses_json_str = json.dumps(courses_data, ensure_ascii=False)

    html_part = f"""
    <div class="max-w-5xl mx-auto space-y-6">
        <div class="bg-white p-8 rounded-3xl shadow-sm border border-slate-100 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <h2 class="text-3xl font-black text-slate-800 mb-2">ยื่นคำขอเทียบโอน</h2>
                <p class="text-slate-500 text-sm">เลือกวิชาในหลักสูตรที่ต้องการเทียบโอน จากนั้นกดปุ่มสร้างฟอร์มด้านล่างเพื่อแนบหลักฐาน</p>
            </div>
            <div class="space-x-2 shrink-0">
                <button type="button" onclick="toggleSelectAll(true)" class="text-xs bg-sky-50 text-sky-700 px-4 py-2.5 rounded-xl hover:bg-sky-100 font-bold transition">เลือกทั้งหมด</button>
                <button type="button" onclick="toggleSelectAll(false)" class="text-xs bg-slate-50 text-slate-600 px-4 py-2.5 rounded-xl hover:bg-slate-100 font-bold transition">ยกเลิกเลือก</button>
            </div>
        </div>

        <div class="bg-white rounded-3xl shadow-sm border border-slate-100 overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="bg-slate-50 text-slate-500 font-extrabold text-xs uppercase tracking-wider">
                        <tr>
                            <th class="px-6 py-5 text-center w-24">เลือก</th>
                            <th class="px-6 py-5 w-32">รหัสวิชา</th>
                            <th class="px-6 py-5 w-64">ชื่อรายวิชา</th>
                            <th class="px-6 py-5">MOOC ที่ต้องใช้แนบหลักฐาน</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {std_rows}
                    </tbody>
                </table>
            </div>
            
            <div class="p-6 bg-slate-50 border-t border-slate-100 text-center md:text-right">
                <button type="button" onclick="generateDynamicUploads()" class="w-full md:w-auto bg-slate-800 hover:bg-slate-900 text-white font-bold py-3.5 px-8 rounded-2xl shadow-md transition">
                    สร้างฟอร์มอัปโหลดหลักฐาน <i class="fa-solid fa-arrow-down ml-2"></i>
                </button>
            </div>
        </div>

        <form method="POST" enctype="multipart/form-data" id="dynamic_upload_container" class="hidden space-y-6 mt-8">
            <div class="bg-white p-8 rounded-3xl shadow-sm border border-sky-100">
                <div class="flex items-center gap-3 border-b border-slate-100 pb-5 mb-6">
                    <div class="bg-sky-100 p-2.5 rounded-xl text-sky-600"><i class="fa-solid fa-cloud-arrow-up text-lg"></i></div>
                    <h3 class="text-xl font-black text-slate-800">กล่องอัปโหลดหลักฐานตามวิชาที่เลือก</h3>
                </div>
                
                <div id="upload_forms_wrapper" class="space-y-5"></div>
                
                <div class="mt-8 pt-6 border-t border-slate-100">
                    <button type="submit" class="w-full bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white font-black py-4 rounded-2xl shadow-lg hover:shadow-xl transition text-lg">
                        ยืนยันการส่งคำขอเทียบโอน
                    </button>
                </div>
            </div>
        </form>
    </div>
    """

    js_template = """
    <script>
    const allCoursesData = __COURSES_JSON__;
    const courseMap = {};
    allCoursesData.forEach(c => { courseMap[c.code] = c; });

    function toggleSelectAll(selectState) {
        const checkboxes = document.querySelectorAll('.course-checkbox:not(:disabled)');
        checkboxes.forEach(cb => {
            cb.checked = selectState;
        });
    }

    function removeUploadBox(code) {
        const box = document.getElementById('upload-box-' + code);
        if(box) box.remove();
        
        const checkbox = document.querySelector('input[value="' + code + '"]');
        if(checkbox) checkbox.checked = false;
        
        const wrapper = document.getElementById('upload_forms_wrapper');
        if (wrapper.children.length === 0) {
            document.getElementById('dynamic_upload_container').classList.add('hidden');
        }
    }

    function generateDynamicUploads() {
        const checkboxes = document.querySelectorAll('.course-checkbox:checked');
        const container = document.getElementById('dynamic_upload_container');
        const wrapper = document.getElementById('upload_forms_wrapper');
        
        if (checkboxes.length === 0) { 
            alert('กรุณาติ๊กเลือกวิชาอย่างน้อย 1 วิชา ก่อนกดสร้างฟอร์มครับ'); 
            return; 
        }

        wrapper.innerHTML = '';
        checkboxes.forEach(cb => {
            const code = cb.value;
            const course = courseMap[code];
            if (!course) return;

            let fileInputsHtml = '';
            course.mooc_list.forEach((mooc_name, index) => {
                fileInputsHtml += `
                <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div class="flex-grow">
                        <span class="bg-sky-100 text-sky-800 text-[11px] px-2.5 py-1 rounded-lg font-black uppercase mb-2 inline-block">ใบประกาศที่ ${index + 1}</span>
                        <p class="text-sm font-bold text-slate-700">${mooc_name}</p>
                    </div>
                    <div class="shrink-0 w-full md:w-auto">
                        <input type="file" name="cert_file_${code}_${index}" accept="image/*,.pdf" required 
                            class="w-full md:w-72 text-xs font-medium file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-sky-600 file:text-white file:font-bold file:cursor-pointer hover:file:bg-sky-700 bg-white border border-slate-200 p-1 rounded-xl">
                    </div>
                </div>
                `;
            });

            const sectionHtml = `
                <div class="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm" id="upload-box-${course.code}">
                    <input type="hidden" name="selected_courses" value="${course.code}">
                    <div class="flex flex-wrap justify-between items-center border-b border-slate-100 pb-4 mb-4 gap-4">
                        <div>
                            <h4 class="font-black text-slate-800 text-lg">${course.name}</h4>
                            <p class="text-sm font-bold text-slate-500 mt-1">รหัส: ${course.code} <span class="mx-2 text-slate-300">|</span> ${course.credits} หน่วยกิต</p>
                        </div>
                        <button type="button" onclick="removeUploadBox('${course.code}')" class="bg-rose-50 hover:bg-rose-100 text-rose-600 px-4 py-2.5 rounded-xl text-xs font-bold transition flex items-center gap-2"><i class="fa-solid fa-trash"></i> เอาวิชานี้ออก</button>
                    </div>
                    <div class="space-y-3">${fileInputsHtml}</div>
                </div>
            `;
            wrapper.insertAdjacentHTML('beforeend', sectionHtml);
        });

        container.classList.remove('hidden');
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ทำงานอัตโนมัติเมื่อกดมาจากหน้าค้นหารายวิชา
    document.addEventListener("DOMContentLoaded", function() {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('selected_courses')) {
            generateDynamicUploads();
        }
    });
    </script>
    """

    js_code = js_template.replace('__COURSES_JSON__', courses_json_str)
    content = html_part + js_code

    return render_layout(content, active_page='submit_credit')

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).order_by(CreditRequest.id.desc()).all()
    except: user_requests = []

    rows = ""
    for r in user_requests:
        status = getattr(r, 'status', 'Pending')
        if status == 'Pending': badge = '<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-amber-100 text-amber-700">รอตรวจ</span>'
        elif status == 'Approved': badge = '<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-emerald-100 text-emerald-700">อนุมัติแล้ว</span>'
        elif status == 'Needs_Revision': badge = f'<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-indigo-100 text-indigo-700">ให้แก้ไข: {r.reject_reason or "-"}</span> <a href="/student/edit_request/{r.id}" class="ml-2 bg-indigo-600 text-white px-3 py-1 rounded text-xs font-bold hover:bg-indigo-700"><i class="fa-solid fa-pen-to-square"></i> แก้ไขรูปหลักฐาน</a>'
        else: badge = f'<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-rose-100 text-rose-700">ไม่อนุมัติ ({r.reject_reason or "-"})</span>'
        
        img_preview = ""
        if getattr(r, 'doc_img', None): img_preview += f'<a href="/static/uploads/{r.doc_img}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap mr-2"><i class="fa-solid fa-image"></i> รูปที่ 1</a>'
        if getattr(r, 'doc_img2', None): img_preview += f'<a href="/static/uploads/{r.doc_img2}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap mr-2"><i class="fa-solid fa-image"></i> รูปที่ 2</a>'
        if getattr(r, 'doc_img3', None): img_preview += f'<a href="/static/uploads/{r.doc_img3}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap mr-2"><i class="fa-solid fa-image"></i> รูปที่ 3</a>'
        
        if not img_preview: img_preview = '<span class="text-[10px] text-slate-400">ไม่มีรูป</span>'

        rows += f"""
        <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-400">{getattr(r, 'req_code', '-')}</td>
            <td class="py-4 px-4 font-extrabold text-slate-800">{getattr(r, 'course_name', '-')}<div class="mt-1 flex gap-2 flex-wrap">{img_preview}</div></td>
            <td class="py-4 px-4 font-bold text-sky-600 text-center">{getattr(r, 'credits', 0)}</td>
            <td class="py-4 px-4">{badge}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto max-w-5xl mx-auto">
        <h3 class="text-2xl font-black text-slate-900 mb-6">ประวัติคำร้องเทียบโอน</h3>
        <table class="w-full text-left min-w-[500px]">
            <thead class="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <tr><th class="py-3 px-4">รหัส</th><th class="py-3 px-4">วิชาที่ขอ / รูปหลักฐาน</th><th class="py-3 px-4 text-center">หน่วยกิต</th><th class="py-3 px-4">สถานะ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-12 text-center text-slate-400">ไม่มีประวัติคำร้องเทียบโอน</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_layout(content, active_page='history')

@app.route('/student/edit_request/<int:req_id>', methods=['GET', 'POST'])
def student_edit_request(req_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)
    if req.user_id != session['user_id']: return redirect(url_for('history'))

    if request.method == 'POST':
        if 'cert_file_0' in request.files:
            file = request.files['cert_file_0']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                req.doc_img = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], req.doc_img))
        if 'cert_file_1' in request.files:
            file = request.files['cert_file_1']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                req.doc_img2 = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], req.doc_img2))
        if 'cert_file_2' in request.files:
            file = request.files['cert_file_2']
            if file and file.filename != '' and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                req.doc_img3 = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], req.doc_img3))

        req.status = 'Pending' 
        req.reject_reason = None
        db.session.commit()
        flash('อัปเดตหลักฐานและส่งให้เจ้าหน้าที่ตรวจสอบเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    course_data_list = get_courses()
    matched_course = next((c for c in course_data_list if c['name'] == req.course_name), None)
    mooc_names = matched_course['mooc_list'] if matched_course else []

    def get_mooc_title(index, default_title):
        if index < len(mooc_names): return f"{default_title} : {mooc_names[index]}"
        return default_title

    ev_html = ""
    if getattr(req, 'doc_img', None):
        title = get_mooc_title(0, "หลักฐานที่ 1")
        ev_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-0" src="/static/uploads/{req.doc_img}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_0" onchange="previewImage(event, \'preview-img-0\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'
    if getattr(req, 'doc_img2', None):
        title = get_mooc_title(1, "หลักฐานที่ 2")
        ev_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-1" src="/static/uploads/{req.doc_img2}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_1" onchange="previewImage(event, \'preview-img-1\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'
    if getattr(req, 'doc_img3', None):
        title = get_mooc_title(2, "หลักฐานที่ 3")
        ev_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-2" src="/static/uploads/{req.doc_img3}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_2" onchange="previewImage(event, \'preview-img-2\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">แก้ไขหลักฐานคำร้อง: {req.course_name}</h3>
        <p class="text-xs text-rose-600 mb-6 font-bold">เหตุผลที่ต้องแก้ไข: {req.reject_reason or "-"}</p>
        <form method="POST" enctype="multipart/form-data" class="space-y-6">
            <div class="space-y-4">{ev_html}</div>
            <button type="submit" class="w-full bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm">บันทึกและส่งให้เจ้าหน้าที่ตรวจสอบอีกครั้ง</button>
        </form>
    </div>
    """
    
    # แก้ปัญหาเครื่องหมายปีกกาของสคริปต์ตีกัน โดยแยกเป็นสตริงปกติ
    content += """
    <script>
        function previewImage(event, imgId) {
            var input = event.target;
            if (input.files && input.files[0]) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    document.getElementById(imgId).src = e.target.result;
                };
                reader.readAsDataURL(input.files[0]);
            }
        }
    </script>
    """
    
    return render_layout(content, active_page='history')

    course_data_list = get_courses()
    matched_course = next((c for c in course_data_list if c['name'] == req.course_name), None)
    mooc_names = matched_course['mooc_list'] if matched_course else []

    def get_mooc_title(index, default_title):
        if index < len(mooc_names): return f"{default_title} : {mooc_names[index]}"
        return default_title

    evidence_html = ""
    # เพิ่ม id ให้รูปภาพ และ onchange ให้ input สำหรับเปลี่ยนรูปเรียลไทม์
    if getattr(req, 'doc_img', None):
        title = get_mooc_title(0, "หลักฐานที่ 1")
        evidence_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-0" src="/static/uploads/{req.doc_img}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_0" onchange="previewImage(event, \'preview-img-0\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'
    if getattr(req, 'doc_img2', None):
        title = get_mooc_title(1, "หลักฐานที่ 2")
        evidence_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-1" src="/static/uploads/{req.doc_img2}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_1" onchange="previewImage(event, \'preview-img-1\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'
    if getattr(req, 'doc_img3', None):
        title = get_mooc_title(2, "หลักฐานที่ 3")
        evidence_html += f'<div class="bg-slate-50 p-4 rounded-2xl border border-slate-200"><p class="text-sm font-bold text-sky-700 mb-2">{title}</p><img id="preview-img-2" src="/static/uploads/{req.doc_img3}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain"><input type="file" name="cert_file_2" onchange="previewImage(event, \'preview-img-2\')" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:bg-sky-600 file:text-white"></div>'

        content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">แก้ไขหลักฐานคำร้อง: {req.course_name}</h3>
        <p class="text-xs text-rose-600 mb-6 font-bold">เหตุผลที่ต้องแก้ไข: {req.reject_reason or "-"}</p>
        <form method="POST" enctype="multipart/form-data" class="space-y-6">
            <!-- แก้ไขตรงนี้เป็นปีกกาเดี่ยว จะโชว์รูปได้แล้วครับ -->
            <div class="space-y-4">{evidence_html}</div>
            <button type="submit" class="w-full bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm">บันทึกและส่งให้เจ้าหน้าที่ตรวจสอบอีกครั้ง</button>
        </form>
    </div>
    
    <script>
        function previewImage(event, imgId) {{
            var input = event.target;
            if (input.files && input.files[0]) {{
                var reader = new FileReader();
                reader.onload = function(e) {{
                    document.getElementById(imgId).src = e.target.result;
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
    except: approved_requests = []

    total_approved = sum(getattr(r, 'credits', 0) for r in approved_requests)
    rows = ""
    for r in approved_requests:
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{getattr(r, 'approved_by', 'เจ้าหน้าที่') or 'เจ้าหน้าที่'}</td>
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
            <td class="py-4 px-4 font-mono font-bold text-sky-600">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-bold text-slate-900">{student_name}<br><span class="text-xs text-sky-600 font-semibold">({student_code})</span></td>
            <td class="py-4 px-4 text-slate-700 font-medium">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-500 text-xs font-medium">{getattr(r, 'date_submitted', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{action_col}</td>
        </tr>
        """
        
    filter_label = "ทั้งหมด"
    if status_filter == 'Approved': filter_label = "อนุมัติแล้ว"
    elif status_filter == 'Pending': filter_label = "รอดำเนินการ"
    elif status_filter == 'Needs_Revision': filter_label = "ส่งกลับให้แก้ไข"

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto space-y-6">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
                <h3 class="text-xl font-black text-slate-900">รายการคำร้องเทียบโอนทั้งหมด (สาขาวิชาระบบสารสนเทศ)</h3>
                <p class="text-xs text-slate-400 mt-1">กำลังแสดงหมวด: <span class="font-bold text-sky-600">{filter_label}</span></p>
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
        admin_user = User.query.get(session['user_id'])
        if action == 'approve':
            req.status = 'Approved'
            req.approved_by = admin_user.fullname
            db.session.commit()
            flash('อนุมัติผ่านเรียบร้อย', 'success')
            return redirect(url_for('admin_requests'))
        elif action == 'reject':
            req.status = 'Rejected'
            req.reject_reason = request.form.get('reject_reason', '-')
            req.approved_by = admin_user.fullname
            db.session.commit()
            flash('ปฏิเสธคำร้องเรียบร้อย', 'success')
            return redirect(url_for('admin_requests'))
        elif action == 'revision':
            req.status = 'Needs_Revision'
            req.reject_reason = request.form.get('reject_reason', 'กรุณาแก้ไขรูปหลักฐานให้ถูกต้อง')
            req.approved_by = admin_user.fullname
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
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{title}</span><a href="/static/uploads/{req.doc_img}" target="_blank"><img src="/static/uploads/{req.doc_img}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'
    if getattr(req, 'doc_img2', None):
        title = get_mooc_title(1, "หลักฐานที่ 2")
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{title}</span><a href="/static/uploads/{req.doc_img2}" target="_blank"><img src="/static/uploads/{req.doc_img2}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'
    if getattr(req, 'doc_img3', None):
        title = get_mooc_title(2, "หลักฐานที่ 3")
        evidence_html += f'<div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl"><span class="text-sm font-bold text-sky-700 bg-sky-100 px-3 py-1.5 rounded-lg mb-2 inline-block">{title}</span><a href="/static/uploads/{req.doc_img3}" target="_blank"><img src="/static/uploads/{req.doc_img3}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain mt-2" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></a></div>'

    student = req.user
    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <div class="flex justify-between items-center mb-6">
            <h3 class="text-xl font-black text-slate-900">พิจารณาคำร้อง: {req.course_name}</h3>
            <span class="bg-slate-100 text-slate-600 px-3 py-1 rounded-lg text-xs font-bold">{getattr(req, 'req_code', '')}</span>
        </div>

        <div class="bg-sky-50/50 p-6 rounded-2xl border border-sky-100 mb-6 flex gap-8 text-sm">
            <div><p class="text-xs font-bold text-slate-400 mb-1">นักศึกษา</p><p class="font-bold">{student.fullname if student else '-'}</p></div>
            <div><p class="text-xs font-bold text-slate-400 mb-1">ระบบ</p><p class="font-bold">{getattr(req, 'institution', '-')}</p></div>
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
    user = User.query.get(session['user_id'])
    if not user: return redirect(url_for('login'))
    display_title = "เจ้าหน้าที่" if user.role in ['admin', 'superadmin'] else f"{user.prefix or ''} {user.fullname}"
    
    edit_btn_html = ""
    if user.role not in ['admin', 'superadmin']:
        edit_btn_html = '<a href="/request_edit_profile" class="absolute top-6 right-6 bg-sky-100 hover:bg-sky-200 text-sky-700 px-4 py-2 rounded-xl text-xs font-bold transition-all"><i class="fa-solid fa-pen mr-1"></i> แก้ไขข้อมูล</a>'

    content = f"""
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl relative">
        {edit_btn_html}
        <h3 class="text-2xl font-black text-slate-900 mb-1">{display_title}</h3>
        <p class="text-sm font-bold text-sky-600 mb-1">รหัสนักศึกษา: {user.member_id or '-'}</p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5 bg-sky-50/50 p-6 rounded-2xl border border-sky-100 text-sm mt-6">
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ชื่อ-สกุล</span> <span class="font-bold text-slate-800">{user.fullname}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เลขบัตรประชาชน</span> <span class="font-bold text-slate-800">{user.id_card or '-'}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เบอร์โทรศัพท์</span> <span class="font-bold text-slate-800">{user.phone or '-'}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">อีเมล</span> <span class="font-bold text-slate-800">{user.email or '-'}</span></div>
            <div class="md:col-span-2"><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ที่อยู่</span> <span class="font-bold text-slate-800">{user.address or '-'}</span></div>
        </div>
    </div>
    """
    return render_layout(content, active_page='profile')

@app.route('/request_edit_profile', methods=['GET', 'POST'])
def request_edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

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
                <div class="col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">ชื่อ-นามสกุล</label><input type="text" name="fullname" value="{user.fullname}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">เบอร์โทรศัพท์</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1.5">อีเมล</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
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
    except: students = []

    rows = ""
    for s in students:
        try: approved_credits = sum(r.credits for r in CreditRequest.query.filter_by(user_id=s.id, status='Approved').all())
        except: approved_credits = 0
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-bold text-sky-600 font-mono">{s.member_id or '-'}<br><span class="text-xs text-slate-400 font-normal">({s.id_card or '-'})</span></td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{s.prefix or ''} {s.fullname}<br><span class="text-xs text-slate-500 font-normal">สาขาวิชาระบบสารสนเทศ</span></td>
            <td class="py-4 px-4 text-xs text-slate-600 font-medium">{s.phone or '-'}<br>{s.email or '-'}</td>
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
    if session.get('role') != 'superadmin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้าจัดการเจ้าหน้าที่ (เฉพาะผู้ดูแลหลักเท่านั้น)', 'error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        id_card = request.form.get('id_card', '').strip()
        password = request.form.get('password', '').strip()
        role_type = request.form.get('role_type', 'admin')
        new_admin = User(member_id=f"ADM{uuid.uuid4().hex[:3].upper()}", prefix="เจ้าหน้าที่", fullname=fullname, id_card=id_card, username=id_card, password=generate_password_hash(password), role=role_type)
        db.session.add(new_admin)
        db.session.commit()
        flash('เพิ่มเจ้าหน้าที่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('manage_admins'))

    admin_list = User.query.filter(User.role.in_(['admin', 'superadmin'])).all()
    rows = ""
    for a in admin_list:
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-bold"><a href="/admin/manage_admin_detail/{a.id}" class="text-sky-600 hover:underline">{a.fullname}</a></td>
            <td class="py-4 px-4 font-mono text-xs">{a.username}</td>
            <td class="py-4 px-4"><span class="px-2 py-1 rounded text-xs font-bold {'bg-purple-100 text-purple-700' if a.role=='superadmin' else 'bg-sky-100 text-sky-700'}">{'ผู้ดูแลหลัก (Super Admin)' if a.role=='superadmin' else 'เจ้าหน้าที่ทั่วไป'}</span></td>
        </tr>
        """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
            <h3 class="text-xl font-black text-slate-900 mb-6">เพิ่มบัญชีเจ้าหน้าที่</h3>
            <form method="POST" class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label class="block text-xs font-bold text-slate-700 mb-1">ชื่อ-นามสกุล</label><input type="text" name="fullname" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-bold text-slate-700 mb-1">เลขบัตรประชาชน (Username)</label><input type="text" name="id_card" maxlength="13" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-bold text-slate-700 mb-1">รหัสผ่าน</label><input type="password" name="password" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-bold text-slate-700 mb-1">ระดับสิทธิ์</label><select name="role_type" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"><option value="admin">เจ้าหน้าที่ทั่วไป</option><option value="superadmin">ผู้ดูแลหลัก (Super Admin)</option></select></div>
                </div>
                <button type="submit" class="w-full bg-sky-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-2">บันทึกเพิ่มเจ้าหน้าที่</button>
            </form>
        </div>
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
            <h3 class="text-lg font-bold text-slate-800 mb-4">รายชื่อเจ้าหน้าที่ในระบบ (คลิกที่ชื่อเพื่อดูรายละเอียด)</h3>
            <table class="w-full text-left">
                <thead class="bg-sky-50 text-xs text-sky-700 uppercase"><tr><th class="py-3 px-4">ชื่อ-สกุล</th><th class="py-3 px-4">Username</th><th class="py-3 px-4">สิทธิ์</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
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
            <h3 class="text-xl font-black text-slate-900">รายละเอียดเจ้าหน้าที่: {target_admin.fullname}</h3>
            <a href="/admin/manage_admins" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ย้อนกลับ</a>
        </div>
        <form method="POST" class="space-y-4">
            <div><label class="block text-xs font-bold text-slate-700 mb-1">ชื่อ-นามสกุล</label><input type="text" name="fullname" value="{target_admin.fullname}" required class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
            <div><label class="block text-xs font-bold text-slate-700 mb-1">เบอร์โทรศัพท์</label><input type="text" name="phone" value="{target_admin.phone or ''}" class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
            <div><label class="block text-xs font-bold text-slate-700 mb-1">อีเมล</label><input type="email" name="email" value="{target_admin.email or ''}" class="w-full border rounded-xl p-3 text-sm bg-sky-50"></div>
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
            return redirect(url_for('home'))
        flash('ข้อมูลไม่ถูกต้อง', 'error')
    
    content = """
    <div class="max-w-md mx-auto my-12 bg-white p-10 rounded-[2rem] shadow-xl text-center border border-sky-100">
        <div class="w-16 h-16 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-2xl mx-auto mb-4"><i class="fa-solid fa-lock"></i></div>
        <h2 class="text-2xl font-black text-slate-900 mb-8">เข้าสู่ระบบ (Login)</h2>
        <form method="POST" class="space-y-4 text-left">
            <div><label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">Username / บัตรประชาชน</label><input type="text" name="username" required class="w-full border rounded-xl p-3 text-sm bg-slate-50 outline-none"></div>
            <div><label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">รหัสผ่าน</label><input type="password" name="password" required class="w-full border rounded-xl p-3 text-sm bg-slate-50 outline-none"></div>
            <button type="submit" class="w-full bg-slate-900 text-white font-bold py-3.5 rounded-xl shadow-md mt-4 hover:bg-black transition">เข้าสู่ระบบ</button>
        </form>
    </div>
    """
    return render_layout(content, active_page='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/secret_clear_all_requests')
def secret_clear_all_requests():
    # ป้องกันไม่ให้คนอื่นเข้าถึงได้ ให้เฉพาะ superadmin เท่านั้น
    if session.get('role') != 'superadmin': 
        return "คุณไม่มีสิทธิ์เข้าถึงหน้านี้"
    
    try:
        deleted_count = db.session.query(CreditRequest).delete()
        db.session.commit()
        flash(f'ลบข้อมูลคำร้องบนระบบออนไลน์สำเร็จทั้งหมด {deleted_count} รายการ!', 'success')
        return redirect(url_for('admin_requests'))
    except Exception as e:
        db.session.rollback()
        return f"เกิดข้อผิดพลาด: {e}"

if __name__ == '__main__':
    app.run(debug=True)

from flask import Response

@app.route('/admin/export_csv')
def admin_export_csv():
    if session.get('role') not in ['admin', 'superadmin']:
        return redirect(url_for('login'))
    
    # ดึงข้อมูลคำร้องทั้งหมด
    requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # เขียน Header รายงาน
    writer.writerow(['รหัสคำร้อง', 'รหัสนักศึกษา', 'ชื่อ-นามสกุล', 'วิชาที่ขอเทียบโอน', 'หน่วยกิต', 'วันที่ยื่น', 'สถานะ', 'ผู้อนุมัติ'])
    
    status_map = {
        'Pending': 'รอดำเนินการ',
        'Approved': 'อนุมัติแล้ว',
        'Needs_Revision': 'ส่งกลับให้แก้ไข'
    }

    for r in requests:
        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'
        st_text = status_map.get(r.status, 'รอดำเนินการ')
        
        writer.writerow([
            getattr(r, 'req_code', '-'),
            student_code,
            student_name,
            getattr(r, 'course_name', '-'),
            getattr(r, 'credits', 0),
            getattr(r, 'date_submitted', '-'),
            st_text,
            getattr(r, 'approved_by', '-') or '-'
        ])
    
    # ใส่ BOM (\ufeff) เพื่อให้ Excel เปิดภาษาไทยได้ถูกต้อง ไม่เป็นต่างดาว
    csv_data = "\ufeff" + output.getvalue()
    
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-disposition": f"attachment; filename=Credit_Bank_Report_{datetime.now().strftime('%Y%m')}.csv"}
    )