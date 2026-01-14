"""
TikTok Content Posting Service
Handles OAuth, video uploads, and posting to TikTok via official API
"""

import aiohttp
import asyncio
import logging
import json
import os
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TikTokPostingService:
    """
    Service for posting videos to TikTok using official Content Posting API
    Docs: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
    """
    
    def __init__(self):
        self.client_key = os.getenv('TIKTOK_CLIENT_KEY')
        self.client_secret = os.getenv('TIKTOK_CLIENT_SECRET')
        self.redirect_uri = os.getenv('TIKTOK_REDIRECT_URI', 'http://127.0.0.1:5000/auth/tiktok/callback')
        
        print(f"🔑 TikTok Service initialized - Client Key: {'✅ SET' if self.client_key else '❌ NOT SET'}")
        logger.info(f"TikTok Service initialized - Client Key: {'SET' if self.client_key else 'NOT SET'}")
    
    def get_oauth_url(self, state: str = None) -> str:
        """
        Generate TikTok OAuth authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
        
        Returns:
            OAuth URL for user authorization
        """
        scope = 'video.upload,video.publish'  # Required scopes for posting
        
        auth_url = (
            f"https://www.tiktok.com/v2/auth/authorize/"
            f"?client_key={self.client_key}"
            f"&scope={scope}"
            f"&response_type=code"
            f"&redirect_uri={self.redirect_uri}"
        )
        
        if state:
            auth_url += f"&state={state}"
        
        return auth_url
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for access token
        
        Args:
            code: Authorization code from OAuth callback
        
        Returns:
            {
                'access_token': str,
                'refresh_token': str,
                'expires_in': int,
                'open_id': str  # TikTok user ID
            }
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://open.tiktokapis.com/v2/oauth/token/',
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    data={
                        'client_key': self.client_key,
                        'client_secret': self.client_secret,
                        'code': code,
                        'grant_type': 'authorization_code',
                        'redirect_uri': self.redirect_uri
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"TikTok token exchange failed: {response.status} - {error_text}")
                    
                    result = await response.json()
                    
                    if result.get('error'):
                        raise ValueError(f"TikTok OAuth error: {result.get('error_description', result.get('error'))}")
                    
                    return result.get('data', {})
        
        except Exception as e:
            logger.error(f"Error exchanging TikTok code: {e}")
            raise
    
    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh expired access token
        
        Args:
            refresh_token: Refresh token from previous authorization
        
        Returns:
            New token data
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://open.tiktokapis.com/v2/oauth/token/',
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                    data={
                        'client_key': self.client_key,
                        'client_secret': self.client_secret,
                        'grant_type': 'refresh_token',
                        'refresh_token': refresh_token
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Token refresh failed: {response.status}")
                    
                    result = await response.json()
                    return result.get('data', {})
        
        except Exception as e:
            logger.error(f"Error refreshing TikTok token: {e}")
            raise
    
    async def upload_video(self, access_token: str, video_path: str, caption: str, privacy_level: str = 'PUBLIC_TO_EVERYONE') -> Dict:
        """
        Upload video to TikTok
        
        Args:
            access_token: User's access token
            video_path: Path to video file (local path or URL)
            caption: Video caption/description
            privacy_level: 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY'
        
        Returns:
            {
                'success': bool,
                'publish_id': str,
                'share_url': str (if available)
            }
        """
        try:
            print(f"📤 Uploading video to TikTok...")
            logger.info(f"Uploading to TikTok: {video_path}")
            
            # Step 1: Initialize upload
            init_response = await self._initialize_upload(access_token)
            
            if not init_response.get('upload_url'):
                raise ValueError("Failed to get TikTok upload URL")
            
            upload_url = init_response['upload_url']
            
            # Step 2: Upload video file
            await self._upload_video_file(upload_url, video_path)
            
            # Step 3: Publish video
            publish_result = await self._publish_video(
                access_token,
                caption,
                privacy_level
            )
            
            print(f"✅ Video uploaded to TikTok successfully!")
            logger.info(f"TikTok video published: {publish_result.get('publish_id')}")
            
            return {
                'success': True,
                'publish_id': publish_result.get('publish_id'),
                'share_url': publish_result.get('share_url')
            }
            
        except Exception as e:
            error_msg = f"Error uploading to TikTok: {e}"
            print(f"❌ {error_msg}")
            logger.error(error_msg)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _initialize_upload(self, access_token: str) -> Dict:
        """Initialize TikTok video upload"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://open.tiktokapis.com/v2/post/publish/video/init/',
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'post_info': {
                            'title': '',  # Set in publish step
                            'privacy_level': 'PUBLIC_TO_EVERYONE',
                            'disable_duet': False,
                            'disable_comment': False,
                            'disable_stitch': False,
                            'video_cover_timestamp_ms': 1000
                        },
                        'source_info': {
                            'source': 'FILE_UPLOAD',
                            'video_size': 0,  # Will be updated
                            'chunk_size': 10000000,  # 10MB chunks
                            'total_chunk_count': 1
                        }
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Init failed: {response.status} - {error_text}")
                    
                    result = await response.json()
                    
                    if result.get('error'):
                        raise ValueError(f"Init error: {result.get('error')}")
                    
                    return result.get('data', {})
        
        except Exception as e:
            logger.error(f"Error initializing TikTok upload: {e}")
            raise
    
    async def _upload_video_file(self, upload_url: str, video_path: str):
        """Upload video file to TikTok"""
        try:
            # Read video file
            with open(video_path, 'rb') as f:
                video_data = f.read()
            
            # Upload to TikTok's server
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    upload_url,
                    data=video_data,
                    headers={'Content-Type': 'video/mp4'}
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Upload failed: {response.status}")
        
        except Exception as e:
            logger.error(f"Error uploading video file: {e}")
            raise
    
    async def _publish_video(self, access_token: str, caption: str, privacy_level: str) -> Dict:
        """Publish uploaded video"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://open.tiktokapis.com/v2/post/publish/status/fetch/',
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'post_info': {
                            'title': caption,
                            'privacy_level': privacy_level
                        }
                    }
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"Publish failed: {response.status}")
                    
                    result = await response.json()
                    return result.get('data', {})
        
        except Exception as e:
            logger.error(f"Error publishing TikTok video: {e}")
            raise


# Singleton instance
tiktok_posting_service = TikTokPostingService()

