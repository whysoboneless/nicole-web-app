"""
User API Key Middleware - Simple approach to enforce user API keys
"""

import threading
from typing import Optional, List
from functools import wraps
from flask import current_app, request, jsonify
from flask_login import current_user
try:
    from anthropic import AsyncAnthropic
except ImportError:
    AsyncAnthropic = None

try:
    # Try importing from Discord bot services first
    import sys
    import os
    parent_dir = os.path.join(os.path.dirname(__file__), '..', '..')
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from services.youtube_service import YouTubeService as OriginalYouTubeService
except ImportError:
    try:
        # Fallback to web app services
        from services.youtube_service import YouTubeService as OriginalYouTubeService
    except ImportError:
        OriginalYouTubeService = None

# Thread-local storage for current user's API keys
_local = threading.local()

class APIKeyError(Exception):
    """Raised when user doesn't have required API keys"""
    pass

def set_user_context(user_id: str, db):
    """Set current user's API keys in thread-local context"""
    _local.user_id = user_id
    
    # Get user's API key with debug logging
    user_anthropic_key = db.get_user_api_key(user_id, 'Anthropic Claude')
    print(f"🔍 API Key check for user {user_id}: {'Found' if user_anthropic_key else 'NOT FOUND'}")
    
    # Fallback to system key if user doesn't have one
    if not user_anthropic_key:
        import os
        from config import OWNER_ID
        # Only use system key for owner or if specifically configured
        if str(user_id) == str(OWNER_ID):
            user_anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
            print(f"✅ Using system Anthropic key for owner {user_id}")
        else:
            print(f"❌ User {user_id} has no Anthropic key and is not owner")
    
    _local.anthropic_key = user_anthropic_key
    _local.youtube_keys = db.get_user_youtube_api_keys(user_id)
    _local.db = db
    
    print(f"🔑 Final key status: {'SET' if _local.anthropic_key else 'MISSING'}")

def get_user_anthropic_key() -> Optional[str]:
    """Get current user's Anthropic API key"""
    return getattr(_local, 'anthropic_key', None)

def get_user_youtube_keys() -> List[str]:
    """Get current user's YouTube API keys"""
    return getattr(_local, 'youtube_keys', [])

def require_anthropic_key():
    """Decorator to require Anthropic API key"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not get_user_anthropic_key():
                raise APIKeyError("Anthropic Claude API key required. Please add it in API Keys section.")
            return func(*args, **kwargs)
        return wrapper
    return decorator

def require_youtube_keys():
    """Decorator to require YouTube API keys"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not get_user_youtube_keys():
                raise APIKeyError("YouTube API key required. Please add it in API Keys section.")
            return func(*args, **kwargs)
        return wrapper
    return decorator

class UserAwareAnthropic:
    """Anthropic client that uses user's API key or system key for owner"""
    
    def __init__(self, api_key=None, **kwargs):
        if not AsyncAnthropic:
            raise ImportError("Anthropic library not available")
        
        # If explicit API key provided, use it directly
        if api_key:
            self._client = AsyncAnthropic(api_key=api_key, **kwargs)
            return
        
        # Check if we're in a Flask request context
        try:
            from flask import has_request_context
            in_request = has_request_context()
        except:
            in_request = False
        
        # If not in request context (e.g., module import), use system key
        if not in_request:
            import os
            system_key = os.environ.get('ANTHROPIC_API_KEY')
            if system_key:
                self._client = AsyncAnthropic(api_key=system_key, **kwargs)
                return
            raise APIKeyError("No ANTHROPIC_API_KEY environment variable set")
        
        # Check if owner - use system key
        try:
            from flask_login import current_user
            from config import OWNER_ID
            if current_user.is_authenticated and str(getattr(current_user, 'discord_id', '')) == str(OWNER_ID):
                # Owner bypass - use system key from environment
                import os
                system_key = os.environ.get('ANTHROPIC_API_KEY')
                if system_key:
                    self._client = AsyncAnthropic(api_key=system_key, **kwargs)
                    return
        except:
            pass
        
        # Non-owner: require user's key
        user_key = get_user_anthropic_key()
        if not user_key:
            raise APIKeyError("Anthropic Claude API key required. Please add it in API Keys section.")
        self._client = AsyncAnthropic(api_key=user_key, **kwargs)
    
    def __getattr__(self, name):
        return getattr(self._client, name)

class UserAwareYouTubeService:
    """YouTube service that uses user's API keys or allows fallback"""
    
    def __init__(self, api_keys=None):
        if not OriginalYouTubeService:
            raise ImportError("YouTube service not available")
        user_keys = get_user_youtube_keys()
        # Priority: User's saved keys > System fallback keys (your keys) > Empty
        if user_keys:
            keys_to_use = user_keys
            print(f"🔑 Using user's YouTube API keys ({len(user_keys)} keys)")
        elif api_keys:
            keys_to_use = api_keys
            print(f"🔑 Using system fallback YouTube API keys ({len(api_keys)} keys)")
        else:
            keys_to_use = []
            print(f"⚠️ No YouTube API keys available")
        self._service = OriginalYouTubeService(api_keys=keys_to_use)
    
    def __getattr__(self, name):
        return getattr(self._service, name)

def patch_api_clients():
    """Patch API clients to use user keys"""
    import anthropic
    import sys
    import os
    
    # Add web app services to path
    web_app_path = os.path.dirname(os.path.dirname(__file__))
    if web_app_path not in sys.path:
        sys.path.insert(0, web_app_path)
    
    # Patch Anthropic
    anthropic.AsyncAnthropic = UserAwareAnthropic
    
    # Patch YouTube service in services module
    try:
        import services.youtube_service
        services.youtube_service.YouTubeService = UserAwareYouTubeService
    except ImportError:
        pass
    
    # Patch in utils_dir if it exists
    try:
        import utils_dir.ai_utils
        # Replace AsyncAnthropic calls in ai_utils
        utils_dir.ai_utils.AsyncAnthropic = UserAwareAnthropic
    except ImportError:
        pass

def api_key_required(func):
    """Decorator for routes that require API keys"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        
        try:
            # Import db here to avoid circular imports
            from core.database import Database
            db = Database()
            
            # Set user context - use Discord ID for consistency with database
            discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
            set_user_context(discord_id, db)
            
            # BYPASS API KEY CHECK FOR OWNER
            from config import OWNER_ID
            if str(current_user.discord_id) == str(OWNER_ID):
                print(f"✅ Owner bypass: Skipping API key check for owner {current_user.discord_id}")
                return func(*args, **kwargs)
            
            # Check for required Anthropic key (non-owners only)
            if not get_user_anthropic_key():
                return jsonify({
                    'success': False, 
                    'error': 'Anthropic Claude API key required. Please add it in the API Keys section.',
                    'redirect': '/api_keys'
                }), 400
            
            return func(*args, **kwargs)
            
        except APIKeyError as e:
            return jsonify({
                'success': False, 
                'error': str(e),
                'redirect': '/api_keys'
            }), 400
        except Exception as e:
            return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
    
    return wrapper
