import os, re
from functools import wraps
from flask import session, redirect, url_for, abort
from models import User, ProjectMember

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")

def current_user():
    uid = session.get('uid')
    if not uid: return None
    return User.query.get(uid)

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for('auth.login_page'))
        return f(*a, **kw)
    return wrapper

def must_be_project_member(project_id):
    u = current_user()
    if not u: return abort(401)
    mem = ProjectMember.query.filter_by(project_id=project_id, user_id=u.id).first()
    if not mem: return abort(403)
    return mem

def is_allowed_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username or ""))

def get_env(name: str, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "", "None") else default

def is_cloudinary_delete_enabled():
    return bool(get_env("CLOUDINARY_API_KEY") and get_env("CLOUDINARY_API_SECRET"))
