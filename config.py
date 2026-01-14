"""
Configuration for Nicole Web Suite
Automatically uses standalone config for deployment, or parent config for local development
"""

import os
import sys

# Check if we're in standalone deployment mode
# (parent config.py doesn't exist or we're explicitly in production)
_parent_config_path = os.path.join(os.path.dirname(__file__), '..', 'config.py')
_is_standalone = not os.path.exists(_parent_config_path) or os.environ.get('FLASK_ENV') == 'production'

if _is_standalone:
    # Use standalone configuration (for VPS deployment)
    from config_standalone import *
    print("[CONFIG] Using standalone configuration")
else:
    # Try to use parent Discord bot config (for local development)
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from config import *
        print("[CONFIG] Using parent Discord bot configuration")
    except Exception as e:
        # Fallback to standalone if parent config fails
        from config_standalone import *
        print(f"[CONFIG] Parent config failed ({e}), using standalone")


class Config:
    """Flask configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or globals().get('SECRET_KEY', 'dev-secret-key-change-this')
    
    # MongoDB
    MONGODB_URI = globals().get('MONGODB_URI', 'mongodb://localhost:27017/nicole')
    
    # Flask-Login settings
    PERMANENT_SESSION_LIFETIME = 86400 * 7  # 7 days
    
    # Get all API keys from the loaded config
    YOUTUBE_API_KEYS = globals().get('YOUTUBE_API_KEYS', [])
    ANTHROPIC_API_KEY = globals().get('ANTHROPIC_API_KEY')
    OPENAI_API_KEY = globals().get('OPENAI_API_KEY')
    REDIS_URL = globals().get('REDIS_URL', 'redis://localhost:6379')
    
    # Whop
    WHOP_API_KEY = globals().get('WHOP_API_KEY')
    WHOP_CLIENT_ID = globals().get('WHOP_CLIENT_ID')
    WHOP_CLIENT_SECRET = globals().get('WHOP_CLIENT_SECRET')
    WHOP_PRODUCT_ID = globals().get('WHOP_PRODUCT_ID')
    WHOP_BETA_PRODUCT_ID = globals().get('WHOP_BETA_PRODUCT_ID')
    WHOP_PREMIUM_PRODUCT_ID = globals().get('WHOP_PREMIUM_PRODUCT_ID')
    WHOP_ADDITIONAL_GROUP_PRODUCT_ID = globals().get('WHOP_ADDITIONAL_GROUP_PRODUCT_ID')
    
    # Make.com webhooks
    MAKE_SCRIPT_WEBHOOK = globals().get('MAKE_SCRIPT_WEBHOOK')
    MAKE_SERIES_ANALYSIS_WEBHOOK = globals().get('MAKE_SERIES_ANALYSIS_WEBHOOK')
    MAKE_VIDEO_SERIES_WEBHOOK = globals().get('MAKE_VIDEO_SERIES_WEBHOOK')
    MAKE_TITLE_GENERATION_WEBHOOK = globals().get('MAKE_TITLE_GENERATION_WEBHOOK')
    MAKE_PLOT_OUTLINE_WEBHOOK = globals().get('MAKE_PLOT_OUTLINE_WEBHOOK')
    
    # Other
    OWNER_ID = globals().get('OWNER_ID', 0)
    GOOGLE_CREDENTIALS_FILE = globals().get('GOOGLE_CREDENTIALS_FILE')
    FLUX_API_KEY = globals().get('FLUX_API_KEY')
    HUGGINGFACE_TOKEN = globals().get('HUGGINGFACE_TOKEN')
    REPLICATE_API_TOKEN = globals().get('REPLICATE_API_TOKEN')
    ELEVENLABS_API_KEY = globals().get('ELEVENLABS_API_KEY')
    
    # Development settings
    DEBUG = os.environ.get('FLASK_ENV') != 'production'
    TESTING = False
