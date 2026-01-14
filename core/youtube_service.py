"""
YouTube service for Nicole Web Suite - REAL Discord bot integration
"""

import logging
import asyncio
import sys
import os

# Add the parent directory to the Python path to import Discord bot modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class YouTubeService:
    """
    REAL Discord bot YouTube service integration - NO MOCK DATA
    """
    def __init__(self):
        # Import REAL Discord bot YouTube service
        from services.youtube_service import YouTubeService as BotYouTubeService
        from config import YOUTUBE_API_KEYS
        
        self.bot_youtube = BotYouTubeService(YOUTUBE_API_KEYS)
        

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

    def get_channel_id_from_url_sync(self, channel_url: str):
        """Extract channel ID from URL synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.get_channel_id_from_url(channel_url))

    def fetch_channel_data_sync(self, channel_id: str):
        """Fetch channel data synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.fetch_channel_data(channel_id))

    def fetch_channel_videos_sync(self, channel_id: str, max_results: int = 50):
        """Fetch channel videos synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.fetch_channel_videos(channel_id, max_results))

    def search_videos_sync(self, query: str, max_results: int = 50):
        """Search videos synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.search_videos(query, max_results))

    def get_video_details_sync(self, video_id: str):
        """Get video details synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.get_video_details(video_id))
    
    def get_video_transcript_sync(self, video_id: str):
        """Get video transcript synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.get_video_transcript(video_id))
    
    def get_video_duration_sync(self, video_id: str):
        """Get video duration synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.get_video_duration(video_id))
    
    def get_video_info_sync(self, video_id: str):
        """Get video info synchronously using REAL Discord bot logic"""
        return self.run_async(self.bot_youtube.get_video_info(video_id))

# Export for compatibility
__all__ = ['YouTubeService'] 
