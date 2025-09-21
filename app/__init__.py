# motie_tool/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from .config import Config

# Initialiseer extensions
db = SQLAlchemy()
#login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialiseer extensions met app
    db.init_app(app)
    migrate = Migrate(app, db)
    #login_manager.init_app(app)
    #login_manager.login_view = 'app.login'
    #login_manager.login_message = 'Log in om toegang te krijgen tot deze pagina.'
    
    # Importeer models
    from .models import User, Party, Motie
    
    # User loader voor Flask-Login
    #@login_manager.user_loader
    #def load_user(user_id):
        #return User.query.get(int(user_id))
    
    # Registreer blueprints
    from .moties import bp as moties_bp
    app.register_blueprint(moties_bp, url_prefix='/moties')
        
    from .amendementen import bp as amendementen_bp
    app.register_blueprint(amendementen_bp, url_prefix='/amendementen')

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .gebruikers import bp as gebruikers_bp
    app.register_blueprint(gebruikers_bp, url_prefix='/gebruikers')

    from .help import bp as help_bp
    app.register_blueprint(help_bp, url_prefix='/help')

    from .partijen import bp as partijen_bp
    app.register_blueprint(partijen_bp, url_prefix='/partijen')

    from .profiel import bp as profielen_bp
    app.register_blueprint(profielen_bp, url_prefix='/profiel')

    from .dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .front import bp as front_bp
    app.register_blueprint(front_bp, url_prefix='/front')
    
    return app

# Voor backwards compatibility
app = create_app()
