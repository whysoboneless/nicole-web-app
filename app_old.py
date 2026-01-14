"""
Flask application factory for Nicole Web Suite
"""

from flask import Flask, redirect, url_for
from flask_login import LoginManager
import os
import logging
from core.logger import NicoleLogger

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Setup clean logging first
    NicoleLogger.setup()
    
    # Basic configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['DEBUG'] = True
    
    # Clean logging setup - no startup spam
    logging.basicConfig(level=logging.WARNING)  # Only show warnings and errors
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'  # Use real auth login route
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        try:
            from core.auth import load_user as auth_load_user
            return auth_load_user(user_id)
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {e}")
            return None
    
    # Initialize database
    try:
        from core.database import init_db
        init_db(app)
    except Exception as e:
        print(f"❌ Database failed: {e}")
    
    # Register blueprints
    try:
        from dashboard.routes import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("✅ Dashboard blueprint registered")
        
        from dashboard.content_studio_routes import content_studio_bp
        app.register_blueprint(content_studio_bp, url_prefix='/studio-api')
        logger.info("✅ Content Studio blueprint registered")
        
        # Register auth blueprint
        from core.auth import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
        logger.info("✅ Auth blueprint registered")
        
    except Exception as e:
        logger.error(f"❌ Blueprint registration failed: {e}")
    
    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.main'))
    
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return "Page not found", 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return "Internal server error", 500
    
    logger.info("✅ Nicole AI Web Suite initialized successfully")
    return app
