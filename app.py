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

# เชื่อมต่อ PostgreSQL บน Render หรือ SQLite
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

# ==========================================
# Database Models
# ==========================================
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
    doc_img = db.Column(db.String(200), nullable=True) # ของเดิม
    doc_img2 = db.Column(db.String(200), nullable=True) # ของเดิม
    evidence_data = db.Column(db.Text, nullable=True) # ระบบใหม่: เก็บ JSON Array [{mooc_name, filename}]
    status = db.Column(db.String(20), default='Pending') 
    reject_reason = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    user = db.relationship('User', backref=db.backref('credits_list', lazy=True))

class ProfileEditRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    new_prefix = db.Column(db.String(20))
    new_fullname = db.Column(db.String(100))
    new_phone = db.Column(db.String(20))
    new_email = db.Column(db.String(100))
    new_address = db.Column(db.Text)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    approved_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.String(20), default="2026-08-26")
    user = db.relationship('User', backref=db.backref('edit_requests', lazy=True))

# ==========================================
# Database Auto-Reset & Migration
# ==========================================
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS evidence_data TEXT;"))
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

# ==========================================
# Google Sheets Integration
# ==========================================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/180MQL9RadQfhO0uN-L3hQGYiRhDPYvzJ/export?format=csv"
IS_THAIMOOC_COURSES = [{"code": "15-02-002", "name": "คุณภาพการใช้ชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ชีวิตและการสร้างคุณค่า (2 ชม.)", "การคิดสร้างสรรค์ เพื่อการพัฒนาตนเอง (2 ชม.)"], "hours": "4 ชม.", "credits": 3}]

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
                courses_dict[current_code] = {"code": current_code, "name": name, "group": group, "provider": provider if provider else "ThaiMOOC", "credits": credits_val, "mooc_list": [], "total_hours": 0.0}
            else:
                if not courses_dict[current_code]["name"] and name: courses_dict[current_code]["name"] = name
                if not courses_dict[current_code]["group"] and group: courses_dict[current_code]["group"] = group
                if not courses_dict[current_code]["provider"] and provider: courses_dict[current_code]["provider"] = provider

            if mooc_name or hours_raw:
                nums = re.findall(r'\d+(?:\.\d+)?', hours_raw)
                if nums: courses_dict[current_code]["total_hours"] += float(nums[0])
                display_mooc = mooc_name
                if hours_raw and hours_raw not in mooc_name:
                    if nums and hours_raw == nums[0]: display_mooc += f" ({hours_raw} ชม.)" 
                    else: display_mooc += f" ({hours_raw})"
                for m in display_mooc.split('\n'):
                    if m.strip(): courses_dict[current_code]["mooc_list"].append(m.strip())

        courses = []
        for data in courses_dict.values():
            th = data["total_hours"]
            if th > 0: data["hours"] = f"{int(th) if th.is_integer() else round(th, 2)} ชม."
            else: data["hours"] = "ไม่ระบุ"
            courses.append(data)
        if courses: return courses
        return IS_THAIMOOC_COURSES
    except Exception:
        return IS_THAIMOOC_COURSES

# ==========================================
# Layout Template
# ==========================================
def render_layout(content, active_page=''):
    def is_active(page_name):
        return "bg-sky-200 text-sky-900 font-extrabold shadow-sm border border-sky-300" if active_page == page_name else "text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 font-medium"

    messages = get_flashed_messages(with_categories=True)
    flash_html = "".join([f'<div class="p-4 mb-4 text-sm rounded-2xl font-semibold shadow-sm flex items-center justify-between border transition-all {"bg-rose-50 text-rose-700 border-rose-200" if category in ["error", "danger"] else "bg-emerald-50 text-emerald-800 border-emerald-200"}"><div class="flex items-center gap-2"><i class="fa-solid {"fa-circle-exclamation text-rose-500" if category in ["error", "danger"] else "fa-circle-check text-emerald-500"} text-lg"></i><span>{message}</span></div><button onclick="this.parentElement.remove()" class="text-xs font-bold px-2 py-1 hover:bg-black/5 rounded-lg">✕</button></div>' for category, message in messages]) if messages else ""

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
            <a href="/" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('home')}"><i class="fa-solid fa-house text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">แดชบอร์ด</span></a>

            {f'''
                {f"""
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/students" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('admin_students')}"><i class="fa-solid fa-users text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">รายชื่อนักศึกษา</span></a>
                    <a href="/admin/requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('admin_requests')}"><i class="fa-solid fa-file-signature text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ตรวจสอบคำร้อง</span></a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">โครงสร้างหลักสูตร</span></a>
                    <a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group mt-2 {is_active('manage_admins')}"><i class="fa-solid fa-user-shield text-lg w-6 text-center text-sky-600"></i><span class="nav-text font-bold">จัดการเจ้าหน้าที่</span></a>
                """ if session.get('role') in ['admin', 'superadmin'] else f"""
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('available_courses')}"><i class="fa-solid fa-magnifying-glass text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ค้นหารายวิชา (Search)</span></a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('all_courses')}"><i class="fa-solid fa-table-list text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หลักสูตรทั้งหมด (Table)</span></a>
                    <a href="/submit_credit" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('submit_credit')}"><i class="fa-solid fa-file-circle-plus text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ยื่นคำขอเทียบโอน</span></a>
                    <a href="/credits" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('credits')}"><i class="fa-solid fa-graduation-cap text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">หน่วยกิตสะสม</span></a>
                    <a href="/history" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl transition-all text-sm group {is_active('history')}"><i class="fa-solid fa-clock-rotate-left text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text">ติดตามสถานะคำขอ</span></a>
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

# ==========================================
# Routes & Controllers
# ==========================================
@app.route('/')
def home():
    if not session.get('user_id'): return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    # ---------------- ADMIN DASHBOARD (กลับไปเป็นแบบกล่องเรียบง่าย) ----------------
    if user.role in ['admin', 'superadmin']:
        try:
            pending_reqs = CreditRequest.query.filter_by(status='Pending').order_by(CreditRequest.id.asc()).all()
            pending_count = len(pending_reqs)
            total_students = User.query.filter_by(role='student').count()
            total_approved_credits = sum(r.credits for r in CreditRequest.query.filter_by(status='Approved').all())
        except:
            pending_reqs, pending_count, total_students, total_approved_credits = [], 0, 0, 0

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

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h3 class="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">คำร้องล่าสุดที่รอตรวจสอบ</h3>
                <div>{urgent_rows}</div>
                <div class="mt-4 text-center"><a href="/admin/requests" class="text-sm font-bold text-sky-600 hover:underline">ดูคำร้องทั้งหมด</a></div>
            </div>
            <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h3 class="text-lg font-bold text-slate-800 mb-4 border-b border-slate-100 pb-2">เมนูด่วน</h3>
                <div class="flex flex-col gap-3">
                    <a href="/admin/students" class="p-4 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-200 transition font-bold text-slate-700"><i class="fa-solid fa-users mr-2 text-sky-500"></i> จัดการรายชื่อนักศึกษา</a>
                    <a href="/all_courses" class="p-4 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-200 transition font-bold text-slate-700"><i class="fa-solid fa-table-list mr-2 text-sky-500"></i> ดูโครงสร้างหลักสูตรทั้งหมด</a>
                </div>
            </div>
        </div>
        """
        return render_layout(content, active_page='home')

    # ---------------- STUDENT DASHBOARD (กลับไปเป็นแบบกล่องเรียบง่าย) ----------------
    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
        approved_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') == 'Approved')
        pending_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') in ['Pending', 'Needs_Revision'])
    except:
        user_requests, approved_credits, pending_credits = [], 0, 0

    history_rows = ""
    for r in sorted(user_requests, key=lambda x: x.id, reverse=True)[:5]:
        status = getattr(r, 'status', 'Pending')
        if status == 'Approved': badge = '<span class="px-2 py-1 rounded bg-emerald-100 text-emerald-700 text-xs font-bold">อนุมัติแล้ว</span>'
        elif status == 'Pending': badge = '<span class="px-2 py-1 rounded bg-amber-100 text-amber-700 text-xs font-bold">รอตรวจ</span>'
        elif status == 'Needs_Revision': badge = '<span class="px-2 py-1 rounded bg-indigo-100 text-indigo-700 text-xs font-bold">แก้ไขข้อมูล</span>'
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

    <div class="bg-white p-6 md:p-8 rounded-2xl shadow-sm border border-slate-200">
        <div class="flex justify-between items-center border-b border-slate-100 pb-3 mb-3">
            <h3 class="text-lg font-bold text-slate-800">ประวัติการยื่นคำขอล่าสุด</h3>
            <a href="/history" class="text-sm text-sky-600 font-bold hover:underline">ดูประวัติทั้งหมด</a>
        </div>
        <div>{history_rows}</div>
        <div class="mt-6 text-center">
            <a href="/submit_credit" class="inline-block bg-slate-900 hover:bg-black text-white px-6 py-3 rounded-xl font-bold transition">ยื่นคำขอเทียบโอนใหม่</a>
        </div>
    </div>
    """
    return render_layout(content, active_page='home')

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))
    course_data = get_courses()
    search_query = request.args.get('search', '').strip().lower()
    selected_provider = request.args.get('provider', '').strip()

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
        mooc_items = "".join([f'<li class="flex items-start gap-2 mb-1.5 text-xs text-slate-600"><i class="fa-solid fa-check text-sky-400 mt-0.5"></i> <span>{m}</span></li>' for m in c['mooc_list']])
        
        if c['name'] in approved_courses:
            btn = '<div class="text-center w-full bg-emerald-50 text-emerald-600 font-bold py-2.5 rounded-xl text-xs border border-emerald-200"><i class="fa-solid fa-check-circle"></i> เทียบโอนแล้ว</div>'
        elif session.get('role') not in ['admin', 'superadmin']:
            btn = f'<a href="/submit_credit?selected_courses={c["code"]}" class="block text-center w-full bg-slate-900 hover:bg-black text-white font-bold py-2.5 rounded-xl text-xs transition">เลือกวิชานี้</a>'
        else: btn = ''

        cards += f"""
        <div class="bg-white rounded-3xl border border-sky-100 p-6 shadow-sm hover:shadow-md transition card-hover flex flex-col h-full">
            <div class="flex justify-between items-start mb-4">
                <span class="font-mono text-[10px] font-black bg-slate-100 text-slate-500 px-2.5 py-1 rounded-lg tracking-widest">{c['code']}</span>
                <span class="px-2.5 py-1 rounded-lg text-[10px] font-black border {badge_prov} uppercase">{c['provider']}</span>
            </div>
            <h3 class="text-lg font-black text-slate-900 leading-snug mb-4">{c['name']}</h3>
            <div class="mb-5 flex-grow">
                <p class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">ต้องเรียนออนไลน์ ({len(c['mooc_list'])} ใบ)</p>
                <ul class="font-medium">{mooc_items}</ul>
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

    content = f"""
    <div class="mb-10 text-center max-w-2xl mx-auto">
        <h2 class="text-3xl font-black text-slate-900 mb-3">ค้นหารายวิชาเทียบโอน</h2>
        <p class="text-slate-500 text-sm font-medium">พิมพ์ชื่อรายวิชา รหัสวิชา หรือชื่อบทเรียนย่อยที่ต้องการค้นหาได้เลย</p>
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

    <div class="flex justify-between items-center mb-6 px-2">
        <h3 class="font-bold text-slate-700 text-sm">ผลการค้นหา: พบ <span class="text-sky-600">{len(filtered_courses)}</span> รายการ</h3>
        <a href="/all_courses" class="text-xs font-bold text-sky-600 hover:underline"><i class="fa-solid fa-list mr-1"></i> ดูแบบตาราง (List View)</a>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-full py-20 text-center bg-white rounded-3xl border border-dashed border-sky-200"><i class="fa-regular fa-face-frown-open text-4xl text-slate-300 mb-3 block"></i><p class="text-slate-500 font-bold">ไม่พบวิชาที่ค้นหา ลองเปลี่ยนคำค้นหาดูนะครับ</p></div>'}
    </div>
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
        mooc_str = "<br>".join([f"- {m}" for m in c['mooc_list']])
        prov_badge = f'<span class="px-2 py-0.5 rounded text-[10px] font-bold {"bg-sky-100 text-sky-700" if c["provider"] == "ThaiMOOC" else "bg-amber-100 text-amber-700"} border border-slate-100">{c["provider"]}</span>'
        
        if c['name'] in approved_courses: btn = '<span class="text-[10px] font-bold text-emerald-600"><i class="fa-solid fa-check mr-1"></i>โอนแล้ว</span>'
        else: btn = f'<a href="/submit_credit?selected_courses={c["code"]}" class="text-[11px] font-bold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-sky-600 transition shadow-sm whitespace-nowrap">เลือกเทียบโอน</a>'

        rows += f"""
        <tr class="border-b border-slate-100 hover:bg-slate-50 text-xs">
            <td class="py-3 px-4 font-mono font-bold text-slate-400">{idx}</td>
            <td class="py-3 px-4 font-mono font-bold text-sky-700">{c['code']}</td>
            <td class="py-3 px-4 font-extrabold text-slate-800">{c['name']}<br><span class="text-[10px] text-slate-400 font-medium">{c['group']}</span></td>
            <td class="py-3 px-4">{prov_badge}</td>
            <td class="py-3 px-4 font-medium text-slate-600 leading-relaxed">{mooc_str}</td>
            <td class="py-3 px-4 text-center font-black text-slate-800">{c['credits']}</td>
            <td class="py-3 px-4 text-center">{btn if session.get('role') not in ['admin', 'superadmin'] else '-'}</td>
        </tr>
        """

    content = f"""
    <div class="mb-6 flex justify-between items-end">
        <div>
            <h2 class="text-2xl font-black text-slate-900">ตารางโครงสร้างหลักสูตร (Table View)</h2>
            <p class="text-slate-500 text-sm font-medium mt-1">แสดงรายวิชาทั้งหมดที่รองรับการเทียบโอนในระบบธนาคารหน่วยกิต</p>
        </div>
        <a href="/available_courses" class="text-xs font-bold bg-white border border-sky-200 text-sky-600 px-4 py-2 rounded-xl hover:bg-sky-50 shadow-sm"><i class="fa-solid fa-magnifying-glass mr-1"></i> กลับไปหน้าค้นหา (Grid)</a>
    </div>

    <div class="bg-white rounded-3xl border border-sky-100 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left min-w-[900px]">
                <thead class="bg-slate-50 border-b border-slate-200 text-[11px] font-black text-slate-500 uppercase tracking-wider">
                    <tr><th class="py-4 px-4 w-10">#</th><th class="py-4 px-4">รหัสวิชา</th><th class="py-4 px-4">ชื่อวิชาหลักสูตร IS</th><th class="py-4 px-4">ระบบ</th><th class="py-4 px-4">ใบเกียรติบัตรย่อยที่ต้องใช้</th><th class="py-4 px-4 text-center">หน่วยกิต</th><th class="py-4 px-4 text-center">จัดการ</th></tr>
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
                
                # วิชานอกหลักสูตร
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
                    
                    req = CreditRequest(
                        req_code=req_code, user_id=session['user_id'], course_name=course_name, 
                        institution=request.form.get('institution', 'ThaiMOOC'), credits=int(request.form.get('credits', 3)), 
                        category=request.form.get('category', 'หมวดวิชาเลือก'),
                        date_submitted=datetime.now().strftime("%Y-%m-%d"),
                        evidence_data=json.dumps(evidence_list, ensure_ascii=False), status='Pending'
                    )
                    db.session.add(req)
                    success_count += 1

                # วิชาในระบบ
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

                    req = CreditRequest(
                        req_code=req_code, user_id=session['user_id'], course_name=matched_course['name'], 
                        institution=matched_course['provider'], credits=matched_course['credits'], 
                        category=matched_course['group'], date_submitted=datetime.now().strftime("%Y-%m-%d"),
                        evidence_data=json.dumps(evidence_list, ensure_ascii=False), status='Pending'
                    )
                    db.session.add(req)
                    success_count += 1

            db.session.commit()
            if success_count > 0:
                flash(f'ยื่นคำขอสำเร็จ {success_count} รายวิชา (รอเจ้าหน้าที่ตรวจสอบ)', 'success')
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
            action_col = f'<input type="checkbox" name="course_codes" value="{item["code"]}" {is_checked} class="w-5 h-5 accent-slate-900 rounded cursor-pointer course-checkbox">'

        mooc_str = "<br>".join([f"- {m}" for m in item['mooc_list']])
        is_subject_rows += f"""
        <tr class="border-b border-sky-50 text-xs hover:bg-slate-50 transition">
            <td class="py-3 px-3 text-center">{action_col}</td>
            <td class="py-3 px-3 font-mono font-bold text-sky-600">{item['code']}</td>
            <td class="py-3 px-3 font-extrabold text-slate-800">{item['name']}</td>
            <td class="py-3 px-3 text-slate-600 font-medium">{mooc_str}</td>
        </tr>
        """

    courses_json = json.dumps(course_data, ensure_ascii=False)
    
    content = f"""
    <div class="max-w-4xl mx-auto mb-10">
        <h2 class="text-3xl font-black text-slate-900 mb-2">ยื่นคำขอเทียบโอน</h2>
        <p class="text-slate-500 text-sm font-medium">เลือกระบบวิชาที่ต้องการ และระบบจะสร้างช่องอัปโหลดเกียรติบัตรให้ตรงกับวิชานั้นๆ โดยอัตโนมัติ</p>
    </div>

    <form method="POST" enctype="multipart/form-data" class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm">
            <h3 class="text-lg font-black text-slate-800 mb-4 border-b border-slate-100 pb-3">1. เลือกวิชาที่ต้องการเทียบโอน</h3>
            <div class="overflow-x-auto border border-slate-100 rounded-xl mb-6">
                <table class="w-full text-left">
                    <thead class="bg-slate-50 text-slate-500 text-[11px] font-black uppercase tracking-wider">
                        <tr><th class="py-3 px-3 text-center w-16">เลือก</th><th class="py-3 px-3">รหัส</th><th class="py-3 px-3">วิชา IS</th><th class="py-3 px-3">MOOC ที่ต้องใช้แนบหลักฐาน</th></tr>
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

    <div class="max-w-4xl mx-auto mt-12 mb-12 border-t border-slate-200 pt-10">
        <div class="bg-amber-50 p-8 rounded-3xl border border-amber-200">
            <h3 class="text-lg font-black text-amber-900 mb-2">กรณีพิเศษ: วิชานอกหลักสูตร</h3>
            <p class="text-xs text-amber-700 mb-6">หากไม่พบวิชาในตาราง สามารถกรอกข้อมูลเองและแนบไฟล์ได้ที่นี่</p>
            <form method="POST" enctype="multipart/form-data" class="space-y-4">
                <input type="hidden" name="course_codes" value="MANUAL_CUSTOM">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label class="block text-xs font-bold text-amber-900 mb-1.5">ชื่อวิชา</label><input type="text" name="manual_course_name" class="w-full rounded-xl p-3 text-sm border border-amber-200 bg-white" required></div>
                    <div class="grid grid-cols-2 gap-2">
                        <div><label class="block text-xs font-bold text-amber-900 mb-1.5">ระบบ</label><select name="institution" class="w-full rounded-xl p-3 text-sm border border-amber-200"><option>ThaiMOOC</option><option>ChulaMOOC</option></select></div>
                        <div><label class="block text-xs font-bold text-amber-900 mb-1.5">หน่วยกิต</label><input type="number" name="credits" value="3" class="w-full rounded-xl p-3 text-sm border border-amber-200"></div>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                    <div><label class="block text-xs font-bold text-amber-900 mb-1.5">เกียรติบัตรใบที่ 1 *</label><input type="file" name="cert_file_MANUAL_1" required class="w-full text-xs font-medium file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-200 file:text-amber-900"></div>
                    <div><label class="block text-xs font-bold text-amber-900 mb-1.5">เกียรติบัตรใบที่ 2 (ถ้ามี)</label><input type="file" name="cert_file_MANUAL_2" class="w-full text-xs font-medium file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-200 file:text-amber-900"></div>
                    <div><label class="block text-xs font-bold text-amber-900 mb-1.5">เกียรติบัตรใบที่ 3 (ถ้ามี)</label><input type="file" name="cert_file_MANUAL_3" class="w-full text-xs font-medium file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-amber-200 file:text-amber-900"></div>
                </div>
                <button type="submit" class="bg-amber-600 text-white font-bold px-6 py-3 rounded-xl text-sm shadow-sm hover:bg-amber-700">ส่งวิชากรณีพิเศษ</button>
            </form>
        </div>
    </div>

    <script>
    const allCoursesData = {courses_json};
    const courseMap = {{}};
    allCoursesData.forEach(c => courseMap[c.code] = c);

    function generateDynamicUploads() {{
        const checkboxes = document.querySelectorAll('.course-checkbox:checked');
        const container = document.getElementById('dynamic_upload_container');
        const wrapper = document.getElementById('upload_forms_wrapper');
        
        if (checkboxes.length === 0) {{ alert('กรุณาติ๊กเลือกวิชาด้านบนก่อนครับ'); return; }}

        wrapper.innerHTML = '';
        checkboxes.forEach(cb => {{
            const code = cb.value;
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
        if(document.querySelectorAll('.course-checkbox:checked').length > 0) {{
            generateDynamicUploads();
        }}
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
        if status == 'Pending': badge = '<span class="px-2 py-1 rounded-lg text-[10px] font-bold bg-amber-100 text-amber-700">รอตรวจ</span>'
        elif status == 'Approved': badge = '<span class="px-2 py-1 rounded-lg text-[10px] font-bold bg-emerald-100 text-emerald-700">อนุมัติแล้ว</span>'
        elif status == 'Needs_Revision': badge = '<span class="px-2 py-1 rounded-lg text-[10px] font-bold bg-indigo-100 text-indigo-700">รอแก้ไข</span>'
        else: badge = '<span class="px-2 py-1 rounded-lg text-[10px] font-bold bg-rose-100 text-rose-700">ไม่อนุมัติ</span>'
        
        img_preview = ""
        evidence_data = getattr(r, 'evidence_data', None)
        if evidence_data:
            try:
                ev_list = json.loads(evidence_data)
                img_preview = " ".join([f'<a href="/static/uploads/{e.get("filename")}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap"><i class="fa-solid fa-image"></i> ใบที่ {i+1}</a>' for i, e in enumerate(ev_list)])
            except: pass
        else:
            if getattr(r, 'doc_img', None) and r.doc_img != 'default_doc.png': img_preview += f'<a href="/static/uploads/{r.doc_img}" target="_blank" class="text-[10px] text-sky-600 underline font-bold whitespace-nowrap mr-2">รูป 1</a>'
        
        if not img_preview: img_preview = '<span class="text-[10px] text-slate-400">ไม่มีรูป</span>'

        rows += f"""
        <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-400">{getattr(r, 'req_code', '-')}</td>
            <td class="py-4 px-4 font-extrabold text-slate-800">{getattr(r, 'course_name', '-')}<div class="mt-1 flex gap-2">{img_preview}</div></td>
            <td class="py-4 px-4 font-bold text-sky-600 text-center">{getattr(r, 'credits', 0)}</td>
            <td class="py-4 px-4 text-center">{badge}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto max-w-5xl mx-auto">
        <h3 class="text-2xl font-black text-slate-900 mb-6">ประวัติคำร้อง</h3>
        <table class="w-full text-left min-w-[500px]">
            <thead class="bg-slate-50 text-[11px] font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                <tr><th class="py-3 px-4">รหัส</th><th class="py-3 px-4">วิชาที่ขอ / รูปหลักฐาน</th><th class="py-3 px-4 text-center">หน่วยกิต</th><th class="py-3 px-4 text-center">สถานะ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-12 text-center text-slate-400">ไม่มีประวัติ</td></tr>'}</tbody>
        </table>
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
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอการพิจารณา</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="bg-gradient-to-r from-sky-500 to-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:from-sky-600 hover:to-blue-700 inline-block shadow-sm">พิจารณาคำร้อง</a>'
        elif status_val == 'Approved':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200">พิจารณาแล้ว</span>'
        else:
            status_badge = f'<span class="px-3 py-1 rounded-full text-xs font-bold {"bg-indigo-100 text-indigo-800" if status_val=="Needs_Revision" else "bg-rose-100 text-rose-800"}">{"ส่งกลับให้แก้" if status_val=="Needs_Revision" else "ไม่อนุมัติ"}</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200">สิ้นสุดคำร้อง</span>'

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
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องเทียบโอนทั้งหมด (สาขาวิชาระบบสารสนเทศ)</h3>
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
            return redirect(url_for('home'))
        elif action == 'reject':
            req.status = 'Rejected'
            req.reject_reason = request.form.get('reject_reason', '-')
            req.approved_by = admin_user.fullname
            db.session.commit()
            flash('ปฏิเสธคำร้องเรียบร้อย', 'success')
            return redirect(url_for('home'))

    evidence_html = ""
    evidence_data = getattr(req, 'evidence_data', None)
    
    if evidence_data:
        try:
            ev_list = json.loads(evidence_data)
            for e in ev_list:
                mooc_name = e.get('mooc_name', 'เกียรติบัตร')
                filename = e.get('filename', '')
                evidence_html += f"""
                <div class="bg-slate-50 border border-slate-200 p-3 rounded-2xl text-center">
                    <p class="text-xs font-bold text-sky-700 bg-sky-100 px-2 py-1 rounded-lg mb-2 inline-block">ตรงกับ: {mooc_name}</p>
                    <a href="/static/uploads/{filename}" target="_blank"><img src="/static/uploads/{filename}" class="max-h-56 mx-auto rounded-xl shadow-sm hover:scale-105 transition"></a>
                </div>
                """
        except: pass
    
    if not evidence_html:
        if getattr(req, 'doc_img', None) and req.doc_img != 'default_doc.png':
            evidence_html += f'<div class="bg-slate-50 p-2 rounded-2xl"><img src="/static/uploads/{req.doc_img}" class="max-h-56 mx-auto rounded-xl shadow-sm"></div>'

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

        <h4 class="font-black text-slate-800 mb-3"><i class="fa-solid fa-images text-sky-500 mr-2"></i> หลักฐานที่นักศึกษาแนบมา</h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {evidence_html if evidence_html else '<p class="text-xs text-slate-400">ไม่มีรูปภาพ</p>'}
        </div>

        <form method="POST" class="border-t border-slate-100 pt-6">
            <label class="block text-xs font-bold text-rose-600 mb-2">ระบุเหตุผล (ถ้าไม่อนุมัติ)</label>
            <textarea name="reject_reason" class="w-full border border-slate-200 rounded-xl p-3 text-sm mb-4 bg-slate-50 outline-none focus:border-rose-300"></textarea>
            <div class="flex justify-end gap-3">
                <button type="submit" name="action" value="reject" class="px-6 py-3 bg-rose-100 text-rose-700 hover:bg-rose-600 hover:text-white font-bold rounded-xl text-sm transition">ไม่อนุมัติ</button>
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
        if new_addr:
            user.address = new_addr
        
        db.session.commit()
        flash('✅ บันทึกข้อมูลส่วนตัวและที่อยู่เรียบร้อยแล้ว', 'success')
        return redirect(url_for('profile'))

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">แก้ไขข้อมูลส่วนตัวและที่อยู่</h3>
        <p class="text-xs text-slate-500 mb-6">คุณสามารถแก้ไขข้อมูลเบื้องต้นและที่อยู่แล้วบันทึกเข้าระบบได้ทันที</p>
        
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้า</label>
                <select name="prefix" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50">
                    <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                    <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                    <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                </select></div>
                <div class="col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล</label><input type="text" name="fullname" value="{user.fullname}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมล</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>

            <div class="border-t border-sky-100 pt-4">
                <label class="block text-xs font-bold text-sky-700 uppercase tracking-wider mb-3"><i class="fa-solid fa-house-user mr-1 text-sky-400"></i> แก้ไขข้อมูลที่อยู่</label>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">บ้านเลขที่</label><input type="text" name="house_no" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">หมู่ที่</label><input type="text" name="moo" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ซอย / ถนน</label><input type="text" name="soi" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ตำบล/แขวง</label><input type="text" name="subdistrict" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">อำเภอ/เขต</label><input type="text" name="district" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">จังหวัด</label><input type="text" name="province" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">รหัสไปรษณีย์</label><input type="text" name="postal_code" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                </div>
            </div>

            <div class="pt-4 flex gap-3">
                <a href="/profile" class="w-1/3 bg-slate-100 hover:bg-slate-200 text-slate-700 text-center font-bold py-3.5 rounded-2xl shadow-sm text-sm transition">ยกเลิก</a>
                <button type="submit" class="w-2/3 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm transition">บันทึกการเปลี่ยนแปลง</button>
            </div>
        </form>
    </div>
    """
    return render_layout(content, active_page='profile')

@app.route('/admin/students')
def admin_students():
    if session.get('role') not in ['admin', 'superadmin']:
        return redirect(url_for('login'))
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
            <td class="py-4 px-4 text-xs text-slate-600 font-medium leading-relaxed"><i class="fa-solid fa-phone text-slate-400 mr-1"></i>{s.phone or '-'}<br><i class="fa-solid fa-envelope text-slate-400 mr-1"></i>{s.email or '-'}</td>
            <td class="py-4 px-4 text-xs text-slate-600 max-w-xs leading-relaxed">{s.address or '-'}</td>
            <td class="py-4 px-4 font-black text-center"><span class="bg-sky-50 text-sky-700 px-3 py-1 rounded-full text-xs font-bold border border-sky-100">{approved_credits} หน่วยกิต</span></td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6"><i class="fa-solid fa-users text-sky-500 mr-2"></i>รายชื่อนักศึกษาสาขาวิชาระบบสารสนเทศ</h3>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสนักศึกษา / บัตรประชาชน</th><th class="py-3 px-4">ชื่อ-นามสกุล / สาขา</th><th class="py-3 px-4">ข้อมูลติดต่อ</th><th class="py-3 px-4">ที่อยู่</th><th class="py-3 px-4 text-center">หน่วยกิตสะสม</th></tr>
            </thead>
            <tbody class="divide-y divide-sky-50">{rows if rows else '<tr><td colspan="5" class="py-12 text-center text-slate-400">ยังไม่มีนักศึกษาลงทะเบียนในระบบ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_layout(content, active_page='admin_students')

@app.route('/admin/manage_admins', methods=['GET', 'POST'])
def manage_admins():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('home'))
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        id_card = request.form.get('id_card', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if User.query.filter_by(id_card=id_card).first():
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนในระบบแล้ว', 'error')
            return redirect(url_for('manage_admins'))

        new_admin = User(member_id=f"ADM{uuid.uuid4().hex[:3].upper()}", prefix="เจ้าหน้าที่", fullname=fullname, id_card=id_card, username=id_card, password=generate_password_hash(password), email=email, phone=phone, role='admin')
        db.session.add(new_admin)
        db.session.commit()
        flash(f'เพิ่มเจ้าหน้าที่ "{fullname}" เรียบร้อยแล้ว', 'success')
        return redirect(url_for('manage_admins'))

    admin_list = User.query.filter(User.role.in_(['admin', 'superadmin'])).all()
    rows = ""
    for a in admin_list:
        role_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-sky-100 text-sky-800 border border-sky-200">ผู้ดูแลหลัก</span>' if a.role == 'superadmin' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">เจ้าหน้าที่</span>'
        rows += f'<tr class="border-b border-sky-50 text-sm"><td class="py-4 px-4 font-bold text-slate-900">{a.fullname}</td><td class="py-4 px-4">{role_badge}</td></tr>'

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
            <h3 class="text-xl font-black text-slate-900 mb-6">เพิ่มบัญชีเจ้าหน้าที่</h3>
            <form method="POST" class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="block text-xs font-bold text-slate-700">ชื่อ-นามสกุล <span class="text-rose-500">*</span></label><input type="text" name="fullname" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-bold text-slate-700">เลขบัตรประชาชน <span class="text-rose-500">* (Username)</span></label><input type="text" name="id_card" maxlength="13" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-bold text-slate-700">รหัสผ่าน <span class="text-rose-500">*</span></label><input type="password" name="password" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                </div>
                <button type="submit" class="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-2">บันทึกเพิ่มเจ้าหน้าที่</button>
            </form>
        </div>
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
            <table class="w-full text-left"><thead class="bg-sky-50 text-xs text-sky-700"><tr><th class="py-3 px-4">ชื่อ-สกุล</th><th class="py-3 px-4">สิทธิ์</th></tr></thead><tbody>{rows}</tbody></table>
        </div>
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
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนในระบบแล้ว', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Username นี้ถูกใช้งานแล้ว กรุณาเลือกชื่อผู้ใช้ใหม่', 'error')
            return redirect(url_for('register'))

        new_member_id = generate_member_id()
        new_user = User(
            member_id=new_member_id, prefix=prefix, fullname=fullname, id_card=id_card, dob=dob, phone=phone, email=email, address=full_address, id_card_img="default_id_card.png", username=username, password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f'สมัครสมาชิกเรียบร้อยแล้ว! รหัสนักศึกษาของคุณคือ: {new_member_id}', 'success')
        return redirect(url_for('login'))

    content = """
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h2 class="text-2xl font-black text-slate-900 text-center mb-8">ลงทะเบียนนักศึกษาสาขาวิชาระบบสารสนเทศ</h2>
        <form method="POST" class="space-y-5">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้า *</label><select name="prefix" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"><option value="นาย">นาย</option><option value="นาง">นาง</option><option value="นางสาว">นางสาว</option></select></div>
                <div class="md:col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล *</label><input type="text" name="fullname" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เลขบัตรประชาชน (13 หลัก) *</label><input type="text" name="id_card" maxlength="13" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">วัน/เดือน/ปีเกิด *</label><input type="date" name="dob" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ *</label><input type="tel" name="phone" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมล *</label><input type="email" name="email" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="border-t border-sky-100 pt-4">
                <label class="block text-xs font-bold text-sky-700 uppercase tracking-wider mb-3"><i class="fa-solid fa-house-user mr-1 text-sky-400"></i> ข้อมูลที่อยู่</label>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">บ้านเลขที่ *</label><input type="text" name="house_no" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">หมู่ที่</label><input type="text" name="moo" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ซอย / ถนน</label><input type="text" name="soi" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ตำบล/แขวง *</label><input type="text" name="subdistrict" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">อำเภอ/เขต *</label><input type="text" name="district" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">จังหวัด *</label><input type="text" name="province" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">รหัสไปรษณีย์ *</label><input type="text" name="postal_code" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-sky-100 pt-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อผู้ใช้งาน (Username) *</label><input type="text" name="username" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password) *</label><input type="password" name="password" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-4">ยืนยันการลงทะเบียน</button>
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
            <div><label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">Username / บัตรประชาชน</label><input type="text" name="username" required class="w-full border border-sky-100 rounded-xl p-3 text-sm bg-slate-50 focus:bg-white outline-none"></div>
            <div><label class="block text-xs font-bold text-slate-500 uppercase mb-1.5">รหัสผ่าน</label><input type="password" name="password" required class="w-full border border-sky-100 rounded-xl p-3 text-sm bg-slate-50 focus:bg-white outline-none"></div>
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