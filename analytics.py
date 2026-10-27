# analytics.py - ระบบสรุปรายงานและวิเคราะห์ข้อมูลฝั่งเจ้าหน้าที่ (เพิ่มตัวกรองรายชื่อนักศึกษา)
from flask import Blueprint, request, session, redirect, url_for, flash
from sqlalchemy import func
import json
from markupsafe import escape

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/admin/analytics')
def admin_analytics():
    try:
        from app import db, User, Course, CreditRequest, render_layout
    except Exception as e:
        return f"<div style='padding:20px; color:red;'><h3>Import Error:</h3><p>{escape(str(e))}</p></div>"

    if session.get('role') not in ['admin', 'superadmin']:
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'error')
        return redirect(url_for('login'))

    try:
        # 1. รับค่าตัวกรองจาก Form
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        selected_course = request.args.get('course_code', '').strip()
        selected_student = request.args.get('student_id', '').strip()
        selected_status = request.args.get('status', '').strip()

        # 2. ค้นหาข้อมูลตามตัวกรอง
        query = CreditRequest.query

        if start_date:
            query = query.filter(CreditRequest.date_submitted.isnot(None)).filter(CreditRequest.date_submitted >= f"{start_date} 00:00")
        if end_date:
            query = query.filter(CreditRequest.date_submitted.isnot(None)).filter(CreditRequest.date_submitted <= f"{end_date} 23:59")
        if selected_course and selected_course != 'ALL':
            query = query.filter(CreditRequest.course_code == selected_course)
        if selected_student and selected_student != 'ALL':
            try:
                query = query.filter(CreditRequest.user_id == int(selected_student))
            except ValueError:
                pass
        if selected_status and selected_status != 'ALL':
            if selected_status == 'Needs_Revision':
                query = query.filter(CreditRequest.status.in_(['Needs_Revision', 'Need_Edit']))
            else:
                query = query.filter(CreditRequest.status == selected_status)

        filtered_requests = query.order_by(CreditRequest.id.desc()).all()

        # 3. คำนวณค่าสถิติ
        total_reqs = len(filtered_requests)
        approved_reqs = [r for r in filtered_requests if getattr(r, 'status', '') == 'Approved']
        pending_reqs = [r for r in filtered_requests if getattr(r, 'status', '') == 'Pending']
        revision_reqs = [r for r in filtered_requests if getattr(r, 'status', '') in ['Needs_Revision', 'Need_Edit']]

        total_approved_credits = sum(getattr(r, 'credits', 0) or 0 for r in approved_reqs)
        approval_rate = round((len(approved_reqs) / total_reqs * 100), 1) if total_reqs > 0 else 0
        unique_students_count = len(set(r.user_id for r in filtered_requests if getattr(r, 'user_id', None)))

        # 4. ดึงข้อมูลรายวิชาและนักศึกษาทั้งหมดสำหรับ Dropdown
        try:
            all_courses = Course.query.order_by(Course.course_code.asc()).all()
        except Exception:
            all_courses = []

        try:
            all_students = User.query.filter_by(role='student').order_by(User.fullname.asc()).all()
            if not all_students:
                all_students = User.query.order_by(User.fullname.asc()).all()
        except Exception:
            all_students = []

        # 5. ข้อมูลสำหรับกราฟ
        status_chart_data = [len(pending_reqs), len(approved_reqs), len(revision_reqs)]

        course_counts = {}
        for r in filtered_requests:
            c_name = getattr(r, 'course_name', 'ไม่ระบุ') or 'ไม่ระบุ'
            course_counts[c_name] = course_counts.get(c_name, 0) + 1
        
        sorted_top_courses = sorted(course_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_course_labels = [tc[0] for tc in sorted_top_courses]
        top_course_values = [tc[1] for tc in sorted_top_courses]

        # 6. แปลงข้อมูลคำร้องเป็น JSON สำหรับ Read-Only Modal และ Export CSV
        requests_data_list = []
        for r in filtered_requests:
            requests_data_list.append({
                'id': r.id,
                'req_code': getattr(r, 'req_code', '') or f'TR{r.id:04d}',
                'student_name': r.user.fullname if getattr(r, 'user', None) else '-',
                'student_code': r.user.member_id if getattr(r, 'user', None) else '-',
                'course_name': getattr(r, 'course_name', '-') or '-',
                'course_code': getattr(r, 'course_code', '-') or '-',
                'credits': getattr(r, 'credits', 0) or 0,
                'institution': getattr(r, 'institution', 'ThaiMOOC') or 'ThaiMOOC',
                'date_submitted': getattr(r, 'date_submitted', '-') or '-',
                'status': getattr(r, 'status', 'Pending') or 'Pending',
                'reject_reason': getattr(r, 'reject_reason', '-') or '-',
                'approved_by': getattr(r, 'approved_by', '-') or '-',
                'doc_img': getattr(r, 'doc_img', '') or '',
                'doc_img2': getattr(r, 'doc_img2', '') or '',
                'doc_img3': getattr(r, 'doc_img3', '') or ''
            })

        requests_json = json.dumps(requests_data_list, ensure_ascii=False)

        # 7. HTML ตัวเลือกรายวิชา นักศึกษา และ ตาราง
        course_options_html = '<option value="ALL">-- เลือกทุกรายวิชา --</option>'
        for c in all_courses:
            is_sel = 'selected' if selected_course == c.course_code else ''
            course_options_html += f'<option value="{escape(c.course_code)}" {is_sel}>{escape(c.course_code)} - {escape(c.course_name)}</option>'

        student_options_html = '<option value="ALL">-- เลือกนักศึกษาทุกคน --</option>'
        for st in all_students:
            is_sel = 'selected' if selected_student == str(st.id) else ''
            st_code = getattr(st, 'member_id', '') or ''
            st_name = getattr(st, 'fullname', '') or ''
            display_label = f"{st_code} - {st_name}" if st_code else st_name
            student_options_html += f'<option value="{st.id}" {is_sel}>{escape(display_label)}</option>'

        table_rows_html = ""
        for r in filtered_requests:
            st_val = getattr(r, 'status', 'Pending')
            if st_val == 'Pending':
                st_badge = '<span class="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1 whitespace-nowrap">⏳ รอดำเนินการ</span>'
            elif st_val == 'Approved':
                st_badge = '<span class="bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1 whitespace-nowrap">✅ อนุมัติแล้ว</span>'
            else:
                st_badge = '<span class="bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-bold px-2.5 py-1 rounded-full inline-flex items-center gap-1 whitespace-nowrap">⚠️ ให้แก้ไข</span>'

            student_name = r.user.fullname if getattr(r, 'user', None) else '-'
            student_code = r.user.member_id if getattr(r, 'user', None) else '-'

            table_rows_html += f"""
            <tr class="hover:bg-slate-50/80 transition border-b border-slate-100 text-xs">
                <td class="py-3.5 px-4 font-mono font-bold text-sky-600 whitespace-nowrap">{escape(getattr(r, 'req_code', f'TR{r.id:04d}') or '')}</td>
                <td class="py-3.5 px-4 font-bold text-slate-800 whitespace-nowrap">{escape(student_name)}<br><span class="text-[10px] text-slate-400 font-normal">({escape(student_code)})</span></td>
                <td class="py-3.5 px-4 font-bold text-slate-700">{escape(getattr(r, 'course_name', '-') or '-')}</td>
                <td class="py-3.5 px-4 text-center font-black text-sky-600 whitespace-nowrap">{getattr(r, 'credits', 0) or 0}</td>
                <td class="py-3.5 px-4 text-center text-slate-500 whitespace-nowrap font-medium">{escape(getattr(r, 'date_submitted', '-') or '-')}</td>
                <td class="py-3.5 px-4 text-center whitespace-nowrap">{st_badge}</td>
                <td class="py-3.5 px-4 text-right whitespace-nowrap">
                    <button onclick="openAnalyticsViewModal({r.id})" class="bg-sky-50 hover:bg-sky-100 text-sky-700 font-bold px-3 py-1.5 rounded-xl border border-sky-200/80 transition inline-flex items-center gap-1 text-xs shadow-sm">
                        <i class="fa-solid fa-eye text-sky-500"></i> ดูรายละเอียด
                    </button>
                </td>
            </tr>
            """

        if not table_rows_html:
            table_rows_html = '<tr><td colspan="7" class="py-12 text-center text-xs font-bold text-slate-400"><i class="fa-solid fa-folder-open text-2xl mb-2 block"></i>ไม่พบข้อมูลคำร้องที่ตรงกับเงื่อนไขการกรอง</td></tr>'

        content = f"""
        <div class="max-w-6xl mx-auto space-y-8">
            <div class="relative overflow-hidden bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl p-8 text-white shadow-xl">
                <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <span class="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs px-3 py-1 rounded-full font-black uppercase tracking-wider">
                            <i class="fa-solid fa-chart-line mr-1"></i> Analytics & Custom Reports
                        </span>
                        <h1 class="text-2xl sm:text-3xl font-black mt-2">รายงานวิเคราะห์สถิติสรุปข้อมูล</h1>
                        <p class="text-xs sm:text-sm text-slate-300 mt-1">สรุปข้อมูลเทียบโอนหน่วยกิตแบบเลือกช่วงเวลา รายวิชา นักศึกษา และสถานะคำร้อง</p>
                    </div>
                </div>
                <div class="absolute -right-10 -bottom-10 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                <div class="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div class="flex items-center gap-2">
                        <div class="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center font-black text-sm">
                            <i class="fa-solid fa-filter"></i>
                        </div>
                        <h3 class="text-sm font-black text-slate-800">ตัวกรองข้อมูลสรุป (Custom Filters)</h3>
                    </div>
                </div>
                
                <form method="GET" action="/admin/analytics" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-1.5">ตั้งแต่วันที่</label>
                        <input type="date" name="start_date" value="{escape(start_date)}" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500 transition">
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-1.5">ถึงวันที่</label>
                        <input type="date" name="end_date" value="{escape(end_date)}" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500 transition">
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-1.5">เลือกรายวิชา</label>
                        <select name="course_code" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500 transition">
                            {course_options_html}
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-1.5">เลือกนักศึกษา</label>
                        <select name="student_id" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500 transition">
                            {student_options_html}
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-black uppercase text-slate-500 mb-1.5">สถานะคำร้อง</label>
                        <select name="status" class="w-full border border-slate-200 rounded-2xl p-3 text-xs font-bold bg-slate-50 outline-none focus:border-indigo-500 transition">
                            <option value="ALL" {'selected' if selected_status=='ALL' or not selected_status else ''}>-- ทุกสถานะ --</option>
                            <option value="Pending" {'selected' if selected_status=='Pending' else ''}>⏳ รอดำเนินการ</option>
                            <option value="Approved" {'selected' if selected_status=='Approved' else ''}>✅ อนุมัติแล้ว</option>
                            <option value="Needs_Revision" {'selected' if selected_status=='Needs_Revision' else ''}>⚠️ ให้แก้ไขหลักฐาน</option>
                        </select>
                    </div>

                    <div class="lg:col-span-5 flex flex-wrap justify-end gap-2 pt-2 border-t border-slate-100">
                        <a href="/admin/analytics" class="bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold px-5 py-2.5 rounded-2xl text-xs transition">
                            ล้างตัวกรอง
                        </a>
                        <button type="button" onclick="exportFilteredCSV()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold px-5 py-2.5 rounded-2xl text-xs shadow-md transition flex items-center gap-2">
                            <i class="fa-solid fa-file-excel"></i> ส่งออกข้อมูล (CSV)
                        </button>
                        <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-6 py-2.5 rounded-2xl text-xs shadow-md transition flex items-center gap-2">
                            <i class="fa-solid fa-magnifying-glass"></i> ประมวลผลรายงาน
                        </button>
                    </div>
                </form>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex items-center justify-between">
                    <div>
                        <p class="text-xs font-black text-slate-400 uppercase tracking-wider">คำร้องตามเงื่อนไข</p>
                        <p class="text-3xl font-black text-slate-800 mt-1">{total_reqs}</p>
                        <p class="text-[11px] font-bold text-slate-400 mt-0.5">รายการทั้งหมด</p>
                    </div>
                    <div class="w-12 h-12 bg-slate-100 text-slate-600 rounded-2xl flex items-center justify-center text-xl font-black">
                        <i class="fa-solid fa-file-lines"></i>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-3xl border border-emerald-100 shadow-sm flex items-center justify-between">
                    <div>
                        <p class="text-xs font-black text-emerald-600 uppercase tracking-wider">หน่วยกิตอนุมัติรวม</p>
                        <p class="text-3xl font-black text-emerald-700 mt-1">{total_approved_credits}</p>
                        <p class="text-[11px] font-bold text-emerald-600 mt-0.5">หน่วยกิตสะสม</p>
                    </div>
                    <div class="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center text-xl font-black">
                        <i class="fa-solid fa-award"></i>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-3xl border border-sky-100 shadow-sm flex items-center justify-between">
                    <div>
                        <p class="text-xs font-black text-sky-600 uppercase tracking-wider">อัตราอนุมัติ (PASS RATE)</p>
                        <p class="text-3xl font-black text-sky-700 mt-1">{approval_rate}%</p>
                        <p class="text-[11px] font-bold text-sky-600 mt-0.5">จากคำร้องช่วงที่เลือก</p>
                    </div>
                    <div class="w-12 h-12 bg-sky-100 text-sky-600 rounded-2xl flex items-center justify-center text-xl font-black">
                        <i class="fa-solid fa-chart-pie"></i>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-3xl border border-indigo-100 shadow-sm flex items-center justify-between">
                    <div>
                        <p class="text-xs font-black text-indigo-600 uppercase tracking-wider">นักศึกษาที่ยื่นเรื่อง</p>
                        <p class="text-3xl font-black text-indigo-700 mt-1">{unique_students_count}</p>
                        <p class="text-[11px] font-bold text-indigo-600 mt-0.5">คน (ไม่ซ้ำรายชื่อ)</p>
                    </div>
                    <div class="w-12 h-12 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center text-xl font-black">
                        <i class="fa-solid fa-users"></i>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
                <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm flex flex-col items-center">
                    <h3 class="text-base font-black text-slate-800 mb-1 w-full text-left">สัดส่วนสถานะคำร้องช่วงที่เลือก</h3>
                    <p class="text-xs text-slate-400 mb-4 w-full text-left">แสดงสัดส่วนภาพรวมกระบวนการพิจารณา</p>
                    <div class="w-56 h-56 relative">
                        <canvas id="analyticsStatusChart"></canvas>
                        <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span class="text-2xl font-black text-slate-800">{total_reqs}</span>
                            <span class="text-[10px] font-bold text-slate-400">คำร้องรวม</span>
                        </div>
                    </div>
                    <div class="flex flex-wrap items-center justify-center gap-3 mt-4 text-[11px] font-bold border-t border-slate-100 pt-3 w-full">
                        <span class="flex items-center gap-1.5 text-amber-600"><span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span> รอตรวจสอบ ({len(pending_reqs)})</span>
                        <span class="flex items-center gap-1.5 text-emerald-600"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> อนุมัติแล้ว ({len(approved_reqs)})</span>
                        <span class="flex items-center gap-1.5 text-indigo-600"><span class="w-2.5 h-2.5 rounded-full bg-indigo-500"></span> ต้องแก้ไข ({len(revision_reqs)})</span>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
                    <h3 class="text-base font-black text-slate-800 mb-1">5 อันดับวิชาที่มีการยื่นคำร้องสูงสุด</h3>
                    <p class="text-xs text-slate-400 mb-4">จำแนกตามจำนวนการยื่นคำร้องในเงื่อนไขที่เลือก</p>
                    <div class="h-64 relative">
                        <canvas id="analyticsTopCourseChart"></canvas>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm space-y-4">
                <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-100 pb-4">
                    <div>
                        <h3 class="text-lg font-black text-slate-800">รายการคำร้องตามตัวกรอง</h3>
                        <p class="text-xs text-slate-400">แสดงผลรวม {total_reqs} รายการ (โหมดดูข้อมูลรายงานอย่างเดียว)</p>
                    </div>
                    <button type="button" onclick="exportFilteredCSV()" class="bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 font-bold px-4 py-2 rounded-xl text-xs transition flex items-center gap-2">
                        <i class="fa-solid fa-file-csv"></i> ส่งออกข้อมูลที่กรองแล้ว (CSV)
                    </button>
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

        <div id="analyticsViewModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4 transition-opacity">
            <div class="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-5 relative border border-slate-100">
                <button onclick="closeAnalyticsModal()" class="absolute top-5 right-5 text-slate-400 hover:text-slate-600 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center transition">
                    <i class="fa-solid fa-xmark"></i>
                </button>

                <div class="flex items-center gap-3 border-b border-slate-100 pb-4">
                    <div class="p-3 bg-indigo-100 text-indigo-600 rounded-2xl"><i class="fa-solid fa-file-invoice text-xl"></i></div>
                    <div>
                        <h3 class="text-base font-black text-slate-800" id="modal_an_course_name">-</h3>
                        <p class="text-xs font-bold text-sky-600" id="modal_an_req_code">-</p>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-3 bg-slate-50 p-4 rounded-2xl text-xs">
                    <div><span class="text-slate-400 font-bold block mb-0.5">นักศึกษา:</span><span id="modal_an_student_name" class="font-bold text-slate-800">-</span></div>
                    <div><span class="text-slate-400 font-bold block mb-0.5">รหัสนักศึกษา:</span><span id="modal_an_student_code" class="font-mono font-bold text-slate-700">-</span></div>
                    <div><span class="text-slate-400 font-bold block mb-0.5">หน่วยกิต:</span><span id="modal_an_credits" class="font-bold text-sky-600">-</span></div>
                    <div><span class="text-slate-400 font-bold block mb-0.5">วันที่ยื่น:</span><span id="modal_an_date" class="font-bold text-slate-700">-</span></div>
                </div>

                <div class="space-y-1.5">
                    <label class="text-xs font-black uppercase text-slate-400">สถานะคำร้อง</label>
                    <div id="modal_an_status_badge"></div>
                    <p id="modal_an_reason_box" class="hidden text-xs text-rose-600 bg-rose-50 p-3 rounded-xl border border-rose-100 font-bold mt-1"></p>
                </div>

                <div class="space-y-1.5">
                    <label class="text-xs font-black uppercase text-slate-400">รูปภาพหลักฐานแนบ</label>
                    <div id="modal_an_images_container" class="grid grid-cols-3 gap-2"></div>
                </div>

                <div class="pt-3 border-t border-slate-100">
                    <button onclick="closeAnalyticsModal()" class="w-full bg-slate-900 hover:bg-black text-white font-bold py-3 rounded-2xl text-xs transition">
                        ปิดหน้าต่าง
                    </button>
                </div>
            </div>
        </div>

        <script>
        let analyticsRequestsData = [];
        try {{
            analyticsRequestsData = {requests_json};
        }} catch (e) {{
            console.error("Parse JSON error:", e);
        }}

        function exportFilteredCSV() {{
            if (!analyticsRequestsData || analyticsRequestsData.length === 0) {{
                alert('ไม่พบข้อมูลคำร้องตามตัวกรองเพื่อส่งออก');
                return;
            }}

            let csvContent = "\\uFEFF";
            csvContent += "รหัสคำร้อง,ชื่อนักศึกษา,รหัสนักศึกษา,ชื่อวิชาที่เทียบโอน,หน่วยกิต,สถาบันผู้จัดหลักสูตร,วันที่ยื่นคำร้อง,สถานะคำร้อง,ผู้พิจารณา/หมายเหตุ\\n";

            analyticsRequestsData.forEach(item => {{
                let stText = 'รอดำเนินการ';
                if (item.status === 'Approved') stText = 'อนุมัติแล้ว';
                else if (item.status === 'Needs_Revision' || item.status === 'Need_Edit') stText = 'ต้องแก้ไข';

                let note = '-';
                if (item.status === 'Approved') note = 'ผู้อนุมัติ: ' + (item.approved_by || 'เจ้าหน้าที่');
                else if (item.status !== 'Pending') note = (item.reject_reason || '-').replace(/"/g, '""');

                let row = [
                    `"${{item.req_code || '-'}}"`,
                    `"${{item.student_name || '-'}}"`,
                    `"${{item.student_code || '-'}}"`,
                    `"${{(item.course_name || '-').replace(/"/g, '""')}}"`,
                    `"${{item.credits || 0}}"`,
                    `"${{item.institution || 'ThaiMOOC'}}"`,
                    `"${{item.date_submitted || '-'}}"`,
                    `"${{stText}}"`,
                    `"${{note}}"`
                ];
                csvContent += row.join(",") + "\\n";
            }});

            const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            const todayStr = new Date().toISOString().slice(0, 10);
            link.setAttribute("href", url);
            link.setAttribute("download", `รายงานสถิติคำร้องเทียบโอน_${{todayStr}}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}

        function openAnalyticsViewModal(id) {{
            const item = analyticsRequestsData.find(r => r.id === id);
            if (!item) return;

            document.getElementById('modal_an_course_name').innerText = item.course_name || '-';
            document.getElementById('modal_an_req_code').innerText = 'รหัสคำร้อง: ' + (item.req_code || '-');
            document.getElementById('modal_an_student_name').innerText = item.student_name || '-';
            document.getElementById('modal_an_student_code').innerText = item.student_code || '-';
            document.getElementById('modal_an_credits').innerText = (item.credits || 0) + ' หน่วยกิต (' + (item.institution || 'ThaiMOOC') + ')';
            document.getElementById('modal_an_date').innerText = item.date_submitted || '-';

            const badgeBox = document.getElementById('modal_an_status_badge');
            const reasonBox = document.getElementById('modal_an_reason_box');

            if (item.status === 'Pending') {{
                badgeBox.innerHTML = `<span class="bg-amber-100 text-amber-800 text-xs font-extrabold px-3 py-1.5 rounded-xl inline-block">⏳ อยู่ระหว่างการตรวจสอบ</span>`;
                reasonBox.classList.add('hidden');
            }} else if (item.status === 'Approved') {{
                badgeBox.innerHTML = `<span class="bg-emerald-100 text-emerald-800 text-xs font-extrabold px-3 py-1.5 rounded-xl inline-block">✅ อนุมัติแล้ว (โดย ${{item.approved_by || 'เจ้าหน้าที่'}})</span>`;
                reasonBox.classList.add('hidden');
            }} else {{
                badgeBox.innerHTML = `<span class="bg-indigo-100 text-indigo-800 text-xs font-extrabold px-3 py-1.5 rounded-xl inline-block">⚠️ ส่งกลับให้แก้ไขหลักฐาน</span>`;
                reasonBox.innerText = 'หมายเหตุข้อผิดพลาด: ' + (item.reject_reason || '-');
                reasonBox.classList.remove('hidden');
            }}

            const imgBox = document.getElementById('modal_an_images_container');
            imgBox.innerHTML = '';
            [item.doc_img, item.doc_img2, item.doc_img3].forEach(img => {{
                if (img) {{
                    imgBox.innerHTML += `<a href="/static/uploads/${{img}}" target="_blank"><img src="/static/uploads/${{img}}" class="h-20 w-full object-cover rounded-xl border border-slate-200 hover:opacity-80 transition"></a>`;
                }}
            }});

            document.getElementById('analyticsViewModal').classList.remove('hidden');
        }}

        function closeAnalyticsModal() {{
            document.getElementById('analyticsViewModal').classList.add('hidden');
        }}

        document.addEventListener("DOMContentLoaded", function() {{
            try {{
                const statusCtx = document.getElementById('analyticsStatusChart').getContext('2d');
                new Chart(statusCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['รอตรวจสอบ', 'อนุมัติแล้ว', 'ต้องแก้ไข'],
                        datasets: [{{
                            data: {json.dumps(status_chart_data)},
                            backgroundColor: ['#f59e0b', '#10b981', '#6366f1'],
                            borderWidth: 0,
                            hoverOffset: 4
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{ legend: {{ display: false }} }},
                        cutout: '75%'
                    }}
                }});
            }} catch(e) {{
                console.error("Status Chart Error:", e);
            }}

            try {{
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
                        layout: {{
                            padding: {{ left: 5, right: 15, top: 5, bottom: 5 }}
                        }},
                        plugins: {{ legend: {{ display: false }} }},
                        scales: {{
                            x: {{ beginAtZero: true, ticks: {{ stepSize: 1, precision: 0 }} }},
                            y: {{
                                ticks: {{
                                    font: {{ family: 'Sarabun', size: 10, weight: 'bold' }},
                                    callback: function(value) {{
                                        const label = this.getLabelForValue(value);
                                        return label.length > 25 ? label.substr(0, 25) + '...' : label;
                                    }}
                                }}
                            }}
                        }}
                    }}
                }});
            }} catch(e) {{
                console.error("Top Course Chart Error:", e);
            }}
        }});
        </script>
        """

        return render_layout(content, active_page='admin_analytics')

    except Exception as e:
        return f"<div style='padding:20px; color:red;'><h3>Analytics Page Error:</h3><p>{escape(str(e))}</p></div>"