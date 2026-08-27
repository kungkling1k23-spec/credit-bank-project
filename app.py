import os
import uuid
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
# Database Auto-Reset & Migration (บังคับเพิ่มคอลัมน์ให้อัตโนมัติ)
# ==========================================
RESET_DB_FOR_PRODUCTION = False

with app.app_context():
    if RESET_DB_FOR_PRODUCTION:
        try:
            db.drop_all()
        except Exception:
            pass

    db.create_all()

    # สั่งบีบเพิ่มคอลัมน์ doc_img2 และ doc_img3 เข้า PostgreSQL โดยตรง
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

# ==========================================
# Helper Functions
# ==========================================
def generate_member_id():
    try:
        last_user = User.query.filter(User.member_id.like('IS%')).order_by(User.id.desc()).first()
        if not last_user or not last_user.member_id:
            return "IS69001"
        
        raw_num = last_user.member_id.replace("IS", "")
        last_num = int(raw_num)
        return f"IS{last_num + 1:05d}"
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
# Layout Template (ปรับสีทึบแน่น 100% Solid Sky Blue)
# ==========================================
LAYOUT_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ธนาคารหน่วยกิต IS RMUTTO - มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
    body { font-family: 'Sarabun', sans-serif; background-color: #f8fafc; }
    .hero-sky { background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 50%, #7dd3fc 100%); }
    .sidebar-transition { transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
    .sidebar-expanded { width: 270px; }
    .sidebar-collapsed { width: 80px; }
    .sidebar-collapsed .nav-text, .sidebar-collapsed .logo-img-full, .sidebar-collapsed .section-title { display: none !important; }
    .sidebar-collapsed .logo-img-small { display: block !important; }
    .sidebar-collapsed .toggle-icon { transform: rotate(180deg); }
    </style>
</head>
<body class="bg-sky-50 min-h-screen text-slate-800 antialiased flex flex-col md:flex-row">

    <!-- Mobile Top Header (สีฟ้าทึบแน่น 100% ไม่ซ้อน) -->
    <div class="md:hidden bg-sky-200 text-slate-900 p-3.5 flex justify-between items-center sticky top-0 z-50 border-b-2 border-sky-300 shadow-md">
        <a href="/" class="flex items-center gap-2 px-2 py-1">
            <img src="/static/images/logo.png" alt="IS RMUTTO Credit Bank" class="h-10 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS+RMUTTO';">
        </a>
        <button id="mobile-toggle" class="p-2 text-sky-900 hover:text-black focus:outline-none"><i class="fa-solid fa-bars text-2xl"></i></button>
    </div>

    <!-- Collapsible Left Sidebar (ปรับเป็นสีฟ้าทึบแน่น bg-sky-200 / bg-sky-100 ป้องกันการซ้อนทับ 100%) -->
    <aside id="sidebar" class="sidebar-expanded sidebar-transition bg-sky-100/80 text-slate-800 h-screen flex flex-col fixed md:sticky top-0 z-40 shadow-lg border-r border-sky-200 hidden md:flex shrink-0">

    <div class="p-4 flex flex-col border-b border-sky-200 bg-sky-200/50 shrink-0">
        <a href="/" class="flex items-center justify-center py-1 px-1">
            <!-- แก้ max-h-14 เพื่อไม่ให้โลโก้ขาด -->
            <img src="/static/images/logo.png" alt="IS RMUTTO Logo" class="w-auto max-h-14 object-contain logo-img-full" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x60?text=IS+RMUTTO';">
            <div class="logo-img-small hidden">
                <div class="w-10 h-10 bg-sky-600 text-white rounded-2xl flex items-center justify-center font-black text-lg shadow-sm">IS</div>
            </div>
        </a>

        <div class="mt-2 pt-2 border-t border-sky-300/60 flex justify-center">
            <button id="sidebar-toggle" class="w-full py-1.5 px-3 rounded-xl bg-white/80 hover:bg-white text-sky-900 flex items-center justify-center gap-2 border border-sky-200 font-bold shadow-sm transition">
                <i class="fa-solid fa-chevron-left text-xs toggle-icon transition-transform"></i>
                <span class="nav-text text-xs">ย่อแถบเมนู</span>
            </button>
        </div>
    </div>

        <!-- Navigation Links (พื้นหลังสีทึบ) -->
        <div class="flex-grow p-4 space-y-1.5 overflow-y-auto bg-sky-200">
            <p class="section-title text-[11px] font-black text-sky-800 uppercase tracking-wider px-3 mb-2 pt-2">เมนูหลัก</p>
            
            <a href="/" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                <i class="fa-solid fa-house text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                <span class="nav-text">หน้าแรก</span>
            </a>

            {% if session.get('user_id') %}
                {% if session.get('role') in ['admin', 'superadmin'] %}
                    <p class="section-title text-[11px] font-black text-sky-800 uppercase tracking-wider px-3 mb-2 pt-4">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/students" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-users text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">รายชื่อนักศึกษา</span>
                    </a>
                    <a href="/admin/requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-file-signature text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">คำร้องเทียบโอน</span>
                    </a>
                    <a href="/admin/profile_requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-user-pen text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">คำร้องแก้ไขข้อมูล</span>
                    </a>
                    <a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-sky-950 bg-sky-300 border border-sky-400 hover:bg-sky-400 transition-all font-extrabold text-sm group mt-2">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-sky-800"></i>
                        <span class="nav-text">เพิ่ม/จัดการเจ้าหน้าที่</span>
                    </a>
                {% else %}
                    <p class="section-title text-[11px] font-black text-sky-800 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-magnifying-glass text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">ค้นหารายวิชา</span>
                    </a>
                    <a href="/submit_credit" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-file-circle-plus text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">ยื่นคำขอเทียบโอน</span>
                    </a>
                    <a href="/credits" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-graduation-cap text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">หน่วยกิตสะสม</span>
                    </a>
                    <a href="/history" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group">
                        <i class="fa-solid fa-clock-rotate-left text-lg w-6 text-center text-sky-700 group-hover:text-sky-900 transition-colors"></i>
                        <span class="nav-text">ประวัติคำขอ</span>
                    </a>
                {% endif %}
            {% else %}
                <div class="pt-4 space-y-2">
                    <a href="/login" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-800 hover:text-sky-950 hover:bg-sky-300 transition-all font-bold text-sm group border border-sky-300">
                        <i class="fa-solid fa-right-to-bracket text-lg w-6 text-center text-sky-700 group-hover:text-sky-900"></i>
                        <span class="nav-text">เข้าสู่ระบบ</span>
                    </a>
                    <a href="/register" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl bg-sky-600 hover:bg-sky-700 text-white font-extrabold transition-all text-sm group shadow-md">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-sky-100"></i>
                        <span class="nav-text">ลงทะเบียนนักศึกษา</span>
                    </a>
                </div>
            {% endif %}
        </div>

        <!-- Footer Profile Link -->
        {% if session.get('user_id') %}
            <div class="p-4 border-t-2 border-sky-300 bg-sky-300">
                <a href="/profile" class="flex items-center gap-3 p-2 rounded-2xl hover:bg-sky-200 transition-all group border border-transparent">
                    <div class="w-9 h-9 rounded-xl bg-sky-100 text-sky-800 font-bold flex items-center justify-center shrink-0">
                        <i class="fa-regular fa-user"></i>
                    </div>
                    <div class="flex flex-col min-w-0 nav-text">
                        <span class="text-xs font-black text-slate-900 truncate">{{ session.get('fullname', 'ผู้ใช้งาน') }}</span>
                        <span class="text-[10px] text-sky-800 capitalize font-extrabold">{% if session.get('role') in ['admin', 'superadmin'] %}เจ้าหน้าที่{% else %}นักศึกษาสาขา IS{% endif %}</span>
                    </div>
                </a>
                <a href="/logout" class="mt-2 flex items-center gap-3 px-3 py-2 text-xs font-extrabold text-rose-700 hover:bg-rose-100 rounded-xl transition-all">
                    <i class="fa-solid fa-arrow-right-from-bracket text-sm w-6 text-center"></i>
                    <span class="nav-text">ออกจากระบบ</span>
                </a>
            </div>
        {% endif %}
    </aside>

    <!-- Main Content Area -->
    <div class="flex-grow flex flex-col min-h-screen min-w-0">
        
        <!-- Flash Alert Messages -->
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

        <!-- Footer ด้านล่างสีฟ้าทึบแน่น 100% -->
        <footer class="bg-sky-200 text-slate-800 mt-auto border-t-2 border-sky-300 shadow-md">
            <div class="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
                <div class="flex flex-col md:flex-row items-center justify-between gap-4 text-xs font-semibold text-center md:text-left">
                    <div class="flex items-center gap-3">
                        <img src="/static/images/logo.png" alt="IS RMUTTO Logo" class="h-10 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS+RMUTTO';">
                        <div>
                            <p class="text-sky-950 font-black text-sm">สาขาวิชาระบบสารสนเทศ (Information Systems)</p>
                            <p class="text-slate-700 mt-0.5 font-bold">คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก</p>
                        </div>
                    </div>
                    <div class="text-slate-700 leading-relaxed font-extrabold">
                        © 2026 Credit Bank System (Information Systems Major).
                    </div>
                </div>
            </div>
        </footer>
    </div>

    <!-- JavaScript for Collapsible Sidebar -->
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
# THAIMOOC & CHULAMOOC IS DATABASE
# ==========================================
IS_THAIMOOC_COURSES = [
    {"code": "15-02-002", "name": "คุณภาพการใช้ชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ชีวิตและการสร้างคุณค่า (2 ชม.)", "2. การคิดสร้างสรรค์เพื่อการพัฒนาตนเอง (5 ชม.)"], "hours": "7 ชม.", "credits": 3},
    {"code": "15-02-003", "name": "การคิดอย่างมีวิจารณญาณและการแก้ปัญหา", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. การคิดเชิงวิพากษ์และการจัดการปัญหา (5 ชม.)", "2. การคิดแก้ปัญหาเชิงสร้างสรรค์ (6 ชม.)"], "hours": "11 ชม.", "credits": 3},
    {"code": "15-02-004", "name": "คุณธรรมจริยธรรมในโลกเทคโนโลยีสารสนเทศ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["จริยธรรมสารสนเทศสำหรับพลเมืองดิจิทัล (7 ชม.)"], "hours": "7 ชม.", "credits": 3},
    {"code": "15-03-005", "name": "ผู้ประกอบการนวัตกรรม", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["การเป็นผู้ประกอบการในศตวรรษที่ 21 (30 ชม.)"], "hours": "30 ชม.", "credits": 3},
    {"code": "15-03-006", "name": "การจัดการเศรษฐกิจชีวภาพ เศรษฐกิจหมุนเวียน และเศรษฐกิจสีเขียว", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ชุมชนแห่งความยั่งยืน (2 ชม.)", "2. หลักเศรษฐศาสตร์เกษตร (6 ชม.)"], "hours": "8 ชม.", "credits": 3},
    {"code": "15-03-007", "name": "เทคโนโลยีสารสนเทศในยุคดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["เทคโนโลยีสารสนเทศในยุคดิจิทัล (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-008", "name": "คณิตศาสตร์และสถิติเพื่อการประกอบอาชีพ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["สถิติธุรกิจ (สถิติเรื่องใกล้ตัว…ไม่น่ากลัวอย่างที่คิด) (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-009", "name": "ภูมิปัญญาเพื่อการประกอบอาชีพ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ภูมิปัญญาไทย กับการพัฒนาการเกษตรอย่างยั่งยืน (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-010", "name": "การวิเคราะห์และนำเสนอข้อมูลด้วยเทคโนโลยีดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. การออกแบบการนำเสนองานอย่างสร้างสรรค์และทันสมัย (10 ชม.)", "2. คอมพิวเตอร์เพื่อการพูดและการนำเสนอ (6 ชม.)"], "hours": "16 ชม.", "credits": 3},
    {"code": "15-03-011", "name": "ผู้ประกอบการดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["การตลาดดิจิทัลสำหรับผู้ประกอบการธุรกิจชุมชน (5 ชม.)"], "hours": "5 ชม.", "credits": 3},
    {"code": "15-03-014", "name": "การพัฒนาศักยภาพเพื่อมุ่งสู่การเป็นผู้ประกอบการมือใหม่", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["การเริ่มต้นเป็นผู้ประกอบการรายใหม่ (A new entrepreneur) (30 ชม.)"], "hours": "30 ชม.", "credits": 3},
    {"code": "15-03-015", "name": "ศาสตร์แห่งการสื่อสาร", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ทักษะการสื่อสารระหว่างบุคคลในการทำงาน (10 ชม.)", "2. การสื่อสารและการประสานงาน (5 ชม.)"], "hours": "15 ชม.", "credits": 3},
    {"code": "15-03-016", "name": "ภาษาอังกฤษเพื่อการสื่อสาร", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ภาษาอังกฤษเพื่อการสื่อสาร (10 ชม.)", "2. ภาษาอังกฤษเพื่อการสื่อสารในสังคม (4 ชม.)"], "hours": "14 ชม.", "credits": 3},
    {"code": "15-03-018", "name": "การใช้ภาษาไทยในชีวิตประจำวัน", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["การใช้ภาษาไทย หรือ ภาษาไทยเพื่อการสื่อสารร่วมสมัย (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-019", "name": "ทักษะภาษาอังกฤษสำหรับผู้ประกอบการออนไลน์", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ง่ายสบายกับการอธิบายกราฟเป็นภาษาอังกฤษ (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-020", "name": "ทักษะการเรียนภาษาอังกฤษผ่านสื่ออิเล็กทรอนิกส์", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ภาษาอังกฤษสำหรับเทคโนโลยีสารสนเทศ (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-021", "name": "เทคนิคการพูดเพื่อความสำเร็จ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["รู้รอบด้านการนำเสนอ (5 ชม.)"], "hours": "5 ชม.", "credits": 3},
    {"code": "15-05-024", "name": "ทักษะชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["ทักษะทางสังคม (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "15-06-027", "name": "ความเป็นพลเมืองไทยและพลเมืองโลก", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["1. ความเป็นพลเมืองโลก (3 ชม.)", "2. การเป็นพลเมือง (10 ชม.)"], "hours": "13 ชม.", "credits": 3},
    {"code": "15-06-028", "name": "วิถีโลก", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["กลยุทธ์สู่ประชาคมอาเซียน: การเมือง เศรษฐกิจ และสังคม (8 ชม.)"], "hours": "8 ชม.", "credits": 3},
    {"code": "15-06-029", "name": "สังคมและวัฒนธรรมไทย", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc_list": ["อารยธรรมและภูมิปัญญาท้องถิ่น (1 ชม.)"], "hours": "1 ชม.", "credits": 3},

    # กลุ่มวิชาแกน (ThaiMOOC & ChulaMOOC)
    {"code": "04-00-101", "name": "หลักการตลาด", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. การจัดการเชิงกลยุทธ์และการตลาดในยุคโลกาภิวัตน์ (10 ชม.)", "2. การตลาดเชิงสร้างสรรค์ (6 ชม.)"], "hours": "16 ชม.", "credits": 3},
    {"code": "04-00-102", "name": "หลักเศรษฐศาสตร์ (Principles of Economics)", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["เศรษฐศาสตร์ตลาดการเงิน (10 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "04-00-103", "name": "องค์การและการจัดการ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. การบริหารจัดการในศตวรรษที่ 21 (6 ชม.)", "2. การจัดการธุรกิจการค้าสมัยใหม่ในยุค Thailand 4.0 (6 ชม.)"], "hours": "12 ชม.", "credits": 3},
    {"code": "04-00-104", "name": "กฎหมายธุรกิจและการภาษีอากร", "group": "หมวดวิชาแกน", "provider": "ChulaMOOC", "mooc_list": ["1. กฎหมายกับธุรกิจ Law for Business: กฎหมายกับธุรกิจยุค Thailand 4.0 และภาษี", "2. กฎหมายกับธุรกิจ Law for Business: กฎหมายพื้นฐานสำหรับธุรกิจ"], "hours": "ChulaMOOC", "credits": 3},
    {"code": "04-00-105", "name": "สถิติเพื่อการวิจัยธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. สถิติและการวิเคราะห์ข้อมูลเบื้องต้น (4 ชม.)", "2. วิจัยทางธุรกิจ (6 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "04-00-106", "name": "ภาษาอังกฤษเพื่อการสื่อสารธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["สตาร์ทอัพอังกฤษ (30 ชม.)"], "hours": "30 ชม.", "credits": 3},
    {"code": "04-00-107", "name": "การบัญชีเบื้องต้นเพื่อการบริหาร", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. บัญชีเบื้องต้น (5 ชม.)", "2. การบัญชีบริหาร (10 ชม.)"], "hours": "15 ชม.", "credits": 3},
    {"code": "04-00-108", "name": "การเงินธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. การบัญชีเพื่อการจัดการและการจัดการทางการเงิน (10 ชม.)", "2. การเงินสำหรับการเริ่มต้นธุรกิจ SET (1 ชม.)"], "hours": "11 ชม.", "credits": 3},
    {"code": "04-00-109", "name": "การจัดการโลจิสติกส์และห่วงโซ่อุปทาน", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. โลจิสติกส์และโซ่อุปทานเบื้องต้น (10 ชม.)", "2. การจัดการคลังสินค้า (10 ชม.)"], "hours": "20 ชม.", "credits": 3},
    {"code": "04-00-110", "name": "ทักษะความเข้าใจและการใช้เทคโนโลยีดิจิทัล", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc_list": ["1. การเข้าใจดิจิทัล (15 ชม.)", "2. ทักษะความเข้าใจความมั่นคงปลอดภัยทางไซเบอร์ (4 ชม.)"], "hours": "19 ชม.", "credits": 3},

    # กลุ่มวิชาเลือก (ThaiMOOC)
    {"code": "04-05-141", "name": "วิทยาการสารสนเทศทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. วิทยาการข้อมูลเบื้องต้น (6 ชม.)", "2. วิทยาการข้อมูลและการประยุกต์ใช้ (30 ชม.)"], "hours": "36 ชม.", "credits": 3},
    {"code": "04-05-232", "name": "การคิดเชิงออกแบบสำหรับนวัตกรรมทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["ปฏิบัติการคิดเชิงออกแบบนวัตกรรม (12 ชม.)"], "hours": "12 ชม.", "credits": 3},
    {"code": "04-05-233", "name": "ธุรกิจดิจิทัลผ่านสื่อสังคมออนไลน์", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. มาตรฐานการผลิตสื่อดิจิทัล (5 ชม.)", "2. การสร้างสรรค์สื่อดิจิทัลบนเครือข่ายสังคมออนไลน์ (5 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "04-05-234", "name": "เครือข่ายคอมพิวเตอร์และความปลอดภัยสำหรับธุรกิจดิจิทัล", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["เครือข่ายและความปลอดภัย (5 ชม.)"], "hours": "5 ชม.", "credits": 3},
    {"code": "04-05-241", "name": "การวิเคราะห์ข้อมูลทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. การเตรียมข้อมูล (12 ชม.)", "2. การวิเคราะห์ข้อมูลสำหรับการจัดการทางธุรกิจ (3 ชม.)"], "hours": "15 ชม.", "credits": 3},
    {"code": "04-05-342", "name": "ระบบสนับสนุนการตัดสินใจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. ระบบสนับสนุนการตัดสินใจสำหรับองค์กรธุรกิจ (6 ชม.)", "2. การตัดสินใจโดยการขับเคลื่อนด้วยข้อมูล (4 ชม.)"], "hours": "10 ชม.", "credits": 3},
    {"code": "04-05-441", "name": "ความคิดสร้างสรรค์และนวัตกรรมในการวิเคราะห์ข้อมูล", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. การสร้างสรรค์เนื้อหาด้วยข้อมูล Data (4 ชม.)", "2. การตัดสินใจโดยการขับเคลื่อนด้วยข้อมูล (4 ชม.)"], "hours": "8 ชม.", "credits": 3},
    {"code": "04-05-443", "name": "การบริหารโครงการระบบสารสนเทศ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc_list": ["1. การวิเคราะห์โครงการและแผนงานยุคดิจิทัล (15 ชม.)", "2. การบริหารโครงการ IT แบบมืออาชีพ (3 ชม.)"], "hours": "18 ชม.", "credits": 3}
]

# ==========================================
# Routes & Controllers
# ==========================================
@app.route('/')
def home():
    if not session.get('user_id'):
       content = f"""
    <div class="mb-6">
        <h2 class="text-3xl font-black text-slate-900">สวัสดีครับ, {user.fullname}</h2>
        <p class="text-xs font-bold text-sky-700 mt-1">รหัสนักศึกษา: {user.member_id} (สาขาวิชาระบบสารสนเทศ)</p>
    </div>

    <!-- เหลือ 3 การ์ดสมดุลพอดี -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">หน่วยกิตสะสมที่อนุมัติแล้ว</p>
                <h3 class="text-3xl font-black text-sky-600">{approved_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">หน่วยกิตรออนุมัติเทียบโอน</p>
                <h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-hourglass-half"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องขอเทียบโอนทั้งหมด</p>
                <h3 class="text-3xl font-black text-slate-800">{len(user_requests)} <span class="text-xs font-medium text-slate-400">รายการ</span></h3>
            </div>
            <div class="w-12 h-12 bg-purple-50 text-purple-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-list-check"></i></div>
        </div>
    </div>
    """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    try:
        user = User.query.get(session['user_id'])
    except Exception:
        session.clear()
        return redirect(url_for('login'))

    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    if user.role in ['admin', 'superadmin']:
        try:
            pending_credits = CreditRequest.query.filter_by(status='Pending').count()
            pending_edits = ProfileEditRequest.query.filter_by(status='Pending').count()
            total_members = User.query.filter_by(role='student').count()
            total_admins = User.query.filter(User.role.in_(['admin', 'superadmin'])).count()
        except Exception:
            pending_credits, pending_edits, total_members, total_admins = 0, 0, 0, 1

        content = f"""
        <div class="mb-8">
            <h2 class="text-2xl font-extrabold text-slate-900">ยินดีต้อนรับ, เจ้าหน้าที่ประจำสาขาวิชาระบบสารสนเทศ</h2>
            <p class="text-slate-600 text-sm mt-1 font-semibold">แผงควบคุมระบบตรวจสอบและอนุมัติสำหรับเจ้าหน้าที่ ({user.fullname})</p>
        </div>

        <div class="mb-8">
            <a href="/admin/manage_admins" class="bg-sky-600 hover:bg-sky-700 text-white p-7 rounded-3xl shadow-md flex items-center justify-between transition-all block border-2 border-sky-400">
                <div>
                    <div class="flex items-center gap-2 mb-2">
                        <span class="bg-white/20 text-white text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider shadow-sm border border-white/30">แอดมินจัดการ</span>
                        <h3 class="text-2xl font-extrabold text-white">➕ เพิ่มเจ้าหน้าที่ตรวจงานระบบสารสนเทศ</h3>
                    </div>
                    <p class="text-sm text-sky-100 font-medium">เพิ่มบัญชีเจ้าหน้าที่ใหม่ด้วยเลขบัตรประชาชนและรหัสผ่านส่วนตัว (ปัจจุบันมีเจ้าหน้าที่ {total_admins} คน)</p>
                </div>
                <div class="w-14 h-14 bg-white/20 text-white rounded-2xl flex items-center justify-center text-2xl shrink-0 backdrop-blur"><i class="fa-solid fa-user-plus"></i></div>
            </a>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <a href="/admin/students" class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between hover:border-sky-400 transition card-hover">
                <div>
                    <p class="text-xs font-black text-slate-500 uppercase tracking-wider mb-1">นักศึกษาสาขา IS ในระบบ</p>
                    <h3 class="text-3xl font-black text-slate-900">{total_members} <span class="text-xs text-slate-400 font-normal">คน</span></h3>
                </div>
                <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-users"></i></div>
            </a>
            <a href="/admin/requests" class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between hover:border-amber-400 transition card-hover">
                <div>
                    <p class="text-xs font-black text-slate-500 uppercase tracking-wider mb-1">คำร้องเทียบโอนค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-file-signature"></i></div>
            </a>
            <a href="/admin/profile_requests" class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between hover:border-indigo-400 transition card-hover">
                <div>
                    <p class="text-xs font-black text-slate-500 uppercase tracking-wider mb-1">คำร้องแก้ไขข้อมูลค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-indigo-500">{pending_edits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-indigo-50 text-indigo-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-user-pen"></i></div>
            </a>
        </div>
        """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    try:
        user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
    except Exception:
        user_requests = []

    approved_reqs = [r for r in user_requests if getattr(r, 'status', '') == 'Approved']
    approved_credits = sum(getattr(r, 'credits', 0) for r in approved_reqs)
    pending_credits = sum(getattr(r, 'credits', 0) for r in user_requests if getattr(r, 'status', '') == 'Pending')
    remaining_credits = max(0, 120 - approved_credits - pending_credits)

    content = f"""
    <div class="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
            <h2 class="text-3xl font-black text-slate-900">สวัสดีครับ, {user.prefix or ''} {user.fullname}</h2>
            <p class="text-sm font-black text-sky-700 mt-1"><i class="fa-solid fa-id-card mr-1 text-sky-500"></i> รหัสนักศึกษา: {user.member_id or '-'} (สาขาวิชาระบบสารสนเทศ)</p>
        </div>
        <a href="/submit_credit" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-6 py-3 rounded-2xl shadow-md transition-all inline-flex items-center gap-2 text-sm shrink-0">
            <i class="fa-solid fa-file-circle-plus text-sky-100"></i> ยื่นคำขอเทียบโอนออนไลน์
        </a>
    </div>

    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <div class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">หน่วยกิตสะสมทั้งหมด</p>
                <h3 class="text-3xl font-black text-sky-600">{approved_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">รออนุมัติเทียบโอน</p>
                <h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-hourglass-half"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องขอเทียบโอน</p>
                <h3 class="text-3xl font-black text-slate-800">{len(user_requests)} <span class="text-xs font-medium text-slate-400">รายการ</span></h3>
            </div>
            <div class="w-12 h-12 bg-purple-50 text-purple-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-list-check"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border-2 border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">เป้าหมายหลักสูตร IS</p>
                <h3 class="text-3xl font-black text-emerald-500">120 <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-emerald-50 text-emerald-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-bullseye"></i></div>
        </div>
    </div>

    <!-- Charts -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div class="bg-white p-6 rounded-3xl border-2 border-sky-100 shadow-sm">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-chart-pie text-sky-600"></i> ความก้าวหน้าหน่วยกิตสาขา IS
            </h3>
            <div class="w-full max-w-[240px] mx-auto py-2">
                <canvas id="creditDoughnutChart"></canvas>
            </div>
        </div>

        <div class="bg-white p-6 rounded-3xl border-2 border-sky-100 shadow-sm lg:col-span-2">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-chart-column text-sky-600"></i> สรุปการสะสมหน่วยกิตจำแนกตามหมวดวิชา
            </h3>
            <div class="w-full h-56">
                <canvas id="creditBarChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Quick Access Actions -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <a href="/available_courses" class="bg-white p-7 rounded-3xl border-2 border-sky-100 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-magnifying-glass"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-sky-600 transition-colors">ค้นหารายวิชา</h3>
            <p class="text-xs text-slate-500 leading-relaxed font-medium">ค้นหารายวิชาออนไลน์ที่เทียบโอนเข้าหลักสูตรสาขาวิชาระบบสารสนเทศ</p>
        </a>
        <a href="/submit_credit" class="bg-white p-7 rounded-3xl border-2 border-sky-100 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-file-pen"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-amber-500 transition-colors">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
            <p class="text-xs text-slate-500 leading-relaxed font-medium">เลือกวิชาที่ต้องเรียนเพิ่ม พร้อมอัปโหลดรูปเกียรติบัตรยื่นเทียบโอน</p>
        </a>
        <a href="/request_edit_profile" class="bg-white p-7 rounded-3xl border-2 border-sky-100 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-purple-50 text-purple-500 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-user-gear"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-purple-500 transition-colors">ขอแก้ไขข้อมูลส่วนตัว</h3>
            <p class="text-xs text-slate-500 leading-relaxed font-medium">แจ้งเรื่องขอเปลี่ยนชื่อ-สกุล อีเมล หรือเบอร์โทรศัพท์ถึงเจ้าหน้าที่ประจำสาขา</p>
        </a>
    </div>

    <script>
        const ctxDoughnut = document.getElementById('creditDoughnutChart').getContext('2d');
        new Chart(ctxDoughnut, {{
            type: 'doughnut',
            data: {{
                labels: ['อนุมัติแล้ว', 'รอพิจารณา', 'คงเหลือถึงเป้าหมาย'],
                datasets: [{{
                    data: [{approved_credits}, {pending_credits}, {remaining_credits}],
                    backgroundColor: ['#0284c7', '#f59e0b', '#cbd5e1'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom', labels: {{ font: {{ family: 'Sarabun', size: 12 }} }} }}
                }},
                cutout: '70%'
            }}
        }});

        const ctxBar = document.getElementById('creditBarChart').getContext('2d');
        new Chart(ctxBar, {{
            type: 'bar',
            data: {{
                labels: ['หมวดวิชาศึกษาทั่วไป', 'หมวดวิชาแกน', 'หมวดวิชาเลือก'],
                datasets: [{{
                    label: 'หน่วยกิตสะสม (อนุมัติแล้ว)',
                    data: [{approved_credits}, {approved_credits}, 0],
                    backgroundColor: '#0284c7',
                    borderRadius: 8
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ beginAtZero: true, max: 60 }}
                }},
                plugins: {{
                    legend: {{ display: false }}
                }}
            }}
        }});
    </script>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: 
        return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip().lower()
    selected_group = request.args.get('group', '').strip()
    selected_provider = request.args.get('provider', '').strip()

    filtered_courses = IS_THAIMOOC_COURSES

    if selected_provider and selected_provider != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['provider'] == selected_provider]

    if selected_group and selected_group != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['group'] == selected_group]

    if search_query:
        filtered_courses = [c for c in filtered_courses if search_query in c['name'].lower() or search_query in c['code'].lower() or any(search_query in m.lower() for m in c['mooc_list'])]

    cards = ""
    for c in filtered_courses:
        badge_provider = "bg-sky-200 text-sky-900 border-sky-300" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-900 border-amber-300"
        mooc_items_html = "".join([f'<li class="flex items-start gap-1.5"><i class="fa-solid fa-angle-right text-sky-600 mt-1 shrink-0"></i><span>{m}</span></li>' for m in c['mooc_list']])

        cards += f"""
        <div class="bg-white rounded-3xl border-2 border-sky-100 p-6 shadow-sm flex flex-col justify-between card-hover">
            <div>
                <div class="flex flex-wrap items-center justify-between gap-2 mb-4 pb-3 border-b border-sky-100">
                    <span class="font-mono text-xs font-bold bg-sky-100 text-sky-800 px-3 py-1 rounded-xl border border-sky-200 shrink-0">
                        {c['code']}
                    </span>
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="px-2.5 py-1 rounded-xl text-[11px] font-black border {badge_provider} shrink-0">
                            {c['provider']}
                        </span>
                        <span class="bg-slate-100 text-slate-700 text-[11px] px-2.5 py-1 rounded-xl font-bold border border-slate-300 shrink-0">
                            {c['group']}
                        </span>
                    </div>
                </div>

                <h3 class="text-lg font-extrabold text-slate-900 mb-2 leading-snug">{c['name']}</h3>
                <p class="text-xs text-slate-500 font-bold mb-3"><i class="fa-solid fa-graduation-cap text-sky-500 mr-1"></i> สาขาวิชาระบบสารสนเทศ (3 หน่วยกิต)</p>
                
                <div class="bg-sky-50 p-4 rounded-2xl border border-sky-200 mb-4">
                    <p class="text-xs font-black text-slate-800 mb-2 flex items-center gap-1">
                        <i class="fa-solid fa-laptop-code text-sky-700"></i> บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม ({c['provider']}):
                    </p>
                    <ul class="text-xs text-slate-700 leading-relaxed space-y-1.5 font-semibold">
                        {mooc_items_html}
                    </ul>
                </div>
            </div>

            <div class="border-t border-sky-100 pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-slate-600 mb-4">
                    <span><i class="fa-regular fa-clock mr-1 text-slate-500"></i> รวมเวลาเรียน: <b>{c['hours']}</b></span>
                    <span class="font-black text-sky-800 text-sm bg-sky-100 px-3 py-1 rounded-xl border border-sky-200">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['provider'] + '&credits=' + str(c['credits']) + '&cat=' + c['group'] + '&major_select=สาขาวิชาระบบสารสนเทศ#form_section" class="block text-center w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3 rounded-2xl text-sm transition shadow-md">ยื่นเทียบโอนวิชานี้</a>' if session.get('role') not in ['admin', 'superadmin'] else ''}
            </div>
        </div>
        """

    content = f"""
    <div class="hero-sky text-slate-900 p-8 rounded-3xl shadow-sm mb-8 flex flex-col md:flex-row justify-between items-center gap-6 border-2 border-sky-300">
        <div>
            <span class="bg-white text-sky-900 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-wider mb-2 inline-block border border-sky-200">Search Courses</span>
            <h2 class="text-3xl font-black text-slate-900">🔍 ค้นหารายวิชาเทียบโอนหลักสูตร</h2>
            <p class="text-slate-800 text-xs mt-1.5 leading-relaxed font-bold">ค้นหารายวิชาในหลักสูตรสาขาวิชาระบบสารสนเทศ และบทเรียนออนไลน์ที่ใช้เปิดเทียบโอน</p>
        </div>
        <div class="bg-white px-6 py-4 rounded-2xl border-2 border-sky-200 text-center shrink-0 shadow-sm">
            <span class="text-xs text-slate-600 block font-bold">จำนวนรายวิชาที่พบ</span>
            <span class="text-3xl font-black text-sky-700">{len(filtered_courses)}</span> <span class="text-xs text-slate-600 font-bold">/ {len(IS_THAIMOOC_COURSES)} วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-6 rounded-3xl border-2 border-sky-100 shadow-sm mb-8 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-globe mr-1 text-sky-500"></i> สื่อการเรียนรู้ (Provider)</label>
                <select name="provider" onchange="this.form.submit()" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    <option value="ทั้งหมด" {'selected' if selected_provider=='ทั้งหมด' or not selected_provider else ''}>ทุกระบบ (Thai & Chula MOOC)</option>
                    <option value="ThaiMOOC" {'selected' if selected_provider=='ThaiMOOC' else ''}>ThaiMOOC</option>
                    <option value="ChulaMOOC" {'selected' if selected_provider=='ChulaMOOC' else ''}>ChulaMOOC</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-layer-group mr-1 text-sky-600"></i> หมวดวิชาหลักสูตร</label>
                <select name="group" onchange="this.form.submit()" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    <option value="ทั้งหมด" {'selected' if selected_group=='ทั้งหมด' or not selected_group else ''}>ทุกหมวดวิชา</option>
                    <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if selected_group=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                    <option value="หมวดวิชาแกน" {'selected' if selected_group=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                    <option value="หมวดวิชาเลือก" {'selected' if selected_group=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                </select>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-magnifying-glass mr-1 text-sky-600"></i> ค้นหาด้วยรหัสวิชา / ชื่อวิชา / วิชา MOOC</label>
                <div class="flex gap-2">
                    <input type="text" name="search" value="{search_query}" placeholder="พิมพ์ชื่อวิชา..." class="w-full px-4 py-3 border-2 border-sky-100 rounded-2xl text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    <button type="submit" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-7 py-3 rounded-2xl text-sm transition shadow-md shrink-0">ค้นหา</button>
                </div>
            </div>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-16 text-slate-400 bg-white rounded-3xl border-2 border-sky-100 font-bold">ไม่พบรายวิชาที่ตรงกับเงื่อนไขการค้นหา</div>'}
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            credits_val = int(request.form.get('credits', 3))
            course_name = request.form.get('course_name', '').strip()
            institution = request.form.get('institution', 'ThaiMOOC')
            category = request.form.get('category', 'หมวดวิชาศึกษาทั่วไป')
            
            # ดึงไฟล์ที่แนบมา (รองรับเลือกพร้อมกันหลายไฟล์)
            files = request.files.getlist('cert_files')
            uploaded_docs = []
            
            for file in files[:3]:  # วนลูปเซฟไฟล์ ไม่เกิน 3 รูป
                if file and file.filename != '' and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    fn = f"cert_{uuid.uuid4().hex[:8]}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    uploaded_docs.append(fn)

            doc1 = uploaded_docs[0] if len(uploaded_docs) > 0 else "default_doc.png"
            doc2 = uploaded_docs[1] if len(uploaded_docs) > 1 else None
            doc3 = uploaded_docs[2] if len(uploaded_docs) > 2 else None

            req = CreditRequest(
                req_code=f"TR2569{uuid.uuid4().hex[:4].upper()}",
                user_id=session['user_id'],
                course_name=course_name,
                institution=institution,
                credits=credits_val,
                category=category,
                date_submitted=datetime.now().strftime("%Y-%m-%d"),
                doc_img=doc1,
                doc_img2=doc2,
                doc_img3=doc3,
                status='Pending'
            )
            db.session.add(req)
            db.session.commit()
            flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว!', 'success')
            return redirect(url_for('history'))
        except Exception as e:
            db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {str(e)}', 'error')

    # ส่วนของ HTML Form
    init_course = request.args.get('course', '')
    init_inst = request.args.get('inst', 'ThaiMOOC')
    init_credits = request.args.get('credits', '3')

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-1">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
        <p class="text-xs text-slate-500 mb-6 font-medium">กรอกรายละเอียดและแนบรูปภาพใบประกาศนียบัตร (แนบได้ 1 ถึง 3 รูป)</p>

        <form method="POST" enctype="multipart/form-data" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">ชื่อรายวิชาในหลักสูตร *</label>
                <input type="text" name="course_name" value="{init_course}" required placeholder="เช่น คุณภาพการใช้ชีวิต" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold focus:outline-none focus:ring-2 focus:ring-sky-400">
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">ระบบออนไลน์ *</label>
                    <select name="institution" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold focus:outline-none focus:ring-2 focus:ring-sky-400">
                        <option value="ThaiMOOC" {'selected' if init_inst=='ThaiMOOC' else ''}>ThaiMOOC</option>
                        <option value="ChulaMOOC" {'selected' if init_inst=='ChulaMOOC' else ''}>ChulaMOOC</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">จำนวนหน่วยกิต *</label>
                    <input type="number" name="credits" value="{init_credits}" min="1" max="10" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold focus:outline-none focus:ring-2 focus:ring-sky-400">
                </div>
            </div>

            <!-- Input แหล่งอัปโหลดรูป 1-3 รูป -->
            <div class="border-t border-sky-100 pt-4">
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5"><i class="fa-solid fa-images mr-1 text-sky-600"></i> แนบรูปภาพใบประกาศ / เกียรติบัตร (1 - 3 รูป) *</label>
                <input type="file" name="cert_files" accept="image/*,.pdf" multiple required class="w-full border border-sky-200 rounded-2xl p-2 text-xs bg-sky-50/40 font-semibold file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-sky-600 file:text-white hover:file:bg-sky-700 transition">
                <p class="text-[11px] text-slate-400 mt-1 font-medium">สามารถกดเลือกทีละหลายไฟล์ได้ไม่เกิน 3 รูป (PNG, JPG, PDF)</p>
            </div>

            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-2">
                <i class="fa-solid fa-paper-plane mr-1"></i> ยืนยันยื่นคำขอเทียบโอน
            </button>
        </form>
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
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">รอการพิจารณา</span>'
            action_btn = '-'
        elif status == 'Approved':
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">อนุมัติแล้ว</span>'
            action_btn = '-'
        else: # Rejected
            badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">ไม่อนุมัติ / ให้แก้ไข</span>'
            action_btn = f'<a href="/submit_credit?edit_id={r.id}#form_section" class="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-xl text-xs font-bold inline-block shadow-sm">แก้ไขเอกสารและยื่นใหม่</a>'

        approved_by = getattr(r, 'approved_by', '-') or '-'
        reason_box = f'<div class="mt-1 text-xs text-rose-600 font-bold"><b>เหตุผลที่ไม่ผ่าน:</b> {r.reject_reason}</div>' if getattr(r, 'reject_reason', None) else ''

        img_preview = f'<a href="/static/uploads/{r.doc_img}" target="_blank" class="text-xs text-sky-600 underline font-extrabold"><i class="fa-solid fa-image mr-1"></i>ดูรูปหลักฐาน</a>' if getattr(r, 'doc_img', None) and r.doc_img != 'default_doc.png' else '<span class="text-xs text-slate-400 font-medium">ไม่มีแนบรูป</span>'

        rows += f"""
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-600">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">
                {getattr(r, 'course_name', '-')}<br>
                {img_preview}
                {reason_box}
            </td>
            <td class="py-4 px-4 text-slate-700 font-bold">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)}</td>
            <td class="py-4 px-4 text-xs text-slate-600 font-bold">{approved_by}</td>
            <td class="py-4 px-4">{badge}</td>
            <td class="py-4 px-4">{action_btn}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">ประวัติคำร้องเทียบโอน (สาขาวิชาระบบสารสนเทศ)</h3>
        <table class="w-full text-left min-w-[750px]">
            <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา / หลักฐาน</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">เจ้าหน้าที่ผู้ตรวจ</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="7" class="py-12 text-center text-slate-400 font-bold">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
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
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-700 font-bold">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-sky-600">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-4 px-4 text-xs text-slate-600 font-bold">{approved_by}</td>
        </tr>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-black text-slate-900">💳 หน่วยกิตสะสมสาขา IS ({total_approved} หน่วยกิต)</h2></div>
    <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
        <table class="w-full text-left min-w-[600px]">
            <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider"><tr><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">ผู้อนุมัติ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-12 text-center text-slate-400 font-bold text-sm">ยังไม่มีรายการหน่วยกิตที่ได้รับการอนุมัติ</td></tr>'}</tbody>
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
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border-2 border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-1">{display_title}</h3>
        <p class="text-sm font-black text-sky-700 mb-1">รหัสนักศึกษา: {user.member_id or '-'}</p>
        <p class="text-xs text-slate-500 mb-6 font-bold">สาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ</p>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5 bg-sky-50 p-6 rounded-2xl border border-sky-200 text-sm">
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">ชื่อ-สกุล</span> <span class="font-extrabold text-slate-900">{user.fullname}</span></div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">เลขบัตรประชาชน</span> <span class="font-extrabold text-slate-900">{user.id_card or '-'}</span></div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">เบอร์โทรศัพท์</span> <span class="font-extrabold text-slate-900">{user.phone or '-'}</span></div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">อีเมล</span> <span class="font-extrabold text-slate-900">{user.email or '-'}</span></div>
            <div class="md:col-span-2"><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">ที่อยู่ตามทะเบียนบ้าน/ที่อยู่ปัจจุบัน</span> <span class="font-extrabold text-slate-900">{user.address or '-'}</span></div>
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
    <div class="max-w-2xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border-2 border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">ส่งคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <p class="text-xs text-slate-500 mb-6 font-medium">กรอกข้อมูลที่ต้องการอัปเดตเพื่อส่งเรื่องให้เจ้าหน้าที่ประจำสาขาอนุมัติ</p>
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้าใหม่</label>
                    <select name="prefix" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                        <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                        <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                        <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                    </select>
                </div>
                <div class="col-span-2">
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุลใหม่</label>
                    <input type="text" name="fullname" value="{user.fullname}" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ใหม่</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมลใหม่</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
            </div>
            <div>
                <label class="block text-xs font-bold text-rose-600 uppercase tracking-wider mb-1.5">เหตุผลในการขอแก้ไข *</label>
                <textarea name="reason" rows="3" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></textarea>
            </div>
            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-2">ส่งคำร้องให้เจ้าหน้าที่พิจารณา</button>
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
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">รอการพิจารณา</span>'
            action_col = f'<a href="/admin/review/{r.id}" class="bg-sky-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:bg-sky-700 inline-block shadow-sm">พิจารณาคำร้อง</a>'
        elif status_val == 'Approved':
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">อนุมัติแล้ว</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-300"><i class="fa-solid fa-lock mr-1"></i>พิจารณาแล้ว</span>'
        else:
            status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">ไม่อนุมัติ / ให้แก้ไข</span>'
            action_col = '<span class="text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-300"><i class="fa-solid fa-lock mr-1"></i>พิจารณาแล้ว</span>'

        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'

        rows += f"""
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-sky-700">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-bold text-slate-900">{student_name}<br><span class="text-xs text-sky-700 font-extrabold">({student_code})</span></td>
            <td class="py-4 px-4 text-slate-700 font-bold">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-500 text-xs font-semibold">{getattr(r, 'date_submitted', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{action_col}</td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องเทียบโอนทั้งหมด (สาขาวิชาระบบสารสนเทศ)</h3>
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">ชื่อนักศึกษา</th><th class="py-3 px-4">วิชาที่ขอเทียบโอน</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400 font-bold">ไม่มีคำร้องในระบบ</td></tr>'}</tbody>
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

    img_html = f'<a href="/static/uploads/{req.doc_img}" target="_blank"><img src="/static/uploads/{req.doc_img}" class="max-h-64 rounded-2xl border-2 border-sky-200 shadow-sm hover:opacity-90 transition"></a>' if getattr(req, 'doc_img', None) and req.doc_img != 'default_doc.png' else '<span class="text-xs text-slate-400 font-bold">ไม่มีแนบรูปภาพหลักฐาน</span>'

    content = f"""
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border-2 border-sky-100 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-6">พิจารณาคำร้องเทียบโอน #{getattr(req, 'req_code', 'TR001')}</h3>
        
        <div class="grid md:grid-cols-2 gap-5 text-sm mb-6 bg-sky-50 p-6 rounded-2xl border border-sky-200">
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">ผู้ยื่นคำร้อง</span><b class="text-slate-900">{student_name}</b> (รหัส: {student_code})</div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">หมวดวิชา</span><b class="text-slate-900">{getattr(req, 'category', 'หมวดวิชาศึกษาทั่วไป')}</b></div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">รายวิชา</span><b class="text-slate-900">{getattr(req, 'course_name', '-')}</b> ({getattr(req, 'credits', 0)} หน่วยกิต)</div>
            <div><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-1">ระบบออนไลน์</span><b class="text-slate-900">{getattr(req, 'institution', '-')}</b></div>
            <div class="md:col-span-2"><span class="text-slate-500 block text-xs font-bold uppercase tracking-wider mb-2">หลักฐานเกียรติบัตรที่แนบมา</span><div>{img_html}</div></div>
        </div>

        <form method="POST" class="space-y-4 border-t border-sky-200 pt-6">
            <div>
                <label class="block text-xs font-bold text-rose-600 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-triangle-exclamation mr-1"></i> กรณีไม่ผ่านการพิจารณา: ระบุเหตุผล / สิ่งที่ให้นักศึกษาแก้ไข</label>
                <textarea name="reject_reason" rows="3" placeholder="ระบุข้อความเพื่อแจ้งเตือนนักศึกษา เช่น รูปถ่ายวุฒิบัตรไม่ชัดเจน หรือ เรียนไม่ครบตามรายวิชาที่กำหนด..." class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-rose-500 outline-none bg-sky-50 font-semibold"></textarea>
            </div>

            <div class="flex justify-end gap-3 pt-2">
                <button type="submit" name="action" value="reject" class="px-6 py-3 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-2xl text-xs transition shadow-md">
                    <i class="fa-solid fa-xmark mr-1"></i> ไม่ผ่านการพิจารณา / ส่งกลับแก้ไข
                </button>
                <button type="submit" name="action" value="approve" class="px-6 py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-2xl text-xs transition shadow-md">
                    <i class="fa-solid fa-check mr-1"></i> อนุมัติผ่านการเทียบโอน
                </button>
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
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-bold text-sky-700 font-mono">
                {s.member_id or '-'}<br>
                <span class="text-xs text-slate-500 font-normal">({s.id_card or '-'})</span>
            </td>
            <td class="py-4 px-4 font-extrabold text-slate-900">
                {s.prefix or ''} {s.fullname}<br>
                <span class="text-xs text-slate-500 font-bold">สาขาวิชาระบบสารสนเทศ</span>
            </td>
            <td class="py-4 px-4 text-xs text-slate-700 font-semibold leading-relaxed">
                <i class="fa-solid fa-phone text-slate-400 mr-1"></i>{s.phone or '-'}<br>
                <i class="fa-solid fa-envelope text-slate-400 mr-1"></i>{s.email or '-'}
            </td>
            <td class="py-4 px-4 text-xs text-slate-700 max-w-xs leading-relaxed font-semibold">
                {s.address or '-'}
            </td>
            <td class="py-4 px-4 font-black text-center">
                <span class="bg-sky-100 text-sky-800 px-3 py-1 rounded-full text-xs font-black border border-sky-200">
                    {approved_credits} หน่วยกิต
                </span>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900"><i class="fa-solid fa-users text-sky-600 mr-2"></i>รายชื่อนักศึกษาสาขาวิชาระบบสารสนเทศ</h3>
                <p class="text-xs text-slate-500 mt-1 font-medium">แสดงข้อมูลนักศึกษาและจำนวนหน่วยกิตที่ได้รับการอนุมัติ</p>
            </div>
            <div class="bg-sky-100 text-sky-900 px-4 py-2 rounded-2xl border border-sky-200 text-xs font-black">
                นักศึกษาในระบบ: {len(students)} คน
            </div>
        </div>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider">
                <tr>
                    <th class="py-3 px-4">รหัสนักศึกษา / บัตรประชาชน</th>
                    <th class="py-3 px-4">ชื่อ-นามสกุล / สาขา</th>
                    <th class="py-3 px-4">ข้อมูลติดต่อ</th>
                    <th class="py-3 px-4">ที่อยู่</th>
                    <th class="py-3 px-4 text-center">หน่วยกิตสะสม</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-sky-100">
                {rows if rows else '<tr><td colspan="5" class="py-12 text-center text-slate-400 font-bold">ยังไม่มีนักศึกษาลงทะเบียนในระบบ</td></tr>'}
            </tbody>
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

        house_no = request.form.get('house_no', '')
        moo = request.form.get('moo', '')
        soi = request.form.get('soi', '')
        subdistrict = request.form.get('subdistrict', '')
        district = request.form.get('district', '')
        province = request.form.get('province', '')
        postal_code = request.form.get('postal_code', '')

        full_address = format_address(house_no, moo, soi, subdistrict, district, province, postal_code)

        if User.query.filter_by(id_card=id_card).first():
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนในระบบแล้ว', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username นี้ถูกใช้งานแล้ว กรุณาเลือกชื่อผู้ใช้ใหม่', 'error')
            return redirect(url_for('register'))

        new_member_id = generate_member_id()

        new_user = User(
            member_id=new_member_id,
            prefix=prefix,
            fullname=fullname,
            id_card=id_card,
            dob=dob,
            phone=phone,
            email=email,
            address=full_address,
            id_card_img="default_id_card.png",
            username=username,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()

        flash(f'สมัครสมาชิกเรียบร้อยแล้ว! รหัสนักศึกษาของคุณคือ: {new_member_id}', 'success')
        return redirect(url_for('login'))

    content = """
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border-2 border-sky-100 shadow-xl">
        <div class="text-center mb-8">
            <h2 class="text-2xl font-black text-slate-900">ลงทะเบียนนักศึกษาสาขาวิชาระบบสารสนเทศ</h2>
            <p class="text-xs text-slate-500 mt-1 font-medium">กรอกข้อมูลส่วนตัวเพื่อสร้างคลังหน่วยกิต Thai/Chula MOOC</p>
        </div>
        <form method="POST" class="space-y-5">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้า *</label>
                    <select name="prefix" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                        <option value="นาย">นาย</option>
                        <option value="นาง">นาง</option>
                        <option value="นางสาว">นางสาว</option>
                    </select>
                </div>
                <div class="md:col-span-2">
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล *</label>
                    <input type="text" name="fullname" required placeholder="ชื่อ นามสกุล" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เลขบัตรประชาชน (13 หลัก) *</label>
                    <input type="text" name="id_card" maxlength="13" required placeholder="เลขบัตรประชาชน" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">วัน/เดือน/ปีเกิด *</label>
                    <input type="date" name="dob" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ *</label><input type="tel" name="phone" required placeholder="08X-XXX-XXXX" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมล *</label><input type="email" name="email" required placeholder="student@rmutto.ac.th" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
            </div>

            <div class="border-t border-sky-100 pt-4">
                <label class="block text-xs font-bold text-sky-800 uppercase tracking-wider mb-3"><i class="fa-solid fa-house-user mr-1 text-sky-600"></i> ข้อมูลที่อยู่ตามทะเบียนบ้าน / ที่อยู่ปัจจุบัน</label>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">บ้านเลขที่ *</label><input type="text" name="house_no" required placeholder="123/45" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">หมู่ที่</label><input type="text" name="moo" placeholder="1" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">ซอย / ถนน</label><input type="text" name="soi" placeholder="สุขุมวิท 21" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">ตำบล/แขวง *</label><input type="text" name="subdistrict" required placeholder="ตำบล" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">อำเภอ/เขต *</label><input type="text" name="district" required placeholder="อำเภอ" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">จังหวัด *</label><input type="text" name="province" required placeholder="จังหวัด" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                    <div><label class="block text-xs font-bold text-slate-600 mb-1">รหัสไปรษณีย์ *</label><input type="text" name="postal_code" required placeholder="10110" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm bg-sky-50 font-semibold"></div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-sky-100 pt-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อผู้ใช้งาน (Username) *</label><input type="text" name="username" required placeholder="ตั้งชื่อผู้ใช้งาน" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password) *</label><input type="password" name="password" required placeholder="กำหนดรหัสผ่าน" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold"></div>
            </div>

            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-4">
                <i class="fa-solid fa-user-plus mr-1 text-sky-100"></i> ยืนยันการลงทะเบียน
            </button>
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
    <div class="max-w-md mx-auto my-12 bg-white p-8 sm:p-10 rounded-3xl border-2 border-sky-100 shadow-xl">
        <div class="text-center mb-8">
            <div class="p-2 mb-3 inline-block">
                <img src="/static/images/logo.png" alt="IS RMUTTO Logo" class="h-20 mx-auto object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/200x80?text=IS+RMUTTO';">
            </div>
            <h2 class="text-2xl font-black text-slate-900">เข้าสู่ระบบ</h2>
            <p class="text-xs text-slate-500 mt-1 font-bold">ธนาคารหน่วยกิต สาขาวิชาระบบสารสนเทศ มทร.ตะวันออก</p>
        </div>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อผู้ใช้งาน หรือ เลขบัตรประชาชน</label>
                <input type="text" name="username" required placeholder="Username / เลขบัตรประชาชน 13 หลัก" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password)</label>
                <input type="password" name="password" required placeholder="รหัสผ่านของคุณ" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
            </div>
            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-2">เข้าสู่ระบบ</button>
            <div class="text-center text-xs pt-4 border-t border-sky-100">
                <a href="/register" class="text-slate-600 hover:text-sky-700 font-bold">ยังไม่มีบัญชีนักศึกษา? <span class="font-extrabold text-sky-700 underline">ลงทะเบียนเข้าใช้งาน</span></a>
            </div>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/manage_admins', methods=['GET', 'POST'])
def manage_admins():
    if session.get('role') not in ['admin', 'superadmin']:
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
        return redirect(url_for('home'))

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        id_card = request.form.get('id_card', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()

        if User.query.filter_by(id_card=id_card).first():
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนในระบบแล้ว', 'error')
            return redirect(url_for('manage_admins'))

        new_admin = User(
            member_id=f"ADM{uuid.uuid4().hex[:3].upper()}",
            prefix="เจ้าหน้าที่",
            fullname=fullname,
            id_card=id_card,
            username=id_card,
            password=generate_password_hash(password),
            email=email,
            phone=phone,
            role='admin'
        )
        db.session.add(new_admin)
        db.session.commit()
        flash(f'เพิ่มเจ้าหน้าที่ "{fullname}" เข้าสู่ระบบเรียบร้อยแล้ว', 'success')
        return redirect(url_for('manage_admins'))

    admin_list = User.query.filter(User.role.in_(['admin', 'superadmin'])).all()
    rows = ""
    for a in admin_list:
        role_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-sky-200 text-sky-900 border border-sky-300">ผู้ดูแลหลัก</span>' if a.role == 'superadmin' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-slate-200 text-slate-800 border border-slate-300">เจ้าหน้าที่ตรวจงาน</span>'
        
        rows += f"""
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-700">{a.id_card}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{a.fullname}</td>
            <td class="py-4 px-4 text-xs text-slate-700 font-semibold">{a.email or '-'}<br>{a.phone or '-'}</td>
            <td class="py-4 px-4">{role_badge}</td>
        </tr>
        """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-xl">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center font-bold text-xl shrink-0"><i class="fa-solid fa-user-plus"></i></div>
                <div>
                    <h3 class="text-xl font-black text-slate-900">เพิ่มบัญชีเจ้าหน้าที่ตรวจงานสาขาวิชา IS</h3>
                    <p class="text-xs text-slate-500 font-medium">กำหนดเลขบัตรประชาชนและรหัสผ่านส่วนตัวสำหรับเจ้าหน้าที่ในการเข้าสู่ระบบ</p>
                </div>
            </div>
            
            <form method="POST" class="space-y-4 border-t border-sky-100 pt-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล เจ้าหน้าที่ <span class="text-rose-500">*</span></label>
                        <input type="text" name="fullname" placeholder="เช่น นายสมศักดิ์ ตรวจการ" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เลขบัตรประชาชน (13 หลัก) <span class="text-rose-500">* (Username)</span></label>
                        <input type="text" name="id_card" maxlength="13" placeholder="เลขบัตรประชาชน 13 หลัก" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมลเจ้าหน้าที่</label>
                        <input type="email" name="email" placeholder="official@rmutto.ac.th" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์</label>
                        <input type="tel" name="phone" placeholder="08X-XXX-XXXX" class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">กำหนดรหัสผ่าน <span class="text-rose-500">*</span></label>
                        <input type="password" name="password" placeholder="รหัสผ่านเข้าใช้งาน" required class="w-full border-2 border-sky-100 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-sky-400 outline-none bg-sky-50 font-semibold">
                    </div>
                </div>

                <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-2">
                    <i class="fa-solid fa-plus mr-1 text-sky-100"></i> บันทึกเพิ่มเจ้าหน้าที่
                </button>
            </form>
        </div>

        <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
            <h3 class="text-xl font-black text-slate-900 mb-6"><i class="fa-solid fa-users-gear text-sky-600 mr-2"></i>รายชื่อเจ้าหน้าที่ผู้มีสิทธิ์ในระบบ</h3>
            <table class="w-full text-left min-w-[600px]">
                <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider">
                    <tr><th class="py-3 px-4">เลขบัตรประชาชน (Username)</th><th class="py-3 px-4">ชื่อ-สกุล เจ้าหน้าที่</th><th class="py-3 px-4">ข้อมูลติดต่อ</th><th class="py-3 px-4">สิทธิ์ผู้ใช้งาน</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
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
        status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">อนุมัติแล้ว</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">ไม่อนุมัติ</span>')
        
        actions = f"""
        <div class="flex items-center gap-2">
            <a href="/admin/approve_profile/{r.id}" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-check"></i> อนุมัติ
            </a>
            <a href="/admin/reject_profile/{r.id}" class="bg-rose-600 hover:bg-rose-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-xmark"></i> ไม่อนุมัติ
            </a>
        </div>
        """ if getattr(r, 'status', 'Pending') == 'Pending' else f'<div class="text-xs text-slate-600 font-semibold">ผู้อนุมัติ:<br><span class="text-sky-700 font-bold">{getattr(r, "approved_by", "เจ้าหน้าที่") or "เจ้าหน้าที่"}</span></div>'

        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'

        rows += f"""
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50 transition">
            <td class="py-4 px-4 font-bold text-slate-900">
                {student_name}<br>
                <span class="text-xs text-sky-700 font-bold">(รหัส: {student_code})</span>
            </td>
            <td class="py-4 px-4 text-xs leading-relaxed font-semibold text-slate-800">
                <b>ชื่อใหม่:</b> {getattr(r, 'new_prefix', '')}{getattr(r, 'new_fullname', '')}<br>
                <b>โทร:</b> {getattr(r, 'new_phone', '-')}<br>
                <b>อีเมล:</b> {getattr(r, 'new_email', '-')}<br>
                <b>ที่อยู่ใหม่:</b> {getattr(r, 'new_address', '-')}
            </td>
            <td class="py-4 px-4 text-xs text-slate-700 max-w-xs leading-relaxed font-semibold">{getattr(r, 'reason', '-')}</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-semibold">{getattr(r, 'created_at', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{actions}</td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border-2 border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <table class="w-full text-left min-w-[750px]">
            <thead class="bg-sky-200 border-b border-sky-300 text-xs font-black text-sky-950 uppercase tracking-wider">
                <tr><th class="py-3 px-4">นักศึกษา</th><th class="py-3 px-4">ข้อมูลที่ขอเปลี่ยนแปลง</th><th class="py-3 px-4">เหตุผลในการขอแก้ไข</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">การจัดการ</th></tr>
            </thead>
            <tbody class="divide-y divide-sky-100">{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400 font-bold">ไม่มีคำร้องขอแก้ไขข้อมูลในระบบ</td></tr>'}</tbody>
        </table>
    </div>
    """
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
                if req.new_address:
                    user.address = req.new_address
            
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