import os
import uuid
from datetime import datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'credit_bank_secret_key_2026'
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///credit_bank.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    date_submitted = db.Column(db.String(20), default="2026-08-13")
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
    created_at = db.Column(db.String(20), default="2026-08-13")
    user = db.relationship('User', backref=db.backref('edit_requests', lazy=True))

with app.app_context():
    try:
        # ลองเพิ่มคอลัมน์ member_id เข้าไปตรงๆ
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN member_id VARCHAR(20)"))
            conn.commit()
    except Exception:
        pass

    try:
        db.create_all()
        # ทดสอบ query ถ้าตารางพัง ให้สั่งสร้างใหม่ทั้งหมด
        User.query.filter_by(username='admin').first()
    except Exception:
        db.session.rollback()
        db.drop_all()
        db.create_all()

    # สร้างบัญชี Admin หลัก
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

# ==========================================
# Helper Functions
# ==========================================
def generate_member_id():
    last_user = User.query.filter(User.member_id.like('MB%')).order_by(User.id.desc()).first()
    if not last_user or not last_user.member_id:
        return "MB00001"
    try:
        last_num = int(last_user.member_id.replace("MB", ""))
        return f"MB{last_num + 1:05d}"
    except ValueError:
        return "MB00001"

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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
                <a href="/logout" class="block px-3 py-2 rounded-lg text-base font-medium text-red-600 hover:bg-red-50">ออกจากระบบ</a>
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
                    สะสมหน่วยกิตจากการเรียนรู้ในระบบ นอกระบบ และตามอัธยาศัย เพื่อใช้เทียบโอนและต่อยอดคุณวุฒิการศึกษาตามคณะและสาขาวิชา
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

    user = User.query.get(session['user_id'])
    
    if user.role in ['admin', 'superadmin']:
        pending_credits = CreditRequest.query.filter_by(status='Pending').count()
        pending_edits = ProfileEditRequest.query.filter_by(status='Pending').count()
        total_members = User.query.filter_by(role='student').count()
        total_admins = User.query.filter(User.role.in_(['admin', 'superadmin'])).count()

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

    user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
    approved_reqs = [r for r in user_requests if r.status == 'Approved']
    approved_credits = sum(r.credits for r in approved_reqs)
    pending_credits = sum(r.credits for r in user_requests if r.status == 'Pending')

    cat_counts = defaultdict(int)
    for r in approved_reqs: cat_counts[r.category] += r.credits
    
    doughnut_labels = ['ในระบบ', 'นอกระบบ', 'ตามอัธยาศัย']
    doughnut_data = [cat_counts.get('ในระบบ', 0), cat_counts.get('นอกระบบ', 0), cat_counts.get('ตามอัธยาศัย', 0)]

    months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    monthly_credits = [0] * 12
    for r in approved_reqs:
        if r.date_submitted and '-' in r.date_submitted:
            try:
                m = int(r.date_submitted.split('-')[1]) - 1
                if 0 <= m < 12: monthly_credits[m] += r.credits
            except ValueError: monthly_credits[7] += r.credits
        else: monthly_credits[7] += r.credits

    cumulative_credits, running = [], 0
    for c in monthly_credits:
        running += c
        cumulative_credits.append(running)

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

    <div class="grid md:grid-cols-3 gap-6 mb-8">
        <div class="md:col-span-2 bg-white p-5 rounded-2xl border shadow-sm">
            <h4 class="font-bold text-gray-700 text-sm mb-4"><i class="fa-solid fa-chart-line text-blue-600 mr-2"></i>หน่วยกิตสะสมรายเดือน</h4>
            <canvas id="lineChart" class="max-h-56"></canvas>
        </div>
        <div class="bg-white p-5 rounded-2xl border shadow-sm">
            <h4 class="font-bold text-gray-700 text-sm mb-4"><i class="fa-solid fa-chart-pie text-blue-600 mr-2"></i>สัดส่วนประเภทหน่วยกิต</h4>
            <canvas id="doughnutChart" class="max-h-56"></canvas>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <a href="/available_courses" class="bg-white p-6 rounded-2xl border shadow-sm hover:shadow-md hover:border-blue-300 transition block">
            <i class="fa-solid fa-book-open text-3xl text-blue-600 mb-3"></i>
            <h3 class="font-bold text-gray-800 mb-1">ค้นหารายวิชาเปิดเทียบโอน</h3>
            <p class="text-xs text-gray-500">เลือกดูรายวิชาที่เปิดรับเทียบโอนแยกตามคณะและสาขาวิชา</p>
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

    <script>
        new Chart(document.getElementById('lineChart').getContext('2d'), {{
            type: 'line',
            data: {{
                labels: {months},
                datasets: [{{
                    label: 'หน่วยกิตสะสม',
                    data: {cumulative_credits},
                    borderColor: '#2563eb',
                    backgroundColor: 'rgba(37, 99, 235, 0.1)',
                    fill: true,
                    tension: 0.3
                }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
        }});

        new Chart(document.getElementById('doughnutChart').getContext('2d'), {{
            type: 'doughnut',
            data: {{
                labels: {doughnut_labels},
                datasets: [{{
                    data: {doughnut_data},
                    backgroundColor: ['#2563eb', '#f59e0b', '#10b981']
                }}]
            }},
            options: {{ responsive: true }}
        }});
    </script>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['username'].strip()
        password_input = request.form['password'].strip()

        user = User.query.filter((User.username == login_input) | (User.id_card == login_input)).first()
        if user and check_password_hash(user.password, password_input):
            session['user_id'] = user.id
            session['fullname'] = user.fullname
            session['role'] = user.role
            session['member_id'] = user.member_id
            return redirect(url_for('home'))
            
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

@app.route('/admin/profile_requests')
def admin_profile_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    
    requests_list = ProfileEditRequest.query.order_by(ProfileEditRequest.id.desc()).all()
    rows = ""
    for r in requests_list:
        status_badge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-800">รอพิจารณา</span>' if r.status == 'Pending' else ('<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800">อนุมัติแล้ว</span>' if r.status == 'Approved' else '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        
        actions = f"""
        <div class="flex items-center gap-2">
            <a href="/admin/approve_profile/{r.id}" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-check"></i> อนุมัติ
            </a>
            <a href="/admin/reject_profile/{r.id}" class="bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition shadow-sm inline-flex items-center gap-1">
                <i class="fa-solid fa-xmark"></i> ไม่อนุมัติ
            </a>
        </div>
        """ if r.status == 'Pending' else f'<div class="text-xs text-gray-500 font-medium">ผู้อนุมัติ:<br><span class="text-blue-700 font-bold">{r.approved_by or "เจ้าหน้าที่"}</span></div>'

        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50 transition">
            <td class="py-4 px-4 font-medium text-gray-800">
                {r.user.fullname}<br>
                <span class="text-xs text-blue-600 font-semibold">(รหัส: {r.user.member_id})</span>
            </td>
            <td class="py-4 px-4 text-xs leading-relaxed">
                <b>ชื่อใหม่:</b> {r.new_prefix}{r.new_fullname}<br>
                <b>โทร:</b> {r.new_phone}<br>
                <b>อีเมล:</b> {r.new_email}<br>
                <b>ที่อยู่ใหม่:</b> {r.new_address or '-'}
            </td>
            <td class="py-4 px-4 text-xs text-gray-600 max-w-xs leading-relaxed">{r.reason}</td>
            <td class="py-4 px-4 text-xs text-gray-400">{r.created_at}</td>
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

@app.route('/admin/approve_profile/<int:req_id>')
def approve_profile(req_id):
    if session.get('role') in ['admin', 'superadmin']:
        admin_user = User.query.get(session['user_id'])
        req = ProfileEditRequest.query.get(req_id)
        if req and req.status == 'Pending':
            user = User.query.get(req.user_id)
            user.prefix = req.new_prefix
            user.fullname = req.new_fullname
            user.phone = req.new_phone
            user.email = req.new_email
            if req.new_address:
                user.address = req.new_address
            
            req.status = 'Approved'
            req.approved_by = admin_user.fullname if admin_user else "เจ้าหน้าที่"
            db.session.commit()
            flash('อนุมัติการแก้ไขข้อมูลส่วนตัวและอัปเดตข้อมูลผู้ใช้เรียบร้อยแล้ว', 'success')
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

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    all_courses = [
        {"code": "00-11-001", "name": "ภาษาไทยเพื่อการสื่อสาร", "campus": "เขตพื้นที่บางพระ (ชลบุรี)", "faculty": "คณะมนุษยศาสตร์และสังคมศาสตร์", "major": "หมวดวิชาศึกษาทั่วไป", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "มทร.ตะวันออก / ปวส.", "status": "มทร.ตะวันออก", "desc": "ทักษะการฟัง การพูด การอ่าน และการเขียนภาษาไทยเพื่อการสื่อสารในงานอาชีพ"},
        {"code": "00-12-002", "name": "ภาษาอังกฤษเพื่อการสื่อสารสากล", "campus": "เขตพื้นที่บางพระ (ชลบุรี)", "faculty": "คณะมนุษยศาสตร์และสังคมศาสตร์", "major": "หมวดวิชาศึกษาทั่วไป", "main_category": "หมวดวิชาศึกษาทั่วไป", "credits": 3, "source": "มทร.ตะวันออก / ปวส.", "status": "มทร.ตะวันออก", "desc": "การสื่อสารภาษาอังกฤษเบื้องต้น การนำเสนอผลงาน และไวยากรณ์ประยุกต์"},
        {"code": "15-03-006", "name": "การจัดการเศรษฐกิจชีวภาพ เศรษฐกิจหมุนเวียน และเศรษฐกิจสีเขียว", "campus": "เขตพื้นที่จักรพงษภูวนารถ (กรุงเทพฯ)", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.กรมอาชีวศึกษา", "status": "มทร.ตะวันออก", "desc": "โมเดลธุรกิจ BCG การอนุรักษ์พลังงาน และแนวคิดความยั่งยืนในองค์กร"},
        {"code": "15-03-007", "name": "เทคโนโลยีสารสนเทศในยุคดิจิทัล", "campus": "เขตพื้นที่จักรพงษภูวนารถ (กรุงเทพฯ)", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาเทคโนโลยีสารสนเทศ", "main_category": "หมวดวิชาเฉพาะ", "credits": 3, "source": "ปวส.", "status": "มทร.ตะวันออก", "desc": "การประยุกต์ใช้ซอฟต์แวร์สำนักงาน ก้อนเมฆ และเครื่องมือดิจิทัลเพื่องานบริหาร"},
        {"code": "MOOC-0008", "name": "การเงินส่วนบุคคล (Personal Finance Online)", "campus": "เขตพื้นที่จักรพงษภูวนารถ (กรุงเทพฯ)", "faculty": "คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ", "major": "สาขาวิชาการจัดการ", "main_category": "หมวดวิชาเลือกเสรี", "credits": 3, "source": "ThaiMOOC", "status": "ต้องตรวจสอบกับประกาศ", "desc": "การวางแผนการเงิน การออม การลงทุน สินเชื่อ และภาษีบุคคลธรรมดาผ่านระบบออนไลน์"}
    ]

    search_query = request.args.get('search', '').strip()
    filtered_courses = [c for c in all_courses if search_query.lower() in c['name'].lower() or search_query.lower() in c['code'].lower()] if search_query else all_courses

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
                <p class="text-xs text-blue-700 font-medium mb-1"><i class="fa-solid fa-location-dot mr-1"></i> {c['campus']}</p>
                <p class="text-xs text-gray-600 font-medium mb-1"><i class="fa-solid fa-building-columns mr-1"></i> {c['faculty']}</p>
                <p class="text-xs text-gray-500 mb-4 leading-relaxed">{c['desc']}</p>
            </div>
            <div class="border-t pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-gray-600 mb-4">
                    <span><i class="fa-solid fa-school mr-1 text-gray-400"></i> {c['source']}</span>
                    <span class="font-bold text-blue-900 text-sm">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['source'] + '&credits=' + str(c['credits']) + '&cat=' + c['main_category'] + '&fac=' + c['faculty'] + '&maj=' + c['major'] + '" class="block text-center w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 rounded-lg text-sm transition">เทียบโอนวิชานี้</a>' if session.get('role') not in ['admin', 'superadmin'] else ''}
            </div>
        </div>
        """

    content = f"""
    <div class="bg-gradient-to-r from-blue-900 to-indigo-800 text-white p-6 rounded-2xl shadow-sm mb-6 flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
            <h2 class="text-2xl font-bold">📚 รายวิชาเปิดรับเทียบโอน</h2>
            <p class="text-blue-100 text-xs mt-1">คู่มือและฐานข้อมูลรายวิชาแยกตามคณะ/สาขาวิชา และหมวดหมู่การเทียบโอน มทร.ตะวันออก</p>
        </div>
        <div class="bg-white/10 backdrop-blur px-5 py-3 rounded-xl border border-white/20 text-center min-w-[180px]">
            <span class="text-xs text-blue-200 block">ยอดเปิดรับทั้งหมด</span>
            <span class="text-2xl font-extrabold text-white">{len(all_courses)}</span> <span class="text-xs text-blue-200">วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-5 rounded-2xl border shadow-sm mb-6 space-y-4">
        <div class="flex flex-col md:flex-row gap-3">
            <div class="flex-1 relative">
                <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3.5 text-gray-400 text-sm"></i>
                <input type="text" name="search" value="{search_query}" placeholder="พิมพ์รหัสวิชา หรือ ชื่อวิชาที่ต้องการค้นหา..." class="w-full pl-10 pr-4 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 outline-none">
            </div>
            <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-2.5 rounded-xl text-sm transition flex items-center justify-center gap-2">
                <i class="fa-solid fa-search"></i> ค้นหารายวิชา
            </button>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-12 text-gray-400 bg-white rounded-2xl border">ไม่พบรายวิชาที่ตรงกับคำค้นหา</div>'}
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    step = request.args.get('step', '1')
    if request.method == 'POST':
        current_step = request.form.get('step')
        if current_step == '1':
            id_card_input = request.form.get('id_card', '').strip()
            if User.query.filter_by(id_card=id_card_input).first():
                flash('เลขบัตรประชาชนนี้เคยลงทะเบียนในระบบแล้ว', 'error')
                return redirect(url_for('register', step='1'))

            house_no = request.form.get('house_no', '')
            moo = request.form.get('moo', '')
            soi = request.form.get('soi', '')
            subdistrict = request.form.get('subdistrict', '')
            district = request.form.get('district', '')
            province = request.form.get('province', '')
            postal_code = request.form.get('postal_code', '')

            full_addr = format_address(house_no, moo, soi, subdistrict, district, province, postal_code)

            session['reg_prefix'] = request.form.get('prefix')
            session['reg_fullname'] = request.form.get('fullname')
            session['reg_id_card'] = id_card_input
            session['reg_dob'] = request.form.get('dob')
            session['reg_phone'] = request.form.get('phone')
            session['reg_email'] = request.form.get('email')
            session['reg_address'] = full_addr

            return redirect(url_for('register', step='2'))

        elif current_step == '2':
            username = request.form.get('username')
            if User.query.filter_by(username=username).first():
                flash('Username นี้ถูกใช้งานแล้ว กรุณาเลือกชื่อผู้ใช้ใหม่', 'error')
                return redirect(url_for('register', step='2'))

            file = request.files.get('id_card_img')
            if not file or file.filename == '':
                flash('กรุณาอัปโหลดรูปถ่ายบัตรประชาชนเพื่อยืนยันตัวตน', 'error')
                return redirect(url_for('register', step='2'))

            filename = secure_filename(f"verify_{username}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            new_member_id = generate_member_id()

            new_user = User(
                member_id=new_member_id,
                prefix=session.get('reg_prefix'),
                fullname=session.get('reg_fullname'),
                id_card=session.get('reg_id_card'),
                dob=session.get('reg_dob'),
                phone=session.get('reg_phone'),
                email=session.get('reg_email'),
                address=session.get('reg_address'),
                id_card_img=filename,
                username=username,
                password=generate_password_hash(request.form.get('password'))
            )
            db.session.add(new_user)
            db.session.commit()

            session['created_member_id'] = new_member_id
            return redirect(url_for('register', step='3'))

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h2 class="text-2xl font-bold text-center text-blue-900 mb-6">สมัครสมาชิกนักศึกษา</h2>
        <form method="POST" class="space-y-4">
            <input type="hidden" name="step" value="1">
            <div class="grid grid-cols-3 gap-3">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">คำนำหน้า</label>
                    <select name="prefix" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="นาย">นาย</option>
                        <option value="นาง">นาง</option>
                        <option value="นางสาว">นางสาว</option>
                    </select>
                </div>
                <div class="col-span-2">
                    <label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อ-นามสกุล</label>
                    <input type="text" name="fullname" required class="w-full border rounded-lg p-2.5 text-sm">
                </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">เลขบัตรประชาชน (13 หลัก)</label>
                    <input type="text" name="id_card" maxlength="13" required class="w-full border rounded-lg p-2.5 text-sm">
                </div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">วัน/เดือน/ปีเกิด</label><input type="date" name="dob" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">เบอร์โทรศัพท์</label><input type="tel" name="phone" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">อีเมล</label><input type="email" name="email" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ถัดไป: ยืนยันตัวตน</button>
        </form>
    </div>
    """ if step == '1' else f"""
    <div class="max-w-xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h2 class="text-2xl font-bold text-center text-blue-900 mb-6">ยืนยันตัวตน & ตั้งรหัสผ่าน</h2>
        <form method="POST" enctype="multipart/form-data" class="space-y-4">
            <input type="hidden" name="step" value="2">
            <div>
                <label class="block text-xs font-semibold text-gray-700 mb-1">อัปโหลดรูปถ่ายบัตรประชาชนจริง *</label>
                <input type="file" name="id_card_img" accept="image/*" required class="w-full border rounded-lg p-2 text-sm bg-gray-50">
            </div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อผู้ใช้งาน (Username)</label><input type="text" name="username" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">รหัสผ่าน (Password)</label><input type="password" name="password" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ยืนยันการสมัคร</button>
        </form>
    </div>
    """ if step == '2' else f"""
    <div class="max-w-md mx-auto bg-white p-8 rounded-2xl border shadow-sm text-center">
        <h2 class="text-2xl font-bold text-gray-800 mb-1">สมัครสมาชิกเสร็จสิ้น!</h2>
        <p class="text-sm font-semibold text-blue-600 mb-4">รหัสสมาชิกของคุณคือ: {session.get('created_member_id', '-')}</p>
        <a href="/login" class="block w-full bg-blue-600 text-white font-medium py-3 rounded-lg hover:bg-blue-700">เข้าสู่ระบบทันที</a>
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
        file = request.files.get('doc_img')
        if not file or file.filename == '':
            flash('กรุณาแนบไฟล์เอกสารประกอบด้วยครับ', 'error')
            return redirect(request.url)

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        unique_filename = f"doc_{session['user_id']}_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))

        req = CreditRequest(
            user_id=session['user_id'], 
            course_name=request.form['course_name'], 
            institution=request.form['institution'], 
            credits=int(request.form['credits']),
            category=request.form.get('category', 'ในระบบ'),
            faculty=request.form.get('faculty'),
            major=request.form.get('major'),
            doc_img=unique_filename
        )
        db.session.add(req)
        db.session.commit()
        flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    content = """
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-6">ยื่นคำขอเทียบโอนหน่วยกิต</h3>
        <form method="POST" enctype="multipart/form-data" class="space-y-4">
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อหลักสูตร / รายวิชา</label><input type="text" name="course_name" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">สถาบัน / แหล่งเรียนรู้</label><input type="text" name="institution" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">จำนวนหน่วยกิต</label><input type="number" name="credits" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">หมวดหมู่การเรียนรู้</label>
                    <select name="category" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="ในระบบ">ในระบบ</option>
                        <option value="นอกระบบ">นอกระบบ</option>
                        <option value="ตามอัธยาศัย">ตามอัธยาศัย</option>
                    </select>
                </div>
            </div>
            <div>
                <label class="block text-xs font-semibold text-gray-700 mb-1">แนบเอกสารประกอบ *</label>
                <input type="file" name="doc_img" accept="image/*,.pdf" required class="w-full border rounded-lg p-2 text-sm bg-gray-50">
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ส่งคำร้องขอเทียบโอน</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).all()
    rows = ""
    for r in user_requests:
        badge = '<span class="px-3 py-1 rounded-full text-xs font-semibold bg-yellow-100 text-yellow-800">รอการพิจารณา</span>' if r.status == 'Pending' else ('<span class="px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">อนุมัติแล้ว</span>' if r.status == 'Approved' else '<span class="px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        doc_link = f'<a href="{url_for("static", filename="uploads/" + r.doc_img)}" target="_blank" class="text-blue-600 hover:underline text-xs"><i class="fa-solid fa-file"></i> เอกสาร</a>' if r.doc_img else '-'

        rows += f"""
        <tr class="border-b text-sm">
            <td class="py-3 px-4 font-mono font-bold text-gray-500">{r.req_code}</td>
            <td class="py-3 px-4 font-medium text-gray-800">{r.course_name}</td>
            <td class="py-3 px-4 text-gray-600">{r.institution}</td>
            <td class="py-3 px-4 font-bold text-blue-900">{r.credits}</td>
            <td class="py-3 px-4">{doc_link}</td>
            <td class="py-3 px-4 text-xs text-gray-500">{r.approved_by or "-"}</td>
            <td class="py-3 px-4">{badge}</td>
        </tr>
        """
    content = f"""
    <div class="bg-white p-6 rounded-2xl border shadow-sm overflow-x-auto">
        <h3 class="text-xl font-bold text-gray-800 mb-4">ประวัติคำร้องเทียบโอน</h3>
        <table class="w-full text-left min-w-[700px]">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase"><tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">สถาบัน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">เอกสาร</th><th class="py-3 px-4">เจ้าหน้าที่ผู้ตรวจ</th><th class="py-3 px-4">สถานะ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="7" class="py-6 text-center text-gray-400">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/credits')
def credits():
    if 'user_id' not in session: return redirect(url_for('login'))
    approved_requests = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
    total_approved = sum(r.credits for r in approved_requests)
    
    rows = ""
    for r in approved_requests:
        rows += f"""
        <tr class="border-b text-sm">
            <td class="py-3.5 px-4 font-medium text-gray-800">{r.course_name}</td>
            <td class="py-3.5 px-4 text-gray-600">{r.institution}</td>
            <td class="py-3.5 px-4 font-bold text-blue-900">{r.credits} หน่วยกิต</td>
            <td class="py-3.5 px-4 text-xs text-gray-500">{r.approved_by or "เจ้าหน้าที่"}</td>
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

@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
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

@app.route('/admin/requests')
def admin_requests():
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    all_requests = CreditRequest.query.order_by(CreditRequest.id.desc()).all()
    rows = ""
    for r in all_requests:
        status_badge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-800">รอพิจารณา</span>' if r.status == 'Pending' else ('<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800">อนุมัติ</span>' if r.status == 'Approved' else '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">ไม่อนุมัติ</span>')
        
        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50">
            <td class="py-3 px-4 font-mono font-bold text-blue-900">{r.req_code}</td>
            <td class="py-3 px-4 font-medium">{r.user.fullname}<br><span class="text-xs text-blue-600">({r.user.member_id})</span></td>
            <td class="py-3 px-4 text-gray-600">{r.course_name}</td>
            <td class="py-3 px-4 text-gray-500">{r.date_submitted}</td>
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

@app.route('/admin/review/<int:req_id>')
def admin_review(req_id):
    if session.get('role') not in ['admin', 'superadmin']: return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    doc_preview = f"""
    <div class="mt-4 p-4 bg-gray-50 border rounded-xl">
        <p class="text-xs font-semibold text-gray-600 mb-2"><i class="fa-solid fa-paperclip mr-1"></i> เอกสารหลักฐานประกอบคำร้อง:</p>
        <a href="{url_for('static', filename='uploads/' + req.doc_img)}" target="_blank" class="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-lg text-xs font-bold border border-blue-200 hover:bg-blue-100 transition">
            <i class="fa-solid fa-file-pdf text-base"></i> เปิดดูไฟล์หลักฐาน
        </a>
    </div>
    """ if req.doc_img else ''

    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-4">พิจารณาคำร้องเทียบโอน #{req.req_code}</h3>
        <div class="grid md:grid-cols-2 gap-4 text-sm mb-4">
            <div><span class="text-gray-400 block text-xs">ผู้ยื่นคำร้อง</span><b>{req.user.fullname}</b> (รหัส: {req.user.member_id})</div>
            <div><span class="text-gray-400 block text-xs">หมวดหมู่</span><b>{req.category}</b></div>
            <div><span class="text-gray-400 block text-xs">รายวิชา</span><b>{req.course_name}</b> ({req.credits} หน่วยกิต)</div>
            <div><span class="text-gray-400 block text-xs">สถานะปัจจุบัน</span><b>{req.status}</b></div>
        </div>
        
        {doc_preview}

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)