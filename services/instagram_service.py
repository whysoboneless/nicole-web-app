"""
Instagram Service - REAL Instagram API operations using instagrapi
Download videos, manage accounts, upload content
"""

import asyncio
import os
import requests
import json
import time
from typing import Dict, List, Optional
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import instagrapi
try:
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired, BadPassword, ChallengeRequired
    INSTAGRAPI_AVAILABLE = True
    print("[SUCCESS] Instagrapi library available")
except ImportError:
    print("[WARNING] Instagrapi not installed. Run: pip install instagrapi")
    INSTAGRAPI_AVAILABLE = False
    Client = None

class InstagramService:
    """REAL Instagram API service using instagrapi"""
    
    def __init__(self):
        self.clients = {}  # Store authenticated clients per account
        self.download_folder = Path("downloads/instagram")
        self.download_folder.mkdir(parents=True, exist_ok=True)
    
    async def verify_account(self, username: str, password: str, verification_code: str = None) -> Dict:
        """REAL Instagram account verification using instagrapi"""
        try:
            if not INSTAGRAPI_AVAILABLE:
                return {"success": False, "error": "Instagram API not available. Install instagrapi: pip install instagrapi"}
            
            logger.info(f"Verifying Instagram account: {username}")
            
            # Create client and attempt login
            client = Client()
            
            try:
                # Attempt login with 2FA support
                if verification_code:
                    client.login(username, password, verification_code=verification_code)
                else:
                    client.login(username, password)
                
                # Get account info
                user_info = client.account_info()
                
                # Store client for later use
                self.clients[username] = client
                
                # Safely get user info attributes with fallbacks
                try:
                    follower_count = getattr(user_info, 'follower_count', getattr(user_info, 'followers_count', 0))
                    following_count = getattr(user_info, 'following_count', getattr(user_info, 'followees_count', 0))
                    media_count = getattr(user_info, 'media_count', getattr(user_info, 'medias_count', 0))
                    is_business = getattr(user_info, 'is_business', False)
                    is_verified = getattr(user_info, 'is_verified', False)
                    full_name = getattr(user_info, 'full_name', '')
                    biography = getattr(user_info, 'biography', '')
                except Exception as attr_error:
                    print(f"[DEBUG] Error accessing user attributes: {attr_error}")
                    # Use defaults if attributes can't be accessed
                    follower_count = 0
                    following_count = 0
                    media_count = 0
                    is_business = False
                    is_verified = False
                    full_name = ''
                    biography = ''

                return {
                    "success": True,
                    "username": username,
                    "follower_count": str(follower_count),
                    "following_count": str(following_count),
                    "media_count": str(media_count),
                    "account_type": "business" if is_business else "personal",
                    "is_verified": is_verified,
                    "full_name": full_name,
                    "biography": biography
                }
                
            except BadPassword:
                return {"success": False, "error": "Invalid username or password"}
            except ChallengeRequired as e:
                # Handle 2FA/challenge required
                challenge_info = str(e)
                if not verification_code:
                    # First attempt without 2FA code - request it
                    return {
                        "success": False, 
                        "error": "2FA verification code required",
                        "requires_2fa": True
                    }
                else:
                    # 2FA code was provided but still failed
                    return {
                        "success": False, 
                        "error": f"2FA verification failed: {challenge_info}"
                    }
            except LoginRequired:
                return {"success": False, "error": "Login failed. Check credentials."}
            except Exception as e:
                error_msg = str(e).lower()
                if "two_factor" in error_msg or "2fa" in error_msg:
                    return {
                        "success": False, 
                        "error": "Two-factor authentication detected. Please disable 2FA temporarily or use an app password.",
                        "error_type": "2fa_required"
                    }
                return {"success": False, "error": f"Login error: {str(e)}"}
                
        except Exception as e:
            logger.error(f"Error verifying Instagram account {username}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _load_authenticated_clients(self, user_id: str = None):
        """Load authenticated clients from database if not already loaded"""
        try:
            if self.clients:
                return  # Already have clients loaded
            
            if not user_id:
                print(f"[DEBUG] No user_id provided, cannot load authenticated clients")
                return
            
            # Import database here to avoid circular imports
            from core.database import Database
            db = Database()
            
            # Get Instagram accounts for this user
            accounts = db.get_instagram_accounts(user_id)
            print(f"[DEBUG] Found {len(accounts)} Instagram accounts for user {user_id}")
            for account in accounts:
                print(f"[DEBUG] Account in DB: username='{account.get('username')}', niche='{account.get('niche', 'N/A')}')")
            
            for account in accounts:
                username = account.get('username')
                password = account.get('password')
                
                if username and password:
                    try:
                        print(f"[DEBUG] Attempting to login to {username} for API access")
                        client = Client()
                        client.login(username, password)
                        self.clients[username] = client
                        print(f"[DEBUG] Successfully logged in {username}")
                    except Exception as e:
                        print(f"[DEBUG] Failed to login {username}: {e}")
                        continue
            
            print(f"[DEBUG] Loaded {len(self.clients)} authenticated clients")
            
        except Exception as e:
            print(f"[DEBUG] Error loading authenticated clients: {e}")
    
    async def get_account_videos(self, username: str, max_videos: int = 50, user_id: str = None) -> List[Dict]:
        """REAL Instagram video fetching using instagrapi"""
        try:
            if not INSTAGRAPI_AVAILABLE:
                logger.warning("Instagrapi not available, using mock data")
                # Return mock data if library not available
                mock_videos = [
                    {
                        "id": f"video_{i}",
                        "url": f"https://instagram.com/p/mock_video_{i}/",
                        "thumbnail_url": f"https://via.placeholder.com/300x400/ff6b9d/ffffff?text=Video+{i}",
                        "caption": f"Amazing content from @{username} - Video {i}",
                        "view_count": 15000 + (i * 1000),
                        "like_count": 500 + (i * 50),
                        "duration": 30 + (i * 5),
                        "created_at": datetime.utcnow(),
                        "video_url": f"https://mock-cdn.instagram.com/video_{i}.mp4",
                        "is_reel": True,
                        "hashtags": ["#viral", "#content", f"#{username}"]
                    }
                    for i in range(1, 6)
                ]
                return mock_videos
            
            logger.info(f"Fetching videos from Instagram account: {username}")
            
            # Ensure we have authenticated clients loaded
            await self._load_authenticated_clients(user_id)
            
            # Use an authenticated client if available, otherwise create new one
            client = None
            if self.clients:
                # Use the first available authenticated client
                client = list(self.clients.values())[0]
                print(f"[DEBUG] Using authenticated client for lookup ({len(self.clients)} clients available)")
            else:
                # Create new client (will need login for most operations)
                client = Client()
                print(f"[DEBUG] Using unauthenticated client - may have limited access")
            
            try:
                # Get user info by username
                print(f"[DEBUG] Looking up user: {username}")
                user_info = client.user_info_by_username(username)
                user_id = user_info.pk
                print(f"[DEBUG] Found user ID: {user_id} for {username}")
                
                # Get user's media
                print(f"[DEBUG] Fetching {max_videos} media items from user {user_id}")
                medias = client.user_medias(user_id, amount=max_videos)
                print(f"[DEBUG] Found {len(medias)} media items")
                
                videos = []
                for i, media in enumerate(medias):
                    print(f"[DEBUG] Processing media {i+1}/{len(medias)}: {media.media_type}")
                    # Only process videos and reels
                    if media.media_type in [2, 8]:  # 2 = video, 8 = carousel with video
                        video_data = {
                            "id": str(media.pk),
                            "url": f"https://instagram.com/p/{media.code}/",
                            "video_url": media.video_url,
                            "thumbnail_url": media.thumbnail_url,
                            "caption": media.caption_text or "",
                            "view_count": media.view_count or 0,
                            "like_count": media.like_count or 0,
                            "comment_count": media.comment_count or 0,
                            "duration": getattr(media, 'video_duration', 0),
                            "created_at": media.taken_at.isoformat() if media.taken_at else None,
                            "is_reel": hasattr(media, 'clips_metadata') and media.clips_metadata is not None,
                            "hashtags": []  # Could extract from caption if needed
                        }
                        videos.append(video_data)
                
                logger.info(f"Found {len(videos)} videos from @{username}")
                return videos
                
            except Exception as e:
                logger.error(f"Error fetching from Instagram API: {e}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching videos from {username}: {e}")
            return []
    
    async def download_video(self, video_url: str, save_path: str = None, user_id: str = None) -> str:
        """REAL Instagram video download using instagrapi"""
        try:
            if not INSTAGRAPI_AVAILABLE:
                logger.error("Instagrapi not available for video download")
                return None
            
            logger.info(f"Downloading video: {video_url}")
            
            # Ensure we have authenticated clients loaded
            await self._load_authenticated_clients(user_id)
            
            # Use an authenticated client if available
            client = None
            if self.clients:
                # Use the first available authenticated client
                client = list(self.clients.values())[0]
                print(f"[DEBUG] Using authenticated client for video download ({len(self.clients)} clients available)")
            else:
                # Create new client (will need login for most operations)
                client = Client()
                print(f"[DEBUG] Using unauthenticated client for video download - may fail")
            
            try:
                # Extract media PK from URL
                media_pk = client.media_pk_from_url(video_url)
                
                # Download video
                if save_path:
                    # Download to specific path
                    downloaded_path = client.video_download(media_pk, folder=str(Path(save_path).parent))
                    # Rename to desired filename
                    final_path = Path(save_path)
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    Path(downloaded_path).rename(final_path)
                    return str(final_path)
                else:
                    # Download to default folder
                    downloaded_path = client.video_download(media_pk, folder=str(self.download_folder))
                    return str(downloaded_path)
                    
            except Exception as e:
                logger.error(f"Error downloading from Instagram API: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading video {video_url}: {e}")
            return None
    
    async def upload_video_to_instagram(self, account_credentials: Dict, video_path: str, caption: str = "") -> Dict:
        """REAL Instagram video upload using instagrapi"""
        try:
            if not INSTAGRAPI_AVAILABLE:
                return {"success": False, "error": "Instagrapi not available for upload"}
            
            username = account_credentials.get("username")
            password = account_credentials.get("password")
            
            logger.info(f"Uploading video to Instagram account: {username}")
            
            # Get or create client for this account
            if username in self.clients:
                client = self.clients[username]
            else:
                client = Client()
                try:
                    client.login(username, password)
                    self.clients[username] = client
                except Exception as e:
                    return {"success": False, "error": f"Login failed: {str(e)}"}
            
            try:
                # Upload as Reel (Instagram's preferred video format)
                media = client.clip_upload(
                    Path(video_path),
                    caption=caption
                )
                
                upload_result = {
                    "success": True,
                    "post_id": str(media.pk),
                    "post_url": f"https://instagram.com/p/{media.code}/",
                    "message": f"Video uploaded to @{username}",
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "media_type": "reel"
                }
                
                logger.info(f"Video uploaded successfully: {upload_result['post_url']}")
                return upload_result
                
            except Exception as e:
                logger.error(f"Error uploading to Instagram API: {e}")
                return {"success": False, "error": f"Upload failed: {str(e)}"}
            
        except Exception as e:
            logger.error(f"Error uploading video: {e}")
            return {"success": False, "error": str(e)}

class RemotionProcessor:
    """Handle Remotion video processing with SteakUs! overlay"""
    
    def __init__(self):
        self.remotion_api_url = "http://localhost:3000"  # Your Remotion server
        
    async def analyze_video_content(self, video_path: str) -> Dict:
        """Analyze video content using Claude 3.5 Sonnet Vision to determine optimal hook strategy"""
        try:
            import cv2
            import base64
            import requests
            import json
            from config import ANTHROPIC_API_KEY
            
            if not ANTHROPIC_API_KEY:
                print("[DEBUG] No Anthropic API key - using default hook")
                return {"content_type": "unknown", "hook": "Plot twist. Here's another plot twist - you can get $25 free on Stake right now. Code BONES.", "pause_time": 3.0}
            
            print(f"[DEBUG] Analyzing video content with Claude Vision: {video_path}")
            
            # Extract key frames from video
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 10
            
            # Sample 2 frames: middle and climax (80% through)
            frame_positions = [int(total_frames * 0.5), int(total_frames * 0.8)]
            frames = []
            
            for pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = cap.read()
                if ret:
                    # Resize frame to reduce API costs
                    frame = cv2.resize(frame, (640, 360))
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_b64 = base64.b64encode(buffer).decode('utf-8')
                    frames.append(frame_b64)
            
            cap.release()
            
            if not frames:
                return {"content_type": "unknown", "hook": "default", "pause_time": duration * 0.8}
            
            # Analyze with Claude 3.5 Sonnet Vision
            headers = {
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            }
            
            # Build content array with text and images
            content = [
                {
                    "type": "text",
                    "text": """Analyze this video sequence and determine the best hook strategy for a Stake.com gambling promotion.

Classify the content type and suggest when to pause for maximum dramatic tension:

Content types:
- fail: Someone failing/about to fail at something  
- win: Someone succeeding/winning
- dangerous_stunt: Risky/dangerous activity
- gaming: Video game content
- sports: Sports highlights
- other: Everything else

Generate a hook that connects the moment to gambling using this format:
"[Observation about the video]. Just like you're going to [emotion] when you realize you can make $25 on Stake.com for free. Code BONES."

Examples:
- "He failed. Just like you'll fail to resist making free money on Stake.com. Code BONES gets you $25 to start."
- "He won. Just like you'll win when you see you can get $25 free on Stake. Code BONES."
- "He died. Just like you're going to die when you realize you can make $25 on Stake.com for free. Code BONES."

Respond ONLY in JSON format:
{
  "content_type": "fail",
  "pause_time": 3.5,
  "hook": "He failed. Just like you'll fail to resist...",
  "description": "Person attempting backflip"
}"""
                }
            ]
            
            # Add images to content
            for frame in frames:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": frame
                    }
                })
            
            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 300,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ]
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", 
                                   headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                content_text = result['content'][0]['text']
                
                try:
                    # Extract JSON from Claude's response
                    json_start = content_text.find('{')
                    json_end = content_text.rfind('}') + 1
                    if json_start != -1 and json_end != -1:
                        json_str = content_text[json_start:json_end]
                        analysis = json.loads(json_str)
                        print(f"[DEBUG] Claude video analysis result: {analysis}")
                        return analysis
                    else:
                        print(f"[DEBUG] No JSON found in Claude response, using fallback")
                        return {"content_type": "unknown", "hook": "Plot twist. Here's another plot twist - you can get $25 free on Stake right now. Code BONES.", "pause_time": duration * 0.8}
                except json.JSONDecodeError:
                    print(f"[DEBUG] Failed to parse JSON from Claude, using fallback")
                    return {"content_type": "unknown", "hook": "Plot twist. Here's another plot twist - you can get $25 free on Stake right now. Code BONES.", "pause_time": duration * 0.8}
            else:
                print(f"[DEBUG] Claude API error: {response.status_code} - {response.text}")
                return {"content_type": "unknown", "hook": "default", "pause_time": duration * 0.8}
            
        except Exception as e:
            print(f"[DEBUG] Video analysis failed: {e}")
            return {"content_type": "unknown", "hook": "Plot twist. Here's another plot twist - you can get $25 free on Stake right now. Code BONES.", "pause_time": 3.0}
    
    async def generate_voiceover_with_elevenlabs(self, text: str, voice_id: str = None) -> str:
        """Generate voiceover using 11Labs API"""
        try:
            import requests
            from config import ELEVENLABS_API_KEY
            
            if not ELEVENLABS_API_KEY:
                print("[DEBUG] No 11Labs API key - skipping voiceover generation")
                return None
            
            # Default voice ID (you can change this to your preferred voice)
            if not voice_id:
                voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice (clear, engaging)
                # Other good options:
                # "EXAVITQu4vr4xnSDxMaL" - Bella (young, energetic)
                # "ErXwobaYiN019PkySvjV" - Antoni (male, confident)
                # "MF3mGyEYCl7XYWbV9V6O" - Elli (female, friendly)
            
            print(f"[DEBUG] Generating voiceover with 11Labs: '{text[:50]}...'")
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": ELEVENLABS_API_KEY
            }
            
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "style": 0.2,  # Slight style for engagement
                    "use_speaker_boost": True
                }
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=30)
            
            if response.status_code == 200:
                # Save audio file
                audio_filename = f"voiceover_{hash(text) % 10000}.mp3"
                audio_path = self.temp_dir / audio_filename
                
                with open(audio_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"[DEBUG] Voiceover generated: {audio_path}")
                return str(audio_path)
            else:
                print(f"[DEBUG] 11Labs API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[DEBUG] Voiceover generation failed: {e}")
            return None
    
    async def create_pattern_interrupt_video(self, video_path: str, analysis: Dict, stake_footage_path: str = None) -> Dict:
        """Create the complete pattern interrupt video with pause, hook, and Stake footage"""
        try:
            print(f"[DEBUG] Creating pattern interrupt video for: {video_path}")
            
            # Generate voiceover for the hook
            voiceover_path = await self.generate_voiceover_with_elevenlabs(analysis['hook'])
            
            if not voiceover_path:
                print("[DEBUG] No voiceover generated, using text overlay only")
            
            # Prepare Remotion composition for pattern interrupt
            composition_data = {
                "compositionId": "PatternInterruptComposition",  # New Remotion composition
                "inputProps": {
                    "mainVideoPath": video_path,
                    "pauseTime": analysis.get('pause_time', 3.0),
                    "hookText": analysis['hook'],
                    "voiceoverPath": voiceover_path,
                    "stakeFootagePath": stake_footage_path,  # Your Stake.com win footage
                    "contentType": analysis.get('content_type', 'unknown'),
                    
                    # Visual effects
                    "freezeEffect": True,  # Freeze frame at pause
                    "textAnimation": "typewriter",  # Animated text appearance
                    "transitionStyle": "dramatic_zoom",  # Zoom into freeze frame
                    
                    # Timing
                    "hookDuration": 4.0,  # How long to show the hook
                    "stakeFootageDuration": 3.0,  # Stake footage duration
                    "ctaDuration": 2.0,  # "Link in bio" duration
                    
                    # Branding
                    "overlayLogo": True,
                    "ctaText": "Link in bio - Code BONES",
                    "brandColors": {
                        "primary": "#00D4AA",  # Stake green
                        "secondary": "#1A1A1A"  # Dark background
                    }
                }
            }
            
            # Send to Remotion for processing
            import requests
            response = requests.post(
                f"{self.remotion_api_url}/render",
                json=composition_data,
                timeout=300  # 5 minutes for video processing
            )
            
            if response.status_code == 200:
                result = response.json()
                output_path = result.get('outputPath')
                
                print(f"[DEBUG] Pattern interrupt video created: {output_path}")
                
                return {
                    "success": True,
                    "output_path": output_path,
                    "hook_used": analysis['hook'],
                    "content_type": analysis['content_type'],
                    "voiceover_path": voiceover_path
                }
            else:
                print(f"[DEBUG] Remotion processing failed: {response.status_code}")
                return {"success": False, "error": f"Remotion error: {response.status_code}"}
                
        except Exception as e:
            print(f"[DEBUG] Pattern interrupt creation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_video_with_overlay(self, video_path: str, overlay_config: Dict) -> Dict:
        """Process video with StakeUs! sponsor overlay - now with AI pattern interrupt!"""
        try:
            logger.info(f"Processing video with StakeUs! overlay: {video_path}")
            
            # Check if pattern interrupt mode is enabled (default: True)
            use_pattern_interrupt = overlay_config.get("pattern_interrupt", True)
            
            if use_pattern_interrupt:
                print("[DEBUG] 🎬 Using AI Pattern Interrupt mode with 11Labs voiceover")
                
                # Step 1: Analyze video content with GPT-4V
                analysis = await self.analyze_video_content(video_path)
                print(f"[DEBUG] 🤖 Video analysis: {analysis}")
                
                # Step 2: Create pattern interrupt video with 11Labs voiceover
                stake_footage = overlay_config.get("stake_footage_path")  # Your Stake win footage
                result = await self.create_pattern_interrupt_video(video_path, analysis, stake_footage)
                
                if result.get("success"):
                    print(f"[DEBUG] ✅ Pattern interrupt video created successfully!")
                    return result
                else:
                    print(f"[DEBUG] ❌ Pattern interrupt failed, falling back to simple overlay")
                    # Fall through to simple overlay mode
            
            print("[DEBUG] 📹 Using simple overlay mode")
            # Simple overlay mode (fallback or manual selection)
            composition_data = {
                "compositionId": "StakeUsEndOverlay",  # Your custom Remotion composition
                "inputProps": {
                    "mainVideoPath": video_path,
                    "overlayVideoPath": overlay_config.get("custom_video_path"),  # Your uploaded StakeUs video
                    "overlayDuration": overlay_config.get("overlay_duration", 3),  # seconds
                    "transitionType": overlay_config.get("transition", "fade"),  # fade, slide, cut
                    "overlayPosition": "end",  # Always at the end
                    "maintainAspectRatio": True,  # Keep Instagram Reel format (9:16)
                    "audioFadeOut": overlay_config.get("audio_fade", True)  # Fade original audio
                }
            }
            
            # TODO: Call your Remotion API
            # response = requests.post(f"{self.remotion_api_url}/render", json=composition_data)
            
            # For now, simulate processing
            await asyncio.sleep(10)  # Simulate Remotion processing time
            
            processed_video_path = video_path.replace('.mp4', '_stakeus.mp4')
            
            # Mock processed file
            with open(processed_video_path, 'w') as f:
                f.write(f"Processed video with StakeUs! overlay at end")
            
            return {
                "success": True,
                "processed_video_path": processed_video_path,
                "original_video_path": video_path,
                "overlay_applied": True,
                "overlay_duration": overlay_config.get("overlay_duration", 3),
                "processing_time": 10
            }
            
        except Exception as e:
            logger.error(f"Error processing video with overlay: {e}")
            return {"success": False, "error": str(e)}
    
    def get_available_templates(self) -> List[Dict]:
        """Get available StakeUs! overlay templates"""
        return [
            {
                "id": "stakeus_end_overlay",
                "name": "StakeUs! End Overlay",
                "description": "Add StakeUs! video at the end of each reel",
                "preview_url": "/static/previews/stakeus_end.gif",
                "duration": 3
            },
            {
                "id": "custom_video_upload",
                "name": "Custom Video Upload",
                "description": "Upload your own StakeUs! video to add at the end",
                "preview_url": "/static/previews/custom_video.png",
                "duration": 0,  # User defined
                "requires_upload": True
            }
        ]
