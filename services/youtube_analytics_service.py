"""
YouTube Analytics Service
Syncs revenue data from YouTube Analytics API
Calculates estimated revenue based on views and RPM
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class YouTubeAnalyticsService:
    """
    Sync YouTube Analytics data for campaign channels
    Calculate revenue estimates based on views and RPM
    """
    
    def __init__(self, db):
        self.db = db
    
    async def sync_campaign_analytics(self, campaign_id: str) -> Dict:
        """
        Sync analytics for all channels in a campaign
        Pulls data from YouTube Analytics API
        """
        
        try:
            logger.info(f"📊 Syncing analytics for campaign: {campaign_id}")
            
            # Get all channels in campaign
            from nicole_web_suite_template.core.database import Database
            web_db = Database()
            channels = web_db.get_campaign_channels(campaign_id)
            
            total_views = 0
            total_revenue = 0
            
            for channel in channels:
                youtube_channel_id = channel.get('youtube_channel_id')
                user_id = str(channel['user_id'])
                
                if not youtube_channel_id:
                    continue
                
                # Get analytics from YouTube
                analytics = await self._get_youtube_analytics(
                    youtube_channel_id,
                    user_id,
                    days=30
                )
                
                if analytics:
                    views = analytics.get('views', 0)
                    watch_time_minutes = analytics.get('watch_time_minutes', 0)
                    estimated_revenue = analytics.get('estimated_revenue', 0)
                    
                    # Update channel stats
                    web_db.update_campaign_channel(str(channel['_id']), {
                        'total_views': views,
                        'estimated_revenue': estimated_revenue,
                        'watch_time_percentage': analytics.get('avg_watch_percentage', 0)
                    })
                    
                    # Log to campaign analytics
                    web_db.log_campaign_analytics(
                        campaign_id,
                        str(channel['_id']),
                        views=views,
                        watch_time_minutes=watch_time_minutes,
                        revenue=estimated_revenue
                    )
                    
                    total_views += views
                    total_revenue += estimated_revenue
            
            logger.info(f"✅ Synced {len(channels)} channels: {total_views} views, ${total_revenue:.2f} revenue")
            
            return {
                'success': True,
                'channels_synced': len(channels),
                'total_views': total_views,
                'total_revenue': total_revenue
            }
            
        except Exception as e:
            logger.error(f"Analytics sync failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _get_youtube_analytics(
        self,
        youtube_channel_id: str,
        user_id: str,
        days: int = 30
    ) -> Optional[Dict]:
        """Get YouTube Analytics data for a channel"""
        
        try:
            # Get channel OAuth credentials
            from database import db as discord_db
            credentials_data = await discord_db.get_channel_oauth_credentials(user_id, youtube_channel_id)
            
            if not credentials_data:
                logger.warning(f"No credentials for channel {youtube_channel_id}")
                return None
            
            # Build YouTube Analytics API client
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            
            credentials = Credentials(
                token=credentials_data.get('token'),
                refresh_token=credentials_data.get('refresh_token'),
                token_uri=credentials_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=credentials_data.get('client_id'),
                client_secret=credentials_data.get('client_secret'),
                scopes=['https://www.googleapis.com/auth/yt-analytics.readonly']
            )
            
            # Refresh if needed
            if not credentials.valid:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
            
            # Build Analytics API client
            youtube_analytics = build('youtubeAnalytics', 'v2', credentials=credentials)
            
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Query analytics
            response = youtube_analytics.reports().query(
                ids=f'channel=={youtube_channel_id}',
                startDate=start_date.strftime('%Y-%m-%d'),
                endDate=end_date.strftime('%Y-%m-%d'),
                metrics='views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage',
                dimensions='day'
            ).execute()
            
            # Parse response
            rows = response.get('rows', [])
            
            if not rows:
                return {'views': 0, 'watch_time_minutes': 0, 'estimated_revenue': 0}
            
            # Aggregate data
            total_views = sum(row[1] for row in rows)  # views column
            total_watch_minutes = sum(row[2] for row in rows)  # estimatedMinutesWatched
            avg_view_duration = sum(row[3] for row in rows) / len(rows)  # averageViewDuration
            avg_view_percentage = sum(row[4] for row in rows) / len(rows) if len(rows[0]) > 4 else 0
            
            # Estimate revenue (views * RPM / 1000)
            # Default RPM: $5 (conservative estimate)
            estimated_rpm = 5.0
            estimated_revenue = (total_views * estimated_rpm) / 1000
            
            return {
                'views': int(total_views),
                'watch_time_minutes': int(total_watch_minutes),
                'avg_view_duration': avg_view_duration,
                'avg_watch_percentage': avg_view_percentage,
                'estimated_revenue': estimated_revenue,
                'estimated_rpm': estimated_rpm
            }
            
        except Exception as e:
            logger.error(f"Failed to get YouTube analytics: {e}")
            return None
    
    async def estimate_channel_revenue(
        self,
        channel_id: str,
        views: int,
        watch_time_percentage: float,
        niche: str = None
    ) -> float:
        """
        Estimate revenue based on views and channel niche
        Different niches have different RPMs
        """
        
        # RPM estimates by niche
        rpm_by_niche = {
            'finance': 15.0,
            'tech': 12.0,
            'ai': 10.0,
            'business': 10.0,
            'crypto': 8.0,
            'education': 7.0,
            'gaming': 3.0,
            'entertainment': 2.5,
            'default': 5.0
        }
        
        # Get RPM for niche
        rpm = rpm_by_niche.get(niche.lower() if niche else 'default', 5.0)
        
        # Adjust RPM based on watch time (better watch time = higher RPM)
        if watch_time_percentage > 60:
            rpm *= 1.3
        elif watch_time_percentage > 40:
            rpm *= 1.1
        elif watch_time_percentage < 30:
            rpm *= 0.8
        
        # Calculate revenue
        revenue = (views * rpm) / 1000
        
        return revenue


# Singleton
youtube_analytics = YouTubeAnalyticsService(None)

