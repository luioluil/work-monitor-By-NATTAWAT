from flask import Flask
from models import db
from views_auth import auth_bp
from views_main import main_bp
from views_tasks import tasks_bp
from utils import get_env
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = get_env('SECRET_KEY', 'dev-change-this')
    app.config['SQLALCHEMY_DATABASE_URI'] = get_env('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(tasks_bp)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
