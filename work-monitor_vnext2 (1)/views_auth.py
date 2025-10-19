from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User
from utils import is_allowed_username

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.get('/login')
def login_page():
    return render_template('auth_login.html')

@auth_bp.post('/login')
def login_post():
    username = (request.form.get('username') or '').strip().lower()
    password = request.form.get('password') or ''
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
        return redirect(url_for('auth.login_page'))
    session['uid'] = u.id
    return redirect(url_for('main.projects'))

@auth_bp.get('/register')
def register_page():
    return render_template('auth_register.html')

@auth_bp.post('/register')
def register_post():
    username = (request.form.get('username') or '').strip().lower()
    display_name = (request.form.get('display_name') or '').strip()
    password = request.form.get('password') or ''
    if not is_allowed_username(username):
        flash("รูปแบบชื่อผู้ใช้ไม่ถูกต้อง (a-z, 0-9, _ ยาว 3-20 ตัว)", "error")
        return redirect(url_for('auth.register_page'))
    if len(password) < 8:
        flash("รหัสผ่านต้องอย่างน้อย 8 ตัว", "error")
        return redirect(url_for('auth.register_page'))
    if User.query.filter_by(username=username).first():
        flash("ชื่อผู้ใช้นี้ถูกใช้แล้ว", "error")
        return redirect(url_for('auth.register_page'))
    u = User(username=username, display_name=display_name)
    u.set_password(password)
    db.session.add(u); db.session.commit()
    session['uid'] = u.id
    return redirect(url_for('main.projects'))

@auth_bp.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login_page'))
