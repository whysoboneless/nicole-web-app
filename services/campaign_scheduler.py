"""
Campaign Scheduler - Automated production for active campaigns
Handles multi-platform production (YouTube, Instagram, TikTok)
Supports high-volume production (600+ videos/day)
"""

import asyncio
import logging
from typing import Dict, List
from datetime import datetime, timedelta
from bson import ObjectId

logger = logging.getLogger(__name__)


class CampaignScheduler:
    """
    Handles automated production scheduling for active campaigns
    Checks upload frequency and triggers production as needed
    """
    
    def __init__(self, db, production_service):
        """
        Initialize scheduler
        
        Args:
            db: Database instance
            production_service: CampaignProductionService instance
        """
        self.db = db
        self.production_service = production_service
    
    async def process_all_campaigns(self):
        """
        Main scheduler loop - called by cron job
        
        For each active campaign:
        1. Get all channels
        2. Check if each channel needs new content
        3. Trigger production asynchronously
        4. Track budget usage
        """
        logger.info("🔄 Campaign scheduler started")
        
        try:
            # Get all active campaigns
            active_campaigns = list(self.db.campaigns.find({'status': 'active'}))
            
            logger.info(f"   Found {len(active_campaigns)} active campaigns")
            
            for campaign in active_campaigns:
                campaign_id = str(campaign['_id'])
                campaign_name = campaign.get('name', 'Unknown')
                
                logger.info(f"📊 Processing campaign: {campaign_name} ({campaign_id})")
                
                try:
                    await self._process_campaign(campaign)
                except Exception as e:
                    logger.error(f"   ❌ Error processing campaign {campaign_id}: {e}")
                    continue
            
            logger.info("✅ Campaign scheduler completed")
            
        except Exception as e:
            logger.error(f"❌ Campaign scheduler failed: {e}")
            import traceback
            traceback.print_exc()
    
    async def _process_campaign(self, campaign: Dict):
        """
        Process a single campaign
        Check all channels and trigger production as needed
        """
        campaign_id = str(campaign['_id'])
        
        # Get all channels for this campaign
        channels = list(self.db.campaign_channels.find({
            'campaign_id': ObjectId(campaign_id)
        }))
        
        logger.info(f"   {len(channels)} channels in campaign")
        
        # Check budget
        monthly_budget = campaign.get('monthly_budget', campaign.get('budget', {}).get('api_cost_limit', 500))
        total_spent = campaign.get('total_api_cost', 0)
        
        if total_spent >= monthly_budget:
            logger.warning(f"   ⚠️ Campaign budget exceeded ({total_spent}/{monthly_budget})")
            return
        
        # Process each channel
        production_tasks = []
        
        for channel in channels:
            if self._should_produce_content(channel):
                # Create production task (don't await - parallel execution)
                task = self._schedule_production(campaign, channel)
                production_tasks.append(task)
        
        # Execute all production tasks in parallel for speed
        if production_tasks:
            logger.info(f"   🚀 Starting {len(production_tasks)} production jobs in parallel")
            await asyncio.gather(*production_tasks, return_exceptions=True)
        else:
            logger.info(f"   ⏸️ No channels need content at this time")
    
    def _should_produce_content(self, channel: Dict) -> bool:
        """
        Check if channel needs new content based on:
        - status (must be 'active')
        - upload_frequency setting
        - last_upload_date
        - budget remaining
        
        Returns:
            True if channel needs new content
        """
        # Check if channel is active
        if channel.get('status') != 'active':
            return False
        
        # Check last upload date
        last_upload = channel.get('last_upload_date')
        frequency = channel.get('upload_frequency', 'weekly')
        
        # Calculate hours between uploads
        frequency_hours = {
            'daily': 24,
            'every_3_days': 72,
            'weekly': 168,
            'biweekly': 336,
            'monthly': 720
        }.get(frequency, 168)  # Default to weekly
        
        # If never uploaded, produce now
        if not last_upload:
            logger.info(f"      ✅ Channel needs content (never uploaded)")
            return True
        
        # Calculate time since last upload
        time_since_upload = datetime.utcnow() - last_upload
        hours_since_upload = time_since_upload.total_seconds() / 3600
        
        if hours_since_upload >= frequency_hours:
            logger.info(f"      ✅ Channel needs content ({hours_since_upload:.1f}h since last upload, frequency: {frequency_hours}h)")
            return True
        
        logger.info(f"      ⏸️ Channel doesn't need content yet ({hours_since_upload:.1f}h/{frequency_hours}h)")
        return False
    
    async def _schedule_production(self, campaign: Dict, channel: Dict):
        """
        Schedule and execute production for a channel
        
        Routes to correct production method based on platform
        """
        channel_id = str(channel['_id'])
        campaign_id = str(campaign['_id'])
        platform = channel.get('platform', 'youtube')
        
        logger.info(f"      🎬 Producing content for {platform} channel {channel_id}")
        
        try:
            # Route to appropriate production method
            if platform == 'youtube':
                result = await self._produce_youtube(campaign, channel)
            elif platform == 'instagram':
                result = await self._produce_instagram(campaign, channel)
            elif platform == 'tiktok':
                result = await self._produce_tiktok(campaign, channel)
            else:
                logger.error(f"Unknown platform: {platform}")
                return
            
            # Update last_upload_date if successful
            if result.get('success'):
                self.db.campaign_channels.update_one(
                    {'_id': channel['_id']},
                    {'$set': {
                        'last_upload_date': datetime.utcnow(),
                        'last_production_result': result
                    }}
                )
                logger.info(f"      ✅ Production successful for {platform} channel")
            else:
                logger.error(f"      ❌ Production failed for {platform} channel: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"      ❌ Production error for channel {channel_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def _produce_youtube(self, campaign: Dict, channel: Dict) -> Dict:
        """Produce YouTube video"""
        return await self.production_service.produce_video_for_campaign(
            campaign_id=str(campaign['_id']),
            channel_id=str(channel['_id']),
            group_id=str(channel['group_id']),
            series_name=channel['series_name'],
            theme_name=channel['theme_name'],
            user_id=str(channel['user_id']),
            youtube_channel_id=channel.get('youtube_channel_id', ''),
            video_duration=channel.get('video_duration', 30),
            voice=channel.get('voice_id', 'af_nicole')
        )
    
    async def _produce_instagram(self, campaign: Dict, channel: Dict) -> Dict:
        """Produce Instagram carousel"""
        return await self.production_service.produce_slideshow_for_instagram(
            campaign_id=str(campaign['_id']),
            channel_id=str(channel['_id']),
            group_id=str(channel['group_id']),
            series_name=channel['series_name'],
            theme_name=channel['theme_name']
        )
    
    async def _produce_tiktok(self, campaign: Dict, channel: Dict) -> Dict:
        """Produce TikTok UGC video"""
        return await self.production_service.produce_ugc_for_tiktok(
            campaign_id=str(campaign['_id']),
            channel_id=str(channel['_id']),
            group_id=str(channel['group_id']),
            series_name=channel['series_name'],
            theme_name=channel['theme_name'],
            voice_id=channel.get('voice_id', 'af_nicole')
        )


# Singleton instance
campaign_scheduler = None


def get_campaign_scheduler(db, production_service):
    """Get or create campaign scheduler singleton"""
    global campaign_scheduler
    if campaign_scheduler is None:
        campaign_scheduler = CampaignScheduler(db, production_service)
    return campaign_scheduler

