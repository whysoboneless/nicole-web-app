"""
Campaign Channel Discovery Service
Uses AI to discover channels for product sales campaigns based on product research
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from anthropic import AsyncAnthropic
import os

logger = logging.getLogger(__name__)

# Get API key from environment
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')


class CampaignChannelDiscoveryService:
    """
    Service for discovering channels for product sales campaigns using AI
    """
    
    def __init__(self, youtube_service, db, analysis_service=None):
        """
        Initialize the service
        
        Args:
            youtube_service: YouTube service instance
            db: Database instance
            analysis_service: AnalysisService instance (optional, for group creation)
        """
        self.youtube_service = youtube_service
        self.db = db
        self.analysis_service = analysis_service
        self.claude_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
    
    async def discover_channels_for_product(
        self,
        product_research: Dict,
        count: int = 5
    ) -> List[Dict]:
        """
        Discover channels that match a product's target audience using AI
        
        Args:
            product_research: Product research data from ProductResearchService
            count: Number of channels to discover
            
        Returns:
            List of discovered channels with match scores and AI analysis
        """
        try:
            logger.info(f"🔍 Starting AI-powered channel discovery for product")
            
            # Extract data from product research
            content_types = product_research.get('content_preferences', {}).get('content_types', [])
            target_audience = product_research.get('target_audience', {})
            product_info = product_research.get('product', {})
            
            if not content_types:
                logger.warning("No content types found in product research")
                return []
            
            logger.info(f"Content types (niche): {content_types}")
            logger.info(f"Target audience: {target_audience}")
            
            discovered_channels = []
            
            # Strategy 1: Direct Match - Use AI to find channels in exact content type
            direct_channels = await self._discover_direct_channels_ai(
                content_types,
                target_audience,
                product_info,
                count // 2
            )
            for channel in direct_channels:
                channel['match_type'] = 'direct'
                discovered_channels.append(channel)
            
            # Strategy 2: Indirect Match - Use AI to find channels with adaptable series/themes
            if len(discovered_channels) < count:
                indirect_channels = await self._discover_indirect_channels_ai(
                    content_types,
                    target_audience,
                    product_info,
                    count - len(discovered_channels)
                )
                for channel in indirect_channels:
                    channel['match_type'] = 'indirect'
                    discovered_channels.append(channel)
            
            # Sort by match score and return top N
            discovered_channels.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            
            logger.info(f"✅ Discovered {len(discovered_channels)} channels using AI")
            return discovered_channels[:count]
            
        except Exception as e:
            logger.error(f"Error discovering channels: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _discover_direct_channels_ai(
        self,
        content_types: List[str],
        target_audience: Dict,
        product_info: Dict,
        count: int
    ) -> List[Dict]:
        """
        Use AI to find channels that directly match the product's content types
        
        Args:
            content_types: List of content types (niche keywords)
            target_audience: Target audience data
            product_info: Product information
            count: Number of channels to find
            
        Returns:
            List of channel data with AI analysis
        """
        discovered = []
        
        if not self.claude_client:
            logger.error("Anthropic API key not available")
            return []
        
        # Use first content type as primary search keyword
        primary_keyword = content_types[0] if content_types else "tutorial"
        
        try:
            # Search for channels using content type as keyword
            if hasattr(self.youtube_service, 'search_videos_sync'):
                search_results = self.youtube_service.search_videos_sync(
                    primary_keyword,
                    max_results=50
                )
            else:
                search_results = await self.youtube_service.search_videos(
                    primary_keyword,
                    max_results=50
                )
            
            if not search_results or 'videos' not in search_results:
                logger.warning("No search results for direct match")
                return []
            
            processed_channels = set()
            
            for video in search_results.get('videos', [])[:50]:
                channel_id = video.get('channelId')
                if not channel_id or channel_id in processed_channels:
                    continue
                
                processed_channels.add(channel_id)
                
                try:
                    # Fetch channel data
                    if hasattr(self.youtube_service, 'fetch_channel_data_sync'):
                        channel_data = self.youtube_service.fetch_channel_data_sync(channel_id)
                    else:
                        channel_data = await self.youtube_service.fetch_channel_data(channel_id)
                    
                    if not channel_data:
                        continue
                    
                    # Fetch channel videos
                    if hasattr(self.youtube_service, 'fetch_channel_videos_sync'):
                        videos = self.youtube_service.fetch_channel_videos_sync(channel_id, max_results=10)
                    else:
                        videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=10)
                    
                    if not videos:
                        continue
                    
                    # Use AI to analyze if channel matches product's target audience
                    matches = await self._ai_analyze_channel_match(
                        channel_data,
                        videos,
                        content_types,
                        target_audience,
                        product_info,
                        match_type='direct'
                    )
                    
                    if matches.get('is_match'):
                        discovered.append({
                            'channel_id': channel_id,
                            'channel_name': channel_data.get('title', 'Unknown'),
                            'channel_url': f"https://youtube.com/channel/{channel_id}",
                            'subscriber_count': channel_data.get('subscriberCount', 0),
                            'video_count': channel_data.get('videoCount', 0),
                            'content_type': primary_keyword,
                            'match_score': matches.get('match_score', 0.8),
                            'ai_analysis': matches.get('analysis', ''),
                            'sample_video': {
                                'id': videos[0].get('id', ''),
                                'title': videos[0].get('title', '')
                            }
                        })
                        
                        if len(discovered) >= count:
                            break
                except Exception as e:
                    logger.warning(f"Error processing channel {channel_id}: {e}")
                    continue
            
            return discovered
            
        except Exception as e:
            logger.error(f"Error in AI direct channel discovery: {e}")
            return []
    
    async def _discover_indirect_channels_ai(
        self,
        content_types: List[str],
        target_audience: Dict,
        product_info: Dict,
        count: int
    ) -> List[Dict]:
        """
        Use AI to find channels with adaptable series/themes that can be adapted to product
        
        Args:
            content_types: Target content types
            target_audience: Target audience data
            product_info: Product information
            count: Number of channels to find
            
        Returns:
            List of channel data with AI analysis and adaptation notes
        """
        discovered = []
        
        if not self.claude_client:
            logger.error("Anthropic API key not available")
            return []
        
        # Search for popular content formats that can be adapted
        adaptable_formats = [
            "top 10",
            "top 5",
            "documentary",
            "educational",
            "explained",
            "how to"
        ]
        
        try:
            for format_keyword in adaptable_formats[:3]:  # Limit searches
                if len(discovered) >= count:
                    break
                
                # Search for channels
                if hasattr(self.youtube_service, 'search_videos_sync'):
                    search_results = self.youtube_service.search_videos_sync(
                        format_keyword,
                        max_results=30
                    )
                else:
                    search_results = await self.youtube_service.search_videos(
                        format_keyword,
                        max_results=30
                    )
                
                if not search_results or 'videos' not in search_results:
                    continue
                
                processed_channels = set()
                
                for video in search_results.get('videos', [])[:30]:
                    channel_id = video.get('channelId')
                    if not channel_id or channel_id in processed_channels:
                        continue
                    
                    processed_channels.add(channel_id)
                    
                    try:
                        # Fetch channel data
                        if hasattr(self.youtube_service, 'fetch_channel_data_sync'):
                            channel_data = self.youtube_service.fetch_channel_data_sync(channel_id)
                        else:
                            channel_data = await self.youtube_service.fetch_channel_data(channel_id)
                        
                        if not channel_data:
                            continue
                        
                        # Check if channel has good engagement
                        if channel_data.get('subscriberCount', 0) < 1000:
                            continue
                        
                        # Fetch videos
                        if hasattr(self.youtube_service, 'fetch_channel_videos_sync'):
                            videos = self.youtube_service.fetch_channel_videos_sync(channel_id, max_results=10)
                        else:
                            videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=10)
                        
                        if not videos:
                            continue
                        
                        # Use AI to analyze if channel can be adapted
                        adaptation_analysis = await self._ai_analyze_channel_adaptation(
                            channel_data,
                            videos,
                            content_types,
                            target_audience,
                            product_info,
                            format_keyword
                        )
                        
                        if adaptation_analysis.get('can_adapt'):
                            discovered.append({
                                'channel_id': channel_id,
                                'channel_name': channel_data.get('title', 'Unknown'),
                                'channel_url': f"https://youtube.com/channel/{channel_id}",
                                'subscriber_count': channel_data.get('subscriberCount', 0),
                                'video_count': channel_data.get('videoCount', 0),
                                'content_format': format_keyword,
                                'match_score': adaptation_analysis.get('match_score', 0.6),
                                'adaptation_notes': adaptation_analysis.get('adaptation_strategy', ''),
                                'ai_analysis': adaptation_analysis.get('analysis', ''),
                                'sample_video': {
                                    'id': video.get('id', ''),
                                    'title': video.get('title', '')
                                }
                            })
                            
                            if len(discovered) >= count:
                                break
                    except Exception as e:
                        logger.warning(f"Error processing indirect channel {channel_id}: {e}")
                        continue
            
            return discovered
            
        except Exception as e:
            logger.error(f"Error in AI indirect channel discovery: {e}")
            return []
    
    async def _ai_analyze_channel_match(
        self,
        channel_data: Dict,
        videos: List[Dict],
        content_types: List[str],
        target_audience: Dict,
        product_info: Dict,
        match_type: str = 'direct'
    ) -> Dict:
        """
        Use Claude AI to analyze if a channel matches the product's target audience
        
        Returns:
            {
                'is_match': bool,
                'match_score': float (0-1),
                'analysis': str
            }
        """
        if not self.claude_client:
            return {'is_match': False, 'match_score': 0.0, 'analysis': 'AI not available'}
        
        try:
            video_titles = [v.get('title', '') for v in videos[:10]]
            video_descriptions = [v.get('description', '')[:200] for v in videos[:10]]
            
            product_name = product_info.get('name', 'Unknown Product')
            primary_buyers = target_audience.get('primary_buyers', [])
            content_types_str = ', '.join(content_types)
            
            prompt = f"""Analyze if this YouTube channel matches the product's target audience and content preferences.

PRODUCT INFORMATION:
- Product Name: {product_name}
- Target Audience: {', '.join(primary_buyers) if primary_buyers else 'Not specified'}
- Content Types Audience Watches: {content_types_str}

CHANNEL INFORMATION:
Channel Name: {channel_data.get('title', 'Unknown')}
Channel Description: {channel_data.get('description', 'No description')[:500]}

Recent Video Titles:
{chr(10).join(f"- {title}" for title in video_titles)}

Video Descriptions (first 200 chars):
{chr(10).join(f"- {desc}..." for desc in video_descriptions if desc)}

ANALYSIS REQUIREMENTS:
1. Does this channel create content that the target audience would watch?
2. Does the channel's content match any of these content types: {content_types_str}?
3. Would someone interested in {product_name} find this channel relevant?
4. Does the channel's audience overlap with: {', '.join(primary_buyers) if primary_buyers else 'general audience'}?

Respond in JSON format:
{{
    "is_match": true/false,
    "match_score": 0.0-1.0,
    "reasoning": "Brief explanation of why this channel matches or doesn't match",
    "content_alignment": "How well the channel's content aligns with the target content types"
}}"""
            
            response = await self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse JSON response
            import json
            try:
                # Extract JSON from response (might have markdown code blocks)
                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0].strip()
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0].strip()
                
                analysis = json.loads(result_text)
                
                return {
                    'is_match': analysis.get('is_match', False),
                    'match_score': float(analysis.get('match_score', 0.0)),
                    'analysis': analysis.get('reasoning', '') + ' ' + analysis.get('content_alignment', '')
                }
            except json.JSONDecodeError:
                # Fallback: parse boolean from text
                is_match = 'true' in result_text.lower() or 'match' in result_text.lower()
                return {
                    'is_match': is_match,
                    'match_score': 0.7 if is_match else 0.3,
                    'analysis': result_text[:200]
                }
            
        except Exception as e:
            logger.error(f"Error in AI channel match analysis: {e}")
            return {'is_match': False, 'match_score': 0.0, 'analysis': f'Error: {str(e)}'}
    
    async def _ai_analyze_channel_adaptation(
        self,
        channel_data: Dict,
        videos: List[Dict],
        content_types: List[str],
        target_audience: Dict,
        product_info: Dict,
        current_format: str
    ) -> Dict:
        """
        Use Claude AI to analyze if a channel's series/themes can be adapted to product
        
        Returns:
            {
                'can_adapt': bool,
                'match_score': float (0-1),
                'adaptation_strategy': str,
                'analysis': str
            }
        """
        if not self.claude_client:
            return {'can_adapt': False, 'match_score': 0.0, 'adaptation_strategy': 'AI not available'}
        
        try:
            video_titles = [v.get('title', '') for v in videos[:10]]
            
            product_name = product_info.get('name', 'Unknown Product')
            primary_buyers = target_audience.get('primary_buyers', [])
            content_types_str = ', '.join(content_types)
            
            prompt = f"""Analyze if this channel's series and themes can be adapted to promote the product.

UNDERSTANDING SERIES & THEMES CLASSIFICATION:
Our system uses a hierarchical structure: Series > Themes > Topics

1. **SERIES**: A collection of videos with a CONSISTENT TITLE FORMAT/STRUCTURE
   - Series names are based on REPETITIVE TITLE PATTERNS across multiple videos
   - Examples: "Top 10...", "Roblox But...", "How to...", "Documentary: ..."
   - Series = The recurring format/structure that ties videos together

2. **THEMES**: Broader categories within a series that group related topics
   - Themes are the overarching narrative or idea the series explores
   - They should be general enough to encompass multiple videos but specific to the series
   - Examples for "Top 10" series: "Product Reviews", "Buying Guides", "Tips & Tricks"
   - Examples for "Roblox But" series: "Time-Based Changes", "Player Limitations"

3. **TOPICS**: Specific subject matter for each individual video
   - Topics are exact phrases from video titles
   - They differentiate one episode from another within the same theme
   - Example: For title "Top 10 Best Laptops 2024", topic = "Best Laptops 2024"

ADAPTATION STRATEGY:
- We can adapt a channel by keeping the SERIES structure (format) but changing:
  * The THEMES to focus on {product_name}-related categories
  * The TOPICS to be about {product_name} or its benefits
  * The niche from current content to {content_types_str}

PRODUCT INFORMATION:
- Product Name: {product_name}
- Target Audience: {', '.join(primary_buyers) if primary_buyers else 'Not specified'}
- Content Types Audience Watches: {content_types_str} (this is the niche we want to adapt to)

CHANNEL INFORMATION:
Channel Name: {channel_data.get('title', 'Unknown')}
Channel Description: {channel_data.get('description', 'No description')[:300]}
Current Content Format: {current_format} (e.g., "Top 10", "Documentary", "Educational")

Recent Video Titles (analyze for series structure):
{chr(10).join(f"- {title}" for title in video_titles)}

ADAPTATION ANALYSIS QUESTIONS:
1. Can this channel's SERIES structure (recurring title format) be maintained while adapting THEMES to {product_name}?
   - Example: "Top 10 X" → "Top 10 {product_name} Tips" or "Top 10 Ways {product_name} Helps"
   
2. Can we identify THEMES in this channel that could be adapted to {content_types_str} content?
   - Would themes like "Product Reviews", "Buying Guides", "Tutorials" work for {product_name}?
   
3. Can we generate new TOPICS within adapted themes that would appeal to: {', '.join(primary_buyers) if primary_buyers else 'the target audience'}?
   - Can we create {product_name}-specific topics that fit the series structure?

4. Would the adapted series structure + themes + topics appeal to the target audience?
   - Does the format match what they watch ({content_types_str})?

CONCRETE EXAMPLES:
- "Top 10 Gaming Chairs" channel → Adapt to "Top 10 {product_name} Features" for {primary_buyers[0] if primary_buyers else 'target audience'}
- "Documentary: History of X" channel → Adapt to "Documentary: How {product_name} Works" 
- "How to X" channel → Adapt to "How to Use {product_name}" or "How {product_name} Helps With Y"

Respond in JSON format:
{{
    "can_adapt": true/false,
    "match_score": 0.0-1.0,
    "adaptation_strategy": "Specific strategy: Keep SERIES structure '[format]', adapt THEMES to '[themes]', create TOPICS about '[product-related topics]'",
    "example_adapted_title": "Example title showing how the series structure would look with product focus",
    "identified_series_structure": "The recurring title pattern you identified (e.g., 'Top 10...', 'How to...')",
    "suggested_themes": ["Theme 1", "Theme 2"] - themes that would work for product content,
    "reasoning": "Brief explanation focusing on series structure preservation and theme/topic adaptation"
}}"""
            
            response = await self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse JSON response
            import json
            try:
                # Extract JSON from response
                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0].strip()
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0].strip()
                
                analysis = json.loads(result_text)
                
                # Build detailed analysis string
                analysis_parts = []
                if analysis.get('reasoning'):
                    analysis_parts.append(analysis.get('reasoning'))
                if analysis.get('identified_series_structure'):
                    analysis_parts.append(f"Series Structure: {analysis.get('identified_series_structure')}")
                if analysis.get('suggested_themes'):
                    themes_str = ', '.join(analysis.get('suggested_themes', []))
                    analysis_parts.append(f"Suggested Themes: {themes_str}")
                if analysis.get('example_adapted_title'):
                    analysis_parts.append(f"Example: {analysis.get('example_adapted_title')}")
                
                return {
                    'can_adapt': analysis.get('can_adapt', False),
                    'match_score': float(analysis.get('match_score', 0.0)),
                    'adaptation_strategy': analysis.get('adaptation_strategy', ''),
                    'identified_series_structure': analysis.get('identified_series_structure', ''),
                    'suggested_themes': analysis.get('suggested_themes', []),
                    'analysis': ' | '.join(analysis_parts) if analysis_parts else analysis.get('reasoning', '')
                }
            except json.JSONDecodeError:
                # Fallback: parse boolean from text
                can_adapt = 'true' in result_text.lower() or 'adapt' in result_text.lower()
                return {
                    'can_adapt': can_adapt,
                    'match_score': 0.6 if can_adapt else 0.2,
                    'adaptation_strategy': result_text[:300],
                    'identified_series_structure': '',
                    'suggested_themes': [],
                    'analysis': result_text[:200]
                }
            
        except Exception as e:
            logger.error(f"Error in AI channel adaptation analysis: {e}")
            return {
                'can_adapt': False,
                'match_score': 0.0,
                'adaptation_strategy': f'Error: {str(e)}',
                'identified_series_structure': '',
                'suggested_themes': [],
                'analysis': f'Error: {str(e)}'
            }
    
    async def create_group_from_discovered_channel(
        self,
        channel_id: str,
        channel_url: str,
        product_research: Dict,
        match_type: str,
        user_id: str,
        group_name: Optional[str] = None
    ) -> Dict:
        """
        Create a group from a discovered channel
        
        Args:
            channel_id: YouTube channel ID
            channel_url: Channel URL
            product_research: Product research data
            match_type: 'direct' or 'indirect'
            user_id: User Discord ID
            group_name: Optional group name
            
        Returns:
            {
                'success': bool,
                'group_id': str,
                'content_style_id': Optional[str],
                'custom_niche': Optional[str]  # For indirect matches
            }
        """
        try:
            logger.info(f"Creating group from channel {channel_id}")
            
            # Fetch channel data
            if hasattr(self.youtube_service, 'fetch_channel_data_sync'):
                channel_data = self.youtube_service.fetch_channel_data_sync(channel_id)
            else:
                channel_data = await self.youtube_service.fetch_channel_data(channel_id)
            
            if hasattr(self.youtube_service, 'fetch_channel_videos_sync'):
                videos = self.youtube_service.fetch_channel_videos_sync(channel_id, max_results=50)
            else:
                videos = await self.youtube_service.fetch_channel_videos(channel_id, max_results=50)
            
            if not channel_data or not videos:
                return {
                    'success': False,
                    'error': 'Failed to fetch channel data'
                }
            
            # Generate group name if not provided
            if not group_name:
                channel_title = channel_data.get('title', 'Unknown Channel')
                product_name = product_research.get('product', {}).get('name', 'Product')
                group_name = f"{product_name} - {channel_title}"
            
            # Create group document
            from datetime import datetime, timezone
            
            group_data = {
                "name": group_name,
                "user_id": user_id,
                "main_channel_id": channel_id,
                "main_channel_data": {
                    "id": channel_id,
                    "title": channel_data.get('title', ''),
                    "description": channel_data.get('description', ''),
                    "subscriberCount": channel_data.get('subscriberCount', 0),
                    "videoCount": channel_data.get('videoCount', 0),
                    "videos": videos
                },
                "competitors": [],
                "series_data": [],
                "is_public": False,
                "createdAt": datetime.now(timezone.utc),
                "lastUpdated": datetime.now(timezone.utc),
                "allowed_users": [user_id]
            }
            
            # Store custom_niche for indirect matches (content types)
            if match_type == 'indirect':
                content_types = product_research.get('content_preferences', {}).get('content_types', [])
                if content_types:
                    group_data['custom_niche'] = content_types[0]  # Primary content type
            
            # Save to database
            group_id = await self.db.create_competitor_group(group_data)
            
            if not group_id:
                return {
                    'success': False,
                    'error': 'Failed to create group'
                }
            
            return {
                'success': True,
                'group_id': str(group_id),
                'custom_niche': group_data.get('custom_niche'),
                'content_style_id': None  # Will be identified/created later
            }
            
        except Exception as e:
            logger.error(f"Error creating group from channel: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance (will be initialized with dependencies)
campaign_channel_discovery_service = None


def get_campaign_channel_discovery_service(youtube_service, db, analysis_service=None):
    """Get or create the campaign channel discovery service"""
    global campaign_channel_discovery_service
    if campaign_channel_discovery_service is None:
        campaign_channel_discovery_service = CampaignChannelDiscoveryService(
            youtube_service,
            db,
            analysis_service
        )
    return campaign_channel_discovery_service

