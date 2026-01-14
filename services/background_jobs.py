"""
Background Jobs Service
Handles scheduled tasks for campaigns:
- Daily lifecycle automation evaluation
- Analytics syncing
- Channel performance monitoring
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Dict, List
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger(__name__)


class BackgroundJobsService:
    """
    Background job scheduler for campaign automation
    Runs daily tasks for lifecycle management and analytics
    """
    
    def __init__(self):
        from nicole_web_suite_template.core.database import Database
        from nicole_web_suite_template.services.campaign_automation_service import campaign_automation
        from nicole_web_suite_template.services.youtube_analytics_service import youtube_analytics
        
        self.db = Database()
        self.automation = campaign_automation
        self.analytics = youtube_analytics
    
    async def run_daily_jobs(self):
        """Run all daily jobs"""
        
        try:
            logger.info("🔄 Running daily background jobs...")
            
            # Job 1: Sync YouTube Analytics
            await self.sync_all_campaign_analytics()
            
            # Job 2: Evaluate lifecycle automation
            await self.evaluate_all_lifecycles()
            
            # Job 3: Clean up old data
            await self.cleanup_old_analytics()
            
            logger.info("✅ Daily jobs complete")
            
        except Exception as e:
            logger.error(f"❌ Daily jobs failed: {e}")
    
    async def sync_all_campaign_analytics(self):
        """Sync analytics for all active campaigns"""
        
        try:
            logger.info("📊 Syncing campaign analytics...")
            
            # Get all active campaigns
            campaigns = self.db.campaigns.find({'status': 'active'})
            
            synced = 0
            for campaign in campaigns:
                campaign_id = str(campaign['_id'])
                
                try:
                    result = await self.analytics.sync_campaign_analytics(campaign_id)
                    if result.get('success'):
                        synced += 1
                except Exception as e:
                    logger.error(f"Failed to sync campaign {campaign_id}: {e}")
            
            logger.info(f"✅ Synced {synced} campaigns")
            
        except Exception as e:
            logger.error(f"Analytics sync job failed: {e}")
    
    async def evaluate_all_lifecycles(self):
        """Evaluate lifecycle automation for all channels"""
        
        try:
            logger.info("🤖 Evaluating lifecycle automation...")
            
            # Get all campaigns with lifecycle automation enabled
            campaigns = self.db.campaigns.find({
                'status': 'active',
                'lifecycle_automation_enabled': True
            })
            
            evaluated = 0
            actions_taken = 0
            
            for campaign in campaigns:
                campaign_id = str(campaign['_id'])
                
                # Get channels for this campaign
                channels = self.db.get_campaign_channels(campaign_id)
                
                for channel in channels:
                    channel_id = str(channel['_id'])
                    
                    # Evaluate channel performance
                    result = await self.automation.evaluate_channel_performance(channel_id)
                    evaluated += 1
                    
                    if result.get('success'):
                        recommendation = result.get('recommendation')
                        
                        # Execute recommended action
                        if recommendation == 'scale':
                            success = await self.automation.execute_lifecycle_action(channel_id, 'scale')
                            if success:
                                actions_taken += 1
                                logger.info(f"   ✅ Scaled channel {channel_id}")
                        
                        elif recommendation == 'pause':
                            success = await self.automation.execute_lifecycle_action(channel_id, 'pause')
                            if success:
                                actions_taken += 1
                                logger.info(f"   ⏸️ Paused channel {channel_id}")
            
            logger.info(f"✅ Evaluated {evaluated} channels, took {actions_taken} actions")
            
        except Exception as e:
            logger.error(f"Lifecycle evaluation failed: {e}")
    
    async def cleanup_old_analytics(self):
        """Clean up analytics data older than 90 days"""
        
        try:
            logger.info("🧹 Cleaning up old analytics...")
            
            cutoff_date = datetime.utcnow() - timedelta(days=90)
            
            result = self.db.campaign_analytics.delete_many({
                'date': {'$lt': cutoff_date}
            })
            
            deleted = result.deleted_count
            logger.info(f"✅ Deleted {deleted} old analytics records")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    async def run_hourly_jobs(self):
        """Run hourly maintenance tasks"""
        
        try:
            logger.info("⏰ Running hourly jobs...")
            
            # Check for stuck production jobs
            await self.check_stuck_productions()
            
            logger.info("✅ Hourly jobs complete")
            
        except Exception as e:
            logger.error(f"Hourly jobs failed: {e}")
    
    async def check_stuck_productions(self):
        """Check for production jobs stuck in processing"""
        
        try:
            # Find channels with very old last_upload dates but status = testing/scaling
            cutoff = datetime.utcnow() - timedelta(hours=24)
            
            stuck_channels = self.db.campaign_channels.find({
                'status': {'$in': ['testing', 'scaling']},
                'last_upload': {'$lt': cutoff}
            })
            
            for channel in stuck_channels:
                logger.warning(f"⚠️ Channel {channel['_id']} may be stuck (no upload in 24h)")
                # Could send notification or auto-pause
            
        except Exception as e:
            logger.error(f"Stuck production check failed: {e}")


# Function to start background scheduler
def start_background_scheduler(app):
    """
    Start APScheduler for background jobs
    Call this from app.py after app creation
    """
    
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = AsyncIOScheduler()
        jobs_service = BackgroundJobsService()
        
        # Daily job at 2 AM
        scheduler.add_job(
            jobs_service.run_daily_jobs,
            CronTrigger(hour=2, minute=0),
            id='daily_jobs',
            name='Daily campaign jobs',
            replace_existing=True
        )
        
        # Hourly job
        scheduler.add_job(
            jobs_service.run_hourly_jobs,
            CronTrigger(minute=0),
            id='hourly_jobs',
            name='Hourly maintenance',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ Background scheduler started")
        
        return scheduler
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        return None


# Singleton
background_jobs = BackgroundJobsService()

