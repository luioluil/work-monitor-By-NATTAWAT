# views_tasks.py
# -*- coding: utf-8 -*-
import cloudinary, cloudinary.uploader
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from datetime import datetime
from models import db, Task, TaskUpdate, TaskFile, TaskUpdateLink, ProjectMember, Task as TaskModel
from utils import current_user, login_required, must_be_project_member, is_cloudinary_delete_enabled, get_env

tasks_bp = Blueprint('tasks', __name__)

# --- Cloudinary config (สำหรับลบไฟล์/อ่านค่า) ---
api_key = get_env("CLOUDINARY_API_KEY")
api_secret = get_env("CLOUDINARY_API_SECRET")
cloud_name = get_env("CLOUDINARY_CLOUD_NAME")
if cloud_name:
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )

# --- Helper ---
def _task_and_membership(task_id):
    t = Task.query.get_or_404(task_id)
    mem = must_be_project_member(t.project_id)
    return t, mem

# --- Create Task ---
@tasks_bp.post('/projects/<int:project_id>/tasks/create')
@login_required
def create_task(project_id):
    must_be_project_member(project_id)
    u = current_user()
    title = (request.form.get('title') or '').strip()
    assignee = (request.form.get('assignee_name') or '').strip()

    if not title:
        flash("กรุณาตั้งชื่องาน", "error")
        return redirect(url_for('main.project_detail', project_id=project_id))

    t = Task(
        project_id=project_id,
        title=title,
        assignee_name=assignee or None,
        created_by_id=u.id,
        status="todo",
        progress_percent=0,
        last_updated=datetime.utcnow()
    )
    db.session.add(t)
    db.session.commit()
    flash("สร้างงานแล้ว ✓", "ok")
    return redirect(url_for('main.project_detail', project_id=project_id))

# --- Task Feed ---
@tasks_bp.get('/tasks/<int:task_id>')
@login_required
def task_feed(task_id):
    t, mem = _task_and_membership(task_id)

    updates = (
        TaskUpdate.query
        .filter_by(task_id=t.id)
        .order_by(TaskUpdate.created_at.desc())
        .all()
    )
    files = (
        TaskFile.query
        .filter_by(task_id=t.id)
        .order_by(TaskFile.created_at.desc())
        .all()
    )

    # ลิงก์ต่ออัปเดต
    links_map = {}
    if updates:
        ids = [u.id for u in updates]
        for l in TaskUpdateLink.query.filter(TaskUpdateLink.task_update_id.in_(ids)).all():
            links_map.setdefault(l.task_update_id, []).append(l)

    # ไฟล์ต่ออัปเดต (ไว้แสดงใต้โพสต์)
    files_by_update = {}
    for f in files:
        if f.task_update_id:
            files_by_update.setdefault(f.task_update_id, []).append(f)

    # ไฟล์ที่ยังไม่ผูกกับโพสต์ (เผื่อแสดง/ย้ายในหน้า)
    loose_files = [f for f in files if not f.task_update_id]

    is_manager = mem.role in ("owner", "ba")

    return render_template(
        'task_feed.html',
        task=t,
        updates=updates,
        files=files,                  # รวมทั้งงาน (เผื่อใช้ที่อื่น)
        links_map=links_map,
        files_by_update=files_by_update,
        loose_files=loose_files,      # <- เพิ่มให้ template ใช้ได้
        is_manager=is_manager,
        cloudinary_cloud_name=get_env("CLOUDINARY_CLOUD_NAME"),
        cloudinary_upload_preset=get_env("CLOUDINARY_UPLOAD_PRESET"),
    )

# --- Create Update ---
@tasks_bp.post('/tasks/<int:task_id>/updates')
@login_required
def create_update(task_id):
    t, mem = _task_and_membership(task_id)
    u = current_user()
    content = (request.form.get('content') or '').strip()
    prog = request.form.get('progress_percent')
    status = request.form.get('status')
    links_text = request.form.get('links') or ''

    if not content:
        flash("กรุณาเขียนรายละเอียดอัปเดต", "error")
        return redirect(url_for('tasks.task_feed', task_id=t.id))

    upd = TaskUpdate(task_id=t.id, author_id=u.id, content=content)

    # อนุญาตเฉพาะ owner/ba ในการปรับ %/สถานะ
    if mem.role in ("owner", "ba"):
        if prog not in (None, ""):
            try:
                pv = max(0, min(100, int(prog)))
                upd.progress_percent = pv
                t.progress_percent = pv
            except Exception:
                pass
        if status and status in ("todo", "doing", "done", "blocked"):
            upd.status = status
            t.status = status

    t.last_updated = datetime.utcnow()
    db.session.add(upd)
    db.session.flush()  # ต้องได้ upd.id เพื่อผูกลิงก์

    # แนบลิงก์ (หนึ่งบรรทัดต่อ 1 ลิงก์)
    for line in links_text.splitlines():
        url = (line or "").strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            db.session.add(TaskUpdateLink(task_update_id=upd.id, url=url))

    db.session.commit()
    flash("โพสต์อัปเดตแล้ว ✓", "ok")
    return redirect(url_for('tasks.task_feed', task_id=t.id))

# --- Register uploaded file (ถูกเรียกหลังอัปโหลด Cloudinary สำเร็จ) ---
@tasks_bp.post('/tasks/<int:task_id>/files/register')
@login_required
def register_uploaded_file(task_id):
    _t, _mem = _task_and_membership(task_id)

    file_name = request.form.get('file_name')
    content_type = request.form.get('content_type')
    size_bytes = int(request.form.get('size_bytes') or 0)
    public_id = request.form.get('public_id')
    secure_url = request.form.get('secure_url')
    task_update_id = request.form.get('task_update_id')  # optional

    allowed_exts = ('.png', '.jpg', '.jpeg', '.pdf', '.docx', '.xlsx')
    if not (file_name and secure_url):
        return {"error": "missing fields"}, 400
    if not file_name.lower().endswith(allowed_exts):
        return {"error": "unsupported file type"}, 400
    if size_bytes > 10 * 1024 * 1024:
        return {"error": "file too large"}, 400

    tf = TaskFile(
        task_id=task_id,
        task_update_id=int(task_update_id) if task_update_id else None,
        file_name=file_name,
        content_type=content_type,
        size_bytes=size_bytes,
        provider="cloudinary",
        public_id=public_id,
        secure_url=secure_url
    )
    db.session.add(tf)
    db.session.commit()
    return {"ok": True, "file_id": tf.id}

# --- Delete file ---
@tasks_bp.post('/tasks/<int:task_id>/files/delete/<int:file_id>')
@login_required
def delete_file(task_id, file_id):
    t, mem = _task_and_membership(task_id)
    f = TaskFile.query.filter_by(id=file_id, task_id=t.id).first_or_404()

    u = current_user()
    owner_task = (t.created_by_id == u.id)
    can = mem.role in ("owner", "ba") or owner_task
    if not can:
        flash("คุณไม่มีสิทธิ์ลบไฟล์นี้", "error")
        return redirect(url_for('tasks.task_feed', task_id=t.id))

    if is_cloudinary_delete_enabled() and f.public_id:
        try:
            cloudinary.uploader.destroy(f.public_id, invalidate=True, resource_type="raw")
        except Exception:
            # ไม่ให้ error จาก Cloudinary ทำให้ flow ล่ม
            pass

    db.session.delete(f)
    db.session.commit()
    flash("ลบไฟล์แล้ว ✓", "ok")
    return redirect(url_for('tasks.task_feed', task_id=t.id))

# --- Change status ---
@tasks_bp.post('/tasks/<int:task_id>/status')
@login_required
def change_status(task_id):
    t, mem = _task_and_membership(task_id)
    if mem.role not in ("owner", "ba"):
        abort(403)

    status = request.form.get('status')
    if status in ("todo", "doing", "done", "blocked"):
        t.status = status
        t.last_updated = datetime.utcnow()
        db.session.add(TaskUpdate(
            task_id=t.id,
            author_id=current_user().id,
            content=f"เปลี่ยนสถานะเป็น {status}",
            status=status
        ))
        db.session.commit()
        flash("อัปเดตสถานะแล้ว ✓", "ok")

    return redirect(url_for('tasks.task_feed', task_id=t.id))

# --- Change progress ---
@tasks_bp.post('/tasks/<int:task_id>/progress')
@login_required
def change_progress(task_id):
    t, mem = _task_and_membership(task_id)
    if mem.role not in ("owner", "ba"):
        abort(403)

    try:
        pv = max(0, min(100, int(request.form.get('progress') or 0)))
    except Exception:
        pv = t.progress_percent

    t.progress_percent = pv
    t.last_updated = datetime.utcnow()
    db.session.add(TaskUpdate(
        task_id=t.id,
        author_id=current_user().id,
        content=f"อัปเดตความคืบหน้าเป็น {pv}%",
        progress_percent=pv
    ))
    db.session.commit()
    flash("อัปเดตเปอร์เซ็นต์แล้ว ✓", "ok")
    return redirect(url_for('tasks.task_feed', task_id=t.id))

# --- Update detail ---
@tasks_bp.get('/updates/<int:update_id>')
@login_required
def update_detail(update_id):
    u = TaskUpdate.query.get_or_404(update_id)
    task = TaskModel.query.get_or_404(u.task_id)
    must_be_project_member(task.project_id)
    links = TaskUpdateLink.query.filter_by(task_update_id=u.id).all()
    files = TaskFile.query.filter_by(task_update_id=u.id).all()
    return render_template('update_detail.html', update=u, links=links, files=files)
