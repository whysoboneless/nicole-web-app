"""
Simple wrapper for Discord bot YouTube service
Handles all the complex imports and provides sync methods
"""

import asyncio
import logging
import sys
import os

logger = logging.getLogger(__name__)

class YouTubeServiceWrapper:
    """Simplified wrapper for Discord bot YouTube service"""
    
    def __init__(self):
        try:
            # Import config
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from config_discord import YOUTUBE_API_KEYS
            
            # Import Discord bot YouTube service
            from services.youtube_service import YouTubeService as BotYouTubeService
            
            self.youtube_service = BotYouTubeService(api_keys=YOUTUBE_API_KEYS)
            self.available = True
            logger.info("✅ YouTube service wrapper initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize YouTube service: {e}")
            self.available = False
            self.youtube_service = None
    
    def _run_async(self, coro):
        """Run async function synchronously"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create new event loop in thread
                import threading
                result = []
                error = []
                
                def run_in_thread():
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        result.append(new_loop.run_until_complete(coro))
                    except Exception as e:
                        error.append(e)
                    finally:
                        new_loop.close()
                
                thread = threading.Thread(target=run_in_thread)
                thread.start()
                thread.join(timeout=60)  # 60 second timeout
                
                if error:
                    raise error[0]
                if result:
                    return result[0]
                return None
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)
    
    def get_video_transcript(self, video_id: str):
        """Get video transcript synchronously"""
        if not self.available:
            return None
        try:
            return self._run_async(self.youtube_service.get_video_transcript(video_id))
        except Exception as e:
            logger.error(f"Error getting transcript for {video_id}: {e}")
            return None
    
    def get_video_duration(self, video_id: str):
        """Get video duration synchronously"""
        if not self.available:
            return 600  # Default 10 minutes
        try:
            return self._run_async(self.youtube_service.get_video_duration(video_id))
        except Exception as e:
            logger.error(f"Error getting duration for {video_id}: {e}")
            return 600
    
    def get_video_info(self, video_id: str):
        """Get video info synchronously"""
        if not self.available:
            return {"title": "", "description": ""}
        try:
            return self._run_async(self.youtube_service.get_video_info(video_id))
        except Exception as e:
            logger.error(f"Error getting info for {video_id}: {e}")
            return {"title": "", "description": ""}

# Create global instance
youtube_wrapper = YouTubeServiceWrapper()
