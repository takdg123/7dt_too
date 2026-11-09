import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    DEBUG = False
    MAIL_DEBUG = False  # with debug on, Flask-Mail wrote the SMTP AUTH line into too_backend.log
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(32).hex())  # For session management
    # SESSION_COOKIE_SECURE: Set based on environment (True for HTTPS, False for HTTP in dev)
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") != "development"  # Only send cookies over HTTPS in production
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'data')
    ALLOWED_EXTENSIONS = {'txt', 'data', 'specmode'}
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv("SDT_MAIL")
    MAIL_PASSWORD = os.getenv("SDT_PASSWORD")
    MAIL_DEFAULT_SENDER = ('7DT Observation Alert', os.getenv("SDT_SENDER")) 

class ProductionConfig(Config):
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

