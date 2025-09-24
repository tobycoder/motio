import os
from datetime import timedelta
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))
BASEDIR = Path(__file__).resolve().parent

def _normalize_db_url(url: str | None) -> str | None:
    if not url:
        return None
    # Railway/Heroku-style short forms -> add driver explicitly
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)  # psycopg2
    elif url.startswith("postgresql://") and "+psycopg" not in url and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)  # or +psycopg if you use psycopg3
    return url


class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-!!!!'
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'dev-secret-key-change-in-production-!!!!'
    ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

    # Database

    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_ECHO = False  # Set to True to see SQL queries in development
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Flask-WTF CSRF
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False  # Set to True in production with HTTPS
    
    # File uploads (for future use)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Mail settings (for future use)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS','false').lower() in ['true','on','1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL','false').lower() in ['true','on','1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')

    
    # Application settings
    APP_NAME = 'Motio'
    GEMEENTE_NAAM = os.environ.get('GEMEENTE_NAAM') or '[GEMEENTE NAAM]'

    # Config logo upload
    LOGO_UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'img', 'partijen')
    ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg'}
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB bijvoorbeeld

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Set to True to see all SQL queries

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}