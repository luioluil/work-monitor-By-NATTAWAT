from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

db = SQLAlchemy()

class User(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  username = db.Column(db.String(20), unique=True, nullable=False, index=True)
  display_name = db.Column(db.String(80), nullable=False)
  password_hash = db.Column(db.String(255), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  def set_password(self, raw: str): self.password_hash = generate_password_hash(raw)
  def check_password(self, raw: str): return check_password_hash(self.password_hash, raw)

class Project(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(140), nullable=False)
  # kept for backward-compat; not used for derived status anymore
  status = db.Column(db.String(32), default="in_progress")
  join_code = db.Column(db.String(8), unique=True, index=True, default=lambda: secrets.token_urlsafe(6)[:8].upper())
  created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProjectMember(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
  user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
  role = db.Column(db.String(16), default="member")  # owner|member|ba
  joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
  title = db.Column(db.String(200), nullable=False)
  assignee_name = db.Column(db.String(120))
  progress_percent = db.Column(db.Integer, default=0)  # 0..100
  last_updated = db.Column(db.DateTime, default=datetime.utcnow)
  status = db.Column(db.String(32), default="todo")    # todo|doing|done|blocked
  reference_url = db.Column(db.String(500))            # legacy, hidden in UI
  created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class TaskUpdate(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
  author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
  content = db.Column(db.Text, nullable=False)
  progress_percent = db.Column(db.Integer)  # optional
  status = db.Column(db.String(32))         # optional
  created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TaskUpdateLink(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  task_update_id = db.Column(db.Integer, db.ForeignKey('task_update.id'), nullable=False, index=True)
  title = db.Column(db.String(200))
  url = db.Column(db.String(1000), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TaskFile(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, index=True)
  task_update_id = db.Column(db.Integer, db.ForeignKey('task_update.id'))
  file_name = db.Column(db.String(255), nullable=False)
  content_type = db.Column(db.String(120))
  size_bytes = db.Column(db.Integer)
  provider = db.Column(db.String(32), default="cloudinary")
  public_id = db.Column(db.String(255))
  secure_url = db.Column(db.String(1000))
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
