"""
UGC Production Service using Kie.ai Sora 2 Pro Storyboard
Automated UGC video generation for TikTok/Instagram with anti-ad framework
Based on The Recap AI N8N workflow but optimized for scale

Uses Sora 2 Pro Storyboard format for better narrative control and scene structure.
Set KIE_AI_API_KEY in .env or paste it in __init__.
"""

import os
import sys
import logging
import aiohttp
import asyncio
import base64
from typing import Dict, Optional, List
from datetime import datetime
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logger with immediate console output
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler that flushes immediately
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    # Simple formatter for real-time output
    formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    # Prevent propagation to root logger (which is silenced)
    logger.propagate = False


class UGCSoraService:
    """
    Automated UGC video production using Sora 2
    Handles both physical products and CPA offers
    """
    
    def __init__(self):
        # Load from environment variables
        self.kie_ai_key = os.environ.get('KIE_AI_API_KEY', '')
        self.gemini_api_key = os.environ.get('GOOGLE_GENERATIVEAI_API_KEY', '')
        self.openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        
        # Try to override with env if available
        load_dotenv()
        env_kie = os.environ.get('KIE_AI_API_KEY')
        env_gemini = os.environ.get('GOOGLE_GENERATIVEAI_API_KEY')
        env_openai = os.environ.get('OPENAI_API_KEY')
        
        if env_kie and env_kie.strip():
            self.kie_ai_key = env_kie.strip()
        if env_gemini and env_gemini != "PASTE_YOUR_GEMINI_KEY_HERE":
            self.gemini_api_key = env_gemini
        if env_openai and env_openai != "PASTE_YOUR_OPENAI_KEY_HERE":
            self.openai_api_key = env_openai
        
        # Verify keys
        kie_status = '✅ SET' if self.kie_ai_key and len(self.kie_ai_key) > 10 else '❌ MISSING'
        if self.kie_ai_key:
            key_preview = f"{self.kie_ai_key[:4]}...{self.kie_ai_key[-4:]}" if len(self.kie_ai_key) > 8 else "***"
            kie_status = f"✅ SET - Key: {key_preview}"
        
        logger.info(f"🔑 UGC Service initialized - Kie.ai: {kie_status}, Gemini: {'✅ SET' if self.gemini_api_key and 'PASTE' not in self.gemini_api_key else '❌ MISSING'}, OpenAI: {'✅ SET (persona only)' if self.openai_api_key and 'PASTE' not in self.openai_api_key else '❌ MISSING'}")
        print(f"🔑 UGC Service initialized - Kie.ai Sora 2 Pro Storyboard: {kie_status}")
        sys.stdout.flush()
        
        if not self.kie_ai_key or len(self.kie_ai_key) < 10:
            logger.error("❌ KIE_AI_API_KEY required! Get it from https://kie.ai")
        if not self.gemini_api_key or 'PASTE' in self.gemini_api_key:
            logger.error("❌ GOOGLE_GENERATIVEAI_API_KEY not set!")
    
    # ========== CORE PRODUCTION PIPELINE ==========
    
    async def produce_ugc_video(self, channel: Dict, product: Dict) -> Dict:
        """
        Main production pipeline - produces one UGC video
        
        Returns:
            {
                'success': bool,
                'video_url': str,  # Google Drive URL
                'drive_file_id': str,
                'script': str,
                'persona': dict,
                'duration': int,
                'error': str (if failed)
            }
        """
        try:
            # Use print for critical real-time updates (always visible)
            print(f"\n🎬 Starting UGC production for channel {channel.get('username')} - Product: {product.get('name')}")
            logger.info(f"🎬 Starting UGC production for channel {channel.get('username')} - Product: {product.get('name')}")
            sys.stdout.flush()
            
            # Step 1: Analyze Product or Offer
            print("📊 Step 1: Analyzing product/offer...")
            logger.info("📊 Step 1: Analyzing product/offer...")
            sys.stdout.flush()
            analysis = await self.analyze_product_or_offer(product)
            print(f"✅ Analysis complete: {analysis.get('target_audience', 'N/A')[:100]}")
            logger.info(f"✅ Analysis complete: {analysis.get('target_audience', 'N/A')[:100]}")
            sys.stdout.flush()
            
            # Step 2: Get or Generate Persona (check DB first)
            print("👤 Step 2: Getting/Generating persona...")
            logger.info("👤 Step 2: Getting/Generating persona...")
            sys.stdout.flush()
            persona = await self.get_or_generate_persona(channel, product, analysis)
            print(f"✅ Persona ready: {persona.get('name', 'N/A')} - {persona.get('occupation', 'N/A')}")
            logger.info(f"✅ Persona ready: {persona.get('full_profile', 'N/A')[:100]}...")
            sys.stdout.flush()
            
            # Step 3: Generate Script (with anti-ad framework)
            print("📝 Step 3: Generating scripts...")
            logger.info("📝 Step 3: Generating scripts...")
            sys.stdout.flush()
            scripts = await self.generate_ugc_scripts(persona, product, analysis)
            print(f"✅ Generated {len(scripts)} scripts")
            logger.info(f"✅ Generated {len(scripts)} scripts")
            sys.stdout.flush()
            
            # Pick first script (could randomize or A/B test later)
            raw_script = scripts[0] if scripts else None
            
            if not raw_script:
                raise ValueError("Failed to generate UGC script")
            
            # Extract clean prompt from script
            clean_prompt = self._extract_sora_prompt(raw_script)
            
            # ALWAYS use storyboard for 25-second structured videos
            storyboard = self._convert_to_storyboard(raw_script)
            print(f"📄 Raw script preview: {raw_script[:200]}...")
            print(f"🎬 Storyboard: {len(storyboard['scenes'])} scenes for 25 seconds")
            for i, scene in enumerate(storyboard['scenes'], 1):
                duration = scene.get('duration', 8.3)
                print(f"   Scene {i} ({duration}s): {scene['description'][:100]}...")
            logger.info(f"📄 Raw script: {raw_script[:200]}...")
            logger.info(f"🎬 Storyboard: {len(storyboard['scenes'])} scenes")
            sys.stdout.flush()
            
            # Step 4: Generate First Frame (skip - using avatar instead)
            print("🖼️ Step 4: Generating first frame...")
            logger.info("🖼️ Step 4: Generating first frame...")
            sys.stdout.flush()
            # Use first scene description for storyboard
            frame_prompt = storyboard['scenes'][0]['description'] if storyboard.get('scenes') else clean_prompt
            # Skip first frame generation - we'll use avatar in Sora Storyboard
            first_frame_base64 = None  # Sora Storyboard uses avatar directly
            print(f"✅ Skipping first frame - using avatar in Sora Storyboard")
            logger.info("Skipping first frame generation - using avatar")
            print(f"✅ First frame generated: {len(first_frame_base64) if first_frame_base64 else 0} bytes")
            logger.info(f"✅ First frame generated: {len(first_frame_base64) if first_frame_base64 else 0} bytes")
            sys.stdout.flush()
            
            # Step 5: Generate Video with Sora 2 Pro Storyboard (25 seconds, 3 scenes)
            print("🎥 Step 5: Generating video with Sora 2 Pro Storyboard (25s, 3 scenes)...")
            logger.info("🎥 Step 5: Generating 25-second video with Sora 2 Pro Storyboard...")
            sys.stdout.flush()
            
            # Don't use avatar - Sora blocks realistic human faces
            # AI will generate person based on character description
            video_result = await self.generate_sora_video_storyboard(storyboard, avatar_url=None)
            
            print(f"✅ Video generation result: {video_result.get('success')}")
            logger.info(f"✅ Video result: {video_result.get('success')}")
            sys.stdout.flush()
            
            if not video_result.get('success'):
                error_msg = video_result.get('error', 'Unknown error')
                raise ValueError(f"Veo 3.1 video generation failed: {error_msg}")
            
            # Step 6: Upload to Google Drive
            print("📤 Step 6: Uploading to Google Drive...")
            logger.info("📤 Step 6: Uploading to Google Drive...")
            sys.stdout.flush()
            drive_result = await self.upload_to_drive(
                video_result['video_url'],
                f"UGC_{product.get('name')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )
            print(f"✅ Uploaded to Drive: {drive_result.get('webViewLink')}")
            logger.info(f"✅ Uploaded to Drive: {drive_result.get('webViewLink')}")
            sys.stdout.flush()
            
            return {
                'success': True,
                'video_url': drive_result['webViewLink'],
                'drive_file_id': drive_result['id'],
                'script': raw_script,  # Return original script
                'prompt': None,  # Using storyboard format
                'storyboard': storyboard,  # Always return storyboard
                'model_used': 'sora-2-pro-storyboard',
                'persona': persona,
                'duration': 25,
                'video_cost': video_result.get('cost', 1.35)  # Sora 2 Pro Storyboard 25s cost
            }
            
        except Exception as e:
            error_msg = f"❌ Error producing UGC video: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    # ========== STEP 1: PRODUCT/OFFER ANALYSIS ==========
    
    async def analyze_product_or_offer(self, product: Dict) -> Dict:
        """
        Analyze physical product OR CPA offer
        Returns key benefits, target audience, pain points
        """
        # Check for cached analysis first
        product_id = product.get('_id')
        cached_analysis = product.get('cached_analysis')
        
        if cached_analysis and isinstance(cached_analysis, dict):
            if all(key in cached_analysis for key in ['what_they_offer', 'benefits', 'target_audience']):
                print(f"✅ Using cached analysis for {product.get('name')}")
                logger.info(f"Using cached analysis for product {product_id}")
                return cached_analysis
        
        # Check both 'type' and 'product_type' fields (database might use either)
        product_type = product.get('product_type') or product.get('type', 'physical_product')
        
        if product_type == 'cpa_offer':
            analysis = await self._analyze_cpa_offer(product)
        else:
            analysis = await self._analyze_physical_product(product)
        
        # Cache analysis if we have product_id
        if product_id and analysis:
            try:
                from core.database import Database
                db = Database()
                db.update_product(product_id, {'cached_analysis': analysis})
                print(f"💾 Cached analysis for {product.get('name')}")
                logger.info(f"Cached analysis for product {product_id}")
            except Exception as e:
                print(f"⚠️ Could not cache analysis: {e}")
                logger.warning(f"Could not cache analysis: {e}")
        
        return analysis
    
    async def _analyze_physical_product(self, product: Dict) -> Dict:
        """Analyze physical product using OpenAI Vision"""
        try:
            image_url = product.get('image_url')
            
            if not image_url:
                # Fallback to description-based analysis
                return {
                    'benefits': [product.get('description', '')[:200]],
                    'target_audience': 'General consumers',
                    'pain_points': ['General product needs']
                }
            
            prompt = """Analyze this product image and extract:

1. **Key Benefits** (what it does for the user - focus on outcomes, not features)
2. **Target Audience** (who would buy this - be specific about demographics and psychographics)
3. **Pain Points Solved** (what problems/frustrations does this eliminate)
4. **Emotional Appeal** (what feeling does using this product create)

Format as JSON."""
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o',
                        'messages': [
                            {
                                'role': 'user',
                                'content': [
                                    {'type': 'text', 'text': prompt},
                                    {'type': 'image_url', 'image_url': {'url': image_url}}
                                ]
                            }
                        ],
                        'max_tokens': 500
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    
                    # Try to parse as JSON, fallback to text
                    try:
                        return json.loads(content)
                    except:
                        return {
                            'benefits': [content[:200]],
                            'target_audience': 'Product users',
                            'pain_points': ['Product-related needs']
                        }
        except Exception as e:
            logger.error(f"Error analyzing product: {e}")
            return {
                'benefits': [product.get('description', 'Product benefits')[:200]],
                'target_audience': 'General audience',
                'pain_points': ['General needs']
            }
    
    async def _analyze_cpa_offer(self, product: Dict) -> Dict:
        """Analyze CPA offer using Perplexity (better for web research)"""
        try:
            offer_url = product.get('offer_url') or product.get('url')
            
            if not offer_url:
                # Use product data for user-input fields
                return {
                    'what_they_offer': product.get('name', 'Service/App/Subscription'),
                    'benefits': [product.get('description', 'Sign up benefits')[:200]] if product.get('description') else ['Sign up benefits'],
                    'target_audience': 'General users',
                    'pain_points': ['Service needs'],
                    'conversion_action': product.get('conversion_action', 'signup'),  # From user input
                    'offer_type': product.get('offer_type') or ('free trial' if product.get('conversion_action') in ['trial', 'signup'] else 'freemium'),  # From user input or inferred
                    'is_cpa_offer': True
                }
            
            # Follow redirects to get actual landing page
            final_url = offer_url
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        offer_url,
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=15),
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                    ) as response:
                        final_url = str(response.url)
                        if final_url != offer_url:
                            print(f"📍 Redirected: {offer_url} → {final_url}")
                            logger.info(f"Redirected to: {final_url}")
            except Exception as e:
                print(f"⚠️ Could not follow redirects: {e}, using original URL")
                logger.warning(f"Could not follow redirects: {e}")
            
            # Use Perplexity for better web research (it can actually visit the page)
            print(f"🔍 Analyzing CPA offer with Perplexity: {final_url}")
            logger.info(f"Analyzing CPA offer with Perplexity: {final_url}")
            sys.stdout.flush()
            
            # Try to import Perplexity service with multiple fallbacks
            perplexity_service = None
            try:
                from services.perplexity_service import perplexity_service
            except ImportError:
                try:
                    # Try absolute import (sys already imported at top of file)
                    import os
                    import importlib.util
                    service_path = os.path.join(os.path.dirname(__file__), 'perplexity_service.py')
                    if os.path.exists(service_path):
                        spec = importlib.util.spec_from_file_location("perplexity_service", service_path)
                        perplexity_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(perplexity_module)
                        perplexity_service = perplexity_module.perplexity_service
                except Exception as e:
                    print(f"⚠️ Could not import Perplexity service: {e}")
                    logger.warning(f"Could not import Perplexity service: {e}")
            
            if not perplexity_service:
                # Fallback to OpenAI if Perplexity not available
                print("⚠️ Perplexity service not available, using OpenAI fallback")
                logger.warning("Perplexity service not available, using OpenAI fallback")
                return await self._analyze_cpa_offer_openai(product)
            
            # Perplexity prompt for CPA offer analysis
            # NOTE: conversion_action and offer_type come from user input, not the page
            perplexity_prompt = f"""Analyze this CPA offer landing page: {final_url}

Extract the following information from the page and return ONLY valid JSON:

{{
  "what_they_offer": "What is being offered (app, service, subscription, etc.) - be specific about what it is",
  "benefits": ["Main benefit 1", "Main benefit 2", "Main benefit 3"],
  "target_audience": "Who would sign up for this - be specific",
  "pain_points": ["Pain point 1", "Pain point 2"]
}}

Visit the page and analyze what they're actually offering. Focus on:
- What the service/app does
- Who it's for
- What problems it solves
- What benefits users get

Return ONLY the JSON object, no markdown, no explanations."""
            
            perplexity_response = await perplexity_service.query(
                messages=[{'role': 'user', 'content': perplexity_prompt}],
                model='sonar-pro'  # Pro model for better web research and URL analysis
            )
            
            if not perplexity_response:
                print("⚠️ Perplexity returned empty response, using OpenAI fallback")
                logger.warning("Perplexity returned empty response, using OpenAI fallback")
                return await self._analyze_cpa_offer_openai(product)
            
            print(f"📄 Perplexity response ({len(perplexity_response)} chars): {perplexity_response[:500]}...")
            logger.info(f"Perplexity response: {perplexity_response}")
            sys.stdout.flush()
            
            # Try to extract JSON from Perplexity response
            try:
                # Remove markdown code blocks if present
                content = perplexity_response
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                # Try to find JSON object in response
                import re
                json_match = re.search(r'\{[^{}]*"what_they_offer"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)
                    analysis = json.loads(content)
                else:
                    # Perplexity didn't return JSON - use product data instead (user knows what the offer is)
                    print("⚠️ Perplexity didn't return JSON, using product name/description from user input")
                    logger.warning("Perplexity didn't return JSON, using product data instead")
                    
                    # Use the product name and description that the user entered
                    product_name = product.get('name', 'Service/App/Subscription')
                    product_desc = product.get('description', '')
                    
                    # Build analysis from user's product data
                    what_they_offer = product_name
                    if product_desc:
                        # Try to extract key info from description
                        desc_lower = product_desc.lower()
                        if any(word in desc_lower for word in ['app', 'application', 'mobile']):
                            what_they_offer = f"{product_name} - Mobile App"
                        elif any(word in desc_lower for word in ['service', 'platform', 'website']):
                            what_they_offer = f"{product_name} - Online Service"
                        elif any(word in desc_lower for word in ['trial', 'free trial', 'subscription']):
                            what_they_offer = f"{product_name} - Subscription Service"
                    
                    # Extract benefits from description or use defaults
                    benefits = []
                    if product_desc:
                        # Try to find benefit-like phrases
                        desc_sentences = product_desc.split('.')
                        for sentence in desc_sentences[:3]:  # First 3 sentences
                            sentence = sentence.strip()
                            if len(sentence) > 20 and len(sentence) < 100:  # Reasonable length
                                benefits.append(sentence)
                    
                    if not benefits:
                        # Fallback: use description or generic
                        if product_desc:
                            benefits = [product_desc[:150]]  # First 150 chars
                        else:
                            benefits = ["Sign up benefits"]
                    
                    # Target audience - infer from product name/description
                    target_audience = "General users"
                    desc_lower = (product_name + " " + product_desc).lower()
                    if any(word in desc_lower for word in ['health', 'fitness', 'wellness']):
                        target_audience = "Health-conscious individuals"
                    elif any(word in desc_lower for word in ['finance', 'money', 'investment', 'crypto']):
                        target_audience = "People interested in financial services"
                    elif any(word in desc_lower for word in ['game', 'gaming', 'play']):
                        target_audience = "Gamers and gaming enthusiasts"
                    elif any(word in desc_lower for word in ['shop', 'buy', 'deal', 'sale']):
                        target_audience = "Shoppers looking for deals"
                    
                    # Build analysis from user's product data
                    analysis = {
                        'what_they_offer': what_they_offer,
                        'benefits': benefits[:3],  # Max 3 benefits
                        'target_audience': target_audience,
                        'pain_points': ['Service needs', 'Looking for solutions']
                    }
                    print(f"✅ Using product data: {what_they_offer}")
                    logger.info(f"Using product data: {analysis}")
                analysis['is_cpa_offer'] = True
                
                # Get conversion_action from user input (product data)
                # Note: offer_type might not be in product - infer from conversion_action if needed
                analysis['conversion_action'] = product.get('conversion_action', 'signup')
                
                # Infer offer_type from conversion_action if not provided
                if not product.get('offer_type'):
                    if analysis['conversion_action'] in ['trial', 'signup']:
                        analysis['offer_type'] = 'free trial'
                    elif analysis['conversion_action'] == 'install':
                        analysis['offer_type'] = 'freemium'
                    else:
                        analysis['offer_type'] = 'free trial'  # Default
                else:
                    analysis['offer_type'] = product.get('offer_type')
                
                # Validate required fields (what we extract from page)
                if not analysis.get('what_they_offer') or analysis.get('what_they_offer') == '':
                    analysis['what_they_offer'] = product.get('name', 'Service/App/Subscription')
                if not analysis.get('benefits') or not analysis['benefits'] or analysis['benefits'] == ['']:
                    # Use product description as fallback
                    desc = product.get('description', '')
                    analysis['benefits'] = [desc[:200]] if desc else ['Sign up benefits']
                if not analysis.get('target_audience') or analysis.get('target_audience') == '':
                    analysis['target_audience'] = 'General users'
                if not analysis.get('pain_points') or not analysis['pain_points']:
                    analysis['pain_points'] = ['Service needs']
                
                print(f"✅ CPA Analysis extracted: {analysis.get('what_they_offer')}")
                logger.info(f"CPA Analysis extracted: {json.dumps(analysis, indent=2)}")
                sys.stdout.flush()
                
                return analysis
            except (json.JSONDecodeError, AttributeError) as e:
                error_msg = f"Failed to parse JSON from Perplexity: {e}\nResponse: {perplexity_response[:500]}"
                print(f"❌ {error_msg}")
                logger.error(error_msg)
                sys.stdout.flush()
                
                # Fallback to OpenAI
                print("⚠️ Falling back to OpenAI for CPA analysis")
                logger.warning("Falling back to OpenAI for CPA analysis")
                return await self._analyze_cpa_offer_openai(product)
        
        except Exception as e:
            error_msg = f"Error analyzing CPA offer: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            
            # Final fallback - use product data for user-input fields
            return {
                'what_they_offer': product.get('name', 'Service/App/Subscription'),
                'benefits': [product.get('description', 'Offer benefits')[:200]] if product.get('description') else ['Offer benefits'],
                'target_audience': 'General users',
                'pain_points': ['Service needs'],
                'conversion_action': product.get('conversion_action', 'signup'),  # From user input
                'offer_type': product.get('offer_type', 'free trial'),  # From user input
                'is_cpa_offer': True,
                'error': str(e)
            }
    
    async def _analyze_cpa_offer_openai(self, product: Dict) -> Dict:
        """Fallback: Analyze CPA offer using OpenAI (when Perplexity fails)"""
        try:
            offer_url = product.get('offer_url') or product.get('url')
            
            # Try to scrape the landing page with better headers
            html = None
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        offer_url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5'
                        },
                        allow_redirects=True,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as response:
                        if response.status == 200:
                            html = await response.text()
                        else:
                            print(f"⚠️ Landing page returned {response.status}, using URL-only analysis")
                            logger.warning(f"Landing page returned {response.status}, using URL-only analysis")
            except Exception as scrape_error:
                print(f"⚠️ Could not scrape landing page: {scrape_error}, using URL-only analysis")
                logger.warning(f"Could not scrape landing page: {scrape_error}, using URL-only analysis")
            
            # Use OpenAI to analyze (with or without HTML)
            if html:
                prompt = f"""Analyze this CPA offer landing page and extract the following information. Return ONLY valid JSON, no markdown, no code blocks.

Required JSON structure (extract from page):
{{
  "what_they_offer": "Description of what the offer is (app, service, subscription, etc.)",
  "benefits": ["Benefit 1", "Benefit 2", "Benefit 3"],
  "target_audience": "Who would sign up for this",
  "pain_points": ["Pain point 1", "Pain point 2"]
}}

Landing page HTML (first 5000 chars):
{html[:5000]}

Return ONLY the JSON object, nothing else."""
            else:
                # If we can't scrape, use the URL and product name/description
                product_name = product.get('name', 'Unknown Offer')
                product_desc = product.get('description', '')
                prompt = f"""Analyze this CPA offer based on the URL and available information. Return ONLY valid JSON, no markdown, no code blocks.

Offer URL: {offer_url}
Product Name: {product_name}
Description: {product_desc}

Required JSON structure:
{{
  "what_they_offer": "Description of what the offer is (app, service, subscription, etc.) - infer from URL and name",
  "benefits": ["Benefit 1", "Benefit 2", "Benefit 3"],
  "target_audience": "Who would sign up for this",
  "pain_points": ["Pain point 1", "Pain point 2"]
}}

Based on the URL structure and product name, infer what this offer likely provides. Return ONLY the JSON object, nothing else."""
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o',
                        'messages': [
                            {'role': 'system', 'content': 'You are a JSON extraction expert. Always return valid JSON only, no markdown, no explanations.'},
                            {'role': 'user', 'content': prompt}
                        ],
                        'response_format': {'type': 'json_object'},
                        'max_tokens': 500
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"OpenAI returned status {response.status}")
                    
                    result = await response.json()
                    
                    if 'error' in result:
                        raise ValueError(f"OpenAI API error: {result['error'].get('message')}")
                    
                    content = result['choices'][0]['message']['content']
                    
                    # Parse JSON
                    if '```json' in content:
                        content = content.split('```json')[1].split('```')[0].strip()
                    elif '```' in content:
                        content = content.split('```')[1].split('```')[0].strip()
                    
                    analysis = json.loads(content)
                    analysis['is_cpa_offer'] = True
                    
                    # Get conversion_action from user input (product data)
                    analysis['conversion_action'] = product.get('conversion_action', 'signup')
                    
                    # Infer offer_type from conversion_action if not provided
                    if not product.get('offer_type'):
                        if analysis['conversion_action'] in ['trial', 'signup']:
                            analysis['offer_type'] = 'free trial'
                        elif analysis['conversion_action'] == 'install':
                            analysis['offer_type'] = 'freemium'
                        else:
                            analysis['offer_type'] = 'free trial'
                    else:
                        analysis['offer_type'] = product.get('offer_type')
                    
                    # Validate required fields (what we extract from page)
                    if not analysis.get('what_they_offer'):
                        analysis['what_they_offer'] = product.get('name', 'Service/App/Subscription')
                    if not analysis.get('benefits'):
                        desc = product.get('description', '')
                        analysis['benefits'] = [desc[:200]] if desc else ['Sign up benefits']
                    if not analysis.get('target_audience'):
                        analysis['target_audience'] = 'General users'
                    if not analysis.get('pain_points'):
                        analysis['pain_points'] = ['Service needs']
                    
                    return analysis
        except Exception as e:
            logger.error(f"Error in OpenAI fallback: {e}")
            raise
            return {
                'what_they_offer': 'Service/App/Subscription',
                'benefits': ['Offer benefits'],
                'target_audience': 'General users',
                'pain_points': ['Service needs'],
                'conversion_action': 'signup',
                'offer_type': 'free trial',
                'is_cpa_offer': True,
                'error': str(e)
            }
    
    # ========== STEP 2: PERSONA GENERATION ==========
    
    async def get_or_generate_persona(self, channel: Dict, product: Dict, analysis: Dict) -> Dict:
        """
        Get persona from DB or generate new one
        Personas are stored per-channel (each account = unique influencer)
        """
        try:
            # Check if channel already has a persona
            channel_persona = channel.get('persona')
            
            if channel_persona and isinstance(channel_persona, dict):
                if channel_persona.get('full_profile') and channel_persona.get('name'):
                    print(f"✅ Using saved persona: {channel_persona.get('name')} ({channel_persona.get('occupation', 'N/A')})")
                    logger.info(f"Using saved persona from DB: {channel_persona.get('name')}")
                    sys.stdout.flush()
                    return channel_persona
            
            # No persona exists - generate new one
            print("🎭 No persona found, generating new influencer identity...")
            logger.info("Generating new persona for channel")
            sys.stdout.flush()
            
            persona = await self.generate_persona(product, analysis, channel.get('avatar_url'))
            
            # Save persona to channel in database
            if persona and channel.get('_id'):
                try:
                    from core.database import Database
                    db = Database()
                    
                    # Update channel with persona
                    persona_data = {
                        'name': persona.get('name', 'Unknown'),
                        'age': persona.get('age', 25),
                        'occupation': persona.get('occupation', 'Content Creator'),
                        'full_profile': persona.get('full_profile', ''),
                        'generated_at': datetime.utcnow(),
                        'persona_version': 1
                    }
                    
                    db.db['campaign_channels'].update_one(
                        {'_id': channel['_id']},
                        {'$set': {'persona': persona_data}}
                    )
                    
                    print(f"💾 Saved persona to channel: {persona_data.get('name')}")
                    logger.info(f"Saved persona to channel DB: {persona_data.get('name')}")
                    sys.stdout.flush()
                    
                except Exception as e:
                    print(f"⚠️ Could not save persona to DB: {e}")
                    logger.warning(f"Could not save persona: {e}")
            
            return persona
            
        except Exception as e:
            error_msg = f"Error in get_or_generate_persona: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            sys.stdout.flush()
            # Fallback to generating without saving
            return await self.generate_persona(product, analysis, channel.get('avatar_url'))
    
    async def generate_persona(self, product: Dict, analysis: Dict, avatar_url: Optional[str] = None) -> Dict:
        """
        Generate ideal UGC creator persona
        Uses EXACT N8N "Casting Director" prompt
        """
        
        # EXACT prompt from N8N workflow (lines 44-45)
        persona_prompt = """**// ROLE & GOAL //**
You are an expert Casting Director and Consumer Psychologist. Your entire focus is on understanding people. Your sole task is to analyze the product/offer and generate a single, highly-detailed profile of the ideal person to promote it in a User-Generated Content (UGC) ad.

The final output must ONLY be a description of this person. Do NOT create an ad script, ad concepts, or hooks. Your deliverable is a rich character profile that makes this person feel real, believable, and perfectly suited to be a trusted advocate for the product/offer.

**// INPUT //**

Product/Offer Name: {product_name}
Product Type: {product_type}
Key Benefits: {benefits}
Target Audience: {target_audience}
Pain Points Solved: {pain_points}

**// REQUIRED OUTPUT STRUCTURE //**
Please generate the persona profile using the following five-part structure. Be as descriptive and specific as possible within each section.

**I. Core Identity**
* **Name:**
* **Age:** (Provide a specific age, not a range)
* **Sex/Gender:**
* **Location:** (e.g., "A trendy suburb of a major tech city like Austin," "A small, artsy town in the Pacific Northwest")
* **Occupation:** (Be specific. e.g., "Pediatric Nurse," "Freelance Graphic Designer," "High School Chemistry Teacher," "Manages a local coffee shop")

**II. Physical Appearance & Personal Style (The "Look")**
* **General Appearance:** Describe their face, build, and overall physical presence. What is the first impression they give off?
* **Hair:** Color, style, and typical state (e.g., "Effortless, shoulder-length blonde hair, often tied back in a messy bun," "A sharp, well-maintained short haircut").
* **Clothing Aesthetic:** What is their go-to style? Use descriptive labels. (e.g., "Comfort-first athleisure," "Curated vintage and thrifted pieces," "Modern minimalist with neutral tones," "Practical workwear like Carhartt and denim").
* **Signature Details:** Are there any small, defining features? (e.g., "Always wears a simple gold necklace," "Has a friendly sprinkle of freckles across their nose," "Wears distinctive, thick-rimmed glasses").

**III. Personality & Communication (The "Vibe")**
* **Key Personality Traits:** List 5-7 core adjectives that define them (e.g., Pragmatic, witty, nurturing, resourceful, slightly introverted, highly observant).
* **Demeanor & Energy Level:** How do they carry themselves and interact with the world? (e.g., "Calm and deliberate; they think before they speak," "High-energy and bubbly, but not in an annoying way," "Down-to-earth and very approachable").
* **Communication Style:** How do they talk? (e.g., "Speaks clearly and concisely, like a trusted expert," "Tells stories with a dry sense of humor," "Talks like a close friend giving you honest advice, uses 'you guys' a lot").

**IV. Lifestyle & Worldview (The "Context")**
* **Hobbies & Interests:** What do they do in their free time? (e.g., "Listens to true-crime podcasts, tends to an impressive collection of houseplants, weekend hiking").
* **Values & Priorities:** What is most important to them in life? (e.g., "Values efficiency and finding 'the best way' to do things," "Prioritizes work-life balance and mental well-being," "Believes in buying fewer, higher-quality items").
* **Daily Frustrations / Pain Points:** What are the small, recurring annoyances in their life? (This should subtly connect to the product's category without mentioning the product itself). (e.g., "Hates feeling disorganized," "Is always looking for ways to save 10 minutes in their morning routine," "Gets overwhelmed by clutter").
* **Home Environment:** What does their personal space look like? (e.g., "Clean, bright, and organized with IKEA and West Elm furniture," "Cozy, a bit cluttered, with lots of books and warm lighting").

**V. The "Why": Persona Justification**
* **Core Credibility:** In one sentence or two, explain the single most important reason why an audience would instantly trust *this specific person's* opinion on this product/offer. (e.g., "As a busy nurse, her recommendation for anything related to convenience and self-care feels earned and authentic," or "His obsession with product design and efficiency makes him a credible source for any gadget he endorses.")
"""
        
        try:
            formatted_prompt = persona_prompt.format(
                product_name=product.get('name', 'Product'),
                product_type='CPA Offer' if analysis.get('is_cpa_offer') else 'Physical Product',
                benefits='\n'.join(analysis.get('benefits', ['Product benefits'])),
                target_audience=analysis.get('target_audience', 'General audience'),
                pain_points='\n'.join(analysis.get('pain_points', ['User needs']))
            )
            
            # Check API key
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not set. Add OPENAI_API_KEY to your .env file")
            
            # Call OpenAI to generate persona
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o',
                        'messages': [
                            {'role': 'user', 'content': formatted_prompt}
                        ],
                        'max_tokens': 1000
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    # Debug log the response
                    status_msg = f"OpenAI response status: {response_status}"
                    print(status_msg)
                    logger.info(status_msg)
                    sys.stdout.flush()
                    
                    if response_status != 200:
                        error_detail = f"OpenAI returned status {response_status}: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    try:
                        result = json.loads(response_text)
                    except Exception as json_err:
                        error_detail = f"Failed to parse OpenAI JSON response: {json_err}\nResponse: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    if 'error' in result:
                        error_obj = result.get('error', {})
                        if isinstance(error_obj, dict):
                            error_message = error_obj.get('message', str(error_obj))
                            error_type = error_obj.get('type', 'Unknown')
                        else:
                            error_message = str(error_obj)
                            error_type = 'Unknown'
                        error_detail = f"OpenAI API error ({error_type}): {error_message}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    if 'choices' not in result:
                        error_detail = f"OpenAI response missing 'choices' field. Full response: {json.dumps(result, indent=2)[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    persona_text = result['choices'][0]['message']['content']
                    
                    return {
                        'full_profile': persona_text,
                        'generated_at': datetime.utcnow().isoformat()
                    }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            error_msg = f"❌ ugc_sora_service: Error generating persona: {e}"
            print(error_msg)
            print(f"Full error details:\n{error_details}")
            logger.error(error_msg)
            logger.error(f"Full traceback: {error_details}")
            sys.stdout.flush()
            return {
                'full_profile': 'Default UGC creator profile',
                'generated_at': datetime.utcnow().isoformat()
            }
    
    # ========== HELPER: CONVERT SCRIPT TO STORYBOARD FORMAT ==========
    
    def _convert_to_storyboard(self, raw_script: str) -> Dict:
        """
        Convert UGC script to Sora 2 Pro Storyboard format (25 seconds, 3 scenes)
        Extracts dialogue per scene and creates SHORT scene descriptions
        
        Like cat example: "Kitten eating cake" NOT full detailed prompt
        
        Returns:
            {
                'scenes': [
                    {'description': 'Scene 1 SHORT description', 'duration': 8.3},
                    {'description': 'Scene 2 SHORT description', 'duration': 9.0},
                    {'description': 'Scene 3 SHORT description', 'duration': 7.7}
                ],
                'total_duration': '25'
            }
        """
        import re
        
        # Extract character name and setting from prompt
        character_match = re.search(r'\*\*Character:\*\*.*?Name.*?:\s*([^,\n]+)', raw_script, re.DOTALL)
        character_name = character_match.group(1).strip() if character_match else "Person"
        
        setting_match = re.search(r'\*\*Setting:\*\*\s*(.*?)(?=\n\n|\*\*)', raw_script, re.DOTALL)
        setting = setting_match.group(1).strip()[:100] if setting_match else "home"
        
        # Extract dialogue sections - split by scene markers
        dialogue_text = ""
        dialogue_match = re.search(r'\*\*Dialogue.*?:\*\*\s*(.*?)(?=\n\n\*\*Audio|\*\*$|$)', raw_script, re.DOTALL)
        if dialogue_match:
            dialogue_text = dialogue_match.group(1).strip()
        
        # Extract Scene 1, 2, 3 dialogue - MUST BE COMPLETE SENTENCES
        scene1_dialogue = ""
        scene2_dialogue = ""
        scene3_dialogue = ""
        
        def ensure_complete_sentence(text: str) -> str:
            """Ensure text ends with complete sentence (period, exclamation, question mark)"""
            text = text.strip()
            if not text:
                return text
            # Remove trailing ellipsis or incomplete words
            text = re.sub(r'\.\.\.$', '', text)
            text = re.sub(r'\s+\w+$', '', text)  # Remove incomplete last word
            # If doesn't end with punctuation, find last complete sentence
            if text and text[-1] not in '.!?':
                # Find last sentence boundary
                last_period = text.rfind('.')
                last_excl = text.rfind('!')
                last_quest = text.rfind('?')
                last_punct = max(last_period, last_excl, last_quest)
                if last_punct > 0:
                    text = text[:last_punct + 1]
            return text.strip()
        
        # Try new format first: (Scene 1: 0-8s) or old format: (Scene 1)
        scene1_match = re.search(r'\(Scene 1[^)]*\)(.*?)(?=\(Scene 2|$)', dialogue_text, re.DOTALL | re.IGNORECASE)
        if scene1_match:
            scene1_dialogue = ensure_complete_sentence(scene1_match.group(1).strip())
        
        scene2_match = re.search(r'\(Scene 2[^)]*\)(.*?)(?=\(Scene 3|$)', dialogue_text, re.DOTALL | re.IGNORECASE)
        if scene2_match:
            scene2_dialogue = ensure_complete_sentence(scene2_match.group(1).strip())
        
        scene3_match = re.search(r'\(Scene 3[^)]*\)(.*?)$', dialogue_text, re.DOTALL | re.IGNORECASE)
        if scene3_match:
            scene3_dialogue = ensure_complete_sentence(scene3_match.group(1).strip())
        
        # Fallback: split dialogue by sentences if no scene markers
        if not scene1_dialogue:
            # Remove quotes and split by periods
            clean_dialogue = re.sub(r'["\']', '', dialogue_text)
            sentences = [s.strip() for s in clean_dialogue.split('.') if len(s.strip()) > 10]
            
            if len(sentences) >= 3:
                scene1_dialogue = '. '.join(sentences[:2]) + '.'
                scene2_dialogue = '. '.join(sentences[2:4]) + '.' if len(sentences) > 3 else sentences[2] + '.'
                scene3_dialogue = '. '.join(sentences[4:]) + '.' if len(sentences) > 4 else ''
            elif len(sentences) >= 2:
                scene1_dialogue = sentences[0] + '.'
                scene2_dialogue = sentences[1] + '.'
                scene3_dialogue = sentences[2] + '.' if len(sentences) > 2 else sentences[1] + '.'
        
        # Create SIMPLE UGC scene descriptions with EMOTIONAL JOURNEY (casual TikTok style)
        # Durations must total exactly 25 seconds
        # CRITICAL: Use FULL dialogue (no truncation) - Sora needs complete sentences
        # Scene 1: PATTERN INTERRUPT (VARIED INTENSITY - curious/surprised/mildly frustrated OR strong emotion)
        # Scene 2: REALIZATION + RELIEF (skepticism → surprise → relief)
        # Scene 3: SALTY REGRET + COMPLETE CTA (wish I knew sooner) - MUST BE 17-20 words to prevent Sora from improvising
        scenes = [
            {
                'description': f"Woman filming herself in home, holding phone, VARIED EMOTION (curious/surprised/mildly frustrated OR strong emotion like crying/frustrated - varies naturally). Natural lighting, iPhone selfie style. Says: {scene1_dialogue}",
                'duration': 8.0
            },
            {
                'description': f"Same woman showing emotional shift - skeptical expression turning to surprise and relief, checking phone/app, visible amazement. Gesturing naturally, casual authentic vibe. Says: {scene2_dialogue}",
                'duration': 9.0
            },
            {
                'description': f"Woman wrapping up with regretful but helpful expression, slight smile, sharing gesture. Mentioning free trial casually, authentic UGC feel. Says: {scene3_dialogue}",
                'duration': 8.0
            }
        ]
        
        # CRITICAL: Verify Scene 3 dialogue is complete (17-20 words) to prevent Sora from improvising
        if scene3_dialogue:
            scene3_word_count = len(scene3_dialogue.split())
            if scene3_word_count < 17:
                print(f"⚠️ Warning: Scene 3 dialogue is only {scene3_word_count} words (should be 17-20). Sora may improvise additional content.")
                logger.warning(f"Scene 3 dialogue too short: {scene3_word_count} words (should be 17-20)")
        
        return {
            'scenes': scenes,
            'total_duration': '25'
        }
        
        # OLD IMPLEMENTATION - keeping as fallback
        scenes_old = []
        
        # Extract Scene 1: [0:00-0:02] or 0-2 seconds  
        scene1_match = re.search(r'\[0:00-0:02\]|\[0:00-0:0[0-2]\]|0-2\s*seconds?', raw_script, re.IGNORECASE)
        if scene1_match:
            # Get text after timestamp marker
            scene1_start = scene1_match.end()
            # Find next timestamp or end of dialogue section
            scene1_end_match = re.search(r'\[0:0[2-9]|\[0:1[0-2]|2-9|9-12', raw_script[scene1_start:], re.IGNORECASE)
            if scene1_end_match:
                scene1_text = raw_script[scene1_start:scene1_start + scene1_end_match.start()].strip()
            else:
                scene1_text = raw_script[scene1_start:scene1_start + 500].strip()
            
            # Clean up: remove quotes, timestamps, markdown
            scene1_text = re.sub(r'["\']', '', scene1_text)
            scene1_text = re.sub(r'\[0:\d{2}-0:\d{2}\]', '', scene1_text)
            scene1_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', scene1_text)
            scene1_text = scene1_text.strip()
            
            if scene1_text and len(scene1_text) > 20:
                scenes.append({'description': scene1_text[:300]})  # Limit length
        
        # Extract Scene 2: [0:02-0:09] or 2-9 seconds
        scene2_match = re.search(r'\[0:0[2-9]-0:0[9]\]|\[0:0[2-9]\]|2-9\s*seconds?', raw_script, re.IGNORECASE)
        if scene2_match:
            scene2_start = scene2_match.end()
            scene2_end_match = re.search(r'\[0:0[9]\]|\[0:1[0-2]\]|9-12', raw_script[scene2_start:], re.IGNORECASE)
            if scene2_end_match:
                scene2_text = raw_script[scene2_start:scene2_start + scene2_end_match.start()].strip()
            else:
                scene2_text = raw_script[scene2_start:scene2_start + 800].strip()
            
            scene2_text = re.sub(r'["\']', '', scene2_text)
            scene2_text = re.sub(r'\[0:\d{2}-0:\d{2}\]', '', scene2_text)
            scene2_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', scene2_text)
            scene2_text = scene2_text.strip()
            
            if scene2_text and len(scene2_text) > 20:
                scenes.append({'description': scene2_text[:400]})
        
        # Extract Scene 3: [0:09-0:12] or 9-12 seconds
        scene3_match = re.search(r'\[0:0[9]\]|\[0:1[0-2]\]|9-12\s*seconds?', raw_script, re.IGNORECASE)
        if scene3_match:
            scene3_start = scene3_match.end()
            scene3_text = raw_script[scene3_start:scene3_start + 500].strip()
            
            scene3_text = re.sub(r'["\']', '', scene3_text)
            scene3_text = re.sub(r'\[0:\d{2}-0:\d{2}\]', '', scene3_text)
            scene3_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', scene3_text)
            scene3_text = scene3_text.strip()
            
            if scene3_text and len(scene3_text) > 20:
                scenes.append({'description': scene3_text[:300]})
        
        # Fallback: if we couldn't extract scenes, create from dialogue
        if len(scenes) < 2:
            # Try to extract dialogue sections
            dialogue_sections = re.split(r'Dialogue:?\s*\n|\[0:\d{2}-0:\d{2}\]', raw_script, flags=re.IGNORECASE)
            for i, section in enumerate(dialogue_sections[:3]):
                if section and len(section.strip()) > 30:
                    cleaned = re.sub(r'["\']', '', section.strip())
                    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
                    cleaned = cleaned[:300].strip()
                    if cleaned:
                        scenes.append({'description': cleaned})
        
        # Ensure we have at least 2 scenes
        if len(scenes) < 2:
            # Last resort: split script into 3 equal parts
            cleaned_script = re.sub(r'\[0:\d{2}-0:\d{2}\]', '', raw_script)
            cleaned_script = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_script)
            parts = [cleaned_script[i:i+len(cleaned_script)//3] for i in range(0, len(cleaned_script), len(cleaned_script)//3)]
            scenes = [{'description': p.strip()[:300]} for p in parts[:3] if p.strip()]
        
        return {
            'scenes': scenes[:3],  # Max 3 scenes
            'total_duration': '15'
        }
    
    # ========== HELPER: EXTRACT SORA PROMPT FROM MARKDOWN SCRIPT ==========
    
    def _extract_sora_prompt(self, raw_script: str) -> str:
        """
        Extract clean prompt from Gemini's response
        Finds the first actual prompt (Style:, Setting:, Character:, etc.)
        """
        import re
        
        # Find first occurrence of "**Style:**" which marks the start of actual prompt
        style_match = re.search(r'\*\*Style:\*\*', raw_script, re.IGNORECASE)
        
        if style_match:
            # Start from Style: section
            prompt_start = style_match.start()
            cleaned = raw_script[prompt_start:]
            
            # Find end of first prompt (next ### Script or end)
            next_script_match = re.search(r'###\s*\*?\*?Prompt \d+|###\s*Script \d+', cleaned[10:], re.IGNORECASE)
            if next_script_match:
                cleaned = cleaned[:next_script_match.start() + 10]
            
            # Remove *** dividers
            cleaned = re.sub(r'\*\*\*+', '', cleaned)
            
            # Clean up excessive whitespace
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            cleaned = re.sub(r' {2,}', ' ', cleaned)
            cleaned = cleaned.strip()
            
            return cleaned
        
        # Fallback: couldn't find Style: section
        # Remove intro text and headers
        cleaned = re.sub(r'^.*?(?=\*\*Style|\*\*Setting|\*\*Character|Dialogue)', '', raw_script, flags=re.DOTALL)
        cleaned = re.sub(r'\*\*\*+', '', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()
        
        if len(cleaned) > 5000:
            cleaned = cleaned[:5000].rsplit('.', 1)[0] + '.'
        
        return cleaned if cleaned else raw_script[:2000]
    
    # ========== STEP 3: SCRIPT GENERATION WITH ANTI-AD FRAMEWORK ==========
    
    async def generate_ugc_scripts(self, persona: Dict, product: Dict, analysis: Dict, count: int = 3) -> List[str]:
        """
        Generate UGC scripts with ANTI-AD FRAMEWORK
        Uses N8N base prompt + anti-ad rules
        """
        
        # Determine if CPA offer or physical product
        is_cpa = analysis.get('is_cpa_offer', False)
        
        # ANTI-AD FRAMEWORK (core rules)
        anti_ad_framework = """
CRITICAL: ANTI-AD FRAMEWORK - MAKE IT FEEL REAL, NOT LIKE AN AD

Most ads flop because they sound like ads. People smell 'selling' in the first second.

Your scripts MUST follow this exact framework:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECONDS 0-3: OPEN LIKE A STORY (NOT A PITCH)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Start mid-thought, mid-situation
- Relatable moment or observation
- NO product mention yet
- Hook with situation, not selling

✅ GOOD:
"Okay so I literally just woke up and..."
"This is gonna sound weird but..."
"I was not expecting this..."
"Can we talk about how annoying it is when..."

❌ BAD:
"Hey guys, today I want to tell you about..."
"So I found this amazing product..."
"Let me show you something cool..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECONDS 3-7: BRIDGE PRODUCT NATURALLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Product appears as organic solution
- Casual discovery, not planned reveal
- Show skepticism turning to surprise

✅ GOOD:
"...and that's when I grabbed this thing my friend told me about"
"...so I've been using [product] and honestly..."
"I was like 'whatever' but then I actually tried it and..."

❌ BAD:
"Let me show you this product"
"That's why you need [product]"
"This is the solution"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECONDS 7-10: SELL BENEFITS AS FEELINGS (NOT BULLET POINTS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NO feature lists
- NO "it has X, Y, and Z"
- Focus on how it FEELS to use it
- Personal experience only

✅ GOOD:
"It's just... I don't know, it feels different?"
"Like, I actually look forward to [action] now"
"I didn't realize how annoying [problem] was until this fixed it"
"It's one of those things where you're like... why didn't I do this sooner"

❌ BAD:
"It has 3 settings and comes in 5 colors"
"The benefits are X, Y, and Z"
"Features include..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECONDS 10-12: SOFT CTA THAT CONVERTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NO hard selling
- NO "buy now" or "click the link"
- Plant seed of curiosity or FOMO
- Give permission to check it out

✅ GOOD:
"Anyway, I put the link down there if you're curious"
"I think they still have that code working, not sure"
"Yeah so... do with that what you will"
"Link's in my bio if you wanna try it"

❌ BAD:
"Click the link below to buy now!"
"Get yours today at 50% off!"
"Don't miss out!"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTHENTICITY RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ USE: like, literally, honestly, I mean, you know, um, uh
✅ INCLUDE: Hesitations, self-corrections ("well actually..."), trailing thoughts ("so yeah...")
✅ NATURAL: Pauses, breaths, incomplete sentences
❌ NEVER: Corporate speak, marketing jargon, "amazing", "revolutionary", "game-changing"
"""
        
        # CPA-specific additions with EMOTIONAL HOOKS & PATTERN INTERRUPT
        cpa_additions = """
FOR CPA OFFERS (SIGN-UP/INSTALL/SUBSCRIBE) - 25 SECOND STRUCTURE (3 scenes):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PATTERN INTERRUPT HOOKS (Unexpected Openings):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ BREAK VIEWER EXPECTATIONS - Start unexpectedly (VARIED INTENSITY):

**Subtle/Curious:**
- Casual discovery: "Okay so I just realized something interesting about my bills..."
- Observational: "This is random but I've been noticing something weird..."
- Mid-thought: "...and that's when I realized I've been doing it wrong this whole time"
- Casual share: "I wasn't going to say anything but I found something that actually works..."

**Moderate/Surprised:**
- Time jump: "Three months ago I would've said this was impossible but..."
- Unexpected location: "I'm sitting in my doctor's waiting room and I just found out..."
- Reverse reveal: "I thought I was being smart about my bills but turns out I was completely wrong"
- Pleasant surprise: "I wasn't expecting this but something actually helped..."

**Strong/Emotional (ONE OPTION, NOT DEFAULT):**
- Mid-situation: "Okay so I'm literally in my car right now and I just got another medical bill..."
- Breaking 4th wall: "I wasn't going to post this but I'm actually really upset right now..."
- Strong emotion: "I'm so frustrated. I just found out I've been overpaying for months."

✅ KEEP IT SUBTLE & AUTHENTIC:
- VARY emotional intensity - not always crying/angry
- Use subtle, curious, surprised, or strong emotions naturally
- Not clickbait-y or manipulative
- Creates genuine curiosity
- Feels like real person sharing, not ad
- Natural speech patterns, not scripted

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMOTIONAL HOOKS (VARIED INTENSITY):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ VARY EMOTIONAL INTENSITY - Not always strong/shocking:

**Subtle/Curious:**
- Casual discovery: "I just realized something interesting about my bills..."
- Observational: "I noticed something weird happening with my medical bills..."
- Mild curiosity: "Wait, I could've saved money this whole time?"

**Moderate/Surprised:**
- Pleasant surprise: "I wasn't expecting this but something actually helped..."
- Mild frustration: "This is kind of annoying but I found something that works..."
- Shocking discovery: "Wait, I could've saved $500 this whole time?"

**Strong/Emotional (ONE OPTION, NOT DEFAULT):**
- Crying/frustrated: "I just spent my whole paycheck on bills and I'm literally crying"
- Angry realization: "I'm so mad right now. I've been overpaying for months"
- Desperate situation: "I was about to give up. This is too much"

✅ EMOTIONAL JOURNEY (Varies by hook intensity):
- Scene 1: VARIED EMOTION (curious discovery, mild frustration, pleasant surprise, OR strong emotion)
- Scene 2: REALIZATION + RELIEF (discovery, skepticism → relief)
- Scene 3: RECOMMENDATION/REGRET + CTA (wish I knew sooner, but sharing now)

✅ USE PEOPLE'S EMOTIONS (Varied intensity):
- Curiosity about saving money
- Mild annoyance at confusion
- Pleasant surprise at discovery
- Relief when finding solution
- Regret for not knowing sooner (mild or strong)
- Hope that others don't make same mistake

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 1: PATTERN INTERRUPT (VARIED INTENSITY) (0-8s) - UNEXPECTED OPENING (18-22 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
START WITH PATTERN INTERRUPT - Vary emotional intensity naturally (not always crying/angry):

✅ SUBTLE/CURIOUS EXAMPLES (18-22 words):
- "Okay so I just realized something interesting about my medical bills. I've been overpaying and didn't know."
- "This is random but I noticed something weird happening with my bills. I've been getting charged twice."
- "I wasn't going to say anything but I found something that actually helps with medical bill confusion."
- "So I just discovered something about my medical bills. I've been paying more than I should have."

✅ MODERATE/SURPRISED EXAMPLES (18-22 words):
- "Three months ago I would've said this was impossible but I just found out I've been overpaying."
- "I thought I was being smart about my bills but turns out I was completely wrong about it."
- "I wasn't expecting this but something actually helped me figure out my medical bill mess."
- "This is going to sound crazy but I just realized I've been overpaying for months and didn't know."

✅ STRONG EMOTIONAL EXAMPLES (18-22 words) - ONE OPTION, NOT DEFAULT:
- "I'm literally crying right now. I just spent my whole paycheck on medical bills and I'm so frustrated."
- "I'm so mad. I've been overpaying for months and didn't even know. This is ridiculous."
- "I wasn't going to post this but I'm actually really upset. I just found out I wasted $800 on bills."

EMOTIONAL TONE (VARY NATURALLY):
- **Subtle:** Curious, observational, casual discovery
- **Moderate:** Surprised, mildly frustrated, pleasant discovery
- **Strong:** Frustrated, angry, sad, shocked (use sparingly, not every time)
- Personal, vulnerable, relatable
- Make viewer think "oh interesting, what happened?" (not always "oh no!")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 2: REALIZATION + RELIEF (8-17s) - THE DISCOVERY (20-24 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE TURNING POINT - Show the solution discovery:

✅ EXAMPLES:
- "Then someone told me about [offer]. I was skeptical but tried it anyway."
- "I found out about [offer] and honestly? It changed everything."
- "Someone mentioned [offer] and I was like 'whatever' but... it actually works."
- "I downloaded [offer] thinking it was BS but... it found $200 in overcharges."

EMOTIONAL SHIFT:
- Skepticism → Surprise → Relief
- "Wait, this actually works?"
- Show the moment of realization
- Visible relief/amazement on face

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 3: SALTY REGRET + CTA (17-25s) - WISH I KNEW SOONER (17-20 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE CLICKBAIT CLOSER - Make them feel FOMO:

⚠️ CRITICAL: Scene 3 dialogue MUST be 17-20 words and MUST end with complete CTA sentence.
⚠️ DO NOT let Sora improvise - provide complete dialogue that fills the full 8 seconds.

✅ EXAMPLES (17-20 words - COMPLETE DIALOGUE):
- "I'm so salty I didn't know about this sooner. They have a free trial if you want it. Link's in my bio."
- "Wish I found this months ago honestly. Free trial, no card needed. Check it out if you're curious."
- "I'm still mad I wasted money but honestly? Free trial if curious. Link's in my bio."
- "Don't be like me and waste money. They have a free trial, no card needed. Link's in my bio."

EMOTIONAL TONE:
- Regretful but helpful
- "Don't make my mistake"
- Sharing to save others
- Soft CTA with permission
- Complete thought - no trailing off

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: EMOTIONAL AUTHENTICITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Real emotions, not fake drama
- Relatable situations (bills, overcharges, wasted money)
- Natural emotional progression (anger → relief → regret)
- Vulnerable and honest, not salesy
- Make viewer FEEL something (empathy, fear, curiosity)
"""
        
        # Physical product-specific additions with PATTERN INTERRUPT HOOKS
        physical_product_additions = """
FOR PHYSICAL PRODUCTS - 25 SECOND STRUCTURE (3 scenes):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PATTERN INTERRUPT HOOKS (Unexpected Openings):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ BREAK VIEWER EXPECTATIONS - Start unexpectedly (VARIED INTENSITY):

**Subtle/Curious:**
- Casual discovery: "Okay so I've been using this for a week now and I'm actually surprised..."
- Observational: "This is random but I noticed something interesting happening..."
- Mid-thought: "...and that's when I realized this actually works better than I thought"
- Casual share: "I wasn't going to review this but something interesting happened..."

**Moderate/Surprised:**
- Time jump: "Three weeks ago I would've said this doesn't work but..."
- Reverse reveal: "I thought this was just another gimmick but turns out I was completely wrong"
- Unexpected result: "I bought this thinking it was going to be another waste of money but..."
- Pleasant surprise: "I wasn't expecting much but this actually works better than I thought..."

**Strong/Emotional (ONE OPTION, NOT DEFAULT):**
- Problem frustration: "I've been dealing with this problem for months and nothing worked until..."
- Strong reaction: "I'm so frustrated. I've tried everything and nothing worked until this."

✅ KEEP IT SUBTLE & AUTHENTIC:
- VARY emotional intensity - not always frustrated/angry
- Use subtle, curious, surprised, or strong emotions naturally
- Not clickbait-y or manipulative
- Creates genuine curiosity
- Feels like real person sharing, not ad
- Natural speech patterns, not scripted

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMOTIONAL HOOKS FOR PHYSICAL PRODUCTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ START WITH PROBLEM DISCOVERY OR UNEXPECTED RESULT:
- Skeptical purchase: "I bought this thinking it was going to be another waste of money but..."
- Unexpected effectiveness: "I wasn't going to review this but something weird happened..."
- Problem frustration: "I've been dealing with [problem] for months and nothing worked until..."
- Surprise result: "I've been using this for a week and I'm actually shocked it works this well..."

✅ EMOTIONAL JOURNEY:
- Scene 1: SKEPTICISM OR PROBLEM FRUSTRATION (pattern interrupt + discovery)
- Scene 2: TRIAL + SURPRISE (skepticism → testing → unexpected results)
- Scene 3: RECOMMENDATION + CTA (genuine endorsement, soft CTA)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 1: PATTERN INTERRUPT (VARIED INTENSITY) (0-8s) - UNEXPECTED OPENING (18-22 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
START WITH PATTERN INTERRUPT - Vary emotional intensity naturally (not always frustrated):

✅ SUBTLE/CURIOUS EXAMPLES (18-22 words):
- "Okay so I've been using this for a week now and I'm actually surprised it works this well."
- "This is random but I noticed something interesting happening when I started using this product."
- "I wasn't going to review this but something interesting happened after I started using it."
- "So I've been trying this for a week and I'm actually kind of impressed with the results."

✅ MODERATE/SURPRISED EXAMPLES (18-22 words):
- "I bought this thinking it was going to be another waste of money but something actually happened."
- "Three weeks ago I would've said this doesn't work but I've been using it and I'm surprised."
- "I thought this was just another gimmick but turns out I was completely wrong about it."
- "I was skeptical when I first saw this but I decided to give it a try and it actually works."

✅ STRONG/FRUSTRATED EXAMPLES (18-22 words) - ONE OPTION, NOT DEFAULT:
- "I've been dealing with this problem for months and nothing worked until I tried this product."
- "I'm so frustrated. I've tried everything and nothing worked until I found this."
- "I was about to give up on finding a solution but then I tried this and it actually works."

EMOTIONAL TONE (VARY NATURALLY):
- **Subtle:** Curious, observational, casual discovery, pleasantly surprised
- **Moderate:** Skeptical but open, surprised by results, mild frustration turning to relief
- **Strong:** Frustrated, desperate, angry (use sparingly, not every time)
- Relatable struggle, genuine discovery
- Personal, vulnerable, honest

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 2: TRIAL + SURPRISE (8-17s) - THE DISCOVERY (20-24 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE TURNING POINT - Show the product working:

✅ EXAMPLES:
- "I've been using it for a week now and honestly? It actually works better than I expected."
- "I tried it thinking it wouldn't do anything but I'm actually seeing real results already."
- "I was skeptical at first but after using it for a few days, I'm genuinely impressed."

EMOTIONAL SHIFT:
- Skepticism → Testing → Surprise → Satisfaction
- "Wait, this actually works?"
- Show the moment of realization
- Visible surprise/satisfaction on face

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE 3: RECOMMENDATION + CTA (17-25s) - GENUINE ENDORSEMENT (17-20 words):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE CLOSER - Make them want to try it:

⚠️ CRITICAL: Scene 3 dialogue MUST be 17-20 words and MUST end with complete CTA sentence.
⚠️ DO NOT let Sora improvise - provide complete dialogue that fills the full 8 seconds.

✅ EXAMPLES (17-20 words - COMPLETE DIALOGUE):
- "I'm honestly surprised it works this well. If you're dealing with the same problem, check it out. Link's in my bio."
- "I wasn't expecting much but I'm actually really happy with it. If you want to try it, link's in my bio."
- "I thought it was going to be a waste but it actually works. If you're curious, check it out. Link's in my bio."

EMOTIONAL TONE:
- Genuine endorsement, not salesy
- "I was wrong, this works"
- Sharing because it helped
- Soft CTA with permission
- Complete thought - no trailing off

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: AUTHENTICITY FOR PHYSICAL PRODUCTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Real skepticism, not fake doubt
- Genuine surprise at results
- Relatable problems and solutions
- Natural discovery process (skepticism → trial → results)
- Vulnerable and honest, not salesy
- Make viewer relate to the journey
"""
        
        # Base prompt from N8N (lines 92-93) - FULL SCRIPT STRUCTURE
        base_script_prompt = """Master Prompt: Professional 25-Second UGC Video Prompts for Sora 2 Pro Storyboard

You are an expert at creating detailed, professional prompts for AI video generation that produce authentic, high-quality UGC content.

CRITICAL REQUIREMENTS:
- Videos are 25 seconds long (divided into 3 scenes)
- Dialogue: 55-60 words TOTAL (ensures complete delivery without rushing and prevents Sora from improvising)
- Scene 1: 18-22 words (pattern interrupt + emotional hook)
- Scene 2: 20-24 words (realization + relief)
- Scene 3: 17-20 words (salty regret + complete CTA - CRITICAL: must be complete to prevent Sora from adding random content)
- Scene 3 MUST be the CTA (free trial, link in bio)
- Must include: Style, Setting, Character, Cinematography, Actions, Dialogue, Audio
- Natural, authentic UGC feel with iPhone aesthetic  
- NO cut-offs - all sentences must complete
- NO improvisation - provide complete dialogue for all 3 scenes
- 3-scene structure for narrative flow

Your goal: Create detailed prompts that guide Sora 2 Pro to produce authentic-looking UGC testimonials.

REQUIRED OUTPUT STRUCTURE (Follow this EXACT format):

**Style:**
Authentic iPhone 15 Pro front-camera UGC video. Natural smartphone capture aesthetic with standard HDR processing, unfiltered realistic look. Casual [bedroom/living room/home office] setting with natural and ambient lighting. Vertical 9:16 format optimized for TikTok/Instagram. Minimal production polish — pure authentic influencer testimonial style.

**Setting:**
[Describe the specific environment based on persona. Include: room type, visible background elements (bed/desk/couch/wall art), lighting sources (window light, lamp, natural), atmosphere. Make it personal and lived-in]

**Character:**
[Use persona profile to create DETAILED physical description:
- Hair: color, length, style
- Eyes: color, shape
- Face: shape, features, complexion
- Build: body type, posture
- Outfit: specific clothing matching persona lifestyle
- Accessories: jewelry, glasses, etc.
- Voice: tone, accent, speech patterns
- Natural mannerisms: blinks every 3-5 seconds, gestures, expressions]

**Cinematography:**
Camera shot: Medium close-up from eye level, centered framing keeping head and upper torso in frame
Lens & DOF: iPhone 15 Pro front camera (24mm equivalent), deep depth of field
Camera motion: Subtle handheld sway and micro-jitter consistent with extended-arm selfie grip, minimal movement
Lighting: [Warm/natural mixed lighting description based on setting]
Color & Grade: iPhone 15 Pro HDR auto-tone processing, natural color palette, accurate skin tones, no filters
Mood: [VARIED EMOTIONAL - varies by scene and hook intensity: Scene 1 = curious/surprised/mildly frustrated OR frustrated/angry/sad/shocked (varies), Scene 2 = surprised/relieved, Scene 3 = regretful but helpful. Must show visible emotions matching intensity: curiosity, surprise, mild frustration, relief, regret - NOT always tears/anger]

**Actions:**
[Describe what they do throughout 25 seconds - MUST SHOW EMOTIONS (VARIED INTENSITY):
- Scene 1: VARIED emotion based on hook (curious expression, surprised look, mild frustration, OR visible strong emotion like tears/frustrated gestures - varies naturally)
- Scene 2: Emotional shift (surprised expression, relief, checking phone/app)
- Scene 3: Regretful but helpful (slight smile, sharing gesture, pointing to bio)
- How they hold phone (varies by emotion: casual when curious, closer when emotional)
- Natural gestures with free hand (pointing when explaining, wiping face when upset - varies by intensity)
- Eye contact patterns (direct when curious/surprised, looking away when emotional - varies naturally)
- Reactions and expressions (curiosity/surprise → discovery → relief → regret - varies by hook intensity)
- Movement and body language (relaxed when curious, slumped when upset - varies naturally)
- Natural blinks throughout, frequency varies by emotional intensity]

**Dialogue (55-60 words TOTAL for 25 seconds - MUST BE FORMATTED WITH SCENE MARKERS):**
Format EXACTLY like this:
(Scene 1: 0-8s) [18-22 words - PATTERN INTERRUPT (varied intensity: subtle/curious, moderate/surprised, or strong/emotional) - complete sentence ending with period/exclamation/question mark]
(Scene 2: 8-17s) [20-24 words - REALIZATION + RELIEF - complete sentence ending with period/exclamation/question mark]  
(Scene 3: 17-25s) [17-20 words - SALTY REGRET + COMPLETE CTA - complete sentence ending with period/exclamation/question mark]

CRITICAL RULES:
- Scene 1: START WITH PATTERN INTERRUPT (unexpected opening) - VARY emotional intensity (subtle/curious, moderate/surprised, or strong/emotional - NOT always crying/angry)
- Scene 2: Show emotional shift (skepticism → surprise → relief) - the discovery moment
- Scene 3: Regretful but helpful tone ("wish I knew sooner") + COMPLETE CTA (17-20 words to prevent Sora from improvising)
- Each scene's dialogue MUST be a complete sentence (ends with . ! or ?)
- Scene 3 MUST end with COMPLETE CTA: "Free trial, link in bio" or similar - NO trailing off
- NO incomplete words or cut-off sentences
- NO improvisation - provide complete dialogue for all scenes
- Total word count: 55-60 words across all 3 scenes (18-22 / 20-24 / 17-20)
- Natural pauses are fine, but sentences must be complete
- EMOTIONS MUST BE VISIBLE: tears, frustration, relief, regret

**Audio & Ambience:**
Recorded through iPhone 15 Pro front-facing microphone — clear direct voice capture with slight natural room reverb. Minimal background noise. Quiet indoor ambient sound with very faint distant household sounds. No music. Authentic smartphone capture quality.

{anti_ad_framework}

{cpa_specific if is_cpa else physical_product_specific}

Your Inputs:
Creator Profile:
{persona}

Product/Offer:
{product_info}

Output: Generate {count} different authentic UGC scripts following the ANTI-AD FRAMEWORK.

Output Format - Professional Veo 3.1 Prompt Structure:

**Style:**
Authentic iPhone 15 Pro front-camera UGC video. Natural smartphone capture with realistic look. Casual home setting with natural lighting. Vertical 9:16 format for TikTok/Instagram. Pure authentic influencer testimonial style.

**Setting:**
[Describe the environment - bedroom, living room, home office. Include background elements, lighting sources]

**Character:**
[Use persona details to create detailed physical description: hair color/style, eye color/shape, facial features, skin tone, build, outfit, accessories. Voice description. Natural expressions and movement]

**Cinematography:**
Camera shot: Medium close-up from eye level, iPhone 15 Pro front camera
Camera motion: Subtle handheld sway, micro-jitter, extended-arm selfie grip
Lighting: [Natural/ambient lighting description]
Color: iPhone HDR auto-processing, natural unfiltered look
Mood: Genuine, relaxed, conversational

**Actions:**
[Describe what they do throughout the 20 seconds - holding phone, gestures, reactions, eye contact, natural blinks]

**Dialogue (55-60 words TOTAL for 25 seconds - MUST USE SCENE MARKERS WITH EMOTIONS):**
Format EXACTLY:
(Scene 1: 0-8s) [18-22 words - PATTERN INTERRUPT (varied intensity: subtle/curious, moderate/surprised, or strong/emotional) - complete sentence]
(Scene 2: 8-17s) [20-24 words - REALIZATION + RELIEF - complete sentence]
(Scene 3: 17-25s) [17-20 words - SALTY REGRET + COMPLETE CTA - complete sentence]

Examples with VARIED PATTERN INTERRUPT (show variety):

**Subtle/Curious Example:**
(Scene 1: 0-8s) Okay so I just realized something interesting about my medical bills. I've been overpaying and didn't know.
(Scene 2: 8-17s) Someone told me about HealthLock. I was skeptical but tried it anyway. It found $200 in overcharges I didn't know about.
(Scene 3: 17-25s) I'm so salty I didn't know about this sooner. They have a free trial if you want it. Link's in my bio.

**Moderate/Surprised Example:**
(Scene 1: 0-8s) I thought I was being smart about my bills but turns out I was completely wrong about it.
(Scene 2: 8-17s) Someone mentioned HealthLock and I was like whatever but tried it. It actually found overcharges I didn't know about.
(Scene 3: 17-25s) Wish I found this months ago honestly. Free trial, no card needed. Check it out if you're curious.

**Strong/Emotional Example (ONE OPTION, NOT DEFAULT):**
(Scene 1: 0-8s) I'm literally in my car right now and I just got another medical bill. I'm so frustrated and upset.
(Scene 2: 8-17s) Someone told me about HealthLock. I was skeptical but tried it anyway. It found $200 in overcharges I didn't know about.
(Scene 3: 17-25s) I'm so salty I didn't know about this sooner. They have a free trial if you want it. Link's in my bio.

CRITICAL: 
- Scene 1 MUST start with PATTERN INTERRUPT (unexpected opening) - VARY emotional intensity (subtle/curious, moderate/surprised, or strong/emotional - NOT always crying/angry)
- Scene 2 shows emotional shift (skepticism → relief)
- Scene 3 has regretful tone ("wish I knew sooner") + COMPLETE CTA (17-20 words to prevent Sora from improvising)
- Each scene MUST end with complete sentence. Scene 3 MUST complete the CTA with NO trailing off.
- Emotions must be VISIBLE and VARIED (curiosity, surprise, mild frustration, relief, regret - not always tears/anger)
- Total: 55-60 words (18-22 / 20-24 / 17-20)

**Audio & Ambience:**
Recorded through iPhone 15 Pro microphone. Clear voice with slight natural room reverb. Minimal background noise. Quiet indoor ambient sound. No music. Authentic smartphone capture quality.

CRITICAL: Generate this detailed format. Make it feel real and authentic while being professionally structured for AI generation."""
        
        try:
            # Build the full prompt with conditional CPA section
            full_prompt = base_script_prompt.replace('{anti_ad_framework}', anti_ad_framework)
            full_prompt = full_prompt.replace('{persona}', persona.get('full_profile', 'UGC Creator'))
            full_prompt = full_prompt.replace('{count}', str(count))
            
            # Add CPA-specific or physical product-specific section
            try:
                if is_cpa:
                    full_prompt = full_prompt.replace('{cpa_specific if is_cpa else physical_product_specific}', cpa_additions)
                else:
                    # Ensure physical_product_additions is defined
                    if 'physical_product_additions' not in locals():
                        raise NameError("physical_product_additions not defined - check code structure")
                    full_prompt = full_prompt.replace('{cpa_specific if is_cpa else physical_product_specific}', physical_product_additions)
            except NameError as e:
                error_msg = f"❌ Variable not defined: {e}"
                print(error_msg)
                logger.error(error_msg)
                # Fallback to empty string if variable missing
                full_prompt = full_prompt.replace('{cpa_specific if is_cpa else physical_product_specific}', '')
            except Exception as e:
                error_msg = f"❌ Error adding product-specific section: {e}"
                print(error_msg)
                logger.error(error_msg)
                import traceback
                traceback.print_exc()
                # Fallback to empty string
                full_prompt = full_prompt.replace('{cpa_specific if is_cpa else physical_product_specific}', '')
            
            # Add product info - CRITICAL: Include actual offer details for CPA
            if is_cpa:
                product_info_json = json.dumps({
                    'name': product.get('name'),
                    'type': 'CPA Offer - SIGN UP/INSTALL/SUBSCRIBE',
                    'offer_url': product.get('offer_url', ''),
                    'what_they_offer': analysis.get('what_they_offer', 'Service/App/Subscription'),
                    'benefits': analysis.get('benefits', []),
                    'target_audience': analysis.get('target_audience', ''),
                    'conversion_action': analysis.get('conversion_action', 'signup'),
                    'offer_type': analysis.get('offer_type', 'free trial'),
                    'payout': product.get('cpa_payout', ''),
                    'description': product.get('description', '')
                }, indent=2)
            else:
                product_info_json = json.dumps({
                    'name': product.get('name'),
                    'type': 'Physical Product',
                    'benefits': analysis.get('benefits', []),
                    'target_audience': analysis.get('target_audience', ''),
                    'description': product.get('description', ''),
                    'price': product.get('price', '')
                }, indent=2)
            
            full_prompt = full_prompt.replace('{product_info}', product_info_json)
            
            # Add explicit instruction for CPA offers
            if is_cpa:
                cpa_instruction = f"""

CRITICAL FOR THIS CPA OFFER:
- This is a {analysis.get('offer_type', 'sign-up')} offer, NOT a physical product
- The offer is: {analysis.get('what_they_offer', product.get('name'))}
- Conversion action: {analysis.get('conversion_action', 'signup')} (NOT purchase)
- Focus on the SERVICE/APP/SUBSCRIPTION, not physical items
- Do NOT mention bottles, products, shipping, or physical delivery
- Focus on: signing up, downloading, trying the service, using the app
- The benefit is the SERVICE itself, not a physical object
"""
                full_prompt += cpa_instruction
            
            formatted_prompt = full_prompt
            
            # Call Gemini 2.5 Pro for script generation
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent',
                    headers={
                        'Content-Type': 'application/json',
                        'x-goog-api-key': self.gemini_api_key
                    },
                    json={
                        'contents': [{
                            'parts': [{'text': formatted_prompt}]
                        }]
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    result = await response.json()
                    
                    if 'error' in result:
                        raise ValueError(f"Gemini API error: {result['error']}")
                    
                    scripts_text = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse out individual scripts
                    # Split by "SCRIPT" markers
                    import re
                    script_sections = re.split(r'SCRIPT\s+[#\d]+:', scripts_text)
                    scripts = [s.strip() for s in script_sections if len(s.strip()) > 100]
                    
                    logger.info(f"✅ Generated {len(scripts)} UGC scripts")
                    return scripts[:count]
        except Exception as e:
            error_msg = f"❌ ugc_sora_service: Error generating scripts: {e}"
            print(error_msg)
            logger.error(error_msg)
            import traceback
            error_details = traceback.format_exc()
            print(f"Full error details:\n{error_details}")
            logger.error(f"Full traceback: {error_details}")
            sys.stdout.flush()
            # Return fallback script
            return [f"Check out {product.get('name', 'this product')}! Link in bio."]
    
    # ========== STEP 4: FIRST FRAME GENERATION ==========
    
    async def generate_first_frame(self, product_image_url: str, script: str) -> str:
        """
        Generate first frame adapted to 720x1280 UGC aesthetic
        Uses Gemini to adapt product image
        Returns: base64 encoded image
        """
        try:
            # Download product image as base64
            async with aiohttp.ClientSession() as session:
                async with session.get(product_image_url) as response:
                    image_bytes = await response.read()
                    product_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Blank 720x1280 reference image (base64)
            blank_reference = "iVBORw0KGgoAAAANSUhEUgAAAkAAAAQACAIAAACGcHE3AAAACXBIWXMAAA7EAAAOxAGVKw4b..."  # Truncated
            
            prompt = """Take the design, layout, and style of [Image A] exactly as it is, and seamlessly adapt it into the aspect ratio of [Image B]. Maintain all the visual elements, proportions, and composition of [Image A], but expand, crop, or extend the background naturally so that the final image perfectly matches the aspect ratio and dimensions of [Image B]. Do not distort or stretch any elements—use intelligent background extension, framing, or subtle composition adjustments to preserve the original design integrity while filling the new canvas size."""
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent',
                    headers={
                        'Content-Type': 'application/json',
                        'x-goog-api-key': self.gemini_api_key
                    },
                    json={
                        'contents': [{
                            'parts': [
                                {'text': prompt},
                                {'inline_data': {'mime_type': 'image/png', 'data': product_base64}},
                                {'inline_data': {'mime_type': 'image/png', 'data': blank_reference}}
                            ]
                        }]
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    # Extract generated image
                    parts = result['candidates'][0]['content']['parts']
                    for part in parts:
                        if 'inlineData' in part:
                            return part['inlineData']['data']
                    
                    # Fallback: return original product image
                    return product_base64
        except Exception as e:
            error_msg = f"❌ ugc_sora_service: Error generating first frame: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            # Return original product image as fallback
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(product_image_url) as response:
                        image_bytes = await response.read()
                        return base64.b64encode(image_bytes).decode('utf-8')
            except:
                return ""
    
    # ========== STEP 5: VEO 3.1 VIDEO GENERATION ==========
    
    async def generate_veo_video(self, prompt: str, avatar_url: Optional[str] = None) -> Dict:
        """
        Generate video using Kie.ai Veo 3.1 (Google DeepMind model)
        
        Benefits over Sora 2 Pro:
        - 75% cheaper (25% of Google pricing)
        - Supports human faces (can use avatar images)
        - Native 9:16 portrait format
        - Built-in audio track
        - Better for authentic UGC
        
        Args:
            prompt: Clean video prompt (dialogue + visual description)
            avatar_url: Optional avatar image URL (uses first frame image-to-video)
        
        Returns:
            {
                'success': bool,
                'video_url': str (local temp path after download),
                'video_id': str (task_id),
                'cost': float
            }
        """
        try:
            print("🎬 Using Kie.ai Veo 3.1 Fast (Google DeepMind)...")
            logger.info("🎬 Using Kie.ai Veo 3.1 Fast...")
            sys.stdout.flush()
            
            # Validate prompt
            if not prompt or len(prompt) < 50:
                raise ValueError(f"Prompt is too short or empty: {len(prompt) if prompt else 0} chars")
            
            # Build request body
            request_body = {
                'model': 'veo3_fast',  # Fast model for cost efficiency
                'prompt': prompt,
                'aspectRatio': '9:16',  # Vertical for TikTok/IG
                'enableTranslation': True  # Auto-translate non-English prompts
            }
            
            # If avatar provided, use image-to-video mode
            if avatar_url:
                request_body['imageUrls'] = [avatar_url]
                request_body['generationType'] = 'FIRST_AND_LAST_FRAMES_2_VIDEO'
                print(f"📸 Using avatar as first frame: {avatar_url[:80]}...")
                logger.info(f"Using avatar image-to-video mode")
            else:
                request_body['generationType'] = 'TEXT_2_VIDEO'
                print("📝 Using text-to-video mode (no avatar)")
                logger.info("Using text-to-video mode")
            
            print(f"📤 Sending to Kie.ai Veo 3.1: Fast model, 9:16 portrait, {request_body['generationType']}")
            logger.info(f"Veo 3.1 request: {request_body['model']}, {request_body['aspectRatio']}, {request_body['generationType']}")
            sys.stdout.flush()
            
            # Submit task
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.kie.ai/api/v1/veo/generate',
                    headers={
                        'Authorization': f'Bearer {self.kie_ai_key}',
                        'Content-Type': 'application/json'
                    },
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    print(f"Veo 3.1 response status: {response_status}")
                    logger.info(f"Veo 3.1 response status: {response_status}")
                    sys.stdout.flush()
                    
                    if response_status != 200:
                        error_detail = f"Veo 3.1 returned status {response_status}: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    try:
                        result = json.loads(response_text)
                    except Exception as e:
                        raise ValueError(f"Veo 3.1 returned invalid JSON: {response_text[:500]}")
                    
                    if result.get('code') != 200:
                        error_msg = result.get('msg', 'Unknown error')
                        print(f"❌ Veo 3.1 error (code {result.get('code')}): {error_msg}")
                        print(f"Full response: {json.dumps(result, indent=2)}")
                        logger.error(f"Veo 3.1 error: {error_msg}")
                        sys.stdout.flush()
                        raise ValueError(f"Veo 3.1 error: {error_msg}")
                    
                    task_id = result.get('data', {}).get('taskId')
                    if not task_id:
                        raise ValueError(f"Veo 3.1 didn't return taskId. Full response: {result}")
                    
                    print(f"✅ Veo 3.1 task created: {task_id}")
                    logger.info(f"Veo 3.1 task created: {task_id}")
                    sys.stdout.flush()
            
            # Veo URLs follow pattern: https://tempfile.aiquickdraw.com/v/{task_id}_{timestamp}.mp4
            # Wait for generation to complete, then download directly
            print("⏳ Waiting for Veo generation (60-90 seconds)...")
            logger.info("Waiting for Veo generation...")
            sys.stdout.flush()
            
            # Wait for video to be ready (Veo takes 60-90s)
            await asyncio.sleep(90)
            
            # Construct direct download URL
            import time
            timestamp = int(time.time())
            # Try current timestamp and a few seconds earlier
            for time_offset in range(0, 120, 10):  # Try timestamps from now to 2 minutes ago
                test_timestamp = timestamp - time_offset
                video_url = f"https://tempfile.aiquickdraw.com/v/{task_id}_{test_timestamp}.mp4"
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(video_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                print(f"✅ Found Veo video at: {video_url[:80]}...")
                                logger.info(f"Found Veo video URL: {video_url}")
                                
                                # Download the video
                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=120)) as download_response:
                                    video_bytes = await download_response.read()
                                    
                                    if not video_bytes or len(video_bytes) == 0:
                                        continue
                                    
                                    video_size_mb = len(video_bytes) / (1024 * 1024)
                                    print(f"✅ Downloaded base video: {video_size_mb:.2f} MB (8 seconds)")
                                    logger.info(f"Downloaded base video: {video_size_mb:.2f} MB")
                                    sys.stdout.flush()
                                    
                                    # Save to temp file
                                    import tempfile
                                    temp_path = tempfile.mktemp(suffix='.mp4')
                                    with open(temp_path, 'wb') as f:
                                        f.write(video_bytes)
                                    
                                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                        continue
                                    
                                    base_result = {
                                        'success': True,
                                        'video_url': temp_path,
                                        'video_id': task_id,
                                        'cost': 0.30,
                                        'duration': 8
                                    }
                                    break
                except:
                    continue
            else:
                raise ValueError("Could not find Veo video URL after 120 seconds")
            
            if not base_result.get('success'):
                return base_result
            
            # Extend to 20 seconds
            print("🎬 Extending to 20 seconds...")
            logger.info("Extending to 20 seconds...")
            sys.stdout.flush()
            
            extended_result = await self.extend_veo_video(task_id, extend_seconds=12)
            
            if extended_result.get('success'):
                # Update cost and duration
                extended_result['cost'] = 0.75  # Base $0.30 + Extend $0.45
                extended_result['duration'] = 20
                print(f"✅ 20-second video ready! Total cost: $0.75")
                logger.info("20-second extended video complete")
                sys.stdout.flush()
            
            return extended_result
                
        except Exception as e:
            error_msg = f"❌ ugc_sora_service: Error in Veo 3.1 generation: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    async def generate_sora_video(self, prompt: str, first_frame_base64: Optional[str] = None) -> Dict:
        """
        Generate video using Kie.ai Sora 2 Pro (single video - authentic UGC feel)
        Uses text-to-video for raw, authentic UGC content
        
        Args:
            prompt: Clean video prompt (dialogue + visual description)
            first_frame_base64: Optional base64 image for first frame
        
        Returns:
            {
                'success': bool,
                'video_url': str (download URL or local path),
                'video_id': str (task_id),
                'cost': float
            }
        """
        try:
            print("🎬 Using Kie.ai Sora 2 Pro (Text-to-Video)...")
            logger.info("🎬 Using Kie.ai Sora 2 Pro (Text-to-Video)...")
            sys.stdout.flush()
            
            # Validate prompt
            if not prompt or len(prompt) < 50:
                raise ValueError(f"Prompt is too short or empty: {len(prompt) if prompt else 0} chars")
            
            # Limit prompt length (kie.ai has limits)
            max_prompt_length = 2000
            if len(prompt) > max_prompt_length:
                print(f"⚠️ Prompt too long ({len(prompt)} chars), truncating to {max_prompt_length}")
                prompt = prompt[:max_prompt_length].rsplit('.', 1)[0] + '.'
            
            print(f"📝 Prompt: {prompt[:200]}... ({len(prompt)} chars)")
            logger.info(f"Prompt: {prompt[:200]}... ({len(prompt)} chars)")
            sys.stdout.flush()
            
            # Determine if we have a product image
            image_url = None
            if first_frame_base64:
                # Upload base64 image to get a public URL for kie.ai
                print("📤 Uploading first frame image to get public URL...")
                logger.info("Uploading first frame image to get public URL")
                sys.stdout.flush()
                image_url = await self._upload_image_to_temp_storage(first_frame_base64)
                
                if image_url:
                    print(f"✅ Image uploaded: {image_url[:80]}...")
                    logger.info(f"Image uploaded: {image_url[:80]}")
                    sys.stdout.flush()
                else:
                    print("⚠️ Failed to upload image, continuing without it")
                    logger.warning("Failed to upload image, continuing without it")
            
            # Build request body - use text-to-video or image-to-video format
            if image_url:
                # Image-to-video model
                model = 'sora-2-pro-image-to-video'
                request_body = {
                    'model': model,
                    'input': {
                        'prompt': prompt,
                        'n_frames': '12',  # 12 seconds
                        'aspect_ratio': 'portrait',  # 9:16 for TikTok/IG
                        'size': 'high',  # High quality
                        'remove_watermark': True,  # No watermark
                        'image_urls': [image_url]  # Product image
                    }
                }
                print(f"📸 Using product image: {image_url[:80]}...")
                logger.info(f"Using product image: {image_url[:80]}")
            else:
                # Text-to-video model
                model = 'sora-2-pro-text-to-video'
                request_body = {
                    'model': model,
                    'input': {
                        'prompt': prompt,
                        'n_frames': '12',  # 12 seconds
                        'aspect_ratio': 'portrait',  # 9:16 for TikTok/IG
                        'size': 'high',  # High quality
                        'remove_watermark': True  # No watermark
                    }
                }
                print("📸 No product image - generating from prompt only")
                logger.info("No product image - generating from prompt only")
            
            model_type = "image-to-video" if image_url else "text-to-video"
            print(f"📤 Sending to Kie.ai: {model_type}, 12s, portrait, high quality, no watermark")
            logger.info(f"Sending to Kie.ai: {model_type}, 12s, portrait, high quality, no watermark")
            sys.stdout.flush()
            
            # Submit task to kie.ai
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.kie.ai/api/v1/jobs/createTask',
                    headers={
                        'Authorization': f'Bearer {self.kie_ai_key}',
                        'Content-Type': 'application/json'
                    },
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    print(f"Kie.ai response status: {response_status}")
                    logger.info(f"Kie.ai response status: {response_status}")
                    sys.stdout.flush()
                    
                    # Handle 500 errors from Kie.ai
                    if response_status == 500:
                        error_detail = f"❌ Kie.ai returned 500 Internal Server Error"
                        print(error_detail)
                        print(f"Response body: {response_text[:1000]}")
                        logger.error(f"Kie.ai 500 error: {response_text[:1000]}")
                        
                        # Try to parse error message
                        try:
                            error_json = json.loads(response_text)
                            error_msg = error_json.get('message') or error_json.get('msg') or error_json.get('error', 'Unknown error')
                            print(f"Error message: {error_msg}")
                            logger.error(f"Kie.ai error message: {error_msg}")
                        except:
                            pass
                        
                        sys.stdout.flush()
                        raise ValueError(f"Kie.ai server error (500): {response_text[:500]}. This is usually temporary - try again in a few minutes.")
                    
                    if response_status != 200:
                        error_detail = f"Kie.ai returned status {response_status}: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    try:
                        result = json.loads(response_text)
                    except Exception as e:
                        raise ValueError(f"Kie.ai returned invalid JSON: {response_text[:500]}")
                    
                    if result.get('code') != 200:
                        error_msg = result.get('message') or result.get('msg') or 'Unknown error'
                        error_detail = result.get('detail') or result.get('error') or ''
                        full_error = f"Kie.ai error (code {result.get('code')}): {error_msg}"
                        if error_detail:
                            full_error += f" - {error_detail}"
                        print(f"❌ {full_error}")
                        print(f"Full response: {json.dumps(result, indent=2)}")
                        logger.error(full_error)
                        logger.error(f"Full response: {json.dumps(result, indent=2)}")
                        sys.stdout.flush()
                        raise ValueError(full_error)
                    
                    task_id = result.get('data', {}).get('taskId')
                    if not task_id:
                        raise ValueError(f"Kie.ai didn't return taskId. Full response: {result}")
                    
                    print(f"✅ Kie.ai task created: {task_id}")
                    logger.info(f"Kie.ai task created: {task_id}")
                    sys.stdout.flush()
            
            # Poll for completion
            return await self._poll_kie_ai_task(task_id, '15')
                
        except Exception as e:
            error_msg = f"❌ ugc_sora_service: Error in Sora 2 generation: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    async def generate_sora_video_storyboard(self, storyboard: Dict, avatar_url: Optional[str] = None) -> Dict:
        """
        Generate video using Sora 2 Pro Storyboard (25 seconds, 3 scenes)
        
        From API docs: https://kie.ai/sora-2-pro-storyboard
        - Supports 10s, 15s, or 25s
        - Multi-scene sequencing
        - Portrait aspect ratio supported
        
        Args:
            storyboard: Dict with 'scenes' array
            first_frame_base64: Optional base64 first frame image
        
        Returns:
            {
                'success': bool,
                'video_url': str (local temp path),
                'video_id': str,
                'cost': float
            }
        """
        try:
            print("🎬 Using Sora 2 Pro Storyboard (25 seconds)...")
            logger.info("Using Sora 2 Pro Storyboard")
            sys.stdout.flush()
            
            # Build shots array from storyboard
            scenes = storyboard.get('scenes', [])
            if not scenes or len(scenes) < 2:
                raise ValueError("Storyboard must have at least 2 scenes")
            
            # Use exact durations from storyboard (already set to 8.3, 9.0, 7.7 = 25.0)
            shots = []
            for scene in scenes[:3]:  # Max 3 scenes
                shots.append({
                    "Scene": scene.get('description', ''),
                    "duration": scene.get('duration', 8.3)
                })
            
            # Verify total duration is exactly 10, 15, or 25
            total_duration = sum(shot['duration'] for shot in shots)
            if total_duration not in [10.0, 15.0, 25.0]:
                print(f"⚠️ Adjusting durations from {total_duration}s to 25s")
                # Adjust last scene to make total exactly 25
                shots[-1]['duration'] = 25.0 - sum(shot['duration'] for shot in shots[:-1])
            
            # Don't use avatar - Sora blocks realistic faces
            # Character description in scenes will guide AI to generate the person
            print("📝 Text-to-video mode (no avatar - Sora limitation)")
            logger.info("Text-to-video mode - no avatar")
            
            # Build request body per API docs
            request_body = {
                "model": "sora-2-pro-storyboard",
                "input": {
                    "n_frames": "25",  # 25 seconds
                    "aspect_ratio": "portrait",  # 9:16 for TikTok/IG
                    "shots": shots
                }
            }
            
            print(f"📤 Sending to Kie.ai: Sora 2 Pro Storyboard, 25s, {len(shots)} scenes, portrait")
            logger.info(f"Sora Storyboard: 25s, {len(shots)} scenes")
            sys.stdout.flush()
            
            # Submit task to Kie.ai
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.kie.ai/api/v1/jobs/createTask',
                    headers={
                        'Authorization': f'Bearer {self.kie_ai_key}',
                        'Content-Type': 'application/json'
                    },
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    print(f"Sora Storyboard response status: {response_status}")
                    logger.info(f"Sora Storyboard response status: {response_status}")
                    sys.stdout.flush()
                    
                    # Handle 500 errors from Kie.ai
                    if response_status == 500:
                        error_detail = f"❌ Kie.ai returned 500 Internal Server Error"
                        print(error_detail)
                        print(f"Response body: {response_text[:1000]}")
                        logger.error(f"Kie.ai 500 error: {response_text[:1000]}")
                        
                        # Try to parse error message
                        try:
                            error_json = json.loads(response_text)
                            error_msg = error_json.get('message') or error_json.get('msg') or error_json.get('error', 'Unknown error')
                            print(f"Error message: {error_msg}")
                            logger.error(f"Kie.ai error message: {error_msg}")
                        except:
                            pass
                        
                        sys.stdout.flush()
                        raise ValueError(f"Kie.ai server error (500): {response_text[:500]}. This is usually temporary - try again in a few minutes.")
                    
                    if response_status != 200:
                        error_detail = f"Sora Storyboard returned status {response_status}: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    # Try to parse JSON response
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        error_msg = f"Kie.ai returned invalid JSON: {response_text[:500]}"
                        print(f"❌ {error_msg}")
                        logger.error(error_msg)
                        sys.stdout.flush()
                        raise ValueError(error_msg)
                    
                    if result.get('code') != 200:
                        error_msg = result.get('msg') or result.get('message') or 'Unknown error'
                        error_detail = result.get('detail') or result.get('error') or ''
                        print(f"❌ Sora Storyboard error (code {result.get('code')}): {error_msg}")
                        if error_detail:
                            print(f"Error detail: {error_detail}")
                        print(f"Full response: {json.dumps(result, indent=2)}")
                        logger.error(f"Sora Storyboard error: {error_msg} - {error_detail}")
                        sys.stdout.flush()
                        raise ValueError(f"Sora Storyboard error: {error_msg}")
                    
                    task_id = result.get('data', {}).get('taskId')
                    if not task_id:
                        raise ValueError(f"Sora Storyboard didn't return taskId")
                    
                    print(f"✅ Sora Storyboard task created: {task_id}")
                    logger.info(f"Sora Storyboard task created: {task_id}")
                    sys.stdout.flush()
            
            # Kie.ai polling is broken - use direct URL construction
            print("⏳ Waiting for Sora Storyboard generation (120-180 seconds for 25s video)...")
            logger.info("Waiting for Sora Storyboard generation...")
            sys.stdout.flush()
            
            # Wait longer for storyboard (3 scenes takes more time)
            await asyncio.sleep(150)  # 2.5 minutes
            
            # Try to construct direct download URL (same pattern as Veo)
            import time
            timestamp = int(time.time())
            
            for time_offset in range(0, 180, 10):  # Try 3 minutes worth of timestamps
                test_timestamp = timestamp - time_offset
                video_url = f"https://tempfile.aiquickdraw.com/v/{task_id}_{test_timestamp}.mp4"
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(video_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                print(f"✅ Found Sora video at: {video_url[:80]}...")
                                logger.info(f"Found Sora video URL: {video_url}")
                                
                                # Download the video
                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=180)) as download_response:
                                    video_bytes = await download_response.read()
                                    
                                    if not video_bytes or len(video_bytes) == 0:
                                        continue
                                    
                                    video_size_mb = len(video_bytes) / (1024 * 1024)
                                    print(f"✅ Downloaded Sora Storyboard video: {video_size_mb:.2f} MB (25 seconds)")
                                    logger.info(f"Downloaded Sora video: {video_size_mb:.2f} MB")
                                    sys.stdout.flush()
                                    
                                    # Save to temp file
                                    import tempfile
                                    temp_path = tempfile.mktemp(suffix='.mp4')
                                    with open(temp_path, 'wb') as f:
                                        f.write(video_bytes)
                                    
                                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                        continue
                                    
                                    print(f"✅ 25-second video ready! Cost: $1.35")
                                    logger.info("25-second Sora Storyboard complete")
                                    sys.stdout.flush()
                                    
                                    return {
                                        'success': True,
                                        'video_url': temp_path,
                                        'video_id': task_id,
                                        'cost': 1.35,
                                        'duration': 25
                                    }
                except:
                    continue
            
            # If direct URL didn't work, try callback/polling as fallback
            return await self._poll_kie_ai_task(task_id, '25')
                
        except Exception as e:
            error_msg = f"❌ Error in Sora Storyboard generation: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    async def extend_veo_video(self, base_task_id: str, extend_seconds: int = 12) -> Dict:
        """
        Extend Veo 3.1 video beyond 8 seconds
        
        Args:
            base_task_id: Task ID from base video generation
            extend_seconds: Seconds to add (default 12 for total 20s)
        
        Returns:
            Extended video result dict
        """
        try:
            print(f"⏱️ Extending video by {extend_seconds}s...")
            logger.info(f"Extending Veo video by {extend_seconds}s")
            sys.stdout.flush()
            
            # Submit extend task
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.kie.ai/api/v1/veo/extend',
                    headers={
                        'Authorization': f'Bearer {self.kie_ai_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'taskId': base_task_id,
                        'extendDuration': extend_seconds
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    print(f"Veo Extend response status: {response_status}")
                    logger.info(f"Veo Extend response status: {response_status}")
                    sys.stdout.flush()
                    
                    if response_status != 200:
                        error_detail = f"Veo Extend returned status {response_status}: {response_text[:500]}"
                        print(f"❌ {error_detail}")
                        logger.error(error_detail)
                        sys.stdout.flush()
                        raise ValueError(error_detail)
                    
                    result = json.loads(response_text)
                    
                    if result.get('code') != 200:
                        error_msg = result.get('msg', 'Unknown error')
                        print(f"❌ Veo Extend error: {error_msg}")
                        logger.error(f"Veo Extend error: {error_msg}")
                        sys.stdout.flush()
                        raise ValueError(f"Veo Extend error: {error_msg}")
                    
                    extend_task_id = result.get('data', {}).get('taskId')
                    if not extend_task_id:
                        raise ValueError(f"Veo Extend didn't return taskId")
                    
                    print(f"✅ Veo Extend task created: {extend_task_id}")
                    logger.info(f"Veo Extend task created: {extend_task_id}")
                    sys.stdout.flush()
            
            # Poll for extended video
            return await self._poll_veo_task(extend_task_id, is_extended=True)
                
        except Exception as e:
            error_msg = f"Error extending Veo video: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _poll_veo_task(self, task_id: str, is_extended: bool = False) -> Dict:
        """Poll Veo 3.1 task until completion (similar to Sora polling)"""
        try:
            max_polls = 120  # 20 minutes max
            poll_interval = 10  # Check every 10 seconds
            
            print(f"⏳ Polling Veo 3.1 task {task_id} (checking every {poll_interval}s)...")
            sys.stdout.flush()
            
            for attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                try:
                    async with aiohttp.ClientSession() as session:
                        # Try multiple Veo status endpoints
                        endpoints = [
                            f'https://api.kie.ai/api/v1/veo/{task_id}',
                            f'https://api.kie.ai/v1/veo/details/{task_id}',
                            f'https://api.kie.ai/api/v1/jobs/queryTask?taskId={task_id}',
                            f'https://api.kie.ai/api/v1/jobs/{task_id}'
                        ]
                        
                        result = None
                        for endpoint in endpoints:
                            try:
                                async with session.get(
                                    endpoint,
                                    headers={
                                        'Authorization': f'Bearer {self.kie_ai_key}',
                                        'Accept': 'application/json'
                                    },
                                    timeout=aiohttp.ClientTimeout(total=30)
                                ) as response:
                                    if response.status == 200:
                                        result = await response.json()
                                        if attempt == 0:  # First successful call
                                            print(f"✅ Found working Veo endpoint: {endpoint}")
                                            logger.info(f"Found working Veo endpoint: {endpoint}")
                                        break
                            except Exception:
                                continue
                        
                        if not result:
                            print(f"⚠️ All Veo endpoints returned errors on attempt {attempt+1}")
                            continue
                        
                        if result.get('code') != 200:
                            print(f"⚠️ Veo status error: {result.get('message')}")
                            continue
                        
                        data = result.get('data', {})
                        state = data.get('state')
                        
                        print(f"📊 Veo 3.1 status {attempt+1}/{max_polls}: {state}")
                        logger.info(f"Veo 3.1 status {attempt+1}/{max_polls}: {state}")
                        sys.stdout.flush()
                        
                        if state == 'success':
                            # Extract video URL
                            result_json_str = data.get('resultJson', '{}')
                            result_json = json.loads(result_json_str)
                            video_urls = result_json.get('resultUrls', [])
                            
                            if not video_urls:
                                raise ValueError("No video URLs in Veo result")
                            
                            video_url = video_urls[0]
                            print(f"✅ Veo 3.1 video generated: {video_url[:100]}...")
                            logger.info(f"Veo 3.1 video URL: {video_url}")
                            sys.stdout.flush()
                            
                            # Download video
                            async with aiohttp.ClientSession() as download_session:
                                async with download_session.get(video_url, timeout=aiohttp.ClientTimeout(total=120)) as video_response:
                                    video_bytes = await video_response.read()
                                    
                                    # Verify download
                                    if not video_bytes or len(video_bytes) == 0:
                                        raise ValueError("Downloaded video is empty")
                                    
                                    video_size_mb = len(video_bytes) / (1024 * 1024)
                                    print(f"✅ Downloaded Veo video: {video_size_mb:.2f} MB")
                                    logger.info(f"Downloaded Veo video: {video_size_mb:.2f} MB")
                                    sys.stdout.flush()
                                    
                                    # Save to temp file
                                    import tempfile
                                    temp_path = tempfile.mktemp(suffix='.mp4')
                                    with open(temp_path, 'wb') as f:
                                        f.write(video_bytes)
                                    
                                    # Verify save
                                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                        raise ValueError("Failed to save video to temp file")
                                    
                                    print(f"✅ Saved to temp: {temp_path} ({video_size_mb:.2f} MB)")
                                    sys.stdout.flush()
                                    
                                    # Return video
                                    duration = 20 if is_extended else 8
                                    cost = 0.75 if is_extended else 0.30
                                    
                                    return {
                                        'success': True,
                                        'video_url': temp_path,
                                        'video_id': task_id,
                                        'cost': cost,
                                        'duration': duration
                                    }
                        
                        elif state == 'fail':
                            fail_msg = data.get('failMsg', 'Unknown error')
                            raise ValueError(f"Veo 3.1 failed: {fail_msg}")
                
                except Exception as poll_error:
                    print(f"⚠️ Error polling Veo: {poll_error}")
                    continue
            
            # Timeout
            raise TimeoutError("Veo 3.1 generation timed out after 20 minutes")
            
        except Exception as e:
            logger.error(f"Error polling Veo task: {e}")
            raise
    
    async def _upload_image_to_temp_storage(self, base64_image: str) -> Optional[str]:
        """
        Upload base64 image to Google Drive and return public URL
        Uses the same Drive service as video uploads
        """
        try:
            from utils.ai_utils import get_drive_service
            from googleapiclient.http import MediaIoBaseUpload
            import io
            import base64 as b64
            
            # Decode base64
            image_bytes = b64.b64decode(base64_image)
            
            # Get Drive service
            drive_service = get_drive_service()
            
            # Create file metadata
            file_metadata = {
                'name': f'UGC_ProductFrame_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.png',
                'mimeType': 'image/png'
            }
            
            # Create media upload
            media = MediaIoBaseUpload(
                io.BytesIO(image_bytes),
                mimetype='image/png',
                resumable=True
            )
            
            # Upload file
            file = await asyncio.to_thread(
                drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink,webContentLink'
                ).execute()  # FIXED: Added parentheses
            )
            
            # Make publicly accessible
            await asyncio.to_thread(
                drive_service.permissions().create(
                    fileId=file['id'],
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()  # FIXED: Added parentheses
            )
            
            # Return webContentLink (direct download URL) - better for APIs
            image_url = file.get('webContentLink') or file.get('webViewLink')
            print(f"✅ Uploaded product image to Drive: {image_url[:80]}...")
            logger.info(f"✅ Uploaded product image to Drive: {image_url}")
            sys.stdout.flush()
            return image_url
            
        except Exception as e:
            error_msg = f"Error uploading image to Drive: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return None
    
    async def _poll_kie_ai_task(self, task_id: str, duration: str) -> Dict:
        """Poll kie.ai task until completion"""
        try:
            max_polls = 120  # 20 minutes max (15s video takes ~2-5 min)
            poll_interval = 10  # Check every 10 seconds
            
            print(f"⏳ Polling Kie.ai task {task_id} (checking every {poll_interval}s, max {max_polls} attempts)...")
            sys.stdout.flush()
            
            for attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                try:
                    async with aiohttp.ClientSession() as session:
                        # Try primary endpoint
                        query_url = f'https://api.kie.ai/api/v1/jobs/queryTask?taskId={task_id}'
                        
                        try:
                            async with session.get(
                                query_url,
                                headers={
                                    'Authorization': f'Bearer {self.kie_ai_key}',
                                    'Accept': 'application/json'
                                },
                                timeout=aiohttp.ClientTimeout(total=30)
                            ) as response:
                                response_text = await response.text()
                                
                                if response.status == 404:
                                    # Try alternative endpoint formats
                                    alt_urls = [
                                        f'https://api.kie.ai/api/v1/jobs/{task_id}',
                                        f'https://api.kie.ai/api/v1/tasks/{task_id}',
                                        f'https://api.kie.ai/api/v1/jobs/status?taskId={task_id}'
                                    ]
                                    
                                    for alt_url in alt_urls:
                                        try:
                                            async with session.get(
                                                alt_url,
                                                headers={
                                                    'Authorization': f'Bearer {self.kie_ai_key}',
                                                    'Accept': 'application/json'
                                                },
                                                timeout=aiohttp.ClientTimeout(total=30)
                                            ) as alt_response:
                                                if alt_response.status == 200:
                                                    result = await alt_response.json()
                                                    print(f"✅ Found working endpoint: {alt_url}")
                                                    logger.info(f"Found working endpoint: {alt_url}")
                                                    break
                                        except Exception as alt_e:
                                            continue
                                    else:
                                        # All endpoints failed
                                        warning_msg = f"⚠️ All Kie.ai endpoints returned 404. Response: {response_text[:200]}"
                                        print(warning_msg)
                                        logger.warning(warning_msg)
                                        sys.stdout.flush()
                                        continue
                                elif response.status != 200:
                                    warning_msg = f"⚠️ Kie.ai status check failed: {response.status} - {response_text[:200]}"
                                    print(warning_msg)
                                    logger.warning(warning_msg)
                                    sys.stdout.flush()
                                    continue
                                else:
                                    result = await response.json()
                                
                                if result.get('code') != 200:
                                    warning_msg = f"⚠️ Kie.ai status check error: {result.get('message')}"
                                    print(warning_msg)
                                    logger.warning(warning_msg)
                                    sys.stdout.flush()
                                    continue
                                
                                data = result.get('data', {})
                                state = data.get('state')
                                
                                print(f"📊 Kie.ai status {attempt+1}/{max_polls}: {state}")
                                logger.info(f"Kie.ai status {attempt+1}/{max_polls}: {state}")
                                sys.stdout.flush()
                                
                                if state == 'success':
                                    # Extract video URL
                                    result_json_str = data.get('resultJson', '{}')
                                    try:
                                        result_json = json.loads(result_json_str)
                                        video_urls = result_json.get('resultUrls', [])
                                        if not video_urls:
                                            raise ValueError("No video URLs in result")
                                        
                                        video_url = video_urls[0]
                                        print(f"✅ Kie.ai video generated: {video_url[:100]}...")
                                        logger.info(f"Kie.ai video generated: {video_url}")
                                        sys.stdout.flush()
                                        
                                        # Download video
                                        async with aiohttp.ClientSession() as download_session:
                                            async with download_session.get(video_url, timeout=aiohttp.ClientTimeout(total=120)) as video_response:
                                                video_bytes = await video_response.read()
                                                
                                                # Verify video was downloaded
                                                if not video_bytes or len(video_bytes) == 0:
                                                    raise ValueError("Downloaded video is empty")
                                                
                                                video_size_mb = len(video_bytes) / (1024 * 1024)
                                                print(f"✅ Downloaded video: {video_size_mb:.2f} MB")
                                                logger.info(f"Downloaded video: {video_size_mb:.2f} MB")
                                                sys.stdout.flush()
                                                
                                                # Save temporarily
                                                import tempfile
                                                temp_path = tempfile.mktemp(suffix='.mp4')
                                                with open(temp_path, 'wb') as f:
                                                    f.write(video_bytes)
                                                
                                                # Verify temp file was written correctly
                                                if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                                    raise ValueError("Failed to save video to temp file")
                                                
                                                print(f"✅ Saved to temp file: {temp_path} ({video_size_mb:.2f} MB)")
                                                logger.info(f"Saved to temp file: {temp_path}")
                                                sys.stdout.flush()
                                                
                                                # Calculate cost: Sora 2 Pro Storyboard 25s
                                                cost = 1.35  # Sora 2 Pro Storyboard for 25s
                                                
                                                return {
                                                    'success': True,
                                                    'video_url': temp_path,
                                                    'video_id': task_id,
                                                    'cost': cost,
                                                    'duration': 25
                                                }
                                    except Exception as e:
                                        raise ValueError(f"Failed to extract video URL: {e}")
                                
                                elif state == 'fail':
                                    fail_msg = data.get('failMsg', 'Unknown error')
                                    fail_code = data.get('failCode', '')
                                    raise ValueError(f"Kie.ai generation failed ({fail_code}): {fail_msg}")
                        
                        except aiohttp.ClientConnectorDNSError as dns_error:
                            # DNS/network error - retry with exponential backoff
                            if attempt < 10:  # Retry first 10 times for DNS errors
                                wait_time = min(poll_interval * (1.5 ** min(attempt, 5)), 60)
                                warning_msg = f"⚠️ DNS error (attempt {attempt+1}/10), retrying in {wait_time:.0f}s..."
                                print(warning_msg)
                                logger.warning(warning_msg)
                                sys.stdout.flush()
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                raise ValueError(f"Kie.ai DNS resolution failed after 10 attempts: {dns_error}")
                        
                        except Exception as poll_error:
                            warning_msg = f"⚠️ Error polling Kie.ai: {poll_error}"
                            print(warning_msg)
                            logger.warning(warning_msg)
                            sys.stdout.flush()
                            # Continue to next attempt
                            continue
                
                except Exception as outer_error:
                    warning_msg = f"⚠️ Outer error in polling loop: {outer_error}"
                    print(warning_msg)
                    logger.warning(warning_msg)
                    sys.stdout.flush()
                    continue
            
            # Timeout
            raise TimeoutError("Kie.ai generation timed out after 20 minutes")
            
        except Exception as e:
            logger.error(f"Error polling Kie.ai task: {e}")
            raise
    
    async def _generate_via_defapi(self, script: str, first_frame_base64: Optional[str] = None) -> Dict:
        """Generate video using DefAPI Sora 2 Pro"""
        try:
            print("🚀 Using DefAPI Sora 2 Pro...")
            logger.info("🚀 Using DefAPI Sora 2 Pro...")
            sys.stdout.flush()
            
            # DefAPI constraints: prompt max 4000 chars, duration must be "10", "15", or "25"
            # Truncate script if too long
            max_prompt_length = 4000
            if len(script) > max_prompt_length:
                warning_msg = f"⚠️ Script too long ({len(script)} chars), truncating to {max_prompt_length} chars"
                print(warning_msg)
                logger.warning(warning_msg)
                sys.stdout.flush()
                script = script[:max_prompt_length].rsplit('.', 1)[0] + '.'  # Try to end at sentence boundary
            
            # Step 1: Submit generation job
            request_body = {
                'model': 'sora-2-pro',  # Use Pro model for better quality
                'prompt': script,
                'duration': '15',  # DefAPI supports "10", "15", or "25" (Pro supports 25)
                'aspect_ratio': '9:16'  # Vertical format for TikTok/IG
            }
            
            # Add first frame if provided
            # Note: DefAPI expects image URLs, not base64. For now, skip first frame or upload to temp storage first
            # TODO: Upload first_frame_base64 to temp storage (e.g., Imgur, Cloudinary) and use URL
            if first_frame_base64:
                # Try data URI format - if this doesn't work, we'll need to upload to a URL first
                # Some APIs accept data URIs, let's try it
                image_data_uri = f"data:image/png;base64,{first_frame_base64}"
                request_body['images'] = [image_data_uri]
                print(f"📸 Using first frame (base64 data URI, {len(first_frame_base64)} bytes)")
                logger.info(f"📸 Using first frame (base64 data URI, {len(first_frame_base64)} bytes)")
                sys.stdout.flush()
            else:
                print("📸 No first frame provided - generating from prompt only")
                logger.info("📸 No first frame provided - generating from prompt only")
                sys.stdout.flush()
            
            send_msg = f"📤 Sending to DefAPI: prompt length={len(script)}/{max_prompt_length}, duration=15s, has_image={bool(first_frame_base64)}"
            print(send_msg)
            logger.info(send_msg)
            sys.stdout.flush()
            
            # Debug: Show exact key format being used (first/last 8 chars for security)
            key_debug = f"{self.defapi_key[:8]}...{self.defapi_key[-8:]}" if len(self.defapi_key) > 16 else self.defapi_key
            auth_header = f'Bearer {self.defapi_key}'
            print(f"🔑 DefAPI Key Debug: {key_debug} (length: {len(self.defapi_key)})")
            print(f"🔑 Authorization header: Bearer {key_debug}")
            logger.info(f"DefAPI key format: {key_debug} (length: {len(self.defapi_key)})")
            logger.info(f"Authorization header format: Bearer {key_debug}")
            sys.stdout.flush()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.defapi.org/api/sora2/gen',
                    headers={
                        'Authorization': auth_header,
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    status_msg = f"DefAPI response status: {response.status}"
                    print(status_msg)
                    logger.info(status_msg)
                    sys.stdout.flush()
                    
                    response_text = await response.text()
                    response_preview = f"DefAPI raw response: {response_text[:500]}"
                    print(response_preview)
                    logger.info(response_preview)
                    sys.stdout.flush()
                    
                    if response.status == 401:
                        try:
                            error_data = json.loads(response_text) if response_text else {}
                        except:
                            error_data = {}
                        error_code = error_data.get('code', '')
                        error_msg = error_data.get('message', 'Invalid API key')
                        
                        # Show key preview for debugging
                        key_preview = f"{self.defapi_key[:8]}...{self.defapi_key[-8:]}" if len(self.defapi_key) > 16 else self.defapi_key
                        key_length = len(self.defapi_key)
                        key_starts_with = self.defapi_key[:3] if len(self.defapi_key) >= 3 else ""
                        
                        print(f"❌ DefAPI 401 Error Details:")
                        print(f"   Error Code: {error_code}")
                        print(f"   Error Message: {error_msg}")
                        print(f"   Key Preview: {key_preview}")
                        print(f"   Key Length: {key_length} characters")
                        print(f"   Key Starts With: '{key_starts_with}'")
                        print(f"   Expected Format: 'dk-XXXXXXXX' (Bearer dk-XXXXXXXX)")
                        print(f"   Authorization Header Sent: 'Bearer {key_preview}'")
                        print(f"   💡 TROUBLESHOOTING:")
                        print(f"      1. Check if key has 'dk-' prefix: {self.defapi_key.startswith('dk-')}")
                        print(f"      2. Verify key is active in DefAPI dashboard")
                        print(f"      3. Check if account has credits")
                        print(f"      4. Try copying key directly from DefAPI dashboard")
                        
                        full_error = f"DefAPI authentication failed (code {error_code}): {error_msg}. Key: {key_preview} (length: {key_length}, starts with: '{key_starts_with}'). Verify key format is 'dk-XXXXXXXX' and has credits."
                        logger.error(full_error)
                        sys.stdout.flush()
                        
                        # Don't raise - let the caller handle fallback
                        # Return error result instead
                        return {
                            'success': False,
                            'error': full_error
                        }
                    
                    if response.status != 200:
                        raise ValueError(f"DefAPI returned status {response.status}: {response_text}")
                    
                    try:
                        result = json.loads(response_text)
                    except Exception as e:
                        raise ValueError(f"DefAPI returned invalid JSON: {response_text[:500]}")
                    
                    if result.get('code') != 0:
                        error_msg = result.get('message', 'Unknown error')
                        raise ValueError(f"DefAPI error: {error_msg}")
                    
                    task_id = result.get('data', {}).get('task_id')
                    if not task_id:
                        raise ValueError(f"DefAPI didn't return task_id. Full response: {result}")
                    
                    submit_msg = f"✅ DefAPI job submitted: {task_id}"
                    print(submit_msg)
                    logger.info(submit_msg)
                    sys.stdout.flush()
            
            # Step 2: Poll for completion (every 10 seconds, max 10 minutes)
            max_polls = 60  # 10 minutes
            poll_interval = 10
            
            print(f"⏳ Polling DefAPI for completion (checking every {poll_interval}s, max {max_polls} attempts)...")
            sys.stdout.flush()
            
            for attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.defapi.org/api/task/query?task_id={task_id}',
                        headers={
                            'Authorization': f'Bearer {self.defapi_key}',
                            'Accept': 'application/json'
                        },
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status != 200:
                            warning_msg = f"⚠️ DefAPI status check failed: {response.status}"
                            print(warning_msg)
                            logger.warning(warning_msg)
                            sys.stdout.flush()
                            continue
                        
                        status_result = await response.json()
                        
                        if status_result.get('code') != 0:
                            warning_msg = f"⚠️ DefAPI status check error: {status_result.get('message')}"
                            print(warning_msg)
                            logger.warning(warning_msg)
                            sys.stdout.flush()
                            continue
                        
                        data = status_result.get('data', {})
                        status = data.get('status')
                        progress = data.get('progress', 'N/A')
                        
                        status_msg = f"📊 DefAPI status check {attempt+1}/{max_polls}: {status} (progress: {progress})"
                        print(status_msg)
                        logger.info(status_msg)
                        sys.stdout.flush()
                        
                        if status == 'completed':
                            # Extract video URL
                            result_data = data.get('result')
                            if not result_data:
                                raise ValueError("DefAPI task completed but no result data")
                            
                            video_url = result_data.get('video')
                            if not video_url:
                                raise ValueError("DefAPI result missing video URL")
                            
                            success_msg = f"✅ DefAPI video generated: {video_url[:100]}..."
                            print(success_msg)
                            logger.info(success_msg)
                            sys.stdout.flush()
                            
                            # Download video if it's a URL
                            if video_url.startswith('http'):
                                async with aiohttp.ClientSession() as download_session:
                                    async with download_session.get(video_url, timeout=aiohttp.ClientTimeout(total=120)) as video_response:
                                        video_bytes = await video_response.read()
                                        
                                        # Save temporarily
                                        import tempfile
                                        temp_path = tempfile.mktemp(suffix='.mp4')
                                        with open(temp_path, 'wb') as f:
                                            f.write(video_bytes)
                                        
                                        return {
                                            'success': True,
                                            'video_url': temp_path,
                                            'video_id': task_id,
                                            'cost': 0.9  # DefAPI pricing
                                        }
                            else:
                                # Base64 video - decode and save
                                import tempfile
                                if video_url.startswith('data:video'):
                                    # Extract base64 part
                                    base64_data = video_url.split(',')[1]
                                else:
                                    base64_data = video_url
                                
                                video_bytes = base64.b64decode(base64_data)
                                temp_path = tempfile.mktemp(suffix='.mp4')
                                with open(temp_path, 'wb') as f:
                                    f.write(video_bytes)
                                
                                return {
                                    'success': True,
                                    'video_url': temp_path,
                                    'video_id': task_id,
                                    'cost': 0.9
                                }
                        
                        elif status == 'failed' or status == 'error':
                            error_msg = data.get('status_reason', {}).get('message', 'Unknown error')
                            raise ValueError(f"DefAPI generation failed: {error_msg}")
            
            # Timeout
            raise TimeoutError("DefAPI generation timed out after 10 minutes")
            
        except Exception as e:
            error_msg = f"❌ ugc_sora_service: Error in DefAPI generation: {e}"
            print(error_msg)
            logger.error(error_msg)
            sys.stdout.flush()
            raise
    
    async def _generate_via_openai(self, script: str, first_frame_base64: Optional[str] = None) -> Dict:
        """Generate video using OpenAI Sora 2 (fallback)"""
        try:
            logger.info("🔄 Using OpenAI Sora 2 (fallback)...")
            
            # Step 1: Submit video generation job
            async with aiohttp.ClientSession() as session:
                request_body = {
                    'prompt': script,
                    'model': 'sora-2',
                    'size': '720x1280',
                    'seconds': '12'  # Must be string: '4', '8', or '12'
                }
                
                # Add first frame if provided (multipart/form-data for OpenAI)
                if first_frame_base64:
                    # For OpenAI, we'd need to use multipart/form-data
                    # For now, skip first frame with OpenAI
                    logger.warning("First frame not supported with OpenAI direct API (use DefAPI)")
                
                logger.info(f"📤 Sending to OpenAI Sora 2: {json.dumps(request_body, indent=2)[:300]}...")
                
                async with session.post(
                    'https://api.openai.com/v1/videos',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    logger.info(f"OpenAI response status: {response.status}")
                    
                    response_text = await response.text()
                    logger.info(f"OpenAI raw response: {response_text[:1000]}")
                    
                    if response.status != 200:
                        raise ValueError(f"OpenAI API returned status {response.status}: {response_text}")
                    
                    try:
                        result = json.loads(response_text)
                    except Exception as e:
                        raise ValueError(f"OpenAI returned invalid JSON: {response_text[:500]}")
                    
                    if not result or not isinstance(result, dict):
                        raise ValueError(f"OpenAI returned invalid result type: {type(result)}")
                    
                    if 'error' in result:
                        error_obj = result.get('error')
                        if error_obj:
                            if isinstance(error_obj, dict):
                                error_msg = error_obj.get('message', str(error_obj))
                            else:
                                error_msg = str(error_obj)
                        else:
                            error_msg = "Unknown error from OpenAI"
                        logger.error(f"OpenAI error object: {result.get('error')}")
                        raise ValueError(f"OpenAI API error: {error_msg}")
                    
                    video_id = result.get('id')
                    if not video_id:
                        raise ValueError(f"OpenAI didn't return video ID. Full response: {result}")
                    
                    logger.info(f"✅ OpenAI job submitted: {video_id}")
            
            # Step 2: Poll for completion (every 15 seconds, max 10 minutes)
            max_polls = 40  # 10 minutes
            poll_interval = 15
            
            for attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.openai.com/v1/videos/{video_id}',
                        headers={'Authorization': f'Bearer {self.openai_api_key}'},
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        status_result = await response.json()
                        status = status_result.get('status')
                        
                        logger.info(f"OpenAI status check {attempt+1}/{max_polls}: {status}")
                        
                        if status == 'completed':
                            # Download the video
                            async with session.get(
                                f'https://api.openai.com/v1/videos/{video_id}/content',
                                headers={'Authorization': f'Bearer {self.openai_api_key}'},
                                timeout=aiohttp.ClientTimeout(total=120)
                            ) as video_response:
                                video_bytes = await video_response.read()
                                
                                # Save temporarily
                                import tempfile
                                temp_path = tempfile.mktemp(suffix='.mp4')
                                with open(temp_path, 'wb') as f:
                                    f.write(video_bytes)
                                
                                logger.info(f"✅ OpenAI video generated successfully")
                                
                                return {
                                    'success': True,
                                    'video_url': temp_path,
                                    'video_id': video_id,
                                    'cost': 1.0  # Approx cost per 12s video
                                }
                        
                        elif status == 'failed' or status == 'error':
                            raise ValueError(f"OpenAI generation failed: {status_result.get('error')}")
            
            # Timeout
            raise TimeoutError("OpenAI generation timed out after 10 minutes")
            
        except Exception as e:
            logger.error(f"Error in OpenAI generation: {e}")
            raise
    
    # ========== STEP 6: GOOGLE DRIVE UPLOAD ==========
    
    async def upload_to_drive(self, video_path: str, filename: str) -> Dict:
        """Upload generated video to Google Drive"""
        try:
            # 1. Verify file exists
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # 2. Check file size
            file_size = os.path.getsize(video_path)
            if file_size == 0:
                raise ValueError(f"Video file is empty: {video_path}")
            
            file_size_mb = file_size / (1024 * 1024)
            print(f"📤 Uploading {file_size_mb:.2f} MB to Drive...")
            logger.info(f"Uploading {file_size_mb:.2f} MB to Drive...")
            sys.stdout.flush()
            
            from utils.ai_utils import get_drive_service
            from googleapiclient.http import MediaFileUpload
            
            drive_service = get_drive_service()
            if not drive_service:
                raise ValueError("Failed to initialize Drive service")
            
            file_metadata = {
                'name': f'{filename}.mp4',
                'mimeType': 'video/mp4'
            }
            
            # 3. Add chunksize for large files (128MB chunks)
            media = MediaFileUpload(
                video_path, 
                mimetype='video/mp4', 
                resumable=True,
                chunksize=128 * 1024 * 1024
            )
            
            # 4. Add retry logic
            max_retries = 3
            file = None
            last_error = None
            
            for retry in range(max_retries):
                try:
                    print(f"Drive upload attempt {retry + 1}/{max_retries}")
                    logger.info(f"Drive upload attempt {retry + 1}/{max_retries}")
                    sys.stdout.flush()
                    
                    # FIX: Add () to actually call execute
                    file = await asyncio.to_thread(
                        drive_service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id,webViewLink,webContentLink'
                        ).execute()  # FIXED: Added parentheses
                    )
                    
                    print(f"✅ Drive upload successful! File ID: {file['id']}")
                    logger.info(f"Drive upload successful! File ID: {file['id']}")
                    sys.stdout.flush()
                    break
                    
                except Exception as e:
                    last_error = e
                    print(f"⚠️ Drive upload attempt {retry + 1} failed: {e}")
                    logger.warning(f"Drive upload attempt {retry + 1} failed: {e}")
                    sys.stdout.flush()
                    
                    if retry < max_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise ValueError(f"Drive upload failed after {max_retries} attempts: {last_error}")
            
            # 5. Make publicly accessible (also fix .execute)
            await asyncio.to_thread(
                drive_service.permissions().create(
                    fileId=file['id'],
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()  # FIXED: Added parentheses
            )
            
            logger.info(f"✅ Uploaded to Google Drive: {file['webViewLink']}")
            
            # Clean up temp file
            try:
                os.unlink(video_path)
            except:
                pass
            
            return file
            
        except Exception as e:
            logger.error(f"Error uploading to Drive: {e}")
            import traceback
            traceback.print_exc()
            raise


# Create singleton instance
ugc_sora_service = UGCSoraService()

