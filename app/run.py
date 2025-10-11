from app import db
from app.models import User, Party, Motie

def init_sample_data():
    """Initialize database with sample data"""
    # Check if data already exists
    if User.query.first() is not None:
        print("Database already contains data, skipping initialization")
        return
    
    print("Initializing database with sample data...")
    
    # Create sample parties
    partijen = [
        Party(naam='VVD', afkorting='VVD', kleur='#0066CC'),
        Party(naam='PvdA', afkorting='PvdA', kleur='#DC143C'),
        Party(naam='CDA', afkorting='CDA', kleur='#00AA44'),
        Party(naam='D66', afkorting='D66', kleur='#00A0D6'),
        Party(naam='GroenLinks', afkorting='GL', kleur='#00AA00'),
        Party(naam='SP', afkorting='SP', kleur='#FF0000'),
        Party(naam='ChristenUnie', afkorting='CU', kleur='#00A0D6'),
        Party(naam='SGP', afkorting='SGP', kleur='#FF8C00'),
    ]
    
    for partij in partijen:
        db.session.add(partij)
    
    db.session.flush()  # Flush to get IDs
    
    # Create sample users
    users = [
        {
            'username': 'admin',
            'email': 'admin@gemeente.nl',
            'naam': 'Test Administrator',
            'password': 'admin123',
            'partij_id': 1  # VVD
        },
        {
            'username': 'pvda_lid',
            'email': 'pvda@gemeente.nl',
            'naam': 'PvdA Raadslid',
            'password': 'pvda123',
            'partij_id': 2  # PvdA
        },
        {
            'username': 'cda_lid',
            'email': 'cda@gemeente.nl',
            'naam': 'CDA Raadslid',
            'password': 'cda123',
            'partij_id': 3  # CDA
        }
    ]
    
    for user_data in users:
        user = User(
            username=user_data['username'],
            email=user_data['email'],
            naam=user_data['naam'],
            partij_id=user_data['partij_id']
        )
        user.set_password(user_data['password'])
        db.session.add(user)
    
    db.session.commit()
    
    print("Sample data created:")
    print("Login credentials:")
    for user_data in users:
        print(f"  {user_data['username']} / {user_data['password']}")

def register_cli(app):
    """Register CLI commands on the given app instance.
    Avoid creating a separate app here to prevent context duplication with Flask CLI.
    """
    @app.cli.command()
    def init_db():
        """Initialize the database."""
        db.create_all()
        init_sample_data()

    @app.cli.command()
    def reset_db():
        """Reset the database."""
        db.drop_all()
        db.create_all()
        init_sample_data()

if __name__ == '__main__':
    # Lazy import to avoid creating a second app when used through Flask CLI
    from app import create_app
    app = create_app()
    register_cli(app)
    with app.app_context():
        db.create_all()
        init_sample_data()
    app.run(debug=True, host='127.0.0.1', port=5000)
