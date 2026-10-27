# analytics.py - ระบบสรุปรายงานและวิเคราะห์ข้อมูลฝั่งเจ้าหน้าที่
from flask import Blueprint, request, session, redirect, url_for, flash
from sqlalchemy import func
import json
from markupsafe import escape

# สร้าง Blueprint เพื่อเชื่อมต่อกับ app.py
analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/admin/analytics')
def admin_analytics():
    # นำเข้าโมเดลและฟังก์ชันจาก app.py แบบ Dynamic เพื่อป้องกันปัญหา Circular Import
    from app import db, User, Course, CreditRequest, render_layout

    # ตรวจสอบสิทธิ์เจ้าหน้าที่
    if session.get('role') not in ['admin', 'superadmin']:
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
        return redirect(url_for('login'))

    # 1. รับค่าตัวกรองจาก Form (GET Parameters)
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    selected_course = request.args.get('course_code', '').strip()
    selected_status = request.args.get('status', '').strip()

    # 2. ค้นหาข้อมูลตามตัวกรอง (Query Filtering)
    query = CreditRequest.query

    # กรองตามช่วงวันที่ยื่น (Date Range)
    if start_date:
        query = query.filter(CreditRequest.date_submitted >= f"{start_date} 00:00")
    if end_date:
        query = query.filter(CreditRequest.date_submitted <= f"{end_date} 23:59")

    # กรองตามรายวิชาที่เลือก
    if selected_course and selected_course != 'ALL':
        query = query.filter(CreditRequest.course_code == selected_course)

    # กรองตามสถานะคำร้อง
    if selected_status and selected_status != 'ALL':
        if selected_status == 'Needs_Revision':
            query = query.filter(CreditRequest.status.in_(['Needs_Revision', 'Need_Edit']))
        else:
            query = query.filter(CreditRequest.status == selected_status)

    filtered_requests = query.order_by(CreditRequest.id.desc()).all()

    # 3. คำนวณค่าสถิติสรุป (Metrics Calculation)
    total_reqs = len(filtered_requests)
    approved_reqs = [r for r in filtered_requests if r.status == 'Approved']
    pending_reqs = [r for r in filtered_requests if r.status == 'Pending']
    revision_reqs = [r for r in filtered_requests if r.status in ['Needs_Revision', 'Need_Edit']]

    total_approved_credits = sum(r.credits or 0 for r in approved_reqs)
    approval_rate = round((len(approved_reqs) / total_reqs * 100), 1) if total_reqs > 0 else 0
    unique_students_count = len(set(r.user_id for r in filtered_requests if r.user_id))

    # 4. ดึงรายวิชาทั้งหมดเพื่อใส่ใน Dropdown ตัวกรอง
    try:
        all_courses = Course.query.order_by(Course.course_code.asc()).all()
    except Exception:
        all_courses = []

    # 5. เตรียมข้อมูลสำหรับกราฟ (Chart.js Data)
    # กราฟที่ 1: สัดส่วนสถานะ
    status_chart_data = [len(pending_reqs), len(approved_reqs), len(revision_reqs)]

    # กราฟที่ 2: Top 5 วิชาที่มีการยื่นคำร้องสูงสุดในเงื่อนไขที่เลือก
    course_counts = {}
    for r in filtered_requests:
        c_name = r.course_name or 'ไม่ระบุ'
        course_counts[c_name] = course_counts.get(c_name, 0) + 1
    
    sorted_top_courses = sorted(course_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_course_labels = [tc[0] for tc in sorted_top_courses]
    top_course_values = [tc[1] for tc in sorted_top_courses]

    # 6. สร้างชุดตัวเลือกรายวิชา HTML
    course_options_html = '<option value="ALL">-- ทุกรายวิชา --</option>'
    for c in all_courses:
        is_sel = 'selected' if selected_course == c.course_code else ''
        course_options_html += f'<option value="{escape(c.course_code)}" {is_sel}>{escape(c.course_code)} - {escape(c.course_name)}</option>'

    # 7. ตารางแสดงรายการคำร้องตามเงื่อนไข
    table_rows_html = ""
    for r in filtered_requests:
        st_badge = ''
        if r.status == 'Pending':
            st_badge = '<span class="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-bold px-2.5 py-1 rounded-full">⏳ รอดำเนินการ</span>'
        elif r.status == 'Approved':
            st_badge = '<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold px-2.5 py-1 rounded-full">✅ อนุมัติแล้ว</span>'
        else:
            st_badge = '<span class="bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-bold px-2.5 py-1 rounded-full">⚠️ ให้แก้ไข</span>'

        student_name = r.user.fullname if r.user else '-'
        student_code = r.user.member_id if r.user else '-'

        table_rows_html += f"""
        <tr class="hover:bg-slate-50 transition border-b border-slate-100 text-xs">
            <td class="py-3.5 px-4 font-mono font-bold text-sky-600 whitespace-nowrap">{escape(r.req_code or f'TR{r.id:04d}')}</td>
            <td class="py-3.5 px-4 font-bold text-slate-800 whitespace-nowrap">{escape(student_name)}<br><span class="text-[10px] text-slate-400 font-normal">({escape(student_code)})</span></td>
            <td class="py-3.5 px-4 font-bold text-slate-700">{escape(r.course_name or '-')}</td>
            <td class="py-3.5 px-4 text-center font-black text-sky-600 whitespace-nowrap">{r.credits or 0}</td>
            <td class="py-3.5 px-4 text-center whitespace-nowrap">{escape(r.date_submitted or '-')}</td>
            <td class="py-3.5 px-4 text-center whitespace-nowrap">{st_badge}</td>
            <td class="py-3.5 px-4 text-right whitespace-nowrap">
                <a href="/admin/review/{r.id}" class="bg-sky-50 hover:bg-sky-100 text-sky-700 font-bold px-3 py-1.5 rounded-xl border border-sky-200 transition inline-block">ดูรายละเอียด</a>
            </td>
        </tr>
        """

    if not table_rows_html:
        table_rows_html = '<tr><td colspan="7" class="py-12 text-center text-xs font-bold text-slate-400">ไม่พบข้อมูลที่ตรงกับเงื่อนไขการกรอง</td></tr>'

    # 8. สร้างหน้า HTML UI
    content = f"""
    <div class="max-w-6xl mx-auto space-y-8">
        <!-- Header -->
        <div class="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-8 text-white shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <span class="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs px-3 py-1 rounded-full font-black uppercase">Analytics & Custom Reports</span>
                <h1 class="text-2xl font-black mt-2">รายงานและสถิติวิเคราะห์ตามช่วงเวลา</h1>
                <p class="text-xs text-slate-300 mt-1">กรองสถิติการยื่นคำร้องเทียบโอนรายวิชา และสรุปยอดหน่วยกิตแบบกำหนดเงื่อนไข</p>
            </div>
            <a href="/admin/requests" class="bg-white/10 hover:bg-white/20 text-white font-extrabold px-5 py-2.5 rounded-2xl text-xs transition border border-white/20">
                ← กลับหน้าตรวจคำร้อง
            </a>
        </div>

        <!-- Filter Box (แถบตัวกรอง) -->
        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
            <div class="flex items-center gap-2 border-b border-slate-100 pb-3">
                <i class="fa-solid fa-filter text-indigo-600"></i>
                <h3 class="text-sm font-black text-slate-800">ตัวกรองข้อมูลสรุป (Custom Filters)</h3>
            </div>
            
            <form method="GET" action="/admin/analytics" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                    <label class="block text-xs font-black uppercase text-slate-400 mb-1">ตั้งแต่วันที่</label>
                    <input type="date" name="start_date" value="{escape(start_date)}" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500">
                </div>

                <div>
                    <label class="block text-xs font-black uppercase text-slate-400 mb-1">ถึงวันที่</label>
                    <input type="date" name="end_date" value="{escape(end_date)}" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500">
                </div>

                <div>
                    <label class="block text-xs font-black uppercase text-slate-400 mb-1">เลือกรายวิชา</label>
                    <select name="course_code" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500">
                        {course_options_html}
                    </select>
                </div>

                <div>
                    <label class="block text-xs font-black uppercase text-slate-400 mb-1">สถานะคำร้อง</label>
                    <select name="status" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500">
                        <option value="ALL" {'selected' if selected_status=='ALL' or not selected_status else ''}>-- ทุกสถานะ --</option>
                        <option value="Pending" {'selected' if selected_status=='Pending' else ''}>⏳ รอดำเนินการ</option>
                        <option value="Approved" {'selected' if selected_status=='Approved' else ''}>✅ อนุมัติแล้ว</option>
                        <option value="Needs_Revision" {'selected' if selected_status=='Needs_Revision' else ''}>⚠️ ให้แก้ไขหลักฐาน</option>
                    </select>
                </div>

                <div class="lg:col-span-4 flex justify-end gap-2 pt-2 border-t border-slate-100">
                    <a href="/admin/analytics" class="bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold px-5 py-2.5 rounded-2xl text-xs transition">
                        ล้างตัวกรอง
                    </a>
                    <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-6 py-2.5 rounded-2xl text-xs shadow-md transition flex items-center gap-2">
                        <i class="fa-solid fa-magnifying-glass"></i> ประมวลผลรายงาน
                    </button>
                </div>
            </form>
        </div>

        <!-- Summary Cards (การ์ดสรุปยอด) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                <p class="text-xs font-black text-slate-400 uppercase">คำร้องตามเงื่อนไข</p>
                <p class="text-3xl font-black text-slate-800 mt-2">{total_reqs} <span class="text-xs font-normal text-slate-400">รายการ</span></p>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-emerald-100 shadow-sm">
                <p class="text-xs font-black text-emerald-600 uppercase">หน่วยกิตอนุมัติรวม</p>
                <p class="text-3xl font-black text-emerald-700 mt-2">{total_approved_credits} <span class="text-xs font-normal text-slate-400">หน่วยกิต</span></p>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm">
                <p class="text-xs font-black text-sky-600 uppercase">อัตราการอนุมัติ (Pass Rate)</p>
                <p class="text-3xl font-black text-sky-700 mt-2">{approval_rate}%</p>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-indigo-100 shadow-sm">
                <p class="text-xs font-black text-indigo-600 uppercase">จำนวนนักศึกษาที่ยื่น</p>
                <p class="text-3xl font-black text-indigo-700 mt-2">{unique_students_count} <span class="text-xs font-normal text-slate-400">คน</span></p>
            </div>
        </div>

        <!-- Charts Grid (ส่วนแสดงกราฟเปรียบเทียบ) -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                <h3 class="text-base font-black text-slate-800 mb-4">สัดส่วนสถานะคำร้องช่วงที่เลือก</h3>
                <div class="h-64 relative">
                    <canvas id="analyticsStatusChart"></canvas>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                <h3 class="text-base font-black text-slate-800 mb-4">5 อันดับวิชาที่มีการยื่นคำร้องสูงสุด</h3>
                <div class="h-64 relative">
                    <canvas id="analyticsTopCourseChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Table Grid (ตารางรายการคำร้องที่กรองได้) -->
        <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
            <div class="flex justify-between items-center border-b border-slate-100 pb-4">
                <div>
                    <h3 class="text-lg font-black text-slate-800">รายการคำร้องตามตัวกรอง</h3>
                    <p class="text-xs text-slate-400">แสดงผลรวม {total_reqs} รายการ</p>
                </div>
            </div>

            <div class="overflow-x-auto max-h-[450px] overflow-y-auto pr-1">
                <table class="w-full text-left border-separate border-spacing-0">
                    <thead class="text-xs text-slate-400 font-extrabold uppercase bg-slate-50 sticky top-0 z-10 shadow-sm">
                        <tr>
                            <th class="px-4 py-3 bg-slate-50 rounded-l-xl">รหัสคำร้อง</th>
                            <th class="px-4 py-3 bg-slate-50">นักศึกษา</th>
                            <th class="px-4 py-3 bg-slate-50">รายวิชา</th>
                            <th class="px-4 py-3 text-center bg-slate-50">หน่วยกิต</th>
                            <th class="px-4 py-3 text-center bg-slate-50">วันที่ยื่น</th>
                            <th class="px-4 py-3 text-center bg-slate-50">สถานะ</th>
                            <th class="px-4 py-3 text-right bg-slate-50 rounded-r-xl">จัดการ</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        {table_rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Chart.js Setup Script -->
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        // 1. Render Status Chart
        const statusCtx = document.getElementById('analyticsStatusChart').getContext('2d');
        new Chart(statusCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['รอตรวจสอบ', 'อนุมัติแล้ว', 'ต้องแก้ไข'],
                datasets: [{{
                    data: {json.dumps(status_chart_data)},
                    backgroundColor: ['#f59e0b', '#10b981', '#6366f1'],
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ position: 'bottom' }} }},
                cutout: '70%'
            }}
        }});

        // 2. Render Top Courses Chart
        const topCourseCtx = document.getElementById('analyticsTopCourseChart').getContext('2d');
        new Chart(topCourseCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(top_course_labels, ensure_ascii=False)},
                datasets: [{{
                    label: 'จำนวนคำร้อง',
                    data: {json.dumps(top_course_values)},
                    backgroundColor: '#3b82f6',
                    borderRadius: 8
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ x: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }}
            }}
        }});
    }});
    </script>
    """

    return render_layout(content, active_page='admin_analytics')