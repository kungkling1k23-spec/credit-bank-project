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
# Database Models (รองรับอัปโหลดใบประกาศสูงสุด 3 รูป)
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
    date_submitted = db.Column(db.String(20), default="2026-09-06")
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
    created_at = db.Column(db.String(20), default="2026-09-06")
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
# Layout Template (เพิ่มเมนู "รายวิชาทั้งหมด" ถัดจากค้นหารายวิชา)
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
        body { font-family: 'Sarabun', sans-serif; background-color: #f8fafc; }
        .sidebar-transition { transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-hover { transition: all 0.2s ease-in-out; }
        .card-hover:hover { transform: translateY(-2px); box-shadow: 0 10px 20px -5px rgba(14, 165, 233, 0.15); }
        .sidebar-expanded { width: 270px; }
        .sidebar-collapsed { width: 80px; }
        .sidebar-collapsed .nav-text, .sidebar-collapsed .logo-img-full, .sidebar-collapsed .section-title { display: none !important; }
        .sidebar-collapsed .logo-img-small { display: block !important; }
        .sidebar-collapsed .toggle-icon { transform: rotate(180deg); }
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800 antialiased flex flex-col md:flex-row">

    <div class="md:hidden bg-sky-100/90 text-slate-900 px-4 py-3 flex justify-between items-center sticky top-0 z-50 border-b border-sky-200 shadow-sm backdrop-blur-md">
        <a href="/" class="flex items-center gap-2">
            <img src="/static/images/logo.png" alt="Logo" class="h-9 object-contain" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x50?text=IS+RMUTTO';">
        </a>
        <button id="mobile-toggle" class="p-2 text-sky-900 bg-sky-200 rounded-xl border border-sky-300"><i class="fa-solid fa-bars text-lg"></i></button>
    </div>

    <aside id="sidebar" class="sidebar-expanded sidebar-transition bg-sky-100/80 text-slate-800 h-screen flex flex-col fixed md:sticky top-0 z-40 shadow-lg border-r border-sky-200 hidden md:flex shrink-0">
        <div class="p-4 flex flex-col border-b border-sky-200 bg-sky-200/50 shrink-0">
            <a href="/" class="flex items-center justify-center py-1 px-1">
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

        <div class="flex-grow p-3 space-y-1 overflow-y-auto">
            <p class="section-title text-[11px] font-black text-sky-800 uppercase px-3 mb-1 pt-2">เมนูหลัก</p>
            <a href="/" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl text-slate-700 hover:text-sky-950 hover:bg-sky-200/60 font-bold text-sm transition">
                <i class="fa-solid fa-house text-base w-6 text-center text-sky-600"></i>
                <span class="nav-text">หน้าแรก</span>
            </a>

            {% if session.get('user_id') %}
                {% if session.get('role') in ['admin', 'superadmin'] %}
                    <p class="section-title text-[11px] font-black text-sky-800 uppercase px-3 mb-1 pt-3">จัดการระบบเจ้าหน้าที่</p>
                    <a href="/admin/students" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-users text-base w-6 text-center text-sky-600"></i><span class="nav-text">รายชื่อนักศึกษา</span></a>
                    <a href="/admin/requests" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-file-signature text-base w-6 text-center text-sky-600"></i><span class="nav-text">คำร้องเทียบโอน</span></a>
                    <a href="/all_courses" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-book-open text-base w-6 text-center text-sky-600"></i><span class="nav-text">รายวิชาทั้งหมด</span></a>
                {% else %}
                    <p class="section-title text-[11px] font-black text-sky-800 uppercase px-3 mb-1 pt-3">บริการนักศึกษา IS</p>
                    <a href="/available_courses" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-magnifying-glass text-base w-6 text-center text-sky-600"></i><span class="nav-text">ค้นหารายวิชา</span></a>
                    <!-- แทรกเมนู "รายวิชาทั้งหมด" ถัดจากหน้าค้นหารายวิชา -->
                    <a href="/all_courses" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-book-open text-base w-6 text-center text-sky-600"></i><span class="nav-text">รายวิชาทั้งหมด</span></a>
                    <a href="/submit_credit" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-file-circle-plus text-base w-6 text-center text-sky-600"></i><span class="nav-text">ยื่นคำขอเทียบโอน</span></a>
                    <a href="/history" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl hover:bg-sky-200/60 font-bold text-sm transition"><i class="fa-solid fa-clock-rotate-left text-base w-6 text-center text-sky-600"></i><span class="nav-text">ประวัติคำขอ</span></a>
                {% endif %}
            {% else %}
                <div class="pt-3 space-y-2">
                    <a href="/login" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl font-bold text-sm border border-sky-300 hover:bg-sky-200/50"><i class="fa-solid fa-right-to-bracket text-base w-6 text-center text-sky-700"></i><span class="nav-text">เข้าสู่ระบบ</span></a>
                    <a href="/register" class="flex items-center gap-3 px-3 py-2.5 rounded-2xl bg-sky-600 text-white font-extrabold text-sm shadow"><i class="fa-solid fa-user-plus text-base w-6 text-center"></i><span class="nav-text">ลงทะเบียนนักศึกษา</span></a>
                </div>
            {% endif %}
        </div>

        {% if session.get('user_id') %}
            <div class="p-3 border-t border-sky-200 bg-sky-200/40 shrink-0">
                <a href="/logout" class="flex items-center gap-3 px-3 py-2 text-xs font-extrabold text-rose-700 hover:bg-rose-100/80 rounded-xl transition">
                    <i class="fa-solid fa-arrow-right-from-bracket text-sm w-6 text-center"></i>
                    <span class="nav-text">ออกจากระบบ</span>
                </a>
            </div>
        {% endif %}
    </aside>

    <div class="flex-grow flex flex-col min-h-screen min-w-0">
        <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="p-4 mb-4 text-sm rounded-2xl font-semibold shadow-sm flex items-center justify-between border transition-all {% if category == 'error' or category == 'danger' %}bg-rose-50 text-rose-700 border-rose-200{% else %}bg-emerald-50 text-emerald-800 border-emerald-200{% endif %}">
                            <div class="flex items-center gap-2"><i class="fa-solid fa-circle-info"></i><span>{{ message }}</span></div>
                            <button onclick="this.parentElement.remove()" class="text-xs font-bold px-2 py-1">✕</button>
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            {{ content | safe }}
        </main>
        <footer class="bg-sky-100/60 text-slate-600 border-t border-sky-200 p-4 text-xs text-center font-bold">© 2026 Credit Bank IS RMUTTO</footer>
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
        <div class="max-w-4xl mx-auto py-12 text-center">
            <h1 class="text-4xl font-black text-slate-900 mb-3">ธนาคารหน่วยกิต IS RMUTTO</h1>
            <p class="text-slate-600 mb-8 font-medium">ระบบสะสมและเทียบโอนหน่วยกิตดิจิทัล สาขาวิชาระบบสารสนเทศ</p>
            <div class="flex justify-center gap-4">
                <a href="/register" class="px-6 py-3 bg-sky-600 text-white font-bold rounded-2xl shadow">ลงทะเบียนนักศึกษา</a>
                <a href="/login" class="px-6 py-3 bg-white text-slate-800 border border-sky-200 font-bold rounded-2xl">เข้าสู่ระบบ</a>
            </div>
        </div>
        """
        return render_template_string(LAYOUT_TEMPLATE, content=content)

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('login'))

    user_requests = CreditRequest.query.filter_by(user_id=user.id).all()
    approved_credits = sum(r.credits for r in user_requests if r.status == 'Approved')
    pending_credits = sum(r.credits for r in user_requests if r.status == 'Pending')

    content = f"""
    <div class="mb-6">
        <h2 class="text-3xl font-black text-slate-900">สวัสดีครับ, {user.fullname}</h2>
        <p class="text-xs font-bold text-sky-700 mt-1">รหัสนักศึกษา: {user.member_id} (สาขาวิชาระบบสารสนเทศ)</p>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase mb-1">หน่วยกิตสะสมที่อนุมัติแล้ว</p>
                <h3 class="text-3xl font-black text-sky-600">{approved_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase mb-1">หน่วยกิตรออนุมัติเทียบโอน</p>
                <h3 class="text-3xl font-black text-amber-500">{pending_credits} <span class="text-xs font-medium text-slate-400">หน่วยกิต</span></h3>
            </div>
            <div class="w-12 h-12 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-hourglass-half"></i></div>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-sky-100 shadow-sm flex items-center justify-between card-hover">
            <div>
                <p class="text-xs font-bold text-slate-400 uppercase mb-1">คำร้องขอเทียบโอนทั้งหมด</p>
                <h3 class="text-3xl font-black text-slate-800">{len(user_requests)} <span class="text-xs font-medium text-slate-400">รายการ</span></h3>
            </div>
            <div class="w-12 h-12 bg-purple-50 text-purple-500 rounded-2xl flex items-center justify-center text-xl"><i class="fa-solid fa-list-check"></i></div>
        </div>
    </div>

    <div class="flex flex-wrap gap-3">
        <a href="/available_courses" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-6 py-3 rounded-2xl shadow transition text-sm flex items-center gap-2"><i class="fa-solid fa-magnifying-glass"></i> ค้นหารายวิชา</a>
        <a href="/all_courses" class="bg-white hover:bg-sky-50 text-sky-800 font-bold px-6 py-3 rounded-2xl border border-sky-200 shadow-sm transition text-sm flex items-center gap-2"><i class="fa-solid fa-book-open"></i> ดูรายวิชาทั้งหมด</a>
        <a href="/submit_credit" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-6 py-3 rounded-2xl shadow transition text-sm flex items-center gap-2"><i class="fa-solid fa-file-circle-plus"></i> ยื่นคำขอเทียบโอน</a>
    </div>
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
        badge_provider = "bg-sky-100 text-sky-900 border-sky-200" if c['provider'] == 'ThaiMOOC' else "bg-amber-100 text-amber-900 border-amber-200"
        mooc_items_html = "".join([f'<li class="flex items-start gap-1.5"><i class="fa-solid fa-angle-right text-sky-600 mt-1 shrink-0"></i><span>{m}</span></li>' for m in c['mooc_list']])

        cards += f"""
        <div class="bg-white rounded-3xl border border-sky-100 p-6 shadow-sm flex flex-col justify-between card-hover">
            <div>
                <div class="flex flex-wrap items-center justify-between gap-2 mb-4 pb-3 border-b border-sky-100">
                    <span class="font-mono text-xs font-bold bg-sky-100 text-sky-800 px-3 py-1 rounded-xl border border-sky-200 shrink-0">{c['code']}</span>
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="px-2.5 py-1 rounded-xl text-[11px] font-black border {badge_provider} shrink-0">{c['provider']}</span>
                        <span class="bg-slate-100 text-slate-700 text-[11px] px-2.5 py-1 rounded-xl font-bold border border-slate-300 shrink-0">{c['group']}</span>
                    </div>
                </div>
                <h3 class="text-lg font-extrabold text-slate-900 mb-2 leading-snug">{c['name']}</h3>
                <p class="text-xs text-slate-500 font-bold mb-3"><i class="fa-solid fa-graduation-cap text-sky-500 mr-1"></i> สาขาวิชาระบบสารสนเทศ (3 หน่วยกิต)</p>
                <div class="bg-sky-50/60 p-4 rounded-2xl border border-sky-200/60 mb-4">
                    <p class="text-xs font-black text-slate-800 mb-2"><i class="fa-solid fa-laptop-code text-sky-700 mr-1"></i> บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม ({c['provider']}):</p>
                    <ul class="text-xs text-slate-700 leading-relaxed space-y-1.5 font-semibold">{mooc_items_html}</ul>
                </div>
            </div>
            <div class="border-t border-sky-100 pt-4 mt-2">
                <div class="flex justify-between items-center text-xs text-slate-600 mb-4">
                    <span><i class="fa-regular fa-clock mr-1"></i> รวมเวลาเรียน: <b>{c['hours']}</b></span>
                    <span class="font-black text-sky-800 text-sm bg-sky-100 px-3 py-1 rounded-xl border border-sky-200">{c['credits']} หน่วยกิต</span>
                </div>
                <a href="/submit_credit?course={c['name']}&inst={c['provider']}&credits={c['credits']}" class="block text-center w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3 rounded-2xl text-sm transition shadow-md">ยื่นเทียบโอนวิชานี้</a>
            </div>
        </div>
        """

    content = f"""
    <div class="hero-sky text-slate-900 p-8 rounded-3xl shadow-sm mb-8 flex flex-col md:flex-row justify-between items-center gap-6 border border-sky-200">
        <div>
            <span class="bg-white/80 text-sky-900 text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-wider mb-2 inline-block border border-sky-200">Search Courses</span>
            <h2 class="text-3xl font-black text-slate-900">🔍 ค้นหารายวิชาเทียบโอนหลักสูตร</h2>
            <p class="text-slate-700 text-xs mt-1.5 leading-relaxed font-bold">ค้นหารายวิชาในหลักสูตรสาขาวิชาระบบสารสนเทศ และบทเรียนออนไลน์ที่ใช้เปิดเทียบโอน</p>
        </div>
        <div class="bg-white/90 px-6 py-4 rounded-2xl border border-sky-200 text-center shrink-0 shadow-sm">
            <span class="text-xs text-slate-600 block font-bold">จำนวนรายวิชาที่พบ</span>
            <span class="text-3xl font-black text-sky-700">{len(filtered_courses)}</span> <span class="text-xs text-slate-600 font-bold">/ {len(IS_THAIMOOC_COURSES)} วิชา</span>
        </div>
    </div>

    <form method="GET" action="/available_courses" class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm mb-8 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5"><i class="fa-solid fa-globe mr-1 text-sky-500"></i> สื่อการเรียนรู้ (Provider)</label>
                <select name="provider" onchange="this.form.submit()" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
                    <option value="ทั้งหมด" {'selected' if selected_provider=='ทั้งหมด' or not selected_provider else ''}>ทุกระบบ (Thai & Chula MOOC)</option>
                    <option value="ThaiMOOC" {'selected' if selected_provider=='ThaiMOOC' else ''}>ThaiMOOC</option>
                    <option value="ChulaMOOC" {'selected' if selected_provider=='ChulaMOOC' else ''}>ChulaMOOC</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5"><i class="fa-solid fa-layer-group mr-1 text-sky-600"></i> หมวดวิชาหลักสูตร</label>
                <select name="group" onchange="this.form.submit()" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
                    <option value="ทั้งหมด" {'selected' if selected_group=='ทั้งหมด' or not selected_group else ''}>ทุกหมวดวิชา</option>
                    <option value="หมวดวิชาศึกษาทั่วไป" {'selected' if selected_group=='หมวดวิชาศึกษาทั่วไป' else ''}>หมวดวิชาศึกษาทั่วไป</option>
                    <option value="หมวดวิชาแกน" {'selected' if selected_group=='หมวดวิชาแกน' else ''}>หมวดวิชาแกน</option>
                    <option value="หมวดวิชาเลือก" {'selected' if selected_group=='หมวดวิชาเลือก' else ''}>หมวดวิชาเลือก</option>
                </select>
            </div>
            <div class="md:col-span-2">
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5"><i class="fa-solid fa-magnifying-glass mr-1 text-sky-600"></i> ค้นหาด้วยรหัสวิชา / ชื่อวิชา</label>
                <div class="flex gap-2">
                    <input type="text" name="search" value="{search_query}" placeholder="พิมพ์ชื่อวิชา..." class="w-full px-4 py-3 border border-sky-200 rounded-2xl text-sm bg-sky-50/40 font-semibold">
                    <button type="submit" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-7 py-3 rounded-2xl text-sm transition shadow-md shrink-0">ค้นหา</button>
                </div>
            </div>
        </div>
    </form>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards if cards else '<div class="col-span-3 text-center py-16 text-slate-400 bg-white rounded-3xl border border-sky-100 font-bold">ไม่พบรายวิชาที่ตรงกับเงื่อนไขการค้นหา</div>'}
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

# ==========================================
# หน้าใหม่: รายวิชาทั้งหมด (All Courses View)
# ==========================================
@app.route('/all_courses')
def all_courses():
    if 'user_id' not in session: 
        return redirect(url_for('login'))

    rows = ""
    for idx, c in enumerate(IS_THAIMOOC_COURSES, 1):
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
                <a href="/submit_credit?course={c['name']}&inst={c['provider']}&credits={c['credits']}" class="bg-sky-600 hover:bg-sky-700 text-white font-bold px-3 py-1.5 rounded-xl text-[11px] inline-block shadow-sm">
                    เลือกวิชานี้เทียบโอน
                </a>
            </td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm mb-8">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-sky-100">
            <div>
                <h2 class="text-2xl font-black text-slate-900 flex items-center gap-2">
                    <i class="fa-solid fa-book-open text-sky-600"></i> รายวิชาทั้งหมดในหลักสูตรสาขาวิชาระบบสารสนเทศ
                </h2>
                <p class="text-xs text-slate-500 mt-1 font-medium">ตารางสรุปรายวิชาในหลักสูตรพร้อมบทเรียนออนไลน์ ThaiMOOC / ChulaMOOC ที่ต้องเรียนเพื่อเทียบโอน</p>
            </div>
            <div class="bg-sky-100 text-sky-900 px-4 py-2 rounded-2xl border border-sky-200 text-xs font-black shrink-0 text-center">
                รวมทั้งหมด {len(IS_THAIMOOC_COURSES)} รายวิชา
            </div>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-sky-100">
            <table class="w-full text-left min-w-[750px]">
                <thead class="bg-sky-100/60 border-b border-sky-200 text-xs font-black uppercase text-slate-700">
                    <tr>
                        <th class="py-3.5 px-4 text-center">#</th>
                        <th class="py-3.5 px-4">รหัสวิชา</th>
                        <th class="py-3.5 px-4">รายวิชาหลักสูตร IS</th>
                        <th class="py-3.5 px-4">หมวดวิชา</th>
                        <th class="py-3.5 px-4">บทเรียนออนไลน์ที่ต้องเรียนเพิ่ม</th>
                        <th class="py-3.5 px-4 text-center">หน่วยกิต</th>
                        <th class="py-3.5 px-4 text-center">การจัดการ</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-sky-100">
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/submit_credit', methods=['GET', 'POST'])
def submit_credit():
    if 'user_id' not in session: 
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            credits_val = int(request.form.get('credits', 3))
            course_name = request.form.get('course_name', '').strip()
            institution = request.form.get('institution', 'ThaiMOOC')
            category = request.form.get('category', 'หมวดวิชาศึกษาทั่วไป')

            files = request.files.getlist('cert_files')
            uploaded_docs = []

            for file in files[:3]:
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
                <input type="text" name="course_name" value="{init_course}" required placeholder="เช่น คุณภาพการใช้ชีวิต" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">ระบบออนไลน์ *</label>
                    <select name="institution" class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
                        <option value="ThaiMOOC" {'selected' if init_inst=='ThaiMOOC' else ''}>ThaiMOOC</option>
                        <option value="ChulaMOOC" {'selected' if init_inst=='ChulaMOOC' else ''}>ChulaMOOC</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 uppercase mb-1">จำนวนหน่วยกิต *</label>
                    <input type="number" name="credits" value="{init_credits}" min="1" max="10" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
                </div>
            </div>

            <div class="border-t border-sky-100 pt-4">
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1.5"><i class="fa-solid fa-images mr-1 text-sky-600"></i> แนบรูปภาพใบประกาศ / เกียรติบัตร (1 - 3 รูป) *</label>
                <input type="file" name="cert_files" accept="image/*,.pdf" multiple required class="w-full border border-sky-200 rounded-2xl p-2 text-xs bg-sky-50/40 font-semibold">
                <p class="text-[11px] text-slate-400 mt-1 font-medium">สามารถเลือกพร้อมกันได้ไม่เกิน 3 รูป (PNG, JPG, PDF)</p>
            </div>

            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl transition shadow-md text-sm mt-2">ยืนยันยื่นคำขอเทียบโอน</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_requests = CreditRequest.query.filter_by(user_id=session['user_id']).order_by(CreditRequest.id.desc()).all()

    rows = ""
    for r in user_requests:
        imgs_html = ""
        for idx, img in enumerate([r.doc_img, r.doc_img2, r.doc_img3], 1):
            if img and img != 'default_doc.png':
                imgs_html += f'<a href="/static/uploads/{img}" target="_blank" class="text-[11px] text-sky-600 underline font-bold mr-2"><i class="fa-solid fa-image"></i> ใบประกาศรูปที่ {idx}</a>'

        rows += f"""
        <tr class="border-b border-sky-100 text-sm hover:bg-sky-50/50 transition">
            <td class="py-4 px-4 font-mono font-bold text-slate-600">{r.req_code}</td>
            <td class="py-4 px-4 font-extrabold text-slate-900">{r.course_name}<br>{imgs_html}</td>
            <td class="py-4 px-4 font-bold">{r.institution}</td>
            <td class="py-4 px-4 font-black text-sky-600">{r.credits}</td>
            <td class="py-4 px-4"><span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800">{r.status}</span></td>
        </tr>
        """

    content = f"""
    <div class="bg-white p-8 rounded-3xl border border-sky-100 shadow-sm overflow-x-auto">
        <h3 class="text-xl font-black mb-6 text-slate-900">ประวัติคำร้องขอเทียบโอน</h3>
        <table class="w-full text-left min-w-[650px]">
            <thead class="bg-sky-100/60 border-b border-sky-200 text-xs font-black uppercase text-slate-700">
                <tr><th class="py-3 px-4">รหัส</th><th class="py-3 px-4">วิชา / รูปใบประกาศที่แนบ</th><th class="py-3 px-4">ระบบ</th><th class="py-3 px-4">หน่วยกิต</th><th class="py-3 px-4">สถานะ</th></tr>
            </thead>
            <tbody>{rows if rows else '<tr><td colspan="5" class="py-8 text-center text-slate-400 font-bold">ไม่มีรายการประวัติคำร้อง</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

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
            return redirect(url_for('home'))
        flash('ข้อมูลเข้าสู่ระบบไม่ถูกต้อง', 'error')

    content = """
    <div class="max-w-md mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl my-10">
        <h2 class="text-2xl font-black mb-6 text-center text-slate-900">เข้าสู่ระบบ</h2>
        <form method="POST" class="space-y-4">
            <input type="text" name="username" placeholder="Username / เลขบัตรประชาชน" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <input type="password" name="password" placeholder="รหัสผ่าน" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl shadow transition">เข้าสู่ระบบ</button>
        </form>
    </div>
    """
    return render_template_string(LAYOUT_TEMPLATE, content=content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        id_card = request.form.get('id_card', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if User.query.filter_by(id_card=id_card).first():
            flash('เลขบัตรประชาชนนี้เคยลงทะเบียนแล้ว', 'error')
            return redirect(url_for('register'))

        new_user = User(
            member_id=generate_member_id(),
            fullname=fullname,
            id_card=id_card,
            username=username,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        flash('ลงทะเบียนเรียบร้อยแล้ว เข้าสู่ระบบได้ทันที', 'success')
        return redirect(url_for('login'))

    content = """
    <div class="max-w-md mx-auto bg-white p-8 rounded-3xl border border-sky-100 shadow-xl my-8">
        <h2 class="text-2xl font-black mb-6 text-center text-slate-900">ลงทะเบียนนักศึกษา IS</h2>
        <form method="POST" class="space-y-4">
            <input type="text" name="fullname" placeholder="ชื่อ-นามสกุล" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <input type="text" name="id_card" maxlength="13" placeholder="เลขบัตรประชาชน 13 หลัก" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <input type="text" name="username" placeholder="Username" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <input type="password" name="password" placeholder="Password" required class="w-full border border-sky-200 rounded-2xl p-3 text-sm bg-sky-50/40 font-semibold">
            <button type="submit" class="w-full bg-sky-600 hover:bg-sky-700 text-white font-bold py-3.5 rounded-2xl shadow transition">ยืนยันการลงทะเบียน</button>
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