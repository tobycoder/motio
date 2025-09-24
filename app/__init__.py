from dotenv import load_dotenv
load_dotenv()

# motie_tool/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from .config import Config
from flask_mail import Mail, Message
import smtplib, logging


# Initialiseer extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
PUBLIC_ENDPOINTS = {
    "auth.login", "auth.register", "auth.logout",  # wat jij openbaar wilt
    "main.index",                                  # bijv. homepage
    "health.ping",                                 # healthcheck
    "static",                                      # nodig voor /static/*
}


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialiseer extensions met app
    db.init_app(app)
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Log in om toegang te krijgen tot deze pagina.'
    
    mail.init_app(app)
    # Importeer models
    from .models import User, Party, Motie
    from .auth.roles import user_has_role
    # User loader voor Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    @app.context_processor
    def inject_role_helpers():
        return dict(user_has_role=user_has_role)

    # Registreer blueprints
    from .moties import bp as moties_bp
    app.register_blueprint(moties_bp, url_prefix='/moties')
        
    from .amendementen import bp as amendementen_bp
    app.register_blueprint(amendementen_bp, url_prefix='/amendementen')

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .gebruikers import bp as gebruikers_bp
    app.register_blueprint(gebruikers_bp, url_prefix='/gebruikers')

    from .partijen import bp as partijen_bp
    app.register_blueprint(partijen_bp, url_prefix='/partijen')

    from .profiel import bp as profielen_bp
    app.register_blueprint(profielen_bp, url_prefix='/profiel')

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/instellingen')

    @app.route("/diag/mail")
    def diag_mail():
        app.logger.setLevel(logging.INFO)
        # zet SMTP debug
        mail.state = getattr(mail, "state", None)
        try:
            # raw smtplib debug
            s = smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"], timeout=20)
            if app.config.get("MAIL_USE_TLS"):
                s.starttls()
            s.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            s.quit()
            # flask-mail test
            msg = Message("Diag mail", recipients=[app.config.get("MAIL_USERNAME")])
            msg.body = "Het werkt 🎉"
            mail.send(msg)
            return "OK: smtp + flask-mail", 200
        except Exception as e:
            app.logger.exception("SMTP/Flask-Mail faalde")
            return f"MAIL ERROR: {e}", 500    

    return app

# Voor backwards compatibility
app = create_app()

