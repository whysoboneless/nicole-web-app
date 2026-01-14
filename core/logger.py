"""
Clean, organized logging system for Nicole AI Web Suite
No fluff, no drama, just essential information
"""

import logging
import sys
from datetime import datetime

class CleanFormatter(logging.Formatter):
    """Clean, hacker-style formatter with minimal noise"""
    
    # Color codes for terminal output
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green  
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        # Get timestamp in clean format
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Get color for log level
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Create clean, minimal log format
        if record.levelname == 'INFO':
            # For INFO: Just show the message with green checkmark
            return f"{color}✅ {record.getMessage()}{reset}"
        elif record.levelname == 'ERROR':
            # For ERROR: Show red X with minimal context
            return f"{color}❌ {record.name}: {record.getMessage()}{reset}"
        elif record.levelname == 'WARNING':
            # For WARNING: Show yellow warning
            return f"{color}⚠️  {record.getMessage()}{reset}"
        elif record.levelname == 'DEBUG':
            # For DEBUG: Show minimal debug info
            return f"{color}🔍 {record.name}: {record.getMessage()}{reset}"
        else:
            # For others: Standard format
            return f"{color}[{timestamp}] {record.levelname}: {record.getMessage()}{reset}"

class NicoleLogger:
    """Clean logging system for Nicole AI"""
    
    @staticmethod
    def setup():
        """Setup clean, organized logging"""
        
        # Remove existing handlers to avoid duplicates
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create console handler with clean formatter
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(CleanFormatter())
        
        # Configure root logger - SILENT by default
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.ERROR)  # Only show errors by default
        
        # Silence noisy third-party libraries
        noisy_loggers = [
            'googleapiclient.discovery_cache',
            'urllib3.connectionpool',
            'httpx',
            'anthropic',
            'motor',
            'pymongo',
            'werkzeug',
            'config_discord',
            'core.database',
            'core.auth',
            'core.youtube_service',
            'core.analysis_service',
            'services',
            'utils',
            'app'
        ]
        
        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
        
        # Set specific loggers to clean levels - ONLY show our custom messages
        logging.getLogger('nicole_bot').setLevel(logging.ERROR)
        logging.getLogger('dashboard.content_studio_routes').setLevel(logging.ERROR)
        logging.getLogger('services.youtube_service').setLevel(logging.ERROR)
        logging.getLogger('database').setLevel(logging.ERROR)
        logging.getLogger('core').setLevel(logging.ERROR)
        logging.getLogger('dashboard').setLevel(logging.ERROR)
        
        # Silence ALL startup noise
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        logging.getLogger().setLevel(logging.ERROR)
        
        return root_logger

# Initialize clean logging
logger = NicoleLogger.setup()

# Export clean logger functions
def success(message):
    """Log success message"""
    logging.info(message)

def error(message, component="system"):
    """Log error message"""
    logging.error(f"{component}: {message}")

def warning(message):
    """Log warning message"""
    logging.warning(message)

def debug(message, component="debug"):
    """Log debug message"""
    logging.debug(f"{component}: {message}")

def progress(message):
    """Log progress message"""
    logging.info(f"🚀 {message}")

def api_call(endpoint, status="started"):
    """Log API call"""
    if status == "started":
        logging.info(f"📡 API → {endpoint}")
    elif status == "success":
        logging.info(f"✅ API → {endpoint}")
    elif status == "error":
        logging.error(f"❌ API → {endpoint}")

def db_operation(operation, status="started"):
    """Log database operation"""
    if status == "started":
        logging.info(f"💾 DB → {operation}")
    elif status == "success":
        logging.info(f"✅ DB → {operation}")
    elif status == "error":
        logging.error(f"❌ DB → {operation}")
