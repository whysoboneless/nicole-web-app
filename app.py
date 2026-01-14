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
        print(f"[ERROR] Database failed: {e}")
    
    # Initialize API key middleware
    try:
        from core.user_api_middleware import patch_api_clients
        patch_api_clients()
    except Exception as e:
        print(f"[ERROR] API middleware failed: {e}")
    
    # Register blueprints (silent)
    try:
        from dashboard.routes import dashboard_bp
        app.register_blueprint(dashboard_bp)
        
        from dashboard.content_studio_routes import content_studio_bp
        app.register_blueprint(content_studio_bp, url_prefix='/studio-api')
        
        from dashboard.content_style_routes import content_style_bp
        app.register_blueprint(content_style_bp)
        
        from core.auth import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/auth')
        
        from dashboard.admin_routes import admin_bp
        app.register_blueprint(admin_bp)
        
        from dashboard.campaign_routes import campaign_bp
        app.register_blueprint(campaign_bp)
        
        from dashboard.product_routes import product_bp
        app.register_blueprint(product_bp)
        
    except Exception as e:
        print(f"[ERROR] Blueprint failed: {e}")
    
    # Start UGC Production Worker
    try:
        import threading
        from workers.ugc_production_worker import run_ugc_scheduler
        
        def start_ugc_worker():
            import asyncio
            asyncio.run(run_ugc_scheduler())
        
        ugc_thread = threading.Thread(target=start_ugc_worker, daemon=True)
        ugc_thread.start()
        print("[OK] UGC Production Worker started")
    except Exception as e:
        print(f"[WARN] UGC Worker failed to start: {e}")
    
    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.main'))
    
    # Health check endpoint for nginx/monitoring
    @app.route('/health')
    def health():
        return {'status': 'healthy', 'app': 'nicole-web-suite'}, 200
    
    return app
