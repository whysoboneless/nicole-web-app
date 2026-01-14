import os
import asyncio
import logging
import re  # Add re import
from typing import List, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from aiocache import cached
from aiocache.serializers import PickleSerializer
from datetime import datetime, timedelta
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import time
import random
from typing import Any, Dict, Optional  # Add this import at the top of the file
from cachetools import TTLCache
import feedparser
from youtubesearchpython.__future__ import (
    VideosSearch,
    ChannelsSearch,
    PlaylistsSearch,
    CustomSearch
)
from youtubesearchpython import Channel
import ssl
import traceback
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ssl import SSLError
from aiohttp import ClientError
from functools import wraps
from googleapiclient.discovery import build
import random
from config import YOUTUBE_API_KEYS
import json
import isodate  # Make sure to add this to requirements.txt
import google_auth_oauthlib
from utils.ai_utils import generate_search_terms, extract_keywords_from_titles
# Optional token fallback if defined in ai_utils
try:
    from utils.ai_utils import REPLICATE_API_TOKEN as AIUTILS_REPLICATE_TOKEN  # type: ignore
except Exception:
    AIUTILS_REPLICATE_TOKEN = None
from typing import Optional  # used in local whisper fallback
import aiohttp

logger = logging.getLogger(__name__)

def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: tuple = (Exception,)
):
    """
    A simple circuit breaker decorator.
    Closes the circuit after a number of consecutive failures.
    Opens the circuit for a specified timeout upon reaching the failure threshold.
    """
    def decorator(func):
        failure_count = 0
        circuit_open = False
        last_failure_time = None

        @wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal failure_count, circuit_open, last_failure_time

            if circuit_open:
                current_time = time.time()
                if current_time - last_failure_time > recovery_timeout:
                    circuit_open = False
                    failure_count = 0
                    logger.info("Circuit closed. Resuming operations.")
                else:
                    logger.error("Circuit is open. Rejecting the request.")
                    raise Exception("Circuit is open. Please try again later.")

            try:
                result = await func(*args, **kwargs)
                failure_count = 0  # Reset after a successful call
                return result
            except expected_exception as e:
                failure_count += 1
                last_failure_time = time.time()
                logger.warning(f"Circuit breaker: Failure {failure_count} for function '{func.__name__}'.")

                if failure_count >= failure_threshold:
                    circuit_open = True
                    logger.error(f"Circuit breaker: Circuit opened due to {failure_count} consecutive failures.")

                raise e  # Re-raise the exception after handling

        return wrapper
    return decorator

class YouTubeService:
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("No YouTube API keys provided")
        self.api_keys = api_keys
        self.current_key_index = 0
        self.youtube = self._create_youtube_client()
        self.daily_quota = 10000  # Total quota per day per key
        self.quota_remaining = {key: self.daily_quota for key in self.api_keys}
        self.quota_reset_time = {key: time.time() + 86400 for key in self.api_keys}
        self.key_cooldown = {key: 0 for key in self.api_keys}  # Cooldown tracker
        self.lock = asyncio.Lock()
        self.cache = TTLCache(maxsize=1000, ttl=3600)
        self.last_request_time = 0
        self.min_time_between_requests = 1  # 1 second
        
        # Log how many API keys we have available
        logger.info(f"YouTube service initialized with {len(api_keys)} API keys")
        for i, key in enumerate(api_keys):
            key_preview = key[:4] + "..." + key[-4:] if len(key) > 10 else key
            logger.info(f"API key {i+1}/{len(api_keys)}: {key_preview}")
        
        self.oauth_config = {
            'client_id': os.getenv('YOUTUBE_CLIENT_ID'),
            'client_secret': os.getenv('YOUTUBE_CLIENT_SECRET'),
            'redirect_uri': os.getenv('YOUTUBE_REDIRECT_URI'),
            'scopes': [
                'https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/yt-analytics.readonly',
                'https://www.googleapis.com/auth/youtube.upload'
            ]
        }

    def _create_youtube_client(self):
        return build('youtube', 'v3', developerKey=self.api_keys[self.current_key_index])

    @retry(
        stop=stop_after_attempt(10),  # Increase retry limit to accommodate more API keys
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((SSLError, ConnectionError, HttpError)),
        reraise=True
    )
    async def _rotate_api_key(self):
        async with self.lock:
            # Check how many keys we have
            logger.info(f"Rotating API key. Have {len(self.api_keys)} API keys available.")
            
            # Create a set to track which keys we've already tried in this rotation cycle
            tried_keys = set()
            
            # Try each key once
            for _ in range(len(self.api_keys)):
                self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
                current_key = self.api_keys[self.current_key_index]
                
                # Skip if we've already tried this key in this rotation cycle
                if self.current_key_index in tried_keys:
                    continue
                    
                tried_keys.add(self.current_key_index)
                
                current_time = time.time()
                if current_time >= self.quota_reset_time[current_key]:
                    self.quota_remaining[current_key] = self.daily_quota
                    self.quota_reset_time[current_key] = current_time + 86400
                    self.key_cooldown[current_key] = 0
                    logger.info(f"YouTube API quota has been reset for key {self.current_key_index+1}/{len(self.api_keys)}.")
                
                if self.quota_remaining[current_key] > 0 and current_time >= self.key_cooldown[current_key]:
                    logger.info(f"Switched to API key {self.current_key_index+1}/{len(self.api_keys)} with {self.quota_remaining[current_key]} quota remaining.")
                    self.youtube = self._create_youtube_client()
                    return
            
            # If we get here, we couldn't find a valid key
            logger.error(f"All {len(self.api_keys)} YouTube API keys are exhausted or in cooldown.")
            raise Exception("No available YouTube API keys.")

    async def _update_quota(self, cost: int):
        async with self.lock:
            # First check if any key has quota available
            if not await self._any_key_available(cost):
                logger.error(f"All YouTube API keys ({len(self.api_keys)}) are exhausted. Falling back to non-API methods.")
                raise Exception("No YouTube API keys with sufficient quota available.")
            
            current_key = self.api_keys[self.current_key_index]
            if self.quota_remaining[current_key] < cost:
                await self._rotate_api_key()
                return await self._update_quota(cost)

            self.quota_remaining[current_key] -= cost
            logger.debug(f"YouTube API quota updated for key {self.current_key_index}. Remaining: {self.quota_remaining[current_key]}")

            if self.quota_remaining[current_key] <= 0:
                self.key_cooldown[current_key] = time.time() + 3600  # 1 hour cooldown
                await self._rotate_api_key()

    async def _any_key_available(self, cost: int = 1) -> bool:
        """Check if any API key has sufficient quota available"""
        current_time = time.time()
        for i, key in enumerate(self.api_keys):
            # Reset quota if needed
            if current_time >= self.quota_reset_time[key]:
                self.quota_remaining[key] = self.daily_quota
                self.quota_reset_time[key] = current_time + 86400
                self.key_cooldown[key] = 0
                return True
                
            # Check if this key has quota and is not in cooldown
            if self.quota_remaining[key] >= cost and current_time >= self.key_cooldown[key]:
                return True
                
        # If we get here, no key is available
        return False
    
    async def _make_api_request(self, request_func, session=None):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                if session:
                    return await request_func(session=session)
                else:
                    return await asyncio.to_thread(request_func)
            except SSLError as ssl_error:
                logger.warning(f"SSL Error occurred (attempt {attempt+1}/{max_retries}): {str(ssl_error)}")
                if attempt == max_retries - 1:
                    raise Exception(f"SSL Error persisted after {max_retries} attempts: {str(ssl_error)}")
                await asyncio.sleep(min(30, 2 ** attempt))
            except HttpError as e:
                # Extract more detailed error information
                error_details = {}
                if hasattr(e, 'error_details') and e.error_details:
                    error_details = e.error_details[0] if isinstance(e.error_details, list) else e.error_details
                
                error_reason = error_details.get('reason', 'unknown')
                error_message = error_details.get('message', str(e))
                status_code = e.status_code if hasattr(e, 'status_code') else 'unknown'
                
                # Log detailed error information
                logger.error(f"YouTube API error: Status {status_code}, Reason: {error_reason}, Message: {error_message}")
                
                if error_reason == 'quotaExceeded':
                    logger.error(f"YouTube API quota exceeded for key {self.current_key_index+1}/{len(self.api_keys)}.")
                    # Check if we have any other key with quota before trying to rotate
                    if not await self._any_key_available():
                        logger.error("All YouTube API keys are exhausted. Cannot proceed with API requests.")
                        raise Exception("All YouTube API keys exhausted")
                    await self._rotate_api_key()
                    # Don't count this as a retry since we're using a different key
                    continue
                elif error_reason == 'rateLimitExceeded':
                    wait_time = min(30, (2 ** attempt) + random.uniform(0, 1))
                    logger.warning(f"Rate limit exceeded. Retrying in {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"API Error: {error_message}")
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(min(10, 2 ** attempt))
            except Exception as e:
                logger.error(f"Unexpected error in API request (attempt {attempt+1}/{max_retries}): {str(e)}")
                logger.error(traceback.format_exc())
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(min(10, 2 ** attempt))
        
        # If we've exhausted all retries, provide a clearer error message
        logger.error("YouTube API request failed after multiple retries with all available API keys.")
        raise Exception("YouTube API request failed after exhausting all retries and API keys.")
    
    @cached(ttl=3600, serializer=PickleSerializer())
    async def fetch_channel_data(self, channel_id: str) -> Dict:
        try:
            await self._update_quota(cost=1)
            response = await self._make_api_request(
                lambda: self.youtube.channels().list(
                    part="snippet,statistics,contentDetails",
                    id=channel_id
                ).execute()
            )
            logger.debug(f"Raw channel data response: {json.dumps(response, indent=2)}")
            logger.debug(f"Channel statistics: {response['items'][0]['statistics']}")  # Debug log

            if not response.get('items'):
                logger.error(f"No channel data found for channel ID: {channel_id}")
                # Try HTML scraping as first fallback
                try:
                    scraped_data = await self._fetch_channel_data_html_scrape(channel_id)
                    if scraped_data:
                        return scraped_data
                except Exception as scrape_error:
                    logger.error(f"HTML scraping fallback failed: {str(scrape_error)}")
                
                # Then try the original fallback
                return await self.fetch_channel_data_fallback(channel_id)

            channel_data = response['items'][0]
            return {
                'id': channel_data['id'],
                'title': channel_data['snippet']['title'],
                'description': channel_data['snippet']['description'],
                'subscriberCount': int(channel_data['statistics'].get('subscriberCount', 0)),
                'videoCount': int(channel_data['statistics'].get('videoCount', 0)),
                'viewCount': int(channel_data['statistics'].get('viewCount', 0)),
                'joinDate': channel_data['snippet']['publishedAt'],
                'thumbnails': channel_data['snippet']['thumbnails'],
                'country': channel_data['snippet'].get('country', 'Unknown')
            }
        except Exception as e:
            logger.error(f"Error fetching channel data for {channel_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Try HTML scraping as first fallback
            try:
                logger.info(f"Trying HTML scraping fallback for channel data")
                scraped_data = await self._fetch_channel_data_html_scrape(channel_id)
                if scraped_data:
                    return scraped_data
            except Exception as scrape_error:
                logger.error(f"HTML scraping fallback failed: {str(scrape_error)}")
            
            # Then try the original fallback
            return await self.fetch_channel_data_fallback(channel_id)

    async def _fetch_channel_data_html_scrape(self, channel_id: str) -> Dict:
        """
        Fallback method to fetch channel data using direct HTML scraping.
        This method doesn't use YouTube API quota.
        """
        try:
            logger.info(f"Using HTML scraping to fetch channel data for {channel_id}")
            import aiohttp
            import json
            import re
            from datetime import datetime
            
            # Build channel URL
            channel_url = f"https://www.youtube.com/channel/{channel_id}/about"
            
            # Fetch the channel page
            async with aiohttp.ClientSession() as session:
                async with session.get(channel_url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch channel page, status: {response.status}")
                        return {}
                    
                    html = await response.text()
                    
                    # Try to extract the initial data JSON
                    initial_data_match = re.search(r'var ytInitialData = ({.*?});', html)
                    if not initial_data_match:
                        initial_data_match = re.search(r'window\["ytInitialData"\] = ({.*?});', html)
                    
                    if not initial_data_match:
                        logger.warning("Could not find YouTube initial data in page")
                        return {}
                    
                    # Parse the JSON data
                    try:
                        initial_data = json.loads(initial_data_match.group(1))
                        
                        # Navigate through the JSON structure to find channel info
                        header = initial_data.get('header', {}).get('c4TabbedHeaderRenderer', {})
                        
                        # If header not found, try alternative path
                        if not header:
                            metadata = initial_data.get('metadata', {}).get('channelMetadataRenderer', {})
                            if not metadata:
                                return {}
                            
                            # Extract channel info from metadata
                            title = metadata.get('title', 'Unknown')
                            description = metadata.get('description', '')
                            # Other fields might not be available in this path
                            return {
                                'id': channel_id,
                                'title': title,
                                'description': description,
                                'subscriberCount': 0,
                                'videoCount': 0,
                                'viewCount': 0,
                                'joinDate': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),  # Use current date as fallback
                                'thumbnails': {},
                                'country': 'Unknown'
                            }
                        
                        # Extract title
                        title = header.get('title', 'Unknown')
                        
                        # Extract channel stats
                        subscriber_count = 0
                        subscriber_text = ''
                        for item in header.get('subscriberCountText', {}).get('runs', []):
                            subscriber_text += item.get('text', '')
                        
                        # Parse subscribers like "1.23M subscribers"
                        if subscriber_text:
                            # Remove "subscribers" text and spaces
                            subscriber_count_text = subscriber_text.replace('subscribers', '').strip()
                            if 'M' in subscriber_count_text:
                                subscriber_count = int(float(subscriber_count_text.replace('M', '')) * 1000000)
                            elif 'K' in subscriber_count_text:
                                subscriber_count = int(float(subscriber_count_text.replace('K', '')) * 1000)
                            else:
                                try:
                                    subscriber_count = int(subscriber_count_text.replace(',', ''))
                                except ValueError:
                                    subscriber_count = 0
                        
                        # Extract description
                        description = ''
                        
                        # Navigate to metadata if available
                        metadata = initial_data.get('metadata', {}).get('channelMetadataRenderer', {})
                        if metadata:
                            description = metadata.get('description', '')
                        
                        # Extract view count
                        view_count = 0
                        view_count_text = ''
                        
                        # Try to find the "About" tab with view count
                        tabs = initial_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
                        for tab in tabs:
                            if 'tabRenderer' in tab and tab['tabRenderer'].get('title') == 'About':
                                about_tab = tab['tabRenderer']
                                
                                # Find view count in about tab
                                content = about_tab.get('content', {}).get('sectionListRenderer', {}).get('contents', [])
                                for section in content:
                                    if 'itemSectionRenderer' in section:
                                        for item in section['itemSectionRenderer'].get('contents', []):
                                            if 'channelAboutFullMetadataRenderer' in item:
                                                about_data = item['channelAboutFullMetadataRenderer']
                                                
                                                # Get view count
                                                view_count_text = about_data.get('viewCountText', {}).get('simpleText', '')
                                                if view_count_text:
                                                    # Extract numbers from text like "123,456,789 views"
                                                    view_match = re.search(r'([\d,]+)', view_count_text)
                                                    if view_match:
                                                        view_count = int(view_match.group(1).replace(',', ''))
                                                
                                                # Try to get join date
                                                join_date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')  # Default to current date
                                                join_date_text = about_data.get('joinedDateText', {}).get('runs', [{}])[0].get('text', '')
                                                
                                                if join_date_text:
                                                    try:
                                                        # Try to parse text like "Joined Jan 15, 2020"
                                                        join_date_match = re.search(r'Joined\s+([A-Za-z]+)\s+(\d+),\s+(\d{4})', join_date_text)
                                                        if join_date_match:
                                                            month_name, day, year = join_date_match.groups()
                                                            month_dict = {
                                                                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                                                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                                                            }
                                                            month = month_dict.get(month_name[:3], 1)
                                                            parsed_date = datetime(int(year), month, int(day))
                                                            join_date = parsed_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                                                    except Exception as date_error:
                                                        logger.warning(f"Error parsing join date: {date_error}")
                                                
                                                # Find video count
                                                video_count = 0
                                                for stat in header.get('stats', []):
                                                    if 'videos' in stat.get('text', {}).get('runs', [{}])[0].get('text', '').lower():
                                                        count_text = stat.get('text', {}).get('runs', [{}])[0].get('text', '')
                                                        # Extract numbers from text like "123 videos"
                                                        count_match = re.search(r'([\d,]+)', count_text)
                                                        if count_match:
                                                            video_count = int(count_match.group(1).replace(',', ''))
                                                
                                                # Extract thumbnails
                                                thumbnails = {}
                                                if 'avatar' in header:
                                                    avatar_thumbs = header['avatar'].get('thumbnails', [])
                                                    if avatar_thumbs:
                                                        for i, thumb in enumerate(avatar_thumbs):
                                                            size = ['default', 'medium', 'high'][min(i, 2)]
                                                            thumbnails[size] = {'url': thumb.get('url', '')}
                    
                        # Create channel data object
                        channel_data = {
                            'id': channel_id,
                            'title': title,
                            'description': description,
                            'subscriberCount': subscriber_count,
                            'videoCount': video_count,
                            'viewCount': view_count,
                            'joinDate': join_date if 'join_date' in locals() else datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                            'thumbnails': thumbnails,
                            'country': 'Unknown'  # Not easily available from HTML
                        }
                        
                        logger.info(f"HTML scraping found channel data for {channel_id}")
                        return channel_data
                        
                    except json.JSONDecodeError as json_error:
                        logger.error(f"Error parsing YouTube initial data: {str(json_error)}")
                        return {}
                
            return {}
        except Exception as e:
            logger.error(f"Error in _fetch_channel_data_html_scrape for channel {channel_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {}

    async def fetch_channel_data_fallback(self, channel_id: str) -> Dict:
        try:
            logger.info(f"Using youtube-search-python fallback to fetch channel data for {channel_id}")
            channels_search = ChannelsSearch(channel_id, limit=1)
            search_results = await channels_search.next()
            if search_results['result']:
                channel = search_results['result'][0]
                return {
                    'id': channel['id'],
                    'title': channel['title'],
                    'description': channel['description'],
                    'subscriberCount': channel['subscribers'],
                    'videoCount': channel['videoCount'],
                    'viewCount': channel['viewCount'],
                    'joinDate': channel['joinedDate'],
                    'thumbnails': channel['thumbnails'],
                    'country': channel.get('country', 'Unknown')
                }
            else:
                raise Exception("Channel not found")
        except Exception as e:
            logger.error(f"Error fetching channel data using youtube-search-python fallback for {channel_id}: {str(e)}")
            return {}
        
    def get_youtube_api(self):
        return build('youtube', 'v3', developerKey=random.choice(YOUTUBE_API_KEYS))
    
    @circuit_breaker()
    async def fetch_channel_videos(self, channel_id: str, max_results: int = 500) -> List[Dict]:
        logger.info(f"Fetching videos for channel {channel_id} (max: {max_results})")
        
        # First, try to use the YouTube API if quota is available
        if await self._any_key_available():
            try:
                logger.info(f"Using YouTube API for channel {channel_id}")
                await self._update_quota(cost=1)
                videos = []
                next_page_token = None
                
                # Ensure max_results has a default value if None and cap at 500
                max_results = min(500, 50 if max_results is None else max_results)
                
                # Get the uploads playlist ID (replace UC with UU)
                uploads_playlist_id = channel_id.replace('UC', 'UU', 1) if channel_id.startswith('UC') else f"UU{channel_id[2:]}"
                logger.info(f"Using uploads playlist ID: {uploads_playlist_id}")
                
                while len(videos) < max_results:
                    try:
                        logger.debug(f"Requesting playlist items for uploads playlist {uploads_playlist_id}, page token: {next_page_token}")
                        playlist_response = await self._make_api_request(
                            lambda: self.youtube.playlistItems().list(
                                part="snippet",
                                playlistId=uploads_playlist_id,
                                maxResults=min(50, max_results - len(videos)),  # YouTube API max is 50 per request
                                pageToken=next_page_token
                            ).execute()
                        )
                        
                        if not playlist_response.get('items'):
                            logger.warning(f"No videos found in playlist response for uploads playlist {uploads_playlist_id}")
                            break
                        
                        video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response.get('items', [])]
                        
                        logger.debug(f"Requesting video details for IDs: {video_ids}")
                        video_response = await self._make_api_request(
                            lambda: self.youtube.videos().list(
                                part="snippet,contentDetails,statistics",
                                id=','.join(video_ids)
                            ).execute()
                        )
                        
                        for item in video_response.get('items', []):
                            video = {
                                'id': item['id'],
                                'title': item['snippet']['title'],
                                'channelId': item['snippet']['channelId'],
                                'publishedAt': item['snippet']['publishedAt'],
                                'duration': item['contentDetails'].get('duration', 'PT0S'),
                                'viewCount': item['statistics'].get('viewCount', '0'),
                                'likeCount': item['statistics'].get('likeCount', '0'),
                                'commentCount': item['statistics'].get('commentCount', '0'),
                                'thumbnail_url': item['snippet']['thumbnails']['high']['url']
                            }
                            # Convert duration to seconds
                            video['duration_seconds'] = self.parse_duration(video['duration'])
                            videos.append(video)
                        
                        next_page_token = playlist_response.get('nextPageToken')
                        if not next_page_token:
                            break
                            
                    except Exception as e:
                        logger.error(f"Error in API request for uploads playlist {uploads_playlist_id}: {str(e)}")
                        break
                
                if videos:
                    logger.info(f"Successfully fetched {len(videos)} videos using YouTube API uploads playlist for channel {channel_id}")
                    return videos
                else:
                    logger.warning(f"YouTube API returned no videos for uploads playlist {uploads_playlist_id}")
                    
            except Exception as e:
                logger.error(f"YouTube API failed for channel {channel_id}: {str(e)}")
                # Don't return here, fall through to HTML scraping
        else:
            logger.warning("No YouTube API quota available, skipping API and using HTML scraping")
        
        # Fallback to HTML scraping if API failed or quota exhausted
        try:
            logger.info(f"Falling back to HTML scraping for channel {channel_id}")
            scraped_videos = await self._fetch_channel_videos_html_scrape(channel_id, max_results)
            if scraped_videos:
                logger.info(f"HTML scraping successful, found {len(scraped_videos)} videos for channel {channel_id}")
                return scraped_videos
        except Exception as scrape_error:
            logger.error(f"HTML scraping failed for channel {channel_id}: {str(scrape_error)}")
        
        # Final fallback using youtube-search-python
        try:
            logger.info(f"Using final fallback method for channel {channel_id}")
            return await self._fetch_channel_videos_fallback(channel_id, max_results)
        except Exception as final_error:
            logger.error(f"All methods failed for channel {channel_id}: {str(final_error)}")
            return []

    async def _fetch_channel_videos_html_scrape(self, channel_id: str, max_results: int = 500) -> List[Dict]:
        """
        Fallback method to fetch videos from a channel using direct HTML scraping.
        This method doesn't use YouTube API quota or youtube-search-python.
        """
        try:
            logger.info(f"Using HTML scraping to fetch videos for channel {channel_id}")
            videos = []
            import aiohttp
            import json
            import re
            from datetime import datetime, timedelta
            
            # Try different URL formats to increase chances of success
            urls_to_try = [
                f"https://www.youtube.com/channel/{channel_id}/videos",
                f"https://www.youtube.com/channel/{channel_id}"
            ]
            
            # Random user agents to avoid blocking
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
            ]
            
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
            
            # Helper function to parse relative dates
            def parse_relative_date(relative_date_text):
                now = datetime.utcnow()
                
                # Check if it's a relative date string
                if not relative_date_text:
                    return now
                    
                # Handle "just now"
                if "just now" in relative_date_text.lower():
                    return now
                    
                # Handle common relative date formats
                time_value = None
                time_unit = None
                
                # First try to match the pattern like "9 days ago", "2 weeks ago"
                match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', relative_date_text.lower())
                if match:
                    time_value = int(match.group(1))
                    time_unit = match.group(2)
                    
                    if time_unit == 'second':
                        return now - timedelta(seconds=time_value)
                    elif time_unit == 'minute':
                        return now - timedelta(minutes=time_value)
                    elif time_unit == 'hour':
                        return now - timedelta(hours=time_value)
                    elif time_unit == 'day':
                        return now - timedelta(days=time_value)
                    elif time_unit == 'week':
                        return now - timedelta(weeks=time_value)
                    elif time_unit == 'month':
                        # Approximation: 1 month ≈ 30 days
                        return now - timedelta(days=time_value * 30)
                    elif time_unit == 'year':
                        # Approximation: 1 year ≈ 365 days
                        return now - timedelta(days=time_value * 365)
                
                # Handle "today", "yesterday"
                if "today" in relative_date_text.lower():
                    return now
                elif "yesterday" in relative_date_text.lower():
                    return now - timedelta(days=1)
                    
                # Handle cases like "10 seconds ago", "a minute ago", etc.
                if "second" in relative_date_text.lower():
                    if "a second" in relative_date_text.lower():
                        return now - timedelta(seconds=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(seconds=int(match.group(1)))
                elif "minute" in relative_date_text.lower():
                    if "a minute" in relative_date_text.lower():
                        return now - timedelta(minutes=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(minutes=int(match.group(1)))
                elif "hour" in relative_date_text.lower():
                    if "an hour" in relative_date_text.lower():
                        return now - timedelta(hours=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(hours=int(match.group(1)))
                        
                # Fallback to today's date if parsing fails
                return now
            
            for url in urls_to_try:
                logger.info(f"Trying to fetch videos from URL: {url}")
                
                # Fetch the channel page
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch channel page at {url}, status: {response.status}")
                            continue
                            
                        html = await response.text()
                        logger.debug(f"Retrieved HTML page of length {len(html)}")
                        
                        # Try different patterns for initial data
                        initial_data = None
                        patterns = [
                            r'var ytInitialData = ({.*?});',
                            r'window\["ytInitialData"\] = ({.*?});',
                            r'ytInitialData = ({.*?});'
                        ]
                        
                        for pattern in patterns:
                            initial_data_match = re.search(pattern, html)
                            if initial_data_match:
                                try:
                                    initial_data = json.loads(initial_data_match.group(1))
                                    logger.info(f"Successfully parsed initial data using pattern: {pattern}")
                                    break
                                except json.JSONDecodeError:
                                    continue
                        
                        if not initial_data:
                            logger.warning(f"Could not extract YouTube initial data from {url}")
                            continue
                        
                        # Multiple attempts to find videos in different locations in the JSON
                        video_items = []
                        
                        # First attempt: look for the Videos tab
                        try:
                            tab_renderer = None
                            tabs = initial_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
                            
                            for tab in tabs:
                                if 'tabRenderer' in tab and tab['tabRenderer'].get('title') == 'Videos':
                                    tab_renderer = tab['tabRenderer']
                                    break
                            
                            if tab_renderer:
                                logger.info("Found Videos tab in channel page")
                                content = tab_renderer.get('content', {})
                                
                                # Check for different content structures
                                if 'sectionListRenderer' in content:
                                    section_list = content['sectionListRenderer']
                                    for section in section_list.get('contents', []):
                                        if 'itemSectionRenderer' in section:
                                            for item in section['itemSectionRenderer'].get('contents', []):
                                                if 'gridRenderer' in item:
                                                    video_items.extend(item['gridRenderer'].get('items', []))
                                
                                # Alternative structure
                                elif 'richGridRenderer' in content:
                                    video_items.extend(content['richGridRenderer'].get('contents', []))
                        except Exception as e:
                            logger.warning(f"Error finding videos in tabs structure: {str(e)}")
                        
                        # Second attempt: look directly for videoRenderer objects
                        if not video_items:
                            try:
                                # Search for videoRenderer in the entire JSON object
                                def find_video_renderers(obj, items=None):
                                    if items is None:
                                        items = []
                                    if isinstance(obj, dict):
                                        for key, value in obj.items():
                                            if key == 'videoRenderer' and isinstance(value, dict) and 'videoId' in value:
                                                items.append({'videoRenderer': value})
                                            elif key == 'gridVideoRenderer' and isinstance(value, dict) and 'videoId' in value:
                                                items.append({'gridVideoRenderer': value})
                                            elif isinstance(value, (dict, list)):
                                                find_video_renderers(value, items)
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            find_video_renderers(item, items)
                                    return items
                                
                                video_items = find_video_renderers(initial_data)
                                if video_items:
                                    logger.info(f"Found {len(video_items)} videos using direct search")
                            except Exception as e:
                                logger.warning(f"Error with direct search for videos: {str(e)}")
                        
                        # If we found videos, process them
                        if video_items:
                            logger.info(f"Found {len(video_items)} video items on channel page")
                            
                            # Process each video
                            for item in video_items[:max_results]:
                                try:
                                    video_data = None
                                    if 'gridVideoRenderer' in item:
                                        video_data = item['gridVideoRenderer']
                                    elif 'videoRenderer' in item:
                                        video_data = item['videoRenderer']
                                    elif 'richItemRenderer' in item:
                                        rich_item = item['richItemRenderer'].get('content', {})
                                        if 'videoRenderer' in rich_item:
                                            video_data = rich_item['videoRenderer']
                                    
                                    if not video_data or 'videoId' not in video_data:
                                        continue
                                        
                                    video_id = video_data.get('videoId', '')
                                    
                                    # Extract title
                                    title = 'Unknown Title'
                                    title_obj = video_data.get('title', {})
                                    if 'runs' in title_obj and title_obj['runs']:
                                        title = title_obj['runs'][0].get('text', title)
                                    elif 'simpleText' in title_obj:
                                        title = title_obj['simpleText']
                                    
                                    # Extract thumbnail
                                    thumbnail_url = ''
                                    thumbnails = video_data.get('thumbnail', {}).get('thumbnails', [])
                                    if thumbnails:
                                        thumbnail_url = thumbnails[-1].get('url', '')
                                    
                                    # Extract publication date - parse relative time
                                    published_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')  # Default to current time
                                    published_text = ''
                                    publish_info = video_data.get('publishedTimeText', {})
                                    
                                    if 'runs' in publish_info:
                                        published_text = ' '.join([run.get('text', '') for run in publish_info['runs']])
                                    elif 'simpleText' in publish_info:
                                        published_text = publish_info['simpleText']
                                    
                                    # Try to parse the relative date text
                                    if published_text:
                                        pub_date = parse_relative_date(published_text)
                                        published_at = pub_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                                        logger.debug(f"Converted relative date '{published_text}' to '{published_at}'")
                                    
                                    # Extract view count
                                    view_count = 0
                                    view_count_text = ''
                                    view_info = video_data.get('viewCountText', {})
                                    
                                    if 'runs' in view_info:
                                        view_count_text = ' '.join([run.get('text', '') for run in view_info['runs']])
                                    elif 'simpleText' in view_info:
                                        view_count_text = view_info['simpleText']
                                    
                                    # Extract view count number
                                    if view_count_text:
                                        view_match = re.search(r'([\d,]+)', view_count_text)
                                        if view_match:
                                            view_count = int(view_match.group(1).replace(',', ''))
                                    
                                    # Extract duration
                                    duration_text = ''
                                    duration_seconds = 0
                                    
                                    if 'lengthText' in video_data:
                                        length_info = video_data['lengthText']
                                        if 'simpleText' in length_info:
                                            duration_text = length_info['simpleText']
                                            
                                            # Parse duration like "12:34" or "1:23:45"
                                            parts = duration_text.split(':')
                                            if len(parts) == 2:  # MM:SS
                                                duration_seconds = int(parts[0]) * 60 + int(parts[1])
                                            elif len(parts) == 3:  # HH:MM:SS
                                                duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                                
                                    # Create standardized video object
                                    video = {
                                        'id': video_id,
                                        'title': title,
                                        'channelId': channel_id,
                                        'publishedAt': published_at,  # Now using parsed relative date
                                        'duration': f"PT{duration_seconds}S",  # Convert to ISO duration format
                                        'duration_seconds': duration_seconds,
                                        'viewCount': str(view_count),
                                        'likeCount': '0',  # Not available in channel listing
                                        'commentCount': '0',  # Not available in channel listing
                                        'thumbnail_url': thumbnail_url
                                    }
                                    
                                    videos.append(video)
                                    
                                except Exception as item_error:
                                    logger.error(f"Error processing video item: {str(item_error)}")
                                    continue
                            
                            if videos:
                                logger.info(f"HTML scraping found {len(videos)} videos for channel {channel_id}")
                                return videos
            
            if not videos:
                logger.warning(f"No videos found using HTML scraping for channel {channel_id}")
                
            return videos
        except Exception as e:
            logger.error(f"Error in _fetch_channel_videos_html_scrape for channel {channel_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    async def _fetch_channel_videos_fallback(self, channel_id: str, max_results: int = 500) -> List[Dict]:
        try:
            logger.info(f"Using youtube-search-python fallback to fetch videos for channel {channel_id}")
            videos = []
            
            # Try to use the non-async Channel approach first (avoiding Channel.get which has issues)
            try:
                from youtubesearchpython import Channel as SyncChannel
                
                # Use the synchronous version which doesn't have proxies issues
                channel_obj = SyncChannel(channel_id)
                channel_data = channel_obj.result()
                
                if isinstance(channel_data, dict) and 'videos' in channel_data:
                    for video in channel_data['videos'][:max_results]:
                        # Format duration to PT format if it's in HH:MM:SS format
                        duration_str = video.get('duration', '')
                        duration_seconds = 0
                        
                        # Parse duration from format like "12:34" or "1:23:45"
                        parts = duration_str.split(':')
                        if len(parts) == 2:  # MM:SS
                            duration_seconds = int(parts[0]) * 60 + int(parts[1])
                        elif len(parts) == 3:  # HH:MM:SS
                            duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        
                        # Clean view count
                        view_count = video.get('viewCount', {}).get('text', '0')
                        if isinstance(view_count, str):
                            view_count = view_count.replace(',', '').replace(' views', '').strip()
                        
                        videos.append({
                            'id': video.get('id', ''),
                            'title': video.get('title', ''),
                            'channelId': channel_id,
                            'publishedAt': video.get('publishDate', ''),
                            'duration': f"PT{duration_seconds}S",  # Convert to ISO format
                            'duration_seconds': duration_seconds,
                            'viewCount': view_count,
                            'likeCount': video.get('likeCount', '0'),
                            'commentCount': video.get('commentCount', '0'),
                            'thumbnail_url': video.get('thumbnails', [{}])[0].get('url', '') if video.get('thumbnails') else ''
                        })
                        if len(videos) >= max_results:
                            break
                
                if videos:
                    logger.info(f"Fetched {len(videos)} videos using synchronous youtube-search-python fallback for channel {channel_id}")
                    return videos
            except Exception as sync_error:
                logger.error(f"Synchronous youtube-search-python approach failed: {str(sync_error)}")
            
            # If the above fails, try the original async method but handle proxies issue
            try:
                # Import here to avoid issues with circular imports
                from youtubesearchpython.__future__ import Channel
                
                # Create a wrapper for Channel.get that doesn't pass proxies
                async def get_channel_no_proxies(channel_id):
                    channel_obj = Channel(channel_id)
                    await channel_obj.get()
                    return channel_obj.result()
                
                channel_data = await get_channel_no_proxies(channel_id)
                
                if isinstance(channel_data, dict) and 'videos' in channel_data:
                    for video in channel_data['videos'][:max_results]:
                        videos.append({
                            'id': video.get('id', ''),
                            'title': video.get('title', ''),
                            'channelId': channel_id,
                            'publishedAt': video.get('publishDate', ''),
                            'duration': video.get('duration', ''),
                            'duration_seconds': 0,  # Will calculate this later
                            'viewCount': video.get('viewCount', {}).get('text', '0').replace(',', ''),
                            'likeCount': video.get('likeCount', '0'),
                            'commentCount': video.get('commentCount', '0')
                        })
                        if len(videos) >= max_results:
                            break
            except Exception as async_error:
                logger.error(f"Async youtube-search-python approach also failed: {str(async_error)}")
            
            logger.info(f"Fetched {len(videos)} videos using youtube-search-python fallback for channel {channel_id}")
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos using youtube-search-python fallback for channel {channel_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    async def search_videos(self, query: str, max_results: int = 50, order: str = None, published_after: str = None, page_token: str = None) -> Dict:
        """
        Search for videos with given parameters
        
        Args:
            query: Search term
            max_results: Maximum number of results to return
            order: Optional - Order of results (viewCount, date, rating, relevance)
            published_after: Optional - ISO 8601 formatted date string
            page_token: Optional - Token for getting next page of results
            
        Returns:
            Dict containing:
            - videos: List of video data
            - nextPageToken: Token for next page (if available)
        """
        logger.info(f"Searching for videos with query: '{query}'{f', order: {order}' if order else ''}")

        try:
            await self._update_quota(cost=1)
            request_params = {
                'q': query,
                'type': "video",
                'part': "id,snippet",
                'maxResults': max_results
            }
            
            # Only add optional parameters if they're provided
            if order:
                request_params['order'] = order
            if published_after:
                request_params['publishedAfter'] = published_after
            if page_token:
                request_params['pageToken'] = page_token
                
            request = self.youtube.search().list(**request_params)
            search_response = await self._make_api_request(request.execute)
            
            videos = []
            for item in search_response.get('items', []):
                video = {
                    'id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'channelId': item['snippet']['channelId'],
                    'channelTitle': item['snippet']['channelTitle'],
                    'publishedAt': item['snippet']['publishedAt'],
                    'thumbnails': item['snippet']['thumbnails'],
                }
                videos.append(video)
            
            logger.info(f"Found {len(videos)} search results for '{query}' using YouTube API")
            
            # Return both videos and next page token
            return {
                'videos': videos,
                'nextPageToken': search_response.get('nextPageToken')
            }
            
        except Exception as e:
            if "quota exceeded" in str(e).lower():
                logger.warning("YouTube API quota exceeded. Falling back to HTML scraping.")
                html_results = await self._search_videos_html_scrape(query, max_results, order)
                return {'videos': html_results, 'nextPageToken': None}
            else:
                logger.error(f"Error searching for videos with query '{query}': {str(e)}")
                logger.info("Falling back to HTML scraping for search.")
                return {'videos': await self._search_videos_html_scrape(query, max_results, order), 'nextPageToken': None}

    async def _search_videos_html_scrape(self, query: str, max_results: int = 50, order: str = None) -> List[Dict]:
        """
        Search for videos using direct HTML scraping of YouTube search results.
        This method doesn't use YouTube API quota.
        
        Args:
            query: Search term
            max_results: Maximum number of results to return
            order: Optional - Order of results (date, viewCount, relevance, rating)
            
        Returns:
            List of video data
        """
        try:
            logger.info(f"Using HTML scraping to search for videos with query: '{query}'")
            import aiohttp
            import json
            import re
            from urllib.parse import quote
            from datetime import datetime, timedelta
            
            videos = []
            
            # Build search URL with ordering if specified
            search_url = f"https://www.youtube.com/results?search_query={quote(query)}"
            if order:
                # Map API ordering to YouTube's UI parameters
                order_param = {
                    'date': 'CAI%253D',       # Upload date
                    'viewCount': 'CAM%253D',   # View count
                    'rating': 'CAE%253D',      # Rating
                    'relevance': ''            # Relevance (default)
                }.get(order, '')
                
                if order_param:
                    search_url += f"&sp={order_param}"
            
            # Helper function to parse relative dates
            def parse_relative_date(relative_date_text):
                now = datetime.utcnow()
                
                # Check if it's a relative date string
                if not relative_date_text:
                    return now
                    
                # Handle "just now"
                if "just now" in relative_date_text.lower():
                    return now
                    
                # Handle common relative date formats
                time_value = None
                time_unit = None
                
                # First try to match the pattern like "9 days ago", "2 weeks ago"
                match = re.search(r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', relative_date_text.lower())
                if match:
                    time_value = int(match.group(1))
                    time_unit = match.group(2)
                    
                    if time_unit == 'second':
                        return now - timedelta(seconds=time_value)
                    elif time_unit == 'minute':
                        return now - timedelta(minutes=time_value)
                    elif time_unit == 'hour':
                        return now - timedelta(hours=time_value)
                    elif time_unit == 'day':
                        return now - timedelta(days=time_value)
                    elif time_unit == 'week':
                        return now - timedelta(weeks=time_value)
                    elif time_unit == 'month':
                        # Approximation: 1 month ≈ 30 days
                        return now - timedelta(days=time_value * 30)
                    elif time_unit == 'year':
                        # Approximation: 1 year ≈ 365 days
                        return now - timedelta(days=time_value * 365)
                
                # Handle "today", "yesterday"
                if "today" in relative_date_text.lower():
                    return now
                elif "yesterday" in relative_date_text.lower():
                    return now - timedelta(days=1)
                    
                # Handle cases like "10 seconds ago", "a minute ago", etc.
                if "second" in relative_date_text.lower():
                    if "a second" in relative_date_text.lower():
                        return now - timedelta(seconds=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(seconds=int(match.group(1)))
                elif "minute" in relative_date_text.lower():
                    if "a minute" in relative_date_text.lower():
                        return now - timedelta(minutes=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(minutes=int(match.group(1)))
                elif "hour" in relative_date_text.lower():
                    if "an hour" in relative_date_text.lower():
                        return now - timedelta(hours=1)
                    match = re.search(r'(\d+)', relative_date_text)
                    if match:
                        return now - timedelta(hours=int(match.group(1)))
                        
                # Fallback to today's date if parsing fails
                return now
            
            # Use a random user agent to avoid blocking
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
            ]
            headers = {
                "User-Agent": random.choice(user_agents),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
            
            # Fetch the search page
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch search page, status: {response.status}")
                        return []
                    
                    html = await response.text()
                    
                    # Try to extract the initial data JSON
                    initial_data_match = re.search(r'var ytInitialData = ({.*?});', html)
                    if not initial_data_match:
                        initial_data_match = re.search(r'window\["ytInitialData"\] = ({.*?});', html)
                    
                    if not initial_data_match:
                        logger.warning("Could not find YouTube initial data in search page")
                        return []
                    
                    # Parse the JSON data
                    try:
                        initial_data = json.loads(initial_data_match.group(1))
                        
                        # Navigate through the JSON structure to find videos
                        contents = initial_data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {})
                        section_list = contents.get('sectionListRenderer', {})
                        
                        if not section_list:
                            # Try alternative path
                            section_list = contents.get('richGridRenderer', {})
                        
                        items = []
                        
                        # Extract items from sectionListRenderer structure
                        if 'contents' in section_list:
                            for section in section_list['contents']:
                                if 'itemSectionRenderer' in section:
                                    items.extend(section.get('itemSectionRenderer', {}).get('contents', []))
                                elif 'richItemRenderer' in section:
                                    rich_item = section.get('richItemRenderer', {}).get('content', {})
                                    if rich_item:
                                        items.append(rich_item)
                        
                        # Process each video
                        video_count = 0
                        for item in items:
                            if video_count >= max_results:
                                break
                            
                            video_renderer = None
                            if 'videoRenderer' in item:
                                video_renderer = item['videoRenderer']
                            elif 'videoWithContextRenderer' in item:
                                video_renderer = item['videoWithContextRenderer']
                            elif 'videoRenderer' in item.get('compactVideoRenderer', {}):
                                video_renderer = item['compactVideoRenderer']['videoRenderer']
                            
                            if not video_renderer:
                                continue
                            
                            try:
                                video_id = video_renderer.get('videoId', '')
                                if not video_id:
                                    continue
                                
                                # Extract title
                                title = ""
                                title_obj = video_renderer.get('title', {})
                                if 'runs' in title_obj:
                                    title = ' '.join([run.get('text', '') for run in title_obj['runs']])
                                elif 'simpleText' in title_obj:
                                    title = title_obj['simpleText']
                                
                                if not title:
                                    continue
                                
                                # Extract channel info
                                channel_title = ""
                                channel_id = ""
                                owner_text = video_renderer.get('ownerText', {})
                                if 'runs' in owner_text:
                                    channel_title = owner_text['runs'][0].get('text', '')
                                    nav_endpoint = owner_text['runs'][0].get('navigationEndpoint', {})
                                    browse_endpoint = nav_endpoint.get('browseEndpoint', {})
                                    channel_id = browse_endpoint.get('browseId', '')
                                
                                # Extract published date
                                published_text = ""
                                published_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')  # Default
                                published_obj = video_renderer.get('publishedTimeText', {})
                                
                                if 'simpleText' in published_obj:
                                    published_text = published_obj['simpleText']
                                elif 'runs' in published_obj:
                                    published_text = ' '.join([run.get('text', '') for run in published_obj['runs']])
                                
                                # Convert relative date to absolute date
                                if published_text:
                                    pub_date = parse_relative_date(published_text)
                                    published_at = pub_date.strftime('%Y-%m-%dT%H:%M:%SZ')
                                    logger.debug(f"Converted relative date '{published_text}' to '{published_at}'")
                                
                                # Extract thumbnail
                                thumbnail_url = ""
                                thumbnails = video_renderer.get('thumbnail', {}).get('thumbnails', [])
                                if thumbnails:
                                    thumbnail_url = thumbnails[-1].get('url', '')
                                
                                # Create video object
                                video = {
                                    'id': video_id,
                                    'title': title,
                                    'channelId': channel_id,
                                    'channelTitle': channel_title,
                                    'publishedAt': published_at,  # Now with converted date
                                    'thumbnails': {'default': {'url': thumbnail_url}} if thumbnail_url else {}
                                }
                                
                                videos.append(video)
                                video_count += 1
                                
                            except Exception as item_error:
                                logger.error(f"Error processing search result item: {str(item_error)}")
                                continue
                        
                        logger.info(f"HTML scraping found {len(videos)} videos for query '{query}'")
                        return videos
                        
                    except json.JSONDecodeError as json_error:
                        logger.error(f"Error parsing YouTube initial data from search: {str(json_error)}")
                        return []
            
            return []
        except Exception as e:
            logger.error(f"Error in _search_videos_html_scrape for query '{query}': {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    def _process_channel_data(self, data: Dict) -> Dict:
        snippet = data.get('snippet', {})
        statistics = data.get('statistics', {})
        branding = data.get('brandingSettings', {}).get('channel', {})

        def parse_count(count_str):
            if isinstance(count_str, int):
                return count_str
            if isinstance(count_str, str):
                if 'M' in count_str:
                    return int(float(count_str.replace('M', '')) * 1000000)
                elif 'K' in count_str:
                    return int(float(count_str.replace('K', '')) * 1000)
                else:
                    return int(float(count_str))
            return 0

        return {
            'id': data.get('id', 'Unknown'),
            'title': snippet.get('title', 'Unknown'),
            'description': snippet.get('description', ''),
            'subscriberCount': parse_count(statistics.get('subscriberCount', 0)),
            'videoCount': parse_count(statistics.get('videoCount', 0)),
            'viewCount': parse_count(statistics.get('viewCount', 0)),
            'joinDate': snippet.get('publishedAt', 'Unknown'),
            'thumbnails': snippet.get('thumbnails', {}),
            'country': branding.get('country', 'Unknown')
        }

    async def _process_video_data(self, video: Dict) -> Dict:
        snippet = video.get('snippet', {})
        video_id = video.get('id', {}).get('videoId') if isinstance(video.get('id'), dict) else video.get('id', 'Unknown')
        
        processed_data = {
            'id': video_id,
            'title': snippet.get('title', 'Unknown'),
            'description': snippet.get('description', ''),
            'publishedAt': snippet.get('publishedAt', 'Unknown'),
            'thumbnails': snippet.get('thumbnails', {}),
            'channelId': snippet.get('channelId', 'Unknown'),
            'channelTitle': snippet.get('channelTitle', 'Unknown')
        }

        duration = await self.get_video_duration(video_id)
        processed_data['duration'] = duration

        return processed_data

    async def get_video_info(self, video_id: str) -> Dict[str, Any]:
        try:
            video_request = self.youtube.videos().list(
                part="snippet",
                id=video_id
            )
            video_response = video_request.execute()

            if video_response.get("items"):
                video_info = video_response["items"][0]["snippet"]
                return {
                    "title": video_info.get("title", ""),
                    "description": video_info.get("description", ""),
                    "published_at": video_info.get("publishedAt", ""),
                    # Add any other relevant information you need
                }
            else:
                logger.warning(f"No video found with ID: {video_id}")
                return {}
        except Exception as e:
            logger.error(f"Error getting video info for {video_id}: {str(e)}")
            return {}
    
    
    def parse_duration(self, duration_string: str) -> int:
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_string)
        if not match:
            return 0
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        return hours * 3600 + minutes * 60 + seconds

    async def get_video_captions(self, video_url: str) -> str:
        try:
            video_id = self.extract_video_id(video_url)
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            formatter = TextFormatter()
            return formatter.format_transcript(transcript)
        except Exception as e:
            logger.error(f"Error fetching captions for video {video_url}: {str(e)}")
            return ""

    def extract_video_id(self, video_url: str) -> str:
        if "youtu.be" in video_url:
            return video_url.split("/")[-1]
        elif "youtube.com" in video_url:
            match = re.search(r"v=([a-zA-Z0-9_-]{11})", video_url)
            if match:
                return match.group(1)
            else:
                raise ValueError("Invalid YouTube URL")
        else:
            raise ValueError("Invalid YouTube URL")

    @cached(ttl=3600, serializer=PickleSerializer())
    async def get_channel_id_from_url(self, channel_url: str) -> str:
        logger.info(f"Extracting channel ID from URL: {channel_url}")
        try:
            # For direct channel URLs
            if '/channel/' in channel_url:
                match = re.search(r'channel/([a-zA-Z0-9_-]+)', channel_url)
                if match:
                    return match.group(1)
            
            # Direct HTML scraping fallback - doesn't use API quota
            try:
                logger.info(f"Using HTML scraping fallback for URL: {channel_url}")
                import aiohttp
                import re
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(channel_url) as response:
                        if response.status == 200:
                            html = await response.text()
                            
                            # Try to extract channel ID from HTML
                            # Look for: "externalId":"UCxxxxxxxx" pattern
                            external_id_match = re.search(r'"externalId":"(UC[a-zA-Z0-9_-]+)"', html)
                            if external_id_match:
                                channel_id = external_id_match.group(1)
                                logger.info(f"Successfully extracted channel ID {channel_id} using HTML scraping")
                                return channel_id
                            
                            # Alternative pattern: /channel/UCxxxxxxxx
                            alt_match = re.search(r'\/channel\/(UC[a-zA-Z0-9_-]+)', html)
                            if alt_match:
                                channel_id = alt_match.group(1)
                                logger.info(f"Successfully extracted channel ID {channel_id} using HTML scraping (alt method)")
                                return channel_id
            except Exception as scrape_error:
                logger.warning(f"HTML scraping fallback failed: {str(scrape_error)}")
                
            # Try non-async youtubesearchpython as extreme fallback
            try:
                logger.info(f"Trying synchronous youtubesearchpython as extreme fallback for: {channel_url}")
                from youtubesearchpython import ChannelsSearch
                
                # For handle URLs, extract the handle
                if '@' in channel_url:
                    handle = channel_url.split('@')[1].split('/')[0].strip()
                    logger.info(f"Extracted handle @{handle} for synchronous search")
                    
                    # Don't use async version which requires proxies
                    search = ChannelsSearch(f"@{handle}", limit=1, language='en', region='US')
                    results = search.result()
                    
                    if results.get('result') and len(results['result']) > 0:
                        channel_id = results['result'][0]['id']
                        logger.info(f"Found channel ID {channel_id} using synchronous search")
                        return channel_id
            except Exception as search_error:
                logger.warning(f"Synchronous youtubesearchpython fallback failed: {str(search_error)}")
            
            # Try to use youtube-search-python but with fixed parameters (no proxies)
            if '@' in channel_url:
                try:
                    logger.info(f"Trying youtube-search-python with fixed parameters for: {channel_url}")
                    from youtubesearchpython.__future__ import ChannelsSearch
                    
                    handle = channel_url.split('@')[1].split('/')[0].strip()
                    # Don't pass proxies parameter
                    channels_search = ChannelsSearch(f"@{handle}", limit=1)
                    search_results = await channels_search.next()
                    
                    if search_results.get('result') and len(search_results['result']) > 0:
                        channel_id = search_results['result'][0]['id']
                        logger.info(f"Found channel ID {channel_id} using fixed youtube-search-python")
                        return channel_id
                except Exception as e:
                    logger.warning(f"Fixed youtube-search-python also failed: {str(e)}")
                    
            # Last resort: try YouTube API if still available
            if '@' in channel_url and any(self.quota_remaining.values()):
                try:
                    # Try API as last resort
                    await self._update_quota(cost=1)
                    handle = channel_url.split('@')[1].split('/')[0].strip()
                    response = await self._make_api_request(
                        lambda: self.youtube.search().list(
                            part="id",
                            q=f"@{handle}",
                            type="channel",
                            maxResults=1
                        ).execute()
                    )
                    
                    if response.get('items'):
                        channel_id = response['items'][0]['id']['channelId']
                        logger.info(f"Found channel ID {channel_id} for handle @{handle} using YouTube API")
                        return channel_id
                except Exception as api_error:
                    logger.warning(f"API fallback also failed: {str(api_error)}")
                    
            # If we reach here, all methods failed
            logger.error(f"All methods to extract channel ID from URL {channel_url} failed")
            return None

        except Exception as e:
            logger.error(f"Error extracting channel ID from URL {channel_url}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None
    
    def _extract_channel_id_from_url(self, url: str) -> str:
        patterns = [
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/channel\/([a-zA-Z0-9_-]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/user\/([a-zA-Z0-9_-]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/@([a-zA-Z0-9_-]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    async def fetch_multiple_channel_data(self, channel_ids: List[str]) -> List[Dict]:
        async def request_func():
            return self.youtube.channels().list(
                part="snippet,statistics,brandingSettings",
                id=",".join(channel_ids)
            ).execute()

        channel_response = await self._make_api_request(request_func)
        
        return [self._process_channel_data(channel) for channel in channel_response.get('items', [])]
    
    def categorize_duration(self, duration_seconds: int) -> str:
        if duration_seconds <= 60:
            return "Shorts"
        elif 240 <= duration_seconds <= 1200:
            return "Medium"
        elif 1200 < duration_seconds <= 3600:
            return "Long"
        elif duration_seconds > 3600:
            return "MEGA Long"
        else:
            return "Uncategorized"
        
    def _extract_identifier_from_url(self, url: str) -> str:
        # Patterns to match different YouTube channel URL formats
        patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/channel/([A-Za-z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/@([A-Za-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/user/([A-Za-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/(?:c/)?([A-Za-zA-Z0-9_-]+)'
        ]
        for pattern in patterns:
            match = re.match(pattern, url)
            if match:
                return match.group(1)
        return None
    
    
    async def fetch_video_data(self, video_id: str) -> Dict:
        try:
            await self._update_quota(cost=1)
            response = await self._make_api_request(
                lambda: self.youtube.videos().list(
                    part="snippet,contentDetails,statistics",
                    id=video_id
                ).execute()
            )
            
            if not response.get('items'):
                logger.error(f"No video data found for video ID: {video_id}")
                return {}

            video_data = response['items'][0]
            return {
                'id': video_data['id'],
                'title': video_data['snippet']['title'],
                'description': video_data['snippet']['description'],
                'publishedAt': video_data['snippet']['publishedAt'],
                'thumbnails': video_data['snippet']['thumbnails'],
                'duration': video_data['contentDetails']['duration'],
                'viewCount': int(video_data['statistics'].get('viewCount', 0)),
                'likeCount': int(video_data['statistics'].get('likeCount', 0)),
                'commentCount': int(video_data['statistics'].get('commentCount', 0))
            }
        except Exception as e:
            logger.error(f"Error fetching video data for {video_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {}

    async def fetch_channel_statistics(self, channel_id: str) -> Dict:
        """Fetch channel statistics including total views"""
        try:
            await self._update_quota(cost=1)
            response = await self._make_api_request(
                lambda: self.youtube.channels().list(
                    part="statistics",
                    id=channel_id
                ).execute()
            )
            
            if not response.get('items'):
                logger.error(f"No statistics found for channel ID: {channel_id}")
                return {}

            stats = response['items'][0]['statistics']
            return {
                'viewCount': int(stats.get('viewCount', 0)),
                'subscriberCount': int(stats.get('subscriberCount', 0)),
                'videoCount': int(stats.get('videoCount', 0))
            }
        except Exception as e:
            logger.error(f"Error fetching channel statistics for {channel_id}: {str(e)}")
            return {}

    async def get_channel_info(self, channel_id: str) -> Dict:
        try:
            # Replace the non-existent execute_api_request with _make_api_request
            await self._update_quota(cost=1)
            response = await self._make_api_request(
                lambda: self.youtube.channels().list(
                    part="snippet,statistics",
                    id=channel_id
                ).execute()
            )
            
            if not response.get('items'):
                return {}
            
            channel_data = response['items'][0]
            published_at = channel_data['snippet']['publishedAt']
            
            # Use the global parse_youtube_date function instead of self.parse_youtube_date
            channel_age = (datetime.utcnow() - parse_youtube_date(published_at)).days
            
            return {
                'title': channel_data['snippet']['title'],
                'description': channel_data['snippet']['description'],
                'publishedAt': published_at,
                'thumbnails': channel_data['snippet'].get('thumbnails', {}),
                'channel_age_days': channel_age,
                'total_views': int(channel_data['statistics'].get('viewCount', 0)),
                'subscriber_count': int(channel_data['statistics'].get('subscriberCount', 0)),
                'video_count': int(channel_data['statistics'].get('videoCount', 0))
            }
        except Exception as e:
            logger.error(f"Error fetching channel info for {channel_id}: {str(e)}")
            return {}
    @circuit_breaker()
    async def get_video_comments(self, video_id: str, max_results: int = 10) -> List[Dict]:
        """
        Fetch comments for a specific video
        """
        try:
            await self._update_quota(cost=1)
            comments = []
            next_page_token = None
            
            while len(comments) < max_results:
                try:
                    response = await self._make_api_request(
                        lambda: self.youtube.commentThreads().list(
                            part="snippet",
                            videoId=video_id,
                            maxResults=min(50, max_results - len(comments)),
                            pageToken=next_page_token,
                            textFormat="plainText"
                        ).execute()
                    )
                    
                    if not response.get('items'):
                        break
                        
                    for item in response['items']:
                        comment = {
                            'id': item['id'],
                            'text': item['snippet']['topLevelComment']['snippet']['textDisplay'],
                            'author': item['snippet']['topLevelComment']['snippet']['authorDisplayName'],
                            'author_channel_id': item['snippet']['topLevelComment']['snippet'].get('authorChannelId', {}).get('value'),
                            'like_count': item['snippet']['topLevelComment']['snippet']['likeCount'],
                            'published_at': item['snippet']['topLevelComment']['snippet']['publishedAt']
                        }
                        comments.append(comment)
                        
                        if len(comments) >= max_results:
                            break
                    
                    next_page_token = response.get('nextPageToken')
                    if not next_page_token:
                        break
                        
                except Exception as e:
                    logger.error(f"Error fetching comments for video {video_id}: {str(e)}")
                    break
            
            logger.info(f"Fetched {len(comments)} comments for video {video_id}")
            return comments
            
        except Exception as e:
            logger.error(f"Error in get_video_comments for video {video_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    @circuit_breaker()
    async def get_video_comments_fallback(self, video_id: str, max_results: int = 10) -> List[Dict]:
        """
        Fallback method to fetch comments using youtube-search-python
        """
        try:
            from youtubesearchpython import Comments
            
            comments_data = await Comments.get(video_id)
            comments = []
            
            if isinstance(comments_data, dict) and 'comments' in comments_data:
                for comment in comments_data['comments'][:max_results]:
                    comments.append({
                        'id': comment.get('id', ''),
                        'text': comment.get('text', ''),
                        'author': comment.get('author', {}).get('name', ''),
                        'author_channel_id': comment.get('author', {}).get('id', ''),
                        'like_count': comment.get('likes', 0),
                        'published_at': comment.get('published', '')
                    })
            
            return comments
            
        except Exception as e:
            logger.error(f"Error in get_video_comments_fallback for video {video_id}: {str(e)}")
            return []
        
    async def get_channel_by_custom_url(self, url: str) -> Dict:
        """Get channel data from custom URL formats like /c/, /@, or /channel/"""
        try:
            # Handle different URL formats
            channel_id = None
            
            if '/channel/' in url:
                channel_id = url.split('/channel/')[1].split('/')[0]
            elif '/c/' in url or '/@' in url:
                # Use Channel class from youtube-search-python
                channel_info = await Channel.get(url)
                if channel_info and 'id' in channel_info:
                    channel_id = channel_info['id']
            
            if not channel_id:
                logger.error(f"Could not extract channel ID from URL: {url}")
                return None

            # Use existing get_channel_info method
            channel_data = await self.get_channel_info(channel_id)
            return channel_data

        except Exception as e:
            logger.error(f"Error getting channel by custom URL {url}: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    async def get_oauth_url(self, state_data: str) -> str:
        """Generate OAuth URL for YouTube authentication"""
        try:
            # Try to use client_secrets.json file if it exists
            if os.path.exists('client_secrets.json'):
                flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                    'client_secrets.json',
                    scopes=self.oauth_config['scopes']
                )
            else:
                # Fall back to using environment variables
                client_config = {
                    "web": {
                        "client_id": os.getenv('YOUTUBE_CLIENT_ID'),
                        "client_secret": os.getenv('YOUTUBE_CLIENT_SECRET'),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost:8080/oauth2callback"]
                    }
                }
                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    client_config,
                    scopes=self.oauth_config['scopes']
                )
            
            # Use localhost for local testing
            flow.redirect_uri = "http://localhost:8080/oauth2callback"
            
            # Create a very short state parameter to avoid Discord's URL length limit
            # Format: userid_prefix:groupid_prefix:channelid_prefix
            short_state = "test_state"
            if state_data and ":" in state_data:
                parts = state_data.split(":")
                if len(parts) >= 3:
                    short_state = f"{parts[0][:4]}:{parts[1][:4]}:{parts[2][:4]}"
                else:
                    short_state = state_data[:15]
            
            # Generate the authorization URL with shorter state
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=short_state
            )
            
            return authorization_url
        except Exception as e:
            logger.error(f"Error generating OAuth URL: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    async def handle_oauth_callback(self, code: str, state: str) -> Dict:
        """Handle OAuth callback and save credentials"""
        try:
            # Extract user_id and group_id from state
            state_parts = state.split('_')
            user_id = state_parts[1]
            group_id = state_parts[2] if len(state_parts) > 2 else None
            
            flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                'client_secrets.json',
                scopes=self.oauth_config['scopes'],
                state=state
            )
            flow.redirect_uri = self.oauth_config['redirect_uri']
            
            # Get credentials
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Get channel ID
            youtube = build('youtube', 'v3', credentials=credentials)
            channels_response = youtube.channels().list(
                part='id',
                mine=True
            ).execute()
            
            channel_id = channels_response['items'][0]['id']
            
            # Save credentials
            oauth_data = {
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes,
                'expiry': credentials.expiry.isoformat()
            }
            
            return {
                'user_id': user_id,
                'group_id': group_id,
                'channel_id': channel_id,
                'oauth_data': oauth_data
            }
            
        except Exception as e:
            logger.error(f"OAuth callback error: {str(e)}")
            raise

    async def get_video_transcript(self, video_id: str) -> Dict[str, Any]:
        """Fetch transcript and duration for a video using the original simple method."""
        try:
            # Get transcript
            transcript = YouTubeTranscriptApi.get_transcript(video_id)

            # Get duration
            duration = await self.get_video_duration(video_id)

            # Format transcript with timestamps
            formatted_transcript = "\n".join(
                f"[{int(entry['start'])}] {entry['text']}" for entry in transcript
            )

            return {
                "transcript": formatted_transcript,
                "duration": duration
            }
        except Exception as e:
            logger.error(f"Error fetching transcript for video {video_id}: {str(e)}")
            # Fallback: try local MP3 download + Replicate Whisper (openai/whisper) if configured
            try:
                whisper_text = await self._fallback_whisper_openai_local(video_id)
                if whisper_text:
                    duration = await self.get_video_duration(video_id)
                    return {"transcript": whisper_text, "duration": duration}
            except Exception as fallback_err:
                logger.warning(f"Local Whisper fallback failed: {fallback_err}")
            return {"transcript": "", "duration": 0}

    async def _fallback_whisper_openai_local(self, video_id: str, language: str = "en") -> Optional[str]:
        """Download low-bitrate MP3 locally with yt-dlp, send to Replicate openai/whisper, then delete file.

        Requirements on local machine:
        - yt-dlp installed (pip install yt-dlp)
        - ffmpeg available on PATH (or set FFMPEG_LOCATION env var)
        - REPLICATE_API_TOKEN set in environment
        """
        try:
            import tempfile
            import shutil
            import json
            import time
            import requests

            # Prefer env var; fall back to token exported in ai_utils if present
            replicate_token = os.getenv("REPLICATE_API_TOKEN") or AIUTILS_REPLICATE_TOKEN
            if not replicate_token:
                return None

            # 1) Download best available audio locally (no ffmpeg required)
            tmpdir = tempfile.mkdtemp(prefix="yt_audio_")
            ffmpeg_location = os.getenv("FFMPEG_LOCATION")
            outtmpl = os.path.join(tmpdir, f"{video_id}.%(ext)s")
            # Import lazily to avoid import error if not installed; user prefers manual installs
            try:
                from yt_dlp import YoutubeDL  # type: ignore
            except Exception:
                return None

            ydl_opts = {
                "outtmpl": outtmpl,
                # Prefer m4a for compatibility; fall back to any bestaudio without re-encoding
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "quiet": True,
                "noprogress": True,
            }
            if ffmpeg_location:
                ydl_opts["ffmpeg_location"] = ffmpeg_location

            url = f"https://www.youtube.com/watch?v={video_id}"
            audio_path: Optional[str] = None
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, True)
                    # Determine output file path from yt-dlp response first
                    try:
                        reqs = info.get("requested_downloads") or []
                        if reqs:
                            fp = reqs[0].get("filepath") or reqs[0].get("_filename")
                            if fp and os.path.exists(fp):
                                audio_path = fp
                    except Exception:
                        pass
                    # Fallback: scan directory for common audio extensions
                    if not audio_path:
                        for name in os.listdir(tmpdir):
                            if name.lower().endswith((".m4a", ".webm", ".mp3", ".wav", ".ogg")):
                                audio_path = os.path.join(tmpdir, name)
                                break
            except Exception as dl_err:
                shutil.rmtree(tmpdir, ignore_errors=True)
                raise dl_err

            if not audio_path or not os.path.exists(audio_path):
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None

            # 2) Upload file to Replicate Files API
            files_url = "https://api.replicate.com/v1/files"
            headers = {"Authorization": f"Token {replicate_token}"}
            with open(audio_path, "rb") as f:
                r = await asyncio.to_thread(
                    requests.post, files_url, headers=headers, files={"file": f}
                )
            if r.status_code not in (200, 201):
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None
            data = r.json()
            file_url = data.get("urls", {}).get("get") or data.get("serving_url") or data.get("url")
            if not file_url:
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None

            # 3) Create Whisper prediction (openai/whisper large-v3)
            # Version from model page
            version_id = os.getenv(
                "OPENAI_WHISPER_VERSION",
                "3c08daf437fe359eb158a5123c395673f0a113dd8b4bd01ddce5936850e2a981",
            )
            create_url = "https://api.replicate.com/v1/predictions"
            headers_json = {
                "Authorization": f"Token {replicate_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "version": version_id,
                "input": {"audio": file_url, "language": language, "translate": False},
            }
            cr = await asyncio.to_thread(
                requests.post, create_url, headers=headers_json, json=payload
            )
            if cr.status_code not in (200, 201):
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None
            pred = cr.json()
            get_url = pred.get("urls", {}).get("get")
            if not get_url:
                shutil.rmtree(tmpdir, ignore_errors=True)
                return None

            # 4) Poll for completion
            deadline = time.time() + int(os.getenv("REPLICATE_POLL_TIMEOUT", "420"))
            text_out: Optional[str] = None
            while time.time() < deadline:
                await asyncio.sleep(1.0)
                gr = await asyncio.to_thread(requests.get, get_url, headers=headers_json)
                if gr.status_code != 200:
                    continue
                jd = gr.json()
                status = jd.get("status")
                if status in {"succeeded", "failed", "canceled"}:
                    if status != "succeeded":
                        break
                    out = jd.get("output")
                    if isinstance(out, str) and out.strip():
                        text_out = out
                    elif isinstance(out, dict):
                        for k in ("text", "transcription", "srt"):
                            v = out.get(k)
                            if isinstance(v, str) and v.strip():
                                text_out = v
                                break
                    elif isinstance(out, list):
                        text_out = "\n".join(map(str, out))
                    break

            return text_out
        finally:
            # 5) Always cleanup local temp directory
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)  # type: ignore[name-defined]
            except Exception:
                pass
    async def _replicate_whisper_transcribe(self, video_id: str, language: str = "en") -> Optional[str]:
        """Use Replicate's whisperx-video-transcribe to transcribe a YouTube URL.

        Model: adidoes/whisperx-video-transcribe
        Docs: https://replicate.com/adidoes/whisperx-video-transcribe

        Returns raw transcript text (SRT or plain) on success, or None on failure.
        """
        try:
            import os
            token = os.getenv("REPLICATE_API_TOKEN")
            if not token:
                logger.warning("Replicate API token not set; skipping Replicate fallback")
                return None

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            # Use generic predictions endpoint with explicit version to avoid 404s
            create_url = "https://api.replicate.com/v1/predictions"

            headers = {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                # Resolve and cache latest model version
                version_id = getattr(self, "_replicate_whisper_version", None)
                if not version_id:
                    version_id = await self._replicate_get_latest_version(session)
                    if not version_id:
                        logger.warning("Could not resolve Replicate model version")
                        return None
                    self._replicate_whisper_version = version_id

                payload = {
                    "version": version_id,
                    "input": {
                        # The model requires either 'audio' or 'url'
                        "url": youtube_url,
                        # whisperx runs alignment; keep minimal inputs for compatibility
                        "language": language
                    }
                }

                # Create prediction
                async with session.post(create_url, headers=headers, json=payload) as resp:
                    if resp.status not in (200, 201):
                        txt = await resp.text()
                        logger.warning(f"Replicate create failed ({resp.status}): {txt}")
                        return None
                    data = await resp.json()

                # Poll for completion (longer, with backoff)
                get_url = data.get("urls", {}).get("get") or f"https://api.replicate.com/v1/predictions/{data.get('id')}"
                try:
                    total_timeout_s = int(os.getenv("REPLICATE_POLL_TIMEOUT", "420"))  # default 7 minutes
                except Exception:
                    total_timeout_s = 420
                poll_interval_s = 1.0
                deadline = time.time() + total_timeout_s
                last_status = None
                while time.time() < deadline:
                    await asyncio.sleep(poll_interval_s)
                    poll_interval_s = min(5.0, poll_interval_s * 1.25)
                    async with session.get(get_url, headers=headers) as g:
                        if g.status != 200:
                            continue
                        status_data = await g.json()
                        status = status_data.get("status")
                        if status != last_status and status not in {None, ""}:
                            last_status = status
                            logger.info(f"Replicate prediction status: {status}")
                        if status in {"succeeded", "failed", "canceled"}:
                            if status != "succeeded":
                                # Surface logs/error details for debugging
                                err_msg = status_data.get("error")
                                logs_msg = status_data.get("logs")
                                if err_msg:
                                    logger.warning(f"Replicate transcription error: {err_msg}")
                                if logs_msg:
                                    logger.warning(f"Replicate logs: {logs_msg[:5000]}")
                                logger.warning(f"Replicate transcription ended with status={status}")
                                return None
                            output = status_data.get("output")
                            # Output could be a string (SRT or plain) or an object
                            if isinstance(output, str):
                                return output
                            if isinstance(output, list):
                                # Join possible segments/lines into a single text
                                try:
                                    return "\n".join(map(str, output))
                                except Exception:
                                    pass
                            # Try nested fields
                            if isinstance(output, dict):
                                for key in ("srt", "text", "transcript"):
                                    val = output.get(key)
                                    if isinstance(val, str) and val.strip():
                                        return val
                            logger.warning("Replicate returned unexpected output format")
                            return None
                logger.warning("Replicate polling timed out for transcription")
                return None
        except Exception as e:
            logger.error(f"Replicate fallback transcription error: {e}")
            return None

    async def _transcript_service_transcribe(self, video_id: str, language: str = "en") -> Optional[str]:
        """Optional self-hosted transcript service fallback if configured by TRANSCRIPT_SERVICE_URL.

        Expects a FastAPI endpoint compatible with the previously shared /transcribe spec
        returning {"srt": "..."} on success.
        """
        try:
            import os
            base_url = os.getenv("TRANSCRIPT_SERVICE_URL")
            if not base_url:
                return None
            url = base_url.rstrip("/") + "/transcribe"
            payload = {"video_id": video_id, "lang": language}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        txt = await resp.text()
                        logger.warning(f"Transcript-service failed ({resp.status}): {txt}")
                        return None
                    data = await resp.json()
            if data.get("error"):
                logger.warning(f"Transcript-service error: {data['error']}")
                return None
            srt_text = data.get("srt")
            if isinstance(srt_text, str) and srt_text.strip():
                return srt_text
            return None
        except Exception as e:
            logger.error(f"Transcript-service fallback error: {e}")
            return None

    async def _replicate_get_latest_version(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Fetch latest version id for the Replicate model and return its id.

        Uses adidoes/whisperx-video-transcribe
        """
        try:
            url = "https://api.replicate.com/v1/models/adidoes/whisperx-video-transcribe"
            import os
            token = os.getenv("REPLICATE_API_TOKEN")
            headers = {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            }
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    txt = await resp.text()
                    logger.warning(f"Failed to fetch Replicate model info ({resp.status}): {txt}")
                    return None
                data = await resp.json()
                latest = data.get("latest_version", {})
                version_id = latest.get("id")
                if version_id:
                    return version_id
                # Fallback: try versions list
                versions_url = url + "/versions"
                async with session.get(versions_url, headers=headers) as vresp:
                    if vresp.status != 200:
                        return None
                    vdata = await vresp.json()
                    items = vdata.get("results") or vdata.get("items") or []
                    if items:
                        return items[0].get("id")
            return None
        except Exception as e:
            logger.error(f"Error resolving Replicate model version: {e}")
            return None
            
    async def get_video_id_from_url(self, url: str) -> str:
        # Extract video ID from URL
        if "youtu.be" in url:
            return url.split("/")[-1]
        elif "youtube.com" in url:
            return url.split("v=")[1].split("&")[0]
        else:
            raise ValueError("Invalid YouTube URL")
            
    async def get_video_duration(self, video_id: str) -> int:
        """
        Fetch video duration in seconds using YouTube Data API.
        If a quotaExceeded error is encountered, rotate the API key and retry.
        """
        attempts = 0
        max_attempts = len(self.api_keys)  # Try each API key once
        
        while attempts < max_attempts:
            try:
                # Ensure quota is available (this might rotate if quota is low)
                await self._update_quota(cost=1)
                
                # Execute the API request in a background thread, since execute() is blocking.
                video_response = await asyncio.to_thread(
                    lambda: self.youtube.videos().list(
                        part="contentDetails",
                        id=video_id
                    ).execute()
                )
                
                if 'items' in video_response and video_response['items']:
                    duration_string = video_response['items'][0]['contentDetails']['duration']
                    return self.parse_duration(duration_string)
                else:
                    logger.warning(f"No content details found for video ID {video_id}")
                    return 0
                    
            except HttpError as e:
                # Check if the error indicates that the quota is exceeded.
                if "quotaExceeded" in str(e):
                    logger.warning(f"YouTube API quota exceeded for key {self.current_key_index+1}/{len(self.api_keys)}. Rotating key...")
                    await self._rotate_api_key()
                    attempts += 1
                else:
                    logger.error(f"Error getting video duration for video {video_id}: {str(e)}")
                    return 0
            except Exception as e:
                logger.error(f"Unexpected error getting video duration: {str(e)}")
                return 0
                
        # All API keys have been exhausted or are in cooldown.
        logger.error(f"All {len(self.api_keys)} YouTube API keys exhausted. Please add more keys or wait for quota reset.")
        return 0  # Return 0 instead of raising an exception

def parse_youtube_date(date_string: str) -> datetime:
    """Convert YouTube date string to datetime object"""
    try:
        # Return current time if date string is empty
        if not date_string or date_string.strip() == '':
            logger.warning("Empty date string provided to parse_youtube_date, using current date")
            return datetime.utcnow()
            
        # Try standard format first
        if '.' in date_string:
            # Format with microseconds
            return datetime.strptime(date_string.split('.')[0] + 'Z', '%Y-%m-%dT%H:%M:%SZ')
        else:
            # Standard format without microseconds
            return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%SZ')
    except Exception as e:
        logger.error(f"Error parsing date {date_string!r}: {str(e)}")
        return datetime.utcnow()

async def get_trending_videos_with_smart_search(series, theme, example_titles, custom_niche=None):
    """Get trending videos using Claude-generated search terms"""
    
    # Generate smart search terms
    search_terms = await generate_search_terms(series, theme, example_titles, custom_niche)
    
    # Search for trending videos with each term
    all_trending_videos = []
    for search_term in search_terms:
        videos = await get_trending_youtube_topics(search_term, hours_ago=48, limit=5)
        all_trending_videos.extend(videos)
    
    # Deduplicate by video ID
    seen_ids = set()
    unique_videos = []
    for video in all_trending_videos:
        if video['id'] not in seen_ids:
            seen_ids.add(video['id'])
            unique_videos.append(video)
    
    # Sort by view velocity again
    unique_videos.sort(key=lambda x: x.get('view_velocity', 0), reverse=True)
    
    # Extract useful trend information
    trend_info = {
        'trending_titles': [video['title'] for video in unique_videos[:10]],
        'trending_channels': list(set(video['channel'] for video in unique_videos[:10])),
        'trending_keywords': await extract_keywords_from_titles([v['title'] for v in unique_videos])
    }
    
    return trend_info


async def get_trending_youtube_topics(search_term: str, hours_ago: int = 168, limit: int = 5) -> List[Dict]:
    """
    Find trending YouTube videos for a specific search term, focusing on recent uploads with high engagement
    
    Args:
        search_term: The search query to use for finding videos
        hours_ago: How recent the videos should be (in hours)
        limit: Maximum number of videos to return
        
    Returns:
        List of video dictionaries with id, title, channel, view_count, and view_velocity
    """
    logger.info(f"Searching for trending videos with term: '{search_term}'")
    
    try:
        from datetime import datetime, timedelta
        import googleapiclient.discovery
        import random
        from config import YOUTUBE_API_KEYS
        
        # First try HTML scraping as a fallback method that doesn't use API quota
        try:
            logger.info(f"Trying HTML scraping first to find trending videos for '{search_term}'")
            # Use the existing search method that handles quotas and fallbacks
            youtube_service = YouTubeService(YOUTUBE_API_KEYS)
            
            # Try HTML scraping directly first
            html_results = await youtube_service._search_videos_html_scrape(
                query=search_term,
                max_results=min(limit * 3, 50),
                order="viewCount"  # Sort by view count
            )
            
            if html_results:
                logger.info(f"Found {len(html_results)} videos via HTML scraping for '{search_term}'")
                # Process these results into the expected format
                trending_videos = []
                now = datetime.utcnow()
                
                for video in html_results:
                    # Try to parse publication date
                    try:
                        published_at = parse_youtube_date(video.get('publishedAt', ''))
                        hours_since_publication = max(1, (now - published_at).total_seconds() / 3600)
                        
                        # Only include recent videos
                        if hours_since_publication <= hours_ago:
                            # Get view count
                            view_count = int(video.get('viewCount', 0))
                            if isinstance(view_count, str):
                                view_count = int(view_count.replace(',', ''))
                            
                            # Calculate view velocity (views per hour)
                            view_velocity = view_count / hours_since_publication
                            
                            trending_videos.append({
                                "id": video.get('id', ''),
                                "title": video.get('title', ''),
                                "channel": video.get('channelTitle', ''),
                                "published_at": video.get('publishedAt', ''),
                                "view_count": view_count,
                                "view_velocity": view_velocity
                            })
                    except Exception as parse_error:
                        logger.debug(f"Error processing HTML video result: {str(parse_error)}")
                        continue
                
                # Sort by view velocity and return top results
                trending_videos.sort(key=lambda x: x["view_velocity"], reverse=True)
                return trending_videos[:limit]
        except Exception as html_error:
            logger.warning(f"HTML scraping failed for trending videos: {str(html_error)}")
        
        # Try synchronous youtube-search-python as another fallback
        try:
            logger.info(f"Trying youtube-search-python for trending videos for '{search_term}'")
            from youtubesearchpython import VideosSearch
            
            # Calculate the timestamp for videos from the last X hours
            now = datetime.utcnow()
            filter_date = now - timedelta(hours=hours_ago)
            
            # Use synchronous version which doesn't have proxies issues
            videos_search = VideosSearch(search_term, limit=min(limit * 3, 50))
            results = videos_search.result()
            trending_videos = []
            
            for item in results.get('result', []):
                try:
                    # Parse publication date if available
                    published_at = item.get('publishTime', '')
                    if not published_at:
                        # Skip if we can't determine age
                        continue
                        
                    published_date = parse_youtube_date(published_at)
                    hours_since_publication = max(1, (now - published_date).total_seconds() / 3600)
                    
                    # Only include videos published within specified timeframe
                    if hours_since_publication <= hours_ago:
                        # Get view count
                        view_text = item.get('viewCount', {}).get('text', '0 views')
                        view_count = int(''.join(filter(str.isdigit, view_text)))
                        
                        # Calculate view velocity
                        view_velocity = view_count / hours_since_publication
                        
                        trending_videos.append({
                            "id": item.get('id', ''),
                            "title": item.get('title', ''),
                            "channel": item.get('channel', {}).get('name', ''),
                            "published_at": published_at,
                            "view_count": view_count,
                            "view_velocity": view_velocity
                        })
                except Exception as item_error:
                    logger.debug(f"Error processing search item: {str(item_error)}")
                    continue
            
            # Sort by view velocity and return top results
            if trending_videos:
                trending_videos.sort(key=lambda x: x["view_velocity"], reverse=True)
                logger.info(f"Found {len(trending_videos)} trending videos via youtube-search-python")
                return trending_videos[:limit]
        except Exception as search_error:
            logger.warning(f"youtube-search-python fallback failed: {str(search_error)}")
        
        # Calculate the timestamp for videos from the last X hours
        now = datetime.utcnow()
        published_after = (now - timedelta(hours=hours_ago)).isoformat("T") + "Z"
        
        # Check if any API key is available before trying API request
        youtube_service = YouTubeService(YOUTUBE_API_KEYS)
        if not await youtube_service._any_key_available():
            logger.error("All YouTube API keys are exhausted. Could not get trending videos.")
            return []
        
        # Use YouTube Data API to search for videos
        api_key = random.choice(YOUTUBE_API_KEYS)
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
        
        # Search for videos matching the query
        search_response = await asyncio.to_thread(
            youtube.search().list(
                q=search_term,
                part="id,snippet",
                type="video",
                order="viewCount",  # Sort by view count to get popular videos
                publishedAfter=published_after,
                maxResults=min(limit * 3, 50)  # Request more videos than needed to filter
            ).execute
        )
        
        # Extract video IDs to get more detailed info
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
        
        if not video_ids:
            logger.warning(f"No videos found for search term: '{search_term}'")
            return []
            
        # Get detailed video info including view counts
        videos_response = await asyncio.to_thread(
            youtube.videos().list(
                id=",".join(video_ids),
                part="snippet,statistics,contentDetails"
            ).execute
        )
        
        # Process videos to include view velocity (views ÷ hours since publication)
        trending_videos = []
        now = datetime.utcnow()
        
        for item in videos_response.get("items", []):
            # Parse publication date
            published_at = datetime.fromisoformat(
                item["snippet"]["publishedAt"].replace("Z", "+00:00")
            )
            hours_since_publication = max(1, (now - published_at.replace(tzinfo=None)).total_seconds() / 3600)
            
            # Get view count
            view_count = int(item["statistics"].get("viewCount", 0))
            
            # Calculate view velocity (views per hour)
            view_velocity = view_count / hours_since_publication
            
            trending_videos.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "view_count": view_count,
                "view_velocity": view_velocity
            })
        
        # Sort by view velocity and return the top results
        trending_videos.sort(key=lambda x: x["view_velocity"], reverse=True)
        
        logger.info(f"Found {len(trending_videos)} trending videos for '{search_term}', returning top {limit}")
        return trending_videos[:limit]
    
    except Exception as e:
        logger.error(f"Error finding trending videos for '{search_term}': {str(e)}")
        return []
