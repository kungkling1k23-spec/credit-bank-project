import os
import uuid
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'credit_bank_secret_key_2026_rmutto_all_campuses'

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
    req_code = db.Column(db.String(20), default="TR2567001")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="ในระบบ")
    faculty = db.Column(db.String(100), default="คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ")
    major = db.Column(db.String(100), default="สาขาการจัดการ")
    date_submitted = db.Column(db.String(20), default="2026-08-14")
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
    created_at = db.Column(db.String(20), default="2026-08-14")
    user = db.relationship('User', backref=db.backref('edit_requests', lazy=True))

with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN member_id VARCHAR(20)"))
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN prefix VARCHAR(20) DEFAULT 'นาย'"))
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN approved_by VARCHAR(100)"))
            conn.execute(text("ALTER TABLE profile_edit_request ADD COLUMN approved_by VARCHAR(100)"))
            conn.commit()
    except Exception:
        pass

    db.create_all()

    try:
        main_admin = User.query.filter_by(username='admin').first()
        if not main_admin:
            main_admin = User(
                member_id='ADM000',
                prefix='นาย',
                fullname='ผู้ดูแลระบบหลัก (Super Admin)', 
                id_card='0000000000000',
                username='admin', 
                password=generate_password_hash('admin123'), 
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
        last_user = User.query.filter(User.member_id.like('MB%')).order_by(User.id.desc()).first()
        if not last_user or not last_user.member_id:
            return "MB00001"
        last_num = int(last_user.member_id.replace("MB", ""))
        return f"MB{last_num + 1:05d}"
    except Exception:
        return f"MB{uuid.uuid4().hex[:5].upper()}"

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
    <title>ธนาคารหน่วยกิต - มทร.ตะวันออก</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>body { font-family: 'Sarabun', sans-serif; }</style>
</head>
<body class="bg-gray-50 flex flex-col min-h-screen text-gray-800">

    <nav class="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <a href="/" class="flex items-center gap-2">
                        <div class="w-9 h-9 bg-blue-600 text-white rounded-lg flex items-center justify-center font-bold text-lg shadow-sm">CB</div>
                        <div class="flex flex-col">
                            <span class="font-bold text-gray-900 text-base leading-tight">Credit Bank</span>
                            <span class="text-[10px] text-gray-500 font-medium">มทร.ตะวันออก</span>
                        </div>
                    </a>
                </div>

                <div class="hidden md:flex items-center space-x-1 lg:space-x-2 text-sm font-medium">
                    <a href="/" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">หน้าแรก</a>
                    {% if session.get('user_id') %}
                        {% if session.get('role') in ['admin', 'superadmin'] %}
                            <a href="/admin/requests" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">คำร้องเทียบโอน</a>
                            <a href="/admin/profile_requests" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">คำร้องแก้ไขข้อมูล</a>
                            <a href="/admin/manage_admins" class="px-3 py-2 rounded-lg text-white bg-blue-600 hover:bg-blue-700 transition font-bold shadow-md flex items-center gap-1">
                                <i class="fa-solid fa-user-plus"></i> เพิ่ม/จัดการเจ้าหน้าที่
                            </a>
                        {% else %}
                            <a href="/available_courses" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">รายวิชาเปิดรับเทียบโอน</a>
                            <a href="/submit_credit" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">ยื่นคำขอเทียบโอน</a>
                            <a href="/credits" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">หน่วยกิตสะสม</a>
                            <a href="/history" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">ประวัติคำขอ</a>
                        {% endif %}
                        <a href="/profile" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">
                            {% if session.get('role') in ['admin', 'superadmin'] %}เจ้าหน้าที่{% else %}โปรไฟล์{% endif %}
                        </a>
                        <a href="/logout" class="px-3 py-2 rounded-lg text-red-600 hover:bg-red-50 transition">ออกจากระบบ</a>
                    {% else %}
                        <a href="/login" class="px-4 py-2 rounded-lg text-blue-600 hover:bg-blue-50 transition">เข้าสู่ระบบ</a>
                        <a href="/register" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">สมัครสมาชิก</a>
                    {% endif %}
                </div>

                <div class="flex items-center md:hidden">
                    <button id="mobile-menu-btn" type="button" class="p-2 rounded-lg text-gray-600 hover:text-gray-900 focus:outline-none">
                        <i class="fa-solid fa-bars text-xl"></i>
                    </button>
                </div>
            </div>
        </div>

        <div id="mobile-menu" class="hidden md:hidden border-t border-gray-100 bg-white px-4 pt-2 pb-4 space-y-1 shadow-lg">
            <a href="/" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">หน้าแรก</a>
            {% if session.get('user_id') %}
                {% if session.get('role') in ['admin', 'superadmin'] %}
                    <a href="/admin/requests" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">คำร้องเทียบโอน</a>
                    <a href="/admin/profile_requests" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">คำร้องแก้ไขข้อมูล</a>
                    <a href="/admin/manage_admins" class="block px-3 py-2 rounded-lg text-base font-bold text-white bg-blue-600 hover:bg-blue-700">เพิ่ม/จัดการเจ้าหน้าที่</a>
                {% else %}
                    <a href="/available_courses" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">รายวิชาเปิดรับเทียบโอน</a>
                    <a href="/submit_credit" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">ยื่นคำขอเทียบโอน</a>
                    <a href="/credits" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">หน่วยกิตสะสม</a>
                    <a href="/history" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">ประวัติคำขอ</a>
                {% endif %}
                <a href="/profile" class="block px-3 py-2 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50">โปรไฟล์</a>
                <a href="/logout" class="block px-3 py-2 rounded-lg text-red-600 hover:bg-red-50">ออกจากระบบ</a>
            {% else %}
                <a href="/login" class="block px-3 py-2 rounded-lg text-base font-medium text-blue-600 hover:bg-blue-50">เข้าสู่ระบบ</a>
                <a href="/register" class="block px-3 py-2 rounded-lg text-base font-medium text-blue-600 hover:bg-blue-50">สมัครสมาชิก</a>
            {% endif %}
        </div>
    </nav>

    <div class="max-w-7xl mx-auto px-4 w-full mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="p-4 mb-4 text-sm rounded-xl font-medium shadow-sm flex items-center justify-between {% if category == 'error' or category == 'danger' %}bg-red-50 text-red-700 border border-red-200{% else %}bg-green-50 text-green-700 border border-green-200{% endif %}">
                        <span>{{ message }}</span>
                        <button onclick="this.parentElement.remove()" class="text-xs font-bold px-2">✕</button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {{ content | safe }}
    </main>

    <footer class="bg-slate-900 text-slate-300 mt-auto border-t border-slate-800">
        <div class="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
            <div class="flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 gap-2 text-center sm:text-left">
                <p>© 2026 Credit Bank System. มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก</p>
                <p>ระบบสารสนเทศเพื่อการเรียนรู้ตลอดชีวิต</p>
            </div>
        </div>
    </footer>

    <script>
        const menuBtn = document.getElementById('mobile-menu-btn');
        const mobileMenu = document.getElementById('mobile-menu');
        if (menuBtn && mobileMenu) {
            menuBtn.addEventListener('click', () => { mobileMenu.classList.toggle('hidden'); });
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
        <div class="max-w-5xl mx-auto py-12 grid md:grid-cols-2 gap-12 items-center">
            <div>
                <h1 class="text-4xl font-extrabold text-blue-950 leading-tight mb-4">
                    ระบบธนาคารหน่วยกิต<br><span class="text-blue-600">มทร.ตะวันออก</span>
                </h1>
                <p class="text-gray-600 mb-8 leading-relaxed">
                    สะสมหน่วยกิตจากการเรียนรู้ในระบบ นอกระบบ และตามอัธยาศัย เพื่อใช้เทียบโอนและต่อยอดคุณวุฒิการศึกษาตามคณะและสาขาวิชา ทั้ง 4 วิทยาเขต/เขตพื้นที่
                </p>
                <div class="space-x-4">
                    <a href="/register" class="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 inline-block">สมัครสมาชิก</a>
                    <a href="/login" class="px-6 py-3 bg-white text-blue-900 border font-semibold rounded-lg hover:bg-gray-50 inline-block">เข้าสู่ระบบ</a>
                </div>
            </div>
            <div class="bg-blue-50 p-8 rounded-3xl border border-blue-100 text-center shadow-inner">
                <i class="fa-solid fa-graduation-cap text-9xl text-blue-600 my-8"></i>
                <h3 class="text-xl font-bold text-blue-900">สะสมความรู้ ปลดล็อกโอกาส</h3>
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
        <div class="mb-6">
            <h2 class="text-2xl font-bold text-gray-800">ยินดีต้อนรับ, เจ้าหน้าที่</h2>
            <p class="text-gray-500 text-sm">แผงควบคุมระบบตรวจสอบและอนุมัติสำหรับเจ้าหน้าที่ ({user.fullname})</p>
        </div>

        <div class="mb-8">
            <a href="/admin/manage_admins" class="bg-gradient-to-r from-blue-700 to-indigo-800 text-white p-6 rounded-2xl shadow-md flex items-center justify-between hover:opacity-95 transition block border-2 border-blue-400">
                <div>
                    <div class="flex items-center gap-2 mb-1">
                        <span class="bg-blue-500 text-white text-[11px] font-bold px-2.5 py-0.5 rounded-full uppercase">เมนูจัดการ</span>
                        <h3 class="text-2xl font-bold">➕ คลิกที่นี่เพื่อ "เพิ่มเจ้าหน้าที่ช่วยตรวจงาน"</h3>
                    </div>
                    <p class="text-sm text-blue-100 mt-1">เพิ่มบัญชีเจ้าหน้าที่ใหม่ด้วยเลขบัตรประชาชนและรหัสผ่านส่วนตัว (ปัจจุบันมีเจ้าหน้าที่ {total_admins} คน)</p>
                </div>
                <div class="w-14 h-14 bg-white/20 text-white rounded-2xl flex items-center justify-center text-2xl shrink-0"><i class="fa-solid fa-user-plus"></i></div>
            </a>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="bg-white p-6 rounded-2xl border shadow-sm flex items-center justify-between">
                <div>
                    <p class="text-xs text-gray-500 mb-1">นักศึกษาในระบบ</p>
                    <h3 class="text-2xl font-bold text-blue-900">{total_members} <span class="text-xs text-gray-400 font-normal">คน</span></h3>
                </div>
                <div class="w-12 h-12 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center text-xl"><i class="fa-solid fa-users"></i></div>
            </div>
            <a href="/admin/requests" class="bg-white p-6 rounded-2xl border shadow-sm flex items-center justify-between hover:border-blue-400 transition">
                <div>
                    <p class="text-xs text-gray-500 mb-1">คำร้องเทียบโอนค้างพิจารณา</p>
                    <h3 class="text-2xl font-bold text-amber-600">{pending_credits} <span class="text-xs text-gray-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-amber-50 text-amber-600 rounded-xl flex items-center justify-center text-xl"><i class="fa-solid fa-file-signature"></i></div>
            </a>
            <a href="/admin/profile_requests" class="bg-white p-6 rounded-2xl border shadow-sm flex items-center justify-between hover:border-blue-400 transition">
                <div>
                    <p class="text-xs text-gray-500 mb-1">คำร้องแก้ไขข้อมูลค้างพิจารณา</p>
                    <h3 class="text-2xl font-bold text-indigo-600">{pending_edits} <span class="text-xs text-gray-400 font-normal">รายการ</span></h3>
                </div>
                <div class="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-xl flex items-center justify-center text-xl"><i class="fa-solid fa-user-pen"></i></div>
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

    content = f"""
    <div class="mb-6">
        <h2 class="text-2xl font-bold text-gray-800">สวัสดีครับ, {user.prefix or ''} {user.fullname}</h2>
        <p class="text-sm font-semibold text-blue-600">รหัสสมาชิก: {user.member_id or '-'}</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div class="bg-white p-5 rounded-2xl border shadow-sm flex items-center justify-between">
            <div>
                <p class="text-xs text-gray-500 font-medium mb-1">หน่วยกิตสะสมทั้งหมด</p>
                <h3 class="text-2xl font-bold text-blue-900">{approved_credits} <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-10 h-10 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-5 rounded-2xl border shadow-sm flex items-center justify-between">
            <div>
                <p class="text-xs text-gray-500 font-medium mb-1">รออนุมัติเทียบโอน</p>
                <h3 class="text-2xl font-bold text-amber-600">{pending_credits} <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-10 h-10 bg-amber-50 text-amber-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-clock"></i></div>
        </div>
        <div class="bg-white p-5 rounded-2xl border shadow-sm flex items-center justify-between">
            <div>
                <p class="text-xs text-gray-500 font-medium mb-1">คำร้องขอเทียบโอน</p>
                <h3 class="text-2xl font-bold text-gray-800">{len(user_requests)} <span class="text-xs font-normal text-gray-400">รายการ</span></h3>
            </div>
            <div class="w-10 h-10 bg-purple-50 text-purple-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-list-check"></i></div>
        </div>
        <div class="bg-white p-5 rounded-2xl border shadow-sm flex items-center justify-between">
            <div>
                <p class="text-xs text-gray-500 font-medium mb-1">เป้าหมายหลักสูตร</p>
                <h3 class="text-2xl font-bold text-emerald-600">120 <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-10 h-10 bg-emerald-50 text-emerald-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-bullseye"></i></div>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <a href="/available_courses" class="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md hover:border-blue-300 transition block">
            <i class="fa-solid fa-book-open text-3xl text-blue-600 mb-3"></i>
            <h3 class="font-bold text-gray-800 mb-1">ค้นหารายวิชาเปิดเทียบโอน</h3>
            <p class="text-xs text-gray-500">เลือกดูรายวิชาที่เปิดรับเทียบโอนแยกตามคณะ/สาขาวิชา และวิทยาเขต</p>
        </a>
        <a href="/submit_credit" class="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md hover:border-blue-300 transition block">
            <i class="fa-solid fa-file-pen text-3xl text-amber-600 mb-3"></i>
            <h3 class="font-bold text-gray-800 mb-1">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
            <p class="text-xs text-gray-500">ส่งเอกสารหลักฐานขอเทียบโอนรายวิชาเข้าสู่ระบบ</p>
        </a>
        <a href="/request_edit_profile" class="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md hover:border-blue-300 transition block">
            <i class="fa-solid fa-user-gear text-3xl text-purple-600 mb-3"></i>
            <h3 class="font-bold text-gray-800 mb-1">ส่งคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
            <p class="text-xs text-gray-500">แจ้งเรื่องขอเปลี่ยนชื่อ-สกุล อีเมล หรือเบอร์โทรศัพท์ถึงเจ้าหน้าที่</p>
        </a>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    # รวมรายวิชาเทียบโอน มทร.ตะวันออก จากไฟล์ฉบับสำรวจทุกวิทยาเขต
    all_courses = [
        # รายวิชาเทียบโอนจริงที่พบหลักฐาน (จักรพงษภูวนารถ - คณะบริหารธุรกิจฯ)
        {"code": "04-00-101", "name": "หลักการตลาด", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "03-211-101 / 3200-1005", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขาการจัดการ 2568 (วิชาเดิม: หลักการตลาด / การขายเบื้องต้น)"},
        {"code": "04-00-102", "name": "หลักเศรษฐศาสตร์", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "3200-1001 / 05-000-101", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขาการจัดการ 2568 (วิชาเดิม: หลักเศรษฐศาสตร์)"},
        {"code": "04-00-104", "name": "กฎหมายธุรกิจและการภาษีอากร", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ / การตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30001-1055 / 20215-2004", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขาการจัดการและแบบเทียบโอนสาขาการตลาด 2568"},
        {"code": "04-00-106", "name": "ภาษาอังกฤษเพื่อการสื่อสารธุรกิจ", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ / การตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "05-081-122 / 05-031-105", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขาการจัดการและสาขาการตลาด 2568"},
        {"code": "04-00-107", "name": "การบัญชีเบื้องต้น", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ / การตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวช./ปวส. การบัญชี", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขาการจัดการและสาขาการตลาด"},
        {"code": "04-00-105", "name": "สถิติเพื่อการวิจัยธุรกิจ", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส./รายวิชาเทียบเท่า", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามแบบเทียบโอนสาขาการตลาด 2568"},
        {"code": "04-00-108", "name": "การเงินธุรกิจ", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส./รายวิชาเทียบเท่า", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามแบบเทียบโอนสาขาการตลาด 2568"},
        {"code": "04-00-109", "name": "การจัดการโลจิสติกส์", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส./รายวิชาเทียบเท่า", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามแบบเทียบโอนสาขาการตลาด 2568"},
        {"code": "04-00-110", "name": "ทักษะความเข้าใจธุรกิจ", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการตลาด", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส./รายวิชาเทียบเท่า", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามแบบเทียบโอนสาขาการตลาด 2568"},
        {"code": "00-31-001", "name": "เทคโนโลยีสารสนเทศในยุคดิจิทัล", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "3001-2100 / 30204-2103", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568 (วิชาเดิม: เทคโนโลยีสารสนเทศเพื่องานอาชีพ)"},
        {"code": "00-31-002", "name": "คณิตศาสตร์และสถิติในชีวิตประจำวัน", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "05-000-105 / 30000-1401", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568 (วิชาเดิม: สถิติธุรกิจ / คณิตศาสตร์เพื่องานอาชีพ)"},
        {"code": "TR-IT01", "name": "การประกอบเครื่องและการติดตั้งซอฟต์แวร์", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30204-2201 / 5051106", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568"},
        {"code": "TR-IT02", "name": "การใช้โปรแกรมสำนักงานชั้นสูง", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30204-2202 / 5051107", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568"},
        {"code": "TR-IT03", "name": "โปรแกรมกราฟิกสำหรับการออกแบบเว็บไซต์", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30204-2403", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568"},
        {"code": "TR-IT04", "name": "การผลิตสื่อมัลติมีเดียสำหรับธุรกิจดิจิทัล", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30204-2204", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568"},
        {"code": "TR-IT05", "name": "การออกแบบและพัฒนาเว็บไซต์", "campus": "เขตพื้นที่จักรพงษภูวนารถ", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "30901-1002", "status": "มทร.ตะวันออก", "desc": "เทียบโอนได้ตามคู่มือเทียบโอนสาขา IT 2568"},

        # วิทยาเขตบางพระ (ชลบุรี)
        {"code": "00-11-001", "name": "ภาษาไทยเพื่อการสื่อสาร", "campus": "เขตพื้นที่บางพระ", "faculty": "คณะมนุษยศาสตร์และสังคมศาสตร์", "major": "หมวดวิชาศึกษาทั่วไป", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "ปวส. / มหาวิทยาลัยอื่น", "status": "มทร.ตะวันออก", "desc": "ทักษะการฟัง การพูด การอ่าน และการเขียนภาษาไทยเพื่อการสื่อสารในงานอาชีพ"},
        {"code": "00-12-002", "name": "ภาษาอังกฤษเพื่อการสื่อสารสากล", "campus": "เขตพื้นที่บางพระ", "faculty": "คณะมนุษยศาสตร์และสังคมศาสตร์", "major": "หมวดวิชาศึกษาทั่วไป", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "ปวส. / มหาวิทยาลัยอื่น", "status": "มทร.ตะวันออก", "desc": "การสื่อสารภาษาอังกฤษเบื้องต้น การนำเสนอผลงาน และไวยากรณ์ประยุกต์"},
        {"code": "01-10-101", "name": "หลักสัตวศาสตร์เบื้องต้น", "campus": "เขตพื้นที่บางพระ", "faculty": "คณะเกษตรศาสตร์และทรัพยากรธรรมชาติ", "major": "สาขาวิชาสัตวศาสตร์", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.เกษตรศาสตร์", "status": "มทร.ตะวันออก", "desc": "การเลี้ยงดูและการจัดการสัตว์เศรษฐกิจ การสุขาภิบาล และโภชนาการสัตว์"},
        {"code": "02-20-102", "name": "วิทยาศาสตร์และเทคโนโลยีเพื่อชีวิต", "campus": "เขตพื้นที่บางพระ", "faculty": "คณะวิทยาศาสตร์และเทคโนโลยี", "major": "ทุกสาขาวิชา", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "ปวส. / สถาบันเดิม", "status": "มทร.ตะวันออก", "desc": "กระบวนการทางวิทยาศาสตร์ นวัตกรรมเทคโนโลยีสมัยใหม่ และการประยุกต์ในชีวิตประจำวัน"},
        {"code": "06-10-101", "name": "การจัดการการบินเบื้องต้น", "campus": "เขตพื้นที่บางพระ", "faculty": "สถาบันเทคโนโลยีการบินและอวกาศ", "major": "สาขาวิชาการจัดการการบิน", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส. / สถานศึกษาเดิม", "status": "มทร.ตะวันออก", "desc": "ระบบการขนส่งทางอากาศ โครงสร้างอุตสาหกรรมการบิน และกฎหมายการบินเบื้องต้น"},

        # วิทยาเขตอุเทนถวาย (กรุงเทพฯ)
        {"code": "08-11-101", "name": "เขียนแบบวิศวกรรม (Engineering Drawing)", "campus": "เขตพื้นที่อุเทนถวาย", "faculty": "คณะวิศวกรรมศาสตร์และสถาปัตยกรรมศาสตร์", "major": "สาขาวิชาวิศวกรรมโยธา", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.ช่างก่อสร้าง/ช่างโยธา", "status": "มทร.ตะวันออก", "desc": "ทักษะการเขียนแบบวิศวกรรม สัญลักษณ์ทางช่าง การเขียนแบบด้วยคอมพิวเตอร์ CAD"},
        {"code": "08-12-102", "name": "การสำรวจทางวิศวกรรม (Engineering Surveying)", "campus": "เขตพื้นที่อุเทนถวาย", "faculty": "คณะวิศวกรรมศาสตร์และสถาปัตยกรรมศาสตร์", "major": "สาขาวิชาวิศวกรรมสำรวจ/โยธา", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.ช่างสำรวจ/โยธา", "status": "มทร.ตะวันออก", "desc": "การใช้กล้องรังวัด การทำแผนที่ภูมิประเทศ การหาค่าระดับ และงานสำรวจเพื่อการก่อสร้าง"},
        {"code": "08-20-103", "name": "การออกแบบสถาปัตยกรรมเบื้องต้น", "campus": "เขตพื้นที่อุเทนถวาย", "faculty": "คณะวิศวกรรมศาสตร์และสถาปัตยกรรมศาสตร์", "major": "สาขาวิชาสถาปัตยกรรมภายใน", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.สถาปัตยกรรม", "status": "มทร.ตะวันออก", "desc": "องค์ประกอบศิลป์ การจัดพื้นที่ใช้สอย การเขียนแบบสถาปัตยกรรม และแนวคิดการออกแบบ"},

        # วิทยาเขตจันทบุรี
        {"code": "10-11-101", "name": "การจัดการเพื่อผู้ประกอบการยุคดิจิทัล", "campus": "เขตพื้นที่จันทบุรี", "faculty": "คณะเทคโนโลยีสังคม", "major": "สาขาวิชาการจัดการเพื่อผู้ประกอบการ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.การจัดการ/การตลาด", "status": "มทร.ตะวันออก", "desc": "การเริ่มธุรกิจใหม่ การวางแผนการเงิน การตลาดดิจิทัล และนวัตกรรมสำหรับผู้ประกอบการ"},
        {"code": "10-12-102", "name": "นวัตกรรมการบริการและการท่องเที่ยว", "campus": "เขตพื้นที่จันทบุรี", "faculty": "คณะเทคโนโลยีสังคม", "major": "สาขาวิชานวัตกรรมการท่องเที่ยวและการโรงแรม", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.การท่องเที่ยวและโรงแรม", "status": "มทร.ตะวันออก", "desc": "อุตสาหกรรมการท่องเที่ยว พฤติกรรมนักท่องเที่ยว การจัดการโรงแรมและการบริการลูกค้า"},
        {"code": "10-21-103", "name": "เทคโนโลยียานยนต์ไฟฟ้า (EV Technology)", "campus": "เขตพื้นที่จันทบุรี", "faculty": "คณะวิศวกรรมศาสตร์", "major": "สาขาวิชาวิศวกรรมยานยนต์ไฟฟ้า", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.ช่างยนต์/ไฟฟ้า", "status": "มทร.ตะวันออก", "desc": "ระบบขับเคลื่อนไฟฟ้า แบตเตอรี่และการประจุพลังงาน ความปลอดภัยในยานยนต์ไฟฟ้า"},

        # MOOC / เรียนรู้นอกระบบ
        {"code": "MOOC-0008", "name": "การเงินส่วนบุคคล (Personal Finance Online)", "campus": "ทุกวิทยาเขต", "faculty": "ทุกคณะ", "major": "ทุกสาขาวิชา", "main_category": "หมวดวิชาเลือกเสรี", "credits": 3, "source": "ThaiMOOC", "status": "ต้องตรวจสอบกับประกาศ", "desc": "การวางแผนการเงิน การออม การลงทุน สินเชื่อ และภาษีบุคคลธรรมดาผ่านระบบออนไลน์"}
    ]

    search_query = request.args.get('search', '').strip().lower()
    selected_campus = request.args.get('campus', '').strip()

    filtered_courses = all_courses

    if selected_campus and selected_campus != "ทั้งหมด":
        filtered_courses = [c for c in filtered_courses if selected_campus in c['campus']]

    if search_query:
        filtered_courses = [c for c in filtered_courses if search_query in c['name'].lower() or search_query in c['code'].lower() or search_query in c['faculty'].lower() or search_query in c['major'].lower()]

    cards = ""
    for c in filtered_courses:
        cards += f"""
        <div class="bg-white p-6 rounded-2xl border shadow-sm flex flex-col justify-between hover:shadow-md transition">
            <div>
                <div class="flex justify-between items-start mb-2">
                    <span class="font-mono text-xs text-gray-500 font-bold bg-gray-100 px-2 py-0.5 rounded">{c['code']}</span>
                    <span class="bg-blue-100 text-blue-800 text-xs px-2.5 py-1 rounded-full font-semibold">{c['main_category']}</span>
                </div>
                <h3 class="text-base font-bold text-gray-800 mb-2 leading-snug">{c['name']}</h3>
                <p class="text-xs text-blue-700 font-semibold mb-1"><i class="fa-solid fa-location-dot mr-1"></i> {c['campus']}</p>
                <p class="text-xs text-gray-600 font-medium mb-1"><i class="fa-solid fa-building-columns mr-1"></i> {c['faculty']}</p>
                <p class="text-xs text-emerald-700 font-medium mb-2"><i class="fa-solid fa-graduation-cap mr-1"></i> {c['major']}</p>
                <p class="text-xs text-gray-500 mb-4 leading-relaxed bg-gray-50 p-2.5 rounded-lg border">{c['desc']}</p>
            </div>
            <div class="border-t pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-gray-600 mb-4">
                    <span><i class="fa-solid fa-school mr-1 text-gray-400"></i> วิชาเดิม: {c['source']}</span>
                    <span class="font-bold text-blue-900 text-sm">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['source'] + '&credits=' + str(c['credits']) + '&cat=' + c['main_category'] + '&fac=' + c['faculty'] + '&maj=' + c['major'] + '" class="block text-center w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 rounded-lg text-sm transition">เทียบโอนวิชานี้</a>' if session.get('role') not in ['admin', 'superadmin'] else ''}
            </div>
        </div>
        """

    content = f"""
    <div class="bg-gradient-to-r from-blue-900 via-indigo-900 to-blue-800 text-white p-6 rounded-2xl shadow-sm mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
            <h2 class="text-2xl font-bold">📚 รายวิชาเปิดรับเทียบโอน (มทร.ตะวันออก)</h2>
            <p class="text-blue-100 text-xs mt-1">ฐานข้อมูลรายวิชาเปิดรับเทียบโอนฉบับสำรวจ รวบรวมทุกวิทยาเขต/เขตพื้นที่ คณะ และสาขาวิชา</p>
        </div>
        <div class="bg-white/10 backdrop-blur px-5 py-3 rounded-xl border border-white/20 text-center min-w-[180px]">
            <span class="text-xs text-blue-200 block">จำนวนรายวิชาที่พบ</span>
            <span class="text-2xl font-extrabold text-white">{len(filtered_courses)}</span> <span class="text-xs text-blue-200">/ {len(all_courses)} วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-5 rounded-2xl border shadow-sm mb-6 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
                <label class="block text-xs font-semibold text-gray-600 mb-1"><i class="fa-solid fa-location-dot mr-1"></i> เลือกวิทยาเขต / เขตพื้นที่</label>
                <select name="campus" onchange="this.form.submit()" class="w-full border rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    <option value="ทั้งหมด" {'selected' if selected_campus=='ทั้งหมด' or not selected_campus else ''}>ทุกวิทยาเขต/เขตพื้นที่</option>
                    <option value="จักรพงษภูวนารถ" {'selected' if selected_campus=='จักรพงษภูวนารถ' else ''}>เขตพื้นที่จักรพงษภูวนารถ (กรุงเทพฯ)</option>
                    <option value="บางพระ" {'selected' if selected_campus=='บางพระ' else ''}>เขตพื้นที่บางพระ (ชลบุรี)</option>
                    <option value="อุเทนถวาย" {'selected' if selected_campus=='อุเทนถวาย' else ''}>เขตพื้นที่อุเทนถวาย (กรุงเทพฯ)</option>
                    <option value="จันทบุรี" {'selected' if selected_campus=='จันทบุรี' else ''}>เขตพื้นที่จันทบุรี</option>
                </select>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-semibold text-gray-600 mb-1"><i class="fa-solid fa-magnifying-glass mr-1"></i> ค้นหาด้วยรหัสวิชา / ชื่อวิชา / คณะ / สาขา</label>
                <div class="flex gap-2">
                    <input type="text" name="search" value="{search_query}" placeholder="พิมพ์คำที่ต้องการค้นหา..." class="w-full px-4 py-2 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-2 rounded-xl text-sm transition shrink-0">ค้นหา</button>
                </div>
            </div>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-12 text-gray-400 bg-white rounded-2xl border">ไม่พบรายวิชาที่ตรงกับเงื่อนไขการค้นหา</div>'}
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
    <div class="max-w-md mx-auto my-8 bg-white p-8 rounded-2xl border shadow-sm">
        <h2 class="text-2xl font-bold text-center text-blue-900 mb-6">เข้าสู่ระบบ</h2>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อผู้ใช้งาน หรือ เลขบัตรประชาชน</label>
                <input type="text" name="username" required placeholder="Username / เลขบัตรประชาชน 13 หลัก" class="w-full border rounded-lg p-2.5 text-sm">
            </div>
            <div>
                <label class="block text-xs font-semibold text-gray-600 mb-1">รหัสผ่าน (Password)</label>
                <input type="password" name="password" required placeholder="รหัสผ่านของคุณ" class="w-full border rounded-lg p-2.5 text-sm">
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700 transition shadow-sm">เข้าสู่ระบบ</button>
            <div class="text-center text-xs pt-2">
                <a href="/register" class="text-gray-500 hover:underline">ยังไม่มีบัญชีนักศึกษา? สมัครสมาชิก</a>
            </div>
        </form>
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
            id_card_img="default_id_card.png",
            username=username,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()

        flash(f'สมัครสมาชิกเรียบร้อยแล้ว! รหัสสมาชิกของคุณคือ: {new_member_id}', 'success')
        return redirect(url_for('login'))

    content = """
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h2 class="text-2xl font-bold text-center text-blue-900 mb-6">สมัครสมาชิกนักศึกษา</h2>
        <form method="POST" class="space-y-4">
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">คำนำหน้า *</label>
                    <select name="prefix" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="นาย">นาย</option>
                        <option value="นาง">นาง</option>
                        <option value="นางสาว">นางสาว</option>
                    </select>
                </div>
                <div class="md:col-span-2">
                    <label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อ-นามสกุล *</label>
                    <input type="text" name="fullname" required placeholder="ชื่อ นามสกุล" class="w-full border rounded-lg p-2.5 text-sm">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">เลขบัตรประชาชน (13 หลัก) *</label>
                    <input type="text" name="id_card" maxlength="13" required placeholder="เลขบัตรประชาชน" class="w-full border rounded-lg p-2.5 text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">วัน/เดือน/ปีเกิด *</label>
                    <input type="date" name="dob" required class="w-full border rounded-lg p-2.5 text-sm">
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">เบอร์โทรศัพท์ *</label><input type="tel" name="phone" required placeholder="08X-XXX-XXXX" class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">อีเมล *</label><input type="email" name="email" required placeholder="student@rmutto.ac.th" class="w-full border rounded-lg p-2.5 text-sm"></div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อผู้ใช้งาน (Username) *</label><input type="text" name="username" required placeholder="ตั้งชื่อผู้ใช้งาน" class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">รหัสผ่าน (Password) *</label><input type="password" name="password" required placeholder="กำหนดรหัสผ่าน" class="w-full border rounded-lg p-2.5 text-sm"></div>
            </div>

            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-3 rounded-lg hover:bg-blue-700 transition shadow-sm text-base mt-2">
                <i class="fa-solid fa-user-plus mr-1"></i> ยืนยันการสมัครสมาชิก
            </button>
        </form>
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
        badge = '<span class="px-3 py-1 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-800">รอการพิจารณา</span>' if status == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">อนุมัติแล้ว</span>' if status == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        approved_by = getattr(r, 'approved_by', '-') or '-'

        rows += f"""
        <tr class="border-b text-sm">
            <td class="py-3 px-4 font-mono font-bold text-gray-500">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-3 px-4 font-medium text-gray-800">{getattr(r, 'course_name', '-')}</td>
            <td class="py-3 px-4 text-gray-600">{getattr(r, 'institution', '-')}</td>
            <td class="py-3 px-4 font-bold text-blue-900">{getattr(r, 'credits', 0)}</td>
            <td class="py-3 px-4 text-xs text-gray-500">{approved_by}</td>
            <td class="py-3 px-4">{badge}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
        <h3 class="text-xl font-bold text-gray-800 mb-4">ประวัติคำร้องเทียบโอน</h3>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase"><tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">สถาบัน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">เจ้าหน้าที่ผู้ตรวจ</th><th class="py-3 px-4">สถานะ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-6 text-center text-gray-400">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
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
        <tr class="border-b text-sm">
            <td class="py-3.5 px-4 font-medium text-gray-800">{getattr(r, 'course_name', '-')}</td>
            <td class="py-3.5 px-4 text-gray-600">{getattr(r, 'institution', '-')}</td>
            <td class="py-3.5 px-4 font-bold text-blue-900">{getattr(r, 'credits', 0)} หน่วยกิต</td>
            <td class="py-3.5 px-4 text-xs text-gray-500">{approved_by}</td>
        </tr>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-bold text-gray-800">💳 หน่วยกิตสะสมของฉัน ({total_approved} หน่วยกิต)</h2></div>
    <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
        <table class="w-full text-left min-w-[600px]">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase"><tr><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">สถาบัน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">ผู้อนุมัติ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="4" class="py-8 text-center text-gray-400 text-sm">ยังไม่มีรายการหน่วยกิตที่ได้รับการอนุมัติ</td></tr>'}</tbody>
        </table>
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
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-2">ส่งคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <form method="POST" class="space-y-4">
            <div class="grid grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">คำนำหน้าใหม่</label>
                    <select name="prefix" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="นาย" {'selected' if user.prefix=='นาย' else ''}>นาย</option>
                        <option value="นาง" {'selected' if user.prefix=='นาง' else ''}>นาง</option>
                        <option value="นางสาว" {'selected' if user.prefix=='นางสาว' else ''}>นางสาว</option>
                    </select>
                </div>
                <div class="col-span-2">
                    <label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อ-นามสกุลใหม่</label>
                    <input type="text" name="fullname" value="{user.fullname}" required class="w-full border rounded-lg p-2.5 text-sm">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">เบอร์โทรศัพท์ใหม่</label><input type="tel" name="phone" value="{user.phone or ''}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">อีเมลใหม่</label><input type="email" name="email" value="{user.email or ''}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            </div>
            <div>
                <label class="block text-xs font-bold text-red-600 mb-1">เหตุผลในการขอแก้ไข *</label>
                <textarea name="reason" rows="3" required class="w-full border rounded-lg p-2.5 text-sm"></textarea>
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ส่งคำร้องให้เจ้าหน้าที่พิจารณา</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        req = CreditRequest(
            user_id=session['user_id'], 
            course_name=request.form.get('course_name', 'วิชาเทียบโอน'), 
            institution=request.form.get('institution', 'สถาบันการศึกษา'), 
            credits=int(request.form.get('credits', 3)),
            category=request.form.get('category', 'ในระบบ'),
            faculty=request.form.get('faculty', 'คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ'),
            major=request.form.get('major', 'สาขาการจัดการ'),
            doc_img="default_doc.png"
        )
        db.session.add(req)
        db.session.commit()
        flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    # รับค่าจาก Query Parameters จากปุ่ม "เทียบโอนวิชานี้"
    init_course = request.args.get('course', '')
    init_inst = request.args.get('inst', '')
    init_credits = request.args.get('credits', '3')
    init_cat = request.args.get('cat', 'ในระบบ')
    init_fac = request.args.get('fac', '')
    init_maj = request.args.get('maj', '')

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-6">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
        <form method="POST" class="space-y-4">
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อหลักสูตร / รายวิชา *</label><input type="text" name="course_name" value="{init_course}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">สถาบันเดิม / แหล่งเรียนรู้ *</label><input type="text" name="institution" value="{init_inst}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">จำนวนหน่วยกิต *</label><input type="number" name="credits" value="{init_credits}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">หมวดหมู่การเรียนรู้</label>
                    <select name="category" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="ในระบบ" {'selected' if init_cat=='ในระบบ' or init_cat=='หมวดวิชาเฉพาะ' or init_cat=='หมวดวิชาศึกษาทั่วไป' else ''}>ในระบบ</option>
                        <option value="นอกระบบ" {'selected' if init_cat=='นอกระบบ' else ''}>นอกระบบ</option>
                        <option value="ตามอัธยาศัย" {'selected' if init_cat=='ตามอัธยาศัย' or init_cat=='หมวดวิชาเลือกเสรี' else ''}>ตามอัธยาศัย</option>
                    </select>
                </div>
            </div>
            <input type="hidden" name="faculty" value="{init_fac}">
            <input type="hidden" name="major" value="{init_maj}">
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ส่งคำร้องขอเทียบโอน</button>
        </form>
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
    <div class="max-w-3xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-2xl font-bold text-gray-800 mb-2">{display_title}</h3>
        <p class="text-sm font-semibold text-blue-600 mb-6">รหัสประจำตัว: {user.member_id or '-'}</p>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-gray-50 p-4 rounded-xl text-sm">
            <div><span class="text-gray-400 block text-xs">ชื่อ-สกุล</span> <span class="font-semibold text-gray-700">{user.fullname}</span></div>
            <div><span class="text-gray-400 block text-xs">เลขบัตรประชาชน</span> <span class="font-semibold text-gray-700">{user.id_card or '-'}</span></div>
            <div><span class="text-gray-400 block text-xs">เบอร์โทรศัพท์</span> <span class="font-semibold text-gray-700">{user.phone or '-'}</span></div>
            <div><span class="text-gray-400 block text-xs">อีเมล</span> <span class="font-semibold text-gray-700">{user.email or '-'}</span></div>
        </div>
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
        role_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800">ผู้ดูแลหลัก</span>' if a.role == 'superadmin' else '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-gray-100 text-gray-800">เจ้าหน้าที่ตรวจงาน</span>'
        
        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50">
            <td class="py-3.5 px-4 font-mono font-bold text-gray-700">{a.id_card}</td>
            <td class="py-3.5 px-4 font-semibold text-gray-800">{a.fullname}</td>
            <td class="py-3.5 px-4 text-xs text-gray-600">{a.email or '-'}<br>{a.phone or '-'}</td>
            <td class="py-3.5 px-4">{role_badge}</td>
        </tr>
        """

    content = f"""
    <div class="max-w-4xl mx-auto space-y-8">
        <div class="bg-white p-6 rounded-2xl border shadow-sm">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-10 h-10 bg-blue-100 text-blue-700 rounded-xl flex items-center justify-center font-bold text-lg"><i class="fa-solid fa-user-plus"></i></div>
                <div>
                    <h3 class="text-xl font-bold text-gray-800">เพิ่มบัญชีเจ้าหน้าที่ตรวจงาน</h3>
                    <p class="text-xs text-gray-500">กำหนดเลขบัตรประชาชนและรหัสผ่านส่วนตัวสำหรับเจ้าหน้าที่ในการเข้าสู่ระบบ</p>
                </div>
            </div>
            
            <form method="POST" class="space-y-4 border-t pt-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อ-นามสกุล เจ้าหน้าที่ <span class="text-red-500">*</span></label>
                        <input type="text" name="fullname" placeholder="เช่น นายสมศักดิ์ ตรวจการ" required class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 mb-1">เลขบัตรประชาชน (13 หลัก) <span class="text-red-500">* (ใช้เป็น Username)</span></label>
                        <input type="text" name="id_card" maxlength="13" placeholder="เลขบัตรประชาชน 13 หลัก" required class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 mb-1">อีเมลเจ้าหน้าที่</label>
                        <input type="email" name="email" placeholder="official@rmutto.ac.th" class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 mb-1">เบอร์โทรศัพท์</label>
                        <input type="tel" name="phone" placeholder="08X-XXX-XXXX" class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-gray-600 mb-1">กำหนดรหัสผ่านส่วนตัว <span class="text-red-500">*</span></label>
                        <input type="password" name="password" placeholder="รหัสผ่านเข้าใช้งาน" required class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                </div>

                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg transition shadow-sm">
                    <i class="fa-solid fa-plus mr-1"></i> บันทึกเพิ่มเจ้าหน้าที่
                </button>
            </form>
        </div>

        <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
            <h3 class="text-lg font-bold text-gray-800 mb-4"><i class="fa-solid fa-users-gear text-blue-600 mr-2"></i>รายชื่อเจ้าหน้าที่ผู้มีสิทธิ์ในระบบ</h3>
            <table class="w-full text-left min-w-[600px]">
                <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase">
                    <tr><th class="py-3 px-4">เลขบัตรประชาชน (Username)</th><th class="py-3 px-4">ชื่อ-สกุล เจ้าหน้าที่</th><th class="py-3 px-4">ข้อมูลติดต่อ</th><th class="py-3 px-4">สิทธิ์ผู้ใช้งาน</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/requests')
def admin_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    all_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    rows = ""
    for r in all_requests:
        status_badge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-800">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800">อนุมัติ</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        
        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50">
            <td class="py-3 px-4 font-mono font-bold text-blue-900">{getattr(r, 'req_code', 'TR001')}</td>
            <td class="py-3 px-4 font-medium">{r.user.fullname if r.user else '-'}<br><span class="text-xs text-blue-600">({r.user.member_id if r.user else '-'})</span></td>
            <td class="py-3 px-4 text-gray-600">{getattr(r, 'course_name', '-')}</td>
            <td class="py-3 px-4 text-gray-500">{getattr(r, 'date_submitted', '-')}</td>
            <td class="py-3 px-4">{status_badge}</td>
            <td class="py-3 px-4">
                <a href="/admin/review/{r.id}" class="bg-blue-600 text-white px-3 py-1.5 rounded text-xs font-semibold hover:bg-blue-700 inline-block">พิจารณา</a>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
        <h3 class="text-xl font-bold text-gray-800 mb-4">รายการคำร้องเทียบโอนทั้งหมด</h3>
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase">
                <tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">ชื่อนักศึกษา</th><th class="py-3 px-4">วิชาที่ขอเทียบโอน</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th><th class="py-3 px-4">จัดการ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-6 text-center text-gray-400">ไม่มีคำร้องในระบบ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/profile_requests')
def admin_profile_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    
    requests_list = ProfileEditRequest.query.order_by(ProfileEditRequest.id.desc()).all()
    rows = ""
    for r in requests_list:
        status_badge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-800">รอพิจารณา</span>' if getattr(r, 'status', 'Pending') == 'Pending' else ('<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800">อนุมัติแล้ว</span>' if getattr(r, 'status', '') == 'Approved' else '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        
        actions = f"""
        <div class="flex items-center gap-2">
            <a href="/admin/approve_profile/{r.id}" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-check"></i> อนุมัติ
            </a>
            <a href="/admin/reject_profile/{r.id}" class="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-xmark"></i> ไม่อนุมัติ
            </a>
        </div>
        """ if getattr(r, 'status', 'Pending') == 'Pending' else f'<div class="text-xs text-gray-500 font-medium">ผู้อนุมัติ:<br><span class="text-blue-700 font-bold">{getattr(r, "approved_by", "เจ้าหน้าที่") or "เจ้าหน้าที่"}</span></div>'

        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50 transition">
            <td class="py-4 px-4 font-medium text-gray-800">
                {r.user.fullname if r.user else '-'}<br>
                <span class="text-xs text-blue-600 font-semibold">(รหัส: {r.user.member_id if r.user else '-'})</span>
            </td>
            <td class="py-4 px-4 text-xs leading-relaxed">
                <b>ชื่อใหม่:</b> {getattr(r, 'new_prefix', '')}{getattr(r, 'new_fullname', '')}<br>
                <b>โทร:</b> {getattr(r, 'new_phone', '-')}<br>
                <b>อีเมล:</b> {getattr(r, 'new_email', '-')}<br>
                <b>ที่อยู่ใหม่:</b> {getattr(r, 'new_address', '-')}
            </td>
            <td class="py-4 px-4 text-xs text-gray-600 max-w-xs leading-relaxed">{getattr(r, 'reason', '-')}</td>
            <td class="py-4 px-4 text-xs text-gray-400">{getattr(r, 'created_at', '-')}</td>
            <td class="py-4 px-4">{status_badge}</td>
            <td class="py-4 px-4">{actions}</td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
        <h3 class="text-xl font-bold text-gray-800 mb-4">รายการคำร้องขอแก้ไขข้อมูลส่วนตัว</h3>
        <table class="w-full text-left min-w-[750px]">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase">
                <tr><th class="py-3.5 px-4">นักศึกษา</th><th class="py-3.5 px-4">ข้อมูลที่ขอเปลี่ยนแปลง</th><th class="py-3.5 px-4">เหตุผลในการขอแก้ไข</th><th class="py-3.5 px-4">วันที่ยื่น</th><th class="py-3.5 px-4">สถานะ</th><th class="py-3.5 px-4">การจัดการ</th></tr>
            </thead>
            <tbody class="divide-y divide-gray-100">{rows if rows else '<tr><td colspan="6" class="py-8 text-center text-gray-400">ไม่มีคำร้องขอแก้ไขข้อมูลในระบบ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/review/<int:req_id>')
def admin_review(req_id):
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-4">พิจารณาคำร้องเทียบโอน #{getattr(req, 'req_code', 'TR001')}</h3>
        <div class="grid md:grid-cols-2 gap-4 text-sm mb-4">
            <div><span class="text-gray-400 block text-xs">ผู้ยื่นคำร้อง</span><b>{req.user.fullname if req.user else '-'}</b> (รหัส: {req.user.member_id if req.user else '-'})</div>
            <div><span class="text-gray-400 block text-xs">หมวดหมู่</span><b>{getattr(req, 'category', 'ในระบบ')}</b></div>
            <div><span class="text-gray-400 block text-xs">รายวิชา</span><b>{getattr(req, 'course_name', '-')}</b> ({getattr(req, 'credits', 0)} หน่วยกิต)</div>
            <div><span class="text-gray-400 block text-xs">สถานะปัจจุบัน</span><b>{getattr(req, 'status', 'Pending')}</b></div>
        </div>

        <div class="flex justify-end space-x-3 mt-6 border-t pt-4">
            <a href="/admin/reject/{req.id}" class="px-5 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700">ไม่อนุมัติ</a>
            <a href="/admin/approve/{req.id}" class="px-5 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700">อนุมัติคำร้อง</a>
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