import os

class Config:
    DEBUG = True
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'data')
    ALLOWED_EXTENSIONS = {'txt', 'data', 'specmode'}
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = '7dt.observation.broker@gmail.com'  # Replace with your email
    MAIL_PASSWORD = 'cqarlzcofgrsgdlh'  # Use app password for Gmail
    MAIL_DEFAULT_SENDER = ('7DT Observation Alert', '7dt.observation.broker@gmail.com')  # Display name and sender


class ProductionConfig(Config):
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

