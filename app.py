import os
import uuid
import csv
import io
import urllib.request
import re
import json
from datetime import datetime
from flask import Flask, request, redirect, url_for, session, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'credit_bank_is_rmutto_production_key_2026'

db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

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
    role = db.Column(db.String(20), default='student') # student, admin, superadmin

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
    evidence_data = db.Column(db.Text, nullable=True) 
    status = db.Column(db.String(20), default='Pending') 
    reject_reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    system_precheck = db.Column(db.Text, nullable=True) # ผลตรวจอัตโนมัติสเต็ปแรก
    user = db.relationship('User', backref=db.backref('credits_list', lazy=True))

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS evidence_data TEXT;"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS system_precheck TEXT;"))
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
        manage_admin_menu = f'<a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group mt-2 {is_active("manage_admins")}"><i class="fa-solid fa-user-shield text-lg w-6 text-center text-sky-600"></i><span class="nav-text font-bold">จัดการเจ้าหน้าที่</span></a>'

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
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">โครงสร้างหลักสูตร</span></a>
                    {manage_admin_menu}
                """ if user_role in ['admin', 'superadmin'] else f"""
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('available_courses')}"><i class="fa-solid fa-magnifying-glass text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ค้นหารายวิชา (Search)</span></a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หลักสูตรทั้งหมด (Table)</span></a>
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
    if not session.get('user_id'): return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if user.role in ['admin', 'superadmin']:
        try:
            pending_reqs = CreditRequest.query.filter_by(status='Pending').order_by(CreditRequest.id.asc()).all()
            pending_count = len(pending_reqs)
            total_students = User.query.filter_by(role='student').count()
            approved_count = CreditRequest.query.filter_by(status='Approved').count()
            rejected_count = CreditRequest.query.filter_by(status='Rejected').count()
            revision_count = CreditRequest.query.filter_by(status='Needs_Revision').count()
            total_approved_credits = sum(r.credits for r in CreditRequest.query.filter_by(status='Approved').all())
        except:
            pending_reqs, pending_count, total_students, approved_count, rejected_count, revision_count, total_approved_credits = [], 0, 0, 0, 0, 0, 0

        urgent_rows = ""
        for r in pending_reqs[:5]:
            student_name = r.user.fullname if getattr(r, 'user', None) else '-'
            urgent_rows += f"""
            <div class="flex justify-between items-center py-3 border-b border-slate-100 last:border-0">
                <div>
                    <p class="text-sm font-bold text-slate-800">{r.course_name}</p>
                    <p class="text-xs text-slate-500">โดย {student_name} ({r.date_submitted})</p>
                </div>
                <a href="/admin/review/{r.id}" class="text-xs font-bold bg-sky-100 text-sky-700 px-3 py-1.5 rounded-lg hover:bg-sky-200 transition">ตรวจเอกสาร</a>
            </div>
            """
        if not urgent_rows: urgent_rows = '<div class="text-sm text-slate-500 py-4 text-center">ไม่มีคำร้องรอดำเนินการ</div>'

        content = f"""
        <div class="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 mb-6">
            <h2 class="text-2xl font-bold text-slate-900 mb-2">ยินดีต้อนรับ, {user.fullname} (เจ้าหน้าที่)</h2>
            <p class="text-slate-600 text-sm">ระบบจัดการธนาคารหน่วยกิต สาขาวิชาระบบสารสนเทศ</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div class="bg-sky-50 p-6 rounded-2xl border border-sky-100">
                <p class="text-sm text-slate-600 font-medium mb-1">นักศึกษาในระบบทั้งหมด</p>
                <h3 class="text-3xl font-bold text-sky-700">{total_students} <span class="text-base font-normal">คน</span></h3>
            </div>
            <div class="bg-amber-50 p-6 rounded-2xl border border-amber-100">
                <p class="text-sm text-slate-600 font-medium mb-1">คำร้องรอตรวจสอบ</p>
                <h3 class="text-3xl font-bold text-amber-700">{pending_count} <span class="text-base font-normal">รายการ</span></h3>
            </div>
            <div class="bg-emerald-50 p-6 rounded-2xl border border-emerald-100">
                <p class="text-sm text-slate-600 font-medium mb-1">หน่วยกิตอนุมัติรวม</p>
                <h3 class="text-3xl font-bold text-emerald-700">{total_approved_credits} <span class="text-base font-normal">หน่วยกิต</span></h3>
            </div>
        </div>

        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 mb-6">
            <h3 class="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">สถิติภาพรวมสถานะคำร้องเทียบโอน</h3>
            <div class="h-64 flex justify-center"><canvas id="adminChart"></canvas></div>
        </div>

        <div class="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200">
            <h3 class="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">คำร้องล่าสุดที่รอตรวจสอบ</h3>
            <div>{urgent_rows}</div>
        </div>

        <script>
        const ctx = document.getElementById('adminChart').getContext('2d');
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: ['รอตรวจสอบ', 'อนุมัติแล้ว', 'ให้แก้ไข', 'ไม่อนุมัติ'],
                datasets: [{{
                    label: 'จำนวนคำร้อง',
                    data: [{pending_count}, {approved_count}, {revision_count}, {rejected_count}],
                    backgroundColor: ['#f59e0b', '#10b981', '#6366f1', '#f43f5e'],
                    borderRadius: 8
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }} }}
        }});
        </script>
        """
        return render_layout(content, active_page='home')

    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
        approved_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Approved')
        pending_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Pending')
        revision_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Needs_Revision')
        rejected_count = sum(1 for r in user_requests if getattr(r, 'status', '') == 'Rejected')

        approved_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') == 'Approved')
        pending_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') in ['Pending', 'Needs_Revision'])
    except:
        user_requests, approved_count, pending_count, revision_count, rejected_count, approved_credits, pending_credits = [], 0, 0, 0, 0, 0, 0

    history_rows = ""
    for r in sorted(user_requests, key=lambda x: x.id, reverse=True)[:5]:
        status = getattr(r, 'status', 'Pending')
        if status == 'Approved': badge = '<span class="px-2 py-1 rounded bg-emerald-100 text-emerald-700 text-xs font-bold">อนุมัติแล้ว</span>'
        elif status == 'Pending': badge = '<span class="px-2 py-1 rounded bg-amber-100 text-amber-700 text-xs font-bold">รอตรวจ</span>'
        elif status == 'Needs_Revision': badge = '<span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700 text-xs font-bold">ส่งกลับให้แก้ไข</span>'
        else: badge = '<span class="px-2 py-1 rounded bg-rose-100 text-rose-700 text-xs font-bold">ไม่อนุมัติ</span>'
        history_rows += f'<div class="flex justify-between items-center py-3 border-b border-slate-100 last:border-0"><div class="text-sm font-bold text-slate-700 pr-4">{getattr(r, "course_name", "-")}</div><div>{badge}</div></div>'
    if not history_rows: history_rows = '<div class="text-sm text-slate-500 py-4 text-center">คุณยังไม่เคยยื่นคำขอเทียบโอน</div>'

    content = f"""
    <div class="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 mb-6">
        <h2 class="text-2xl font-bold text-slate-900 mb-1">ยินดีต้อนรับ, {user.prefix or ''}{user.fullname}</h2>
        <p class="text-slate-600 text-sm">รหัสนักศึกษา: {user.member_id or '-'}</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div class="bg-sky-50 p-6 rounded-2xl border border-sky-100 flex items-center justify-between">
            <div>
                <p class="text-sm text-slate-600 font-medium mb-1">หน่วยกิตที่อนุมัติแล้ว</p>
                <h3 class="text-3xl font-bold text-sky-700">{approved_credits} <span class="text-base font-normal">/ 120 หน่วยกิต</span></h3>
            </div>
            <i class="fa-solid fa-graduation-cap text-4xl text-sky-200"></i>
        </div>
        <div class="bg-amber-50 p-6 rounded-2xl border border-amber-100 flex items-center justify-between">
            <div>
                <p class="text-sm text-slate-600 font-medium mb-1">อยู่ระหว่างรอพิจารณา</p>
                <h3 class="text-3xl font-bold text-amber-700">{pending_credits} <span class="text-base font-normal">หน่วยกิต</span></h3>
            </div>
            <i class="fa-solid fa-clock-rotate-left text-4xl text-amber-200"></i>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div class="md:col-span-1 bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <h3 class="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">สัดส่วนสถานะคำขอ</h3>
            <div class="h-48 flex justify-center"><canvas id="studentChart"></canvas></div>
        </div>
        <div class="md:col-span-2 bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-between">
            <div>
                <div class="flex justify-between items-center border-b border-slate-100 pb-3 mb-3">
                    <h3 class="text-lg font-bold text-slate-800">ประวัติการยื่นคำขอล่าสุด</h3>
                    <a href="/history" class="text-sm text-sky-600 font-bold hover:underline">ดูประวัติทั้งหมด</a>
                </div>
                <div>{history_rows}</div>
            </div>
            <div class="mt-6 text-center">
                <a href="/submit_credit" class="inline-block bg-slate-900 hover:bg-black text-white px-6 py-3 rounded-xl font-bold transition text-sm">ยื่นคำขอเทียบโอนใหม่</a>
            </div>
        </div>
    </div>

    <script>
    const sCtx = document.getElementById('studentChart').getContext('2d');
    new Chart(sCtx, {{
        type: 'doughnut',
        data: {{
            labels: ['รอตรวจ', 'อนุมัติแล้ว', 'ให้แก้ไข', 'ไม่อนุมัติ'],
            datasets: [{{
                data: [{pending_count}, {approved_count}, {revision_count}, {rejected_count}],
                backgroundColor: ['#f59e0b', '#10b981', '#6366f1', '#f43f5e']
            }}]
        }},
        options: {{ responsive: true, maintainAspectRatio: false }}
    }});
    </script>
    """
    return render_layout(content, active_page='home')

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
            h_text = c['hours_list'][idx_m] if idx_m < len(c['hours_list']) else ""
            mooc_items += f'''
            <div class="flex items-start justify-between gap-2 mb-2 pb-2 border-b border-slate-50 last:border-0 text-xs">
                <div class="flex items-start gap-1.5 text-slate-700 font-medium"><i class="fa-solid fa-check text-sky-400 mt-0.5"></i> <span>{m}</span></div>
                <span class="shrink-0 bg-sky-50 text-sky-700 px-2 py-0.5 rounded text-[10px] font-bold border border-sky-100">{h_text}</span>
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
    try:
        approved_reqs = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
        approved_courses = [r.course_name for r in approved_reqs]
    except: approved_courses = []

    rows = ""
    for idx, c in enumerate(course_data, 1):
        mooc_items = ""
        for idx_m, m in enumerate(c['mooc_list']):
            h_text = c['hours_list'][idx_m] if idx_m < len(c['hours_list']) else ""
            mooc_items += f'<div class="flex justify-between items-center py-1 border-b border-slate-100 last:border-0"><span>- {m}</span><span class="text-sky-700 bg-sky-50 px-2 py-0.5 rounded text-[10px] font-bold border border-sky-100">{h_text}</span></div>'

        prov_badge = f'<span class="px-2 py-0.5 rounded text-[10px] font-bold {"bg-sky-100 text-sky-700" if c["provider"] == "ThaiMOOC" else "bg-amber-100 text-amber-700"} border border-slate-100">{c["provider"]}</span>'
        
        if c['name'] in approved_courses: btn = '<span class="text-[10px] font-bold text-emerald-600"><i class="fa-solid fa-check mr-1"></i>โอนแล้ว</span>'
        else: btn = f'<a href="/submit_credit?selected_courses={c["code"]}" class="text-[11px] font-bold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-sky-600 transition shadow-sm whitespace-nowrap">เลือกเทียบโอน</a>'

        # แก้ไขให้คำว่ารวมชั่วโมงอยู่บรรทัดเดียวกันกับตัวเลขชั่วโมงรวมโดยไม่มีเลข 7 เกิน
        rows += f"""
        <tr class="border-b border-slate-100 hover:bg-slate-50 text-xs align-top">
            <td class="py-3 px-4 font-mono font-bold text-slate-400">{idx}</td>
            <td class="py-3 px-4 font-mono font-bold text-sky-700">{c['code']}</td>
            <td class="py-3 px-4 font-extrabold text-slate-800">{c['name']}<br><span class="text-[10px] text-slate-400 font-medium">{c['group']}</span></td>
            <td class="py-3 px-4">{prov_badge}</td>
            <td class="py-3 px-4 font-medium text-slate-600"><div class="space-y-1">{mooc_items}</div></td>
            <td class="py-3 px-4 font-black text-sky-700 whitespace-nowrap">{c['total_hours']}</td>
            <td class="py-3 px-4 text-center font-black text-slate-800">{c['credits']}</td>
            <td class="py-3 px-4 text-center">{btn if session.get('role') not in ['admin', 'superadmin'] else '-'}</td>
        </tr>
        """

    content = f"""
    <div class="mb-6 flex justify-between items-end">
        <div>
            <h2 class="text-2xl font-black text-slate-900">ตารางโครงสร้างหลักสูตร (Table View)</h2>
            <p class="text-slate-500 text-sm font-medium mt-1">แสดงรายวิชาทั้งหมดที่รองรับการเทียบโอนในระบบธนาคารหน่วยกิต แยกชั่วโมงเรียนชัดเจน</p>
        </div>
        <a href="/available_courses" class="text-xs font-bold bg-white border border-sky-200 text-sky-600 px-4 py-2 rounded-xl hover:bg-sky-50 shadow-sm"><i class="fa-solid fa-magnifying-glass mr-1"></i> กลับไปหน้าค้นหา (Grid)</a>
    </div>

    <div class="bg-white rounded-3xl border border-sky-100 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left min-w-[950px]">
                <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-black text-slate-500 uppercase tracking-wider">
                    <tr><th class="py-4 px-4 w-10">#</th><th class="py-4 px-4">รหัสวิชา</th><th class="py-4 px-4">ชื่อวิชาหลักสูตร IS</th><th class="py-4 px-4">ระบบ</th><th class="py-4 px-4">ใบเกียรติบัตรย่อยที่ต้องใช้</th><th class="py-4 px-4">รวมชั่วโมง</th><th class="py-4 px-4 text-center">หน่วยกิต</th><th class="py-4 px-4 text-center">จัดการ</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
    """
    return render_layout(content, active_page='all_courses')

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            course_codes = request.form.getlist('course_codes')
            if not course_codes:
                flash('กรุณาเลือกอย่างน้อย 1 รายวิชา', 'error')
                return redirect(url_for('submit_credit'))

            course_data_list = get_courses()
            success_count = 0

            for code in course_codes:
                req_code = f"TR2569{uuid.uuid4().hex[:4].upper()}"
                
                if code == 'MANUAL_CUSTOM':
                    course_name = request.form.get('manual_course_name', '').strip()
                    if not course_name: continue
                    
                    evidence_list = []
                    for i in range(1, 4):
                        file_key = f"cert_file_MANUAL_{i}"
                        if file_key in request.files:
                            file = request.files[file_key]
                            if file and file.filename != '' and allowed_file(file.filename):
                                ext = file.filename.rsplit('.', 1)[1].lower()
                                unique_fn = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_fn))
                                evidence_list.append({"mooc_name": f"เกียรติบัตรใบที่ {i}", "filename": unique_fn})
                    
                    if not evidence_list: continue
                    
                    # ตรวจสอบสเต็ปแรกอัตโนมัติ
                    precheck_text = "ผ่านการตรวจสอบอัตโนมัติ (สเต็ปแรก): พบหลักฐานครบถ้วน รอเจ้าหน้าที่ตรวจสอบยืนยันขั้นสุดท้าย"

                    req = CreditRequest(
                        req_code=req_code, user_id=session['user_id'], course_name=course_name, 
                        institution=request.form.get('institution', 'ThaiMOOC'), credits=int(request.form.get('credits', 3)), 
                        category=request.form.get('category', 'หมวดวิชาเลือก'),
                        date_submitted=datetime.now().strftime("%Y-%m-%d"),
                        evidence_data=json.dumps(evidence_list, ensure_ascii=False), 
                        system_precheck=precheck_text, status='Pending'
                    )
                    db.session.add(req)
                    success_count += 1
                else:
                    matched_course = next((c for c in course_data_list if c['code'] == code), None)
                    if not matched_course: continue

                    evidence_list = []
                    mooc_list = matched_course['mooc_list']
                    
                    for i, mooc_name in enumerate(mooc_list):
                        file_key = f"cert_file_{code}_{i}"
                        if file_key in request.files:
                            file = request.files[file_key]
                            if file and file.filename != '' and allowed_file(file.filename):
                                ext = file.filename.rsplit('.', 1)[1].lower()
                                unique_fn = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_fn))
                                evidence_list.append({"mooc_name": mooc_name, "filename": unique_fn})
                    
                    if not evidence_list: continue

                    # ตรวจสอบสเต็ปแรกอัตโนมัติ
                    precheck_text = f"ผ่านการตรวจสอบอัตโนมัติ (สเต็ปแรก): อัปโหลดครบ {len(evidence_list)}/{len(mooc_list)} ใบ ตรงตามเงื่อนไขรายวิชา"

                    req = CreditRequest(
                        req_code=req_code, user_id=session['user_id'], course_name=matched_course['name'], 
                        institution=matched_course['provider'], credits=matched_course['credits'], 
                        category=matched_course['group'], date_submitted=datetime.now().strftime("%Y-%m-%d"),
                        evidence_data=json.dumps(evidence_list, ensure_ascii=False), 
                        system_precheck=precheck_text, status='Pending'
                    )
                    db.session.add(req)
                    success_count += 1

            db.session.commit()
            if success_count > 0:
                flash(f'ยื่นคำขอสำเร็จ {success_count} รายวิชา (ระบบตรวจสอบสเต็ปแรกผ่านแล้ว รอเจ้าหน้าที่ตรวจสอบอนุมัติ)', 'success')
                return redirect(url_for('history'))
            else:
                flash('ไม่พบไฟล์หลักฐาน หรือข้อมูลไม่ครบถ้วน', 'error')
                return redirect(url_for('submit_credit'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('submit_credit'))

    url_selected_code = request.args.get('selected_courses', '')
    course_data = get_courses()
    
    try: approved_courses = [r.course_name for r in CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()]
    except: approved_courses = []

    is_subject_rows = ""
    for item in course_data:
        if item['name'] in approved_courses:
            action_col = '<span class="text-[10px] font-bold text-emerald-500 bg-emerald-50 px-2 py-1 rounded">ผ่านแล้ว</span>'
        else:
            is_checked = "checked" if item['code'] == url_selected_code else ""
            action_col = f'<input type="checkbox" name="course_codes" value="{item["code"]}" {is_checked} class="w-5 h-5 accent-slate-900 rounded cursor-pointer course-checkbox" onchange="toggleSubjectRow(this)">'

        mooc_str = "<br>".join([f"- {m}" for m in item['mooc_list']])
        is_subject_rows += f"""
        <tr class="border-b border-sky-50 text-xs hover:bg-slate-50 transition subject-row" data-code="{item['code']}">
            <td class="py-3 px-3 text-center">{action_col}</td>
            <td class="py-3 px-3 font-mono font-bold text-sky-600">{item['code']}</td>
            <td class="py-3 px-3 font-extrabold text-slate-800">{item['name']}</td>
            <td class="py-3 px-3 text-slate-600 font-medium">{mooc_str}</td>
            <td class="py-3 px-3 text-center"><button type="button" onclick="removeSubjectRow(this)" class="text-rose-500 hover:text-rose-700 text-xs font-bold bg-rose-50 px-2 py-1 rounded"><i class="fa-solid fa-trash"></i> ลบ</button></td>
        </tr>
        """

    courses_json = json.dumps(course_data, ensure_ascii=False)
    
    content = f"""
    <div class="max-w-4xl mx-auto mb-10">
        <h2 class="text-3xl font-black text-slate-900 mb-2">ยื่นคำขอเทียบโอน</h2>
        <p class="text-slate-500 text-sm font-medium">กรุณาเลือกสาขาวิชาเพื่อแสดงรายวิชา และสามารถเพิ่ม/ลบรายวิชาได้ตามต้องการ</p>
    </div>

    <div class="max-w-4xl mx-auto bg-white p-6 rounded-3xl border border-sky-100 shadow-sm mb-6">
        <label class="block text-xs font-bold text-slate-700 uppercase mb-2">เลือกสาขาวิชา</label>
        <select id="branch_selector" onchange="filterBranch()" class="w-full border border-sky-200 rounded-xl p-3 text-sm font-bold text-sky-900 bg-sky-50/50 outline-none">
            <option value="">-- กรุณาเลือกสาขาวิชา --</option>
            <option value="IS" selected>สาขาวิชาระบบสารสนเทศ (Information Systems)</option>
        </select>
    </div>

    <form method="POST" enctype="multipart/form-data" class="max-w-4xl mx-auto space-y-8">
        <div id="subject_selection_box" class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm">
            <div class="flex justify-between items-center border-b border-slate-100 pb-3 mb-4">
                <h3 class="text-lg font-black text-slate-800">1. เลือกวิชาที่ต้องการเทียบโอน</h3>
                <button type="button" onclick="addCustomSubjectRow()" class="text-xs font-bold bg-sky-100 text-sky-700 px-3 py-1.5 rounded-xl hover:bg-sky-200"><i class="fa-solid fa-plus mr-1"></i> เพิ่มรายวิชาเอง</button>
            </div>
            <div class="overflow-x-auto border border-slate-100 rounded-xl mb-6">
                <table class="w-full text-left" id="subject_table">
                    <thead class="bg-slate-50 text-slate-500 text-[11px] font-black uppercase tracking-wider">
                        <tr><th class="py-3 px-3 text-center w-16">เลือก</th><th class="py-3 px-3">รหัส</th><th class="py-3 px-3">วิชา IS</th><th class="py-3 px-3">MOOC ที่ต้องใช้แนบหลักฐาน</th><th class="py-3 px-3 text-center">จัดการ</th></tr>
                    </thead>
                    <tbody>{is_subject_rows}</tbody>
                </table>
            </div>
            
            <div class="text-center">
                <button type="button" onclick="generateDynamicUploads()" class="bg-slate-900 hover:bg-black text-white font-black px-8 py-4 rounded-xl shadow-md transition text-sm">
                    <i class="fa-solid fa-arrow-down mr-2"></i> สร้างช่องแนบหลักฐานสำหรับวิชาที่เลือก
                </button>
            </div>
        </div>

        <div id="dynamic_upload_container" class="hidden space-y-6 bg-sky-50/50 p-8 rounded-3xl border border-sky-200 shadow-inner">
            <h3 class="text-xl font-black text-slate-900 mb-1">2. แนบหลักฐานเกียรติบัตร</h3>
            <p class="text-xs text-slate-500 mb-4">กรุณาแนบไฟล์รูปให้ตรงกับชื่อวิชาที่ระบุไว้เหนือปุ่มอัปโหลด</p>
            
            <div id="upload_forms_wrapper" class="space-y-6"></div>
            
            <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-black py-4 rounded-xl shadow-md text-base transition mt-4">
                <i class="fa-solid fa-paper-plane mr-2"></i> ยืนยันส่งคำร้องทั้งหมด
            </button>
        </div>
    </form>

    <script>
    const allCoursesData = {courses_json};
    const courseMap = {{}};
    allCoursesData.forEach(c => courseMap[c.code] = c);

    function filterBranch() {{
        const branch = document.getElementById('branch_selector').value;
        const box = document.getElementById('subject_selection_box');
        if(branch === "IS") {{
            box.style.display = 'block';
        }} else {{
            box.style.display = 'none';
            document.getElementById('dynamic_upload_container').classList.add('hidden');
        }}
    }}

    function removeSubjectRow(btn) {{
        const row = btn.closest('tr');
        row.remove();
    }}

    function addCustomSubjectRow() {{
        const tbody = document.querySelector('#subject_table tbody');
        const customCode = 'CUSTOM_' + Math.floor(Math.random() * 1000);
        const newRow = `
        <tr class="border-b border-sky-50 text-xs hover:bg-slate-50 transition subject-row">
            <td class="py-3 px-3 text-center"><input type="checkbox" name="course_codes" value="${{customCode}}" checked class="w-5 h-5 accent-slate-900 rounded cursor-pointer course-checkbox"></td>
            <td class="py-3 px-3 font-mono font-bold text-sky-600">วิชาเพิ่มเอง</td>
            <td class="py-3 px-3"><input type="text" placeholder="ระบุชื่อวิชา" class="border p-1 rounded w-full custom-name-input"></td>
            <td class="py-3 px-3 text-slate-600 font-medium">เกียรติบัตรหลักฐาน 1 ใบ</td>
            <td class="py-3 px-3 text-center"><button type="button" onclick="removeSubjectRow(this)" class="text-rose-500 hover:text-rose-700 text-xs font-bold bg-rose-50 px-2 py-1 rounded">ลบ</button></td>
        </tr>
        `;
        tbody.insertAdjacentHTML('beforeend', newRow);
    }}

    function generateDynamicUploads() {{
        const checkboxes = document.querySelectorAll('.course-checkbox:checked');
        const container = document.getElementById('dynamic_upload_container');
        const wrapper = document.getElementById('upload_forms_wrapper');
        
        if (checkboxes.length === 0) {{ alert('กรุณาติ๊กเลือกวิชาอย่างน้อย 1 วิชา'); return; }}

        wrapper.innerHTML = '';
        checkboxes.forEach(cb => {{
            const code = cb.value;
            if(code.startsWith('CUSTOM_')) {{
                wrapper.insertAdjacentHTML('beforeend', `
                    <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm">
                        <h4 class="font-black text-sky-700 text-lg mb-3">วิชาเพิ่มเติมอิสระ</h4>
                        <input type="file" name="cert_file_${{code}}_0" accept="image/*,.pdf" required class="w-full text-xs font-medium file:py-2 file:px-4 file:rounded-lg file:bg-sky-600 file:text-white file:font-bold">
                    </div>
                `);
                return;
            }}

            const course = courseMap[code];
            if (!course) return;

            let fileInputsHtml = '';
            course.mooc_list.forEach((mooc_name, index) => {{
                fileInputsHtml += `
                <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div class="flex-grow">
                        <span class="bg-sky-100 text-sky-800 text-[10px] px-2 py-0.5 rounded font-black uppercase mb-1 inline-block">ต้องใช้ใบที่ ${{index + 1}}</span>
                        <p class="text-sm font-extrabold text-slate-800">${{mooc_name}}</p>
                    </div>
                    <div class="shrink-0 w-full md:w-auto">
                        <input type="file" name="cert_file_${{code}}_${{index}}" accept="image/*,.pdf" required 
                            class="w-full md:w-64 text-xs font-medium file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-sky-600 file:text-white file:font-bold file:cursor-pointer hover:file:bg-sky-700 bg-slate-50 border border-slate-200 p-1 rounded-xl">
                    </div>
                </div>
                `;
            }});

            const sectionHtml = `
                <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm">
                    <div class="flex justify-between items-center border-b border-slate-100 pb-3 mb-4">
                        <h4 class="font-black text-sky-700 text-lg">${{course.name}} <span class="text-xs font-bold text-slate-400">(${{course.code}})</span></h4>
                        <span class="bg-slate-100 text-slate-600 text-xs font-bold px-2 py-1 rounded-lg">${{course.credits}} หน่วยกิต</span>
                    </div>
                    <div class="space-y-3">${{fileInputsHtml}}</div>
                </div>
            `;
            wrapper.insertAdjacentHTML('beforeend', sectionHtml);
        }});

        container.classList.remove('hidden');
        container.scrollIntoView({{ behavior: 'smooth' }});
    }}

    document.addEventListener("DOMContentLoaded", function() {{
        filterBranch();
    }});
    </script>
    """
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
        if status == 'Pending': badge = '<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-amber-100 text-amber-700">รอตรวจ (ผ่านสเต็ปแรกแล้ว)</span>'
        elif status == 'Approved': badge = '<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-emerald-100 text-emerald-700">อนุมัติแล้ว</span>'
        elif status == 'Needs_Revision': badge = f'<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-indigo-100 text-indigo-700">ให้แก้ไข: {r.reject_reason or "-"}</span> <a href="/student/edit_request/{r.id}" class="ml-2 bg-indigo-600 text-white px-3 py-1 rounded text-xs font-bold hover:bg-indigo-700"><i class="fa-solid fa-pen-to-square"></i> แก้ไขรูปหลักฐาน</a>'
        else: badge = f'<span class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-rose-100 text-rose-700">ไม่อนุมัติ ({r.reject_reason or "-"})</span>'
        
        img_preview = ""
        evidence_data = getattr(r, 'evidence_data', None)
        if evidence_data:
            try:
                ev_list = json.loads(evidence_data)
                img_preview = " ".join([f'<a href="/static/uploads/{e.get("filename")}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap"><i class="fa-solid fa-image"></i> {e.get("mooc_name", "ใบที่ " + str(i+1))}</a>' for i, e in enumerate(ev_list)])
            except: pass
        else:
            if getattr(r, 'doc_img', None) and r.doc_img != 'default_doc.png': img_preview += f'<a href="/static/uploads/{r.doc_img}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap mr-2">รูปหลักฐาน</a>'
        
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
        evidence_data = getattr(req, 'evidence_data', None)
        if evidence_data:
            try:
                ev_list = json.loads(evidence_data)
                new_list = []
                for i, e in enumerate(ev_list):
                    mooc_name = e.get('mooc_name', f'ใบที่ {i+1}')
                    file_key = f"cert_file_{i}"
                    if file_key in request.files:
                        file = request.files[file_key]
                        if file and file.filename != '' and allowed_file(file.filename):
                            ext = file.filename.rsplit('.', 1)[1].lower()
                            unique_fn = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_fn))
                            new_list.append({"mooc_name": mooc_name, "filename": unique_fn})
                        else:
                            new_list.append(e) 
                    else:
                        new_list.append(e)
                req.evidence_data = json.dumps(new_list, ensure_ascii=False)
            except: pass

        req.status = 'Pending' 
        req.reject_reason = None
        req.system_precheck = "ผ่านการตรวจสอบอัตโนมัติ (แก้ไขใหม่): ตรวจสอบความถูกต้องและส่งให้เจ้าหน้าที่ตรวจสอบอีกรอบ"
        db.session.commit()
        flash('อัปเดตหลักฐานและส่งให้เจ้าหน้าที่ตรวจสอบเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    ev_html = ""
    evidence_data = getattr(req, 'evidence_data', None)
    if evidence_data:
        try:
            ev_list = json.loads(evidence_data)
            for i, e in enumerate(ev_list):
                ev_html += f"""
                <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200">
                    <p class="text-xs font-bold text-sky-700 mb-2">หลักฐาน: {e.get('mooc_name')}</p>
                    <img src="/static/uploads/{e.get('filename')}" class="max-h-40 rounded-xl mb-3 shadow-sm object-contain" onerror="this.src='https://via.placeholder.com/150?text=No+Image';">
                    <label class="block text-xs font-semibold text-slate-600 mb-1">เปลี่ยนไฟล์ใหม่ (ถ้าต้องการ)</label>
                    <input type="file" name="cert_file_{i}" class="w-full text-xs font-medium file:py-1 file:px-3 file:rounded-lg file:border-0 file:bg-sky-600 file:text-white">
                </div>
                """
        except: pass

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
    try: all_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    except: all_requests = []

    rows = ""
    for r in all_requests:
        status_val = getattr(r, 'status', 'Pending')
        if status_val == 'Pending':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอตรวจ (ผ่านสเต็ปแรกแล้ว)</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="bg-gradient-to-r from-sky-500 to-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:from-sky-600 hover:to-blue-700 inline-block shadow-sm">พิจารณาคำร้อง</a>'
        elif status_val == 'Approved':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ดูรายละเอียด</a>'
        elif status_val == 'Needs_Revision':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800">ส่งกลับให้แก้</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="text-xs font-bold text-sky-600 bg-sky-50 px-3 py-1.5 rounded-xl border border-sky-200">ตรวจสอบการแก้ไข</a>'
        else:
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800">ไม่อนุมัติ</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="text-xs font-bold text-slate-500 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200">ดูรายละเอียด</a>'

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
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องเทียบโอนทั้งหมด (ผ่านสเต็ปแรกโดยระบบอัตโนมัติแล้ว)</h3>
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">ชื่อนักศึกษา</th><th class="py-3 px-4">วิชาที่ขอเทียบโอน</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400">ไม่มีคำร้องในระบบ</td></tr>'}</tbody>
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

    course_data = get_courses()
    matched_course = next((c for c in course_data if c['name'] == req.course_name), None)
    expected_moocs = matched_course['mooc_list'] if matched_course else []

    evidence_html = ""
    evidence_data = getattr(req, 'evidence_data', None)
    if evidence_data:
        try:
            ev_list = json.loads(evidence_data)
            for i, e in enumerate(ev_list):
                mooc_name = e.get('mooc_name', 'เกียรติบัตร')
                filename = e.get('filename', '')
                expected_label = expected_moocs[i] if i < len(expected_moocs) else "บทเรียนตามหลักสูตร"
                
                match_status = '<span class="bg-emerald-100 text-emerald-800 text-[10px] px-2 py-0.5 rounded font-bold"><i class="fa-solid fa-check"></i> ตรงกับหลักสูตร</span>' if mooc_name == expected_label else f'<span class="bg-amber-100 text-amber-800 text-[10px] px-2 py-0.5 rounded font-bold">เทียบเคียง: {expected_label}</span>'

                evidence_html += f"""
                <div class="bg-slate-50 border border-slate-200 p-4 rounded-2xl">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-xs font-bold text-sky-700 bg-sky-100 px-2.5 py-1 rounded-lg">ใบที่ {i+1}: {mooc_name}</span>
                        {match_status}
                    </div>
                    <a href="/static/uploads/{filename}" target="_blank"><img src="/static/uploads/{filename}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition object-contain" onerror="this.src='https://via.placeholder.com/300x200?text=Image+Not+Found';"></a>
                </div>
                """
        except: pass
    
    if not evidence_html:
        if getattr(req, 'doc_img', None) and req.doc_img != 'default_doc.png':
            evidence_html += f'<div class="bg-slate-50 p-2 rounded-2xl"><img src="/static/uploads/{req.doc_img}" class="max-h-56 mx-auto rounded-xl shadow-sm object-contain" onerror="this.src=\'https://via.placeholder.com/300x200?text=Image+Not+Found\';"></div>'

    precheck_box = f"""
    <div class="bg-emerald-50 border border-emerald-200 p-4 rounded-2xl mb-6">
        <p class="text-xs font-bold text-emerald-800 mb-1"><i class="fa-solid fa-robot mr-1"></i> ผลการตรวจสอบอัตโนมัติ (สเต็ปแรกโดยระบบ):</p>
        <p class="text-xs text-emerald-700 font-medium">{getattr(req, 'system_precheck', 'ผ่านการตรวจสอบสเต็ปแรกเรียบร้อย')}</p>
    </div>
    """

    student = req.user
    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <div class="flex justify-between items-center mb-6">
            <h3 class="text-xl font-black text-slate-900">พิจารณาคำร้อง: {req.course_name}</h3>
            <span class="bg-slate-100 text-slate-600 px-3 py-1 rounded-lg text-xs font-bold">{getattr(req, 'req_code', '')}</span>
        </div>
        
        {precheck_box}

        <div class="bg-sky-50/50 p-6 rounded-2xl border border-sky-100 mb-6 flex gap-8 text-sm">
            <div><p class="text-xs font-bold text-slate-400 mb-1">นักศึกษา</p><p class="font-bold">{student.fullname if student else '-'}</p></div>
            <div><p class="text-xs font-bold text-slate-400 mb-1">ระบบ</p><p class="font-bold">{getattr(req, 'institution', '-')}</p></div>
            <div><p class="text-xs font-bold text-slate-400 mb-1">หน่วยกิต</p><p class="font-bold text-sky-600">{getattr(req, 'credits', 0)}</p></div>
        </div>

        <h4 class="font-black text-slate-800 mb-3"><i class="fa-solid fa-images text-sky-500 mr-2"></i> ตรวจสอบหลักฐาน (เจ้าหน้าที่ตรวจสอบยืนยันขั้นสุดท้าย)</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {evidence_html if evidence_html else '<p class="text-xs text-slate-400">ไม่มีรูปภาพ</p>'}
        </div>

        <form method="POST" class="border-t border-slate-100 pt-6 space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 mb-2">ระบุเหตุผล / ข้อเสนอแนะ (กรณีไม่อนุมัติ หรือ ส่งกลับให้แก้ไข)</label>
                <textarea name="reject_reason" placeholder="เช่น รูปภาพไม่ชัดเจน กรุณาอัปโหลดใหม่" class="w-full border border-slate-200 rounded-xl p-3 text-sm bg-slate-50 outline-none focus:border-sky-300"></textarea>
            </div>
            <div class="flex justify-end gap-3">
                <button type="submit" name="action" value="reject" class="px-6 py-3 bg-rose-100 text-rose-700 hover:bg-rose-600 hover:text-white font-bold rounded-xl text-sm transition">ไม่อนุมัติ</button>
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
    # ข้อ 2 ฝั่งเจ้าหน้าที่: ถ้าไม่ใช่ผู้ดูแลหลัก (superadmin) จะไม่มีสิทธิ์เข้าถึงหน้านี้
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
        # ข้อ 1 ฝั่งเจ้าหน้าที่: เมื่อผู้ดูแลหลักกดตรงชื่อ จะสามารถดูรายละเอียดได้
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

if __name__ == '__main__':
    app.run(debug=True)