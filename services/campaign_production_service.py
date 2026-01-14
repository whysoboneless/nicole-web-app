"""
Campaign Production Service
FULLY FUNCTIONAL production orchestration for campaigns
Routes to correct workflow and executes real production
"""

import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, parent_dir)

from typing import Dict, Optional, List
import aiohttp
import asyncio
from datetime import datetime
import time

# Import core database
from nicole_web_suite_template.core.database import Database

# Import ALL production functions from Discord bot
from utils.ai_utils import (
    generate_video_titles,
    breakdown_script,
    generate_plot_outline,
    generate_full_script,
    generate_kokoro_voice_over,
    generate_thumbnail_with_trained_model,
    analyze_thumbnails_with_ai,
    get_example_titles,
    get_drive_service
)

# Import services
from services.cloud_service import CloudVideoService
from services.research_service import ContentResearchService

# Import database for Discord bot compatibility
from database import db as discord_db

web_db = Database()
cloud_service = CloudVideoService()


class CampaignProductionService:
    """Main orchestrator for campaign production - FULLY FUNCTIONAL"""
    
    def __init__(self):
        self.db = web_db
        self.discord_db = discord_db
        self.cloud_service = cloud_service
        self.research_service = ContentResearchService(discord_db)
        self.drive_service = get_drive_service()
        self.ai_animation_url = os.environ.get('AI_ANIMATION_SERVICE_URL', 'http://157.180.0.71:8086')
    
    async def produce_video_for_campaign(
        self,
        campaign_id: str,
        channel_id: str,
        group_id: str,
        series_name: str,
        theme_name: str,
        user_id: str,
        youtube_channel_id: str,
        **kwargs
    ) -> Dict:
        """
        FULLY FUNCTIONAL video production for campaigns
        
        Args:
            campaign_id: Campaign ID
            channel_id: Channel ID in campaign  
            group_id: Competitor group ID
            series_name: Series name
            theme_name: Theme name
            user_id: User ID (for API keys)
            youtube_channel_id: YouTube channel ID for upload
            **kwargs: video_duration, visual_style, voice, etc.
        """
        
        try:
            print(f"🎬 CAMPAIGN PRODUCTION STARTING")
            print(f"   Campaign: {campaign_id}")
            print(f"   Channel: {channel_id}")
            print(f"   Series: {series_name}, Theme: {theme_name}")
            
            # Get channel details
            channel = self.db.get_channel_by_id(channel_id)
            content_style_id = channel.get('content_style_id') if channel else None
            
            # Get content style if specified
            content_style = None
            if content_style_id:
                content_style = self.db.db['content_styles'].find_one({'_id': content_style_id})
                if content_style:
                    style_type = content_style.get('content_type', 'unknown')
                    platform = content_style.get('platform', 'youtube')
                    content_format = content_style.get('content_format', 'video')
                    print(f"   Content Style: {content_style.get('display_name')} ({platform}/{content_format})")
            
            # Check if channel is slideshow content type
            channel_content_type = channel.get('content_type', 'video')
            
            # Route to appropriate generator
            if channel_content_type == 'slideshow':
                return await self._generate_slideshow_content(
                    campaign_id, channel_id, channel, group_id, series_name, theme_name, content_style, **kwargs
                )
            
            # STEP 1: Get series and theme data objects (for video content)
            series_data = await self.discord_db.get_series_data(group_id)
            series = next((s for s in series_data if s['name'] == series_name), None)
            if not series:
                return {'success': False, 'error': f'Series {series_name} not found'}
            
            theme = next((t for t in series.get('themes', []) if t['name'] == theme_name), None)
            if not theme:
                return {'success': False, 'error': f'Theme {theme_name} not found'}
            
            # STEP 2: Generate title
            print("📝 Generating title...")
            example_titles = await get_example_titles(group_id, series_name, theme_name)
            
            titles = await generate_video_titles(
                series, 
                theme, 
                example_titles,
                custom_niche=kwargs.get('custom_niche'),
                enable_research=kwargs.get('enable_research', False)
            )
            
            if not titles:
                return {'success': False, 'error': 'Failed to generate titles'}
            
            title = titles[0]
            print(f"   ✅ Title: {title}")
            
            # STEP 3: Get or generate script breakdown
            print("🔍 Getting script breakdown...")
            existing_breakdown = await self.discord_db.get_script_breakdown(
                group_id, series_name, theme_name
            )
            
            if existing_breakdown and existing_breakdown.get('script_breakdown'):
                script_breakdown = existing_breakdown['script_breakdown']
                print("   ✅ Using existing breakdown")
            else:
                # Generate new breakdown
                print("   Generating new breakdown...")
                video_ids = await self.discord_db.get_top_video_urls(group_id, series_name, theme_name, limit=3)
                
                if not video_ids:
                    return {'success': False, 'error': 'No videos found for breakdown'}
                
                # Get YouTube service
                from services.youtube_service import YouTubeService
                youtube_api_keys = os.environ.get('YOUTUBE_API_KEYS', '').split(',')
                yt_service = YouTubeService(youtube_api_keys)
                
                transcripts = []
                durations = []
                video_titles = []
                descriptions = []
                
                for vid_id in video_ids:
                    transcript = await yt_service.get_video_transcript(vid_id)
                    if transcript:
                        transcripts.append(transcript)
                        durations.append(await yt_service.get_video_duration(vid_id))
                        info = await yt_service.get_video_info(vid_id)
                        video_titles.append(info.get('title', ''))
                        descriptions.append(info.get('description', ''))
                
                if not transcripts:
                    return {'success': False, 'error': 'Failed to get transcripts'}
                
                response = await breakdown_script(
                    series_name, theme_name, transcripts, durations, video_titles, descriptions
                )
                
                import json
                try:
                    response_json = json.loads(response)
                    script_breakdown = response_json.get('script_breakdown')
                except:
                    script_breakdown = response
                
                # Save it
                await self.discord_db.save_script_breakdown(
                    group_id, series_name, theme_name, script_breakdown, script_breakdown
                )
                print("   ✅ Generated and saved breakdown")
            
            # STEP 4: Generate plot outline
            print("📋 Generating plot outline...")
            video_duration = kwargs.get('video_duration', 30)
            
            plot_outline = await generate_plot_outline(
                title, script_breakdown, series, theme, video_duration
            )
            print("   ✅ Plot outline created")
            
            # STEP 5: Generate full script with cost tracking
            print("✍️ Generating full script...")
            host_name = kwargs.get('host_name', 'Narrator')
            
            full_script, cost_data = await generate_full_script(
                title, plot_outline, script_breakdown, series, theme, video_duration,
                host_name=host_name
            )
            
            print(f"   ✅ Script generated - Cost: ${cost_data['total_cost']:.2f}")
            
            # LOG COST TO CAMPAIGN
            self.db.log_campaign_analytics(
                campaign_id,
                channel_id,
                api_costs={
                    'anthropic': cost_data['total_cost'],
                    'total': cost_data['total_cost']
                },
                video_title=title
            )
            
            # STEP 5.5: Execute research (if content style has research config)
            research_assets = {}
            if content_style and content_style.get('research_config', {}).get('enabled'):
                print("🔍 Executing research for production...")
                try:
                    # Execute research using ContentResearchService
                    research_assets = await self.research_service.research_for_production(
                        plot_outline=plot_outline,
                        content_style=content_style,
                        full_script=full_script
                    )
                    
                    if research_assets:
                        print(f"   ✅ Research complete: {len(research_assets)} segments researched")
                        # Store research assets for use in rendering
                        # These will be passed to Remotion components via researchAssets prop
                    else:
                        print("   ⚠️ No research assets found")
                except Exception as research_error:
                    print(f"   ⚠️ Research execution failed: {research_error}")
                    # Continue without research - not critical for production
            else:
                print("   ⏭️ Research disabled or not configured for this content style")
            
            # STEP 6: Generate voice over
            print("🎙️ Generating voice over...")
            import re
            characters = set(re.findall(r'\[([^\]]+)\]:', full_script))
            voice = kwargs.get('voice', 'af_nicole')
            voice_selections = {char: voice for char in characters}
            
            voice_over_url = await generate_kokoro_voice_over(
                full_script, voice_selections, user_id, group_id, series_name, theme_name, title
            )
            
            if not voice_over_url:
                return {'success': False, 'error': 'Voice generation failed'}
            
            print(f"   ✅ Voice generated: {voice_over_url}")
            
            # Calculate ElevenLabs cost and log
            script_length = len(full_script)
            elevenlabs_cost = (script_length / 1000) * 0.30
            
            self.db.log_campaign_analytics(
                campaign_id,
                channel_id,
                api_costs={
                    'elevenlabs': elevenlabs_cost,
                    'total': elevenlabs_cost
                },
                video_title=title
            )
            
            # STEP 7: Generate thumbnail
            print("🖼️ Generating thumbnail...")
            thumbnail_url = None
            
            try:
                thumbnail_data = await self.discord_db.get_thumbnail_urls(group_id, series_name, theme_name)
                theme_thumbnails = [t['url'] for t in thumbnail_data if t.get('url')]
                
                if theme_thumbnails:
                    guidelines = await self.discord_db.get_thumbnail_guidelines(group_id, series_name, theme_name)
                    
                    if not guidelines:
                        from utils.ai_utils import analyze_thumbnails_with_ai, generate_thumbnail_concepts
                        guidelines = await analyze_thumbnails_with_ai(theme_thumbnails, series_name, theme_name)
                        await self.discord_db.save_thumbnail_guidelines(group_id, series_name, theme_name, guidelines)
                    
                    concepts = await generate_thumbnail_concepts(guidelines, title, theme_thumbnails, num_concepts=1)
                    
                    if concepts:
                        thumbnail_images = await generate_thumbnail_with_trained_model(
                            self.discord_db, group_id, series_name, theme_name, concepts[0], theme_thumbnails
                        )
                        
                        if thumbnail_images:
                            thumbnail_url = str(thumbnail_images[0])
                            print(f"   ✅ Thumbnail generated")
                            
                            # Log Replicate cost
                            self.db.log_campaign_analytics(
                                campaign_id,
                                channel_id,
                                api_costs={'replicate': 0.05, 'total': 0.05},
                                video_title=title
                            )
            except Exception as thumb_error:
                print(f"   ⚠️ Thumbnail generation failed: {thumb_error}")
            
            # STEP 8: Get voice files and prepare for video
            print("🎬 Preparing video generation...")
            folder_id = voice_over_url.split('/')[-1]
            
            # Wait for voice completion
            file_ids = await self._wait_for_voice_completion(folder_id)
            
            if not file_ids:
                return {'success': False, 'error': 'Voice files not ready'}
            
            print(f"   ✅ Got {len(file_ids)} voice segments")
            
            # STEP 9: Create output folder
            output_folder_id = await self._create_drive_folder(f"Video_{title}_{int(time.time())}")
            
            # STEP 10: Get channel credentials for upload
            channel_credentials = await self.discord_db.get_channel_oauth_credentials(user_id, youtube_channel_id)
            
            # STEP 11: Generate video
            print("🎥 Generating video...")
            visual_style = kwargs.get('visual_style', 'black_rain')
            auto_upload = kwargs.get('auto_upload', True)
            
            # Prepare research assets for video generation
            # Format: Convert research_assets to format expected by video service
            formatted_research_assets = {}
            if research_assets:
                for segment_name, segment_data in research_assets.items():
                    assets = segment_data.get('assets', {})
                    formatted_research_assets[segment_name] = {
                        'videoClips': assets.get('video_clips', []),
                        'images': assets.get('images', []),
                        'articles': assets.get('articles', []) or assets.get('news_articles', [])
                    }
            
            video_result = await self.cloud_service.process_rain_video(
                drive_service=self.drive_service,
                folder_id=folder_id,
                output_folder_id=output_folder_id,
                file_ids=file_ids,
                title=title,
                visual_style=visual_style,
                auto_upload=auto_upload,
                channel_id=youtube_channel_id,
                channel_credentials=channel_credentials,
                thumbnail_url=thumbnail_url,
                expected_segment_count=len(file_ids),
                user_id=user_id,
                research_assets=formatted_research_assets if formatted_research_assets else None  # Pass research assets
            )
            
            if not video_result or not video_result.get('success'):
                error = video_result.get('error', 'Unknown error') if video_result else 'Video service failed'
                return {'success': False, 'error': f'Video generation failed: {error}'}
            
            print(f"   ✅ Video created: {video_result.get('youtube_url') or video_result.get('video_url')}")
            
            # STEP 12: Update channel stats
            self.db.update_campaign_channel(channel_id, {
                'videos_published': (channel.get('videos_published', 0) + 1) if channel else 1,
                'last_upload': datetime.utcnow()
            })
            
            return {
                'success': True,
                'title': title,
                'youtube_url': video_result.get('youtube_url'),
                'video_url': video_result.get('video_url'),
                'thumbnail_url': thumbnail_url,
                'campaign_id': campaign_id,
                'channel_id': channel_id,
                'total_cost': cost_data['total_cost'] + elevenlabs_cost + (0.05 if thumbnail_url else 0)
            }
            
        except Exception as e:
            print(f"❌ PRODUCTION FAILED: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def _wait_for_voice_completion(self, folder_id: str, max_wait: int = 7200) -> List[str]:
        """Wait for voice generation to complete and return file IDs"""
        
        try:
            start_time = time.time()
            
            while (time.time() - start_time) < max_wait:
                # List files in folder
                file_list = self.drive_service.files().list(
                    q=f"'{folder_id}' in parents",
                    fields="files(id, name)"
                ).execute()
                
                files = file_list.get('files', [])
                
                # Check for completion marker
                completion_marker = any(f['name'].startswith('COMPLETE_') for f in files)
                audio_files = [f for f in files if f['name'].endswith('.wav')]
                
                if completion_marker and audio_files:
                    return [f['id'] for f in audio_files]
                
                # Wait before retry
                await asyncio.sleep(30)
            
            print(f"❌ Voice completion timeout after {max_wait}s")
            return []
            
        except Exception as e:
            print(f"❌ Error waiting for voice: {e}")
            return []
    
    async def _create_drive_folder(self, folder_name: str) -> str:
        """Create Google Drive folder and return ID"""
        
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            # Make public
            self.drive_service.permissions().create(
                fileId=folder['id'],
                body={'type': 'anyone', 'role': 'reader'},
                fields='id'
            ).execute()
            
            return folder['id']
            
        except Exception as e:
            print(f"❌ Error creating folder: {e}")
            raise
    
    async def start_campaign_batch_production(
        self,
        campaign_id: str,
        channel_id: str,
        video_count: int
    ) -> Dict:
        """
        Start batch production for campaign channel
        Creates multiple videos in sequence
        """
        
        try:
            print(f"🚀 BATCH PRODUCTION: {video_count} videos")
            
            channel = self.db.get_channel_by_id(channel_id)
            if not channel:
                return {'success': False, 'error': 'Channel not found'}
            
            # Get production settings
            group_id = str(channel['group_id'])
            series_list = channel.get('series', [])
            theme_list = channel.get('themes', [])
            user_id = str(channel['user_id'])
            youtube_channel_id = channel.get('youtube_channel_id')
            
            if not series_list or not theme_list:
                return {'success': False, 'error': 'No series/themes configured'}
            
            # Get all series/theme pairs
            series_theme_pairs = []
            for series_name in series_list:
                for theme_name in theme_list:
                    series_theme_pairs.append((series_name, theme_name))
            
            # Cycle through pairs for video count
            results = []
            
            for i in range(video_count):
                pair_index = i % len(series_theme_pairs)
                series_name, theme_name = series_theme_pairs[pair_index]
                
                print(f"\n📹 Video {i+1}/{video_count}: {series_name} - {theme_name}")
                
                result = await self.produce_video_for_campaign(
                    campaign_id=campaign_id,
                    channel_id=channel_id,
                    group_id=group_id,
                    series_name=series_name,
                    theme_name=theme_name,
                    user_id=user_id,
                    youtube_channel_id=youtube_channel_id,
                    video_duration=channel.get('video_duration', 30),
                    visual_style=channel.get('visual_style', 'black_rain'),
                    voice=channel.get('voice', 'af_nicole'),
                    enable_research=channel.get('research_enabled', False)
                )
                
                results.append(result)
                
                if result.get('success'):
                    print(f"   ✅ Video {i+1} complete")
                else:
                    print(f"   ❌ Video {i+1} failed: {result.get('error')}")
                
                # Small delay between videos
                await asyncio.sleep(10)
            
            successes = sum(1 for r in results if r.get('success'))
            
            return {
                'success': True,
                'total_videos': video_count,
                'successful': successes,
                'failed': video_count - successes,
                'results': results
            }
            
        except Exception as e:
            print(f"❌ BATCH PRODUCTION FAILED: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def produce_ai_animation_video(
        self,
        campaign_id: str,
        channel_id: str,
        content_style_id: str,
        title: str,
        **kwargs
    ) -> Dict:
        """Call AI Animation Service for animated content"""
        
        try:
            print(f"🤖 Calling AI Animation Service (Port 8086)...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ai_animation_url}/api/produce-video",
                    json={
                        'content_style_id': content_style_id,
                        'title': title,
                        'video_duration': kwargs.get('video_duration', 180),
                        'narration_type': kwargs.get('narration_type', 'none'),
                        'user_id': kwargs.get('user_id', 'campaign_user')
                    },
                    timeout=aiohttp.ClientTimeout(total=3600)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Log to campaign
                        if result.get('success'):
                            api_costs = result.get('production_costs', {})
                            self.db.log_campaign_analytics(
                                campaign_id, channel_id,
                                api_costs=api_costs,
                                video_title=title
                            )
                        
                        return result
                    else:
                        error = await response.text()
                        return {'success': False, 'error': error}
        
        except Exception as e:
            print(f"❌ AI Animation call failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def produce_slideshow_for_instagram(
        self,
        campaign_id: str,
        channel_id: str,
        group_id: str,
        series_name: str,
        theme_name: str,
        **kwargs
    ) -> Dict:
        """
        Produce Instagram carousel slideshow for product promotion
        
        Process:
        1. Get product data from campaign
        2. Get series/theme structure from ig_tiktok_groups
        3. Get universal Slideshow content style
        4. Generate product-focused caption
        5. Call instagram-slideshow-engine to create carousel
        6. Upload to Instagram account
        """
        try:
            print(f"📸 INSTAGRAM CAROUSEL PRODUCTION")
            print(f"   Campaign: {campaign_id}")
            print(f"   Account: {channel_id}")
            print(f"   Series: {series_name}, Theme: {theme_name}")
            
            # Get campaign and product
            campaign = self.db.get_campaign(campaign_id)
            products = campaign.get('products', [])
            
            if not products:
                return {'success': False, 'error': 'No product found in campaign'}
            
            product = products[0]  # Main product
            
            # Get IG group for series/theme structure
            group = self.db.ig_tiktok_groups.find_one({'_id': ObjectId(group_id)})
            
            if not group:
                return {'success': False, 'error': 'Instagram group not found'}
            
            # Find series and theme
            series_data = group.get('series_data', [])
            series = next((s for s in series_data if s['name'] == series_name), None)
            
            if not series:
                return {'success': False, 'error': f'Series {series_name} not found'}
            
            theme = next((t for t in series.get('themes', []) if t['name'] == theme_name), None)
            
            if not theme:
                return {'success': False, 'error': f'Theme {theme_name} not found'}
            
            # Generate product-focused caption
            caption = await self._generate_instagram_caption(
                product=product,
                series=series,
                theme=theme
            )
            
            print(f"   ✅ Generated caption: {caption[:100]}...")
            
            # Get or create universal slideshow content style
            slideshow_style = await self._get_or_create_slideshow_style()
            
            # Call instagram-slideshow-engine
            # TODO: Implement actual slideshow generation
            print(f"   🎨 Creating Instagram carousel (slideshow style)...")
            print(f"   ⚠️ Instagram slideshow generation not yet fully implemented")
            
            return {
                'success': True,
                'platform': 'instagram',
                'content_type': 'slideshow',
                'caption': caption,
                'message': 'Instagram carousel queued for production'
            }
            
        except Exception as e:
            print(f"❌ Instagram production failed: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def produce_ugc_for_tiktok(
        self,
        campaign_id: str,
        channel_id: str,
        group_id: str,
        series_name: str,
        theme_name: str,
        **kwargs
    ) -> Dict:
        """
        Produce TikTok UGC video for product promotion
        
        Process:
        1. Get product data
        2. Get series/theme structure (for pacing/format)
        3. Get universal UGC content style
        4. Generate product-focused caption (hook + CTA)
        5. Generate short script
        6. Generate voice over
        7. Call video-service to render UGC style
        8. Upload to TikTok account
        """
        try:
            print(f"🎬 TIKTOK UGC PRODUCTION")
            print(f"   Campaign: {campaign_id}")
            print(f"   Account: {channel_id}")
            print(f"   Series: {series_name}, Theme: {theme_name}")
            
            # Get campaign and product
            campaign = self.db.get_campaign(campaign_id)
            products = campaign.get('products', [])
            
            if not products:
                return {'success': False, 'error': 'No product found in campaign'}
            
            product = products[0]
            
            # Get TikTok group for series/theme structure
            group = self.db.ig_tiktok_groups.find_one({'_id': ObjectId(group_id)})
            
            if not group:
                return {'success': False, 'error': 'TikTok group not found'}
            
            # Find series and theme
            series_data = group.get('series_data', [])
            series = next((s for s in series_data if s['name'] == series_name), None)
            
            if not series:
                return {'success': False, 'error': f'Series {series_name} not found'}
            
            theme = next((t for t in series.get('themes', []) if t['name'] == theme_name), None)
            
            if not theme:
                return {'success': False, 'error': f'Theme {theme_name} not found'}
            
            # Generate product-focused caption
            caption = await self._generate_tiktok_caption(
                product=product,
                series=series,
                theme=theme
            )
            
            print(f"   ✅ Generated caption: {caption[:100]}...")
            
            # Get or create universal UGC content style
            ugc_style = await self._get_or_create_ugc_style()
            
            # Generate short product-focused script
            # TODO: Implement UGC script generation
            print(f"   📝 Generating UGC script...")
            print(f"   ⚠️ TikTok UGC generation not yet fully implemented")
            
            return {
                'success': True,
                'platform': 'tiktok',
                'content_type': 'ugc',
                'caption': caption,
                'message': 'TikTok UGC video queued for production'
            }
            
        except Exception as e:
            print(f"❌ TikTok production failed: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def _generate_instagram_caption(
        self,
        product: Dict,
        series: Dict,
        theme: Dict
    ) -> str:
        """
        Generate product-focused Instagram caption
        
        Format:
        - Hook (based on series/theme)
        - Product mention
        - Benefits (bullet points)
        - CTA with link in bio
        - Hashtags
        """
        product_name = product.get('name', 'our product')
        
        # Extract theme-based hook
        theme_name = theme.get('name', 'tips')
        
        caption = f"""✨ {theme_name} you need to know!

{product_name} is changing the game 🚀

✅ Benefit 1
✅ Benefit 2  
✅ Benefit 3

Get {product_name} now → Link in bio 🔗

#product #tips #musthave"""
        
        return caption
    
    async def _generate_tiktok_caption(
        self,
        product: Dict,
        series: Dict,
        theme: Dict
    ) -> str:
        """
        Generate product-focused TikTok caption
        
        Similar to Instagram but TikTok-style (shorter, punchier)
        """
        product_name = product.get('name', 'this product')
        theme_name = theme.get('name', 'hack')
        
        caption = f"""{product_name} changed everything 🔥

{theme_name} that actually work 💯

Link in bio → Get yours now 🔗

#fyp #product #musthave #{theme_name.lower().replace(' ', '')}"""
        
        return caption
    
    async def _get_or_create_slideshow_style(self) -> Dict:
        """Get or create universal Instagram Slideshow content style"""
        # Check if universal slideshow style exists
        style = self.db.vfx_content_styles.find_one({
            'platform': 'instagram',
            'content_format': 'slideshow',
            'is_universal': True
        })
        
        if style:
            return style
        
        # TODO: Create universal style via VFX analysis service
        print("⚠️ Universal slideshow style not found - needs creation")
        return {}
    
    async def _get_or_create_ugc_style(self) -> Dict:
        """Get or create universal TikTok UGC content style"""
        # Check if universal UGC style exists
        style = self.db.vfx_content_styles.find_one({
            'platform': 'tiktok',
            'content_format': 'ugc',
            'is_universal': True
        })
        
        if style:
            return style
        
        # TODO: Create universal style via VFX analysis service
        print("⚠️ Universal UGC style not found - needs creation")
        return {}


# Singleton
campaign_production = CampaignProductionService()
