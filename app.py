import os
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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # จำกัดขนาดไฟล์อัปโหลดไม่เกิน 16MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ==========================================
# Database Models
# ==========================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), default="660123456789")
    prefix = db.Column(db.String(20), default="นาย")
    fullname = db.Column(db.String(100), nullable=False)
    id_card = db.Column(db.String(20), nullable=True)
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
    date_submitted = db.Column(db.String(20), default="2026-08-11")
    doc_img = db.Column(db.String(200), nullable=True)  # ฟิลด์เก็บชื่อไฟล์รูปเอกสารประกอบ
    status = db.Column(db.String(20), default='Pending')
    user = db.relationship('User', backref=db.backref('credits_list', lazy=True))

# อัปเดตโครงสร้างตาราง DB อัตโนมัติกรณีเพิ่มคอลัมน์ใหม่
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE user ADD COLUMN prefix VARCHAR(20) DEFAULT 'นาย'"))
            conn.commit()
    except Exception:
        pass

    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE credit_request ADD COLUMN doc_img VARCHAR(200)"))
            conn.commit()
    except Exception:
        pass

    if not User.query.filter_by(username='admin').first():
        admin = User(
            prefix='นาย',
            fullname='สมชาย ใจดี (เจ้าหน้าที่)', 
            username='admin', 
            password=generate_password_hash('admin123'), 
            role='admin', 
            student_id="ADM-001",
            phone="081-234-5678",
            email="admin@creditbank.ac.th"
        )
        db.session.add(admin)
        db.session.commit()

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
    <style>body { font-family: 'Sarabun', sans-serif; }</style>
</head>
<body class="bg-gray-50 flex flex-col min-h-screen text-gray-800">

    <!-- Navigation Bar -->
    <nav class="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <!-- โลโก้ -->
                <div class="flex items-center">
                    <a href="/" class="flex items-center gap-2">
                        <div class="w-9 h-9 bg-blue-600 text-white rounded-lg flex items-center justify-center font-bold text-lg shadow-sm">CB</div>
                        <div class="flex flex-col">
                            <span class="font-bold text-gray-900 text-base leading-tight">Credit Bank</span>
                            <span class="text-[10px] text-gray-500 font-medium">มทร.ตะวันออก</span>
                        </div>
                    </a>
                </div>

                <!-- เมนู Desktop -->
                <div class="hidden md:flex items-center space-x-1 lg:space-x-4 text-sm font-medium">
                    <a href="/" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">หน้าแรก</a>
                    <a href="/available_courses" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">รายวิชาเปิดรับเทียบโอน</a>
                    <a href="/submit_credit" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">ยื่นคำขอเทียบโอน</a>
                    <a href="/history" class="px-3 py-2 rounded-lg text-gray-700 hover:text-blue-600 hover:bg-gray-50 transition">ประวัติคำขอ</a>
                </div>

                <!-- ปุ่ม Hamburger มือถือ -->
                <div class="flex items-center md:hidden">
                    <button id="mobile-menu-btn" type="button" class="p-2 rounded-lg text-gray-600 hover:text-gray-900 hover:bg-gray-100 focus:outline-none">
                        <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>

        <!-- เมนู Mobile Dropdown -->
        <div id="mobile-menu" class="hidden md:hidden border-t border-gray-100 bg-white px-4 pt-2 pb-4 space-y-1 shadow-lg">
            <a href="/" class="block px-3 py-2.5 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-600">หน้าแรก</a>
            <a href="/available_courses" class="block px-3 py-2.5 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-600">รายวิชาเปิดรับเทียบโอน</a>
            <a href="/submit_credit" class="block px-3 py-2.5 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-600">ยื่นคำขอเทียบโอน</a>
            <a href="/history" class="block px-3 py-2.5 rounded-lg text-base font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-600">ประวัติคำขอ</a>
        </div>
    </nav>

    <!-- ส่วนที่จะแสดงเนื้อหาของแต่ละหน้า (ต้องใช้ {{ content | safe }}) -->
    <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {{ content | safe }}
    </main>

    <!-- Footer -->
    <footer class="bg-slate-900 text-slate-300 mt-auto border-t border-slate-800">
        <div class="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 pb-6 border-b border-slate-800">
                <div class="md:col-span-2 space-y-2">
                    <span class="inline-block text-[11px] font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        Information System Project
                    </span>
                    <h4 class="text-sm sm:text-base font-bold text-white leading-relaxed">
                        โปรเจคพัฒนาระบบสารสนเทศสำหรับเก็บสะสมหน่วยกิต และการเทียบโอน เพื่อการเรียนรู้ตลอดชีวิต (ธนาคารหน่วยกิต)
                    </h4>
                    <p class="text-xs text-slate-400">
                        ของนักศึกษา มหาวิทยาลัยเทคโนโลยีราชมงคลตะวันออก สาขาระบบสารสนเทศ
                    </p>
                </div>
                <div class="space-y-2">
                    <h5 class="text-xs font-semibold text-slate-200 uppercase tracking-wider">ลิงก์ด่วน</h5>
                    <ul class="grid grid-cols-2 gap-2 text-xs md:block md:space-y-2">
                        <li><a href="/" class="hover:text-blue-400 transition-colors">หน้าแรก</a></li>
                        <li><a href="/available_courses" class="hover:text-blue-400 transition-colors">รายวิชาที่เปิดเทียบโอน</a></li>
                        <li><a href="/submit_credit" class="hover:text-blue-400 transition-colors">ยื่นคำขอเทียบโอน</a></li>
                        <li><a href="/history" class="hover:text-blue-400 transition-colors">ประวัติคำขอ</a></li>
                    </ul>
                </div>
            </div>
            <div class="pt-4 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500 gap-2 text-center sm:text-left">
                <p>© 2026 Credit Bank System. Rajamangala University of Technology Tawan-ok.</p>
                <p>สาขาวิชาระบบสารสนเทศ คณะบริหารธุรกิจและเทคโนโลยีสารสนเทศ</p>
            </div>
        </div>
    </footer>

    <script>
        const menuBtn = document.getElementById('mobile-menu-btn');
        const mobileMenu = document.getElementById('mobile-menu');
        menuBtn.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });
    </script>
</body>
</html>
"""

# ==========================================
# Routes & Controllers
# ==========================================
@app.route('/')
def home():
    if session.get('user_id'): return redirect(url_for('dashboard'))
    content = """
    <div class="max-w-6xl mx-auto py-12 grid md:grid-cols-2 gap-12 items-center">
        <div>
            <h1 class="text-4xl font-extrabold text-blue-950 leading-tight mb-4">
                ระบบธนาคารหน่วยกิต<br><span class="text-blue-600">เพื่อการเรียนรู้ตลอดชีวิต</span>
            </h1>
            <p class="text-gray-600 mb-8 leading-relaxed">
                สะสมหน่วยกิตจากการเรียนรู้ในระบบ นอกระบบ และตามอัธยาศัย เพื่อใช้เทียบโอนและต่อยอดคุณวุฒิการศึกษา
            </p>
            <div class="space-x-4">
                <a href="/register" class="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700">สมัครสมาชิก</a>
                <a href="/login" class="px-6 py-3 bg-white text-blue-900 border font-semibold rounded-lg hover:bg-gray-50">เข้าสู่ระบบ</a>
            </div>
        </div>
        <div class="bg-blue-50 p-8 rounded-3xl border border-blue-100 text-center shadow-inner">
            <i class="fa-solid fa-graduation-cap text-9xl text-blue-600 my-8"></i>
            <h3 class="text-xl font-bold text-blue-900">สะสมความรู้ ปลดล็อกโอกาส</h3>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))

    if session.get('role') == 'admin':
        all_requests = CreditRequest.query.all()
        pending_reqs = [r for r in all_requests if r.status == 'Pending']
        approved_reqs = [r for r in all_requests if r.status == 'Approved']
        total_students = User.query.filter_by(role='student').count()

        rows = ""
        for r in pending_reqs:
            doc_badge = f'<span class="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded"><i class="fa-solid fa-paperclip"></i> มีเอกสาร</span>' if r.doc_img else '<span class="text-xs text-gray-400">ไม่มี</span>'
            rows += f"""
            <tr class="border-b text-sm hover:bg-gray-50">
                <td class="py-3 px-4 font-mono font-bold text-blue-900">{r.req_code}</td>
                <td class="py-3 px-4 font-medium">{r.user.fullname}</td>
                <td class="py-3 px-4 text-gray-600">{r.course_name}</td>
                <td class="py-3 px-4">{doc_badge}</td>
                <td class="py-3 px-4 text-gray-500">{r.date_submitted}</td>
                <td class="py-3 px-4">
                    <a href="/admin/review/{r.id}" class="bg-blue-600 text-white px-3 py-1.5 rounded text-xs font-semibold hover:bg-blue-700">พิจารณาคำร้อง</a>
                </td>
            </tr>
            """

        content = f"""
        <div class="mb-6">
            <h2 class="text-2xl font-bold text-gray-800">แผงควบคุม (เจ้าหน้าที่)</h2>
            <p class="text-gray-500 text-sm">จัดการคำร้องเทียบโอนหน่วยกิตและตรวจสอบข้อมูลนักศึกษา</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-white p-5 rounded-xl border shadow-sm">
                <p class="text-xs text-gray-500 mb-1">นักศึกษาทั้งหมด</p>
                <h3 class="text-2xl font-bold text-blue-900">{total_students} <span class="text-xs text-gray-400 font-normal">คน</span></h3>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm">
                <p class="text-xs text-gray-500 mb-1">คำร้องใหม่ (รอการพิจารณา)</p>
                <h3 class="text-2xl font-bold text-yellow-600">{len(pending_reqs)} <span class="text-xs text-gray-400 font-normal">รายการ</span></h3>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm">
                <p class="text-xs text-gray-500 mb-1">อนุมัติแล้ว</p>
                <h3 class="text-2xl font-bold text-green-600">{len(approved_reqs)} <span class="text-xs text-gray-400 font-normal">รายการ</span></h3>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm">
                <p class="text-xs text-gray-500 mb-1">หน่วยกิตสะสมรวม</p>
                <h3 class="text-2xl font-bold text-gray-800">{sum(r.credits for r in approved_reqs)} <span class="text-xs text-gray-400 font-normal">หน่วยกิต</span></h3>
            </div>
        </div>

        <div class="bg-white p-6 rounded-xl border shadow-sm">
            <h4 class="font-bold text-gray-800 mb-4">คำร้องที่ต้องการการพิจารณา</h4>
            <table class="w-full text-left">
                <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase">
                    <tr><th class="py-2 px-4">รหัสคำร้อง</th><th class="py-2 px-4">ชื่อนักศึกษา</th><th class="py-2 px-4">รายการขอเทียบโอน</th><th class="py-2 px-4">หลักฐาน</th><th class="py-2 px-4">วันที่ยื่น</th><th class="py-2 px-4">การจัดการ</th></tr>
                </thead>
                <tbody>{rows if rows else '<tr><td colspan="6" class="py-6 text-center text-gray-400 text-sm">ไม่มีคำร้องค้างพิจารณา</td></tr>'}</tbody>
            </table>
        </div>
        """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    else:
        user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).all()
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
            <h2 class="text-2xl font-bold text-gray-800">สวัสดีครับ, {session.get('fullname')}</h2>
            <p class="text-gray-500 text-sm">รหัสนักศึกษา : {session.get('student_id', '660123456789')}</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-white p-5 rounded-xl border shadow-sm flex items-center justify-between">
                <div>
                    <p class="text-xs text-gray-500 font-medium mb-1">หน่วยกิตสะสมทั้งหมด</p>
                    <h3 class="text-2xl font-bold text-blue-900">{approved_credits + pending_credits} <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
                </div>
                <div class="w-10 h-10 bg-purple-50 text-purple-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-clock"></i></div>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm flex items-center justify-between">
                <div>
                    <p class="text-xs text-gray-500 font-medium mb-1">รอการอนุมัติ</p>
                    <h3 class="text-2xl font-bold text-yellow-600">{pending_credits} <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
                </div>
                <div class="w-10 h-10 bg-yellow-50 text-yellow-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-file-lines"></i></div>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm flex items-center justify-between">
                <div>
                    <p class="text-xs text-gray-500 font-medium mb-1">อนุมัติแล้ว</p>
                    <h3 class="text-2xl font-bold text-green-600">{approved_credits} <span class="text-xs font-normal text-gray-400">หน่วยกิต</span></h3>
                </div>
                <div class="w-10 h-10 bg-green-50 text-green-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-basket-shopping"></i></div>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm flex items-center justify-between">
                <div>
                    <p class="text-xs text-gray-500 font-medium mb-1">คำร้องทั้งหมด</p>
                    <h3 class="text-2xl font-bold text-gray-800">{len(user_requests)} <span class="text-xs font-normal text-gray-400">รายการ</span></h3>
                </div>
                <div class="w-10 h-10 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center"><i class="fa-solid fa-list-check"></i></div>
            </div>
        </div>

        <div class="grid md:grid-cols-3 gap-6 mb-8">
            <div class="md:col-span-2 bg-white p-5 rounded-xl border shadow-sm">
                <h4 class="font-bold text-gray-700 text-sm mb-4">หน่วยกิตสะสมรายเดือน</h4>
                <canvas id="lineChart" class="max-h-56"></canvas>
            </div>
            <div class="bg-white p-5 rounded-xl border shadow-sm">
                <h4 class="font-bold text-gray-700 text-sm mb-4">สัดส่วนหน่วยกิต</h4>
                <canvas id="doughnutChart" class="max-h-56"></canvas>
            </div>
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

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        if 'profile_img' in request.files:
            file = request.files['profile_img']
            if file and file.filename != '':
                filename = secure_filename(f"user_{user.id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                user.profile_img = filename
                db.session.commit()
                flash('อัปเดตรูปโปรไฟล์เรียบร้อยแล้ว', 'success')
                return redirect(url_for('profile'))

    if user and getattr(user, 'profile_img', None) and user.profile_img != 'default_profile.png':
        img_html = f'<img src="{url_for("static", filename="uploads/" + user.profile_img)}" class="w-full h-full object-cover">'
    else:
        img_html = '<i class="fa-solid fa-user text-5xl text-gray-400"></i>'

    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <div class="flex flex-col md:flex-row items-center md:items-start space-y-6 md:space-y-0 md:space-x-8 pb-8 border-b">
            <div class="text-center">
                <div class="w-32 h-32 rounded-full overflow-hidden border-4 border-blue-100 shadow-md mx-auto mb-4 bg-gray-100 flex items-center justify-center">
                    {img_html}
                </div>
                <form method="POST" enctype="multipart/form-data" class="space-y-2">
                    <label class="cursor-pointer bg-blue-50 text-blue-700 hover:bg-blue-100 px-3 py-1.5 rounded-lg text-xs font-semibold inline-block transition">
                        <i class="fa-solid fa-camera mr-1"></i> เปลี่ยนรูปโปรไฟล์ (ไม่บังคับ)
                        <input type="file" name="profile_img" class="hidden" accept="image/*" onchange="this.form.submit()">
                    </label>
                </form>
            </div>
            
            <div class="flex-1">
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="text-2xl font-bold text-gray-800">{user.prefix or ''} {user.fullname}</h3>
                        <p class="text-sm text-gray-500">รหัสนักศึกษา: {user.student_id or '-'}</p>
                    </div>
                    <span class="bg-blue-100 text-blue-800 text-xs px-3 py-1 rounded-full font-semibold">{user.role.upper()}</span>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6 bg-gray-50 p-4 rounded-xl text-sm">
                    <div><span class="text-gray-400 block text-xs">เลขบัตรประชาชน</span> <span class="font-semibold text-gray-700">{user.id_card or '-'}</span></div>
                    <div><span class="text-gray-400 block text-xs">วัน/เดือน/ปีเกิด</span> <span class="font-semibold text-gray-700">{user.dob or '-'}</span></div>
                    <div><span class="text-gray-400 block text-xs">เบอร์โทรศัพท์</span> <span class="font-semibold text-gray-700">{user.phone or '-'}</span></div>
                    <div><span class="text-gray-400 block text-xs">อีเมล</span> <span class="font-semibold text-gray-700">{user.email or '-'}</span></div>
                    <div class="md:col-span-2"><span class="text-gray-400 block text-xs">ที่อยู่ปัจจุบัน</span> <span class="font-semibold text-gray-700">{user.address or '-'}</span></div>
                </div>
            </div>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

import uuid # เพิ่มการนำเข้า uuid ด้านบนสุดของไฟล์

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: return redirect(url_for('login'))
    default_course = request.args.get('course', '')
    default_inst = request.args.get('inst', '')
    default_credits = request.args.get('credits', '')
    default_cat = request.args.get('cat', 'ในระบบ')

    if request.method == 'POST':
        file = request.files.get('doc_img')
        if not file or file.filename == '':
            flash('กรุณาแนบรูปภาพหรือไฟล์ PDF เอกสารประกอบการพิจารณาด้วยครับ', 'error')
            return redirect(request.url)

        # ตรวจสอบนามสกุลไฟล์
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ['png', 'jpg', 'jpeg', 'pdf']:
            flash('รองรับเฉพาะไฟล์รูปภาพ (PNG, JPG) และ PDF เท่านั้น', 'error')
            return redirect(request.url)

        # สุ่มชื่อไฟล์ใหม่ด้วย UUID เพื่อป้องกันชื่อซ้ำ
        unique_filename = f"doc_{session['user_id']}_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))

        req = CreditRequest(
            user_id=session['user_id'], 
            course_name=request.form['course_name'], 
            institution=request.form['institution'], 
            credits=int(request.form['credits']),
            category=request.form.get('category', 'ในระบบ'),
            doc_img=unique_filename
        )
        db.session.add(req)
        db.session.commit()
        flash('ยื่นคำขอเทียบโอนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('history'))

    content = f"""
    <div class="max-w-2xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-6">ส่งคำร้องขอเทียบโอนหน่วยกิต</h3>
        <form method="POST" enctype="multipart/form-data" class="space-y-4">
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อหลักสูตร / รายวิชา</label><input type="text" name="course_name" value="{default_course}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">สถาบัน / แพลตฟอร์ม</label><input type="text" name="institution" value="{default_inst}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div class="grid grid-cols-2 gap-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">จำนวนหน่วยกิต</label><input type="number" name="credits" value="{default_credits}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">หมวดหมู่การเรียนรู้</label>
                    <select name="category" class="w-full border rounded-lg p-2.5 text-sm">
                        <option value="ในระบบ" {'selected' if default_cat == 'ในระบบ' else ''}>ในระบบ</option>
                        <option value="นอกระบบ" {'selected' if default_cat == 'นอกระบบ' else ''}>นอกระบบ</option>
                        <option value="ตามอัธยาศัย" {'selected' if default_cat == 'ตามอัธยาศัย' else ''}>ตามอัธยาศัย</option>
                    </select>
                </div>
            </div>

            <div class="border-t pt-4 mt-2">
                <label class="block text-xs font-semibold text-gray-700 mb-1">
                    แนบเอกสารประกอบ <span class="text-red-500">* (JPG, PNG หรือ PDF)</span>
                </label>
                <p class="text-xs text-gray-400 mb-2">กรุณาแนบ Transcript, เกียรติบัตร หรือ คำอธิบายรายวิชา</p>
                <input type="file" name="doc_img" accept="image/*,.pdf" required class="w-full border rounded-lg p-2 text-sm bg-gray-50">
            </div>

            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700 transition">ส่งคำร้องขอเทียบโอน</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/review/<int:req_id>')
def admin_review(req_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    req = CreditRequest.query.get_or_404(req_id)

    if req.doc_img:
        doc_preview = f"""
        <div class="mt-4 p-4 bg-gray-50 border rounded-xl">
            <p class="text-xs font-semibold text-gray-600 mb-2"><i class="fa-solid fa-paperclip mr-1"></i> เอกสารหลักฐานประกอบคำร้อง:</p>
            <a href="{url_for('static', filename='uploads/' + req.doc_img)}" target="_blank">
                <img src="{url_for('static', filename='uploads/' + req.doc_img)}" class="max-h-80 rounded-lg border shadow-sm hover:opacity-90 transition">
            </a>
            <p class="text-xs text-gray-400 mt-1">* คลิกที่รูปเพื่อดูภาพขนาดเต็ม</p>
        </div>
        """
    else:
        doc_preview = """
        <div class="mt-4 p-4 bg-gray-50 border rounded-xl text-xs text-gray-400 italic">
            ไม่มีการแนบรูปภาพเอกสารประกอบ
        </div>
        """

    content = f"""
    <div class="max-w-4xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-4">พิจารณาคำร้องเทียบโอน #{req.req_code}</h3>
        <div class="grid md:grid-cols-2 gap-4 text-sm mb-4">
            <div><span class="text-gray-400 block text-xs">ผู้ยื่นคำร้อง</span><b>{req.user.fullname}</b> ({req.user.student_id})</div>
            <div><span class="text-gray-400 block text-xs">หมวดหมู่</span><b>{req.category}</b></div>
            <div><span class="text-gray-400 block text-xs">รายวิชา</span><b>{req.course_name}</b> ({req.credits} หน่วยกิต)</div>
            <div><span class="text-gray-400 block text-xs">สถาบัน</span><b>{req.institution}</b></div>
        </div>
        
        {doc_preview}

        <div class="flex justify-end space-x-3 mt-6 border-t pt-4">
            <a href="/admin/reject/{req.id}" class="px-5 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700">ไม่อนุมัติ</a>
            <a href="/admin/approve/{req.id}" class="px-5 py-2 bg-green-600 text-white rounded-lg text-sm font-semibold hover:bg-green-700">อนุมัติคำร้อง</a>
        </div>
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
        doc_link = f'<a href="{url_for("static", filename="uploads/" + r.doc_img)}" target="_blank" class="text-blue-600 hover:underline text-xs"><i class="fa-solid fa-image"></i> ดูรูป</a>' if r.doc_img else '<span class="text-gray-300 text-xs">-</span>'
        rows += f"""
        <tr class="border-b text-sm"><td class="py-3 px-4 font-mono font-bold text-gray-500">{r.req_code}</td><td class="py-3 px-4 font-medium text-gray-800">{r.course_name}</td><td class="py-3 px-4 text-gray-600">{r.institution}</td><td class="py-3 px-4 font-bold text-blue-900">{r.credits}</td><td class="py-3 px-4">{doc_link}</td><td class="py-3 px-4 text-gray-500 text-xs">{r.date_submitted}</td><td class="py-3 px-4">{badge}</td></tr>
        """
    content = f"""
    <div class="bg-white p-6 rounded-2xl border shadow-sm">
        <h3 class="text-xl font-bold text-gray-800 mb-4">ประวัติคำร้องเทียบโอน</h3>
        <table class="w-full text-left">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase"><tr><th class="py-3 px-4">รหัสคำร้อง</th><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">สถาบัน</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">เอกสาร</th><th class="py-3 px-4">วันที่ยื่น</th><th class="py-3 px-4">สถานะ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="7" class="py-6 text-center text-gray-400">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/available_courses')
def available_courses():
    if 'user_id' not in session: return redirect(url_for('login'))
    courses = [
        {"code": "CS101", "name": "การเขียนโปรแกรมคอมพิวเตอร์เบื้องต้น", "category": "ในระบบ", "institution": "มหาวิทยาลัยเปิด", "credits": 3, "desc": "พื้นฐานแนวคิดการเขียนโปรแกรม โครงสร้างข้อมูล และอัลกอริทึม"},
        {"code": "DB201", "name": "ระบบจัดการฐานข้อมูล (Database Systems)", "category": "ในระบบ", "institution": "สถาบันเทคโนโลยี", "credits": 3, "desc": "การออกแบบฐานข้อมูลเชิงสัมพันธ์ SQL และการบริหารจัดการข้อมูล"},
        {"code": "MOOC01", "name": "การพัฒนาเว็บแอปพลิเคชันด้วย Python & Flask", "category": "นอกระบบ", "institution": "ThaiMOOC", "credits": 3, "desc": "เรียนรู้การพัฒนา Web API และ Dashboard ด้วย Python"},
        {"code": "MOOC02", "name": "Data Analytics & Data Science สำหรับผู้เริ่มต้น", "category": "นอกระบบ", "institution": "Coursera / edX", "credits": 2, "desc": "ทักษะการวิเคราะห์ข้อมูลเบื้องต้น การใช้วิธีทางสถิติและ Visualization"},
        {"code": "SKILL01", "name": "การบริหารจัดการโครงการยุคดิจิทัล (Agile/Scrum)", "category": "ตามอัธยาศัย", "institution": "สถาบันพัฒนาทักษะดิจิทัล", "credits": 2, "desc": "การบริหารโครงการซอฟต์แวร์และการทำงานร่วมกันด้วยกระบวนการ Agile"},
        {"code": "SKILL02", "name": "ภาษาอังกฤษเพื่อการสื่อสารในองค์กร", "category": "ตามอัธยาศัย", "institution": "ศูนย์ภาษาและอาเซียนศึกษา", "credits": 3, "desc": "ทักษะการสื่อสาร การเขียนอีเมล และการนำเสนอผลงานภาษาอังกฤษ"},
    ]
    cards = ""
    for c in courses:
        cat_badge = '<span class="bg-blue-100 text-blue-800 text-xs px-2.5 py-1 rounded-full font-semibold">ในระบบ</span>' if c['category'] == 'ในระบบ' else ('<span class="bg-amber-100 text-amber-800 text-xs px-2.5 py-1 rounded-full font-semibold">นอกระบบ</span>' if c['category'] == 'นอกระบบ' else '<span class="bg-emerald-100 text-emerald-800 text-xs px-2.5 py-1 rounded-full font-semibold">ตามอัธยาศัย</span>')
        cards += f"""
        <div class="bg-white p-6 rounded-2xl border shadow-sm flex flex-col justify-between hover:shadow-md transition">
            <div>
                <div class="flex justify-between items-start mb-3"><span class="font-mono text-xs text-gray-400 font-bold">{c['code']}</span>{cat_badge}</div>
                <h3 class="text-lg font-bold text-gray-800 mb-2">{c['name']}</h3>
                <p class="text-xs text-gray-500 mb-4 leading-relaxed">{c['desc']}</p>
            </div>
            <div class="border-t pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-gray-600 mb-4">
                    <span><i class="fa-solid fa-building-columns mr-1 text-gray-400"></i> {c['institution']}</span>
                    <span class="font-bold text-blue-900 text-sm">{c['credits']} หน่วยกิต</span>
                </div>
                {'<a href="/submit_credit?course=' + c['name'] + '&inst=' + c['institution'] + '&credits=' + str(c['credits']) + '&cat=' + c['category'] + '" class="block text-center w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 rounded-lg text-sm transition">เทียบโอนวิชานี้</a>' if session.get('role') != 'admin' else ''}
            </div>
        </div>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-bold text-gray-800">📚 หลักสูตรที่เปิดรับเทียบโอน</h2></div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">{cards}</div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/credits')
def credits():
    if 'user_id' not in session: return redirect(url_for('login'))
    approved_requests = CreditRequest.query.filter_by(user_id=session['user_id'], status='Approved').all()
    total_approved = sum(r.credits for r in approved_requests)
    target_credits = 120
    progress_pct = min(100, int((total_approved / target_credits) * 100)) if target_credits else 0
    c_in = sum(r.credits for r in approved_requests if r.category == 'ในระบบ')
    c_out = sum(r.credits for r in approved_requests if r.category == 'นอกระบบ')
    c_self = sum(r.credits for r in approved_requests if r.category == 'ตามอัธยาศัย')
    rows = ""
    for r in approved_requests:
        rows += f"""
        <tr class="border-b text-sm hover:bg-gray-50">
            <td class="py-3.5 px-4 font-medium text-gray-800">{r.course_name}</td>
            <td class="py-3.5 px-4 text-gray-600">{r.institution}</td>
            <td class="py-3.5 px-4"><span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">{r.category}</span></td>
            <td class="py-3.5 px-4 font-bold text-blue-900">{r.credits} หน่วยกิต</td>
            <td class="py-3.5 px-4 text-xs text-gray-500">{r.date_submitted}</td>
            <td class="py-3.5 px-4"><span class="inline-flex items-center text-xs font-semibold text-green-700 bg-green-50 px-2.5 py-1 rounded-full"><i class="fa-solid fa-circle-check mr-1"></i> สะสมเรียบร้อย</span></td>
        </tr>
        """
    content = f"""
    <div class="mb-6"><h2 class="text-2xl font-bold text-gray-800">💳 หน่วยกิตสะสมของฉัน</h2></div>
    <div class="bg-white p-6 rounded-2xl border shadow-sm mb-8">
        <div class="flex justify-between items-center mb-3">
            <div><span class="text-xs font-bold text-blue-600 uppercase">ความก้าวหน้า</span><h3 class="text-lg font-bold text-gray-800">เป้าหมายหลักสูตร (120 หน่วยกิต)</h3></div>
            <div class="text-right"><span class="text-3xl font-extrabold text-blue-900">{total_approved}</span><span class="text-sm text-gray-400"> / 120 หน่วยกิต</span></div>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-4 overflow-hidden mb-2"><div class="bg-blue-600 h-4 rounded-full transition-all duration-500" style="width: {progress_pct}%;"></div></div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div class="bg-blue-50 border border-blue-100 p-5 rounded-2xl"><span class="text-sm font-semibold text-blue-900">ในระบบ</span><p class="text-2xl font-bold text-blue-900">{c_in} หน่วยกิต</p></div>
        <div class="bg-amber-50 border border-amber-100 p-5 rounded-2xl"><span class="text-sm font-semibold text-amber-900">นอกระบบ</span><p class="text-2xl font-bold text-amber-900">{c_out} หน่วยกิต</p></div>
        <div class="bg-emerald-50 border border-emerald-100 p-5 rounded-2xl"><span class="text-sm font-semibold text-emerald-900">ตามอัธยาศัย</span><p class="text-2xl font-bold text-emerald-900">{c_self} หน่วยกิต</p></div>
    </div>
    <div class="bg-white p-6 rounded-2xl border shadow-sm">
        <h3 class="text-lg font-bold text-gray-800 mb-4">รายการรายวิชาที่สะสมสำเร็จ</h3>
        <table class="w-full text-left">
            <thead class="bg-gray-50 border-b text-xs text-gray-500 uppercase"><tr><th class="py-3 px-4">วิชา</th><th class="py-3 px-4">สถาบัน</th><th class="py-3 px-4">ประเภท</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">วันที่รับรอง</th><th class="py-3 px-4">สถานะ</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="6" class="py-8 text-center text-gray-400 text-sm">ยังไม่มีรายการหน่วยกิตที่ได้รับการอนุมัติ</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/admin/approve/<int:req_id>')
def approve(req_id):
    if session.get('role') == 'admin':
        req = CreditRequest.query.get(req_id)
        if req:
            req.status = 'Approved'
            db.session.commit()
            flash('อนุมัติคำร้องเทียบโอนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/reject/<int:req_id>')
def reject(req_id):
    if session.get('role') == 'admin':
        req = CreditRequest.query.get(req_id)
        if req:
            req.status = 'Rejected'
            db.session.commit()
            flash('ปฏิเสธคำร้องเรียบร้อยแล้ว', 'error')
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    step = request.args.get('step', '1')

    if request.method == 'POST':
        current_step = request.form.get('step')
        if current_step == '1':
            session['reg_prefix'] = request.form.get('prefix')
            session['reg_fullname'] = request.form.get('fullname')
            session['reg_id_card'] = request.form.get('id_card')
            session['reg_dob'] = request.form.get('dob')
            session['reg_phone'] = request.form.get('phone')
            session['reg_email'] = request.form.get('email')
            session['reg_address'] = request.form.get('address')
            return redirect(url_for('register', step='2'))

        elif current_step == '2':
            username = request.form.get('username')
            if User.query.filter_by(username=username).first():
                flash('Username นี้ถูกใช้งานแล้ว', 'error')
                return redirect(url_for('register', step='2'))

            file_filename = None
            if 'id_card_img' in request.files:
                file = request.files['id_card_img']
                if file and file.filename != '':
                    file_filename = secure_filename(f"verify_{username}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_filename))

            new_user = User(
                prefix=session.get('reg_prefix'),
                fullname=session.get('reg_fullname'),
                id_card=session.get('reg_id_card'),
                dob=session.get('reg_dob'),
                phone=session.get('reg_phone'),
                email=session.get('reg_email'),
                address=session.get('reg_address'),
                id_card_img=file_filename,
                username=username,
                password=generate_password_hash(request.form.get('password'))
            )
            db.session.add(new_user)
            db.session.commit()

            for key in ['reg_prefix', 'reg_fullname', 'reg_id_card', 'reg_dob', 'reg_phone', 'reg_email', 'reg_address']:
                session.pop(key, None)

            return redirect(url_for('register', step='3'))

    step_indicator = f"""
    <div class="flex items-center justify-center mb-8 space-x-4">
        <div class="flex items-center space-x-2 {'text-blue-600 font-bold' if step == '1' else 'text-gray-400'}">
            <span class="w-8 h-8 rounded-full flex items-center justify-center border-2 {'border-blue-600 bg-blue-50' if step == '1' else 'border-gray-300'}">1</span>
            <span class="text-xs">ข้อมูลส่วนตัว</span>
        </div>
        <div class="w-8 h-0.5 bg-gray-200"></div>
        <div class="flex items-center space-x-2 {'text-blue-600 font-bold' if step == '2' else 'text-gray-400'}">
            <span class="w-8 h-8 rounded-full flex items-center justify-center border-2 {'border-blue-600 bg-blue-50' if step == '2' else 'border-gray-300'}">2</span>
            <span class="text-xs">ยืนยันตัวตน</span>
        </div>
        <div class="w-8 h-0.5 bg-gray-200"></div>
        <div class="flex items-center space-x-2 {'text-blue-600 font-bold' if step == '3' else 'text-gray-400'}">
            <span class="w-8 h-8 rounded-full flex items-center justify-center border-2 {'border-blue-600 bg-blue-50' if step == '3' else 'border-gray-300'}">3</span>
            <span class="text-xs">เสร็จสิ้น</span>
        </div>
    </div>
    """

    if step == '1':
        content = f"""
        <div class="max-w-xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
            <h2 class="text-2xl font-bold text-center text-blue-900 mb-2">สมัครสมาชิกนักศึกษา</h2>
            <p class="text-xs text-center text-gray-500 mb-6">กรอกข้อมูลส่วนตัวเพื่อลงทะเบียน</p>
            {step_indicator}
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
                        <input type="text" name="fullname" value="{session.get('reg_fullname', '')}" required class="w-full border rounded-lg p-2.5 text-sm">
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="block text-xs font-semibold text-gray-600 mb-1">เลขบัตรประชาชน</label><input type="text" name="id_card" value="{session.get('reg_id_card', '')}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                    <div><label class="block text-xs font-semibold text-gray-600 mb-1">วัน/เดือน/ปีเกิด</label><input type="date" name="dob" value="{session.get('reg_dob', '')}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div><label class="block text-xs font-semibold text-gray-600 mb-1">เบอร์โทรศัพท์</label><input type="tel" name="phone" value="{session.get('reg_phone', '')}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                    <div><label class="block text-xs font-semibold text-gray-600 mb-1">อีเมล</label><input type="email" name="email" value="{session.get('reg_email', '')}" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                </div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">ที่อยู่ปัจจุบัน</label><textarea name="address" rows="2" class="w-full border rounded-lg p-2.5 text-sm">{session.get('reg_address', '')}</textarea></div>
                <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ถัดไป: ยืนยันตัวตน <i class="fa-solid fa-arrow-right ml-1"></i></button>
            </form>
        </div>
        """
    elif step == '2':
        content = f"""
        <div class="max-w-xl mx-auto bg-white p-8 rounded-2xl border shadow-sm">
            <h2 class="text-2xl font-bold text-center text-blue-900 mb-2">ยืนยันตัวตน & ตั้งรหัสผ่าน</h2>
            <p class="text-xs text-center text-gray-500 mb-6">อัปโหลดเอกสารและตั้งรหัสผ่าน</p>
            {step_indicator}
            <form method="POST" enctype="multipart/form-data" class="space-y-4">
                <input type="hidden" name="step" value="2">
                <div>
                    <label class="block text-xs font-semibold text-gray-600 mb-1">อัปโหลดรูปถ่ายบัตรประชาชน/เอกสารยืนยันตัวตน</label>
                    <input type="file" name="id_card_img" required class="w-full border rounded-lg p-2 text-sm bg-gray-50">
                </div>
                <hr class="my-4">
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">ชื่อผู้ใช้งาน (Username)</label><input type="text" name="username" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div><label class="block text-xs font-semibold text-gray-600 mb-1">รหัสผ่าน (Password)</label><input type="password" name="password" required class="w-full border rounded-lg p-2.5 text-sm"></div>
                <div class="flex justify-between space-x-4 pt-2">
                    <a href="/register?step=1" class="w-1/2 text-center bg-gray-100 text-gray-700 font-medium py-2.5 rounded-lg hover:bg-gray-200">ย้อนกลับ</a>
                    <button type="submit" class="w-1/2 bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">ยืนยันการสมัคร</button>
                </div>
            </form>
        </div>
        """
    else:
        content = f"""
        <div class="max-w-md mx-auto bg-white p-8 rounded-2xl border shadow-sm text-center">
            {step_indicator}
            <div class="w-20 h-20 bg-green-100 text-green-600 rounded-full flex items-center justify-center text-3xl mx-auto mb-4"><i class="fa-solid fa-check"></i></div>
            <h2 class="text-2xl font-bold text-gray-800 mb-2">สมัครสมาชิกเสร็จสิ้น!</h2>
            <p class="text-sm text-gray-500 mb-6">บัญชีของคุณลงทะเบียนเรียบร้อยแล้ว สามารถเข้าสู่ระบบได้ทันที</p>
            <a href="/login" class="block w-full bg-blue-600 text-white font-medium py-3 rounded-lg hover:bg-blue-700">เข้าสู่ระบบทันที</a>
        </div>
        """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            session['fullname'] = user.fullname
            session['role'] = user.role
            session['student_id'] = user.student_id
            return redirect(url_for('dashboard'))
        flash('ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง', 'error')

    content = """
    <div class="max-w-md mx-auto my-12 bg-white p-8 rounded-2xl border shadow-sm">
        <h2 class="text-2xl font-bold text-center text-blue-900 mb-6">เข้าสู่ระบบ</h2>
        <form method="POST" class="space-y-4">
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">Username</label><input type="text" name="username" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <div><label class="block text-xs font-semibold text-gray-600 mb-1">Password</label><input type="password" name="password" required class="w-full border rounded-lg p-2.5 text-sm"></div>
            <button type="submit" class="w-full bg-blue-600 text-white font-medium py-2.5 rounded-lg hover:bg-blue-700">เข้าสู่ระบบ</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)