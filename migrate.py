import re
from app import app, db, Course, CourseLesson

with app.app_context():
    print("🔄 กำลังเริ่มย้ายข้อมูลบทเรียนจากคอลัมน์ online_lesson เข้าตาราง course_lesson...")

    # 1. ล้างข้อมูลในตาราง course_lesson ก่อนย้าย
    db.session.query(CourseLesson).delete()
    db.session.commit()

    courses = Course.query.all()
    total_added = 0

    for c in courses:
        if not c.online_lesson:
            continue

        # แปลงตัวตัดบทเรียน ¶ และตัวขึ้นบรรทัดใหม่
        raw_text = str(c.online_lesson).replace('¶', '\n')
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        for line in lines:
            # ดึงจำนวนชั่วโมงจากข้อความในวงเล็บ เช่น (5 ชม.) ถ้าไม่มีให้ใช้ชั่วโมงวิชาหลัก
            match = re.search(r'\((\d+)\s*ชม\.\)', line)
            lesson_hours = int(match.group(1)) if match else (c.hours or 0)

            # บันทึกบทเรียนย่อยลงฐานข้อมูล
            lesson = CourseLesson(
                course_code=c.course_code,
                lesson_name=line,
                hours=lesson_hours
            )
            db.session.add(lesson)
            total_added += 1

    db.session.commit()
    print(f"✅ สำเร็จ! เพิ่มบทเรียนย่อยเข้าตาราง course_lesson ทั้งหมด {total_added} รายการ")