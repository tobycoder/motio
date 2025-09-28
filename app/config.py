import os
from datetime import timedelta
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))
BASEDIR = Path(__file__).resolve().parent

def _db_uri_from_env() -> str:
    uri = os.getenv("DATABASE_URL", "sqlite:///motio.db")  # lokale fallback
    # Railway/Postgres kan nog 'postgres://' geven; SQLAlchemy wil 'postgresql+psycopg2://'
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
    # Sommige hosts verwachten TLS; als je connectieproblemen krijgt, forceer SSL:
    if uri.startswith("postgresql") and "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"
    return uri


class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-!!!!'
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'dev-secret-key-change-in-production-!!!!'
    ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

    # Database
    _env_url = (os.getenv("DATABASE_URL")
                or os.getenv("RAILWAY_DATABASE_URL")
                or os.getenv("POSTGRES_URL")  # fallback, just in case
                )

    SQLALCHEMY_DATABASE_URI = _db_uri_from_env()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
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