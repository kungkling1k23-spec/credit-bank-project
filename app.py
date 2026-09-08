import os
import uuid
import csv
import io
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
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
    doc_img = db.Column(db.String(200), nullable=True)
    doc_img2 = db.Column(db.String(200), nullable=True)
    doc_img3 = db.Column(db.String(200), nullable=True)
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
RESET_DB_FOR_PRODUCTION = False

with app.app_context():
    if RESET_DB_FOR_PRODUCTION:
        try:
            db.drop_all()
        except Exception:
            pass

    db.create_all()

    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS doc_img2 VARCHAR(200);"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN IF NOT EXISTS doc_img3 VARCHAR(200);"))
            conn.commit()
    except Exception as e:
        print("Migration Notice:", e)

    try:
        main_admin = User.query.filter((User.username == 'Admin_rmutto') | (User.username == 'admin')).first()
        if not main_admin:
            main_admin = User(
                member_id='ADM001',
                prefix='นาย',
                fullname='ผู้ดูแลระบบหลัก (Super Admin)', 
                id_card='0000000000000',
                username='Admin_rmutto', 
                password=generate_password_hash('rmutto2026'), 
                role='superadmin', 
                phone="081-000-0000",
                email="admin@rmutto.ac.th"
            )
            db.session.add(main_admin)
            db.session.commit()
    except Exception:
        db.session.rollback()

def generate_member_id():
    try:
        last_user = User.query.filter(User.member_id.like('IS%')).order_by(User.id.desc()).first()
        if not last_user or not last_user.member_id:
            return "IS69001"
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
# ลิงก์สำหรับดึงข้อมูลเป็น CSV อัตโนมัติจาก Google Sheets ที่แชร์ไว้
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/180MQL9RadQfhO0uN-L3hQGYiRhDPYvzJ/export?format=csv"

# ข้อมูลสำรอง (Fallback) ในกรณีที่ Google Sheets ล่มหรือต่อเน็ตไม่ได้
IS_THAIMOOC_COURSES = [
    {"code": "15-02-002", "name": "คุณภาพการใช้ชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ชีวิตและการสร้างคุณค่า (2 ชม.)", "2. การคิดสร้างสรรค์เพื่อการพัฒนาตนเอง (5 ชม.)"], "hours": "7 ชม.", "credits": 3}
]

def get_courses():
    try:
        req = urllib.request.Request(SHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=10)
        csv_data = response.read().decode('utf-8')
        
        reader = csv.DictReader(io.StringIO(csv_data))
        courses = []
        for row in reader:
            code = row.get('รหัสวิชา', '').strip()
            if not code: continue # ข้ามบรรทัดที่ไม่มีรหัสวิชา
            
            name = row.get('ชื่อวิชา', '').strip()
            group = row.get('หมวดวิชา', '').strip()
            provider = row.get('ระบบ', 'ThaiMOOC').strip()
            hours = row.get('ชั่วโมงเรียน', '').strip()
            
            credits_raw = row.get('หน่วยกิต', '3').strip()
            try:
                credits = int(credits_raw)
            except:
                credits = 3
            
            mooc_raw = row.get('บทเรียนออนไลน์', '')
            mooc_list = [m.strip() for m in mooc_raw.split('\n') if m.strip()]
            
            courses.append({
                "code": code,
                "name": name,
                "group": group,
                "provider": provider,
                "hours": hours,
                "credits": credits,
                "mooc_list": mooc_list
            })
        
        if courses:
            return courses
        return IS_THAIMOOC_COURSES
    except Exception as e:
        print("Google Sheet Load Error:", e)
        return IS_THAIMOOC_COURSES

# ==========================================
# Layout Template
# ==========================================
LAYOUT_TEMPLATE = """
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
        body { font-family: 'Sarabun', sans-serif; background-color: #f0f9ff; }
        .hero-sky { background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 50%, #7dd3fc 100%); }
        .sidebar-transition { transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-hover { transition: all 0.25s ease-in-out; }
        .card-hover:hover { transform: translateY(-3px); box-shadow: 0 12px 24px -10px rgba(14, 165, 233, 0.15); }
        .sidebar-expanded { width: 270px; }
        .sidebar-collapsed { width: 85px; }
        .sidebar-collapsed .nav-text { display: none; }
        .sidebar-collapsed .logo-img-full { display: none; }
        .sidebar-collapsed .logo-img-small { display: block !important; }
        .sidebar-collapsed .section-title { display: none; }
        .sidebar-collapsed .toggle-icon { transform: rotate(180deg); }
    </style>
</head>
<body class="bg-sky-50/50 min-h-screen text-slate-800 antialiased flex flex-col md:flex-row">

    <div class="md:hidden bg-sky-100 text-slate-800 p-3 flex justify-between items-center sticky top-0 z-50 border-b border-sky-200 shadow-md">
        <a href="/" class="flex items-center gap-2 px-2 py-1">
            <img src="/static/images/logo.png" alt="IS RMUTTO Credit Bank" class="h-10 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS+RMUTTO';">
        </a>
        <button id="mobile-toggle" class="p-2 text-sky-800 hover:text-sky-950 focus:outline-none"><i class="fa-solid fa-bars text-xl"></i></button>
    </div>

    <aside id="sidebar" class="sidebar-expanded sidebar-transition bg-sky-100 text-slate-700 min-h-screen flex flex-col fixed md:sticky top-0 z-40 shadow-xl border-r border-sky-200 hidden md:flex shrink-0 w-full md:w-auto">
        <div class="p-4 flex flex-col border-b border-sky-200 bg-sky-200/40">
            <a href="/" class="flex items-center justify-center overflow-hidden py-2 px-2 group">
                <img src="/static/images/logo.png" alt="IS RMUTTO Credit Bank" class="w-full max-h-20 object-contain logo-img-full transition-transform group-hover:scale-105" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x80?text=IS+RMUTTO+Credit+Bank';">
                <div class="logo-img-small hidden">
                    <div class="w-11 h-11 bg-gradient-to-tr from-sky-500 to-blue-600 text-white rounded-2xl flex items-center justify-center font-black text-xl shadow-md">IS</div>
                </div>
            </a>
            <div class="mt-3 pt-2 border-t border-sky-200/60 hidden md:flex justify-center">
                <button id="sidebar-toggle" class="w-full py-1.5 px-3 rounded-xl bg-sky-200 hover:bg-sky-300 text-sky-800 flex items-center justify-center gap-2 transition-all group border border-sky-300/50">
                    <i class="fa-solid fa-chevron-left text-xs toggle-icon transition-transform duration-300"></i>
                    <span class="nav-text text-xs font-bold text-sky-800">ย่อแถบเมนู</span>
                </button>
            </div>
        </div>

        <div class="flex-grow p-4 space-y-1.5 overflow-y-auto">
            <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-2">เมนูหลัก</p>
            <a href="/" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                <i class="fa-solid fa-house text-lg w-6 text-center text-sky-500 group-hover:text-sky-700 transition-colors"></i>
                <span class="nav-text font-semibold">หน้าแรก</span>
            </a>

            {% if session.get('user_id') %}
                {% if session.get('role') in ['admin', 'superadmin'] %}
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/students" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-users text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">รายชื่อนักศึกษา</span>
                    </a>
                    <a href="/admin/requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-file-signature text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">คำร้องเทียบโอน</span>
                    </a>
                    <a href="/admin/profile_requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-user-pen text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">คำร้องแก้ไขข้อมูล</span>
                    </a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-book-open text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">รายวิชาทั้งหมด (Google Sheets)</span>
                    </a>
                    <a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-sky-900 bg-sky-200 border border-sky-300 hover:bg-sky-300 transition-all font-medium text-sm group mt-2">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-sky-600"></i><span class="nav-text font-bold">เพิ่ม/จัดการเจ้าหน้าที่</span>
                    </a>
                {% else %}
                    <p class="section-title text-[11px] font-extrabold text-sky-700 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-magnifying-glass text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">ค้นหารายวิชา</span>
                    </a>
                    <a href="/all_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-book-open text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">รายวิชาทั้งหมด</span>
                    </a>
                    <a href="/submit_credit" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-file-circle-plus text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">ยื่นคำขอเทียบโอน</span>
                    </a>
                    <a href="/credits" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-graduation-cap text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">หน่วยกิตสะสม</span>
                    </a>
                    <a href="/history" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-clock-rotate-left text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">ประวัติคำขอ</span>
                    </a>
                {% endif %}
            {% else %}
                <div class="pt-4 space-y-2">
                    <a href="/login" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-700 hover:text-sky-900 hover:bg-sky-200/80 transition-all font-medium text-sm group border border-sky-200">
                        <i class="fa-solid fa-right-to-bracket text-lg w-6 text-center text-sky-500 group-hover:text-sky-700"></i><span class="nav-text font-semibold">เข้าสู่ระบบ</span>
                    </a>
                    <a href="/register" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold transition-all text-sm group shadow-md shadow-sky-400/30">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-sky-100"></i><span class="nav-text">ลงทะเบียนนักศึกษา</span>
                    </a>
                </div>
            {% endif %}
        </div>

        {% if session.get('user_id') %}
            <div class="p-4 border-t border-sky-200 bg-sky-200/40">
                <a href="/profile" class="flex items-center gap-3 p-2 rounded-2xl hover:bg-sky-200/60 transition-all group border border-transparent">
                    <div class="w-9 h-9 rounded-xl bg-sky-200 text-sky-700 font-bold flex items-center justify-center shrink-0"><i class="fa-regular fa-user"></i></div>
                    <div class="flex flex-col min-w-0 nav-text">
                        <span class="text-xs font-bold text-slate-800 truncate">{{ session.get('fullname', 'ผู้ใช้งาน') }}</span>
                        <span class="text-[10px] text-sky-700 capitalize font-medium">{% if session.get('role') in ['admin', 'superadmin'] %}เจ้าหน้าที่{% else %}นักศึกษาสาขา IS{% endif %}</span>
                    </div>
                </a>
                <a href="/logout" class="mt-2 flex items-center gap-3 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl transition-all">
                    <i class="fa-solid fa-arrow-right-from-bracket text-sm w-6 text-center"></i><span class="nav-text">ออกจากระบบ</span>
                </a>
            </div>
        {% endif %}
    </aside>

    <div class="flex-grow flex flex-col min-h-screen min-w-0">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full mt-6">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="p-4 mb-4 text-sm rounded-2xl font-semibold shadow-sm flex items-center justify-between border transition-all {% if category == 'error' or category == 'danger' %}bg-rose-50 text-rose-700 border-rose-200{% else %}bg-emerald-50 text-emerald-800 border-emerald-200{% endif %}">
                            <div class="flex items-center gap-2">
                                <i class="fa-solid {% if category == 'error' or category == 'danger' %}fa-circle-exclamation text-rose-500{% else %}fa-circle-check text-emerald-500{% endif %} text-lg"></i>
                                <span>{{ message }}</span>
                            </div>
                            <button onclick="this.parentElement.remove()" class="text-xs font-bold px-2 py-1 hover:bg-black/5 rounded-lg">✕</button>
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
        </div>

        <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {{ content | safe }}
        </main>

        <footer class="bg-sky-100 text-slate-600 mt-auto border-t border-sky-200">
            <div class="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
                <div class="flex flex-col md:flex-row items-center justify-between gap-4 text-xs font-medium text-center md:text-left">
                    <div class="flex items-center gap-3">
                        <img src="/static/images/logo.png" alt="IS RMUTTO Logo" class="h-10 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS+RMUTTO';">
                        <div>
                            <p class="text-sky-900 font-bold text-sm">สาขาวิชาระบบสารสนเทศ (Information Systems)</p>
                            <p class="text-slate-600 mt-0.5">คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก</p>
                        </div>
                    </div>
                    <div class="text-slate-500 leading-relaxed font-semibold">© 2026 Credit Bank System</div>
                </div>
            </div>
        </footer>
    </div>

    <script>
        const sidebar = document.getElementById('sidebar');
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const mobileToggle = document.getElementById('mobile-toggle');

        if (sidebarToggle && sidebar) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('sidebar-expanded');
                sidebar.classList.toggle('sidebar-collapsed');
            });
        }
        if (mobileToggle && sidebar) {
            mobileToggle.addEventListener('click', () => {
                sidebar.classList.toggle('hidden');
            });
        }
    </script>
</body>
</html>
"""

# ==========================================
# Routes & Controllers
# ==========================================
@app.route('/')
def home():
    if not session.get('user_id'):
        content = """
        <div class="max-w-5xl mx-auto py-10 md:py-16 grid md:grid-cols-2 gap-10 items-center">
            <div>
                <span class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-sky-100 text-sky-800 mb-5 border border-sky-200">
                    <i class="fa-solid fa-laptop-code text-sky-500"></i> สาขาวิชาระบบสารสนเทศ (IS) มทร.ตะวันออก
                </span>
                <div class="space-y-2 mb-6">
                    <h1 class="text-4xl sm:text-5xl font-black text-slate-900 leading-relaxed tracking-normal">ธนาคารหน่วยกิต</h1>
                    <p class="text-3xl sm:text-4xl font-extrabold text-sky-600 leading-relaxed">เทียบโอน Thai & Chula MOOC</p>
                    <p class="text-3xl sm:text-4xl font-extrabold text-blue-500 leading-relaxed">สาขาวิชาระบบสารสนเทศ</p>
                </div>
                <p class="text-slate-600 mb-8 leading-relaxed text-base font-normal">ระบบสะสมและเทียบโอนหน่วยกิตดิจิทัล สำหรับนักศึกษาสาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก</p>
                <div class="flex flex-wrap gap-4">
                    <a href="/register" class="px-7 py-3.5 bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold rounded-2xl shadow-lg shadow-sky-400/30 hover:shadow-xl transition-all inline-flex items-center gap-2"><i class="fa-solid fa-user-plus text-sky-100"></i> สมัครสมาชิกนักศึกษา IS</a>
                    <a href="/login" class="px-7 py-3.5 bg-white text-slate-800 border border-sky-200 font-bold rounded-2xl hover:bg-sky-50 transition shadow-sm inline-flex items-center gap-2">เข้าสู่ระบบ</a>
                </div>
            </div>
            <div class="hero-sky p-8 rounded-3xl text-center shadow-lg relative overflow-hidden border border-sky-200 flex flex-col items-center justify-center">
                <div class="mb-4 w-full max-w-xs flex justify-center py-2">
                    <img src="/static/images/logo.png" alt="IS RMUTTO Credit Bank Logo" class="w-full max-h-28 object-contain drop-shadow" onerror="this.onerror=null; this.src='https://via.placeholder.com/300x150?text=IS+RMUTTO+Credit+Bank';">
                </div>
                <h3 class="text-xl font-black text-slate-800 mb-1">Information Systems</h3>
                <p class="text-slate-600 text-xs leading-relaxed max-w-sm mx-auto font-medium">ระบบคลังหน่วยกิตการเรียนรู้ผ่านสื่อออนไลน์ ThaiMOOC / ChulaMOOC</p>
            </div>
        </div>
        """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if user.role in ['admin', 'superadmin']:
        try:
            pending_credits = CreditRequest.query.filter_by(status='Pending').count()
            pending_edits = ProfileEditRequest.query.filter_by(status='Pending').count()
            total_members = User.query.filter_by(role='student').count()
            total_admins = User.query.filter(User.role.in_(['admin', 'superadmin'])).count()
        except:
            pending_credits, pending_edits, total_members, total_admins = 0, 0, 0, 1

        content = f"""
        <div class="mb-8">
            <h2 class="text-2xl font-extrabold text-slate-900">ยินดีต้อนรับ, เจ้าหน้าที่ประจำสาขาวิชาระบบสารสนเทศ</h2>
            <p class="text-slate-500 text-sm mt-1">แผงควบคุมระบบตรวจสอบและอนุมัติสำหรับเจ้าหน้าที่ ({user.fullname})</p>
        </div>
        <div class="mb-8">
            <a href="/admin/manage_admins" class="bg-gradient-to-r from-sky-500 to-blue-600 text-white p-7 rounded-3xl shadow-md flex items-center justify-between hover:opacity-95 transition-all block border border-sky-300">
                <div>
                    <div class="flex items-center gap-2 mb-2">
                        <span class="bg-white/20 text-white text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider shadow-sm border border-white/30">แอดมินจัดการ</span>
                        <h3 class="text-2xl font-extrabold text-white">➕ เพิ่มเจ้าหน้าที่ตรวจงานระบบสารสนเทศ</h3>
                    </div>
                    <p class="text-sm text-sky-100">เพิ่มบัญชีเจ้าหน้าที่ใหม่ด้วยเลขบัตรประชาชนและรหัสผ่านส่วนตัว (ปัจจุบันมีเจ้าหน้าที่ {total_admins} คน)</p>
                </div>
                <div class="w-14 h-14 bg-white/20 text-white rounded-2xl flex items-center justify-center text-2xl shrink-0 backdrop-blur"><i class="fa-solid fa-user-plus"></i></div>
            </a>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <a href="/admin/students" class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between hover:border-sky-400 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">นักศึกษาสาขา IS ในระบบ</p>
                    <h3 class="text-3xl font-black text-slate-900">{total_members} <span class="text-xs text-slate-400 font-normal">คน</span></h3>
                </div>
                <div class="w-12 h-12 bg-sky-50 text-sky-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-users"></i></div>
            </a>
            <a href="/admin/requests" class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between hover:border-amber-400 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องเทียบโอนค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-file-signature"></i></div>
            </a>
            <a href="/admin/profile_requests" class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between hover:border-indigo-400 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องแก้ไขข้อมูลค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-indigo-500">{pending_edits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-indigo-50 text-indigo-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-user-pen"></i></div>
            </a>
        </div>
        """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
    except:
        user_requests = []

    approved_reqs = [r for r in user_requests if getattr(r, 'status', '') == 'Approved']
    approved_credits = sum(getattr(r, 'credits', 0) for r in approved_reqs)
    pending_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') == 'Pending')
    remaining_credits = max(0, 120 - approved_credits - pending_credits)

    content = f"""
    <div class="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
            <h2 class="text-3xl font-black text-slate-900">สวัสดีครับ, {user.prefix or ''} {user.fullname}</h2>
            <p class="text-sm font-bold text-sky-600 mt-1"><i class="fa-solid fa-id-card mr-1 text-sky-400"></i> รหัสนักศึกษา: {user.member_id or '-'} (สาขาวิชาระบบสารสนเทศ)</p>
        </div>
        <a href="/submit_credit" class="bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold px-6 py-3 rounded-2xl shadow-md shadow-sky-400/20 transition-all inline-flex items-center gap-2 text-sm shrink-0">
            <i class="fa-solid fa-file-circle-plus text-sky-100"></i> ยื่นคำขอเทียบโอนออนไลน์
        </a>
    </div>

    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div><p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">หน่วยกิตสะสมทั้งหมด</p><h3 class="text-3xl font-black text-sky-600">{approved_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3></div>
            <div class="w-12 h-12 bg-sky-50 text-sky-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div><p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">รออนุมัติเทียบโอน</p><h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3></div>
            <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-hourglass-half"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div><p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องขอเทียบโอน</p><h3 class="text-3xl font-black text-slate-800">{len(user_requests)} <span class="text-xs font-medium text-slate-400">รายการ</span></h3></div>
            <div class="w-12 h-12 bg-purple-50 text-purple-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-list-check"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div><p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">เป้าหมายหลักสูตร IS</p><h3 class="text-3xl font-black text-emerald-500">120 <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3></div>
            <div class="w-12 h-12 bg-emerald-50 text-emerald-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-bullseye"></i></div>
        </div>
    </div>

    <!-- Charts -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2"><i class="fa-solid fa-chart-pie text-sky-500"></i> ความก้าวหน้าหน่วยกิตสาขา IS</h3>
            <div class="w-full max-w-[240px] mx-auto py-2"><canvas id="creditDoughnutChart"></canvas></div>
        </div>
        <div class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm lg:col-span-2">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2"><i class="fa-solid fa-chart-column text-sky-500"></i> สรุปการสะสมหน่วยกิต</h3>
            <div class="w-full h-56"><canvas id="creditBarChart"></canvas></div>
        </div>
    </div>

    <script>
        const ctxDoughnut = document.getElementById('creditDoughnutChart').getContext('2d');
        new Chart(ctxDoughnut, {{
            type: 'doughnut',
            data: {{
                labels: ['อนุมัติแล้ว', 'รอพิจารณา', 'คงเหลือถึงเป้าหมาย'],
                datasets: [{{
                    data: [{approved_credits}, {pending_credits}, {remaining_credits}],
                    backgroundColor: ['#0284c7', '#f59e0b', '#e2e8f0'],
                    borderWidth: 0
                }}]
            }},
            options: {{ responsive: true, cutout: '70%', plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ family: 'Sarabun', size: 12 }} }} }} }} }}
        }});

        const ctxBar = document.getElementById('creditBarChart').getContext('2d');
        new Chart(ctxBar, {{
            type: 'bar',
            data: {{
                labels: ['หน่วยกิตอนุมัติทั้งหมด'],
                datasets: [{{ label: 'หน่วยกิตสะสม (อนุมัติแล้ว)', data: [{approved_credits}], backgroundColor: '#38bdf8', borderRadius: 8 }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true, max: 120 }} }}, plugins: {{ legend: {{ display: false }} }} }}
        }});
    </script>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))

    # ดึงข้อมูลจาก Google Sheets (สดๆ ทันที)
    course_data = get_courses()

    search_query = request.args.get('search', '').strip().lower()
    selected_group = request.args.get('group', '').strip()
    selected_provider = request.args.get('provider', '').strip()

    filtered_courses = course_data

    if selected_provider and selected_provider != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['provider'] == selected_provider]

    if selected_group and selected_group != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['group'] == selected_group]

    if search_query:
        filtered_courses = [c for c in filtered_courses if search_query in c['name'].lower() or search_query in c['code'].lower() or any(search_query in m.lower() for m in c['mooc_list'])]

    cards = ""
    for c in filtered_courses:
        badge_provider = "bg-sky-100 text-sky-800 border-sky-200" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-800 border-amber-200"
        mooc_items_html = "".join([f'<li class="flex items-start gap-1.5"><i class="fa-solid fa-angle-right text-sky-500 mt-1 shrink-0"></i><span>{m}</span></li>' for m in c['mooc_list']])

        cards += f"""
        <div class="bg-white rounded-3xl border border-sky-100 p-6 shadow-sm flex flex-col justify-between card-hover">
            <div>
                <div class="flex flex-wrap items-center justify-between gap-2 mb-4 pb-3 border-b border-sky-50">
                    <span class="font-mono text-xs font-bold bg-sky-50 text-sky-700 px-3 py-1 rounded-xl border border-sky-100 shrink-0">{c['code']}</span>
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="px-2.5 py-1 rounded-xl text-[11px] font-bold border {badge_provider} shrink-0">{c['provider']}</span>
                        <span class="bg-slate-50 text-slate-600 text-[11px] px-2.5 py-1 rounded-xl font-bold border border-slate-200 shrink-0">{c['group']}</span>
                    </div>
                </div>
                <h3 class="text-lg font-extrabold text-slate-900 mb-2 leading-snug">{c['name']}</h3>
                <div class="bg-sky-50/50 p-4 rounded-2xl border border-sky-100 mb-4">
                    <p class="text-xs font-bold text-slate-800 mb-2 flex items-center gap-1"><i class="fa-solid fa-laptop-code text-sky-600"></i> บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม ({c['provider']}):</p>
                    <ul class="text-xs text-slate-600 leading-relaxed space-y-1.5 font-medium">{mooc_items_html}</ul>
                </div>
            </div>
            <div class="border-t border-sky-50 pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-slate-600 mb-4">
                    <span><i class="fa-regular fa-clock mr-1 text-slate-400"></i> รวมเวลาเรียน: <b>{c['hours']}</b></span>
                    <span class="font-black text-sky-700 text-sm bg-sky-50 px-3 py-1 rounded-xl border border-sky-100">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['provider'] + '&credits=' + str(c['credits']) + '&cat=' + c['group'] + '&major_select=สาขาวิชาระบบสารสนเทศ#form_section" class="block text-center w-full bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold py-3 rounded-2xl text-sm transition shadow-md shadow-sky-400/20">ยื่นเทียบโอนวิชานี้</a>' if session.get('role') not in ['admin', 'superadmin'] else ''}
            </div>
        </div>
        """

    content = f"""
    <div class="hero-sky text-slate-800 p-8 rounded-3xl shadow-sm mb-8 flex flex-col md:flex-row justify-between items-center gap-6 border border-sky-200">
        <div>
            <span class="bg-white/80 text-sky-800 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-wider mb-2 inline-block border border-white">Live from Google Sheets</span>
            <h2 class="text-3xl font-extrabold text-slate-900">🔍 ค้นหารายวิชาเทียบโอนหลักสูตร</h2>
            <p class="text-slate-600 text-xs mt-1.5 leading-relaxed">ข้อมูลอัปเดตแบบเรียลไทม์จากระบบ Google Sheets ของสาขาวิชา</p>
        </div>
        <div class="bg-white/80 backdrop-blur px-6 py-4 rounded-2xl border border-white text-center shrink-0 shadow-sm">
            <span class="text-xs text-slate-500 block font-medium">จำนวนรายวิชาที่พบ</span>
            <span class="text-3xl font-black text-sky-600">{len(filtered_courses)}</span> <span class="text-xs text-slate-500">/ {len(course_data)} วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm mb-8 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-globe mr-1 text-sky-400"></i> สื่อการเรียนรู้</label>
                <select name="provider" onchange="this.form.submit()" class="w-full border border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50/50 font-medium">
                    <option value="ทั้งหมด" {'selected' if selected_provider=='ทั้งหมด' or not selected_provider else ''}>ทุกระบบ (Thai & Chula MOOC)</option>
                    <option value="ThaiMOOC" {'selected' if selected_provider=='ThaiMOOC' else ''}>ThaiMOOC</option>
                    <option value="ChulaMOOC" {'selected' if selected_provider=='ChulaMOOC' else ''}>ChulaMOOC</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-layer-group mr-1 text-sky-500"></i> หมวดวิชาหลักสูตร</label>
                <select name="group" onchange="this.form.submit()" class="w-full border border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50/50 font-medium">
                    <option value="ทั้งหมด" {'selected' if selected_group=='ทั้งหมด' or not selected_group else ''}>ทุกหมวดวิชา</option>
                    <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if selected_group=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                    <option value="หมวดวิชาแกน" {'selected' if selected_group=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                    <option value="หมวดวิชาเลือก" {'selected' if selected_group=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                </select>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-magnifying-glass mr-1 text-sky-500"></i> ค้นหาด้วยรหัสวิชา / ชื่อวิชา</label>
                <div class="flex gap-2">
                    <input type="text" name="search" value="{search_query}" placeholder="พิมพ์ชื่อวิชา..." class="w-full px-4 py-3 border border-sky-100 rounded-2xl text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50/50 font-medium">
                    <button type="submit" class="bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold px-7 py-3 rounded-2xl text-sm transition shadow-md shadow-sky-400/20 shrink-0">ค้นหา</button>
                </div>
            </div>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-16 text-slate-400 bg-white rounded-3xl border border-sky-100">ไม่พบรายวิชาที่ตรงกับเงื่อนไขการค้นหา</div>'}
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/all_courses')
def all_courses():
    if 'user_id' not in session: return redirect(url_for('login'))

    # ดึงข้อมูลจาก Google Sheets
    course_data = get_courses()
    rows = ""
    for idx, c in enumerate(course_data, 1):
        provider_badge = '<span class="bg-sky-100 text-sky-900 border border-sky-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">ThaiMOOC</span>' if c['provider'] == 'ThaiMOOC' else '<span class="bg-amber-100 text-amber-900 border border-amber-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">ChulaMOOC</span>'
        mooc_multiline = "<br>".join([f"• {m}" for m in c['mooc_list']])

        rows += f"""
        <tr class="border-b border-sky-100 text-xs hover:bg-sky-50/50 transition">
            <td class="py-3.5 px-4 font-mono font-bold text-slate-500 text-center">{idx}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-sky-700">{c['code']}</td>
            <td class="py-3.5 px-4 font-extrabold text-slate-900">{c['name']}<br>{provider_badge}</td>
            <td class="py-3.5 px-4 font-bold text-slate-700">{c['group']}</td>
            <td class="py-3.5 px-4 text-slate-700 leading-relaxed max-w-xs font-semibold">{mooc_multiline}</td>
            <td class="py-3.5 px-4 text-center font-black text-sky-600">{c['credits']}</td>
            <td class="py-3.5 px-4 text-center">
                <a href="/submit_credit?course={c['name']}&inst={c['provider']}&credits={c['credits']}&cat={c['group']}&major_select=สาขาวิชาระบบสารสนเทศ#form_section" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-3 py-1.5 rounded-xl text-[11px] inline-block shadow-sm">ยื่นเทียบโอน</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm mb-8">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-sky-100">
            <div>
                <h2 class="text-2xl font-black text-slate-900 flex items-center gap-2">
                    <i class="fa-solid fa-book-open text-sky-600"></i> รายวิชาทั้งหมดในหลักสูตร (เชื่อมต่อ Google Sheets)
                </h2>
                <p class="text-xs text-slate-500 mt-1 font-medium">ตารางสรุปรายวิชาอัปเดตแบบเรียลไทม์จาก Google Sheets ของสาขาวิชาระบบสารสนเทศ</p>
            </div>
            <div class="bg-emerald-100 text-emerald-800 px-4 py-2 rounded-2xl border border-emerald-200 text-xs font-black shrink-0 flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> โหลดข้อมูลแล้ว {len(course_data)} วิชา
            </div>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-sky-100">
            <table class="w-full text-left min-w-[850px]">
                <thead class="bg-sky-100/60 border-b border-sky-200 text-xs font-black uppercase text-slate-700">
                    <tr><th class="py-3.5 px-4 text-center">#</th><th class="py-3.5 px-4">รหัสวิชา</th><th class="py-3.5 px-4">รายวิชาหลักสูตร IS</th><th class="py-3.5 px-4">หมวดวิชา</th><th class="py-3.5 px-4">บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม</th><th class="py-3.5 px-4 text-center">หน่วยกิต</th><th class="py-3.5 px-4 text-center">จัดการ</th></tr>
                </thead>
                <tbody class="divide-y divide-sky-100">{rows}</tbody>
            </table>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)


@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            credits_raw = request.form.get('credits', '3')
            try:
                credits_val = int(credits_raw)
            except (ValueError, TypeError):
                credits_val = 3

            course_name = request.form.get('course_name', '').strip() or 'รายวิชาเทียบโอน'
            institution = request.form.get('institution', '').strip() or 'ThaiMOOC'
            category = request.form.get('category', 'หมวดวิชาศึกษาทั่วไป')
            faculty = "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ"
            major = request.form.get('major', 'สาขาวิชาระบบสารสนเทศ')

            doc_filename = "default_doc.png"
            if 'cert_file' in request.files:
                file = request.files['cert_file']
                if file and file.filename != '' and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    unique_fn = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_fn)
                    file.save(save_path)
                    doc_filename = unique_fn

            req_id_to_update = request.form.get('edit_req_id')
            if req_id_to_update:
                existing_req = CreditRequest.query.get(req_id_to_update)
                if existing_req and existing_req.user_id == session['user_id']:
                    existing_req.course_name = course_name
                    existing_req.institution = institution
                    existing_req.credits = credits_val
                    existing_req.category = category
                    if doc_filename != "default_doc.png":
                        existing_req.doc_img = doc_filename
                    existing_req.status = 'Pending'
                    existing_req.reject_reason = None
                    db.session.commit()
                    flash('แก้ไขและยื่นเอกสารขอเทียบโอนอีกครั้งเรียบร้อยแล้ว!', 'success')
                    return redirect(url_for('history'))

            req_code = f"TR2569{uuid.uuid4().hex[:4].upper()}"

            req = CreditRequest(
                req_code=req_code,
                user_id=session['user_id'], 
                course_name=course_name, 
                institution=institution, 
                credits=credits_val,
                category=category,
                faculty=faculty,
                major=major,
                date_submitted=datetime.now().strftime("%Y-%m-%d"),
                doc_img=doc_filename,
                status='Pending'
            )
            db.session.add(req)
            db.session.commit()
            flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('history'))

        except Exception as e:
            db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล กรุณาลองใหม่อีกครั้ง ({str(e)})', 'error')
            return redirect(url_for('submit_credit'))

    init_course = request.args.get('course', '')
    init_inst = request.args.get('inst', 'ThaiMOOC')
    init_credits = request.args.get('credits', '3')
    init_cat = request.args.get('cat', 'หมวดวิชาศึกษาทั่วไป')
    selected_major = request.args.get('major_select', '')
    edit_req_id = request.args.get('edit_id', '')

    if edit_req_id:
        old_req = CreditRequest.query.get(edit_req_id)
        if old_req and old_req.user_id == session['user_id']:
            init_course = old_req.course_name
            init_inst = old_req.institution
            init_credits = str(old_req.credits)
            init_cat = old_req.category
            selected_major = "สาขาวิชาระบบสารสนเทศ"

    is_subject_rows = ""
    if selected_major == "สาขาวิชาระบบสารสนเทศ":
        # ดึงข้อมูลจาก Google Sheets แทนรายการเก่า
        course_data = get_courses()
        for item in course_data:
            provider_badge = '<span class="bg-sky-100 text-sky-800 border border-sky-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">ThaiMOOC</span>' if item['provider'] == 'ThaiMOOC' else '<span class="bg-amber-100 text-amber-800 border border-amber-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">ChulaMOOC</span>'
            mooc_multiline = "<br>".join([f"• {m}" for m in item['mooc_list']])

            is_subject_rows += f"""
            <tr class="border-b border-sky-50 text-xs hover:bg-sky-50/50 transition">
                <td class="py-3.5 px-3 font-mono font-bold text-slate-500">{item['code']}</td>
                <td class="py-3.5 px-3 font-extrabold text-slate-900">{item['name']}<br>{provider_badge}</td>
                <td class="py-3.5 px-3 text-slate-700 leading-relaxed max-w-xs font-medium">{mooc_multiline}</td>
                <td class="py-3.5 px-3 text-center font-bold text-slate-700">{item['hours']}</td>
                <td class="py-3.5 px-3 text-center">
                    <a href="/submit_credit?course={item['name']}&inst={item['provider']}&credits={item['credits']}&cat={item['group']}&major_select=สาขาวิชาระบบสารสนเทศ#form_section" class="bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold px-3 py-1.5 rounded-xl text-[11px] inline-block shadow-sm">เลือกวิชานี้</a>
                </td>
            </tr>
            """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 bg-sky-50 text-sky-500 rounded-2xl flex items-center justify-center font-bold text-lg shrink-0"><i class="fa-solid fa-graduation-cap"></i></div>
                <div>
                    <h3 class="text-xl font-black text-slate-900">เลือกสาขาวิชาเพื่อดูรายวิชาที่ต้องเรียนเพิ่ม (ดึงจาก Google Sheets)</h3>
                </div>
            </div>

            <form method="GET" action="/submit_credit" class="mb-4">
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">เลือกสาขาวิชาของคุณ <span class="text-rose-500">*</span></label>
                <div class="flex gap-3">
                    <select name="major_select" onchange="this.form.submit()" class="w-full border border-sky-100 rounded-2xl p-3.5 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50/50 font-extrabold text-sky-800">
                        <option value="" {'selected' if not selected_major else ''}>-- กรุณาเลือกสาขาวิชาเพื่อเริ่มใช้งาน --</option>
                        <option value="สาขาวิชาระบบสารสนเทศ" {'selected' if selected_major=='สาขาวิชาระบบสารสนเทศ' else ''}>สาขาวิชาระบบสารสนเทศ (Information Systems - IS)</option>
                    </select>
                </div>
            </form>

            {'''
            <div class="overflow-x-auto rounded-2xl border border-sky-100">
                <table class="w-full text-left min-w-[650px]">
                    <thead class="bg-sky-50 text-sky-800 text-[11px] font-bold uppercase tracking-wider border-b border-sky-100">
                        <tr><th class="py-3 px-3">รหัสวิชา</th><th class="py-3 px-3">รายวิชาในหลักสูตร IS</th><th class="py-3 px-3">บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม</th><th class="py-3 px-3 text-center">ชั่วโมงเรียน</th><th class="py-3 px-3 text-center">การดำเนินการ</th></tr>
                    </thead>
                    <tbody class="divide-y divide-sky-50">''' + is_subject_rows + '''</tbody>
                </table>
            </div>
            ''' if selected_major == 'สาขาวิชาระบบสารสนเทศ' else '''<div class="text-center py-10 border border-dashed border-sky-200 rounded-2xl bg-sky-50/30"><p class="text-xs font-bold text-slate-500">เลือกสาขาก่อนครับ</p></div>'''}
        </div>

        <div id="form_section" class="bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl scroll-mt-6">
            <h3 class="text-2xl font-black text-slate-900 mb-2">แบบฟอร์มยื่นคำขอเทียบโอนหน่วยกิต</h3>
            <p class="text-xs text-slate-500 mb-6">กรอกรายละเอียดและแนบรูปภาพวุฒิบัตร/เกียรติบัตร ที่เรียนจบมาแล้ว</p>
            
            <form method="POST" enctype="multipart/form-data" class="space-y-4">
                <input type="hidden" name="major" value="สาขาวิชาระบบสารสนเทศ">
                <input type="hidden" name="edit_req_id" value="{edit_req_id}">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อรายวิชาในหลักสูตร *</label><input type="text" name="course_name" value="{init_course}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50/50 font-medium"></div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">แหล่งเรียนรู้ / ระบบออนไลน์ *</label>
                    <select name="institution" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50 font-medium">
                        <option value="ThaiMOOC" {'selected' if init_inst=='ThaiMOOC' else ''}>ThaiMOOC</option>
                        <option value="ChulaMOOC" {'selected' if init_inst=='ChulaMOOC' else ''}>ChulaMOOC</option>
                    </select>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">จำนวนหน่วยกิต *</label><input type="number" name="credits" value="{init_credits}" min="1" max="10" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50 font-medium"></div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">หมวดวิชาหลักสูตร</label>
                        <select name="category" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50 font-medium">
                            <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if init_cat=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                            <option value="หมวดวิชาแกน" {'selected' if init_cat=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                            <option value="หมวดวิชาเลือก" {'selected' if init_cat=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                        </select>
                    </div>
                </div>
                <div class="border-t border-sky-100 pt-4">
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-file-image mr-1 text-sky-400"></i> แนบรูปภาพเกียรติบัตร / วุฒิบัตร *</label>
                    <input type="file" name="cert_file" accept="image/*,.pdf" class="w-full border border-sky-100 rounded-2xl p-2.5 text-xs bg-sky-50/50 font-medium file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-sky-500 file:text-white">
                </div>
                <button type="submit" class="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-sky-400/20 text-sm mt-2">ยืนยันส่งคำร้องขอเทียบโอน</button>
            </form>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).order_by(CreditRequest.id.desc()).all()
    except Exception:
        user_requests = []

    rows = ""
    for r in user_requests:
        status = getattr(r, 'status', 'Pending')
        
        if status == 'Pending':
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอพิจารณา</span>'
            action_btn = '-'
        elif status == 'Approved':
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>'
            action_btn = '-'
        else: # Rejected
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ / ให้แก้ไข</span>'
            action_btn = f'<a href="/submit_credit?edit_id={r.id}#form_section" class="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold inline-block shadow-sm">แก้ไขเอกสารและยื่นใหม่</a>'

        approved_by = getattr(r, 'approved_by', '-') or '-'
        reason_box = f'<div class="mt-1 text-xs text-rose-600 font-medium"><b>เหตุผลที่ไม่ผ่าน:</b> {r.reject_reason}</div>' if getattr(r, 'reject_reason', None) else ''
        img_preview = f'<a href="/static/uploads/{r.doc_img}" target="_blank" class="text-xs text-sky-600 underline font-bold"><i class="fa-solid fa-image mr-1"></i>ดูรูปหลักฐาน</a>' if getattr(r, 'doc_img', None) and r.doc_img != 'default_doc.png' else '<span class="text-xs text-slate-400">ไม่มีแนบรูป</span>'

        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-500">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}<br>{img_preview}{reason_box}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)}</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{approved_by}</td>
            <td class="py-4 px-4">{badge}</td>
            <td class="py-4 px-4">{action_btn}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">ประวัติคำร้องเทียบโอน (สาขาวิชาระบบสารสนเทศ)</h3>
        <table class="w-full text-left min-w-[750px]">
            <thead class="bg-sky-50 border-b border-sky-100 text-xs font-bold text-sky-700 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา / หลักฐาน</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">ผู้ตรวจ</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="7" class="py-12 text-center text-slate-400">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/credits')
def credits():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        approved_requests = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
    except Exception:
        approved_requests = []

    total_approved = sum(getattr(r, 'credits', 0) for r in approved_requests)
    rows = ""
    for r in approved_requests:
        approved_by = getattr(r, 'approved_by', 'เจ้าหน้าที่') or 'เจ้าหน้าที่'
        rows += f"""
        <tr class="border-b border-sky-50 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{approved_by}</td>
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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user: return redirect(url_for('login'))
    display_title = "เจ้าหน้าที่" if user.role in ['admin', 'superadmin'] else f"{user.prefix or ''} {user.fullname}"
    
    content = f"""
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/request_edit_profile', methods=['GET', 'POST'])
def request_edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        prefix = request.form.get('prefix')
        fullname = request.form.get('fullname')
        phone = request.form.get('phone')
        email = request.form.get('email')
        
        house_no = request.form.get('house_no', '')
        moo = request.form.get('moo', '')
        soi = request.form.get('soi', '')
        subdistrict = request.form.get('subdistrict', '')
        district = request.form.get('district', '')
        province = request.form.get('province', '')
        postal_code = request.form.get('postal_code', '')

        full_addr = format_address(house_no, moo, soi, subdistrict, district, province, postal_code)
        reason = request.form.get('reason', '').strip()

        if not reason:
            flash('กรุณาระบุรายละเอียดและเหตุผลในการขอแก้ไขข้อมูลให้ครบถ้วนด้วยครับ', 'error')
            return redirect(url_for('request_edit_profile'))

        edit_req = ProfileEditRequest(
            user_id=user.id,
            new_prefix=prefix,
            new_fullname=fullname,
            new_phone=phone,
            new_email=email,
            new_address=full_addr,
            reason=reason
        )
        db.session.add(edit_req)
        db.session.commit()

        flash('ส่งคำร้องขอแก้ไขข้อมูลส่วนตัวสำเร็จแล้ว รอเจ้าหน้าที่พิจารณาตรวจสอบ', 'success')
        return redirect(url_for('profile'))

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">ส่งคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้าใหม่</label>
                <select name="prefix" class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50">
                    <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                    <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                    <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                </select></div>
                <div class="col-span-2"><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุลใหม่</label><input type="text" name="fullname" value="{user.fullname}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ใหม่</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมลใหม่</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            </div>
            <div>
                <label class="block text-xs font-bold text-rose-600 uppercase tracking-wider mb-1.5">เหตุผลในการขอแก้ไข *</label>
                <textarea name="reason" rows="3" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></textarea>
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-2">ส่งคำร้องให้เจ้าหน้าที่พิจารณา</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/requests')
def admin_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    
    try:
        all_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    except Exception:
        all_requests = []

    rows = ""
    for r in all_requests:
        status_val = getattr(r, 'status', 'Pending')
        
        if status_val == 'Pending':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอการพิจารณา</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="bg-gradient-to-r from-sky-500 to-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:from-sky-600 hover:to-blue-700 inline-block shadow-sm">พิจารณาคำร้อง</a>'
        elif status_val == 'Approved':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200"><i class="fa-solid fa-lock mr-1"></i>พิจารณาแล้ว</span>'
        else:
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ / ให้แก้ไข</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200"><i class="fa-solid fa-lock mr-1"></i>พิจารณาแล้ว</span>'

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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/review/<int:req_id>', methods=['GET', 'POST'])
def admin_review(req_id):
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    if req.status != 'Pending':
        flash('คำร้องนี้ได้รับการพิจารณาไปแล้ว ไม่สามารถแก้ไขได้อีก', 'error')
        return redirect(url_for('admin_requests'))

    if request.method == 'POST':
        action = request.form.get('action')
        reject_reason = request.form.get('reject_reason', '').strip()
        admin_user = User.query.get(session['user_id'])

        if action == 'approve':
            req.status = 'Approved'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('อนุมัติคำร้องเทียบโอนเรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin_requests'))
        
        elif action == 'reject':
            if not reject_reason:
                flash('กรุณาระบุเหตุผลหรือสิ่งที่ต้องแก้ไขก่อนส่งตีกลับให้นักศึกษาด้วยครับ', 'error')
                return redirect(url_for('admin_review', req_id=req_id))
            
            req.status = 'Rejected'
            req.reject_reason = reject_reason
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('ปฏิเสธ/ส่งเรื่องกลับให้นักศึกษาแก้ไขเรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin_requests'))

    student_name = req.user.fullname if getattr(req, 'user', None) else '-'
    student_code = req.user.member_id if getattr(req, 'user', None) else '-'

    img_html = f'<a href="/static/uploads/{req.doc_img}" target="_blank"><img src="/static/uploads/{req.doc_img}" class="max-h-64 rounded-2xl border border-sky-100 shadow-sm hover:opacity-90 transition"></a>' if getattr(req, 'doc_img', None) and req.doc_img != 'default_doc.png' else '<span class="text-xs text-slate-400">ไม่มีแนบรูปภาพหลักฐาน</span>'

    content = f"""
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-6">พิจารณาคำร้องเทียบโอน #{getattr(req, 'req_code', 'TR001')}</h3>
        
        <div class="grid md:grid-cols-2 gap-5 text-sm mb-6 bg-sky-50/50 p-6 rounded-2xl border border-sky-100">
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ผู้ยื่นคำร้อง</span><b class="text-slate-800">{student_name}</b> (รหัส: {student_code})</div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">หมวดวิชา</span><b class="text-slate-800">{getattr(req, 'category', 'หมวดวิชาศึกษาทั่วไป')}</b></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">รายวิชา</span><b class="text-slate-800">{getattr(req, 'course_name', '-')}</b> ({getattr(req, 'credits', 0)} หน่วยกิต)</div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ระบบออนไลน์</span><b class="text-slate-800">{getattr(req, 'institution', '-')}</b></div>
            <div class="md:col-span-2"><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-2">หลักฐานเกียรติบัตรที่แนบมา</span><div>{img_html}</div></div>
        </div>

        <form method="POST" class="space-y-4 border-t border-sky-100 pt-6">
            <div>
                <label class="block text-xs font-bold text-rose-600 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-triangle-exclamation mr-1"></i> กรณีไม่ผ่านการพิจารณา: ระบุเหตุผล / สิ่งที่ให้นักศึกษาแก้ไข</label>
                <textarea name="reject_reason" rows="3" placeholder="ระบุข้อความเพื่อแจ้งเตือนนักศึกษา..." class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></textarea>
            </div>
            <div class="flex justify-end gap-3 pt-2">
                <button type="submit" name="action" value="reject" class="px-6 py-3 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-2xl text-xs transition shadow-md">ไม่ผ่านการพิจารณา / ส่งกลับแก้ไข</button>
                <button type="submit" name="action" value="approve" class="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-2xl text-xs transition shadow-md">อนุมัติผ่านการเทียบโอน</button>
            </div>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/students')
def admin_students():
    if session.get('role') not in ['admin', 'superadmin']:
        return redirect(url_for('login'))

    try:
        students = User.query.filter_by(role='student').order_by(User.id.desc()).all()
    except Exception:
        students = []

    rows = ""
    for s in students:
        try:
            approved_credits = sum(r.credits for r in CreditRequest.query.filter_by(user_id=s.id, status='Approved').all())
        except Exception:
            approved_credits = 0

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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('username', '').strip()
        password_input = request.form.get('password', '').strip()

        try:
            user = User.query.filter((User.username == login_input) | (User.id_card == login_input)).first()
            if user and check_password_hash(user.password, password_input):
                session['user_id'] = user.id
                session['fullname'] = user.fullname
                session['role'] = user.role
                session['member_id'] = user.member_id
                return redirect(url_for('home'))
        except Exception:
            pass

        flash('ชื่อผู้ใช้งาน/เลขบัตรประชาชน หรือรหัสผ่านไม่ถูกต้อง', 'error')

    content = """
    <div class="max-w-md mx-auto my-12 bg-white p-8 sm:p-10 rounded-3xl border border-sky-100 shadow-xl text-center">
        <h2 class="text-2xl font-black text-slate-900 mb-8">เข้าสู่ระบบ</h2>
        <form method="POST" class="space-y-4 text-left">
            <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Username หรือ บัตรประชาชน</label><input type="text" name="username" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password)</label><input type="password" name="password" required class="w-full border border-sky-100 rounded-2xl p-3 text-sm bg-sky-50/50"></div>
            <button type="submit" class="w-full bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold py-3.5 rounded-2xl shadow-md text-sm mt-2">เข้าสู่ระบบ</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

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
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/profile_requests')
def admin_profile_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    
    try:
        requests_list = ProfileEditRequest.query.order_by(ProfileEditRequest.id.desc()).all()
    except Exception:
        requests_list = []

    rows = ""
    for r in requests_list:
        status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ</span>')
        actions = f'<a href="/admin/approve_profile/{r.id}" class="bg-emerald-600 text-white px-3 py-1 rounded-xl text-xs">อนุมัติ</a> <a href="/admin/reject_profile/{r.id}" class="bg-rose-600 text-white px-3 py-1 rounded-xl text-xs">ไม่อนุมัติ</a>' if getattr(r, 'status', 'Pending') == 'Pending' else '-'
        student_name = r.user.fullname if getattr(r, 'user', None) else '-'

        rows += f'<tr class="border-b border-sky-50 text-sm"><td class="py-4 px-4 font-bold">{student_name}</td><td class="py-4 px-4">{status_badge}</td><td class="py-4 px-4">{actions}</td></tr>'

    content = f'<div class="bg-white p-8 rounded-3xl shadow-sm"><table class="w-full text-left"><tbody>{rows}</tbody></table></div>'
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/approve_profile/<int:req_id>')
def approve_profile(req_id):
    if session.get('role') in ['admin', 'superadmin']:
        admin_user = User.query.get(session['user_id'])
        req = ProfileEditRequest.query.get(req_id)
        if req and req.status == 'Pending':
            user = User.query.get(req.user_id)
            if user:
                user.prefix = req.new_prefix
                user.fullname = req.new_fullname
                user.phone = req.new_phone
                user.email = req.new_email
                if req.new_address: user.address = req.new_address
            req.status = 'Approved'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('อนุมัติการแก้ไขข้อมูลส่วนตัวเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin_profile_requests'))

@app.route('/admin/reject_profile/<int:req_id>')
def reject_profile(req_id):
    if session.get('role') in ['admin', 'superadmin']:
        admin_user = User.query.get(session['user_id'])
        req = ProfileEditRequest.query.get(req_id)
        if req and req.status == 'Pending':
            req.status = 'Rejected'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('ปฏิเสธคำร้องขอแก้ไขข้อมูลเรียบร้อยแล้ว', 'error')
    return redirect(url_for('admin_profile_requests'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)