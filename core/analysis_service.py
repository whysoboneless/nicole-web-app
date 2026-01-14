"""
Analysis service for Nicole Web Suite
Integrates with Discord bot's analysis service - REAL FUNCTIONALITY ONLY
"""

import logging
import asyncio
import sys
import os

# Add the parent directory to the Python path to import Discord bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class AnalysisService:
    """
    Real Discord bot analysis service integration - NO MOCK DATA
    """
    def __init__(self):
        self.bot_analysis = None
        self.youtube_service = None
        self.db = None
        
        

    def _ensure_services_loaded(self):
        """Load Discord bot services only when needed to avoid circular imports"""
        if self.bot_analysis is None:
            # Import Discord bot services - REAL INTEGRATION
            from services.analysis_service import AnalysisService as BotAnalysisService
            from services.youtube_service import YouTubeService
            from database import Database
            from utils.cache_manager import CacheManager
            from utils.progress_tracker import ProgressTracker
            from config import YOUTUBE_API_KEYS
            
            # Initialize REAL components
            self.db = Database()
            self.youtube_service = YouTubeService(YOUTUBE_API_KEYS)
            cache_manager = CacheManager()
            progress_tracker = ProgressTracker()
            
            # Create a web bot object for the analysis service
            class WebBot:
                def __init__(self, db, youtube_service):
                    self.db = db
                    self.youtube_service = youtube_service
                    
            web_bot = WebBot(self.db, self.youtube_service)
            
            # Initialize the REAL bot analysis service
            self.bot_analysis = BotAnalysisService(
                youtube_service=self.youtube_service,
                cache_manager=cache_manager,
                progress_tracker=progress_tracker,
                db=self.db,
                bot=web_bot
            )
            
            

    def run_async(self, coro):
        """Run async function synchronously"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If event loop is running, use executor
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result(timeout=60)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(coro)

    def perform_niche_analysis_sync(self, channel_url: str, group_name: str, 
                                   is_public: bool = False, user_id: str = None):
        """Perform REAL niche analysis synchronously using Discord bot logic"""
        
        # Load services only when needed
        self._ensure_services_loaded()
        
        # Create a web interaction object for the Discord bot service
        class WebInteraction:
            def __init__(self, user_id):
                self.user = type('User', (), {'id': user_id})()
                self.followup = type('Followup', (), {
                    'send': lambda *args, **kwargs: print(f"Would send: {args}, {kwargs}")
                })()
        
        web_interaction = WebInteraction(user_id) if user_id else None
        
        try:
            result = self.run_async(
                self.bot_analysis.perform_niche_analysis(
                    interaction=web_interaction,
                    channel_url=channel_url,
                    group_name=group_name,
                    is_public=is_public
                )
            )
            return result
        except Exception as e:
            logger.error(f"Error in perform_niche_analysis_sync: {str(e)}")
            return {"error": str(e)}

    def get_channel_id_from_url_sync(self, channel_url: str) -> str:
        """Get channel ID from URL synchronously"""
        self._ensure_services_loaded()
        return self.run_async(self.youtube_service.get_channel_id_from_url(channel_url))

    def analyze_competitor_group_sync(self, group_id: str):
        """Analyze competitor group using REAL Discord bot logic"""
        self._ensure_services_loaded()
        return self.run_async(self.bot_analysis.analyze_competitor_channels(group_id))

    def get_group_analysis_sync(self, group_id: str):
        """Get group analysis using REAL Discord bot logic"""
        self._ensure_services_loaded()
        return self.run_async(self.bot_analysis.get_group_analysis(group_id))

    def analyze_competitor_channels_sync(self, group_id: str):
        """Analyze competitor channels synchronously - equivalent to Discord bot functionality"""
        self._ensure_services_loaded()
        try:
            result = self.run_async(self.bot_analysis.analyze_competitor_channels(group_id))
            print(f"✅ Analyzed competitor channels for group {group_id}")
            return result
        except Exception as e:
            logger.error(f"Error analyzing competitor channels: {str(e)}")
            return {"error": str(e)}

    def add_channel_by_url_sync(self, group_id: str, channel_url: str):
        """Add channel by URL using REAL Discord bot logic"""
        self._ensure_services_loaded()
        return self.run_async(self.bot_analysis.add_channel_by_url(group_id, channel_url))

# Export for compatibility
__all__ = ['AnalysisService'] 
