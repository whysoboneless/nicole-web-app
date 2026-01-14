"""
VFX Service for Sora 2 Integration
Handles video analysis, VFX guidelines creation, and scene generation
"""

import json
import cv2
import base64
import requests
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

class VFXService:
    def __init__(self):
        self.sora_api_key = os.getenv('SORA_API_KEY', 'dk-6dfd18d8b8e4a1867f8ca28a7e035817')  # DeFi API for Sora 2
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        
    async def analyze_series_vfx_patterns(self, series_name: str, theme_name: str, video_urls: List[str]) -> Dict:
        """
        Analyze existing series videos to extract visual patterns
        Similar to thumbnail analysis but for video frames
        """
        try:
            print(f"[DEBUG] Analyzing VFX patterns for {series_name} - {theme_name}")
            
            if not video_urls:
                print("[DEBUG] No video URLs provided, using default VFX patterns")
                return self._get_default_vfx_guidelines(series_name, theme_name)
            
            # Extract key frames from videos
            frames = await self._extract_video_frames(video_urls[:3])  # Limit to 3 videos for cost
            
            if not frames:
                print("[DEBUG] No frames extracted, using default VFX patterns")
                return self._get_default_vfx_guidelines(series_name, theme_name)
            
            # Analyze frames with Claude Vision
            vfx_patterns = await self._analyze_frames_with_claude(frames, series_name, theme_name)
            
            return vfx_patterns
            
        except Exception as e:
            print(f"[DEBUG] VFX analysis failed: {e}")
            return self._get_default_vfx_guidelines(series_name, theme_name)
    
    async def _extract_video_frames(self, video_urls: List[str]) -> List[str]:
        """Extract key frames from videos for analysis"""
        frames = []
        
        for video_url in video_urls[:2]:  # Limit to 2 videos
            try:
                # Download video temporarily
                temp_video = await self._download_video_temp(video_url)
                if not temp_video:
                    continue
                
                # Extract frames using OpenCV
                cap = cv2.VideoCapture(temp_video)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                
                if total_frames == 0 or fps == 0:
                    cap.release()
                    continue
                
                # Extract frames at 10%, 30%, 50%, 70%, 90% of video
                frame_positions = [int(total_frames * p) for p in [0.1, 0.3, 0.5, 0.7, 0.9]]
                
                for pos in frame_positions:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                    ret, frame = cap.read()
                    if ret:
                        # Resize and encode frame
                        frame = cv2.resize(frame, (640, 360))
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        frame_b64 = base64.b64encode(buffer).decode('utf-8')
                        frames.append(frame_b64)
                
                cap.release()
                os.unlink(temp_video)  # Clean up temp file
                
            except Exception as e:
                print(f"[DEBUG] Error extracting frames from {video_url}: {e}")
                continue
        
        print(f"[DEBUG] Extracted {len(frames)} frames for analysis")
        return frames
    
    async def _download_video_temp(self, video_url: str) -> Optional[str]:
        """Download video to temporary file"""
        try:
            response = requests.get(video_url, stream=True, timeout=30)
            if response.status_code == 200:
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_file.close()
                return temp_file.name
        except Exception as e:
            print(f"[DEBUG] Error downloading video: {e}")
        return None
    
    async def _analyze_frames_with_claude(self, frames: List[str], series_name: str, theme_name: str) -> Dict:
        """Analyze video frames with Claude Vision to extract VFX patterns"""
        try:
            if not self.anthropic_api_key:
                print("[DEBUG] No Anthropic API key - using default patterns")
                return self._get_default_vfx_guidelines(series_name, theme_name)
            
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            # Build content with frames (limit to 5 frames for cost)
            content = [
                {
                    "type": "text",
                    "text": f"""Analyze these video frames from the series "{series_name}" theme "{theme_name}" to extract VFX patterns for Sora 2 generation.

Create comprehensive VFX guidelines that identify:

1. VISUAL STYLE ANALYSIS:
   - Camera angles and movements (static, pan, zoom, tracking)
   - Lighting patterns (natural, dramatic, soft, harsh)
   - Color palettes and grading
   - Composition rules and framing
   - Environment types and settings

2. SCENE STRUCTURE PATTERNS:
   - How scenes typically start (establishing shots, close-ups)
   - Transition styles between segments
   - Pacing and rhythm patterns
   - Visual hierarchy and focus points

3. TECHNICAL SPECIFICATIONS:
   - Shot types (wide, medium, close-up, extreme close-up)
   - Camera stability (handheld, tripod, gimbal)
   - Depth of field preferences
   - Motion blur and shutter effects

4. CONTENT-SPECIFIC ELEMENTS:
   - How different content types are visualized
   - Character/subject positioning patterns
   - Background complexity levels
   - Text overlay zones and safe areas

Respond in JSON format with this structure:
{{
  "VFX_GUIDELINES": {{
    "SERIES_VISUAL_IDENTITY": {{
      "dominant_camera_angles": ["angle1", "angle2"],
      "lighting_patterns": ["pattern1", "pattern2"],
      "environment_types": ["type1", "type2"],
      "color_palettes": ["#hex1", "#hex2"],
      "movement_styles": ["style1", "style2"]
    }},
    "SEGMENT_MAPPING": {{
      "introduction": {{
        "visual_type": "shot_type",
        "sora_prompt_template": "template with {{variables}}",
        "duration_range": [min, max],
        "camera_movement": "movement_type"
      }},
      "explanation": {{
        "visual_type": "shot_type",
        "sora_prompt_template": "template with {{variables}}",
        "duration_range": [min, max],
        "camera_movement": "movement_type"
      }},
      "conclusion": {{
        "visual_type": "shot_type",
        "sora_prompt_template": "template with {{variables}}",
        "duration_range": [min, max],
        "camera_movement": "movement_type"
      }}
    }},
    "TRAINING_GUIDANCE": {{
      "critical_elements": {{
        "must_maintain": ["element1", "element2"],
        "can_vary": ["element1", "element2"],
        "style_anchors": ["anchor1", "anchor2"]
      }},
      "prompt_generation": {{
        "base_template": "base template with {{variables}}",
        "style_modifiers": ["modifier1", "modifier2"],
        "technical_specs": ["spec1", "spec2"]
      }}
    }}
  }}
}}"""
                }
            ]
            
            # Add frames (limit to 5)
            for frame in frames[:5]:
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
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ]
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", 
                                   headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                content_text = result['content'][0]['text']
                
                # Extract JSON from Claude's response
                json_start = content_text.find('{')
                json_end = content_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = content_text[json_start:json_end]
                    vfx_guidelines = json.loads(json_str)
                    print(f"[DEBUG] Successfully analyzed VFX patterns with Claude")
                    return vfx_guidelines
                else:
                    print(f"[DEBUG] No JSON found in Claude response")
                    return self._get_default_vfx_guidelines(series_name, theme_name)
            else:
                print(f"[DEBUG] Claude API error: {response.status_code}")
                return self._get_default_vfx_guidelines(series_name, theme_name)
                
        except Exception as e:
            print(f"[DEBUG] Claude analysis failed: {e}")
            return self._get_default_vfx_guidelines(series_name, theme_name)
    
    def _get_default_vfx_guidelines(self, series_name: str, theme_name: str) -> Dict:
        """Default VFX guidelines when analysis fails"""
        return {
            "VFX_GUIDELINES": {
                "SERIES_VISUAL_IDENTITY": {
                    "dominant_camera_angles": ["medium_shot", "close_up", "establishing_shot"],
                    "lighting_patterns": ["natural_daylight", "soft_interior", "cinematic_dramatic"],
                    "environment_types": ["modern_interior", "outdoor_natural", "urban_setting"],
                    "color_palettes": ["#2c3e50", "#3498db", "#ecf0f1", "#e74c3c"],
                    "movement_styles": ["slow_pan", "static_hold", "gentle_zoom", "smooth_tracking"]
                },
                "SEGMENT_MAPPING": {
                    "introduction": {
                        "visual_type": "establishing_shot",
                        "sora_prompt_template": "Cinematic establishing shot of {environment}, {lighting}, professional video production quality, smooth camera movement",
                        "duration_range": [3, 5],
                        "camera_movement": "slow_pan"
                    },
                    "explanation": {
                        "visual_type": "medium_shot",
                        "sora_prompt_template": "Medium shot focusing on {subject}, {lighting}, professional framing, stable camera",
                        "duration_range": [5, 8],
                        "camera_movement": "static_hold"
                    },
                    "conclusion": {
                        "visual_type": "close_up",
                        "sora_prompt_template": "Close-up shot with {emotional_tone}, {lighting}, impactful framing, subtle zoom",
                        "duration_range": [3, 4],
                        "camera_movement": "gentle_zoom"
                    }
                },
                "TRAINING_GUIDANCE": {
                    "critical_elements": {
                        "must_maintain": ["consistent_lighting", "professional_quality", "stable_camera", "cinematic_framing"],
                        "can_vary": ["environment_details", "subject_positioning", "background_elements", "color_temperature"],
                        "style_anchors": ["film_quality", "smooth_movement", "natural_lighting"]
                    },
                    "prompt_generation": {
                        "base_template": "Cinematic {shot_type} of {subject} in {environment}, {lighting_style}, professional video production quality, {camera_movement}",
                        "style_modifiers": ["film_grain", "color_graded", "shallow_depth_of_field", "cinematic_aspect_ratio"],
                        "technical_specs": ["4K_resolution", "24fps", "stable_camera_movement", "professional_lighting"]
                    }
                }
            }
        }
    
    async def create_vfx_breakdown(self, script_breakdown: Dict, vfx_guidelines: Dict) -> List[Dict]:
        """
        Create VFX breakdown from script breakdown using VFX guidelines
        Maps each script segment to Sora 2 prompts
        """
        try:
            print(f"[DEBUG] Creating VFX breakdown from {len(script_breakdown.get('segments', []))} script segments")
            
            vfx_breakdown = []
            guidelines = vfx_guidelines.get('VFX_GUIDELINES', {})
            segment_mapping = guidelines.get('SEGMENT_MAPPING', {})
            
            for i, segment in enumerate(script_breakdown.get('segments', [])):
                # Classify segment type
                segment_type = self._classify_segment_type(segment.get('content', ''), i, len(script_breakdown.get('segments', [])))
                
                # Get VFX pattern for this segment type
                vfx_pattern = segment_mapping.get(segment_type, segment_mapping.get('explanation', {}))
                
                # Generate Sora prompt
                sora_prompt = self._generate_sora_prompt(segment, vfx_pattern, guidelines)
                
                vfx_scene = {
                    'segment_id': segment.get('id', i),
                    'segment_title': segment.get('title', f'Scene {i+1}'),
                    'content': segment.get('content', ''),
                    'segment_type': segment_type,
                    'visual_type': vfx_pattern.get('visual_type', 'medium_shot'),
                    'sora_prompt': sora_prompt,
                    'duration': segment.get('duration', vfx_pattern.get('duration_range', [5, 8])[0]),
                    'camera_movement': vfx_pattern.get('camera_movement', 'static_hold'),
                    'technical_notes': {
                        'shot_type': vfx_pattern.get('visual_type', 'medium_shot'),
                        'lighting': 'natural_daylight',
                        'environment': 'modern_interior'
                    }
                }
                
                vfx_breakdown.append(vfx_scene)
            
            print(f"[DEBUG] Created VFX breakdown with {len(vfx_breakdown)} scenes")
            return vfx_breakdown
            
        except Exception as e:
            print(f"[DEBUG] VFX breakdown creation failed: {e}")
            return []
    
    def _classify_segment_type(self, content: str, index: int, total_segments: int) -> str:
        """Classify script segment type for VFX mapping"""
        content_lower = content.lower()
        
        # First segment is usually introduction
        if index == 0:
            return 'introduction'
        
        # Last segment is usually conclusion
        if index == total_segments - 1:
            return 'conclusion'
        
        # Check content for specific patterns
        if any(word in content_lower for word in ['introduce', 'welcome', 'today we', 'in this']):
            return 'introduction'
        elif any(word in content_lower for word in ['conclude', 'summary', 'in conclusion', 'finally']):
            return 'conclusion'
        else:
            return 'explanation'
    
    def _generate_sora_prompt(self, segment: Dict, vfx_pattern: Dict, guidelines: Dict) -> str:
        """Generate Sora 2 prompt from segment and VFX pattern"""
        try:
            # Get prompt template
            template = vfx_pattern.get('sora_prompt_template', 
                                    'Cinematic {shot_type} of {subject}, professional video production quality')
            
            # Extract variables from content
            content = segment.get('content', '')
            
            # Basic variable substitution
            variables = {
                'shot_type': vfx_pattern.get('visual_type', 'medium_shot').replace('_', ' '),
                'subject': self._extract_subject_from_content(content),
                'environment': self._select_environment(guidelines),
                'lighting': self._select_lighting(guidelines),
                'lighting_style': self._select_lighting(guidelines),
                'camera_movement': vfx_pattern.get('camera_movement', 'static_hold').replace('_', ' '),
                'emotional_tone': self._extract_emotional_tone(content)
            }
            
            # Replace variables in template
            prompt = template
            for key, value in variables.items():
                prompt = prompt.replace(f'{{{key}}}', value)
            
            # Add technical specifications
            tech_specs = guidelines.get('TRAINING_GUIDANCE', {}).get('technical_specs', [])
            if tech_specs:
                prompt += f", {', '.join(tech_specs[:2])}"
            
            return prompt
            
        except Exception as e:
            print(f"[DEBUG] Prompt generation failed: {e}")
            return f"Cinematic medium shot, professional video production quality, {segment.get('content', '')[:50]}..."
    
    def _extract_subject_from_content(self, content: str) -> str:
        """Extract main subject from content"""
        # Simple extraction - could be enhanced with NLP
        words = content.split()[:10]  # First 10 words
        
        # Look for common subjects
        subjects = ['person', 'character', 'narrator', 'host', 'speaker']
        for word in words:
            if any(subj in word.lower() for subj in subjects):
                return word
        
        return 'professional presenter'
    
    def _select_environment(self, guidelines: Dict) -> str:
        """Select appropriate environment from guidelines"""
        environments = guidelines.get('SERIES_VISUAL_IDENTITY', {}).get('environment_types', ['modern_interior'])
        return environments[0].replace('_', ' ')
    
    def _select_lighting(self, guidelines: Dict) -> str:
        """Select appropriate lighting from guidelines"""
        lighting = guidelines.get('SERIES_VISUAL_IDENTITY', {}).get('lighting_patterns', ['natural_daylight'])
        return lighting[0].replace('_', ' ')
    
    def _extract_emotional_tone(self, content: str) -> str:
        """Extract emotional tone from content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['exciting', 'amazing', 'incredible']):
            return 'excited and energetic'
        elif any(word in content_lower for word in ['serious', 'important', 'critical']):
            return 'serious and focused'
        elif any(word in content_lower for word in ['calm', 'peaceful', 'gentle']):
            return 'calm and serene'
        else:
            return 'professional and confident'
    
    async def generate_sora_video(self, sora_prompt: str, duration: int = 10, reference_image: str = None) -> Optional[str]:
        """
        Generate video using Sora 2 via DeFi API
        Returns URL to generated video
        
        Note: Each video is 10 seconds long and costs $0.10 per request
        """
        try:
            # Check for Sora API key
            sora_api_key = os.getenv('SORA_API_KEY', 'dk-6dfd18d8b8e4a1867f8ca28a7e035817')
            if not sora_api_key:
                print("[DEBUG] No Sora API key - returning placeholder")
                return None
            
            print(f"[DEBUG] Generating Sora video via DeFi API: {sora_prompt[:100]}...")
            
            # Import requests for API call
            import requests
            import json
            
            # DeFi API endpoint
            api_url = "https://defapi.org/model/openai/sora-2"
            
            # Prepare request payload
            payload = {
                "prompt": sora_prompt,
                "duration": 10,  # Fixed at 10 seconds per the API spec
                "resolution": "1920x1080",
                "fps": 24
            }
            
            # Add reference image if provided
            if reference_image:
                payload["image"] = reference_image
                print(f"[DEBUG] Using reference image for Sora generation")
            
            # Headers with API key
            headers = {
                "Authorization": f"Bearer {sora_api_key}",
                "Content-Type": "application/json"
            }
            
            # Make API request
            response = requests.post(api_url, json=payload, headers=headers, timeout=300)
            
            if response.status_code == 200:
                result = response.json()
                
                # Extract video URL from response
                video_url = result.get('video_url') or result.get('output') or result.get('url')
                
                if video_url:
                    print(f"[DEBUG] Sora video generated successfully: {video_url}")
                    return video_url
                else:
                    print(f"[DEBUG] No video URL in response: {result}")
                    return None
            else:
                print(f"[DEBUG] Sora API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[DEBUG] Sora generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ===== SORA PROMPTING GUIDELINES =====
    
    SORA_PROMPT_STRUCTURE = {
        "camera_setup": "Specify camera type, position, and movement (e.g., 'Front-facing action-cam locked on face')",
        "dialogue_script": "Exact words with lipsync specification (e.g., 'He speaks with clear lipsync: \"exact words here\"')",
        "audio_design": "Sound environment and voice processing (e.g., 'Natural wind roar, voice close-mic'd and compressed')",
        "visual_details": "Specific props, clothing, environment elements (e.g., 'goggles flutter, altimeter visible')",
        "camera_movement": "Movement style and stability (e.g., 'Energetic but stable framing with subtle shake')",
        "lighting": "Light source, time of day, mood (e.g., 'Midday sun, golden hour, dramatic shadows')",
        "ending_action": "How the scene concludes (e.g., 'End on first tug of canopy and wind noise dropping')"
    }
    
    CONTENT_STYLE_TEMPLATES = {
        "educational_documentary": {
            "camera_setup": "Static or slow push-in on instructor, professional framing",
            "dialogue_pattern": "Clear, authoritative delivery with pauses for emphasis",
            "audio_style": "Clean studio sound, professional microphone, minimal background",
            "visual_elements": "Clean background, props/charts relevant to topic, good lighting",
            "pacing": "Measured, allowing information to sink in"
        },
        "news_documentary": {
            "camera_setup": "Professional news setup, slight camera movement for dynamism",
            "dialogue_pattern": "Authoritative, urgent when needed, clear pronunciation",
            "audio_style": "Broadcast quality, news room ambiance, clear voice separation",
            "visual_elements": "Graphics, data displays, professional studio or field setting",
            "pacing": "Steady, informative, building importance"
        },
        "cinematic_narrative": {
            "camera_setup": "Cinematic angles, dramatic movements, film-like composition",
            "dialogue_pattern": "Emotional delivery, natural pauses, character-driven",
            "audio_style": "Atmospheric sound, music integration, spatial audio",
            "visual_elements": "Dramatic lighting, props that tell story, environmental mood",
            "pacing": "Variable, building tension and release"
        },
        "conversational_review": {
            "camera_setup": "Intimate framing, slight handheld feel, personal space",
            "dialogue_pattern": "Casual, direct to camera, natural speech patterns",
            "audio_style": "Room tone, natural reverb, conversational mic distance",
            "visual_elements": "Personal space, relevant products/items, cozy lighting",
            "pacing": "Natural conversation rhythm, thoughtful pauses"
        },
        "entertainment_casual": {
            "camera_setup": "Dynamic angles, energetic movement, engaging framing",
            "dialogue_pattern": "High energy, expressive, audience engagement",
            "audio_style": "Vibrant sound, music integration, energetic processing",
            "visual_elements": "Colorful environment, props for energy, dynamic lighting",
            "pacing": "Fast, energetic, maintaining excitement"
        },
        "professional_informational": {
            "camera_setup": "Professional framing, steady camera work, authoritative positioning",
            "dialogue_pattern": "Clear, professional delivery, confident tone",
            "audio_style": "Clean audio, professional microphone, minimal background noise",
            "visual_elements": "Professional setting, relevant props, good lighting",
            "pacing": "Steady, informative, building credibility"
        }
    }
    
    # ===== SORA-SPECIFIC METHODS =====
    
    async def generate_sora_storyboard(self, title: str, series_name: str, theme_name: str, 
                                     format_type: str, duration: int, scene_count: int, 
                                     script_breakdown: Dict = None, group_id: str = None,
                                     db = None) -> List[Dict]:
        """
        Generate Sora storyboard using script breakdown as foundation (much more efficient!)
        Auto-generates script breakdown if one doesn't exist.
        """
        try:
            print(f"[DEBUG] Generating Sora storyboard: {title} ({format_type}, {duration}s, {scene_count} scenes)")
            
            # If no script breakdown provided, try to get existing or generate new one
            # EXACT same logic as content_studio_routes.py
            if not script_breakdown and db and group_id:
                print("[DEBUG] Checking for existing script breakdown...")
                
                try:
                    # STEP 1: Check for existing breakdown (EXACT same as content_studio_routes.py)
                    existing_breakdown = db.get_script_breakdown_sync(group_id, series_name, theme_name)
                    
                    print(f"[DEBUG] Existing breakdown result: {type(existing_breakdown)} - {existing_breakdown is not None}")
                    if existing_breakdown:
                        print(f"[DEBUG] Existing breakdown keys: {existing_breakdown.keys() if isinstance(existing_breakdown, dict) else 'not a dict'}")
                    
                    if existing_breakdown and existing_breakdown.get('script_breakdown'):
                        script_breakdown = existing_breakdown.get('script_breakdown')
                        print(f"[DEBUG] ✅ Found existing script breakdown in database! Type: {type(script_breakdown)}")
                    elif existing_breakdown and existing_breakdown.get('guidelines'):
                        script_breakdown = existing_breakdown.get('guidelines')
                        print(f"[DEBUG] ✅ Found existing guidelines in database, using as breakdown! Type: {type(script_breakdown)}")
                    else:
                        print("[DEBUG] No existing script breakdown - generating new one...")
                        
                        # STEP 2: Generate new breakdown if none exists (EXACT same as content_studio_routes.py)
                        from utils_dir.ai_utils import breakdown_script
                        from core.youtube_service import YouTubeService
                        
                        # Use sync YouTube service for web app compatibility
                        yt_service = YouTubeService()
                        
                        video_ids = db.get_top_video_urls_sync(group_id, series_name, theme_name, limit=3)
                        print(f"[DEBUG] Found {len(video_ids)} videos for script breakdown generation")
                        
                        if video_ids:
                            # EXACT same transcript collection logic as content_studio_routes.py
                            transcripts = []
                            video_durations = []
                            video_titles = []
                            video_descriptions = []
                            required_count = 3
                            collected = 0
                            checked = set()
                            queue = list(video_ids)
                            
                            while queue and collected < required_count:
                                video_id = queue.pop(0)
                                if not video_id or video_id in checked:
                                    continue
                                checked.add(video_id)
                                
                                transcript = yt_service.get_video_transcript_sync(video_id)
                                if transcript:
                                    transcripts.append(transcript)
                                    video_duration = yt_service.get_video_duration_sync(video_id)
                                    video_durations.append(video_duration)
                                    video_info = yt_service.get_video_info_sync(video_id)
                                    video_titles.append(video_info.get('title', ''))
                                    video_descriptions.append(video_info.get('description', ''))
                                    collected += 1
                                else:
                                    # Try to get more videos
                                    try:
                                        more = db.get_top_video_urls_sync(group_id, series_name, theme_name, limit=20)
                                        for vid in more:
                                            if vid not in checked:
                                                queue.append(vid)
                                    except Exception:
                                        pass
                            
                            if transcripts:
                                print(f"[DEBUG] Retrieved {len(transcripts)} transcripts - generating script breakdown with AI")
                                response = await breakdown_script(
                                    series_name, theme_name, 
                                    transcripts, video_durations, video_titles, video_descriptions
                                )
                                
                                # Parse response (EXACT same as content_studio_routes.py)
                                try:
                                    import json
                                    response_json = json.loads(response)
                                    script_breakdown = response_json.get('script_breakdown')
                                    print(f"[DEBUG] ✅ Successfully generated script breakdown automatically!")
                                    
                                    # STEP 3: Save to database (EXACT same as content_studio_routes.py)
                                    safe_series_name = series_name.replace(" ", "_")
                                    safe_theme_name = theme_name.replace(" ", "_")
                                    db.save_script_breakdown_sync(
                                        group_id, safe_series_name, safe_theme_name, 
                                        script_breakdown, script_breakdown
                                    )
                                    print(f"[DEBUG] Saved new script breakdown to database")
                                except Exception as parse_error:
                                    print(f"[DEBUG] Failed to parse script breakdown response: {parse_error}")
                                    script_breakdown = None
                            else:
                                print("[DEBUG] No transcripts retrieved - cannot generate script breakdown")
                        else:
                            print("[DEBUG] No videos found for script breakdown generation")
                        
                except Exception as gen_error:
                    print(f"[DEBUG] Error with script breakdown: {gen_error}")
                    import traceback
                    traceback.print_exc()
            
            if script_breakdown:
                # Parse script breakdown if it's a JSON string (EXACT same as content_studio_routes.py)
                if isinstance(script_breakdown, str):
                    try:
                        import json
                        # Show first 100 chars for debugging
                        print(f"[DEBUG] Attempting to parse JSON (first 100 chars): {script_breakdown[:100]}")
                        script_breakdown = json.loads(script_breakdown)
                        print("[DEBUG] ✅ Parsed script breakdown from JSON string successfully")
                    except Exception as parse_error:
                        print(f"[DEBUG] ❌ Failed to parse script breakdown JSON: {parse_error}")
                        print(f"[DEBUG] Malformed JSON at char {parse_error.pos if hasattr(parse_error, 'pos') else 'unknown'}")
                        # Treat it as plain text and wrap in basic structure
                        script_breakdown = {"segments": [{"content": script_breakdown, "title": "Content Overview"}]}
                        print("[DEBUG] Wrapped as plain text in basic structure")
                
                # Use script breakdown to understand content structure and style
                print("[DEBUG] Using script breakdown for storyboard generation")
                storyboard_scenes = await self._generate_storyboard_from_script(
                    title, series_name, theme_name, format_type, duration, scene_count, script_breakdown
                )
            else:
                # Fallback to basic storyboard if no script breakdown available
                print("[DEBUG] No script breakdown available, using basic AI storyboard generation")
                storyboard_scenes = await self._generate_basic_storyboard(
                    title, series_name, theme_name, format_type, duration, scene_count
                )
            
            return storyboard_scenes
            
        except Exception as e:
            print(f"[DEBUG] Sora storyboard generation failed: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_storyboard(title, format_type, duration, scene_count)
    
    async def _generate_storyboard_from_script(self, title: str, series_name: str, theme_name: str,
                                             format_type: str, duration: int, scene_count: int, 
                                             script_breakdown: Dict) -> List[Dict]:
        """Generate Sora storyboard using PRODUCTION workflow
        
        Flow: Script Breakdown → Plot Outline (adapted to duration) → Segment Extraction → Sora Prompts
        
        Each plot segment duration is converted to multiple 10-second Sora clips:
        - "Introduction: 01:30" = 9 x 10-second clips
        - "Main Content: 03:00" = 18 x 10-second clips
        - etc.
        """
        try:
            if not self.anthropic_api_key:
                print("[DEBUG] No Anthropic API key - using fallback storyboard")
                return self._get_fallback_storyboard(title, format_type, duration, scene_count)
            
            # ================================
            # STEP 1: Generate Plot Outline (EXACT same as production)
            # ================================
            duration_minutes = duration / 60.0
            print(f"[DEBUG] Step 1: Generating plot outline for {duration}s ({duration_minutes:.2f} min) using production code...")
            
            from utils_dir.ai_utils import generate_plot_outline
            
            # Create series/theme objects (same format as production)
            series = {'name': series_name}
            theme = {'name': theme_name}
            
            # Generate plot outline with Sora-specific context
            # Add special note in the script breakdown to inform it's for Sora
            sora_context = f"""
            
🎬 SORA GENERATION CONTEXT (CRITICAL):
- This plot outline is for OpenAI Sora 2 video generation
- Each scene will be generated as a separate 10-second AI video
- Scenes will be stitched together to create the final {duration}s video
- Keep segments SHORT and CLEAR for AI video generation
- Each segment should be self-contained and visually descriptive
- Total video duration: {duration}s = {(duration + 9) // 10} x 10-second Sora clips
"""
            
            # Add context to script breakdown
            if isinstance(script_breakdown, str):
                script_breakdown_with_context = script_breakdown + sora_context
            elif isinstance(script_breakdown, dict):
                script_breakdown_with_context = script_breakdown.get('script_breakdown', str(script_breakdown)) + sora_context
            else:
                script_breakdown_with_context = str(script_breakdown) + sora_context
            
            # Call the SAME plot outline generator as production
            # Set system key for Sora generation
            import os
            os.environ['ANTHROPIC_API_KEY'] = self.anthropic_api_key
            
            plot_outline = await generate_plot_outline(
                title=title,
                guidelines=script_breakdown_with_context,
                series=series,
                theme=theme,
                video_length=duration_minutes,
                enable_research=False  # No research for Sora
            )
            
            print(f"[DEBUG] Generated plot outline, extracting segments...")
            
            # ================================
            # STEP 2: Extract Segments with Durations (ai_utils.py)
            # ================================
            from utils_dir.ai_utils import extract_segments
            
            try:
                segments = await extract_segments(plot_outline)
                print(f"[DEBUG] ✅ Extracted {len(segments)} segments from plot outline")
                
                # Show segment details
                for i, seg in enumerate(segments[:5]):
                    print(f"[DEBUG]   Segment {i+1}: '{seg['name']}' - Duration: {seg.get('duration', 'unknown')}")
                    
            except Exception as e:
                print(f"[DEBUG] ❌ Could not extract segments from plot outline: {e}")
                # Fallback: Create basic segments
                num_10s_segments = (duration + 9) // 10
                segments = []
                for i in range(num_10s_segments):
                    segments.append({
                        "name": f"Scene {i+1}",
                        "duration": "00:10",
                        "timestamp": f"00:{i*10:02d} - 00:{(i+1)*10:02d}"
                    })
                print(f"[DEBUG] Created {len(segments)} fallback segments")
            
            # ================================
            # STEP 3: Convert Segments to 10-Second Sora Clips
            # ================================
            # Each segment duration → multiple 10s clips
            # Example: "Introduction: 01:30" = 9 clips, "Incident: 03:00" = 18 clips
            
            def parse_duration_to_seconds(duration_str):
                """Convert duration like '03:00' or '180 seconds' to seconds"""
                try:
                    if 'second' in duration_str.lower():
                        return int(duration_str.split()[0])
                    parts = duration_str.split(':')
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except:
                    return 10  # Default to 10 seconds
                return 10
            
            # Build clip mapping
            sora_clips = []
            total_clips_needed = (duration + 9) // 10
            clip_counter = 0
            
            for seg in segments:
                seg_duration_seconds = parse_duration_to_seconds(seg.get('duration', '00:10'))
                clips_for_segment = max(1, (seg_duration_seconds + 9) // 10)  # Round up
                
                print(f"[DEBUG] Segment '{seg['name']}' ({seg_duration_seconds}s) → {clips_for_segment} x 10s clips")
                
                # Create clips for this segment
                for clip_idx in range(clips_for_segment):
                    if clip_counter >= total_clips_needed:
                        break
                    
                    sora_clips.append({
                        'segment_name': seg['name'],
                        'segment_part': f"{clip_idx + 1}/{clips_for_segment}",
                        'clip_number': clip_counter + 1,
                        'total_clips': total_clips_needed
                    })
                    clip_counter += 1
                
                if clip_counter >= total_clips_needed:
                    break
            
            print(f"[DEBUG] Mapped {len(segments)} segments to {len(sora_clips)} Sora clips")
            content_style = self._analyze_script_content_style(segments)
            style_template = self.CONTENT_STYLE_TEMPLATES.get(content_style, self.CONTENT_STYLE_TEMPLATES["professional_informational"])

            # ================================
            # STEP 4: Generate Sora Prompts (using Claude with mapping)
            # ================================
            
            # Format the mapping for Claude
            mapping_summary = "\n".join([
                f"Clip {clip['clip_number']}: {clip['segment_name']} (part {clip['segment_part']})"
                for clip in sora_clips[:20]  # Show first 20
            ])
            if len(sora_clips) > 20:
                mapping_summary += f"\n... and {len(sora_clips) - 20} more clips"

            prompt = f"""You are an AI Director creating Sora video prompts using PRODUCTION plot outline structure.

📋 PLOT OUTLINE STRUCTURE (from production system):
{len(segments)} segments mapped to {len(sora_clips)} Sora clips:
{mapping_summary}

EXAMPLE MAPPING:
- "Introduction" (30s) → Clips 1-3 (each 10s)
- "Main Incident #1" (180s) → Clips 4-21 (18 x 10s)
- "Conclusion" (30s) → Clips 22-24 (3 x 10s)
Total: 24 clips for 240s (4 minutes)

🚨 CRITICAL: EACH SORA PROMPT IS GENERATED INDEPENDENTLY WITH NO CONTEXT FROM OTHER SCENES!

⚠️ ABSOLUTE REQUIREMENTS:
1. Each scene is EXACTLY 10 seconds (Sora limitation)
2. Each prompt MUST BE COMPLETELY SELF-CONTAINED
3. NEVER use pronouns like "he", "she", "it", "the character" - ALWAYS use full descriptions
4. REPEAT ALL VISUAL DETAILS in EVERY prompt (character appearance, setting, lighting, props)
5. Only change the ACTION/STORY progression between scenes
6. Each scene must specify ending position that next scene will START from

❌ WRONG - Using pronouns and "same" (Sora has NO context):
Scene 1: "Orange cat with white paws sits sadly..."
Scene 2: "Same cat finds a dollar..." ← "Same"?? Sora doesn't know Scene 1!
Scene 3: "The cat looks sad..." ← "The cat"?? Which cat??

✅ CORRECT - Repeat IDENTICAL descriptions (NO pronouns, NO "same"):
Scene 1: "Medium shot of orange tabby cat with white paws and green collar, sitting on gray concrete sidewalk next to red brick wall, overcast daylight, realistic fur texture. Orange tabby cat with white paws stares at ground with drooping ears. Ambient city sounds, soft meowing. Camera slowly pushes in on orange cat's sad green eyes. End with orange cat's head lowering in defeat."

Scene 2: "Medium shot of orange tabby cat with white paws and green collar on gray concrete sidewalk next to red brick wall, overcast daylight, realistic fur texture. Orange tabby cat with white paws suddenly perks up with ears forward. Orange cat spots crumpled dollar bill wedged under sidewalk crack, green eyes widening. Ambient city sounds, happy chirping meow. Camera follows as orange cat with white paws reaches toward dollar. End with orange cat pulling dollar out with paw, holding it triumphantly in mouth."

Scene 3: "Medium shot of orange tabby cat with white paws and green collar on gray concrete sidewalk next to red brick wall, overcast daylight, realistic fur texture. Orange tabby cat grips dollar bill in mouth proudly. Human hand with tan skin wearing blue sleeve reaches down and plucks dollar from orange cat's mouth. Orange cat's green eyes go wide with shock. Ambient city sounds, sad descending meow. Camera static as hand retreats. End with orange tabby cat with white paws staring forward, ears flat, heartbroken expression."

NOTICE: Every prompt repeats "orange tabby cat with white paws and green collar" + "gray sidewalk" + "red brick wall" + "overcast daylight" - NEVER says "same" or uses pronouns!

TITLE: "{title}"
SERIES: "{series_name}" - THEME: "{theme_name}"
FORMAT: {format_type}-form video
TOTAL DURATION: {duration} seconds

YOUR TASK: Create {len(sora_clips)} self-contained Sora prompts (10s each)
- Follow the segment mapping above
- Clips in the same segment should progress the segment's story/action
- Maintain segment essence across its multiple clips
- Keep the series style and storytelling approach
- Each clip is COMPLETELY self-contained (repeat ALL visuals)

CONTENT STYLE: {content_style}

INSTRUCTIONS FOR CREATING SELF-CONTAINED PROMPTS:
1. Scene 1: Establish ALL visual elements with COMPLETE details
   - Character: "Professional male presenter age 35 with short black hair, wearing navy blue suit and red tie, standing in..."
   - Setting: "modern studio with white walls, wooden desk, gray carpet, three monitor setup visible..."
   - Lighting: "bright overhead studio lights with soft key light from left, minimal shadows..."

2. Scene 2-{len(sora_clips)}: COPY-PASTE the EXACT same visual descriptions, change ONLY the action
   - Character: "Professional male presenter age 35 with short black hair, wearing navy blue suit and red tie..." (IDENTICAL)
   - Setting: "modern studio with white walls, wooden desk, gray carpet, three monitor setup visible..." (IDENTICAL)  
   - Lighting: "bright overhead studio lights with soft key light from left, minimal shadows..." (IDENTICAL)
   - Action: NEW (sitting down, gesturing, turning toward camera, etc.)

3. NEVER write "same presenter" or "he" or "the man" - ALWAYS write full description
4. Think of it like you're describing {len(sora_clips)} completely separate photos to {len(sora_clips)} different people who can't see each other's work

For "{title}":
- Pick consistent identifiers and use them in ALL {len(sora_clips)} scenes
- Only the character's ACTIONS and DIALOGUE change
- Everything else (appearance, setting, lighting, camera) stays word-for-word identical

Respond in JSON format with {len(sora_clips)} scenes:
{{
  "storyboard_scenes": [
    {{
      "scene_number": 1,
      "title": "Opening - Establish Core Identifiers",
      "description": "Sets up all visual elements that will repeat",
      "duration": 10,
      "prompt": "Medium shot of [COMPLETE SUBJECT DESCRIPTION: age, gender, hair, clothing, accessories] in [COMPLETE SETTING: walls, floor, furniture, props, colors] with [COMPLETE LIGHTING: direction, color, intensity]. [Subject with full description] performs [opening action] while speaking with lipsync: '[exact dialogue]'. [Complete audio description]. [Camera movement]. End with [subject with full description] in [exact ending pose/position].",
      "visual_style": "Shot type and style",
      "audio_style": "Complete audio description",
      "camera_movement": "Specific movement",
      "lighting": "Exact lighting setup"
    }},
    {{
      "scene_number": 2,
      "title": "Story Progression",
      "description": "Continues story with IDENTICAL visuals",  
      "duration": 10,
      "prompt": "Medium shot of [EXACT SAME SUBJECT DESCRIPTION from Scene 1: age, gender, hair, clothing, accessories] in [EXACT SAME SETTING from Scene 1: walls, floor, furniture, props, colors] with [EXACT SAME LIGHTING from Scene 1: direction, color, intensity]. [Subject with FULL description again] performs [NEW action] while speaking with lipsync: '[NEW dialogue]'. [SAME audio description]. [SAME camera specs]. End with [subject with FULL description] in [NEW ending pose for Scene 3].",
      "visual_style": "IDENTICAL to Scene 1",
      "audio_style": "IDENTICAL to Scene 1"
    }},
    {{
      "scene_number": 3,
      "title": "Resolution",
      "description": "Concludes story with IDENTICAL visuals",
      "duration": 10,
      "prompt": "Medium shot of [EXACT SAME SUBJECT DESCRIPTION: copy from Scenes 1&2] in [EXACT SAME SETTING: copy from Scenes 1&2] with [EXACT SAME LIGHTING: copy from Scenes 1&2]. [Subject with FULL description] performs [FINAL action] while speaking with lipsync: '[final dialogue]'. [SAME audio]. [SAME camera]. End with [subject with FULL description] in [conclusive pose]."
    }}
  ]
}}

🚨 CRITICAL RULE: Copy-paste the subject, setting, and lighting descriptions WORD-FOR-WORD into every scene. Change ONLY the action/dialogue!"""

            # Calculate required tokens based on number of clips
            # Each clip needs ~200 tokens, buffer for long videos
            required_tokens = min(max(4000, len(sora_clips) * 250), 8000)

            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": required_tokens,  # Scale with clip count (4K for short, 8K for long)
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", 
                                   headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                content_text = result['content'][0]['text']
                
                # Extract JSON from Claude's response
                json_start = content_text.find('{')
                json_end = content_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = content_text[json_start:json_end]
                    storyboard_data = json.loads(json_str)
                    scenes = storyboard_data.get('storyboard_scenes', [])
                    print(f"[DEBUG] Generated {len(scenes)} storyboard scenes from script breakdown")
                    return scenes
                else:
                    print(f"[DEBUG] No JSON found in Claude response")
                    return self._get_fallback_storyboard(title, format_type, duration, scene_count)
            else:
                print(f"[DEBUG] Claude API error: {response.status_code}")
                return self._get_fallback_storyboard(title, format_type, duration, scene_count)
                
        except Exception as e:
            print(f"[DEBUG] Script-based storyboard generation failed: {e}")
            return self._get_fallback_storyboard(title, format_type, duration, scene_count)
    
    def _analyze_script_content_style(self, segments: List[Dict]) -> str:
        """Analyze script segments to determine content style"""
        if not segments:
            return "general_narrative"
        
        # Analyze content patterns
        total_content = " ".join([seg.get('content', '') for seg in segments[:10]]).lower()
        
        # Educational/Informational patterns
        if any(word in total_content for word in ['learn', 'understand', 'explain', 'tutorial', 'guide', 'how to']):
            return "educational_documentary"
        
        # News/Current events patterns  
        elif any(word in total_content for word in ['breaking', 'news', 'report', 'today', 'recent', 'update']):
            return "news_documentary"
        
        # Storytelling/Narrative patterns
        elif any(word in total_content for word in ['story', 'tale', 'once upon', 'character', 'journey']):
            return "cinematic_narrative"
        
        # Review/Analysis patterns
        elif any(word in total_content for word in ['review', 'analysis', 'opinion', 'think', 'believe']):
            return "conversational_review"
        
        # Entertainment/Gaming patterns
        elif any(word in total_content for word in ['game', 'play', 'fun', 'entertainment', 'funny']):
            return "entertainment_casual"
        
        else:
            return "professional_informational"
    
    def _format_script_segments_for_analysis(self, segments: List[Dict]) -> str:
        """Format script segments for Claude analysis"""
        if not segments:
            return "No script segments available"
        
        formatted = []
        for i, segment in enumerate(segments):
            content = segment.get('content', '')[:200]  # First 200 chars
            title = segment.get('title', f'Segment {i+1}')
            formatted.append(f"- {title}: {content}...")
        
        return "\n".join(formatted)
    
    async def _generate_basic_storyboard(self, title: str, series_name: str, theme_name: str,
                                       format_type: str, duration: int, scene_count: int) -> List[Dict]:
        """Generate basic storyboard when no script breakdown is available
        
        Uses Claude AI to create storyboard without script context
        Still ensures 10-second scene continuity for stitching
        """
        # Use fallback which already handles 10s segments properly
        return self._get_fallback_storyboard(title, format_type, duration, scene_count)
    
    async def _generate_storyboard_with_claude(self, title: str, series_name: str, theme_name: str,
                                             format_type: str, duration: int, scene_count: int, 
                                             vfx_guidelines: Dict) -> List[Dict]:
        """Generate storyboard using Claude with series pattern analysis"""
        try:
            if not self.anthropic_api_key:
                print("[DEBUG] No Anthropic API key - using fallback storyboard")
                return self._get_fallback_storyboard(title, format_type, duration, scene_count)
            
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.anthropic_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            # Calculate scene durations
            scene_duration = duration // scene_count
            
            prompt = f"""You are an AI Director creating a Sora video storyboard for the series "{series_name}" theme "{theme_name}".

TITLE: "{title}"
FORMAT: {format_type}-form video
TOTAL DURATION: {duration} seconds
SCENES: {scene_count} scenes (~{scene_duration}s each)

SERIES VISUAL GUIDELINES:
{vfx_guidelines.get('VFX_GUIDELINES', {})}

Create a detailed storyboard that:
1. Maintains the visual style and patterns of this series
2. Tells a compelling story that fits the title
3. Uses Sora's audio+video generation capabilities
4. Follows the series' typical content structure

For each scene, provide:
- Scene title and description
- Detailed Sora prompt (visual + audio description)
- Duration in seconds
- Visual style matching series patterns
- Audio style (narration, dialogue, music, effects)

IMPORTANT: Sora generates both video AND audio together, so include audio descriptions in prompts.

Respond in JSON format:
{{
  "storyboard_scenes": [
    {{
      "scene_number": 1,
      "title": "Scene title",
      "description": "What happens in this scene",
      "duration": {scene_duration},
      "prompt": "Detailed Sora prompt including both visual and audio elements",
      "visual_style": "Style matching series (e.g., cinematic, documentary, etc.)",
      "audio_style": "Audio description (narration, dialogue, music, etc.)",
      "camera_movement": "Camera movement style",
      "lighting": "Lighting style"
    }}
  ]
}}

Make it engaging and true to the series style while leveraging Sora's unique capabilities!"""

            payload = {
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = requests.post("https://api.anthropic.com/v1/messages", 
                                   headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                content_text = result['content'][0]['text']
                
                # Extract JSON from Claude's response
                json_start = content_text.find('{')
                json_end = content_text.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = content_text[json_start:json_end]
                    storyboard_data = json.loads(json_str)
                    scenes = storyboard_data.get('storyboard_scenes', [])
                    print(f"[DEBUG] Generated {len(scenes)} storyboard scenes with Claude")
                    return scenes
                else:
                    print(f"[DEBUG] No JSON found in Claude response")
                    return self._get_fallback_storyboard(title, format_type, duration, scene_count)
            else:
                print(f"[DEBUG] Claude API error: {response.status_code}")
                return self._get_fallback_storyboard(title, format_type, duration, scene_count)
                
        except Exception as e:
            print(f"[DEBUG] Claude storyboard generation failed: {e}")
            return self._get_fallback_storyboard(title, format_type, duration, scene_count)
    
    def _get_fallback_storyboard(self, title: str, format_type: str, duration: int, scene_count: int) -> List[Dict]:
        """Fallback storyboard when AI generation fails
        
        CRITICAL: Each scene is exactly 10 seconds (Sora limitation)
        Scenes will be stitched together to create final video
        """
        # Ensure proper types (safety check)
        duration = int(duration) if not isinstance(duration, int) else duration
        scene_count = int(scene_count) if not isinstance(scene_count, int) else scene_count
        
        # CRITICAL: Each Sora clip is EXACTLY 10 seconds
        # Calculate how many 10s segments needed
        num_10s_segments = (duration + 9) // 10  # Round up
        actual_duration = num_10s_segments * 10
        
        print(f"[DEBUG] Fallback: {duration}s requested → Creating {num_10s_segments} x 10s clips = {actual_duration}s total")
        
        scenes = []
        
        scene_templates = [
            {
                "title": "Opening",
                "description": "Establish the setting and introduce the main concept",
                "visual_style": "establishing_shot",
                "audio_style": "engaging_narration",
                "camera_movement": "slow_pan"
            },
            {
                "title": "Development", 
                "description": "Explore the main topic with detailed explanation",
                "visual_style": "medium_shot",
                "audio_style": "informative_narration",
                "camera_movement": "static_hold"
            },
            {
                "title": "Climax",
                "description": "Present the most important or exciting information",
                "visual_style": "close_up",
                "audio_style": "dramatic_narration",
                "camera_movement": "gentle_zoom"
            },
            {
                "title": "Resolution",
                "description": "Conclude with key takeaways or call to action",
                "visual_style": "wide_shot",
                "audio_style": "conclusive_narration", 
                "camera_movement": "pull_back"
            },
            {
                "title": "Finale",
                "description": "Final impactful moment or summary",
                "visual_style": "dramatic_angle",
                "audio_style": "memorable_conclusion",
                "camera_movement": "dynamic_movement"
            }
        ]
        
        # Establish core identifiers that will be repeated in ALL scenes
        core_subject = "professional presenter with short dark hair wearing casual button-up shirt"
        core_setting = "modern minimalist studio with white walls and wooden desk"
        core_lighting = "bright overhead studio lighting with soft natural light from window"
        core_audio = "clear studio audio with professional microphone"
        
        for i in range(num_10s_segments):
            template = scene_templates[i % len(scene_templates)]
            
            # Build the action (only thing that changes)
            if i == 0:
                action = "introducing the topic with welcoming gesture"
                ending_action = "gesturing toward the topic area while smiling"
            elif i == num_10s_segments - 1:
                action = "concluding with final key point"
                ending_action = "giving confident nod and slight wave"
            else:
                action = f"explaining {template['title'].lower()} with engaging gestures"
                ending_action = "transitioning to next point with hand gesture"
            
            # CRITICAL: Repeat identical visual descriptions, only change the action
            scene = {
                "scene_number": i + 1,
                "title": f"{template['title']} - {title}",
                "description": template['description'],
                "duration": 10,  # FIXED: Always 10 seconds per Sora API
                "prompt": (
                    f"Medium shot of {core_subject} in {core_setting}, {core_lighting}. "
                    f"{core_subject.capitalize()} is {action} about '{title}'. "
                    f"{core_audio}. Camera: {template['camera_movement']}. "
                    f"End with {core_subject} {ending_action}."
                ),
                "visual_style": template['visual_style'],
                "audio_style": template['audio_style'],
                "camera_movement": template['camera_movement'],
                "lighting": "professional_cinematic"
            }
            scenes.append(scene)
        
        print(f"[DEBUG] Generated {len(scenes)} fallback storyboard scenes")
        return scenes
    
    def generate_test_sora_prompts(self, content_style: str = "educational_documentary") -> List[str]:
        """Generate test Sora prompts for immediate testing"""
        
        test_prompts = {
            "educational_documentary": [
                "Medium shot of a confident female instructor in a modern classroom, looking directly at camera with professional lighting. She speaks with clear lipsync: 'Today we're going to learn something that will completely change how you think about productivity. Most people get this completely wrong, but I'm about to show you the secret.' Clean studio audio, authoritative delivery. Whiteboard visible behind her, she gestures naturally. Slow push-in on her face as she delivers the key line. End with her confident smile and slight nod.",
                
                "Close-up of hands drawing a diagram on a whiteboard, marker squeaking softly. Male voice narrates with clear pronunciation: 'This simple framework has helped thousands of people double their output in just 30 days.' Camera pulls back to reveal the complete diagram. Professional classroom lighting, clean background. Steady camera work, educational pacing. End with the instructor stepping back to reveal the full framework."
            ],
            
            "entertainment_casual": [
                "Dynamic front-facing camera on an excited young streamer with RGB lighting behind him. He suddenly jumps up from his gaming chair and shouts with clear lipsync: 'NO WAY! Did you guys just see that?! Chat, that was literally impossible!' Gaming setup visible, monitor glow on his face. High energy audio with slight reverb. Camera follows his movement as he paces excitedly. End with him pointing directly at camera saying 'Smash that like button!'",
                
                "Handheld camera following a content creator through a colorful room filled with props. She speaks energetically with clear lipsync: 'Guys, I just discovered something that's going to blow your mind! This is either genius or completely insane.' Vibrant lighting, casual but engaging framing. Natural room tone, conversational audio. She picks up and examines various items. End with her holding up the main product with a huge grin."
            ],
            
            "cinematic_narrative": [
                "Extreme close-up of weathered hands holding an old photograph, golden hour light streaming through dusty air. Deep, emotional male voice with clear lipsync: 'I never thought I'd see this place again. Twenty years ago, I made a promise here.' Atmospheric audio with subtle wind. Camera slowly pulls back to reveal abandoned warehouse. Film grain, cinematic color grading. End with him looking up and whispering 'Sarah, if you can hear me, I kept my word.'",
                
                "Dramatic low-angle shot of a woman silhouetted against storm clouds, wind whipping her hair. She speaks with emotional intensity and clear lipsync: 'They said it couldn't be done. They said I was crazy to even try.' Thunder rumbles in distance, voice cuts through wind. Cinematic lighting, dramatic shadows. Camera circles her slowly as she speaks. End with lightning flash illuminating her determined expression."
            ],
            
            "conversational_review": [
                "Intimate medium shot of a casual reviewer in cozy room with warm lighting, holding a product. He speaks directly to camera with natural delivery and clear lipsync: 'Okay guys, I've been testing this for three weeks now, and I have to be honest with you. This either completely changed my life, or it's the biggest waste of money I've ever spent.' Room tone, natural reverb. He sets product down thoughtfully. Slight handheld feel, personal framing. End with him leaning back and saying 'Let me break down exactly what happened.'",
                
                "Close-up of reviewer's face with soft key lighting, cozy background visible. She speaks conversationally with clear lipsync: 'Before I tell you whether this is worth buying, let me share what happened when I tried it for the first time.' Natural audio, intimate mic distance. Camera slowly pushes in as she builds suspense. Warm, inviting atmosphere. End with her raising an eyebrow and smiling mysteriously."
            ],
            
            "comedy_funny": [
                "Medium shot of a comedian in casual clothes standing in front of a brick wall, looking directly at camera with perfect comedic timing. He speaks with clear lipsync and exaggerated expressions: 'So I went to the store yesterday to buy some common sense, but apparently they were all sold out. The cashier looked at me and said, sir, this is a Wendy's.' Slight handheld camera for authenticity, comedy club lighting. Natural room tone with slight echo. End with him shrugging and making a 'what can you do' face.",
                
                "Close-up reaction shot of a person's face as they taste something terrible, eyes widening in horror. They speak with perfect lipsync and dramatic delivery: 'I don't know what I expected, but it definitely wasn't this. This tastes like disappointment mixed with regret and a hint of why did I do this to myself.' Kitchen lighting, natural audio with slight reverb. Camera slowly zooms in on their disgusted expression. End with them dramatically spitting into a napkin."
            ],
            
            "meme_viral": [
                "TikTok-style vertical framing of a Gen Z creator in their bedroom with LED strip lights. They speak directly to camera with perfect lipsync and trending delivery: 'POV: You're trying to explain to your parents why you need another streaming subscription when you already have seventeen of them and you're still watching the same three shows on repeat.' Trendy lighting, phone camera quality. Natural room audio with slight compression. Quick gestures and expressions. End with them doing the classic 'it is what it is' shrug.",
                
                "Phone camera POV of someone dramatically lip-syncing to trending audio while doing mundane tasks. They mouth with perfect sync: 'When you realize you've been pronouncing 'epitome' wrong your entire life and now you question everything you thought you knew about the English language.' Kitchen/bedroom setting, natural lighting. Trending audio style with bass boost. Exaggerated facial expressions and hand gestures. End with them staring directly into camera with existential crisis face."
            ]
        }
        
        return test_prompts.get(content_style, test_prompts["educational_documentary"])

# Initialize service
vfx_service = VFXService()
