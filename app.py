import os
import uuid
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'credit_bank_is_rmutto_secret_key_2026_v2'

db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///credit_bank.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

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
    status = db.Column(db.String(20), default='Pending')
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

with app.app_context():
    db.create_all()

    try:
        main_admin = User.query.filter((User.username == 'Admin_rmutto') | (User.username == 'admin')).first()
        if not main_admin:
            main_admin = User(
                member_id='ADM000',
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
            return "IS00001"
        last_num = int(last_user.member_id.replace("IS", ""))
        return f"IS{last_num + 1:05d}"
    except Exception:
        return f"IS{uuid.uuid4().hex[:5].upper()}"

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
# Layout Template
# ==========================================
LAYOUT_TEMPLATE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ธนาคารหน่วยกิต สาขาวิชาระบบสารสนเทศ - มทร.ตะวันออก</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: 'Sarabun', sans-serif; background-color: #f8fafc; }
        .hero-gradient { background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #1e1b4b 100%); }
        .sidebar-transition { transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-hover { transition: all 0.25s ease-in-out; }
        .card-hover:hover { transform: translateY(-3px); box-shadow: 0 12px 24px -10px rgba(0, 0, 0, 0.08); }
        .sidebar-expanded { width: 260px; }
        .sidebar-collapsed { width: 80px; }
        .sidebar-collapsed .nav-text { display: none; }
        .sidebar-collapsed .logo-text { display: none; }
        .sidebar-collapsed .section-title { display: none; }
        .sidebar-collapsed .toggle-icon { transform: rotate(180deg); }
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800 antialiased flex flex-col md:flex-row">

    <!-- Mobile Top Header -->
    <div class="md:hidden bg-slate-900 text-white p-4 flex justify-between items-center sticky top-0 z-50 border-b border-slate-800">
        <a href="/" class="flex items-center gap-2.5">
            <div class="w-9 h-9 bg-blue-800 text-amber-400 rounded-xl flex items-center justify-center font-extrabold text-base">IS</div>
            <span class="font-bold text-base tracking-tight">Credit Bank - สาขาวิชาระบบสารสนเทศ</span>
        </a>
        <button id="mobile-toggle" class="p-2 text-slate-300 hover:text-white"><i class="fa-solid fa-bars text-xl"></i></button>
    </div>

    <!-- Collapsible Left Sidebar -->
    <aside id="sidebar" class="sidebar-expanded sidebar-transition bg-slate-900 text-slate-300 min-h-screen flex flex-col fixed md:sticky top-0 z-40 shadow-2xl border-r border-slate-800 hidden md:flex shrink-0">
        
        <!-- Header Logo Zone -->
        <div class="p-5 flex flex-col border-b border-slate-800/80">
            <a href="/" class="flex items-center gap-3 overflow-hidden justify-center md:justify-start">
                <div class="w-10 h-10 bg-gradient-to-tr from-blue-700 to-indigo-600 text-amber-400 rounded-2xl flex items-center justify-center font-black text-lg shrink-0 shadow-md shadow-blue-900/40">
                    IS
                </div>
                <div class="flex flex-col logo-text transition-all">
                    <span class="font-black text-white text-base leading-tight tracking-tight">Credit Bank</span>
                    <span class="text-[10px] text-amber-400 font-bold tracking-wider uppercase">ระบบสารสนเทศ มทร.ตะวันออก</span>
                </div>
            </a>

            <!-- Toggle Button BELOW Logo -->
            <div class="mt-4 pt-3 border-t border-slate-800/60 hidden md:flex justify-center">
                <button id="sidebar-toggle" class="w-full py-1.5 px-3 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-amber-400 flex items-center justify-center gap-2 transition-all group border border-slate-700/50">
                    <i class="fa-solid fa-chevron-left text-xs toggle-icon transition-transform duration-300"></i>
                    <span class="nav-text text-xs font-bold text-slate-300 group-hover:text-amber-400">ย่อแถบเมนู</span>
                </button>
            </div>
        </div>

        <!-- Navigation Links -->
        <div class="flex-grow p-4 space-y-1.5 overflow-y-auto">
            <p class="section-title text-[11px] font-extrabold text-slate-500 uppercase tracking-wider px-3 mb-2 pt-2">เมนูหลัก</p>
            
            <a href="/" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                <i class="fa-solid fa-house text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                <span class="nav-text font-semibold">หน้าแรก</span>
            </a>

            {% if session.get('user_id') %}
                {% if session.get('role') in ['admin', 'superadmin'] %}
                    <p class="section-title text-[11px] font-extrabold text-slate-500 uppercase tracking-wider px-3 mb-2 pt-4">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/students" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-users text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">รายชื่อนักศึกษา</span>
                    </a>
                    <a href="/admin/requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-file-signature text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">คำร้องเทียบโอน</span>
                    </a>
                    <a href="/admin/profile_requests" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-user-pen text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">คำร้องแก้ไขข้อมูล</span>
                    </a>
                    <a href="/admin/manage_admins" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-amber-400 bg-blue-900/40 border border-blue-800/50 hover:bg-blue-900/60 transition-all font-medium text-sm group mt-2">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-amber-400"></i>
                        <span class="nav-text font-bold">เพิ่ม/จัดการเจ้าหน้าที่</span>
                    </a>
                {% else %}
                    <p class="section-title text-[11px] font-extrabold text-slate-500 uppercase tracking-wider px-3 mb-2 pt-4">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-laptop-code text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">ค้นหาวิชา Thai/Chula MOOC</span>
                    </a>
                    <a href="/submit_credit" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-file-circle-plus text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">ยื่นคำขอเทียบโอน</span>
                    </a>
                    <a href="/credits" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-graduation-cap text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">หน่วยกิตสะสม</span>
                    </a>
                    <a href="/history" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-clock-rotate-left text-lg w-6 text-center text-slate-400 group-hover:text-amber-400 transition-colors"></i>
                        <span class="nav-text font-semibold">ประวัติคำขอ</span>
                    </a>
                {% endif %}
            {% else %}
                <div class="pt-4 space-y-2">
                    <a href="/login" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl text-slate-300 hover:text-white hover:bg-slate-800/80 transition-all font-medium text-sm group">
                        <i class="fa-solid fa-right-to-bracket text-lg w-6 text-center text-slate-400 group-hover:text-amber-400"></i>
                        <span class="nav-text font-semibold">เข้าสู่ระบบ</span>
                    </a>
                    <a href="/register" class="flex items-center gap-3.5 px-3.5 py-3 rounded-2xl bg-gradient-to-r from-blue-900 to-indigo-800 text-white font-bold transition-all text-sm group shadow-md shadow-blue-900/30">
                        <i class="fa-solid fa-user-plus text-lg w-6 text-center text-amber-400"></i>
                        <span class="nav-text">ลงทะเบียนนักศึกษา</span>
                    </a>
                </div>
            {% endif %}
        </div>

        <!-- Footer Profile Link -->
        {% if session.get('user_id') %}
            <div class="p-4 border-t border-slate-800 bg-slate-900/80">
                <a href="/profile" class="flex items-center gap-3 p-2 rounded-2xl hover:bg-slate-800 transition-all group">
                    <div class="w-9 h-9 rounded-xl bg-blue-800 text-amber-400 font-bold flex items-center justify-center shrink-0">
                        <i class="fa-regular fa-user"></i>
                    </div>
                    <div class="flex flex-col min-w-0 nav-text">
                        <span class="text-xs font-bold text-white truncate">{{ session.get('fullname', 'ผู้ใช้งาน') }}</span>
                        <span class="text-[10px] text-slate-400 capitalize">{% if session.get('role') in ['admin', 'superadmin'] %}เจ้าหน้าที่{% else %}นักศึกษาสาขา IS{% endif %}</span>
                    </div>
                </a>
                <a href="/logout" class="mt-2 flex items-center gap-3 px-3 py-2 text-xs font-bold text-rose-400 hover:bg-rose-950/30 rounded-xl transition-all">
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

        <footer class="bg-slate-900 text-slate-400 mt-auto border-t border-slate-800">
            <div class="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
                <div class="flex flex-col md:flex-row items-center justify-between gap-4 text-xs font-medium text-center md:text-left">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-lg bg-blue-800 text-amber-400 font-bold flex items-center justify-center">IS</div>
                        <div>
                            <p class="text-slate-200 font-bold text-sm">สาขาวิชาระบบสารสนเทศ - มทร.ตะวันออก</p>
                            <p class="text-slate-500 mt-0.5">คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ</p>
                        </div>
                    </div>
                    <div class="text-slate-400 leading-relaxed">
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
    # กลุ่มศึกษาทั่วไป (ThaiMOOC)
    {"code": "15-02-002", "name": "คุณภาพการใช้ชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. ชีวิตและการสร้างคุณค่า (2 ชม.) / 2. การคิดสร้างสรรค์เพื่อการพัฒนาตนเอง (5 ชม.)", "hours": "7 ชม.", "credits": 3},
    {"code": "15-02-003", "name": "การคิดอย่างมีวิจารณญาณและการแก้ปัญหา", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. การคิดเชิงวิพากษ์และการจัดการปัญหา (5 ชม.) / 2. การคิดแก้ปัญหาเชิงสร้างสรรค์ (6 ชม.)", "hours": "11 ชม.", "credits": 3},
    {"code": "15-02-004", "name": "คุณธรรมจริยธรรมในโลกเทคโนโลยีสารสนเทศ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "จริยธรรมสารสนเทศสำหรับพลเมืองดิจิทัล", "hours": "7 ชม.", "credits": 3},
    {"code": "15-03-005", "name": "ผู้ประกอบการนวัตกรรม", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "การเป็นผู้ประกอบการในศตวรรษที่ 21", "hours": "30 ชม.", "credits": 3},
    {"code": "15-03-006", "name": "การจัดการเศรษฐกิจชีวภาพ เศรษฐกิจหมุนเวียน และเศรษฐกิจสีเขียว", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. ชุมชนแห่งความยั่งยืน (2 ชม.) / 2. หลักเศรษฐศาสตร์เกษตร (6 ชม.)", "hours": "8 ชม.", "credits": 3},
    {"code": "15-03-007", "name": "เทคโนโลยีสารสนเทศในยุคดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "เทคโนโลยีสารสนเทศในยุคดิจิทัล", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-008", "name": "คณิตศาสตร์และสถิติเพื่อการประกอบอาชีพ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "สถิติธุรกิจ (สถิติเรื่องใกล้ตัว…ไม่น่ากลัวอย่างที่คิด)", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-009", "name": "ภูมิปัญญาเพื่อการประกอบอาชีพ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "ภูมิปัญญาไทย กับการพัฒนาการเกษตรอย่างยั่งยืน", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-010", "name": "การวิเคราะห์และนำเสนอข้อมูลด้วยเทคโนโลยีดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. การออกแบบการนำเสนองานอย่างสร้างสรรค์และทันสมัย (10 ชม.) / 2. คอมพิวเตอร์เพื่อการพูดและการนำเสนอ (6 ชม.)", "hours": "16 ชม.", "credits": 3},
    {"code": "15-03-011", "name": "ผู้ประกอบการดิจิทัล", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "การตลาดดิจิทัลสำหรับผู้ประกอบการธุรกิจชุมชน", "hours": "5 ชม.", "credits": 3},
    {"code": "15-03-014", "name": "การพัฒนาศักยภาพเพื่อมุ่งสู่การเป็นผู้ประกอบการมือใหม่", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "การเริ่มต้นเป็นผู้ประกอบการรายใหม่ (A new entrepreneur)", "hours": "30 ชม.", "credits": 3},
    {"code": "15-03-015", "name": "ศาสตร์แห่งการสื่อสาร", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. ทักษะการสื่อสารระหว่างบุคคลในการทำงาน (10 ชม.) / 2. การสื่อสารและการประสานงาน (5 ชม.)", "hours": "15 ชม.", "credits": 3},
    {"code": "15-03-016", "name": "ภาษาอังกฤษเพื่อการสื่อสาร", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. ภาษาอังกฤษเพื่อการสื่อสาร (10 ชม.) / 2. ภาษาอังกฤษเพื่อการสื่อสารในสังคม (4 ชม.)", "hours": "14 ชม.", "credits": 3},
    {"code": "15-03-018", "name": "การใช้ภาษาไทยในชีวิตประจำวัน", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "การใช้ภาษาไทย หรือ ภาษาไทยเพื่อการสื่อสารร่วมสมัย", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-019", "name": "ทักษะภาษาอังกฤษสำหรับผู้ประกอบการออนไลน์", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "ง่ายสบายกับการอธิบายกราฟเป็นภาษาอังกฤษ", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-020", "name": "ทักษะการเรียนภาษาอังกฤษผ่านสื่ออิเล็กทรอนิกส์", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "ภาษาอังกฤษสำหรับเทคโนโลยีสารสนเทศ", "hours": "10 ชม.", "credits": 3},
    {"code": "15-03-021", "name": "เทคนิคการพูดเพื่อความสำเร็จ", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "รู้รอบด้านการนำเสนอ", "hours": "5 ชม.", "credits": 3},
    {"code": "15-05-024", "name": "ทักษะชีวิต", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "ทักษะทางสังคม", "hours": "10 ชม.", "credits": 3},
    {"code": "15-06-027", "name": "ความเป็นพลเมืองไทยและพลเมืองโลก", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "1. ความเป็นพลเมืองโลก (3 ชม.) / 2. การเป็นพลเมือง (10 ชม.)", "hours": "13 ชม.", "credits": 3},
    {"code": "15-06-028", "name": "วิถีโลก", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "กลยุทธ์สู่ประชาคมอาเซียน: การเมือง เศรษฐกิจ และสังคม", "hours": "8 ชม.", "credits": 3},
    {"code": "15-06-029", "name": "สังคมและวัฒนธรรมไทย", "group": "หมวดวิชาศึกษาทั่วไป", "provider": "ThaiMOOC", "mooc": "อารยธรรมและภูมิปัญญาท้องถิ่น", "hours": "1 ชม.", "credits": 3},

    # กลุ่มวิชาแกน (ThaiMOOC & ChulaMOOC)
    {"code": "04-00-101", "name": "หลักการตลาด", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. การจัดการเชิงกลยุทธ์และการตลาดในยุคโลกาภิวัตน์ (10 ชม.) / 2. การตลาดเชิงสร้างสรรค์ (6 ชม.)", "hours": "16 ชม.", "credits": 3},
    {"code": "04-00-102", "name": "หลักเศรษฐศาสตร์ (Principles of Economics)", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "เศรษฐศาสตร์ตลาดการเงิน", "hours": "10 ชม.", "credits": 3},
    {"code": "04-00-103", "name": "องค์การและการจัดการ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. การบริหารจัดการในศตวรรษที่ 21 (6 ชม.) / 2. การจัดการธุรกิจการค้าสมัยใหม่ในยุค Thailand 4.0 (6 ชม.)", "hours": "12 ชม.", "credits": 3},
    {"code": "04-00-104", "name": "กฎหมายธุรกิจและการภาษีอากร", "group": "หมวดวิชาแกน", "provider": "ChulaMOOC", "mooc": "1. กฎหมายกับธุรกิจ Law for Business: กฎหมายกับธุรกิจยุค Thailand 4.0 และภาษี / 2. กฎหมายพื้นฐานสำหรับธุรกิจ", "hours": "ตามโครงสร้าง ChulaMOOC", "credits": 3},
    {"code": "04-00-105", "name": "สถิติเพื่อการวิจัยธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. สถิติและการวิเคราะห์ข้อมูลเบื้องต้น (4 ชม.) / 2. วิจัยทางธุรกิจ (6 ชม.)", "hours": "10 ชม.", "credits": 3},
    {"code": "04-00-106", "name": "ภาษาอังกฤษเพื่อการสื่อสารธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "สตาร์ทอัพอังกฤษ", "hours": "30 ชม.", "credits": 3},
    {"code": "04-00-107", "name": "การบัญชีเบื้องต้นเพื่อการบริหาร", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. บัญชีเบื้องต้น (5 ชม.) / 2. การบัญชีบริหาร (10 ชม.)", "hours": "15 ชม.", "credits": 3},
    {"code": "04-00-108", "name": "การเงินธุรกิจ", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. การบัญชีเพื่อการจัดการและการจัดการทางการเงิน (10 ชม.) / 2. การเงินสำหรับการเริ่มต้นธุรกิจ SET (1 ชม.)", "hours": "11 ชม.", "credits": 3},
    {"code": "04-00-109", "name": "การจัดการโลจิสติกส์และห่วงโซ่อุปทาน", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. โลจิสติกส์และโซ่อุปทานเบื้องต้น (10 ชม.) / 2. การจัดการคลังสินค้า (10 ชม.)", "hours": "20 ชม.", "credits": 3},
    {"code": "04-00-110", "name": "ทักษะความเข้าใจและการใช้เทคโนโลยีดิจิทัล", "group": "หมวดวิชาแกน", "provider": "ThaiMOOC", "mooc": "1. การเข้าใจดิจิทัล (15 ชม.) / 2. ทักษะความเข้าใจความมั่นคงปลอดภัยทางไซเบอร์ (4 ชม.)", "hours": "19 ชม.", "credits": 3},

    # กลุ่มวิชาเลือก (ThaiMOOC)
    {"code": "04-05-141", "name": "วิทยาการสารสนเทศทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. วิทยาการข้อมูลเบื้องต้น (6 ชม.) / 2. วิทยาการข้อมูลและการประยุกต์ใช้ (30 ชม.)", "hours": "36 ชม.", "credits": 3},
    {"code": "04-05-232", "name": "การคิดเชิงออกแบบสำหรับนวัตกรรมทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "ปฏิบัติการคิดเชิงออกแบบนวัตกรรม", "hours": "12 ชม.", "credits": 3},
    {"code": "04-05-233", "name": "ธุรกิจดิจิทัลผ่านสื่อสังคมออนไลน์", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. มาตรฐานการผลิตสื่อดิจิทัล (5 ชม.) / 2. การสร้างสรรค์สื่อดิจิทัลบนเครือข่ายสังคมออนไลน์ (5 ชม.)", "hours": "10 ชม.", "credits": 3},
    {"code": "04-05-234", "name": "เครือข่ายคอมพิวเตอร์และความปลอดภัยสำหรับธุรกิจดิจิทัล", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "เครือข่ายและความปลอดภัย", "hours": "5 ชม.", "credits": 3},
    {"code": "04-05-241", "name": "การวิเคราะห์ข้อมูลทางธุรกิจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. การเตรียมข้อมูล (12 ชม.) / 2. การวิเคราะห์ข้อมูลสำหรับการจัดการทางธุรกิจ (3 ชม.)", "hours": "15 ชม.", "credits": 3},
    {"code": "04-05-342", "name": "ระบบสนับสนุนการตัดสินใจ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. ระบบสนับสนุนการตัดสินใจสำหรับองค์กรธุรกิจ (6 ชม.) / 2. การตัดสินใจโดยการขับเคลื่อนด้วยข้อมูล (4 ชม.)", "hours": "10 ชม.", "credits": 3},
    {"code": "04-05-441", "name": "ความคิดสร้างสรรค์และนวัตกรรมในการวิเคราะห์ข้อมูล", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. การสร้างสรรค์เนื้อหาด้วยข้อมูล Data (4 ชม.) / 2. การตัดสินใจโดยการขับเคลื่อนด้วยข้อมูล (4 ชม.)", "hours": "8 ชม.", "credits": 3},
    {"code": "04-05-443", "name": "การบริหารโครงการระบบสารสนเทศ", "group": "หมวดวิชาเลือก", "provider": "ThaiMOOC", "mooc": "1. การวิเคราะห์โครงการและแผนงานยุคดิจิทัล (15 ชม.) / 2. การบริหารโครงการ IT แบบมืออาชีพ (3 ชม.)", "hours": "18 ชม.", "credits": 3}
]

# ==========================================
# Routes & Controllers
# ==========================================
@app.route('/')
def home():
    if not session.get('user_id'):
        content = """
        <div class="max-w-5xl mx-auto py-10 md:py-16 grid md:grid-cols-2 gap-10 items-center">
            <div>
                <span class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 mb-5 border border-amber-200">
                    <i class="fa-solid fa-laptop-code text-amber-600"></i> สาขาวิชาระบบสารสนเทศ (IS) มทร.ตะวันออก
                </span>
                
                <div class="space-y-3 mb-6">
                    <h1 class="text-4xl sm:text-5xl font-black text-slate-900 leading-relaxed tracking-normal">
                        ธนาคารหน่วยกิต
                    </h1>
                    <p class="text-3xl sm:text-4xl font-extrabold text-blue-900 leading-relaxed">
                        เทียบโอน Thai & Chula MOOC
                    </p>
                    <p class="text-3xl sm:text-4xl font-extrabold text-amber-600 leading-relaxed">
                        สาขาวิชาระบบสารสนเทศ
                    </p>
                </div>

                <p class="text-slate-600 mb-8 leading-relaxed text-base font-normal">
                    ระบบสะสมและเทียบโอนหน่วยกิตดิจิทัล สำหรับนักศึกษาสาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ มทร.ตะวันออก เพื่อการเรียนรู้ผ่านระบบ ThaiMOOC และ ChulaMOOC
                </p>
                <div class="flex flex-wrap gap-4">
                    <a href="/register" class="px-7 py-3.5 bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold rounded-2xl shadow-lg shadow-blue-900/20 hover:shadow-xl transition-all inline-flex items-center gap-2">
                        <i class="fa-solid fa-user-plus text-amber-400"></i> สมัครสมาชิกนักศึกษา IS
                    </a>
                    <a href="/login" class="px-7 py-3.5 bg-white text-slate-800 border border-slate-200 font-bold rounded-2xl hover:bg-slate-50 transition shadow-sm inline-flex items-center gap-2">
                        เข้าสู่ระบบ
                    </a>
                </div>
            </div>

            <div class="hero-gradient p-10 rounded-3xl text-center shadow-2xl relative overflow-hidden border border-slate-700/50">
                <div class="w-24 h-24 bg-white/10 text-amber-400 rounded-3xl mx-auto flex items-center justify-center text-4xl mb-6 backdrop-blur border border-white/10">
                    <i class="fa-solid fa-graduation-cap"></i>
                </div>
                <h3 class="text-2xl font-bold text-white mb-2">Information Systems</h3>
                <p class="text-slate-300 text-sm leading-relaxed max-w-sm mx-auto">ระบบคลังหน่วยกิตการเรียนรู้ผ่านสื่อออนไลน์ ThaiMOOC / ChulaMOOC สำหรับนักศึกษาสาขาวิชาระบบสารสนเทศ</p>
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
            <p class="text-slate-500 text-sm mt-1">แผงควบคุมระบบตรวจสอบและอนุมัติสำหรับเจ้าหน้าที่ ({user.fullname})</p>
        </div>

        <div class="mb-8">
            <a href="/admin/manage_admins" class="hero-gradient text-white p-7 rounded-3xl shadow-xl flex items-center justify-between hover:opacity-95 transition-all block border border-slate-700/50">
                <div>
                    <div class="flex items-center gap-2 mb-2">
                        <span class="bg-amber-500 text-slate-950 text-[10px] font-black px-2.5 py-0.5 rounded-full uppercase tracking-wider">แอดมินจัดการ</span>
                        <h3 class="text-2xl font-extrabold text-white">➕ เพิ่มเจ้าหน้าที่ตรวจงานระบบสารสนเทศ</h3>
                    </div>
                    <p class="text-sm text-slate-300">เพิ่มบัญชีเจ้าหน้าที่ใหม่ด้วยเลขบัตรประชาชนและรหัสผ่านส่วนตัว (ปัจจุบันมีเจ้าหน้าที่ {total_admins} คน)</p>
                </div>
                <div class="w-14 h-14 bg-white/10 text-amber-400 rounded-2xl flex items-center justify-center text-2xl shrink-0 backdrop-blur border border-white/10"><i class="fa-solid fa-user-plus"></i></div>
            </a>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <a href="/admin/students" class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between hover:border-blue-500 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">นักศึกษาสาขา IS ในระบบ</p>
                    <h3 class="text-3xl font-black text-slate-900">{total_members} <span class="text-xs text-slate-400 font-normal">คน</span></h3>
                </div>
                <div class="w-12 h-12 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-users"></i></div>
            </a>
            <a href="/admin/requests" class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between hover:border-amber-400 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องเทียบโอนค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-amber-600">{pending_credits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-file-signature"></i></div>
            </a>
            <a href="/admin/profile_requests" class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between hover:border-indigo-400 transition card-hover">
                <div>
                    <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องแก้ไขข้อมูลค้างพิจารณา</p>
                    <h3 class="text-3xl font-black text-indigo-600">{pending_edits} <span class="text-xs text-slate-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-user-pen"></i></div>
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
            <p class="text-sm font-bold text-blue-900 mt-1"><i class="fa-solid fa-id-card mr-1 text-amber-500"></i> รหัสนักศึกษา/สมาชิก: {user.member_id or '-'} (สาขาวิชาระบบสารสนเทศ)</p>
        </div>
        <a href="/submit_credit" class="bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold px-6 py-3 rounded-2xl shadow-md shadow-blue-900/20 transition-all inline-flex items-center gap-2 text-sm shrink-0">
            <i class="fa-solid fa-file-circle-plus text-amber-400"></i> ยื่นคำขอเทียบโอนออนไลน์
        </a>
    </div>

    <!-- Stat Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">หน่วยกิตสะสมทั้งหมด</p>
                <h3 class="text-3xl font-black text-blue-950">{approved_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">รออนุมัติเทียบโอน</p>
                <h3 class="text-3xl font-black text-amber-600">{pending_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-hourglass-half"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">คำร้องขอเทียบโอน</p>
                <h3 class="text-3xl font-black text-slate-800">{len(user_requests)} <span class="text-xs font-medium text-slate-400">รายการ</span></h3>
            </div>
            <div class="w-12 h-12 bg-purple-50 text-purple-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-list-check"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">เป้าหมายหลักสูตร IS</p>
                <h3 class="text-3xl font-black text-emerald-600">120 <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-emerald-50 text-emerald-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-bullseye"></i></div>
        </div>
    </div>

    <!-- Charts -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div class="bg-white p-6 rounded-3xl border border-slate-200/80 shadow-sm">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-chart-pie text-blue-900"></i> ความก้าวหน้าหน่วยกิตสาขา IS
            </h3>
            <div class="w-full max-w-[240px] mx-auto py-2">
                <canvas id="creditDoughnutChart"></canvas>
            </div>
        </div>

        <div class="bg-white p-6 rounded-3xl border border-slate-200/80 shadow-sm lg:col-span-2">
            <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-chart-column text-indigo-700"></i> สรุปการสะสมหน่วยกิตจำแนกตามหมวดวิชา
            </h3>
            <div class="w-full h-56">
                <canvas id="creditBarChart"></canvas>
            </div>
        </div>
    </div>

    <!-- Quick Access Actions -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <a href="/available_courses" class="bg-white p-7 rounded-3xl border border-slate-200/80 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-laptop-code"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-blue-900 transition-colors">วิชา Thai/Chula MOOC</h3>
            <p class="text-xs text-slate-500 leading-relaxed">ค้นหารายวิชาออนไลน์ที่เทียบโอนเข้าหลักสูตรสาขาวิชาระบบสารสนเทศ</p>
        </a>
        <a href="/submit_credit" class="bg-white p-7 rounded-3xl border border-slate-200/80 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-amber-50 text-amber-600 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-file-pen"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-amber-600 transition-colors">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
            <p class="text-xs text-slate-500 leading-relaxed">เลือกวิชาที่ต้องเรียนเพิ่มและส่งหลักฐานขอเทียบโอนเข้าสู่ระบบ</p>
        </a>
        <a href="/request_edit_profile" class="bg-white p-7 rounded-3xl border border-slate-200/80 shadow-sm card-hover block group">
            <div class="w-12 h-12 bg-purple-50 text-purple-600 rounded-2xl flex items-center justify-center text-xl mb-4 group-hover:scale-110 transition-transform">
                <i class="fa-solid fa-user-gear"></i>
            </div>
            <h3 class="font-bold text-slate-900 text-lg mb-1 group-hover:text-purple-600 transition-colors">ขอแก้ไขข้อมูลส่วนตัว</h3>
            <p class="text-xs text-slate-500 leading-relaxed">แจ้งเรื่องขอเปลี่ยนชื่อ-สกุล อีเมล หรือเบอร์โทรศัพท์ถึงเจ้าหน้าที่ประจำสาขา</p>
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
                    backgroundColor: ['#1e3a8a', '#d97706', '#e2e8f0'],
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
                    backgroundColor: '#1e3a8a',
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
    if 'user_id' not in session: return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip().lower()
    selected_group = request.args.get('group', '').strip()
    selected_provider = request.args.get('provider', '').strip()

    filtered_courses = IS_THAIMOOC_COURSES

    if selected_provider and selected_provider != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['provider'] == selected_provider]

    if selected_group and selected_group != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if c['group'] == selected_group]

    if search_query:
        filtered_courses = [c for c in filtered_courses if search_query in c['name'].lower() or search_query in c['code'].lower() or search_query in c['mooc'].lower()]

    cards = ""
    for c in filtered_courses:
        badge_color = "bg-blue-100 text-blue-900 border-blue-200" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-900 border-amber-200"
        
        cards += f"""
        <div class="bg-white rounded-3xl border border-slate-200/80 p-6 shadow-sm flex flex-col justify-between card-hover">
            <div>
                <div class="flex justify-between items-start mb-3 gap-2">
                    <span class="font-mono text-xs text-slate-700 font-bold bg-slate-100 px-3 py-1 rounded-xl border border-slate-200">{c['code']}</span>
                    <div class="flex gap-1.5">
                        <span class="px-2.5 py-1 rounded-full text-xs font-bold border {badge_color}">{c['provider']}</span>
                        <span class="bg-blue-50 text-blue-900 text-xs px-2.5 py-1 rounded-full font-bold border border-blue-100">{c['group']}</span>
                    </div>
                </div>
                <h3 class="text-base font-extrabold text-slate-900 mb-2 leading-snug">{c['name']}</h3>
                <p class="text-xs text-slate-500 font-medium mb-2"><i class="fa-solid fa-graduation-cap text-amber-500 mr-1"></i> สาขาวิชาระบบสารสนเทศ (3 หน่วยกิต)</p>
                <div class="bg-slate-50 p-3.5 rounded-2xl border border-slate-100 mb-4">
                    <p class="text-xs font-bold text-slate-700 mb-1"><i class="fa-solid fa-laptop-code text-blue-900 mr-1"></i> รายวิชาที่ต้องเรียนใน {c['provider']}:</p>
                    <p class="text-xs text-slate-600 leading-relaxed">{c['mooc']}</p>
                </div>
            </div>
            <div class="border-t border-slate-100 pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-slate-600 mb-4">
                    <span><i class="fa-regular fa-clock mr-1 text-slate-400"></i> จำนวนชั่วโมง: <b>{c['hours']}</b></span>
                    <span class="font-black text-blue-950 text-sm bg-blue-50 px-2.5 py-0.5 rounded-lg">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['provider'] + '&credits=' + str(c['credits']) + '&cat=' + c['group'] + '" class="block text-center w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-2.5 rounded-xl text-sm transition shadow-sm">ยื่นเทียบโอนวิชานี้</a>' if session.get('role') not in ['admin', 'superadmin'] else ''}
            </div>
        </div>
        """

    content = f"""
    <div class="hero-gradient text-white p-8 rounded-3xl shadow-xl mb-8 flex flex-col md:flex-row justify-between items-center gap-6 border border-slate-700/50">
        <div>
            <span class="bg-amber-500 text-slate-950 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-wider mb-2 inline-block">IS Major Database</span>
            <h2 class="text-3xl font-extrabold">💻 รายวิชาเทียบโอน ThaiMOOC & ChulaMOOC</h2>
            <p class="text-slate-300 text-xs mt-1.5 leading-relaxed">แยกหมวดหมู่อย่างชัดเจนสำหรับนักศึกษาสาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ</p>
        </div>
        <div class="bg-white/10 backdrop-blur-md px-6 py-4 rounded-2xl border border-white/10 text-center shrink-0">
            <span class="text-xs text-slate-300 block font-medium">จำนวนรายวิชาหลักสูตร</span>
            <span class="text-3xl font-black text-amber-400">{len(filtered_courses)}</span> <span class="text-xs text-slate-300">/ {len(IS_THAIMOOC_COURSES)} วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-6 rounded-3xl border border-slate-200/80 shadow-sm mb-8 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-globe mr-1 text-amber-500"></i> สื่อการเรียนรู้ (Provider)</label>
                <select name="provider" onchange="this.form.submit()" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    <option value="ทั้งหมด" {'selected' if selected_provider=='ทั้งหมด' or not selected_provider else ''}>ทุกระบบ (Thai & Chula MOOC)</option>
                    <option value="ThaiMOOC" {'selected' if selected_provider=='ThaiMOOC' else ''}>ThaiMOOC</option>
                    <option value="ChulaMOOC" {'selected' if selected_provider=='ChulaMOOC' else ''}>ChulaMOOC</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-layer-group mr-1 text-blue-900"></i> หมวดวิชาหลักสูตร</label>
                <select name="group" onchange="this.form.submit()" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    <option value="ทั้งหมด" {'selected' if selected_group=='ทั้งหมด' or not selected_group else ''}>ทุกหมวดวิชา</option>
                    <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if selected_group=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                    <option value="หมวดวิชาแกน" {'selected' if selected_group=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                    <option value="หมวดวิชาเลือก" {'selected' if selected_group=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                </select>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"><i class="fa-solid fa-magnifying-glass mr-1 text-blue-900"></i> ค้นหาด้วยรหัสวิชา / ชื่อวิชา / วิชา MOOC</label>
                <div class="flex gap-2">
                    <input type="text" name="search" value="{search_query}" placeholder="พิมพ์ชื่อวิชา..." class="w-full px-4 py-3 border border-slate-200 rounded-2xl text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    <button type="submit" class="bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold px-7 py-3 rounded-2xl text-sm transition shadow-md shadow-blue-900/20 shrink-0">ค้นหา</button>
                </div>
            </div>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-16 text-slate-400 bg-white rounded-3xl border border-slate-200/80">ไม่พบรายวิชาที่ตรงกับเงื่อนไขการค้นหา</div>'}
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
                doc_img="default_doc.png",
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
    selected_major = request.args.get('major_select', 'สาขาวิชาระบบสารสนเทศ')

    # สร้างรายการวิชาสำหรับสาขาวิชาระบบสารสนเทศ
    is_subject_rows = ""
    for idx, item in enumerate(IS_THAIMOOC_COURSES, 1):
        provider_badge = '<span class="bg-blue-100 text-blue-900 border border-blue-200 px-2 py-0.5 rounded-full text-[10px] font-bold">ThaiMOOC</span>' if item['provider'] == 'ThaiMOOC' else '<span class="bg-amber-100 text-amber-900 border border-amber-200 px-2 py-0.5 rounded-full text-[10px] font-bold">ChulaMOOC</span>'
        
        is_subject_rows += f"""
        <tr class="border-b border-slate-100 text-xs hover:bg-slate-50 transition">
            <td class="py-3 px-3 font-mono font-bold text-slate-500">{item['code']}</td>
            <td class="py-3 px-3 font-extrabold text-slate-900">{item['name']}<br>{provider_badge}</td>
            <td class="py-3 px-3 text-slate-600 leading-relaxed max-w-xs">{item['mooc']}</td>
            <td class="py-3 px-3 text-center font-bold text-slate-700">{item['hours']}</td>
            <td class="py-3 px-3 text-center">
                <a href="/submit_credit?course={item['name']}&inst={item['provider']}&credits={item['credits']}&cat={item['group']}&major_select=สาขาวิชาระบบสารสนเทศ#form_section" class="bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold px-3 py-1.5 rounded-xl text-[11px] inline-block shadow-sm">
                    เลือกวิชานี้เพื่อยื่นเทียบโอน
                </a>
            </td>
        </tr>
        """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        
        <!-- Step 1: เลือกสาขาวิชาเพื่อดูวิชาที่ต้องเรียนเพิ่ม -->
        <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-xl">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center font-bold text-lg shrink-0"><i class="fa-solid fa-graduation-cap text-amber-500"></i></div>
                <div>
                    <h3 class="text-xl font-black text-slate-900">เลือกสาขาวิชาเพื่อดูรายวิชาที่ต้องเรียนเพิ่ม</h3>
                    <p class="text-xs text-slate-500">ระบบจะแสดงบทเรียนออนไลน์ ThaiMOOC / ChulaMOOC ทั้งหมดที่ต้องเรียนเพิ่มตามหลักสูตร</p>
                </div>
            </div>

            <form method="GET" action="/submit_credit" class="mb-6">
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">เลือกสาขาวิชาของคุณ *</label>
                <div class="flex gap-3">
                    <select name="major_select" onchange="this.form.submit()" class="w-full border border-slate-200 rounded-2xl p-3.5 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-extrabold text-blue-950">
                        <option value="สาขาวิชาระบบสารสนเทศ" selected>สาขาวิชาระบบสารสนเทศ (Information Systems - IS)</option>
                    </select>
                </div>
            </form>

            <div class="bg-amber-50 border border-amber-200/80 p-4 rounded-2xl mb-6 flex items-start gap-3 text-amber-900 text-xs leading-relaxed font-medium">
                <i class="fa-solid fa-circle-info text-amber-600 text-base shrink-0 mt-0.5"></i>
                <div>
                    <b>คำแนะนำสำหรับนักศึกษาสาขาวิชาระบบสารสนเทศ:</b> ตารางด้านล่างแสดงรายวิชาในหลักสูตรและบทเรียนออนไลน์ ThaiMOOC / ChulaMOOC ที่ต้องเรียนเพิ่ม คุณสามารถคลิกปุ่ม <b>"เลือกวิชานี้เพื่อยื่นเทียบโอน"</b> เพื่อดึงข้อมูลลงแบบฟอร์มด้านล่างได้ทันที
                </div>
            </div>

            <!-- ตารางรายวิชาต้องเรียนเพิ่ม -->
            <div class="overflow-x-auto rounded-2xl border border-slate-200">
                <table class="w-full text-left min-w-[650px]">
                    <thead class="bg-slate-100 text-slate-600 text-[11px] font-bold uppercase tracking-wider border-b border-slate-200">
                        <tr>
                            <th class="py-3 px-3">รหัสวิชา</th>
                            <th class="py-3 px-3">รายวิชาในหลักสูตร IS</th>
                            <th class="py-3 px-3">บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม</th>
                            <th class="py-3 px-3 text-center">ชั่วโมงเรียน</th>
                            <th class="py-3 px-3 text-center">การดำเนินการ</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {is_subject_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Step 2: ฟอร์มยื่นคำร้องขอเทียบโอน -->
        <div id="form_section" class="bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl scroll-mt-6">
            <h3 class="text-2xl font-black text-slate-900 mb-2">แบบฟอร์มยื่นคำขอเทียบโอนหน่วยกิต</h3>
            <p class="text-xs text-slate-500 mb-6">ตรวจสอบรายละเอียดวิชา และกดส่งคำร้องขอเทียบโอนถึงเจ้าหน้าที่</p>
            
            <form method="POST" class="space-y-4">
                <input type="hidden" name="major" value="สาขาวิชาระบบสารสนเทศ">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อรายวิชาในหลักสูตร *</label>
                    <input type="text" name="course_name" value="{init_course}" required placeholder="เช่น คุณภาพการใช้ชีวิต" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">แหล่งเรียนรู้ / ระบบออนไลน์ *</label>
                    <select name="institution" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                        <option value="ThaiMOOC" {'selected' if init_inst=='ThaiMOOC' else ''}>ThaiMOOC</option>
                        <option value="ChulaMOOC" {'selected' if init_inst=='ChulaMOOC' else ''}>ChulaMOOC</option>
                    </select>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">จำนวนหน่วยกิต *</label>
                        <input type="number" name="credits" value="{init_credits}" min="1" max="10" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">หมวดวิชาหลักสูตร</label>
                        <select name="category" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                            <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if init_cat=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                            <option value="หมวดวิชาแกน" {'selected' if init_cat=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                            <option value="หมวดวิชาเลือก" {'selected' if init_cat=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-blue-900/20 text-sm mt-2">
                    <i class="fa-solid fa-paper-plane mr-1 text-amber-400"></i> ยืนยันส่งคำร้องขอเทียบโอน
                </button>
            </form>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    try:
        user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).all()
    except Exception:
        user_requests = []

    rows = ""
    for r in user_requests:
        status = getattr(r, 'status', 'Pending')
        badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอการพิจารณา</span>' if status == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>' if status == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ</span>')
        approved_by = getattr(r, 'approved_by', '-') or '-'

        rows += f"""
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-500">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-blue-900">{getattr(r, 'credits', 0)}</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{approved_by}</td>
            <td class="py-4 px-4">{badge}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">ประวัติคำร้องเทียบโอน (สาขาวิชาระบบสารสนเทศ)</h3>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider"><tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">เจ้าหน้าที่ผู้ตรวจ</th><th class="py-3 px-4">สถานะ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
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
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-extrabold text-slate-900">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-600 font-medium">{getattr(r, 'institution', '-')}</td>
            <td class="py-4 px-4 font-black text-blue-900">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-4 px-4 text-xs text-slate-500 font-medium">{approved_by}</td>
        </tr>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-black text-slate-900">💳 หน่วยกิตสะสมสาขา IS ({total_approved} หน่วยกิต)</h2></div>
    <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
        <table class="w-full text-left min-w-[600px]">
            <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider"><tr><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">ระบบที่เรียน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">ผู้อนุมัติ</th></tr></thead>
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
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-1">{display_title}</h3>
        <p class="text-sm font-bold text-blue-900 mb-1">รหัสนักศึกษา/สมาชิก: {user.member_id or '-'}</p>
        <p class="text-xs text-slate-500 mb-6">สาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ</p>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5 bg-slate-50 p-6 rounded-2xl border border-slate-100 text-sm">
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ชื่อ-สกุล</span> <span class="font-bold text-slate-800">{user.fullname}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เลขบัตรประชาชน</span> <span class="font-bold text-slate-800">{user.id_card or '-'}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">เบอร์โทรศัพท์</span> <span class="font-bold text-slate-800">{user.phone or '-'}</span></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">อีเมล</span> <span class="font-bold text-slate-800">{user.email or '-'}</span></div>
            <div class="md:col-span-2"><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ที่อยู่ตามทะเบียนบ้าน/ที่อยู่ปัจจุบัน</span> <span class="font-bold text-slate-800">{user.address or '-'}</span></div>
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
    <div class="max-w-2xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-2">ส่งคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <p class="text-xs text-slate-500 mb-6">กรอกข้อมูลที่ต้องการอัปเดตเพื่อส่งเรื่องให้เจ้าหน้าที่ประจำสาขาอนุมัติ</p>
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้าใหม่</label>
                    <select name="prefix" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                        <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                        <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                        <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                    </select>
                </div>
                <div class="col-span-2">
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุลใหม่</label>
                    <input type="text" name="fullname" value="{user.fullname}" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ใหม่</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมลใหม่</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
            </div>
            <div>
                <label class="block text-xs font-bold text-rose-600 uppercase tracking-wider mb-1.5">เหตุผลในการขอแก้ไข *</label>
                <textarea name="reason" rows="3" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></textarea>
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-blue-900/20 text-sm mt-2">ส่งคำร้องให้เจ้าหน้าที่พิจารณา</button>
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
        status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติ</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ</span>')
        
        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'

        rows += f"""
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-blue-900">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-4 px-4 font-bold text-slate-900">{student_name}<br><span class="text-xs text-blue-900 font-semibold">({student_code})</span></td>
            <td class="py-4 px-4 text-slate-700 font-medium">{getattr(r, 'course_name', '-')}</td>
            <td class="py-4 px-4 text-slate-500 text-xs font-medium">{getattr(r, 'date_submitted', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">
                <a href="/admin/review/{r.id}" class="bg-gradient-to-r from-blue-900 to-indigo-800 text-white px-4 py-2 rounded-xl text-xs font-bold hover:from-blue-950 hover:to-indigo-900 inline-block shadow-sm">พิจารณา</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องเทียบโอนทั้งหมด (สาขาวิชาระบบสารสนเทศ)</h3>
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">ชื่อนักศึกษา</th><th class="py-3 px-4">วิชาที่ขอเทียบโอน</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400">ไม่มีคำร้องในระบบ</td></tr>'}</tbody>
        </table>
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
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-bold text-blue-900 font-mono">
                {s.member_id or '-'}<br>
                <span class="text-xs text-slate-400 font-normal">({s.id_card or '-'})</span>
            </td>
            <td class="py-4 px-4 font-extrabold text-slate-900">
                {s.prefix or ''} {s.fullname}<br>
                <span class="text-xs text-slate-500 font-normal">สาขาวิชาระบบสารสนเทศ</span>
            </td>
            <td class="py-4 px-4 text-xs text-slate-600 font-medium leading-relaxed">
                <i class="fa-solid fa-phone text-slate-400 mr-1"></i>{s.phone or '-'}<br>
                <i class="fa-solid fa-envelope text-slate-400 mr-1"></i>{s.email or '-'}
            </td>
            <td class="py-4 px-4 text-xs text-slate-600 max-w-xs leading-relaxed">
                {s.address or '-'}
            </td>
            <td class="py-4 px-4 font-black text-center">
                <span class="bg-blue-50 text-blue-900 px-3 py-1 rounded-full text-xs font-bold border border-blue-200">
                    {approved_credits} หน่วยกิต
                </span>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900"><i class="fa-solid fa-users text-blue-900 mr-2"></i>รายชื่อนักศึกษาสาขาวิชาระบบสารสนเทศ</h3>
                <p class="text-xs text-slate-500 mt-1">แสดงข้อมูลนักศึกษาและจำนวนหน่วยกิตที่ได้รับการอนุมัติ</p>
            </div>
            <div class="bg-blue-50 text-blue-900 px-4 py-2 rounded-2xl border border-blue-100 text-xs font-bold">
                นักศึกษาในระบบ: {len(students)} คน
            </div>
        </div>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider">
                <tr>
                    <th class="py-3 px-4">รหัสนักศึกษา / บัตรประชาชน</th>
                    <th class="py-3 px-4">ชื่อ-นามสกุล / สาขา</th>
                    <th class="py-3 px-4">ข้อมูลติดต่อ</th>
                    <th class="py-3 px-4">ที่อยู่</th>
                    <th class="py-3 px-4 text-center">หน่วยกิตสะสม</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
                {rows if rows else '<tr><td colspan="5" class="py-12 text-center text-slate-400">ยังไม่มีนักศึกษาลงทะเบียนในระบบ</td></tr>'}
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
    <div class="max-w-3xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl">
        <div class="text-center mb-8">
            <h2 class="text-2xl font-black text-slate-900">ลงทะเบียนนักศึกษาสาขาวิชาระบบสารสนเทศ</h2>
            <p class="text-xs text-slate-500 mt-1">กรอกข้อมูลส่วนตัวเพื่อสร้างคลังหน่วยกิต Thai/Chula MOOC</p>
        </div>
        <form method="POST" class="space-y-5">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">คำนำหน้า *</label>
                    <select name="prefix" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                        <option value="นาย">นาย</option>
                        <option value="นาง">นาง</option>
                        <option value="นางสาว">นางสาว</option>
                    </select>
                </div>
                <div class="md:col-span-2">
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล *</label>
                    <input type="text" name="fullname" required placeholder="ชื่อ นามสกุล" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เลขบัตรประชาชน (13 หลัก) *</label>
                    <input type="text" name="id_card" maxlength="13" required placeholder="เลขบัตรประชาชน" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">วัน/เดือน/ปีเกิด *</label>
                    <input type="date" name="dob" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์ *</label><input type="tel" name="phone" required placeholder="08X-XXX-XXXX" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมล *</label><input type="email" name="email" required placeholder="student@rmutto.ac.th" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
            </div>

            <div class="border-t border-slate-100 pt-4">
                <label class="block text-xs font-bold text-blue-900 uppercase tracking-wider mb-3"><i class="fa-solid fa-house-user mr-1 text-amber-500"></i> ข้อมูลที่อยู่ตามทะเบียนบ้าน / ที่อยู่ปัจจุบัน</label>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">บ้านเลขที่ *</label><input type="text" name="house_no" required placeholder="123/45" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">หมู่ที่</label><input type="text" name="moo" placeholder="1" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ซอย / ถนน</label><input type="text" name="soi" placeholder="สุขุมวิท 21" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">ตำบล/แขวง *</label><input type="text" name="subdistrict" required placeholder="ตำบล" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">อำเภอ/เขต *</label><input type="text" name="district" required placeholder="อำเภอ" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">จังหวัด *</label><input type="text" name="province" required placeholder="จังหวัด" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                    <div><label class="block text-xs font-semibold text-slate-600 mb-1">รหัสไปรษณีย์ *</label><input type="text" name="postal_code" required placeholder="10110" class="w-full border border-slate-200 rounded-2xl p-3 text-sm bg-slate-50 font-medium"></div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-slate-100 pt-4">
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อผู้ใช้งาน (Username) *</label><input type="text" name="username" required placeholder="ตั้งชื่อผู้ใช้งาน" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
                <div><label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password) *</label><input type="password" name="password" required placeholder="กำหนดรหัสผ่าน" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium"></div>
            </div>

            <button type="submit" class="w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-blue-900/20 text-sm mt-4">
                <i class="fa-solid fa-user-plus mr-1 text-amber-400"></i> ยืนยันการลงทะเบียน
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
    <div class="max-w-md mx-auto my-12 bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl">
        <div class="text-center mb-8">
            <div class="w-14 h-14 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center font-black text-2xl mx-auto mb-3">IS</div>
            <h2 class="text-2xl font-black text-slate-900">เข้าสู่ระบบ</h2>
            <p class="text-xs text-slate-500 mt-1">ธนาคารหน่วยกิต สาขาวิชาระบบสารสนเทศ มทร.ตะวันออก</p>
        </div>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อผู้ใช้งาน หรือ เลขบัตรประชาชน</label>
                <input type="text" name="username" required placeholder="Username / เลขบัตรประชาชน 13 หลัก" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">รหัสผ่าน (Password)</label>
                <input type="password" name="password" required placeholder="รหัสผ่านของคุณ" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-blue-900/20 text-sm mt-2">เข้าสู่ระบบ</button>
            <div class="text-center text-xs pt-4 border-t border-slate-100">
                <a href="/register" class="text-slate-500 hover:text-blue-900 font-medium">ยังไม่มีบัญชีนักศึกษา? <span class="font-bold text-blue-900 underline">ลงทะเบียนเข้าใช้งาน</span></a>
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
            member_id=f"ADM{uuid.uuid4().hex[:4].upper()}",
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
        role_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-900 border border-blue-200">ผู้ดูแลหลัก</span>' if a.role == 'superadmin' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">เจ้าหน้าที่ตรวจงาน</span>'
        
        rows += f"""
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-700">{a.id_card}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{a.fullname}</td>
            <td class="py-4 px-4 text-xs text-slate-600 font-medium">{a.email or '-'}<br>{a.phone or '-'}</td>
            <td class="py-4 px-4">{role_badge}</td>
        </tr>
        """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-xl">
            <div class="flex items-center gap-3 mb-6">
                <div class="w-12 h-12 bg-blue-50 text-blue-900 rounded-2xl flex items-center justify-center font-bold text-xl shrink-0"><i class="fa-solid fa-user-plus text-amber-500"></i></div>
                <div>
                    <h3 class="text-xl font-black text-slate-900">เพิ่มบัญชีเจ้าหน้าที่ตรวจงานสาขาวิชา IS</h3>
                    <p class="text-xs text-slate-500">กำหนดเลขบัตรประชาชนและรหัสผ่านส่วนตัวสำหรับเจ้าหน้าที่ในการเข้าสู่ระบบ</p>
                </div>
            </div>
            
            <form method="POST" class="space-y-4 border-t border-slate-100 pt-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">ชื่อ-นามสกุล เจ้าหน้าที่ <span class="text-rose-500">*</span></label>
                        <input type="text" name="fullname" placeholder="เช่น นายสมศักดิ์ ตรวจการ" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เลขบัตรประชาชน (13 หลัก) <span class="text-rose-500">* (Username)</span></label>
                        <input type="text" name="id_card" maxlength="13" placeholder="เลขบัตรประชาชน 13 หลัก" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">อีเมลเจ้าหน้าที่</label>
                        <input type="email" name="email" placeholder="official@rmutto.ac.th" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">เบอร์โทรศัพท์</label>
                        <input type="tel" name="phone" placeholder="08X-XXX-XXXX" class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">กำหนดรหัสผ่าน <span class="text-rose-500">*</span></label>
                        <input type="password" name="password" placeholder="รหัสผ่านเข้าใช้งาน" required class="w-full border border-slate-200 rounded-2xl p-3 text-sm focus:ring-2 focus:ring-blue-900 outline-none bg-slate-50 font-medium">
                    </div>
                </div>

                <button type="submit" class="w-full bg-gradient-to-r from-blue-900 to-indigo-800 hover:from-blue-950 hover:to-indigo-900 text-white font-bold py-3.5 rounded-2xl transition shadow-md shadow-blue-900/20 text-sm mt-2">
                    <i class="fa-solid fa-plus mr-1 text-amber-400"></i> บันทึกเพิ่มเจ้าหน้าที่
                </button>
            </form>
        </div>

        <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
            <h3 class="text-xl font-black text-slate-900 mb-6"><i class="fa-solid fa-users-gear text-blue-900 mr-2"></i>รายชื่อเจ้าหน้าที่ผู้มีสิทธิ์ในระบบ</h3>
            <table class="w-full text-left min-w-[600px]">
                <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider">
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
        status_badge = '<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">อนุมัติแล้ว</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">ไม่อนุมัติ</span>')
        
        actions = f"""
        <div class="flex items-center gap-2">
            <a href="/admin/approve_profile/{r.id}" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-check"></i> อนุมัติ
            </a>
            <a href="/admin/reject_profile/{r.id}" class="bg-rose-600 hover:bg-rose-700 text-white px-3.5 py-1.5 rounded-xl text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-xmark"></i> ไม่อนุมัติ
            </a>
        </div>
        """ if getattr(r, 'status', 'Pending') == 'Pending' else f'<div class="text-xs text-slate-500 font-medium">ผู้อนุมัติ:<br><span class="text-blue-900 font-bold">{getattr(r, "approved_by", "เจ้าหน้าที่") or "เจ้าหน้าที่"}</span></div>'

        student_name = r.user.fullname if getattr(r, 'user', None) else '-'
        student_code = r.user.member_id if getattr(r, 'user', None) else '-'

        rows += f"""
        <tr class="border-b border-slate-100 text-sm hover:bg-slate-50 transition">
            <td class="py-4 px-4 font-bold text-slate-900">
                {student_name}<br>
                <span class="text-xs text-blue-900 font-semibold">(รหัส: {student_code})</span>
            </td>
            <td class="py-4 px-4 text-xs leading-relaxed font-medium text-slate-700">
                <b>ชื่อใหม่:</b> {getattr(r, 'new_prefix', '')}{getattr(r, 'new_fullname', '')}<br>
                <b>โทร:</b> {getattr(r, 'new_phone', '-')}<br>
                <b>อีเมล:</b> {getattr(r, 'new_email', '-')}<br>
                <b>ที่อยู่ใหม่:</b> {getattr(r, 'new_address', '-')}
            </td>
            <td class="py-4 px-4 text-xs text-slate-600 max-w-xs leading-relaxed">{getattr(r, 'reason', '-')}</td>
            <td class="py-4 px-4 text-xs text-slate-400 font-medium">{getattr(r, 'created_at', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{actions}</td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-slate-200/80 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black text-slate-900 mb-6">รายการคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <table class="w-full text-left min-w-[750px]">
            <thead class="bg-slate-50 border-b border-slate-100 text-xs font-bold text-slate-400 uppercase tracking-wider">
                <tr><th class="py-3 px-4">นักศึกษา</th><th class="py-3 px-4">ข้อมูลที่ขอเปลี่ยนแปลง</th><th class="py-3 px-4">เหตุผลในการขอแก้ไข</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">การจัดการ</th></tr>
            </thead>
            <tbody class="divide-y divide-slate-100">{rows if rows else '<tr><td colspan="6" class="py-12 text-center text-slate-400">ไม่มีคำร้องขอแก้ไขข้อมูลในระบบ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/review/<int:req_id>')
def admin_review(req_id):
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    student_name = req.user.fullname if getattr(req, 'user', None) else '-'
    student_code = req.user.member_id if getattr(req, 'user', None) else '-'

    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 sm:p-10 rounded-3xl border border-slate-200/80 shadow-xl">
        <h3 class="text-2xl font-black text-slate-900 mb-6">พิจารณาคำร้องเทียบโอน #{getattr(req, 'req_code', 'TR001')}</h3>
        <div class="grid md:grid-cols-2 gap-5 text-sm mb-6 bg-slate-50 p-6 rounded-2xl border border-slate-100">
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">ผู้ยื่นคำร้อง</span><b class="text-slate-800">{student_name}</b> (รหัส: {student_code})</div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">หมวดวิชา</span><b class="text-slate-800">{getattr(req, 'category', 'หมวดวิชาศึกษาทั่วไป')}</b></div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">รายวิชา</span><b class="text-slate-800">{getattr(req, 'course_name', '-')}</b> ({getattr(req, 'credits', 0)} หน่วยกิต)</div>
            <div><span class="text-slate-400 block text-xs font-bold uppercase tracking-wider mb-1">สถานะปัจจุบัน</span><b class="text-slate-800">{getattr(req, 'status', 'Pending')}</b></div>
        </div>

        <div class="flex justify-end space-x-3 mt-6 border-t border-slate-100 pt-6">
            <a href="/admin/reject/{req.id}" class="px-6 py-3 bg-rose-600 text-white rounded-2xl text-xs font-bold hover:bg-rose-700 transition">ไม่อนุมัติ</a>
            <a href="/admin/approve/{req.id}" class="px-6 py-3 bg-emerald-600 text-white rounded-2xl text-xs font-bold hover:bg-emerald-700 transition">อนุมัติคำร้อง</a>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/approve/<int:req_id>')
def approve(req_id):
    if session.get('role') in ['admin', 'superadmin']:
        admin_user = User.query.get(session['user_id'])
        req = CreditRequest.query.get(req_id)
        if req:
            req.status = 'Approved'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('อนุมัติคำร้องเทียบโอนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin_requests'))

@app.route('/admin/reject/<int:req_id>')
def reject(req_id):
    if session.get('role') in ['admin', 'superadmin']:
        admin_user = User.query.get(session['user_id'])
        req = CreditRequest.query.get(req_id)
        if req:
            req.status = 'Rejected'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('ปฏิเสธคำร้องเรียบร้อยแล้ว', 'error')
    return redirect(url_for('admin_requests'))

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