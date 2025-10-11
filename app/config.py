import os
from datetime import timedelta
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))
BASEDIR = Path(__file__).resolve().parent


def _normalize_db_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "+psycopg2" in url:
        url = url.replace("+psycopg2", "+psycopg")
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    # Security
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production-!!!!"
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT") or "dev-secret-key-change-in-production-!!!!"
    ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}

    # Database
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    # Be defensive against stale/broken connections and long connect waits
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        # Psycopg connect timeout in seconds (avoid worker timeouts on dead DB)
        "connect_args": {"connect_timeout": 3},
    }

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Flask-WTF CSRF
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False

    # File uploads (for future use)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Resend mail settings
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY") or "re_iZf4AQE7_AxfsmPZAykJkSN9i8pPYVH8v"
    RESEND_DEFAULT_FROM = os.environ.get("RESEND_DEFAULT_FROM") or "no-reply@motio.tech"

    # Application settings
    APP_NAME = "Motio"
    GEMEENTE_NAAM = os.environ.get("GEMEENTE_NAAM") or "[GEMEENTE NAAM]"

    # Config logo upload
    LOGO_UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "img", "partijen")
    ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_SSL_STRICT = True


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
