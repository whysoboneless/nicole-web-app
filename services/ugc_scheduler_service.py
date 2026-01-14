"""
UGC Production Scheduler
Automatically produces videos for active TikTok/Instagram channels based on their upload schedule
NO manual triggers - fully automated
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Dict
from core.database import Database

# Setup logger with immediate console output
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler that flushes immediately
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.propagate = False

class UGCSchedulerService:
    """
    Background service that checks active social media channels
    and automatically produces videos when due
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.running = False
    
    async def start(self):
        """Start the scheduler - runs continuously"""
        self.running = True
        logger.info("🚀 UGC Scheduler started - monitoring active channels")
        
        while self.running:
            try:
                # Reset daily production costs at midnight UTC
                now = datetime.utcnow()
                if now.hour == 0 and now.minute < 5:  # Reset window: 00:00-00:05 UTC
                    await self._reset_daily_costs()
                
                await self.check_and_produce()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
            
            # Check every hour
            await asyncio.sleep(3600)
    
    async def _reset_daily_costs(self):
        """Reset daily production costs at midnight"""
        try:
            channels_collection = self.db.db['campaign_channels']
            result = channels_collection.update_many(
                {'production_cost': {'$gt': 0}},
                {'$set': {'production_cost': 0}}
            )
            if result.modified_count > 0:
                logger.info(f"💰 Reset daily production costs for {result.modified_count} channels")
        except Exception as e:
            logger.error(f"Error resetting daily costs: {e}")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("🛑 UGC Scheduler stopped")
    
    async def check_and_produce(self):
        """
        Check all active TikTok/Instagram channels
        Produce videos for those that are due
        """
        try:
            # Get all active social media channels
            active_channels = self.get_active_social_channels()
            
            logger.info(f"📊 Checking {len(active_channels)} active social channels")
            
            for channel in active_channels:
                try:
                    if self.should_produce_video(channel):
                        logger.info(f"📹 Video due for {channel.get('platform')} channel: {channel.get('username')}")
                        await self.trigger_production(channel)
                except Exception as e:
                    logger.error(f"Error processing channel {channel.get('_id')}: {e}")
            
        except Exception as e:
            logger.error(f"Error in check_and_produce: {e}")
    
    def get_active_social_channels(self) -> List[Dict]:
        """Get all active TikTok and Instagram channels with product assigned"""
        try:
            # Use correct collection name
            channels_collection = self.db.db['campaign_channels']
            channels = channels_collection.find({
                'status': 'active',
                'platform': {'$in': ['tiktok', 'instagram']},
                'product_id': {'$exists': True, '$ne': None}  # Must have product assigned
            })
            
            return list(channels)
        except Exception as e:
            logger.error(f"Error getting active channels: {e}")
            return []
    
    def should_produce_video(self, channel: Dict) -> bool:
        """
        Determine if a video is due for this channel
        Based on videos_per_day or upload_frequency and last upload time
        """
        try:
            # Check if channel is disabled
            if channel.get('status') == 'disabled':
                return False
            
            # Get videos per day (new) or fallback to frequency (legacy)
            videos_per_day = channel.get('videos_per_day')
            if videos_per_day:
                # Calculate hours between videos: 24 / videos_per_day
                required_hours = 24.0 / videos_per_day
            else:
                # Legacy: use frequency string
                frequency = channel.get('upload_frequency', 'daily')
                required_hours = self.frequency_to_hours(frequency)
            
            last_upload = channel.get('last_upload_time')
            
            # If never uploaded, produce first video
            if not last_upload:
                logger.info(f"Channel {channel.get('username')} has no uploads yet - producing first video")
                return True
            
            # Calculate hours since last upload
            now = datetime.utcnow()
            hours_since_last = (now - last_upload).total_seconds() / 3600
            
            # Check if enough time has passed
            is_due = hours_since_last >= required_hours
            
            if is_due:
                logger.info(f"Video due: {hours_since_last:.1f}h since last upload (required: {required_hours:.1f}h)")
            
            return is_due
            
        except Exception as e:
            logger.error(f"Error checking if video is due: {e}")
            return False
    
    def frequency_to_hours(self, frequency: str) -> float:
        """Convert upload frequency to hours between videos (legacy support)"""
        frequency_map = {
            'daily': 24,
            'every_2_days': 48,
            'every_3_days': 72,
            'weekly': 168,
            'twice_daily': 12,
            'three_times_daily': 8
        }
        
        return frequency_map.get(frequency, 24)  # Default to daily
    
    async def trigger_production(self, channel: Dict):
        """
        Trigger video production for a channel
        Routes to UGC or slideshow service based on content style
        """
        try:
            # Determine content style
            platform = channel.get('platform')
            if platform == 'tiktok':
                content_style = channel.get('tiktok_content_style', 'ugc_video')
            elif platform == 'instagram':
                content_style = channel.get('instagram_post_type', 'reel')
            else:
                logger.error(f"Unknown platform: {platform}")
                return
            
            logger.info(f"📋 Content style for {channel.get('username')}: {content_style}")
            
            # Route to appropriate service
            if content_style in ['ugc_video', 'reel']:
                # Use UGC service
                await self._produce_ugc_video(channel)
            elif content_style in ['slideshow', 'carousel']:
                # Slideshow not yet implemented
                logger.info(f"⏭️ Skipping {channel.get('username')} - slideshow production not yet implemented")
                return
            else:
                logger.warning(f"⚠️ Unknown content style '{content_style}' for {channel.get('username')}")
                return
                
        except Exception as e:
            logger.error(f"Error triggering production: {e}")
            import traceback
            traceback.print_exc()
    
    async def _produce_ugc_video(self, channel: Dict):
        """
        Produce UGC video for a channel
        """
        try:
            from services.ugc_sora_service import ugc_sora_service
            
            # Get product/offer details
            product_id = channel.get('product_id')
            if not product_id:
                logger.error(f"Channel {channel.get('username')} has no product assigned")
                return
            
            product = self.db.get_product(str(product_id))
            if not product:
                logger.error(f"Product {product_id} not found")
                return
            
            # Check daily spend limit
            daily_spend = channel.get('production_cost', 0)
            daily_limit = channel.get('daily_production_spend', 0)
            cost_per_video = 0.32  # UGC video cost
            
            if daily_limit > 0 and daily_spend + cost_per_video > daily_limit:
                logger.info(f"💰 Daily spend limit reached for {channel.get('username')}: ${daily_spend:.2f}/${daily_limit:.2f}")
                return
            
            # Produce the video
            logger.info(f"🎬 Starting UGC production for {channel.get('username')} - {product.get('name')}")
            
            result = await ugc_sora_service.produce_ugc_video(channel, product)
            
            if result.get('success'):
                # Update channel with new upload and cost tracking
                channels_collection = self.db.db['campaign_channels']
                
                # Get current totals for logging
                updated_channel = channels_collection.find_one({'_id': channel['_id']})
                current_production_cost = updated_channel.get('production_cost', 0) if updated_channel else 0
                current_total_cost = updated_channel.get('total_production_cost', 0) if updated_channel else 0
                
                channels_collection.update_one(
                    {'_id': channel['_id']},
                    {
                        '$set': {
                            'last_upload_time': datetime.utcnow(),
                            'latest_video_url': result['video_url']
                        },
                        '$inc': {
                            'videos_produced': 1,
                            'total_videos_produced': 1,
                            'production_cost': cost_per_video,  # Daily running total
                            'total_production_cost': cost_per_video  # Lifetime total
                        }
                    }
                )
                
                new_daily_cost = current_production_cost + cost_per_video
                new_total_cost = current_total_cost + cost_per_video
                
                logger.info(f"✅ Video produced and uploaded: {result['video_url']}")
                logger.info(f"💰 Cost: ${cost_per_video:.2f} (Today: ${new_daily_cost:.2f}, Total: ${new_total_cost:.2f})")
                
                # Auto-post to TikTok/Instagram if channel has OAuth token
                await self.post_to_social_media(channel, result)
            else:
                logger.error(f"❌ Production failed: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error in UGC production: {e}")
            import traceback
            traceback.print_exc()
    
    async def post_to_social_media(self, channel: Dict, video_result: Dict):
        """
        Post video to TikTok or Instagram after generation
        """
        try:
            platform = channel.get('platform')
            
            # Check if channel has OAuth token
            access_token = channel.get('access_token')
            if not access_token:
                logger.info(f"No access token for {platform} channel - skipping auto-post")
                return
            
            video_url = video_result.get('video_url')  # Google Drive URL
            caption = f"Check out this! #ad"  # TODO: Generate dynamic captions
            
            if platform == 'tiktok':
                from services.tiktok_posting_service import tiktok_posting_service
                result = await tiktok_posting_service.upload_video(
                    access_token,
                    video_url,
                    caption
                )
                if result.get('success'):
                    logger.info(f"✅ Posted to TikTok: {result.get('share_url')}")
                else:
                    logger.error(f"❌ TikTok post failed: {result.get('error')}")
            
            elif platform == 'instagram':
                from services.instagram_posting_service import instagram_posting_service
                ig_user_id = channel.get('ig_user_id')
                
                if not ig_user_id:
                    logger.warning("No Instagram user ID - skipping post")
                    return
                
                result = await instagram_posting_service.upload_reel(
                    access_token,
                    ig_user_id,
                    video_url,
                    caption
                )
                if result.get('success'):
                    logger.info(f"✅ Posted to Instagram: {result.get('permalink')}")
                else:
                    logger.error(f"❌ Instagram post failed: {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Error posting to social media: {e}")


# Singleton instance
_scheduler_instance = None

def get_scheduler(db: Database) -> UGCSchedulerService:
    """Get or create scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = UGCSchedulerService(db)
    return _scheduler_instance

