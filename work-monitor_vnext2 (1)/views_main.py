from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy import func
from models import db, Project, ProjectMember, Task, TaskFile, TaskUpdate, TaskUpdateLink
from utils import current_user, login_required, must_be_project_member, is_cloudinary_delete_enabled
import cloudinary, cloudinary.uploader

main_bp = Blueprint('main', __name__)

@main_bp.get('/')
def root():
    return redirect(url_for('main.projects'))

def derive_project_status(task_statuses):
    if not task_statuses:
        return 'in_progress'
    # task_statuses is list like ['todo','done',...]
    all_done = all(s == 'done' for s in task_statuses)
    any_blocked = any(s == 'blocked' for s in task_statuses)
    any_doing = any(s == 'doing' for s in task_statuses)
    if all_done:
        return 'done'
    if any_blocked and not any_doing:
        return 'blocked'
    return 'in_progress'

@main_bp.get('/projects')
@login_required
def projects():
    u = current_user()
    # projects the user is member of
    proj_rows = db.session.query(Project).join(ProjectMember, Project.id==ProjectMember.project_id)         .filter(ProjectMember.user_id==u.id).order_by(Project.created_at.desc()).all()

    # map project -> role for the current user
    roles = dict(db.session.query(ProjectMember.project_id, ProjectMember.role)                 .filter(ProjectMember.user_id==u.id).all())

    # collect task statuses per project
    pids = [p.id for p in proj_rows] or [-1]
    task_rows = db.session.query(Task.project_id, Task.status)                .filter(Task.project_id.in_(pids)).all()
    task_map = {}
    for pid, st in task_rows:
        task_map.setdefault(pid, []).append(st)

    # derive project status and counts
    proj_status = {p.id: derive_project_status(task_map.get(p.id, [])) for p in proj_rows}
    done = sum(1 for pid,s in proj_status.items() if s=='done')
    inprog = sum(1 for pid,s in proj_status.items() if s=='in_progress')
    blocked = sum(1 for pid,s in proj_status.items() if s=='blocked')
    total = len(proj_rows)

    # member counts per project
    member_counts = dict(db.session.query(ProjectMember.project_id, func.count(ProjectMember.id))                         .filter(ProjectMember.project_id.in_(pids)).group_by(ProjectMember.project_id).all())

    return render_template('projects.html',
                           projects=proj_rows, counts=member_counts,
                           total=total, done=done, inprog=inprog, blocked=blocked,
                           roles=roles, proj_status=proj_status)

@main_bp.post('/projects/create')
@login_required
def create_project():
    u = current_user()
    name = (request.form.get('name') or '').strip()
    if not name:
        flash("ตั้งชื่อโปรเจ็กต์ก่อนน้า", "error")
        return redirect(url_for('main.projects'))
    p = Project(name=name, created_by_id=u.id)
    db.session.add(p); db.session.flush()
    db.session.add(ProjectMember(project_id=p.id, user_id=u.id, role="owner"))
    db.session.commit()
    return redirect(url_for('main.project_detail', project_id=p.id))

@main_bp.post('/projects/join')
@login_required
def join_project():
    code = (request.form.get('join_code') or '').strip().upper()
    p = Project.query.filter_by(join_code=code).first()
    if not p:
        flash("ไม่พบโปรเจ็กต์จากโค้ดนี้", "error")
        return redirect(url_for('main.projects'))
    u = current_user()
    if not ProjectMember.query.filter_by(project_id=p.id, user_id=u.id).first():
        db.session.add(ProjectMember(project_id=p.id, user_id=u.id))
        db.session.commit()
    return redirect(url_for('main.project_detail', project_id=p.id))

@main_bp.post('/projects/<int:project_id>/delete')
@login_required
def delete_project(project_id):
    # only owner can delete
    mem = must_be_project_member(project_id)
    if mem.role != 'owner': abort(403)
    # Cascade delete: files -> updates/links -> tasks -> members -> project
    # delete cloud files if keys provided
    files = TaskFile.query.join(Task, Task.id==TaskFile.task_id)            .filter(Task.project_id==project_id).all()
    if is_cloudinary_delete_enabled():
        for f in files:
            try:
                if f.public_id:
                    cloudinary.uploader.destroy(f.public_id, invalidate=True, resource_type="raw")
            except Exception:
                pass
    for f in files: db.session.delete(f)

    updates = TaskUpdate.query.join(Task, Task.id==TaskUpdate.task_id)              .filter(Task.project_id==project_id).all()
    for urow in updates: db.session.delete(urow)

    links = TaskUpdateLink.query.join(TaskUpdate, TaskUpdate.id==TaskUpdateLink.task_update_id)            .join(Task, Task.id==TaskUpdate.task_id).filter(Task.project_id==project_id).all()
    for l in links: db.session.delete(l)

    tasks = Task.query.filter_by(project_id=project_id).all()
    for t in tasks: db.session.delete(t)

    members = ProjectMember.query.filter_by(project_id=project_id).all()
    for m in members: db.session.delete(m)

    p = Project.query.get_or_404(project_id)
    db.session.delete(p)
    db.session.commit()
    flash("ลบโปรเจกต์และข้อมูลทั้งหมดแล้ว ✓", "ok")
    return redirect(url_for('main.projects'))

@main_bp.post('/projects/<int:project_id>/leave')
@login_required
def leave_project(project_id):
    # non-owner can leave; owner not allowed (ต้องลบเท่านั้น)
    u = current_user()
    mem = ProjectMember.query.filter_by(project_id=project_id, user_id=u.id).first_or_404()
    if mem.role == 'owner':
        flash("Owner ต้องใช้ปุ่ม 'ลบโปรเจกต์' เท่านั้น", "error")
        return redirect(url_for('main.projects'))
    db.session.delete(mem); db.session.commit()
    flash("ออกจากโปรเจกต์แล้ว ✓", "ok")
    return redirect(url_for('main.projects'))

@main_bp.get('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    mem = must_be_project_member(project_id)
    p = Project.query.get_or_404(project_id)
    tasks = Task.query.filter_by(project_id=p.id).order_by(Task.last_updated.desc()).all()
    members = ProjectMember.query.filter_by(project_id=p.id).all()
    is_manager = mem.role in ('owner','ba')
    return render_template('project_detail.html',
                           project=p, tasks=tasks, members=members,
                           is_manager=is_manager,
                           invite_link=url_for('main.create_invite', project_id=p.id))

@main_bp.get('/projects/<int:project_id>/invite')
@login_required
def create_invite(project_id):
    must_be_project_member(project_id)
    p = Project.query.get_or_404(project_id)
    return render_template('invite.html', project=p)
