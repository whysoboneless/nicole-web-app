"""
Web Analysis Service - EXACT copy of Discord bot AnalysisService but without Discord dependencies
"""

import asyncio
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging
import statistics
import traceback
import time
from core.database import Database
from bson import ObjectId
import json
import re
import asyncio

# Import Discord bot utilities directly
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from utils.ai_utils import get_claude_analysis, check_videos_in_series, parse_claude_response, check_shared_series
    from services.youtube_service import YouTubeService
    from services.content_generation_service import ContentGenerationService
    from utils.cache_manager import CacheManager
    from utils.progress_tracker import ProgressTracker
    from utils.ai_utils import identify_niche_and_demographics, get_claude_analysis
    from datetime import datetime, timezone
    from utils.ai_utils import check_shared_series
    from utils import ai_utils
    from config import YOUTUBE_API_KEYS, REDIS_URL
    # print("✅ Successfully imported Discord bot modules for web analysis service")  # Commented - too noisy
except ImportError as e:
    # print(f"❌ Could not import Discord bot modules: {e}")  # Commented - too noisy
    # Create fallback empty classes
    class YouTubeService:
        def __init__(self, *args): pass
    class ContentGenerationService:
        def __init__(self, *args): pass
    class CacheManager:
        def __init__(self, *args): pass
    class ProgressTracker:
        def __init__(self, *args): pass
    REDIS_URL = 'redis://localhost:6379'  # Fallback
    YOUTUBE_API_KEYS = []

logger = logging.getLogger(__name__)

class WebAnalysisService:
    """EXACT copy of Discord bot AnalysisService but adapted for web app"""
    
    def __init__(self, db: Database):
        try:
            print(f"🔍 Initializing WebAnalysisService...")
            print(f"🔍 YOUTUBE_API_KEYS available: {len(YOUTUBE_API_KEYS) if YOUTUBE_API_KEYS else 0}")
            print(f"🔍 REDIS_URL: {REDIS_URL}")
            
            self.youtube_service = YouTubeService(YOUTUBE_API_KEYS)
            print(f"✅ YouTube service initialized")
            
            self.cache_manager = CacheManager(redis_url=REDIS_URL, youtube_service=self.youtube_service)
            print(f"✅ Cache manager initialized")
            
            self.progress_tracker = ProgressTracker(redis_url=REDIS_URL)
            print(f"✅ Progress tracker initialized")
            
            self.db = db
            self.content_generation_service = ContentGenerationService()
            print(f"✅ WebAnalysisService fully initialized")
        except Exception as e:
            print(f"❌ Error initializing WebAnalysisService: {e}")
            import traceback
            traceback.print_exc()
            self.db = db
            # Initialize with None for fallback
            self.youtube_service = None
            self.cache_manager = None
            self.progress_tracker = None
            self.content_generation_service = None

    
    async def perform_niche_analysis(
        self,
        channel_url: str,
        group_name: str,
        user_id: str,  # MongoDB ObjectId as string
        is_public: bool = False,
        discord_id: str = None,  # Discord ID for allowed_users (same as Discord bot)
        user_doc: dict = None  # User document for is_premium, etc
    ) -> Dict:
        """EXACT same logic as Discord bot but without Discord interaction"""
        logger.info(f"Starting niche analysis for channel URL {channel_url} with group name '{group_name}'")

        try:
            # Step 1: Extract channel ID (EXACT same as Discord bot)
            # print(f"🔍 Extracting channel ID from URL: {channel_url}")  # Debug - commented
            # print(f"🔍 YouTube service is: {self.youtube_service}")  # Debug - commented
            
            if self.youtube_service is None:
                logger.error("YouTube service is None!")
                return {"error": "YouTube service not initialized"}
            
            channel_id = await self.youtube_service.get_channel_id_from_url(channel_url)
            if not channel_id:
                logger.error(f"Failed to extract channel ID from URL: {channel_url}")
                return {"error": "Failed to extract channel ID"}

            # Step 2: Fetch channel data and videos (EXACT same as Discord bot)
            channel_data = await self.youtube_service.fetch_channel_data(channel_id)
            logger.info(f"Fetched channel data for {channel_id}")

            videos = await self.youtube_service.fetch_channel_videos(channel_id)
            logger.info(f"Fetched {len(videos)} videos for channel {channel_id}")

            if not videos:
                logger.error(f"No videos found for channel {channel_id}")
                return {"error": "No videos found"}

            # Step 3: Check if channel already exists (EXACT same as Discord bot)
            existing_group = self.db.competitor_groups.find_one({
                "$or": [
                    {"main_channel_id": channel_id},
                    {"competitors.channelId": channel_id}
                ]
            })
            if existing_group:
                logger.info(f"Channel {channel_id} is already part of group {existing_group['_id']}")
                return {"message": "Channel already in a group", "group_id": str(existing_group['_id'])}

            # Step 4: Create initial group (EXACT same as Discord bot)
            group_id = await self.create_initial_group(
                user_id=user_id, 
                channel_id=channel_id, 
                channel_data=channel_data, 
                videos=videos, 
                group_name=group_name, 
                is_public=is_public,
                discord_id=discord_id,  # Pass discord_id for allowed_users
                user_doc=user_doc  # Pass user_doc for is_premium, etc
            )
            if not group_id:
                return {"error": "Failed to create initial group"}

            # Step 5: Generate series data with Claude (EXACT same as Discord bot)
            video_data = [{'title': video['title'], 'views': video['viewCount'], 'thumbnail': video.get('thumbnailUrl', ''), 'channel_id': channel_id} for video in videos]
            
            logger.info(f"Performing Claude analysis for group {group_id}")
            series_data = await get_claude_analysis(video_data, channel_data['title'])

            if not series_data:
                logger.warning(f"Empty Claude analysis for group {group_id}. Using default series.")
                series_data = self.create_default_series(video_data)
            elif isinstance(series_data, str):
                try:
                    series_data = json.loads(series_data)
                except json.JSONDecodeError:
                    series_data = self.create_default_series(video_data)
            elif isinstance(series_data, dict):
                series_data = [series_data]
            elif not isinstance(series_data, list):
                series_data = self.create_default_series(video_data)

            # Step 6: Clean and update series data (EXACT same as Discord bot)
            cleaned_series_data = self.clean_series_data(series_data, video_data)
            self.db.update_competitor_group(group_id, {"series_data": cleaned_series_data})

            # Step 7: Find potential competitors (EXACT same as Discord bot)
            potential_competitors = await self.rapid_initial_competitor_discovery(group_id, cleaned_series_data)

            # Step 8: Filter competitors (EXACT same as Discord bot)
            filtered_competitors = {}
            main_channel_id = channel_data.get('id')
            for series_name, competitors in potential_competitors.items():
                unique_competitors = {comp['channel']['id']: comp for comp in competitors if comp['channel']['id'] != main_channel_id}
                filtered_competitors[series_name] = list(unique_competitors.values())

            logger.info(f"Found potential competitors for web app")

            # Return data for CompetitorSelectionView
            return {
                "group_id": group_id,
                "potential_competitors": filtered_competitors,
                "channel_data": channel_data,
                "videos": videos,
                "series_data": cleaned_series_data
            }

        except Exception as e:
            import traceback
            logger.error(f"Error in perform_niche_analysis: {str(e)}")
            print(f"❌ web_analysis_service: Error in perform_niche_analysis: {str(e)}")
            print(f"❌ web_analysis_service: Full traceback:")
            traceback.print_exc()
            return {"error": str(e)}
    
    async def create_initial_group(
        self,
        user_id: str,  # MongoDB ObjectId as string
        channel_id: str,
        channel_data: Dict,
        videos: List[Dict],
        group_name: str,
        is_public: bool,
        discord_id: str = None,  # Discord ID for allowed_users (same as Discord bot)
        user_doc: dict = None  # User document for is_premium, etc
    ):
        """EXACT same create_initial_group as Discord bot but without Discord interaction"""
        logger.info(f"Starting create_initial_group for channel {channel_id} with group name '{group_name}'")
        try:
            # Use discord_id for allowed_users if provided (EXACT same as Discord bot)
            # Discord bot uses: "allowed_users": [str(interaction.user.id)]
            allowed_users_value = discord_id if discord_id else user_id
            
            # Get user premium status from user_doc (EXACT same as Discord bot CreateGroupModal)
            is_premium = user_doc.get('is_premium', False) if user_doc else False
            
            # EXACT same group_data structure as Discord bot
            group_data = {
                "name": group_name,
                "user_id": discord_id if discord_id else user_id,  # Discord bot uses Discord ID
                "main_channel_id": channel_id,
                "main_channel_data": channel_data,
                "videos": videos,
                "competitors": [],
                "top_performers": [],
                "new_viral_channels": [],
                "categorized_competitors": [],
                "trending_topics": [],
                "is_public": is_public,
                "is_premium": is_premium,  # Use actual user premium status
                "is_purchasable": False,
                "price": 0,
                "whop_product_id": None,
                "performance_data": {
                    "avg_monthly_views": 0,
                    "avg_monthly_subs": 0,
                    "avg_estimated_revenue": 0,
                    "avg_upload_frequency": 0,
                    "total_competitors": 0
                },
                "performance_distribution": {},
                "comparative_analysis": {},
                "series_data": [],
                "niche_viability": {
                    "status": "",
                    "emerging_stars": [],
                    "growth_metrics": {},
                    "performance_baselines": {},
                    "estimated_rpm": 0
                },
                "createdAt": datetime.utcnow(),
                "lastUpdated": datetime.utcnow(),
                "created_at": datetime.utcnow(),  # Discord bot adds this in update_data
                "allowed_users": [allowed_users_value],  # Use Discord ID (same as Discord bot)
                "owner_id": ObjectId(user_id)  # MongoDB ObjectId for owner_id
            }

            logger.info(f"Creating competitor group in database for channel {channel_id}")
            group_id = self.db.create_competitor_group(group_data)
            if not group_id:
                logger.error(f"Failed to create competitor group for channel {channel_id}")
                return None
            logger.info(f"Created competitor group with ID: {group_id}")

            return str(group_id)
        except Exception as e:
            logger.error(f"Unexpected error in create_initial_group for channel {channel_id}: {str(e)}")
            return None
    
    # Copy ALL other methods from Discord bot AnalysisService exactly
    async def rapid_initial_competitor_discovery(self, group_id: str, series_data: List[Dict]):
        """EXACT copy from Discord bot"""
        logger.info(f"Starting rapid initial competitor discovery for group {group_id}")
        search_results = {}
        potential_competitors = {}
        max_results_per_topic = 50

        try:
            group = self.db.get_competitor_group(group_id)
            main_channel_id = group.get('main_channel_id')

            for series in series_data:
                series_name = series['name']
                search_results[series_name] = {}
                potential_competitors[series_name] = []

                for theme in series.get('themes', []):
                    for topic in theme.get('topics', []):
                        search_query = topic.get('example', '')
                        logger.info(f"Searching for: {search_query} in group {group_id}")
                        try:
                            # Use regular search (automatically falls back to HTML scraping if quota exceeded)
                            results = await self.youtube_service.search_videos(search_query, max_results=max_results_per_topic)
                            logger.info(f"Found {len(results['videos'])} search results for '{search_query}'")
                            
                            # Store search results
                            search_results[series_name][search_query] = results['videos']
                            
                            # Process results for potential competitors
                            for result in results['videos']:
                                channel_id = result.get('channelId')
                                if channel_id and channel_id != main_channel_id and not any(c['channel']['id'] == channel_id for c in potential_competitors[series_name]):
                                    try:
                                        # Fetch full channel data for stats
                                        channel_data = await self.youtube_service.fetch_channel_data(channel_id)
                                        if channel_data:
                                            potential_competitors[series_name].append({
                                                'channel': {
                                                    'id': channel_id,
                                                    'title': channel_data.get('title', result.get('channelTitle', '')),
                                                    'subscriberCount': channel_data.get('subscriberCount', '0'),
                                                    'videoCount': channel_data.get('videoCount', '0'),
                                                    'viewCount': channel_data.get('viewCount', '0'),
                                                    'thumbnails': channel_data.get('thumbnails', {})
                                                },
                                                'video': {
                                                    'id': result.get('id', ''),
                                                    'title': result.get('title', ''),
                                                    'thumbnails': result.get('thumbnails', {}),
                                                    'publishedAt': result.get('publishedAt', '')
                                                }
                                            })
                                    except Exception as e:
                                        logger.warning(f"Failed to fetch channel data for {channel_id}: {str(e)}")
                                        # Fallback to basic data
                                        potential_competitors[series_name].append({
                                            'channel': {
                                                'id': channel_id,
                                                'title': result.get('channelTitle', ''),
                                                'subscriberCount': '0',
                                                'videoCount': '0',
                                                'viewCount': '0',
                                                'thumbnails': {}
                                            },
                                            'video': {
                                                'id': result.get('id', ''),
                                                'title': result.get('title', ''),
                                                'thumbnails': result.get('thumbnails', {}),
                                                'publishedAt': result.get('publishedAt', '')
                                            }
                                        })
                                    
                                    if len(potential_competitors[series_name]) >= 10:
                                        break

                        except Exception as e:
                            logger.error(f"Error searching for '{search_query}': {str(e)}")
                            continue

            # Remove empty series from potential_competitors
            potential_competitors = {k: v for k, v in potential_competitors.items() if v}

            # Update the group with search results and potential competitors
            self.db.update_competitor_group(group_id, {
                'search_results': search_results,
                'potential_competitors': potential_competitors
            })

            total_competitors = sum(len(competitors) for competitors in potential_competitors.values())
            logger.info(f"Finished rapid initial competitor discovery for group {group_id}. Found {total_competitors} potential competitors.")
            return potential_competitors

        except Exception as e:
            logger.error(f"Error in rapid_initial_competitor_discovery: {str(e)}")
            raise
    
    def clean_series_data(self, series_data, video_data):
        """EXACT copy from Discord bot"""
        if isinstance(series_data, str):
            try:
                series_data = json.loads(series_data)
            except json.JSONDecodeError:
                logger.error("Failed to parse series_data as JSON")
                return self.create_default_series(video_data)

        if not isinstance(series_data, list):
            logger.error(f"series_data is not a list: {type(series_data)}")
            return self.create_default_series(video_data)

        cleaned_data = []
        for series in series_data:
            if not isinstance(series, dict):
                logger.warning(f"Skipping non-dict series: {series}")
                continue
            cleaned_series = {
                "name": series.get("name", "Unknown Series"),
                "themes": [],
                "total_views": 0,
                "video_count": 0,
                "channels_with_series": set()
            }
            for theme in series.get("themes", []):
                if not isinstance(theme, dict):
                    logger.warning(f"Skipping non-dict theme: {theme}")
                    continue
                cleaned_theme = {
                    "name": theme.get("name", "Unknown Theme"),
                    "topics": [],
                    "total_views": 0,
                    "video_count": 0
                }
                for topic in theme.get("topics", []):
                    if not isinstance(topic, dict):
                        logger.warning(f"Skipping non-dict topic: {topic}")
                        continue
                    matching_videos = [
                        v for v in video_data 
                        if v['title'].strip().lower() == topic.get("example", "").strip().lower()
                    ]
                    if matching_videos:
                        example_video = max(matching_videos, key=lambda v: v.get('views', 0))
                        cleaned_topic = {
                            "name": topic.get("name", "Unknown Topic"),
                            "example": example_video['title'],
                            "views": int(example_video.get('views', 0)),
                            "thumbnail_url": example_video.get('thumbnail', ''),
                            "published_at": example_video.get('published_at', ''),
                            "id": example_video.get('id', ''),
                            "channel_id": example_video.get('channel_id', '')
                        }
                        cleaned_theme["topics"].append(cleaned_topic)
                        cleaned_theme["total_views"] += cleaned_topic["views"]
                        cleaned_theme["video_count"] += 1
                        cleaned_series["channels_with_series"].add(cleaned_topic["channel_id"])
                if cleaned_theme["topics"]:
                    cleaned_theme["avg_views"] = cleaned_theme["total_views"] / cleaned_theme["video_count"]
                    cleaned_series["themes"].append(cleaned_theme)
                    cleaned_series["total_views"] += cleaned_theme["total_views"]
                    cleaned_series["video_count"] += cleaned_theme["video_count"]
            if cleaned_series["themes"]:
                cleaned_series["avg_views"] = cleaned_series["total_views"] / cleaned_series["video_count"]
                cleaned_series["channels_with_series"] = list(cleaned_series["channels_with_series"])
                cleaned_series["themes"].sort(key=lambda x: x.get('avg_views', 0), reverse=True)
                cleaned_data.append(cleaned_series)

        cleaned_data.sort(key=lambda x: x.get("avg_views", 0), reverse=True)
        return cleaned_data

    def create_default_series(self, videos):
        """EXACT copy from Discord bot"""
        example_video = videos[0] if isinstance(videos, list) and videos else {"title": "No videos available", "views": 0}
        return [{
            "name": "Default Series",
            "themes": [{
                "name": "General Content",
                "topics": [{
                    "name": "Mixed Topics",
                    "example": example_video["title"],
                    "views": example_video["views"]
                }],
                "total_views": example_video["views"],
                "video_count": 1
            }],
            "total_views": example_video["views"],
            "video_count": 1
        }]
    
    async def add_competitor_to_group(self, group_id: str, channel_id: str, matching_title: str, matching_series: List[Dict]):
        """EXACT copy from Discord bot"""
        logger.info(f"Adding competitor {channel_id} to group {group_id}")
        try:
            competitor_data = await self.youtube_service.fetch_channel_data(channel_id)
            if not competitor_data:
                logger.error(f"Failed to fetch channel data for {channel_id}")
                return None

            competitor_videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=50)
            if not competitor_videos:
                logger.error(f"Failed to fetch videos for channel {channel_id}")
                return None

            processed_videos = []
            total_views = total_likes = total_comments = total_duration = 0
            
            for video in competitor_videos:
                processed_video = {
                    "videoId": video['id'],
                    "title": video['title'],
                    "publishedAt": video['publishedAt'],
                    "viewCount": int(video.get('viewCount', 0)),
                    "likeCount": int(video.get('likeCount', 0)),
                    "commentCount": int(video.get('commentCount', 0)),
                    "duration": video.get('duration', 'PT0S'),
                    "duration_seconds": video.get('duration_seconds', 0),
                    "series_data": next((series['name'] for series in matching_series if video['title'] in series.get('matching_titles', [])), None),
                    "thumbnail_url": video.get('thumbnail_url', '')
                }
                processed_videos.append(processed_video)
                total_views += processed_video['viewCount']
                total_likes += processed_video['likeCount']
                total_comments += processed_video['commentCount']
                total_duration += processed_video['duration_seconds']

            avg_video_duration = total_duration / len(processed_videos) if processed_videos else 0

            upload_frequency = self.calculate_upload_frequency(processed_videos)
            monthly_views = self.estimate_monthly_views(processed_videos)
            monthly_subscriber_growth = self.estimate_monthly_subscriber_growth(competitor_data)
            growth_score = self.calculate_growth_score(competitor_data, processed_videos)
            
            competitor = {
                "channel_id": channel_id,
                "title": competitor_data['title'],
                "description": competitor_data['description'],
                "subscriberCount": competitor_data['subscriberCount'],
                "videoCount": competitor_data['videoCount'],
                "viewCount": competitor_data['viewCount'],
                "publishedAt": competitor_data['joinDate'],
                "thumbnails": competitor_data['thumbnails'],
                "videos": processed_videos,
                "upload_frequency": upload_frequency,
                "monthly_views": monthly_views,
                "monthly_subscriber_growth": monthly_subscriber_growth,
                "growth_score": growth_score,
                "shared_series": matching_series,
                "series_analyzed": True,
                "total_video_views": total_views,
                "total_video_likes": total_likes,
                "total_video_comments": total_comments,
                "average_views_per_video": total_views / len(processed_videos) if processed_videos else 0,
                "engagement_rate": (total_likes + total_comments) / total_views if total_views > 0 else 0,
                "matching_title": matching_title,
                "matching_series": matching_series,
                "avg_video_duration": avg_video_duration
            }
            
            result = self.db.add_competitor_to_group(group_id, competitor)
            if result:
                logger.info(f"Added competitor {competitor['channel_id']} to group {group_id}")
                return competitor
            else:
                logger.warning(f"Failed to add competitor {competitor['channel_id']} to group {group_id}")
                return None

        except Exception as e:
            logger.error(f"Error adding competitor {channel_id} to group {group_id}: {str(e)}")
            return None
    
    def calculate_upload_frequency(self, videos: List[Dict]) -> float:
        """EXACT copy from Discord bot"""
        if not videos:
            return 0.0
        
        upload_dates = [datetime.fromisoformat(video['publishedAt'].rstrip('Z')).replace(tzinfo=timezone.utc) for video in videos]
        oldest_video_date = min(upload_dates)
        newest_video_date = max(upload_dates)
        
        time_span = max((newest_video_date - oldest_video_date).days, 1)
        months = time_span / 30.44
        
        return round(len(videos) / months, 2)
    
    def estimate_monthly_views(self, videos: List[Dict]) -> int:
        """EXACT copy from Discord bot"""
        if not videos:
            return 0
        
        total_views = sum(int(v.get('viewCount', 0)) for v in videos)
        upload_dates = [datetime.fromisoformat(video['publishedAt'].rstrip('Z')).replace(tzinfo=timezone.utc) for video in videos]
        oldest_video_date = min(upload_dates)
        newest_video_date = max(upload_dates)
        
        months_active = max((newest_video_date - oldest_video_date).days / 30.44, 1)
        
        return int(total_views / months_active)
    
    def estimate_monthly_subscriber_growth(self, channel_data: Dict) -> float:
        """EXACT copy from Discord bot"""
        try:
            subscriber_count = int(channel_data.get('statistics', {}).get('subscriberCount', 0))
            published_at = channel_data.get('snippet', {}).get('publishedAt')
            
            if not published_at:
                return subscriber_count * 0.01
            
            channel_age = datetime.now(timezone.utc) - datetime.fromisoformat(published_at.rstrip('Z')).replace(tzinfo=timezone.utc)
            months = channel_age.days / 30.44
            
            if months == 0:
                return 0
            
            monthly_growth = subscriber_count / months
            return monthly_growth
        except Exception as e:
            logger.error(f"Error estimating monthly subscriber growth: {str(e)}")
            return 0

    def calculate_growth_score(self, channel_data: Dict, videos: List[Dict]) -> float:
        """EXACT copy from Discord bot"""
        monthly_views = self.estimate_monthly_views(videos)
        monthly_sub_growth = self.estimate_monthly_subscriber_growth(channel_data)
        upload_frequency = self.calculate_upload_frequency(videos)
        
        view_score = monthly_views / 1000
        sub_score = monthly_sub_growth * 10
        frequency_score = upload_frequency * 5
        
        total_score = view_score + sub_score + frequency_score
        
        return round(total_score, 2)

    def analyze_competitor_series(self, group_id: str, competitor_channel_id: str):
        """EXACT copy from Discord bot"""
        logger.info(f"Analyzing competitor series for channel {competitor_channel_id} in group {group_id}")
        try:
            group = self.db.get_competitor_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return None

            series_data = group.get('series_data', [])
            if not series_data:
                logger.warning(f"No series data found for group {group_id}")
                return []

            competitor_videos = self.youtube_service.fetch_channel_videos(competitor_channel_id, max_results=50)
            if not competitor_videos:
                logger.error(f"Failed to fetch videos for competitor {competitor_channel_id}")
                return []

            matching_series = check_shared_series(competitor_videos, series_data)
            logger.info(f"Found {len(matching_series)} matching series for competitor {competitor_channel_id}")
            
            return matching_series

        except Exception as e:
            logger.error(f"Error analyzing competitor series for {competitor_channel_id}: {str(e)}")
            return []

    def finalize_competitor_group(self, group_id: str, selected_competitors: List[str]):
        """EXACT copy from Discord bot"""
        logger.info(f"Finalizing competitor group {group_id} with {len(selected_competitors)} competitors")
        try:
            group = self.db.get_competitor_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return False

            # Add selected competitors to the group
            for channel_id in selected_competitors:
                logger.info(f"Adding competitor {channel_id} to group {group_id}")
                
                # Analyze competitor series
                matching_series = self.analyze_competitor_series(group_id, channel_id)
                
                # Add competitor with series analysis
                competitor = self.add_competitor_to_group(
                    group_id, 
                    channel_id, 
                    "Selected Competitor", 
                    matching_series
                )
                
                if not competitor:
                    logger.warning(f"Failed to add competitor {channel_id} to group {group_id}")

            # Calculate performance metrics
            self.calculate_group_performance_metrics(group_id)
            
            # Generate comparative analysis
            self.generate_comparative_analysis(group_id)
            
            # Update group status
            self.db.update_competitor_group(group_id, {
                "status": "completed",
                "lastUpdated": datetime.utcnow()
            })

            logger.info(f"Successfully finalized competitor group {group_id}")
            return True

        except Exception as e:
            logger.error(f"Error finalizing competitor group {group_id}: {str(e)}")
            return False

    def calculate_group_performance_metrics(self, group_id: str):
        """Calculate performance metrics for the group"""
        logger.info(f"Calculating performance metrics for group {group_id}")
        try:
            group = self.db.get_competitor_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return

            competitors = group.get('competitors', [])
            if not competitors:
                logger.warning(f"No competitors found for group {group_id}")
                return

            # Calculate averages
            total_monthly_views = sum(comp.get('monthly_views', 0) for comp in competitors)
            total_monthly_subs = sum(comp.get('monthly_subscriber_growth', 0) for comp in competitors)
            total_upload_frequency = sum(comp.get('upload_frequency', 0) for comp in competitors)
            
            # Store metrics in group
            num_competitors = len(competitors)
            metrics = {
                'avg_monthly_views': total_monthly_views / num_competitors if num_competitors > 0 else 0,
                'avg_monthly_subs': total_monthly_subs / num_competitors if num_competitors > 0 else 0,
                'avg_upload_frequency': total_upload_frequency / num_competitors if num_competitors > 0 else 0
            }
            
            self.db.update_competitor_group(group_id, {'performance_metrics': metrics})
            logger.info(f"Updated performance metrics for group {group_id}")
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {str(e)}")
    
    def generate_comparative_analysis(self, group_id: str):
        """Generate comparative analysis for the group"""
        logger.info(f"Generating comparative analysis for group {group_id}")
        try:
            # This is a placeholder - in the full implementation this would generate detailed analysis
            # For now, just mark it as complete
            self.db.update_competitor_group(group_id, {
                'comparative_analysis': {
                    'generated_at': datetime.utcnow(),
                    'status': 'completed'
                }
            })
            logger.info(f"Completed comparative analysis for group {group_id}")
        except Exception as e:
            logger.error(f"Error generating comparative analysis: {str(e)}")
