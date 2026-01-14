import asyncio
from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging
import statistics
import traceback
import time
from database import Database
from bson import ObjectId
import json
import re
import asyncio
from utils.ai_utils import get_claude_analysis
from services.youtube_service import YouTubeService
from services.content_generation_service import ContentGenerationService    
from utils.ai_utils import get_claude_analysis, check_videos_in_series, parse_claude_response ,check_shared_series
from utils.cache_manager import CacheManager
from utils.progress_tracker import ProgressTracker
from utils.ai_utils import identify_niche_and_demographics, get_claude_analysis
from datetime import datetime, timezone
from utils.ai_utils import check_shared_series
from utils import ai_utils


logger = logging.getLogger(__name__)

class AnalysisService:
    def __init__(self, youtube_service: YouTubeService, cache_manager: CacheManager, progress_tracker: ProgressTracker, db: Database, bot):
        self.youtube_service = youtube_service
        self.cache_manager = cache_manager
        self.progress_tracker = progress_tracker
        self.db = db
        self.content_generation_service = ContentGenerationService()
        self.bot = bot
    
    async def initialize(self):
        await self.load_group_data()
        await self.filter_search_results()
        await self.send_initial_message()

    async def check_shared_series(self, series_data: Dict, search_result_titles: List[str], current_series_name: str):
        return await ai_utils.check_shared_series(series_data, search_result_titles, current_series_name)
    
    
    async def perform_niche_analysis(
        self,
        interaction: discord.Interaction,
        channel_url: str,
        group_name: str,
        is_public: bool = False
    ) -> Dict:
        logger.info(f"Starting niche analysis for channel URL {channel_url} with group name '{group_name}'")

        try:
            channel_id = await self.youtube_service.get_channel_id_from_url(channel_url)
            if not channel_id:
                logger.error(f"Failed to extract channel ID from URL: {channel_url}")
                if interaction:
                    await interaction.followup.send("Failed to extract channel ID from the URL provided. Please check the URL and try again.", ephemeral=True)
                return {"error": "Failed to extract channel ID"}

            # Fetch channel data and videos
            channel_data = await self.youtube_service.fetch_channel_data(channel_id)
            logger.info(f"Fetched channel data for {channel_id}: {json.dumps(channel_data, indent=2)}")

            videos = await self.youtube_service.fetch_channel_videos(channel_id)
            logger.info(f"Fetched {len(videos)} videos for channel {channel_id}")

            if not videos:
                logger.error(f"No videos found for channel {channel_id}")
                if interaction:
                    await interaction.followup.send(f"No videos found for channel {channel_id}. Please check if the channel has public videos.", ephemeral=True)
                return {"error": "No videos found"}

            # Check if the channel is already part of a group
            existing_group = await self.db.competitor_groups.find_one({
                "$or": [
                    {"main_channel_id": channel_id},
                    {"competitors.channelId": channel_id}
                ]
            })
            if existing_group:
                logger.info(f"Channel {channel_id} is already part of group {existing_group['_id']}")
                if interaction:
                    await interaction.followup.send(
                        f"This channel is already part of the group: {existing_group['name']}",
                        ephemeral=True
                    )
                return {"message": "Channel already in a group", "group_id": str(existing_group['_id'])}

            # Create initial group
            group_id = await self.create_initial_group(interaction, channel_id, channel_data, videos, group_name, is_public)
            if not group_id:
                return {"error": "Failed to create initial group"}

            # Extract video titles and create video_data
            video_data = [{'title': video['title'], 'views': video['viewCount'], 'thumbnail': video.get('thumbnailUrl', ''), 'channel_id': channel_id} for video in videos]
            
            # Perform Claude analysis to generate series data
            logger.info(f"Performing Claude analysis for group {group_id}")
            series_data = await get_claude_analysis(video_data, channel_data['title'])

            logger.debug(f"Raw series_data: {series_data}")

            if not series_data:
                logger.warning(f"Empty Claude analysis for group {group_id}. Using default series.")
                series_data = self.create_default_series(video_data)
            elif isinstance(series_data, str):
                logger.warning(f"Series data is a string for group {group_id}. Attempting to parse.")
                try:
                    series_data = json.loads(series_data)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse series data as JSON for group {group_id}. Using default series.")
                    series_data = self.create_default_series(video_data)
            elif isinstance(series_data, dict):
                logger.warning(f"Series data is a dict for group {group_id}. Wrapping in a list.")
                series_data = [series_data]
            elif not isinstance(series_data, list):
                logger.error(f"Unexpected series data type for group {group_id}: {type(series_data)}. Using default series.")
                series_data = self.create_default_series(video_data)

            # Clean and update series data
            cleaned_series_data = self.clean_series_data(series_data, video_data)
            await self.db.update_competitor_group(group_id, {"series_data": cleaned_series_data})
            # Verify the updated series data
            updated_group = await self.db.get_competitor_group(str(group_id))
            logger.info(f"Verified series data in group {group_id}: {json.dumps(updated_group.get('series_data', []), indent=2)}")

            # Perform rapid initial competitor discovery
            potential_competitors = await self.rapid_initial_competitor_discovery(group_id, cleaned_series_data)

            # Filter out duplicate channels and the main channel
            filtered_competitors = {}
            main_channel_id = channel_data.get('id')
            for series_name, competitors in potential_competitors.items():
                unique_competitors = {comp['channel']['id']: comp for comp in competitors if comp['channel']['id'] != main_channel_id}
                filtered_competitors[series_name] = list(unique_competitors.values())

            logger.info(f"Filtered potential competitors: {json.dumps(filtered_competitors, indent=2)}")

            # Return the necessary data
            return {
                "group_id": group_id,
                "potential_competitors": filtered_competitors,
                "channel_data": channel_data,
                "videos": videos,
                "series_data": cleaned_series_data
            }

        except Exception as e:
            logger.error(f"Error in perform_niche_analysis: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            pass  # No interaction needed for web app
            return {"error": str(e)}
    
    async def finalize_group(self, group_id: str, selected_competitors: set):
        logger.info(f"Finalizing group {group_id} with {len(selected_competitors)} selected competitors")
        try:
            group = await self.db.get_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return False

            update_data = {
                "competitors": list(selected_competitors),
                "last_updated": datetime.now(timezone.utc)
            }

            result = await self.db.update_group(group_id, update_data)
            if result:
                logger.info(f"Successfully finalized group {group_id}")
                return True
            else:
                logger.error(f"Failed to update group {group_id}")
                return False
        except Exception as e:
            logger.error(f"Error finalizing group {group_id}: {str(e)}")
            return False
        
    async def remove_competitor_from_group(self, group_id: str, channel_id: str) -> bool:
        try:
            result = await self.db.remove_competitor_from_group(group_id, channel_id)
            return result
        except Exception as e:
            logger.error(f"Error in remove_competitor_from_group: {str(e)}")
            return False
         
    def video_belongs_to_series(self, video: Dict, series: Dict) -> bool:
        video_title = video.get('title', '').lower()
        series_name = series['name'].lower()
        
        if series_name in video_title:
            return True
        
        for theme in series.get('themes', []):
            for topic in theme.get('topics', []):
                if topic['name'].lower() in video_title:
                    return True
        
        logger.debug(f"Video '{video_title}' does not belong to series '{series_name}'")
        return False
    
    async def cache_filtered_results(self, group_id: str, filtered_results: Dict):
        await self.db.competitor_groups.update_one(
            {"_id": ObjectId(group_id)},
            {"$set": {"cached_filtered_results": filtered_results}}
        )
        logger.info(f"Cached filtered results for group {group_id}")

    async def get_cached_filtered_results(self, group_id: str) -> Dict:
        group = await self.db.competitor_groups.find_one({"_id": ObjectId(group_id)})
        return group.get('cached_filtered_results', {})
    
    async def analyze_individual_series(self, group_id: str, series: dict, series_search_results: list):
        series_name = series['name']
        logger.info(f"Analyzing series: {series_name}")
        logger.debug(f"Series structure: {json.dumps(series, indent=2)}")
        logger.debug(f"Series search results (first 5): {json.dumps(series_search_results[:5], indent=2)}")
        
        # Extract titles safely
        titles = []
        for video in series_search_results:
            if isinstance(video, dict):
                title = video.get('snippet', {}).get('title')
                if title:
                    titles.append(title)
            elif isinstance(video, str):
                titles.append(video)
        
        logger.debug(f"Extracted titles (first 5): {titles[:5]}")
        
        shared_series_results = await self.check_shared_series(
            [series],  # Wrap the series in a list
            titles,
            series_name
        )
        
        return shared_series_results
    
    async def search_potential_competitors(self, group_id: str, series_data: List[Dict]):
        logger.info(f"Searching for potential competitors for group {group_id}")
        potential_competitors = {}

        for series in series_data:
            series_name = series['name']
            potential_competitors[series_name] = []

            for theme in series.get('themes', []):
                for topic in theme.get('topics', []):
                    search_query = topic.get('example', '')

                    logger.info(f"Searching for: {search_query} in group {group_id}")
                    search_results = await self.youtube_service.search_videos(search_query, max_results=50)
                    logger.info(f"Found {len(search_results)} search results for query: {search_query} in group {group_id}")

                    filtered_results = await self.filter_search_results(search_results, [series])

                    potential_competitors[series_name].extend(filtered_results)

        return potential_competitors

    async def filter_search_results(self, search_results: List[Dict], series_data: List[Dict]):
        filtered_results = []
        search_result_titles = [result['snippet']['title'] for result in search_results]
        shared_series_results = await check_shared_series(series_data, search_result_titles)

        for result, is_shared in zip(search_results, shared_series_results['shared_series']):
            if is_shared:
                channel_data = await self.youtube_service.fetch_channel_data(result['snippet']['channelId'])
                filtered_results.append({
                    'channel': {
                        'id': channel_data['id'],
                        'title': channel_data['snippet']['title'],
                        'subscriberCount': channel_data['statistics']['subscriberCount'],
                        'videoCount': channel_data['statistics']['videoCount'],
                        'viewCount': channel_data['statistics']['viewCount'],
                        'thumbnails': channel_data['snippet']['thumbnails']
                    },
                    'video': {
                        'id': result['id']['videoId'],
                        'title': result['snippet']['title'],
                        'description': result['snippet']['description'],
                        'thumbnails': result['snippet']['thumbnails'],
                        'publishedAt': result['snippet']['publishedAt']
                    },
                    'matching_series': is_shared['name'],
                    'matching_theme': is_shared['theme'],
                    'matching_topic': is_shared['topic']
                })

        return filtered_results

    def title_matches_series(self, title: str, series: Dict) -> bool:
        series_name = series['name'].lower()
        if series_name in title.lower():
            return True
        for theme in series.get('themes', []):
            for topic in theme.get('topics', []):
                if topic['name'].lower() in title.lower():
                    return True
        return False

    async def rapid_initial_competitor_discovery(self, group_id: str, series_data: List[Dict]):
        logger.info(f"Starting rapid initial competitor discovery for group {group_id}")
        search_results = {}
        potential_competitors = {}
        max_results_per_topic = 50

        try:
            group = await self.db.get_competitor_group(group_id)
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
                            results = await self.youtube_service.search_videos(search_query, max_results=max_results_per_topic)
                            logger.info(f"Found {len(results['videos'])} search results for '{search_query}' using YouTube API")
                            
                            # Store search results
                            search_results[series_name][search_query] = results['videos']
                            
                            # Process results for potential competitors
                            for result in results['videos']:
                                channel_id = result.get('channelId')
                                if channel_id and channel_id != main_channel_id and not any(c['channel']['id'] == channel_id for c in potential_competitors[series_name]):
                                    potential_competitors[series_name].append({
                                        'channel': {
                                            'id': channel_id,
                                            'title': result.get('channelTitle', ''),
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
            await self.db.update_competitor_group(group_id, {
                'search_results': search_results,
                'potential_competitors': potential_competitors
            })

            total_competitors = sum(len(competitors) for competitors in potential_competitors.values())
            logger.info(f"Finished rapid initial competitor discovery for group {group_id}. Found {total_competitors} potential competitors.")
            return potential_competitors

        except Exception as e:
            logger.error(f"Error in rapid_initial_competitor_discovery: {str(e)}")
            raise
    def group_search_results_by_channel(self, search_results, processed_channels):
        channels = {}
        for video in search_results:
            channel_id = video.get('channelId')
            if channel_id and channel_id not in processed_channels:
                if channel_id not in channels:
                    channels[channel_id] = []
                channels[channel_id].append(video)
        return channels
        
    async def process_channel(self, group_id: str, channel_id: str, series_data: List[Dict], main_channel_avg_duration: float):
        try:
            channel_videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=50)
            if not channel_videos:
                logger.warning(f"No videos found for channel {channel_id}")
                return False

            channel_avg_duration = self.calculate_average_duration(channel_videos)
            if abs(channel_avg_duration - main_channel_avg_duration) > 60:  # 1 minute threshold
                logger.debug(f"Channel {channel_id} average duration is not compatible. Main: {main_channel_avg_duration:.2f}s, Channel: {channel_avg_duration:.2f}s")
                return False

            channel_video_titles = [video['title'] for video in channel_videos]
            shared_series_result = await check_shared_series(series_data, channel_video_titles)

            if shared_series_result['is_eligible']:
                competitor_data = await self.youtube_service.fetch_channel_data(channel_id)
                if competitor_data:
                    await self.add_competitor_to_group(group_id, competitor_data, channel_videos, series_data)
                    logger.info(f"Added competitor {channel_id} to group {group_id}. Shared series: {shared_series_result['shared_series_count']}")
                    return True
                else:
                    logger.warning(f"Failed to fetch channel data for {channel_id}")
                    return False
            else:
                logger.debug(f"Channel {channel_id} does not share enough series with the main channel. Shared series: {shared_series_result['shared_series_count']}")
                return False
        except Exception as e:
            logger.error(f"Error processing channel {channel_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
        
    async def filter_competitors(self, potential_competitors: Dict[str, List[Dict]], series_data: List[Dict]) -> Dict[str, List[Dict]]:
        filtered_competitors = {}
        for series_name, competitors in potential_competitors.items():
            filtered_competitors[series_name] = []
            for competitor in competitors:
                video_titles = [competitor['video']['title']]
                shared_series = await self.ai_utils.check_shared_series(series_data, video_titles)
                if shared_series['is_eligible']:
                    filtered_competitors[series_name].append(competitor)
        return filtered_competitors
    

    async def check_videos_in_series(self, series_data: List[Dict], videos: List[Dict]) -> Dict[str, List[Dict]]:
        logger.info("Categorizing videos into series")
        result = {}
        
        for series in series_data:
            series_name = series['name']
            result.setdefault(series_name, [])
            
            for theme in series.get('themes', []):
                theme_name = theme['name']
                
                for topic in theme.get('topics', []):
                    topic_name = topic['name']
                    topic_keywords = set(re.findall(r'\w+', topic_name.lower()))
                    
                    for video in videos:
                        video_title = video.get('title', '').lower()
                        video_keywords = set(re.findall(r'\w+', video_title))
                        
                        # Check if there's significant overlap between video title and topic keywords
                        if len(topic_keywords.intersection(video_keywords)) >= 2:
                            result[series_name].append({
                                'video': video,
                                'theme': theme_name,
                                'topic': topic_name
                            })
        
        # Remove series with no matching videos
        result = {k: v for k, v in result.items() if v}
        return result
    
    async def search_videos_with_fallback(self, query: str, max_results: int = 50) -> List[Dict]:
        try:
            return await self.youtube_service.search_videos(query, max_results=max_results)
        except Exception as e:
            logger.warning(f"YouTube API search failed: {str(e)}. Falling back to youtube-search-python.")
            return await self.youtube_service.search_videos_fallback(query, max_results=max_results)
    
    def count_shared_series(self, main_series_data: List[Dict], competitor_series_data: List[Dict]) -> int:
        shared_count = 0
        for main_series in main_series_data:
            for comp_series in competitor_series_data:
                if main_series['name'] == comp_series['name']:
                    shared_count += 1
                    break
        return shared_count
    
    
    def parse_duration(self, duration: str) -> float:
        match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration)
        if not match:
            return 0
        hours = int(match.group(1)[:-1]) if match.group(1) else 0
        minutes = int(match.group(2)[:-1]) if match.group(2) else 0
        seconds = int(match.group(3)[:-1]) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds

    def are_durations_compatible(self, main_channel_videos, competitor_videos):
        main_channel_durations = [self.parse_duration(video['duration']) for video in main_channel_videos]
        competitor_durations = [self.parse_duration(video['duration']) for video in competitor_videos]
        
        main_channel_avg_duration = statistics.mean(main_channel_durations)
        competitor_avg_duration = statistics.mean(competitor_durations)
        
        duration_difference = abs(main_channel_avg_duration - competitor_avg_duration) / main_channel_avg_duration
        if duration_difference > 0.25:
            logger.info(f"Video durations are not similar. Main: {main_channel_avg_duration:.2f}s, Competitor: {competitor_avg_duration:.2f}s")
            return False
        
        if competitor_avg_duration < 90 and main_channel_avg_duration > 300:
            logger.info(f"Competitor videos are too short compared to main channel. Main: {main_channel_avg_duration:.2f}s, Competitor: {competitor_avg_duration:.2f}s")
            return False
        
        logger.info(f"Durations are compatible. Main: {main_channel_avg_duration:.2f}s, Competitor: {competitor_avg_duration:.2f}s")
        return 0.5 * main_channel_avg_duration <= competitor_avg_duration <= 1.5 * main_channel_avg_duration

    def check_similar_duration(self, main_videos: List[Dict], competitor_videos: List[Dict]) -> bool:
        main_avg_duration = sum(v['duration'] for v in main_videos) / len(main_videos)
        comp_avg_duration = sum(v['duration'] for v in competitor_videos) / len(competitor_videos)
        return abs(main_avg_duration - comp_avg_duration) <= 60  # Within 1 minute difference

    async def analyze_competitors_async(self, group_id: str):
        try:
            competitors = await self.youtube_service.find_competitors(group_id)
            for competitor in competitors:
                await self.db.add_competitor_to_group(group_id, competitor)
            logger.info(f"Competitor analysis completed for group {group_id}")
        except Exception as e:
            logger.error(f"Error in analyze_competitors_async for group {group_id}: {str(e)}")

    async def discover_trends(self, group_id: str):
        try:
            trends = await self.youtube_service.analyze_trends(group_id)
            await self.db.update_group_trends(group_id, trends)
            logger.info(f"Trend discovery completed for group {group_id}")
        except Exception as e:
            logger.error(f"Error in discover_trends for group {group_id}: {str(e)}")

    async def create_initial_group(
        self,
        interaction,  # Can be None for web app
        channel_id: str,
        channel_data: Dict,
        videos: List[Dict],
        group_name: str,
        is_public: bool
    ):
        logger.info(f"Starting create_initial_group for channel {channel_id} with group name '{group_name}'")
        try:
            group_data = {
                "name": group_name,
                "user_id": str(interaction.user.id) if interaction else "web_user",
                "main_channel_id": channel_id,
                "main_channel_data": channel_data,
                "videos": videos,
                "competitors": [],
                "top_performers": [],
                "new_viral_channels": [],
                "categorized_competitors": [],
                "trending_topics": [],
                "is_public": is_public,
                "is_premium": False,
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
                "allowed_users": [str(interaction.user.id)] if interaction else ["web_user"]
            }

            logger.info(f"Creating competitor group in database for channel {channel_id}")
            group_id = await self.db.create_competitor_group(group_data)
            if not group_id:
                logger.error(f"Failed to create competitor group for channel {channel_id}")
                pass  # No interaction needed for web app
                return None
            logger.info(f"Created competitor group with ID: {group_id}")

            return str(group_id)
        except Exception as e:
            logger.error(f"Unexpected error in create_initial_group for channel {channel_id}: {str(e)}")
            logger.error(f"Full error details: {traceback.format_exc()}")
            pass  # No interaction needed for web app
            return None
    
    async def perform_claude_analysis(self, videos: List[Dict], channel_data: Dict, group_id: str):
        logger.info(f"Starting Claude analysis for group {group_id}")
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                video_titles = [video.get('snippet', {}).get('title', 'Unknown Title') for video in videos]
                claude_analysis = await get_claude_analysis(video_titles, channel_data.get('snippet', {}).get('title', 'Unknown Channel'))
                
                if claude_analysis and isinstance(claude_analysis, list) and len(claude_analysis) > 0:
                    logger.info(f"Valid Claude analysis received for group {group_id}")
                    return claude_analysis
                else:
                    logger.warning(f"Invalid Claude analysis received for group {group_id}. Retrying...")
            except Exception as e:
                logger.error(f"Error in Claude API call for group {group_id} (attempt {attempt + 1}): {str(e)}")
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying Claude analysis for group {group_id} in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
        
        logger.error(f"Max retries reached for Claude API call for group {group_id}")
        return self.create_default_series(videos)
    
    async def process_series_data(self, claude_analysis: List[Dict], group_id: str):
        logger.info(f"Processing Claude analysis results for group {group_id}")
        processed_series_data = []

        for series in claude_analysis:
            try:
                series_name = series.get('name', 'Unknown Series')
                series_doc = await self.db.create_series(str(group_id), series_name)
                series_data = {"name": series_name, "themes": []}

                for theme in series.get('themes', []):
                    theme_name = theme.get('name', 'Unnamed Theme')
                    await self.db.add_theme_to_series(str(series_doc), theme_name)
                    theme_data = {"name": theme_name, "topics": []}

                    for topic in theme.get('topics', []):
                        topic_name = topic.get('name', 'Unnamed Topic')
                        topic_example = topic.get('example', '')
                        await self.db.add_topic_to_theme(str(series_doc), theme_name, topic_name, topic_example)
                        theme_data['topics'].append({"name": topic_name, "example": topic_example})
                    
                    series_data['themes'].append(theme_data)
                
                processed_series_data.append(series_data)
            except Exception as e:
                logger.error(f"Error processing series '{series.get('name', 'Unknown')}' for group {group_id}: {str(e)}")
                logger.error(f"Full error details: {traceback.format_exc()}")
        
        return processed_series_data

    async def analyze_competitors_async(self, group_id: str):
        logger.info(f"Entered analyze_competitors_async for group {group_id}")
        try:
            logger.info(f"Starting rapid initial competitor discovery for group {group_id}")
            await self.rapid_initial_competitor_discovery(group_id)
            logger.info(f"Completed rapid initial competitor discovery for group {group_id}")
            
            logger.info(f"Starting continuous competitor analysis for group {group_id}")
            asyncio.create_task(self.continuous_competitor_analysis(group_id))
            logger.info(f"Continuous competitor analysis task created for group {group_id}")
        except Exception as e:
            logger.error(f"Error in analyze_competitors_async for group {group_id}: {str(e)}")
            logger.error(traceback.format_exc())

    async def continuous_competitor_analysis(self, group_id: str):
        logger.info(f"Starting continuous_competitor_analysis for group {group_id}")
        iteration_count = 0
        while True:
            try:
                iteration_count += 1
                logger.info(f"Beginning iteration {iteration_count} of continuous analysis for group {group_id}")
                
                group = await self.db.get_competitor_group(group_id)
                if not group:
                    logger.error(f"Group {group_id} not found. Stopping continuous analysis.")
                    break
                
                main_channel_videos = group['main_channel_data']['videos']
                series_data = await self.db.get_series_data(group_id)
                logger.info(f"Retrieved {len(main_channel_videos)} videos for main channel in group {group_id}")

                for series in series_data:
                    for theme in series['themes']:
                        for topic in theme['topics']:
                            logger.info(f"Processing search results for topic '{topic['name']}' in group {group_id}")
                            new_competitors = await self.process_search_results(group_id, topic['example'], series_data, main_channel_videos)
                            logger.info(f"Found {new_competitors} new competitors for topic '{topic['name']}' in group {group_id}")

                logger.info(f"Updating group metrics for group {group_id}")
                await self.update_group_metrics(group_id)
                
                logger.info(f"Identifying top performers for group {group_id}")
                await self.identify_top_performers(group_id)
                
                logger.info(f"Categorizing competitors for group {group_id}")
                await self.categorize_competitors(group_id)
                
                logger.info(f"Extracting trending topics for group {group_id}")
                await self.extract_trending_topics(group_id)

                logger.info(f"Completed iteration {iteration_count} of continuous analysis for group {group_id}")
                
                wait_time = 60
                logger.info(f"Waiting for {wait_time} seconds before next iteration for group {group_id}")
                await asyncio.sleep(wait_time)

            except Exception as e:
                logger.error(f"Error in iteration {iteration_count} of continuous_competitor_analysis for group {group_id}: {str(e)}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                
                retry_wait_time = 300
                logger.info(f"Waiting for {retry_wait_time} seconds before retrying for group {group_id}")
                await asyncio.sleep(retry_wait_time)

            finally:
                logger.info(f"Finished iteration {iteration_count} for group {group_id}")

    async def process_search_results(self, group_id: str, topic: Dict, series_data: List[Dict], main_channel_videos: List[Dict]):
        logger.info(f"Starting process_search_results for group {group_id}")
        potential_competitors = {}
        processed_channels = set()

        example_title = topic.get('example', '')
        logger.info(f"Searching for videos with title: '{example_title}'")

        try:
            search_results = await self.youtube_service.search_videos(example_title, max_results=50)
            logger.info(f"Found {len(search_results)} search results for '{example_title}'")
        except Exception as e:
            logger.error(f"Error searching videos for topic '{example_title}': {str(e)}")
            return potential_competitors

        search_result_titles = [video['snippet']['title'] for video in search_results]
        logger.info(f"Collected {len(search_result_titles)} video titles from search results")

        shared_series_results = await check_shared_series(series_data, search_result_titles)
        logger.info(f"Shared series results: {json.dumps(shared_series_results, indent=2)}")

        if not shared_series_results['is_eligible']:
            logger.info("No shared series found. Skipping further processing.")
            return potential_competitors

        for video in search_results:
            channel_id = video['snippet']['channelId']
            if channel_id in processed_channels or channel_id == group_id:
                continue

            processed_channels.add(channel_id)

            matching_series = [series for series in shared_series_results['shared_series'] if video['snippet']['title'] in series['matching_titles']]
            
            if matching_series:
                logger.info(f"Channel {channel_id} shares series: {[series['name'] for series in matching_series]}")
                try:
                    # Get channel videos to check for shorts
                    channel_videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=10)
                    
                    # Skip if primarily shorts channel
                    shorts_count = sum(1 for v in channel_videos if v.get('duration_seconds', 0) < 60)
                    if shorts_count / len(channel_videos) > 0.5:  # If more than 50% are shorts
                        logger.info(f"Skipping channel {channel_id} - primarily shorts content")
                        continue

                    channel_data = await self.youtube_service.fetch_channel_data(channel_id)
                    video_details = await self.youtube_service.get_video_details(video['id']['videoId'])
                    
                    for series in matching_series:
                        if series['name'] not in potential_competitors:
                            potential_competitors[series['name']] = []
                        
                        potential_competitors[series['name']].append({
                            'channel': {
                                'id': channel_data['id'],
                                'title': channel_data['snippet']['title'],
                                'thumbnails': channel_data['snippet']['thumbnails'],
                                'subscriberCount': channel_data['statistics']['subscriberCount'],
                                'videoCount': channel_data['statistics']['videoCount'],
                                'viewCount': channel_data['statistics']['viewCount']
                            },
                            'video': {
                                'id': video_details['id'],
                                'title': video_details['snippet']['title'],
                                'thumbnails': video_details['snippet']['thumbnails'],
                                'publishedAt': video_details['snippet']['publishedAt'],
                                'duration': video_details['contentDetails']['duration'],
                                'viewCount': video_details['statistics']['viewCount'],
                                'likeCount': video_details['statistics'].get('likeCount', '0'),
                                'commentCount': video_details['statistics'].get('commentCount', '0')
                            },
                            'matching_series': series['name']
                        })
                except Exception as e:
                    logger.error(f"Error fetching data for channel {channel_id}: {str(e)}")

        return potential_competitors
    
    async def is_eligible_competitor(self, main_channel_videos: List[Dict], competitor_videos: List[Dict], competitor_channel_id: str, group_id: str) -> bool:
        main_channel_durations = [self.parse_duration(video['duration']) for video in main_channel_videos]
        competitor_durations = [self.parse_duration(video['duration']) for video in competitor_videos]
        
        main_channel_avg_duration = statistics.mean(main_channel_durations) if main_channel_durations else 0
        competitor_avg_duration = statistics.mean(competitor_durations) if competitor_durations else 0
        
        logger.info(f"Main channel average duration: {main_channel_avg_duration:.2f} seconds")
        logger.info(f"Competitor channel average duration: {competitor_avg_duration:.2f} seconds")
        
        if main_channel_avg_duration == 0 or competitor_avg_duration == 0:
            logger.warning(f"Average duration is 0 for main channel or competitor {competitor_channel_id}")
            return False
        
        duration_compatible = self.are_durations_compatible(main_channel_videos, competitor_videos)
        
        main_channel_titles = [video['title'] for video in main_channel_videos]
        competitor_titles = [video['title'] for video in competitor_videos]
        
        shared_series_result = await self.check_shared_series(main_channel_titles, competitor_titles)
        
        logger.info(f"Shared series result for channel {competitor_channel_id}: {shared_series_result}")
        
        if not shared_series_result['is_eligible'] or shared_series_result['shared_series_count'] < 2:
            logger.info(f"Channel {competitor_channel_id} is not eligible as a competitor for group {group_id}. Reason: Insufficient shared series: {shared_series_result['shared_series_count']} (required: 2)")
            return False
        
        return duration_compatible

    def categorize_videos_by_series(self, videos: List[Dict], series_data: List[Dict]):
        video_titles = [video['title'] for video in videos]
        return check_videos_in_series(series_data, video_titles)
    
    async def check_series_compatibility(self, competitor_videos: List[Dict], series_data: List[Dict]) -> bool:
        categorized_videos = await self.check_videos_in_series(series_data, competitor_videos)
        shared_series_count = sum(1 for videos in categorized_videos.values() if len(videos) >= 2)
        return shared_series_count >= 2

    async def add_competitor_to_group(self, group_id: str, channel_id: str, matching_title: str, matching_series: List[Dict]):
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
                    "thumbnail_url": video.get('thumbnail_url', '')  # Correct access
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
            
            result = await self.db.add_competitor_to_group(group_id, competitor)
            if result:
                logger.info(f"Added competitor {competitor['channel_id']} to group {group_id}. Shared series: {len(matching_series)}")
                return competitor
            else:
                logger.warning(f"Failed to add competitor {competitor['channel_id']} to group {group_id}")
                return None

        except Exception as e:
            logger.error(f"Error adding competitor {channel_id} to group {group_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    async def get_shared_series(self, competitor_videos: List[Dict], series_data: List[Dict]) -> int:
        shared_series = 0
        for series in series_data:
            series_name = series['name']
            for video in competitor_videos:
                if series_name.lower() in video['title'].lower():
                    shared_series += 1
                    break
        return shared_series
    
    def find_shared_series(self, competitor_videos: List[Dict], series_data: List[Dict]) -> List[Dict]:
        shared_series = []
        for series in series_data:
            series_name = series['name']
            series_videos = [video for video in competitor_videos if self.video_matches_series(video, series)]
            if len(series_videos) >= 2:
                shared_series.append({
                    'name': series_name,
                    'videos': series_videos
                })
        return shared_series

    def video_matches_series(self, video: Dict, series: Dict) -> bool:
        video_title = video.get('title', '').lower()
        for theme in series.get('themes', []):
            for topic in theme.get('topics', []):
                if topic['name'].lower() in video_title:
                    return True
        return False

    def prepare_series_check_data(series_data: List[Dict], competitor_videos: List[Dict]):
        series_examples = []
        for series in series_data:
            for theme in series['themes']:
                for topic in theme['topics']:
                    series_examples.append(f"{series['name']} - Example: {topic['example']}")
        
        competitor_titles = [video['snippet']['title'] for video in competitor_videos]
        
        return series_examples, competitor_titles

    async def process_claude_analysis(self, group_id: str, claude_analysis: List[Dict]):
        for series in claude_analysis:
            series_id = await self.db.series.insert_one({
                "group_id": ObjectId(group_id),
                "name": series['name'],
                "themes": series.get('themes', [])
            })
            logger.info(f"Created series '{series['name']}' with ID {series_id.inserted_id} for group {group_id}")
        
        await self.db.update_group_series_data(group_id, claude_analysis)

    def calculate_upload_frequency(self, videos: List[Dict]) -> float:
        if not videos:
            return 0.0
        
        upload_dates = [datetime.fromisoformat(video['publishedAt'].rstrip('Z')).replace(tzinfo=timezone.utc) for video in videos]
        oldest_video_date = min(upload_dates)
        newest_video_date = max(upload_dates)
        
        time_span = max((newest_video_date - oldest_video_date).days, 1)  # Ensure at least 1 day
        months = time_span / 30.44  # Average number of days in a month
        
        return round(len(videos) / months, 2)  # Round to 2 decimal places
    
    async def perform_competitor_series_analysis(self, group_id: str, competitor_id: str):
        competitor = await self.db.get_competitor(group_id, competitor_id)
        if competitor['series_analyzed']:
            return

        video_titles = [video['title'] for video in competitor['videos']]
        claude_analysis = await get_claude_analysis(video_titles, competitor['title'])
        
        series_data = parse_claude_response(claude_analysis)
        
        await self.db.update_competitor_series_data(group_id, competitor_id, series_data)
        await self.db.set_competitor_series_analyzed(group_id, competitor_id, True)
        
        logger.info(f"Performed series analysis for competitor {competitor_id} in group {group_id}")

    def estimate_monthly_views(self, videos: List[Dict]) -> int:
        if not videos:
            return 0
        
        total_views = sum(int(v.get('viewCount', 0)) for v in videos)
        upload_dates = [datetime.fromisoformat(video['publishedAt'].rstrip('Z')).replace(tzinfo=timezone.utc) for video in videos]
        oldest_video_date = min(upload_dates)
        newest_video_date = max(upload_dates)
        
        months_active = max((newest_video_date - oldest_video_date).days / 30.44, 1)  # Ensure at least 1 month
        
        return int(total_views / months_active)
    
    def categorize_video_by_series(self, video, series_data):
        video_title = video['title'].lower()
        for series in series_data:
            for theme in series['themes']:
                for topic in theme['topics']:
                    if topic['name'].lower() in video_title:
                        return series['name']
        return None

    def estimate_monthly_subscriber_growth(self, channel_data: Dict) -> float:
        try:
            subscriber_count = int(channel_data.get('statistics', {}).get('subscriberCount', 0))
            published_at = channel_data.get('snippet', {}).get('publishedAt')
            
            if not published_at:
                logger.warning(f"publishedAt not found for channel {channel_data.get('id')}. Using default growth rate.")
                return subscriber_count * 0.01  # Assume 1% monthly growth as a default
            
            channel_age = datetime.now(timezone.utc) - datetime.fromisoformat(published_at.rstrip('Z')).replace(tzinfo=timezone.utc)
            months = channel_age.days / 30.44  # Average number of days in a month
            
            if months == 0:
                return 0
            
            monthly_growth = subscriber_count / months
            return monthly_growth
        except Exception as e:
            logger.error(f"Error estimating monthly subscriber growth: {str(e)}")
            return 0

    def calculate_growth_score(self, channel_data: Dict, videos: List[Dict]) -> float:
        monthly_views = self.estimate_monthly_views(videos)
        monthly_sub_growth = self.estimate_monthly_subscriber_growth(channel_data)
        upload_frequency = self.calculate_upload_frequency(videos)
        
        view_score = monthly_views / 1000  # Normalize views
        sub_score = monthly_sub_growth * 10  # Weight subscriber growth more heavily
        frequency_score = upload_frequency * 5  # Consider upload frequency
        
        total_score = view_score + sub_score + frequency_score
        
        return round(total_score, 2)  # Round to 2 decimal places for readability
    
    async def continuous_competitor_discovery(self, group_id: str, batch_size: int = 5) -> int:
        try:
            logger.info(f"Starting continuous competitor discovery for group {group_id}")
            group = await self.db.get_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return 0

            discovered_competitors = 0
            series_data = group.get('series_data', [])

            # Generate example titles from the main channel's series data
            example_titles = [topic['example'] for series in series_data for theme in series['themes'] for topic in theme['topics'] if 'example' in topic]

            for title in example_titles:
                logger.info(f"Searching for: {title} in group {group_id}")
                search_results = await self.youtube_service.search_videos(title, max_results=50)
                logger.info(f"Found {len(search_results)} search results for title: {title} in group {group_id}")

                search_result_titles = [result['snippet']['title'] for result in search_results if 'snippet' in result and 'title' in result['snippet']]
                
                # Get the current series name
                current_series_name = next((series['name'] for series in series_data if title.startswith(series['name'])), None)
                
                if current_series_name:
                    shared_series_results = await self.check_shared_series(series_data, search_result_titles, current_series_name)

                    if shared_series_results['is_eligible']:
                        for shared_series in shared_series_results['shared_series']:
                            for matching_title in shared_series['matching_titles']:
                                matching_video = next((video for video in search_results if video.get('snippet', {}).get('title', '') == matching_title), None)
                                if matching_video and 'snippet' in matching_video:
                                    channel_id = matching_video['snippet']['channelId']
                                    try:
                                        competitor_data = await self.youtube_service.fetch_channel_data(channel_id)
                                        video_data = await self.youtube_service.get_video_details(matching_video['id']['videoId'])
                                        
                                        potential_competitor = {
                                            'channel': competitor_data,
                                            'video': video_data,
                                            'matching_series': shared_series['name'],
                                            'matching_theme': shared_series['theme'],
                                            'matching_topic': shared_series['topic']
                                        }
                                        
                                        # Store the potential competitor in the database
                                        await self.db.add_potential_competitor(group_id, potential_competitor)
                                        
                                        discovered_competitors += 1
                                        logger.info(f"Added new potential competitor: {channel_id} to group {group_id}")

                                        if discovered_competitors >= batch_size:
                                            logger.info(f"Reached batch size of {batch_size} new potential competitors for group {group_id}")
                                            return discovered_competitors
                                    except Exception as e:
                                        logger.error(f"Error processing potebn ntial competitor {channel_id} for group {group_id}: {str(e)}")
                                        logger.error(f"Full traceback: {traceback.format_exc()}")

                await asyncio.sleep(5)  # Add a 5-second delay between processing each search query

            logger.info(f"Completed continuous competitor discovery for group {group_id}. Discovered {discovered_competitors} new potential competitors.")
            return discovered_competitors
        except Exception as e:
            logger.error(f"Unexpected error in continuous_competitor_discovery for group {group_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return 0
    
    def calculate_average_duration(self, videos: List[Dict]) -> float:
        durations = [self.parse_duration(video['contentDetails']['duration']) for video in videos if 'contentDetails' in video]
        return sum(durations) / len(durations) if durations else 0

    async def update_group_metrics(self, group_id: str):
        logger.info(f"Updating group metrics for group {group_id}")
        competitors = await self.db.get_competitors(group_id)
        
        total_monthly_views = sum(c['monthlyViews'] for c in competitors)
        total_monthly_subs = sum(c['monthlySubscriberGrowth'] for c in competitors)
        total_upload_frequency = sum(c['uploadFrequency'] for c in competitors)
        
        avg_monthly_views = total_monthly_views / len(competitors) if competitors else 0
        avg_monthly_subs = total_monthly_subs / len(competitors) if competitors else 0
        avg_upload_frequency = total_upload_frequency / len(competitors) if competitors else 0
        
        await self.db.update_group_performance_data(group_id, {
            "avg_monthly_views": avg_monthly_views,
            "avg_monthly_subs": avg_monthly_subs,
            "avg_upload_frequency": avg_upload_frequency,
            "total_competitors": len(competitors)
        })
        logger.info(f"Group metrics updated for group {group_id}")
    
    async def identify_top_performers(self, group_id: str):
        logger.info(f"Identifying top performers for group {group_id}")
        competitors = await self.db.get_competitors(group_id)
        top_performers = {
            "subscribers": max(competitors, key=lambda x: x['subscriberCount']),
            "views": max(competitors, key=lambda x: x['viewCount']),
            "growth": max(competitors, key=lambda x: x['growth_score'])
        }
        await self.db.update_top_performers(group_id, top_performers)
        logger.info(f"Top performers identified for group {group_id}")

    async def categorize_competitors(self, group_id: str):
        logger.info(f"Categorizing competitors for group {group_id}")
        competitors = await self.db.get_competitors(group_id)
        categories = {
            "Newcomer Content": [c for c in competitors if 0 <= c['subscriberCount'] <= 1000],
            "Rising Creators": [c for c in competitors if 1001 <= c['subscriberCount'] <= 10000],
            "Emerging Stars": [c for c in competitors if 10001 <= c['subscriberCount'] <= 100000],
            "Established Channels": [c for c in competitors if 100001 <= c['subscriberCount'] <= 1000000],
            "Industry Giants": [c for c in competitors if c['subscriberCount'] > 1000000]
        }
        await self.db.update_categorized_competitors(group_id, categories)
        logger.info(f"Competitors categorized for group {group_id}")

    async def extract_trending_topics(self, group_id: str):
        logger.info(f"Extracting trending topics for group {group_id}")
        competitors = await self.db.get_competitors(group_id)
        all_titles = [video['title'] for competitor in competitors for video in competitor['videos']]
        trending_topics = self.content_generation_service.extract_trending_topics(all_titles)
        await self.db.update_trending_topics(group_id, trending_topics)
        logger.info(f"Trending topics extracted for group {group_id}")

    async def get_group_analysis(self, group_id: str):
        group = await self.db.get_competitor_group(group_id)
        if not group:
            return {"error": "Group not found"}

        return {
            "group_name": group['name'],
            "main_channel": group['main_channel_data'],
            "competitors": group['competitors'],
            "top_performers": group['top_performers'],
            "new_viral_channels": group['new_viral_channels'],
            "categorized_competitors": group['categorized_competitors'],
            "trending_topics": group['trending_topics'],
            "performance_data": group['performance_data'],
            "performance_distribution": group['performance_distribution'],
            "comparative_analysis": group['comparative_analysis']
        }

    async def generate_series_data(self, group_id: str, videos: List[Dict], channel_data: Dict):
        logger.info(f"Generating series data for group {group_id}")
        video_titles = [video.get('title', '') for video in videos]
        channel_title = channel_data.get('title', 'Unknown Channel')

        logger.info(f"Extracted {len(video_titles)} video titles")
        logger.info(f"First few titles: {video_titles[:5]}")

        if not video_titles:
            logger.warning(f"No valid video titles found for group {group_id}. Using default series.")
            return self.create_default_series(videos)

        try:
            series_data = await get_claude_analysis(video_titles, channel_title)
            
            if not series_data or not isinstance(series_data, list) or len(series_data) == 0:
                logger.warning(f"Invalid Claude analysis for group {group_id}. Using default series.")
                return self.create_default_series(videos)

            logger.info(f"Generated {len(series_data)} series for group {group_id}")
            return series_data
        except Exception as e:
            logger.error(f"Error generating series data for group {group_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return self.create_default_series(videos)
        
    async def analyze_competitor_channels(self, group_id: str):
        try:
            group = await self.db.get_competitor_group(group_id)
            if not group: 
                logger.error(f"Group {group_id} not found")
                return False

            all_video_data = []
            channel_video_map = {}

            # Add main channel to the analysis
            main_channel_id = group.get('main_channel_id')
            if main_channel_id:
                main_channel_data = group.get('main_channel_data', {})
                main_channel_videos = main_channel_data.get('videos', [])
                main_channel_video_data = [{
                    'id': video.get('id'),
                    'title': video.get('title', '').strip(), 
                    'views': int(video.get('viewCount', 0)),
                    'thumbnail': video.get('thumbnail_url', ''),
                    'channel_id': main_channel_id,
                    'published_at': video.get('publishedAt', '')
                } for video in main_channel_videos if video.get('id')]
                
                if main_channel_video_data:
                    all_video_data.extend(main_channel_video_data)
                    channel_video_map[main_channel_id] = main_channel_video_data

            # Process competitors
            competitors = group.get('competitors', [])
            for competitor in competitors:
                channel_id = competitor['channel_id']
                videos = competitor.get('videos', [])
                
                if not videos:
                    logger.warning(f"No videos found for competitor {channel_id}")
                    continue

                try:
                    channel_video_data = [{
                        'id': video['videoId'],
                        'title': video['title'].strip(),
                        'views': int(video['viewCount']),
                        'thumbnail': video.get('thumbnail_url', ''),
                        'channel_id': channel_id,
                        'published_at': video.get('publishedAt', '')
                    } for video in videos if video.get('videoId')]
                    
                    if channel_video_data:
                        all_video_data.extend(channel_video_data)
                        channel_video_map[channel_id] = channel_video_data
                except Exception as e:
                    logger.error(f"Error processing competitor {channel_id}: {e}")
                    continue  # Ensure we continue processing other competitors

            if not all_video_data:
                logger.error(f"No videos found for any channels in group {group_id}")
                return False

            # Get and clean series data for all videos
            series_data = await get_claude_analysis(all_video_data, "All Competitors")
            if not series_data:
                logger.error("Failed to get series analysis")
                return False

            cleaned_series_data = self.clean_series_data(series_data, all_video_data)

            # Update competitors' series data
            for competitor in competitors:
                channel_id = competitor['channel_id']
                if channel_id not in channel_video_map:
                    continue

                channel_series_data = self.filter_series_data_for_channel(
                    cleaned_series_data, 
                    channel_id, 
                    channel_video_map[channel_id]
                )
                
                # Calculate averages and ensure proper structure
                for series in channel_series_data:
                    total_views = sum(theme.get('total_views', 0) for theme in series.get('themes', []))
                    video_count = sum(theme.get('video_count', 0) for theme in series.get('themes', []))
                    series['avg_views'] = total_views / video_count if video_count > 0 else 0
                    series['video_count'] = video_count
                    series['channels_with_series'] = [channel_id]
                    
                    # Process themes
                    for theme in series.get('themes', []):
                        theme['channels_with_theme'] = [channel_id]
                        if not theme.get('topics'):
                            theme['topics'] = []

                # Update competitor's series_data in memory
                competitor['series_data'] = channel_series_data

            # Handle main channel series data
            if main_channel_id and main_channel_id in channel_video_map:
                main_channel_series_data = self.filter_series_data_for_channel(
                    cleaned_series_data, 
                    main_channel_id, 
                    channel_video_map[main_channel_id]
                )
                
                # Calculate averages and ensure proper structure
                for series in main_channel_series_data:
                    total_views = sum(theme.get('total_views', 0) for theme in series.get('themes', []))
                    video_count = sum(theme.get('video_count', 0) for theme in series.get('themes', []))
                    series['avg_views'] = total_views / video_count if video_count > 0 else 0
                    series['video_count'] = video_count
                    series['channels_with_series'] = [main_channel_id]
                    
                    for theme in series.get('themes', []):
                        theme['channels_with_theme'] = [main_channel_id]
                        if not theme.get('topics'):
                            theme['topics'] = []

                # Update main channel data in memory
                group['main_channel_data']['series_data'] = main_channel_series_data
                # Add this line to update group['series_data']
                group['series_data'] = main_channel_series_data

            # Update the entire group document
            await self.db.update_competitor_group(group_id, {
                'competitors': competitors,
                'main_channel_data': group['main_channel_data'],
                'series_data': group['series_data']  # Include the updated series_data
            })

            logger.info(f"Successfully completed series analysis for group {group_id}")
            return True

        except Exception as e:
            logger.error(f"Error in analyze_competitor_channels: {e}", exc_info=True)
            return False
    
    def filter_series_data_for_channel(self, series_data, channel_id, channel_videos):
        channel_series_data = []
        for series in series_data:
            channel_series = {
                "name": series["name"],
                "themes": [],
                "total_views": 0,
                "video_count": 0,
                "channels_with_series": series.get("channels_with_series", [])
            }
            for theme in series["themes"]:
                channel_theme = {
                    "name": theme["name"],
                    "topics": [],
                    "total_views": 0,
                    "video_count": 0
                }
                for topic in theme["topics"]:
                    if any(video['title'] == topic['example'] and video['channel_id'] == channel_id for video in channel_videos):
                        channel_theme["topics"].append(topic)
                        channel_theme["total_views"] += topic["views"]
                        channel_theme["video_count"] += 1
                if channel_theme["topics"]:
                    channel_series["themes"].append(channel_theme)
                    channel_series["total_views"] += channel_theme["total_views"]
                    channel_series["video_count"] += channel_theme["video_count"]
            if channel_series["themes"]:
                channel_series_data.append(channel_series)
        return channel_series_data
    
    def clean_series_data(self, series_data, video_data):
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
        logger.debug(f"Cleaned series data: {cleaned_data}")
        
        for series in cleaned_data:
            logger.debug(f"Series '{series['name']}' has {series['video_count']} videos with total views {series['total_views']} and avg views {series.get('avg_views', 0):,.2f}")
        
        return cleaned_data

    def create_default_series(self, videos):
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
    
    async def add_channel_by_url(self, group_id: str, channel_url: str) -> Dict:
        try:
            # Extract channel ID from URL
            channel_id = await self.youtube_service.get_channel_id_from_url(channel_url)
            if not channel_id:
                return {"success": False, "error": "Invalid channel URL"}

            # Check if channel already exists in group
            existing = await self.db.is_competitor(group_id, channel_id)
            if existing:
                return {"success": False, "error": "Channel already exists in group"}

            # Fetch channel data and videos
            competitor_data = await self.youtube_service.fetch_channel_data(channel_id)
            if not competitor_data:
                return {"success": False, "error": "Failed to fetch channel data"}

            # Get channel's recent videos to analyze
            videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=50)
            if not videos:
                return {"success": False, "error": "Failed to fetch channel videos"}

            # Create a basic matching series entry
            matching_series = [{
                "name": "Manual Addition",
                "matching_titles": [videos[0]['title']]  # Use first video as example
            }]

            # Add competitor to group
            competitor = await self.add_competitor_to_group(
                group_id,
                channel_id,
                videos[0]['title'],  # Use first video title as matching title
                matching_series
            )

            if competitor:
                return {"success": True, "competitor": competitor}
            else:
                return {"success": False, "error": "Failed to add competitor to group"}

        except Exception as e:
            logger.error(f"Error in add_channel_by_url: {str(e)}")
            return {"success": False, "error": str(e)}

    async def analyze_audience_demographics(self, comments: List[Dict]) -> Dict:
        """
        Analyze comment demographics using AI utils
        """
        return await ai_utils.analyze_audience_demographics(comments)