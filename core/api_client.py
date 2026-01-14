"""
Nicole API Client for Flask Web App
Synchronous client to call the Nicole Backend API.
"""

import requests
from typing import Optional, Dict, Any, List
import logging
import os

logger = logging.getLogger(__name__)

# API URL - default to localhost, override with environment variable
API_BASE_URL = os.getenv("NICOLE_API_URL", "http://localhost:8000")


class NicoleAPIClient:
    """Synchronous client for making requests to the Nicole Backend API."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or API_BASE_URL).rstrip("/")
        self.session = requests.Session()
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Dict = None, 
        params: Dict = None,
        timeout: int = 30
    ) -> Dict:
        """Make an HTTP request to the API."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=timeout
            )
            
            result = response.json()
            
            if response.status_code >= 400:
                logger.error(f"API error: {response.status_code} - {result}")
                raise APIError(response.status_code, result.get("detail", "Unknown error"))
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error to API: {e}")
            raise APIError(500, f"Connection failed: {str(e)}")
    
    # ============ User Endpoints ============
    
    def get_user(self, discord_id: str) -> Dict:
        """Get user by Discord ID."""
        return self._request("GET", f"/api/users/{discord_id}")
    
    def create_user(self, username: str, discord_id: str) -> Dict:
        """Create or get existing user."""
        return self._request("POST", "/api/users/", data={
            "username": username,
            "discord_id": discord_id
        })
    
    def update_user(self, discord_id: str, **updates) -> Dict:
        """Update user properties."""
        return self._request("PUT", f"/api/users/{discord_id}", data=updates)
    
    def user_exists(self, discord_id: str) -> bool:
        """Check if user exists."""
        result = self._request("GET", f"/api/users/{discord_id}/exists")
        return result.get("exists", False)
    
    # ============ Group Endpoints ============
    
    def get_my_groups(self, discord_id: str) -> List[Dict]:
        """Get all groups owned by a user."""
        result = self._request("GET", "/api/groups/my", params={"discord_id": discord_id})
        return result.get("groups", [])
    
    def get_available_groups(self, discord_id: str) -> List[Dict]:
        """Get available public groups for a user."""
        result = self._request("GET", "/api/groups/available", params={"discord_id": discord_id})
        return result.get("groups", [])
    
    def list_all_groups(self) -> List[Dict]:
        """Get all groups."""
        result = self._request("GET", "/api/groups/")
        return result.get("groups", [])
    
    def get_group(self, group_id: str) -> Dict:
        """Get group details by ID."""
        return self._request("GET", f"/api/groups/{group_id}")
    
    def get_group_statistics(self, group_id: str) -> Dict:
        """Get statistics for a group."""
        return self._request("GET", f"/api/groups/{group_id}/statistics")
    
    def get_group_competitors(self, group_id: str) -> List[Dict]:
        """Get competitors for a group."""
        result = self._request("GET", f"/api/groups/{group_id}/competitors")
        return result.get("competitors", [])
    
    def get_group_series(self, group_id: str) -> List[Dict]:
        """Get series data for a group."""
        result = self._request("GET", f"/api/groups/{group_id}/series")
        return result.get("series", [])
    
    def get_group_themes(self, group_id: str) -> List[Dict]:
        """Get themes for a group."""
        result = self._request("GET", f"/api/groups/{group_id}/themes")
        return result.get("themes", [])
    
    def update_group(self, group_id: str, **updates) -> Dict:
        """Update a group."""
        return self._request("PUT", f"/api/groups/{group_id}", data=updates)
    
    def delete_group(self, group_id: str) -> Dict:
        """Delete a group."""
        return self._request("DELETE", f"/api/groups/{group_id}")
    
    # ============ Analysis Endpoints ============
    
    def start_analysis(
        self, 
        channel_url: str, 
        group_name: str, 
        discord_id: str,
        is_public: bool = False
    ) -> Dict:
        """Start a niche analysis."""
        return self._request("POST", "/api/analysis/start", data={
            "channel_url": channel_url,
            "group_name": group_name,
            "discord_id": discord_id,
            "is_public": is_public
        })
    
    def get_analysis_status(self, analysis_id: str) -> Dict:
        """Get analysis progress."""
        return self._request("GET", f"/api/analysis/{analysis_id}/status")
    
    def get_analysis_result(self, analysis_id: str) -> Dict:
        """Get completed analysis result."""
        return self._request("GET", f"/api/analysis/{analysis_id}/result")
    
    # ============ Content Endpoints ============
    
    def generate_titles(
        self,
        group_id: str,
        series_name: str,
        theme_name: str,
        count: int = 5,
        custom_niche: str = None,
        enable_research: bool = False
    ) -> List[str]:
        """Generate video titles."""
        result = self._request("POST", "/api/content/titles", data={
            "group_id": group_id,
            "series_name": series_name,
            "theme_name": theme_name,
            "count": count,
            "custom_niche": custom_niche,
            "enable_research": enable_research
        }, timeout=120)  # Longer timeout for AI generation
        return result.get("titles", [])
    
    def generate_plot_outline(
        self,
        title: str,
        guidelines: str,
        series: Dict,
        theme: Dict,
        video_length: float = 10.0,
        enable_research: bool = False
    ) -> str:
        """Generate plot outline."""
        result = self._request("POST", "/api/content/plot-outline", data={
            "title": title,
            "guidelines": guidelines,
            "series": series,
            "theme": theme,
            "video_length": video_length,
            "enable_research": enable_research
        }, timeout=120)
        return result.get("plot_outline", "")
    
    def generate_script(
        self,
        title: str,
        plot_outline: str,
        script_breakdown: str,
        series: Dict,
        theme: Dict,
        video_length: float = 10.0,
        characters: List[str] = None,
        host_name: str = None
    ) -> Dict:
        """Generate full script."""
        return self._request("POST", "/api/content/script", data={
            "title": title,
            "plot_outline": plot_outline,
            "script_breakdown": script_breakdown,
            "series": series,
            "theme": theme,
            "video_length": video_length,
            "characters": characters,
            "host_name": host_name
        }, timeout=180)  # Long timeout for script generation
    
    def generate_voice(self, script: str, voice_name: str) -> str:
        """Generate voice over."""
        result = self._request("POST", "/api/content/voice", data={
            "script": script,
            "voice_name": voice_name
        }, timeout=300)  # Long timeout for voice generation
        return result.get("audio_url", "")
    
    def generate_thumbnail_concepts(
        self,
        guidelines: str,
        video_title: str,
        reference_urls: List[str],
        num_concepts: int = 3
    ) -> List[str]:
        """Generate thumbnail concepts."""
        result = self._request("POST", "/api/content/thumbnail/concepts", data={
            "guidelines": guidelines,
            "video_title": video_title,
            "reference_urls": reference_urls,
            "num_concepts": num_concepts
        }, timeout=60)
        return result.get("concepts", [])
    
    def generate_thumbnail(self, concept: str, reference_urls: List[str]) -> str:
        """Generate thumbnail image."""
        result = self._request("POST", "/api/content/thumbnail/generate", data={
            "concept": concept,
            "reference_urls": reference_urls
        }, timeout=120)
        return result.get("image_url", "")
    
    def get_available_voices(self) -> List[Dict]:
        """Get list of available voice options."""
        result = self._request("GET", "/api/content/voices")
        return result.get("voices", [])
    
    # ============ Production Endpoints ============
    
    def generate_production_titles(
        self,
        group_id: str,
        series_name: str,
        theme_name: str,
        count: int = 5,
        custom_niche: str = None,
        enable_research: bool = False
    ) -> List[str]:
        """Generate titles for production."""
        result = self._request("POST", "/api/production/titles", data={
            "group_id": group_id,
            "series_name": series_name,
            "theme_name": theme_name,
            "count": count,
            "custom_niche": custom_niche,
            "enable_research": enable_research
        }, timeout=120)
        return result.get("titles", [])
    
    def get_script_breakdown(
        self,
        group_id: str,
        series_name: str,
        theme_name: str
    ) -> Dict:
        """Get or generate script breakdown."""
        return self._request("POST", "/api/production/script-breakdown", data={
            "group_id": group_id,
            "series_name": series_name,
            "theme_name": theme_name
        }, timeout=180)
    
    def generate_production_thumbnail(
        self,
        group_id: str,
        series_name: str,
        theme_name: str,
        video_title: str,
        custom_niche: str = None
    ) -> Dict:
        """Generate thumbnail for production."""
        return self._request("POST", "/api/production/thumbnail/generate", data={
            "group_id": group_id,
            "series_name": series_name,
            "theme_name": theme_name,
            "video_title": video_title,
            "custom_niche": custom_niche
        }, timeout=180)
    
    def start_mass_production(
        self,
        group_id: str,
        channel_id: str,
        series_themes: List[Dict[str, str]],
        video_count: int,
        user_discord_id: str,
        video_duration: float = 30.0,
        visual_style: str = "black_rain",
        host_name: str = "Narrator",
        default_voice: str = "af_nicole"
    ) -> Dict:
        """Start mass production job."""
        return self._request("POST", "/api/production/mass-production/start", data={
            "group_id": group_id,
            "channel_id": channel_id,
            "series_themes": series_themes,
            "video_count": video_count,
            "video_duration": video_duration,
            "visual_style": visual_style,
            "host_name": host_name,
            "default_voice": default_voice,
            "user_discord_id": user_discord_id
        })
    
    def get_mass_production_status(self, job_id: str) -> Dict:
        """Get mass production job status."""
        return self._request("GET", f"/api/production/mass-production/{job_id}/status")
    
    def get_content_guidelines(self, group_id: str, series_name: str, theme_name: str) -> Dict:
        """Get content guidelines."""
        return self._request("GET", f"/api/production/guidelines/{group_id}/{series_name}/{theme_name}")
    
    def get_thumbnail_guidelines(self, group_id: str, series_name: str, theme_name: str) -> Dict:
        """Get thumbnail guidelines."""
        return self._request("GET", f"/api/production/thumbnail-guidelines/{group_id}/{series_name}/{theme_name}")
    
    # ============ Health Check ============
    
    def health_check(self) -> bool:
        """Check if API is healthy."""
        try:
            result = self._request("GET", "/health")
            return result.get("status") == "healthy"
        except:
            return False


class APIError(Exception):
    """Exception raised when API returns an error."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


# Global client instance
api_client = NicoleAPIClient()


def get_api_client() -> NicoleAPIClient:
    """Get the global API client instance."""
    return api_client

