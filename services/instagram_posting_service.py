"""
Instagram Content Posting Service
Handles OAuth, video/carousel uploads, and posting to Instagram via Graph API
"""

import aiohttp
import asyncio
import logging
import json
import os
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class InstagramPostingService:
    """
    Service for posting videos and carousels to Instagram using Graph API
    Supports both Reels and Feed posts
    """
    
    def __init__(self):
        self.app_id = os.getenv('INSTAGRAM_APP_ID')
        self.app_secret = os.getenv('INSTAGRAM_APP_SECRET')
        self.redirect_uri = os.getenv('INSTAGRAM_REDIRECT_URI', 'http://127.0.0.1:5000/auth/instagram/callback')
        
        print(f"🔑 Instagram Service initialized - App ID: {'✅ SET' if self.app_id else '❌ NOT SET'}")
        logger.info(f"Instagram Service initialized - App ID: {'SET' if self.app_id else 'NOT SET'}")
    
    def get_oauth_url(self, state: str = None) -> str:
        """
        Generate Instagram OAuth authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
        
        Returns:
            OAuth URL for user authorization
        """
        scope = 'instagram_basic,instagram_content_publish'  # Required permissions
        
        auth_url = (
            f"https://api.instagram.com/oauth/authorize"
            f"?client_id={self.app_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={scope}"
            f"&response_type=code"
        )
        
        if state:
            auth_url += f"&state={state}"
        
        return auth_url
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for long-lived access token
        
        Args:
            code: Authorization code from OAuth callback
        
        Returns:
            {
                'access_token': str,
                'user_id': str,
                'expires_in': int
            }
        """
        try:
            # Step 1: Get short-lived token
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.instagram.com/oauth/access_token',
                    data={
                        'client_id': self.app_id,
                        'client_secret': self.app_secret,
                        'grant_type': 'authorization_code',
                        'redirect_uri': self.redirect_uri,
                        'code': code
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Token exchange failed: {response.status} - {error_text}")
                    
                    short_token_data = await response.json()
                    short_token = short_token_data.get('access_token')
                    user_id = short_token_data.get('user_id')
            
            # Step 2: Exchange for long-lived token
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://graph.instagram.com/access_token',
                    params={
                        'grant_type': 'ig_exchange_token',
                        'client_secret': self.app_secret,
                        'access_token': short_token
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Long-lived token exchange failed: {response.status}")
                    
                    long_token_data = await response.json()
                    
                    return {
                        'access_token': long_token_data.get('access_token'),
                        'user_id': user_id,
                        'expires_in': long_token_data.get('expires_in', 5184000)  # ~60 days
                    }
        
        except Exception as e:
            logger.error(f"Error exchanging Instagram code: {e}")
            raise
    
    async def upload_reel(self, access_token: str, ig_user_id: str, video_url: str, caption: str) -> Dict:
        """
        Upload video as Instagram Reel
        
        Args:
            access_token: User's access token
            ig_user_id: Instagram User ID
            video_url: Publicly accessible video URL
            caption: Video caption
        
        Returns:
            {
                'success': bool,
                'media_id': str,
                'permalink': str
            }
        """
        try:
            print(f"📤 Uploading Reel to Instagram...")
            logger.info(f"Uploading Reel: {video_url}")
            
            # Step 1: Create media container
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'https://graph.instagram.com/v18.0/{ig_user_id}/media',
                    params={
                        'access_token': access_token,
                        'media_type': 'REELS',
                        'video_url': video_url,
                        'caption': caption,
                        'share_to_feed': True
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Container creation failed: {response.status} - {error_text}")
                    
                    result = await response.json()
                    container_id = result.get('id')
                    
                    if not container_id:
                        raise ValueError(f"No container ID returned: {result}")
            
            # Step 2: Poll until video is ready
            print(f"⏳ Processing video on Instagram...")
            
            for attempt in range(60):  # 5 minutes max
                await asyncio.sleep(5)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://graph.instagram.com/v18.0/{container_id}',
                        params={
                            'access_token': access_token,
                            'fields': 'status_code'
                        }
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            status = result.get('status_code')
                            
                            if status == 'FINISHED':
                                break
                            elif status == 'ERROR':
                                raise ValueError("Instagram video processing failed")
            
            # Step 3: Publish the media
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'https://graph.instagram.com/v18.0/{ig_user_id}/media_publish',
                    params={
                        'access_token': access_token,
                        'creation_id': container_id
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Publish failed: {response.status}")
                    
                    result = await response.json()
                    media_id = result.get('id')
            
            # Get media permalink
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://graph.instagram.com/v18.0/{media_id}',
                    params={
                        'access_token': access_token,
                        'fields': 'permalink'
                    }
                ) as response:
                    result = await response.json()
                    permalink = result.get('permalink')
            
            print(f"✅ Instagram Reel published: {permalink}")
            logger.info(f"Instagram Reel published: {permalink}")
            
            return {
                'success': True,
                'media_id': media_id,
                'permalink': permalink
            }
            
        except Exception as e:
            error_msg = f"Error uploading Instagram Reel: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def upload_carousel(self, access_token: str, ig_user_id: str, image_urls: List[str], caption: str) -> Dict:
        """
        Upload carousel post to Instagram
        
        Args:
            access_token: User's access token
            ig_user_id: Instagram User ID
            image_urls: List of publicly accessible image URLs (2-10 images)
            caption: Post caption
        
        Returns:
            {
                'success': bool,
                'media_id': str,
                'permalink': str
            }
        """
        try:
            print(f"📤 Uploading carousel to Instagram ({len(image_urls)} images)...")
            logger.info(f"Uploading carousel with {len(image_urls)} images")
            
            # Validate image count
            if len(image_urls) < 2 or len(image_urls) > 10:
                raise ValueError("Carousel must have 2-10 images")
            
            # Step 1: Create media containers for each image
            container_ids = []
            
            for i, image_url in enumerate(image_urls):
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'https://graph.instagram.com/v18.0/{ig_user_id}/media',
                        params={
                            'access_token': access_token,
                            'image_url': image_url,
                            'is_carousel_item': True
                        }
                    ) as response:
                        if response.status != 200:
                            raise ValueError(f"Image {i+1} container failed: {response.status}")
                        
                        result = await response.json()
                        container_ids.append(result.get('id'))
                
                print(f"✅ Image {i+1}/{len(image_urls)} container created")
            
            # Step 2: Create carousel container
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'https://graph.instagram.com/v18.0/{ig_user_id}/media',
                    params={
                        'access_token': access_token,
                        'media_type': 'CAROUSEL',
                        'children': ','.join(container_ids),
                        'caption': caption
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Carousel container failed: {response.status}")
                    
                    result = await response.json()
                    carousel_container_id = result.get('id')
            
            # Step 3: Publish carousel
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'https://graph.instagram.com/v18.0/{ig_user_id}/media_publish',
                    params={
                        'access_token': access_token,
                        'creation_id': carousel_container_id
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Carousel publish failed: {response.status}")
                    
                    result = await response.json()
                    media_id = result.get('id')
            
            # Get permalink
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://graph.instagram.com/v18.0/{media_id}',
                    params={
                        'access_token': access_token,
                        'fields': 'permalink'
                    }
                ) as response:
                    result = await response.json()
                    permalink = result.get('permalink')
            
            print(f"✅ Instagram carousel published: {permalink}")
            logger.info(f"Instagram carousel published: {permalink}")
            
            return {
                'success': True,
                'media_id': media_id,
                'permalink': permalink
            }
            
        except Exception as e:
            error_msg = f"Error uploading Instagram carousel: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
instagram_posting_service = InstagramPostingService()

