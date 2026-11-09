from flask import Flask
from flask_mail import Mail
from flask_cors import CORS

mail = Mail()  # Create an instance of Flask-Mail

def create_app():
    app = Flask(__name__, static_folder='../../frontend/build', static_url_path="/static/")
    app.config.from_object('config.Config')
    mail.init_app(app)

    CORS(app, resources={
        r"/too/api/*": {
            "origins": ["https://proton.snu.ac.kr"],
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"],   # 필요한 것만
            "allow_headers": ["Content-Type", "Authorization", "X-CSRF-Token"],
            "supports_credentials": True,
            "max_age": 3600               # preflight 캐시
        }
    })
    # Register routes
    with app.app_context():
        from .routes import api_bp
        app.register_blueprint(api_bp)

    return app
