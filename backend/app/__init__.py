from flask import Flask
from flask_mail import Mail
from flask_cors import CORS
import os

mail = Mail()  # Create an instance of Flask-Mail

def create_app():
    app = Flask(__name__, static_folder='../../frontend/build')
    app.config.from_object('config.Config')
    mail.init_app(app)

    CORS(app, resources={r"/*": {"origins": "https://trusted-domain.com"}})
    # Register routes
    with app.app_context():
        from .routes import api_bp
        app.register_blueprint(api_bp)

    return app
