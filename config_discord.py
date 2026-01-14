import os
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from anthropic import Anthropic
import logging
from logging.handlers import RotatingFileHandler
import colorlog
import sys
import requests
from google.cloud import vision
from google.oauth2 import service_account
load_dotenv()

# Create custom formatter for different log levels
def setup_logger():
    logger = logging.getLogger('nicole_bot')
    logger.setLevel(logging.INFO)

    # Define a more cyberpunk color scheme
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s[NICOLE]%(reset)s %(bold_white)s%(message)s %(reset)s%(bold_blue)s[%(asctime)s]%(reset)s",
        datefmt="%H:%M:%S",
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'bold_green',
            'WARNING':  'bold_yellow',
            'ERROR':    'bold_red',
            'CRITICAL': 'bold_red,bg_white',
        },
        secondary_log_colors={
            'message': {
                'DEBUG':    'cyan',
                'INFO':     'bold_green',
                'WARNING':  'bold_yellow',
                'ERROR':    'bold_red',
                'CRITICAL': 'bold_red'
            }
        },
        style='%'
    )

    # Console handler with cyberpunk styling
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File handler (keeping it simple for log files)
    file_handler = RotatingFileHandler(
        'logs/nicole_bot.log', 
        maxBytes=10000000, 
        backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter('[NICOLE] %(message)s [%(asctime)s]')
    )

    logger.handlers = []
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Silence noisy modules
    for log_name in ['discord', 'websockets', 'asyncio', 'aiohttp']:
        logging.getLogger(log_name).setLevel(logging.WARNING)

    return logger

logger = setup_logger()

# Load all environment variables first
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
YOUTUBE_API_KEYS = os.getenv('YOUTUBE_API_KEYS').split(',')

try:
    YOUTUBE_API_KEYS = json.loads(os.getenv('YOUTUBE_API_KEYS', '[]'))
    if not YOUTUBE_API_KEYS:
        raise ValueError("No YouTube API keys available")
except json.JSONDecodeError:
    # If JSON parsing fails, try splitting by comma
    YOUTUBE_API_KEYS = [key.strip() for key in os.getenv('YOUTUBE_API_KEYS', '').split(',') if key.strip()]


MONGODB_URI = os.getenv('MONGODB_URI')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
WHOP_API_KEY = os.getenv('WHOP_API_KEY')
WHOP_CLIENT_ID = os.getenv('WHOP_CLIENT_ID')
WHOP_CLIENT_SECRET = os.getenv('WHOP_CLIENT_SECRET')
WHOP_PRODUCT_ID = os.getenv('WHOP_PRODUCT_ID')
WHOP_API_BASE_URL = "https://api.whop.com"
MAKE_SCRIPT_WEBHOOK = os.getenv('MAKE_SCRIPT_WEBHOOK')
MAKE_SERIES_ANALYSIS_WEBHOOK = os.getenv('MAKE_SERIES_ANALYSIS_WEBHOOK')
MAKE_VIDEO_SERIES_WEBHOOK = os.getenv('MAKE_VIDEO_SERIES_WEBHOOK')
MAKE_TITLE_GENERATION_WEBHOOK = os.getenv('MAKE_TITLE_GENERATION_WEBHOOK')
MAKE_PLOT_OUTLINE_WEBHOOK = os.getenv('MAKE_PLOT_OUTLINE_WEBHOOK')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
GOOGLE_CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'googlecred', 'google_credentials.json')
FLUX_API_KEY = os.getenv('FLUX_API_KEY')

# Add with other environment variables
HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')
WHOP_BETA_PRODUCT_ID = os.getenv('WHOP_BETA_PRODUCT_ID')
WHOP_PREMIUM_PRODUCT_ID = os.getenv('WHOP_PREMIUM_PRODUCT_ID')
WHOP_ADDITIONAL_GROUP_PRODUCT_ID = os.getenv('WHOP_ADDITIONAL_GROUP_PRODUCT_ID')

# Add to required_vars list
required_vars = [
    'DISCORD_TOKEN',
    'MONGODB_URI',
    'ANTHROPIC_API_KEY',
    'WHOP_API_KEY',
    'WHOP_CLIENT_ID',
    'WHOP_CLIENT_SECRET',
    'WHOP_PRODUCT_ID',
    'MAKE_SCRIPT_WEBHOOK',
    'MAKE_SERIES_ANALYSIS_WEBHOOK',
    'MAKE_VIDEO_SERIES_WEBHOOK',
    'MAKE_TITLE_GENERATION_WEBHOOK',
    'MAKE_PLOT_OUTLINE_WEBHOOK',
    'OWNER_ID',
    'REDIS_URL',
    'GOOGLE_CREDENTIALS_FILE',
    'HUGGINGFACE_TOKEN',
    'WHOP_BETA_PRODUCT_ID',
    'WHOP_PREMIUM_PRODUCT_ID',
    'WHOP_ADDITIONAL_GROUP_PRODUCT_ID'
]

for var in required_vars:
    if not globals()[var]:
        raise EnvironmentError(f"{var} is not set in the environment variables.")

# YouTube API setup
if YOUTUBE_API_KEYS:
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEYS[0])
else:
    logger.error("No YouTube API keys available. YouTube functionality will be limited.")
    youtube = None

# Anthropic setup
CLAUDE_API_KEY = ANTHROPIC_API_KEY
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
try:
    anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
    
except Exception as e:
    print(f"⚠️ Warning: Could not initialize Anthropic client: {e}")
    anthropic = None

OWNER_ID = int(OWNER_ID) if OWNER_ID else None  # Convert to integer if it exists

MAX_GROUPS_PER_MONTH = 5  # or whatever number you want to set as the maximum

# Load Google Cloud Vision credentials
GOOGLE_APPLICATION_CREDENTIALS = os.path.join(
    os.path.dirname(__file__), 
    'googlecred', 
    'service_account.json'
)
vision_credentials = service_account.Credentials.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS)
vision_client = vision.ImageAnnotatorClient(credentials=vision_credentials)

# Load Replicate API Key
REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN')
if not REPLICATE_API_TOKEN:
    raise EnvironmentError("REPLICATE_API_TOKEN is not set in the environment variables.")

# Set the environment variable for the Replicate client
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
# ... rest of your configurations ...
