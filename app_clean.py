"""
Clean Flask application factory for Nicole Web Suite
"""

from flask import Flask, redirect, url_for
from flask_login import LoginManager
import os

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Setup clean logging first
    from core.logger import NicoleLogger
    NicoleLogger.setup()
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['DEBUG'] = True
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        try:
            from core.auth import load_user as auth_load_user
            return auth_load_user(user_id)
        except Exception:
            return None
    
    # Initialize database (silent)
    try:
        from core.database import init_db
        init_db(app)
    except Exception as e:
        print(f"❌ Database failed: {e}")
    
    # Register blueprints (silent)
    try:
        from dashboard.routes import dashboard_bp
        app.register_blueprint(dashboard_bp)
        
        from dashboard.content_studio_routes import content_studio_bp
        app.register_blueprint(content_studio_bp, url_prefix='/studio-api')
        
        from core.auth import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
        
    except Exception as e:
        print(f"❌ Blueprint failed: {e}")
    
    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.main'))
    
    return app
