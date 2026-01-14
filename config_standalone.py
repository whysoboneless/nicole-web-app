"""
Standalone configuration for Nicole Web Suite
This replaces the dependency on the parent config.py for deployment
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# Logging Setup
# =============================================================================

def setup_logger():
    """Set up application logger"""
    logger = logging.getLogger('nicole_bot')
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[NICOLE] %(message)s [%(asctime)s]', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

logger = setup_logger()

# =============================================================================
# Core Configuration
# =============================================================================

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
DEBUG = FLASK_ENV != 'production'

# =============================================================================
# Database
# =============================================================================

MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/niche_research')

# =============================================================================
# AI APIs
# =============================================================================

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY')
PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY')

# =============================================================================
# YouTube API
# =============================================================================

# Support both JSON array and comma-separated formats
import json
_youtube_keys_raw = os.environ.get('YOUTUBE_API_KEYS', os.environ.get('YOUTUBE_API_KEY', ''))
try:
    YOUTUBE_API_KEYS = json.loads(_youtube_keys_raw) if _youtube_keys_raw.startswith('[') else []
except:
    YOUTUBE_API_KEYS = []

if not YOUTUBE_API_KEYS and _youtube_keys_raw:
    YOUTUBE_API_KEYS = [k.strip() for k in _youtube_keys_raw.split(',') if k.strip()]

# =============================================================================
# Redis (Optional - for caching)
# =============================================================================

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

# =============================================================================
# Whop Integration (Optional - for payments)
# =============================================================================

WHOP_API_KEY = os.environ.get('WHOP_API_KEY')
WHOP_CLIENT_ID = os.environ.get('WHOP_CLIENT_ID')
WHOP_CLIENT_SECRET = os.environ.get('WHOP_CLIENT_SECRET')
WHOP_PRODUCT_ID = os.environ.get('WHOP_PRODUCT_ID')
WHOP_BETA_PRODUCT_ID = os.environ.get('WHOP_BETA_PRODUCT_ID')
WHOP_PREMIUM_PRODUCT_ID = os.environ.get('WHOP_PREMIUM_PRODUCT_ID')
WHOP_ADDITIONAL_GROUP_PRODUCT_ID = os.environ.get('WHOP_ADDITIONAL_GROUP_PRODUCT_ID')
WHOP_API_BASE_URL = "https://api.whop.com"

# =============================================================================
# Make.com Webhooks (Optional - for automation)
# =============================================================================

MAKE_SCRIPT_WEBHOOK = os.environ.get('MAKE_SCRIPT_WEBHOOK')
MAKE_SERIES_ANALYSIS_WEBHOOK = os.environ.get('MAKE_SERIES_ANALYSIS_WEBHOOK')
MAKE_VIDEO_SERIES_WEBHOOK = os.environ.get('MAKE_VIDEO_SERIES_WEBHOOK')
MAKE_TITLE_GENERATION_WEBHOOK = os.environ.get('MAKE_TITLE_GENERATION_WEBHOOK')
MAKE_PLOT_OUTLINE_WEBHOOK = os.environ.get('MAKE_PLOT_OUTLINE_WEBHOOK')

# =============================================================================
# Discord OAuth (Required for login)
# =============================================================================

DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.environ.get('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.environ.get('DISCORD_REDIRECT_URI', 'http://127.0.0.1:5000/auth/discord/callback')
OWNER_DISCORD_ID = os.environ.get('OWNER_DISCORD_ID', '528049173178875924')
OWNER_ID = int(os.environ.get('OWNER_ID', '0'))

# Discord Bot (Optional)
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

# =============================================================================
# Google Services
# =============================================================================

GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE')

# =============================================================================
# Image/Video Generation
# =============================================================================

FLUX_API_KEY = os.environ.get('FLUX_API_KEY')
HUGGINGFACE_TOKEN = os.environ.get('HUGGINGFACE_TOKEN')

# Sora API
SORA_API_KEY = os.environ.get('SORA_API_KEY')
SORA_API_URL = 'https://defapi.org/model/openai/sora-2'

# =============================================================================
# Application Limits
# =============================================================================

MAX_GROUPS_PER_MONTH = 5

# =============================================================================
# Flask-Login Settings
# =============================================================================

PERMANENT_SESSION_LIFETIME = 86400 * 7  # 7 days

# =============================================================================
# Initialize API Clients (lazy initialization to avoid import errors)
# =============================================================================

# Anthropic client
anthropic = None
try:
    if ANTHROPIC_API_KEY:
        from anthropic import Anthropic
        anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
except ImportError:
    pass

# YouTube client
youtube = None
try:
    if YOUTUBE_API_KEYS:
        from googleapiclient.discovery import build
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEYS[0])
except ImportError:
    pass

# Vision client (optional - requires google-cloud-vision)
vision_client = None
try:
    _google_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if _google_creds and os.path.exists(_google_creds):
        from google.cloud import vision
        from google.oauth2 import service_account
        vision_credentials = service_account.Credentials.from_service_account_file(_google_creds)
        vision_client = vision.ImageAnnotatorClient(credentials=vision_credentials)
except ImportError:
    pass
except Exception:
    pass
