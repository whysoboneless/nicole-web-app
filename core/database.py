"""
Database connection to MongoDB - Works standalone or with Discord bot
"""

import sys
import os
import asyncio
import threading
from typing import Optional, List, Dict, Any
import pymongo
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

# Try to get MONGODB_URI from local config first, then fall back to parent
try:
    # Try local web suite config first
    from config_standalone import MONGODB_URI
except ImportError:
    try:
        # Fall back to parent Discord bot config
        parent_dir = os.path.join(os.path.dirname(__file__), '..', '..')
        sys.path.insert(0, parent_dir)
        from config import MONGODB_URI
    except ImportError:
        # Last resort: environment variable
        MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/niche_research')

# Clean startup - no verbose prints

class Database:
    """
    REAL Discord bot database integration - Direct MongoDB connection
    Uses the EXACT same database as Discord bot with synchronous operations for Flask
    """
    
    def __init__(self):
        # Direct MongoDB connection using EXACT same URI and database name as Discord bot
        self.client = MongoClient(MONGODB_URI, maxPoolSize=20)
        self.db = self.client['niche_research']  # EXACT same database name as Discord bot
        
        # VFX Analysis database (separate database for VFX service)
        self.vfx_db = self.client['vfx_analysis_results']
        self.vfx_content_styles = self.vfx_db['ai_animation_styles']
        
        # Collections (EXACT same as Discord bot database.py)
        self.users = self.db['users']
        self.web_users = self.db['web_users']  # New collection for web app users
        self.groups = self.db['competitor_groups']  # Discord bot uses 'competitor_groups'
        self.competitor_groups = self.db['competitor_groups']
        self.competitors = self.db['competitor_channels']
        self.channel_data = self.db['channels']
        self.series = self.db['series']
        self.content_creation = self.db['content_creation']
        self.content_calendar = self.db.content_calendar
        self.voice_profiles = self.db['voice_profiles']
        self.scheduled_content = self.db['scheduled_content']
        self.youtube_channel_settings = self.db['youtube_channel_settings']
        self.channels = self.db['channels']
        self.used_titles = self.db['used_titles']
        self.videos = self.db['videos']
        self.video_outliers = self.db['video_outliers']
        self.user_api_keys = self.db['user_api_keys']  # New collection for user API keys
        self.competitor_search_data = self.db['competitor_search_data']
        
        # Instagram Studio collections
        self.instagram_accounts = self.db['instagram_accounts']
        self.instagram_videos = self.db['instagram_videos']
        self.instagram_jobs = self.db['instagram_jobs']
        self.instagram_schedule = self.db['instagram_schedule']
        
        # VFX Collections
        self.vfx_guidelines = self.db['vfx_guidelines']
        self.vfx_breakdowns = self.db['vfx_breakdowns']
        self.sora_generations = self.db['sora_generations']
        
        # Campaign System Collections (NEW)
        self.campaigns = self.db['campaigns']
        self.campaign_channels = self.db['campaign_channels']
        self.campaign_analytics = self.db['campaign_analytics']
        
        # IG/TikTok Groups Collection (for Instagram & TikTok series/theme analysis)
        self.ig_tiktok_groups = self.db['ig_tiktok_groups']
        
        # Products Collection (for saving and managing products)
        self.products = self.db['products']
        
        # Create indexes for campaign collections
        self._create_campaign_indexes()
        self._create_product_indexes()
        self._create_ig_tiktok_indexes()
        
        # Clean init - no prints
    
    # Web App User Methods
    def get_web_user_by_id(self, user_id):
        """Get web user by ID"""
        try:
            return self.web_users.find_one({"_id": ObjectId(user_id)})
        except:
            return None
    
    def create_web_user(self, username, email, password_hash=None):
        """Create a new web user"""
        user_data = {
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "is_admin": False,
            "is_premium": False,
            "is_beta": True,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow()
        }
        result = self.web_users.insert_one(user_data)
        return self.web_users.find_one({"_id": result.inserted_id})
    
    def get_web_user_groups_sync(self, user_id):
        """Get groups for web user - using web user ID instead of Discord ID"""
        try:
            # Get groups where the web user is the owner
            query = {
                "$or": [
                    {"owner_id": user_id},
                    {"owner_ids": user_id},
                    {"assigned_users": user_id}
                ]
            }
            groups = list(self.competitor_groups.find(query).sort("created_at", -1))
            print(f"✅ Found {len(groups)} groups for web user {user_id}")
            return groups
        except Exception as e:
            print(f"Error getting web user groups: {e}")
            return []
    
    def get_web_user_available_groups_sync(self, user_id):
        """Get available groups for web user"""
        try:
            # Get public groups that the user doesn't own
            user_groups = self.get_web_user_groups_sync(user_id)
            user_group_ids = [str(g.get('_id')) for g in user_groups]
            
            query = {
                "is_public": True,
                "_id": {"$nin": [ObjectId(gid) for gid in user_group_ids if gid]}
            }
            available_groups = list(self.competitor_groups.find(query).sort("created_at", -1))
            print(f"✅ Found {len(available_groups)} available groups for web user {user_id}")
            return available_groups
        except Exception as e:
            print(f"Error getting available groups: {e}")
            return []

    # User API Key Management Methods
    def save_user_api_key(self, user_id: str, service: str, name: str, api_key: str, description: str = "") -> bool:
        """Save or update a user's API key for a specific service"""
        try:
            # Encrypt the API key (simple base64 encoding for now - in production use proper encryption)
            import base64
            encrypted_key = base64.b64encode(api_key.encode()).decode()
            
            # Check if key already exists for this user and service
            existing = self.user_api_keys.find_one({
                "user_id": user_id,
                "service": service
            })
            
            if existing:
                # Update existing key
                self.user_api_keys.update_one(
                    {"user_id": user_id, "service": service},
                    {
                        "$set": {
                            "name": name,
                            "api_key": encrypted_key,
                            "description": description,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            else:
                # Insert new key
                self.user_api_keys.insert_one({
                    "user_id": user_id,
                    "service": service,
                    "name": name,
                    "api_key": encrypted_key,
                    "description": description,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "last_used": None,
                    "status": "active"
                })
            return True
        except Exception as e:
            print(f"Error saving API key: {e}")
            return False

    def get_user_api_keys(self, user_id: str) -> List[Dict]:
        """Get all API keys for a user"""
        try:
            keys = list(self.user_api_keys.find({"user_id": user_id}))
            
            # Decrypt keys for display and format for template
            import base64
            for key in keys:
                try:
                    decrypted_key = base64.b64decode(key["api_key"].encode()).decode()
                    key["key"] = decrypted_key  # Template expects 'key' field
                    key["api_key"] = decrypted_key  # Keep for backward compatibility
                except:
                    key["key"] = "***ENCRYPTED***"
                    key["api_key"] = "***ENCRYPTED***"
                
                key["_id"] = str(key["_id"])
                key["id"] = str(key["_id"])  # Alpine.js template expects 'id' field
                # Ensure required fields exist for template
                key["showKey"] = False  # For show/hide functionality
                key["icon"] = self._get_service_icon(key.get("service", ""))
                
                # Convert datetime objects to strings for JSON serialization
                if key.get("created_at"):
                    if hasattr(key["created_at"], "strftime"):
                        key["dateAdded"] = key["created_at"].strftime("%Y-%m-%d")
                        key["created_at"] = key["created_at"].isoformat()
                    else:
                        key["dateAdded"] = str(key["created_at"])
                else:
                    key["dateAdded"] = "Unknown"
                
                if key.get("updated_at"):
                    if hasattr(key["updated_at"], "strftime"):
                        key["updated_at"] = key["updated_at"].isoformat()
                    else:
                        key["updated_at"] = str(key["updated_at"])
                
                key["lastUsed"] = key.get("last_used", "Never")
                if key["lastUsed"] and hasattr(key["lastUsed"], "strftime"):
                    key["lastUsed"] = key["lastUsed"].strftime("%Y-%m-%d")
            
            return keys
        except Exception as e:
            print(f"Error getting API keys: {e}")
            return []
    
    def _get_service_icon(self, service: str) -> str:
        """Get icon for service"""
        icons = {
            'Anthropic Claude': '🧠',
            'YouTube Data API': '📺',
            'YouTube Analytics API': '📊',
            'Replicate': '🔄',
            'ElevenLabs': '🎙️'
        }
        return icons.get(service, '🔑')

    def create_discord_user(self, user_data: Dict) -> bool:
        """Create a new Discord user in the database"""
        try:
            result = self.users.insert_one(user_data)
            return result.inserted_id is not None
        except Exception as e:
            print(f"Error creating Discord user: {e}")
            return False

    def get_user_api_key(self, user_id: str, service: str) -> Optional[str]:
        """Get a specific API key for a user and service"""
        try:
            # First try to find with the current user_id
            key_doc = self.user_api_keys.find_one({
                "user_id": user_id,
                "service": service,
                "status": "active"
            })
            
            if key_doc:
                # Decrypt the key
                import base64
                return base64.b64decode(key_doc["api_key"].encode()).decode()
            
            # If not found and this is a web user (owner_user, demo_user), 
            # try to find keys saved with Discord ID for backward compatibility
            if user_id in ['owner_user', 'demo_user']:
                # For owner_user, try the actual Discord ID
                discord_id = '528049173178875924' if user_id == 'owner_user' else None
                if discord_id:
                    key_doc = self.user_api_keys.find_one({
                        "user_id": discord_id,
                        "service": service,
                        "status": "active"
                    })
                    if key_doc:
                        import base64
                        return base64.b64decode(key_doc["api_key"].encode()).decode()
            
            # Also try the reverse - if user_id is a Discord ID, try to find keys saved with web user ID
            elif user_id == '528049173178875924':
                key_doc = self.user_api_keys.find_one({
                    "user_id": "owner_user",
                    "service": service,
                    "status": "active"
                })
                if key_doc:
                    import base64
                    return base64.b64decode(key_doc["api_key"].encode()).decode()
            
            return None
        except Exception as e:
            print(f"Error getting API key: {e}")
            return None

    def get_user_youtube_api_keys(self, user_id: str) -> List[str]:
        """Get all YouTube API keys for a user"""
        try:
            # First try with current user_id
            youtube_keys = list(self.user_api_keys.find({
                "user_id": user_id,
                "service": {"$in": ["YouTube Data API", "YouTube Analytics API"]},
                "status": "active"
            }))
            
            # If not found and this is a web user, try Discord ID for backward compatibility
            if not youtube_keys and user_id in ['owner_user', 'demo_user']:
                discord_id = '528049173178875924' if user_id == 'owner_user' else None
                if discord_id:
                    youtube_keys = list(self.user_api_keys.find({
                        "user_id": discord_id,
                        "service": {"$in": ["YouTube Data API", "YouTube Analytics API"]},
                        "status": "active"
                    }))
            
            import base64
            keys = []
            for key_doc in youtube_keys:
                try:
                    decrypted_key = base64.b64decode(key_doc["api_key"].encode()).decode()
                    keys.append(decrypted_key)
                except:
                    continue
            
            return keys
        except Exception as e:
            print(f"Error getting YouTube API keys: {e}")
            return []

    def delete_user_api_key(self, user_id: str, service: str) -> bool:
        """Delete a user's API key for a specific service"""
        try:
            result = self.user_api_keys.delete_one({
                "user_id": user_id,
                "service": service
            })
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting API key: {e}")
            return False

    def update_api_key_usage(self, user_id: str, service: str) -> bool:
        """Update the last used timestamp for an API key"""
        try:
            self.user_api_keys.update_one(
                {"user_id": user_id, "service": service},
                {"$set": {"last_used": datetime.utcnow()}}
            )
            return True
        except Exception as e:
            print(f"Error updating API key usage: {e}")
            return False

    def get_user_groups_sync(self, discord_id: str) -> List[Dict]:
        """Get user groups synchronously - REAL DATA FROM DISCORD BOT DATABASE"""
        try:
            # First get the user by discord_id to get their MongoDB _id
            user = self.users.find_one({"discord_id": discord_id})
            if not user:
                print(f"No user found with discord_id: {discord_id}")
                return []
            
            user_object_id = user['_id']  # This is the MongoDB ObjectId
            print(f"✅ Found user {user.get('username', 'Unknown')} with _id: {user_object_id}")
            
            # Query groups using the EXACT same logic as Discord bot's get_groups_by_owner
            groups = list(self.competitor_groups.find({
                "$or": [
                    {"owner_id": user_object_id},
                    {"owner_ids": user_object_id}, 
                    {"assigned_users": user_object_id}
                ]
            }).sort("created_at", -1))
            
            print(f"✅ Found {len(groups)} groups for user {discord_id} (MongoDB _id: {user_object_id})")
            return groups
                
        except Exception as e:
            print(f"❌ Error getting user groups: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_group_sync(self, group_id: str) -> Optional[Dict]:
        """Get group by ID synchronously - REAL DATA"""
        try:
            # Convert string ID to ObjectId for MongoDB query
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return None
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if group:
                print(f"✅ Found group: {group.get('name', 'Unknown')}")
            else:
                print(f"❌ No group found with ID: {group_id}")
            return group
        except Exception as e:
            print(f"❌ Error getting group: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def create_group_sync(self, group_data: Dict) -> bool:
        """Create group synchronously - REAL DATA"""
        try:
            result = self.competitor_groups.insert_one(group_data)
            print(f"✅ Created group with ID: {result.inserted_id}")
            return True
        except Exception as e:
            print(f"❌ Error creating group: {e}")
            return False

    def get_user_by_discord_id_sync(self, discord_id: str) -> Optional[Dict]:
        """Get user by discord ID synchronously - checks both users and web_users collections"""
        try:
            # First check users collection (Discord bot users)
            user = self.users.find_one({"discord_id": discord_id})
            if user:
                print(f"✅ Found user in users: {user.get('username', 'Unknown')}")
                return user
            
            # If not found, check web_users collection
            user = self.web_users.find_one({"discord_id": discord_id})
            if user:
                print(f"✅ Found user in web_users: {user.get('username', 'Unknown')}")
                return user
            
            print(f"❌ User not found with discord_id: {discord_id}")
            return None
        except Exception as e:
            print(f"❌ Error getting user: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_user_sync(self, user_data: Dict) -> bool:
        """Create user synchronously - REAL DATA"""
        try:
            result = self.users.insert_one(user_data)
            print(f"✅ Created user with ID: {result.inserted_id}")
            return True
        except Exception as e:
            print(f"❌ Error creating user: {e}")
            return False

    def update_group_sync(self, group_id: str, update_data: Dict) -> bool:
        """Update group synchronously - REAL DATA"""
        try:
            result = self.competitor_groups.update_one(
                {"_id": group_id},
                {"$set": update_data}
            )
            print(f"✅ Updated group: {result.modified_count} documents")
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating group: {e}")
            return False

    def delete_group_sync(self, group_id: str) -> bool:
        """Delete group synchronously - REAL DATA"""
        try:
            result = self.competitor_groups.delete_one({"_id": group_id})
            print(f"✅ Deleted group: {result.deleted_count} documents")
            return result.deleted_count > 0
        except Exception as e:
            print(f"❌ Error deleting group: {e}")
            return False

    def get_competitors_sync(self, group_id: str) -> List[Dict]:
        """Get competitors for group synchronously - REAL DATA"""
        try:
            # Convert string ID to ObjectId for MongoDB query
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return []
            else:
                object_id = group_id
            
            # Get group first to get competitor channel IDs
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ No group found with ID: {group_id}")
                return []
            
            # Get competitors directly from the group (they're stored as full objects in 'competitors' field)
            competitors = group.get("competitors", [])
            
            # Also check the old format (competitor_channels) for backward compatibility
            if not competitors:
                competitor_channel_ids = group.get("competitor_channels", [])
                if competitor_channel_ids:
                    competitors = list(self.channels.find({"_id": {"$in": competitor_channel_ids}}))
            
            print(f"✅ Found {len(competitors)} competitors for group {group_id}")
            return competitors
        except Exception as e:
            print(f"❌ Error getting competitors: {e}")
            import traceback
            traceback.print_exc()
            return []

    def add_competitor_sync(self, competitor_data: Dict) -> bool:
        """Add competitor synchronously - REAL DATA"""
        try:
            result = self.channels.insert_one(competitor_data)
            print(f"✅ Added competitor with ID: {result.inserted_id}")
            return True
        except Exception as e:
            print(f"❌ Error adding competitor: {e}")
            return False

    def get_public_groups_sync(self) -> List[Dict]:
        """Get public groups synchronously - REAL DATA"""
        try:
            groups = list(self.competitor_groups.find({"is_public": True}))
            print(f"✅ Found {len(groups)} public groups")
            return groups
        except Exception as e:
            print(f"❌ Error getting public groups: {e}")
            return []

    def get_available_groups_sync(self, discord_id: str) -> List[Dict]:
        """Get available groups for user synchronously - EXACT same logic as Discord bot"""
        try:
            # First get the user by discord_id to get their MongoDB _id
            user = self.users.find_one({"discord_id": discord_id})
            if not user:
                print(f"No user found with discord_id: {discord_id}")
                return []
            
            user_object_id = user['_id']  # This is the MongoDB ObjectId
            
            # Get user's current groups (same as Discord bot logic)
            user_groups = set(user.get('groups', []))
            
            # Get all public groups
            all_public_groups = list(self.competitor_groups.find({"is_public": True}))
            
            # Filter out groups user is already a member of (EXACT same logic as Discord bot)
            available_groups = [
                {
                    "_id": str(group["_id"]),
                    "name": group.get("name", f"Unnamed Group {str(group['_id'])[-6:]}"),
                    "is_premium": group.get("is_premium", False),
                    "is_public": group.get("is_public", False),
                    "price": group.get("price", 0),
                    "whop_product_id": group.get("whop_product_id", None),
                    "is_purchasable": group.get("is_purchasable", False),
                }
                for group in all_public_groups 
                if str(group['_id']) not in user_groups
            ]
            
            print(f"✅ Found {len(available_groups)} available groups for user {discord_id}")
            return available_groups
            
        except Exception as e:
            print(f"❌ Error getting available groups: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_group_stats_sync(self, group_id: str) -> Dict:
        """Get group statistics synchronously - REAL DATA"""
        try:
            # Convert string ID to ObjectId for MongoDB query
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return {}
            else:
                object_id = group_id
            
            # Get group info
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ No group found with ID: {group_id}")
                return {}
            
            # Get competitor count
            competitor_count = len(group.get("competitor_channels", []))
            
            stats = {
                "competitor_count": competitor_count,
                "member_count": len(group.get("members", [])),
                "created_date": group.get("created_at"),
                "last_updated": group.get("updated_at"),
                "is_public": group.get("is_public", False)
            }
            
            print(f"✅ Generated stats for group {group_id}")
            return stats
            
        except Exception as e:
            print(f"❌ Error getting group stats: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_top_series_sync(
        self,
        group_id: str,
        timeframe: str = '90d',
        subscriber_min: int = None,
        subscriber_max: int = None,
        channel_id: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get top performing series synchronously - EXACT same logic as Discord bot"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return []
            else:
                object_id = group_id
            
            # Use the EXACT same pipeline as Discord bot
            pipeline = [
                {'$match': {'_id': object_id}},
                {'$project': {
                    'main_channel_id': 1,
                    'main_channel_data': {
                        'series_data': 1,
                        'subscriberCount': 1
                    },
                    'competitors': {
                        '$filter': {
                            'input': '$competitors',
                            'as': 'competitor',
                            'cond': {'$ne': ['$$competitor.series_data', None]}
                        }
                    }
                }},
                {'$addFields': {
                    'competitors': {
                        '$map': {
                            'input': '$competitors',
                            'as': 'competitor',
                            'in': {
                                'channel_id': '$$competitor.channel_id',
                                'series_data': '$$competitor.series_data',
                                'subscriberCount': '$$competitor.subscriberCount'
                            }
                        }
                    }
                }}
            ]
            
            # Execute query
            group = list(self.competitor_groups.aggregate(pipeline))
            if not group:
                print(f"❌ No group found with ID: {group_id}")
                return []
            
            group = group[0]  # Get first result
            
            # Process data in memory (EXACT same logic as Discord bot)
            all_series_data = []
            
            # Add main channel series if it exists
            if group.get('main_channel_data', {}).get('series_data'):
                main_channel_id = group['main_channel_id']
                main_channel_data = group['main_channel_data']
                for series in main_channel_data.get('series_data', []):
                    series['channel_id'] = main_channel_id
                    series['subscriberCount'] = int(main_channel_data.get('subscriberCount', 0))
                    all_series_data.append(series)
            
            # Process competitors' series data
            for competitor in group.get('competitors', []):
                if competitor.get('series_data'):
                    competitor_channel_id = competitor.get('channel_id')
                    for series in competitor['series_data']:
                        series['channel_id'] = competitor_channel_id
                        series['subscriberCount'] = int(competitor.get('subscriberCount', 0))
                        all_series_data.append(series)
            
            # Apply filters (EXACT same logic as Discord bot)
            if channel_id:
                all_series_data = [s for s in all_series_data if s.get('channel_id') == channel_id]
            
            if subscriber_min is not None or subscriber_max is not None:
                all_series_data = [
                    s for s in all_series_data 
                    if ((subscriber_min is None or s.get('subscriberCount', 0) >= subscriber_min) and
                        (subscriber_max is None or s.get('subscriberCount', 0) <= subscriber_max))
                ]
            
            # Combine series with same name using dictionary for O(1) lookup
            combined_series = {}
            for series in all_series_data:
                series_name = series.get('name')
                if not series_name:
                    continue
                    
                if series_name not in combined_series:
                    combined_series[series_name] = {
                        'name': series_name,
                        'themes': {},
                        'total_views': 0,
                        'video_count': 0,
                        'channels_with_series': set()
                    }
                
                comb_series = combined_series[series_name]
                comb_series['channels_with_series'].add(series.get('channel_id'))
                comb_series['total_views'] += series.get('avg_views', 0) * series.get('video_count', 0)
                comb_series['video_count'] += series.get('video_count', 0)
                
                # Process themes with optimized data structure
                for theme in series.get('themes', []):
                    theme_name = theme.get('name')
                    if not theme_name:
                        continue
                        
                    theme_data = comb_series['themes'].setdefault(theme_name, {
                        'name': theme_name,
                        'topics': [],
                        'total_views': 0,
                        'video_count': 0,
                        'channels_with_theme': set()
                    })
                    
                    theme_data['channels_with_theme'].add(series.get('channel_id'))
                    theme_data['total_views'] += theme.get('total_views', 0)
                    theme_data['video_count'] += theme.get('video_count', 0)
                    theme_data['topics'].extend(theme.get('topics', []))

            # Final formatting (EXACT same logic as Discord bot)
            final_series = []
            for series_data in combined_series.values():
                series_data['channels_with_series'] = list(series_data['channels_with_series'])
                series_data['avg_views'] = (
                    series_data['total_views'] / series_data['video_count'] 
                    if series_data['video_count'] > 0 else 0
                )
                
                # Convert themes
                series_data['themes'] = [
                    {
                        **theme_data,
                        'channels_with_theme': list(theme_data['channels_with_theme']),
                        'avg_views': (
                            theme_data['total_views'] / theme_data['video_count']
                            if theme_data['video_count'] > 0 else 0
                        )
                    }
                    for theme_data in series_data['themes'].values()
                ]
                
                final_series.append(series_data)
            
            # Sort and limit
            final_series.sort(key=lambda x: x['avg_views'], reverse=True)
            final_series = final_series[:limit]
            
            print(f"✅ Found {len(final_series)} top series for group {group_id}")
            return final_series
            
        except Exception as e:
            print(f"❌ Error getting top series: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_top_series_sync_simple(self, group_id: str, timeframe: str = '90d', limit: int = 10) -> List[Dict]:
        """Simplified version for basic queries"""
        return self.get_top_series_sync(group_id, timeframe, None, None, None, limit)

    def get_top_series_sync_overall(self, group_id: str, timeframe: str = '90d', limit: int = 10) -> List[Dict]:
        """Overall analysis - no filters"""
        return self.get_top_series_sync(group_id, timeframe, None, None, None, limit)

    def get_top_series_sync_subscriber_level(self, group_id: str, timeframe: str = '90d', subscriber_min: int = None, subscriber_max: int = None, limit: int = 10) -> List[Dict]:
        """Subscriber level analysis with subscriber range filters"""
        return self.get_top_series_sync(group_id, timeframe, subscriber_min, subscriber_max, None, limit)

    def get_top_series_sync_channel_specific(self, group_id: str, timeframe: str = '90d', channel_id: str = None, limit: int = 10) -> List[Dict]:
        """Channel-specific analysis with channel filter"""
        return self.get_top_series_sync(group_id, timeframe, None, None, channel_id, limit)

    def needs_series_analysis_sync(self, group_id: str) -> bool:
        """Check if series analysis is needed for group"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return True
            else:
                object_id = group_id
            
            # Check if we have recent series data
            series_count = self.series.count_documents({"group_id": object_id})
            return series_count == 0
            
        except Exception as e:
            print(f"❌ Error checking analysis need: {e}")
            return True

    def get_month_content_sync(self, group_id: str) -> List[Dict]:
        """Get current month's planned content"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get current month's content from content_calendar
            content = list(self.content_calendar.find({"group_id": object_id}))
            print(f"✅ Found {len(content)} content items for current month")
            return content
            
        except Exception as e:
            print(f"❌ Error getting month content: {e}")
            return []

    def get_upcoming_content_sync(self, group_id: str) -> List[Dict]:
        """Get upcoming content for group"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get upcoming scheduled content
            content = list(self.scheduled_content.find({"group_id": object_id}))
            print(f"✅ Found {len(content)} upcoming content items")
            return content
            
        except Exception as e:
            print(f"❌ Error getting upcoming content: {e}")
            return []

    def get_competitor_upload_frequency_sync(self, group_id: str) -> Dict:
        """Get competitor upload frequency analysis"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return {}
            else:
                object_id = group_id
            
            # Get group to find competitors
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return {}
            
            # Analyze competitor upload patterns (simplified)
            competitor_channels = group.get("competitor_channels", [])
            frequency_data = {
                "average_uploads_per_week": 3.5,  # This would be calculated from real data
                "most_active_day": "Tuesday",
                "optimal_posting_time": "2:00 PM",
                "competitor_count": len(competitor_channels)
            }
            
            print(f"✅ Generated upload frequency data for group {group_id}")
            return frequency_data
            
        except Exception as e:
            print(f"❌ Error getting upload frequency: {e}")
            return {}

    def get_all_series_themes_sync(self, group_id: str) -> Dict[str, List[Dict]]:
        """Get all themes for ALL series in a group - works like trend discovery (no content_creation required)"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return {}
            else:
                object_id = group_id
            
            # Use the same approach as get_top_series_sync - extract from group's series data
            # This works for all groups, not just those with content_creation field
            pipeline = [
                {'$match': {'_id': object_id}},
                {'$project': {
                    'main_channel_data': {
                        'series_data': 1
                    },
                    'competitors': {
                        '$filter': {
                            'input': '$competitors',
                            'as': 'competitor',
                            'cond': {'$ne': ['$$competitor.series_data', None]}
                        }
                    },
                    'content_creation': 1  # Also check content_creation as fallback
                }}
            ]
            
            # Execute query
            group_result = list(self.competitor_groups.aggregate(pipeline))
            if not group_result:
                print(f"❌ No group found with ID: {group_id}")
                return {}
            
            group = group_result[0]
            all_series_themes = {}
            
            # ALWAYS try to extract from main_channel_data and competitors first (like trend discovery)
            # This works for all groups regardless of content_creation field
            # Collect all series from main channel and competitors
            all_series_data = []
            
            # Add main channel series if it exists
            if group.get('main_channel_data', {}).get('series_data'):
                all_series_data.extend(group['main_channel_data']['series_data'])
            
            # Process competitors' series data
            for competitor in group.get('competitors', []):
                if competitor.get('series_data'):
                    all_series_data.extend(competitor['series_data'])
            
            # Combine series with same name
            combined_series = {}
            for series in all_series_data:
                series_name = series.get('name')
                if not series_name:
                    continue
                
                if series_name not in combined_series:
                    combined_series[series_name] = {
                        'name': series_name,
                        'themes': {},
                        'total_views': 0,
                        'video_count': 0
                    }
                
                comb_series = combined_series[series_name]
                comb_series['total_views'] += series.get('avg_views', 0) * series.get('video_count', 0)
                comb_series['video_count'] += series.get('video_count', 0)
                
                # Process themes
                for theme in series.get('themes', []):
                    theme_name = theme.get('name')
                    if not theme_name:
                        continue
                    
                    if theme_name not in comb_series['themes']:
                        comb_series['themes'][theme_name] = {
                            'name': theme_name,
                            'total_views': 0,
                            'video_count': 0
                        }
                    
                    theme_data = comb_series['themes'][theme_name]
                    theme_data['total_views'] += theme.get('total_views', 0)
                    theme_data['video_count'] += theme.get('video_count', 0)
            
            # Convert to expected format
            for series_name, series_data in combined_series.items():
                themes_list = []
                for theme_name, theme_data in series_data['themes'].items():
                    avg_views = (
                        theme_data['total_views'] / theme_data['video_count']
                        if theme_data['video_count'] > 0 else 0
                    )
                    themes_list.append({
                        "name": theme_name,
                        "video_count": theme_data['video_count'],
                        "total_views": theme_data['total_views'],
                        "avg_views": avg_views,
                        "has_script_breakdown": False,
                        "has_thumbnail_model": False,
                        "has_resources": False
                    })
                
                if themes_list:
                    all_series_themes[series_name] = themes_list
            
            # Also merge in any data from content_creation if it exists (for trained models, etc.)
            content_creation = group.get("content_creation", {})
            if content_creation:
                for series_name, series_data in content_creation.items():
                    if not isinstance(series_data, dict):
                        continue
                    
                    # If series already exists from main_channel_data, merge themes
                    if series_name in all_series_themes:
                        existing_themes = {t['name']: t for t in all_series_themes[series_name]}
                        for theme_name, theme_data in series_data.items():
                            if isinstance(theme_data, dict) and theme_name not in existing_themes:
                                # Add theme from content_creation if not already present
                                has_script_breakdown = bool(theme_data.get("script_breakdown"))
                                has_thumbnail_model = bool(theme_data.get("trained_model_version") and theme_data.get("thumbnail_guidelines"))
                                
                                all_series_themes[series_name].append({
                                    "name": theme_name,
                                    "video_count": theme_data.get("video_count", 0),
                                    "total_views": theme_data.get("total_views", 0),
                                    "avg_views": theme_data.get("avg_views", 0),
                                    "has_script_breakdown": has_script_breakdown,
                                    "has_thumbnail_model": has_thumbnail_model,
                                    "has_resources": has_script_breakdown and has_thumbnail_model,
                                    "script_breakdown": theme_data.get("script_breakdown"),
                                    "trained_model_version": theme_data.get("trained_model_version"),
                                    "thumbnail_guidelines": theme_data.get("thumbnail_guidelines")
                                })
                    else:
                        # Series only exists in content_creation, add it
                        themes_list = []
                        for theme_name, theme_data in series_data.items():
                            if isinstance(theme_data, dict):
                                has_script_breakdown = bool(theme_data.get("script_breakdown"))
                                has_thumbnail_model = bool(theme_data.get("trained_model_version") and theme_data.get("thumbnail_guidelines"))
                                
                                themes_list.append({
                                    "name": theme_name,
                                    "video_count": theme_data.get("video_count", 0),
                                    "total_views": theme_data.get("total_views", 0),
                                    "avg_views": theme_data.get("avg_views", 0),
                                    "has_script_breakdown": has_script_breakdown,
                                    "has_thumbnail_model": has_thumbnail_model,
                                    "has_resources": has_script_breakdown and has_thumbnail_model,
                                    "script_breakdown": theme_data.get("script_breakdown"),
                                    "trained_model_version": theme_data.get("trained_model_version"),
                                    "thumbnail_guidelines": theme_data.get("thumbnail_guidelines")
                                })
                        
                        if themes_list:
                            all_series_themes[series_name] = themes_list
            
            print(f"✅ Found {len(all_series_themes)} series with themes for group {group_id}")
            return all_series_themes
            
        except Exception as e:
            print(f"❌ Error getting all series themes for group {group_id}: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_series_themes_sync(self, group_id: str, series_name: str) -> List[Dict]:
        """Get all themes with trained models and guidelines for a series - EXACT same logic as Discord bot"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    print(f"❌ Invalid ObjectId format: {group_id}")
                    return []
            else:
                object_id = group_id
            
            # First get the group document
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group or "content_creation" not in group:
                print(f"❌ No group found or no content_creation field for group {group_id}")
                return []

            themes_list = []
            series_data = group.get("content_creation", {}).get(series_name, {})
            
            # Iterate through themes in the series (EXACT same logic as Discord bot)
            for theme_name, theme_data in series_data.items():
                if isinstance(theme_data, dict):  # Make sure it's a dictionary
                    # Check if this theme has both model and guidelines
                    if (theme_data.get("trained_model_version") and 
                        theme_data.get("thumbnail_guidelines")):
                        themes_list.append({
                            "name": theme_name,
                            "trained_model_version": theme_data["trained_model_version"],
                            "thumbnail_guidelines": theme_data["thumbnail_guidelines"],
                            "created_at": theme_data.get("model_trained_at", datetime.utcnow())
                        })

            print(f"✅ Found {len(themes_list)} themes with trained models for series {series_name}")
            return themes_list

        except Exception as e:
            print(f"❌ Error getting themes for series {series_name}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_all_series_sync(self, group_id: str) -> List[Dict]:
        """Get all series for a group"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get all series for the group
            series_data = list(self.series.find({"group_id": object_id}))
            print(f"✅ Found {len(series_data)} total series for group {group_id}")
            return series_data
            
        except Exception as e:
            print(f"❌ Error getting all series: {e}")
            return []


    def get_subscriber_range_sync(self, range_str: str) -> tuple:
        """Get subscriber range from string - EXACT same logic as Discord bot"""
        if range_str == "0-10K":
            return 0, 10000
        elif range_str == "10K-100K":
            return 10000, 100000
        elif range_str == "100K-1M":
            return 100000, 1000000
        elif range_str == "1M+":
            return 1000000, None
        else:
            return None, None

    def get_competitor_channels_sync(self, group_id: str) -> List[Dict]:
        """Get competitor channels for a group"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get group to find competitors
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return []
            
            # Get competitor details from competitor_channels collection
            competitor_channel_ids = group.get("competitor_channels", [])
            competitors = list(self.channels.find({"_id": {"$in": competitor_channel_ids}}))
            
            print(f"✅ Found {len(competitors)} competitor channels for group {group_id}")
            return competitors
            
        except Exception as e:
            print(f"❌ Error getting competitor channels: {e}")
            return []

    def get_channel_data_sync(self, channel_id: str) -> Dict:
        """Get channel data by ID"""
        try:
            channel = self.channels.find_one({"_id": channel_id})
            return channel if channel else {}
        except Exception as e:
            print(f"❌ Error getting channel data: {e}")
            return {}

    def get_series_data_by_name_sync(self, group_id: str, series_name: str) -> Dict:
        """Get series data by name - matches Discord bot's approach"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return {}
            else:
                object_id = group_id
            
            # Get group from groups collection (matches Discord bot approach)
            group = self.groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ Group not found: {group_id}")
                return {}
            
            # Get series data from main channel data
            main_channel_data = group.get('main_channel_data', {})
            main_series_data = main_channel_data.get('series_data', [])
            
            for series in main_series_data:
                if series.get('name', '').lower() == series_name.lower():
                    return series
            
            # Get series data from competitors data
            competitors = group.get('competitors', [])
            for competitor in competitors:
                competitor_series_data = competitor.get('series_data', [])
                for series in competitor_series_data:
                    if series.get('name', '').lower() == series_name.lower():
                        return series
            
            print(f"❌ Series '{series_name}' not found in group {group_id}")
            return {}
            
        except Exception as e:
            print(f"❌ Error getting series data by name: {e}")
            return {}

    def get_themes_data_sync(self, group_id: str) -> List[Dict]:
        """Get themes data for a group - matches Discord bot's approach"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get group from groups collection (not competitor_groups)
            group = self.groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ Group not found: {group_id}")
                return []
            
            themes_data = []
            
            # Get themes from main channel data
            main_channel_data = group.get('main_channel_data', {})
            main_series_data = main_channel_data.get('series_data', [])
            
            for series in main_series_data:
                for theme in series.get('themes', []):
                    themes_data.append({
                        'name': theme.get('name', ''),
                        'description': theme.get('description', ''),
                        'topics': theme.get('topics', [])
                    })
            
            # Get themes from competitors data
            competitors = group.get('competitors', [])
            for competitor in competitors:
                competitor_series_data = competitor.get('series_data', [])
                for series in competitor_series_data:
                    for theme in series.get('themes', []):
                        themes_data.append({
                            'name': theme.get('name', ''),
                            'description': theme.get('description', ''),
                            'topics': theme.get('topics', [])
                        })
            
            return themes_data
            
        except Exception as e:
            print(f"❌ Error getting themes data: {str(e)}")
            return []

    def get_outlier_videos_sync(self, group_id: str, limit: int = 10) -> List[Dict]:
        """Get outlier videos for a group"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            # Get outlier videos from video_outliers collection
            outliers = list(self.video_outliers.find({"group_id": object_id}).sort("outlier_score", -1).limit(limit))
            
            print(f"✅ Found {len(outliers)} outlier videos for group {group_id}")
            return outliers
            
        except Exception as e:
            print(f"❌ Error getting outlier videos: {e}")
            return []

    def get_top_themes_sync(self, group_id: str, timeframe: str = '90d', limit: int = 5) -> List[Dict]:
        """Get top themes for a group - REAL DATA"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            # Get themes from series data
            pipeline = [
                {"$match": {"group_id": object_id}},
                {"$unwind": "$themes"},
                {"$group": {
                    "_id": "$themes.name",
                    "total_views": {"$sum": "$themes.total_views"},
                    "video_count": {"$sum": 1},
                    "avg_views": {"$avg": "$themes.avg_views"}
                }},
                {"$sort": {"total_views": -1}},
                {"$limit": limit}
            ]
            
            themes = list(self.series.aggregate(pipeline))
            return themes
            
        except Exception as e:
            print(f"❌ Error getting top themes: {e}")
            return []

    # Content Creation Database Methods
    def get_plot_outline_sync(self, group_id: str, series_name: str, theme_name: str) -> Optional[str]:
        """Get plot outline for content creation"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            content = self.content_creation.find_one({
                "group_id": object_id,
                "series_name": series_name,
                "theme_name": theme_name
            })
            
            return content.get('plot_outline') if content else None
            
        except Exception as e:
            print(f"❌ Error getting plot outline: {e}")
            return None

    def get_script_breakdown_sync(self, group_id: str, series_name: str, theme_name: str) -> Optional[Dict]:
        """Get script breakdown for content creation - matches main database structure"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            # Use the SAME structure as main database - look in competitor_groups
            safe_series_name = series_name.replace('.', '_').replace(' ', '_')
            safe_theme_name = theme_name.replace('.', '_').replace(' ', '_')
            
            group = self.competitor_groups.find_one(
                {"_id": object_id},
                {f"content_creation.{safe_series_name}.{safe_theme_name}": 1}
            )
            
            if group and 'content_creation' in group:
                content = group['content_creation'].get(safe_series_name, {}).get(safe_theme_name, {})
                script_breakdown = content.get('script_breakdown')
                guidelines = content.get('guidelines')
                
                # Return ALL the data the frontend needs
                if script_breakdown or guidelines:
                    return {
                        'script_breakdown': script_breakdown,
                        'guidelines': guidelines,
                        'script_breakdown_doc_url': content.get('script_breakdown_doc_url'),
                        'plot_outline_doc_url': content.get('plot_outline_doc_url'),
                        'full_script_doc_url': content.get('full_script_doc_url'),
                        'thumbnail_guidelines': content.get('thumbnail_guidelines'),
                        'trained_model_version': content.get('trained_model_version')
                    }
            return None
            
        except Exception as e:
            print(f"❌ Error getting script breakdown: {e}")
            return None

    def get_full_script_sync(self, group_id: str, series_name: str, theme_name: str) -> Optional[str]:
        """Get full script for content creation"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            content = self.content_creation.find_one({
                "group_id": object_id,
                "series_name": series_name,
                "theme_name": theme_name
            })
            
            return content.get('full_script') if content else None
            
        except Exception as e:
            print(f"❌ Error getting full script: {e}")
            return None

    def get_thumbnail_guidelines_sync(self, group_id: str, series_name: str, theme_name: str) -> Optional[str]:
        """Get thumbnail guidelines for content creation"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            content = self.content_creation.find_one({
                "group_id": object_id,
                "series_name": series_name,
                "theme_name": theme_name
            })
            
            return content.get('thumbnail_guidelines') if content else None
            
        except Exception as e:
            print(f"❌ Error getting thumbnail guidelines: {e}")
            return None

    def get_thumbnail_urls_sync(self, group_id: str, series_name: str, theme_name: str) -> List[str]:
        """Get thumbnail URLs for content creation"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            content = self.content_creation.find_one({
                "group_id": object_id,
                "series_name": series_name,
                "theme_name": theme_name
            })
            
            return content.get('thumbnail_urls', []) if content else []
            
        except Exception as e:
            print(f"❌ Error getting thumbnail URLs: {e}")
            return []

    def save_thumbnail_guidelines_sync(self, group_id: str, series_name: str, theme_name: str, guidelines: str) -> bool:
        """Save thumbnail guidelines for content creation"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {
                    "$set": {
                        "thumbnail_guidelines": guidelines,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving thumbnail guidelines: {e}")
            return False

    def get_example_titles_sync(self, group_id: str, series_name: str, theme_name: str) -> List[str]:
        """Get example titles for content creation - matches Discord bot's approach"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            # Get group from groups collection
            group = self.groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ Group not found: {group_id}")
                return []
            
            example_titles = []
            
            # Get example titles from main channel data
            main_channel_data = group.get('main_channel_data', {})
            main_series_data = main_channel_data.get('series_data', [])
            
            for series in main_series_data:
                if series.get('name', '').lower() == series_name.lower():
                    for theme in series.get('themes', []):
                        if theme.get('name', '').lower() == theme_name.lower():
                            # Collect all example titles from topics
                            for topic in theme.get('topics', []):
                                example = topic.get('example')
                                if example:
                                    example_titles.append(example)
            
            # Get example titles from competitors data
            competitors = group.get('competitors', [])
            for competitor in competitors:
                competitor_series_data = competitor.get('series_data', [])
                for series in competitor_series_data:
                    if series.get('name', '').lower() == series_name.lower():
                        for theme in series.get('themes', []):
                            if theme.get('name', '').lower() == theme_name.lower():
                                # Collect all example titles from topics
                                for topic in theme.get('topics', []):
                                    example = topic.get('example')
                                    if example:
                                        example_titles.append(example)
            
            print(f"✅ Found {len(example_titles)} example titles for {series_name}/{theme_name}")
            return example_titles
            
        except Exception as e:
            print(f"❌ Error getting example titles: {str(e)}")
            return []

    def get_top_video_urls_sync(self, group_id: str, series_name: str, theme_name: str, limit: int = 3) -> List[str]:
        """Get top video URLs for script breakdown - matches Discord bot's approach"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            # Get group from groups collection
            group = self.groups.find_one({"_id": object_id})
            if not group:
                print(f"❌ Group not found: {group_id}")
                return []
            
            video_urls = []
            
            # Get video URLs from main channel data
            main_channel_data = group.get('main_channel_data', {})
            main_series_data = main_channel_data.get('series_data', [])
            
            for series in main_series_data:
                if series.get('name', '').lower() == series_name.lower():
                    for theme in series.get('themes', []):
                        if theme.get('name', '').lower() == theme_name.lower():
                            # Collect video URLs from topics
                            for topic in theme.get('topics', []):
                                video_url = topic.get('video_url')
                                if video_url and len(video_urls) < limit:
                                    video_urls.append(video_url)
            
            # Get video URLs from competitors data
            competitors = group.get('competitors', [])
            for competitor in competitors:
                competitor_series_data = competitor.get('series_data', [])
                for series in competitor_series_data:
                    if series.get('name', '').lower() == series_name.lower():
                        for theme in series.get('themes', []):
                            if theme.get('name', '').lower() == theme_name.lower():
                                # Collect video URLs from topics
                                for topic in theme.get('topics', []):
                                    video_url = topic.get('video_url')
                                    if video_url and len(video_urls) < limit:
                                        video_urls.append(video_url)
            
            print(f"✅ Found {len(video_urls)} video URLs for {series_name}/{theme_name}")
            return video_urls[:limit]
            
        except Exception as e:
            print(f"❌ Error getting top video URLs: {str(e)}")
            return []

    def save_content_creation_data_sync(self, group_id: str, series_name: str, theme_name: str, data: Dict) -> bool:
        """Save content creation data"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            data['group_id'] = object_id
            data['series_name'] = series_name
            data['theme_name'] = theme_name
            data['updated_at'] = datetime.utcnow()
            
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {"$set": data},
                upsert=True
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving content creation data: {e}")
            return False

    def get_content_creation_data_sync(self, group_id: str, series_name: str, theme_name: str) -> Optional[Dict]:
        """Get content creation data"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            content = self.content_creation.find_one({
                "group_id": object_id,
                "series_name": series_name,
                "theme_name": theme_name
            })
            
            return content
            
        except Exception as e:
            print(f"❌ Error getting content creation data: {e}")
            return None
    
    async def get_content_creation_data(self, group_id: str, series_name: str, theme_name: str) -> Optional[Dict]:
        """Get content creation data (async)"""
        return self.get_content_creation_data_sync(group_id, series_name, theme_name)

    def update_content_creation_field_sync(self, group_id: str, series_name: str, theme_name: str, field: str, value: Any) -> bool:
        """Update a specific field in content creation data"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {
                    "$set": {
                        field: value,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating content creation field: {e}")
            return False

# Duplicate method removed - using the correct one above that looks in competitor_groups

    def update_script_breakdown_doc_url(self, group_id: str, series_name: str, theme_name: str, doc_url: str) -> bool:
        """Update script breakdown doc URL"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
                
            safe_series_name = series_name.replace('.', '_').replace(' ', '_')
            safe_theme_name = theme_name.replace('.', '_').replace(' ', '_')
            
            result = self.competitor_groups.update_one(
                {"_id": object_id},
                {"$set": {f"content_creation.{safe_series_name}.{safe_theme_name}.script_breakdown_doc_url": doc_url}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating doc URL: {e}")
            return False

    def save_script_breakdown_sync(self, group_id: str, series_name: str, theme_name: str, breakdown: str, guidelines: str) -> bool:
        """Save script breakdown and guidelines"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
                
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {
                    "$set": {
                        "script_breakdown": breakdown,
                        "guidelines": guidelines,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"❌ Error saving script breakdown: {e}")
            return False

    def save_plot_outline_sync(self, group_id: str, series_name: str, theme_name: str, outline: str, doc_url: str = None) -> bool:
        """Save plot outline"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
                
            update_data = {
                "plot_outline": outline,
                "updated_at": datetime.utcnow()
            }
            if doc_url:
                update_data["plot_outline_url"] = doc_url
                
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {"$set": update_data},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"❌ Error saving plot outline: {e}")
            return False

    def save_full_script_sync(self, group_id: str, series_name: str, theme_name: str, script: str) -> bool:
        """Save full script"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
                
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {
                    "$set": {
                        "full_script": script,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"❌ Error saving full script: {e}")
            return False

    def save_voice_over_url_sync(self, group_id: str, series_name: str, theme_name: str, video_title: str, voice_over_url: str) -> bool:
        """Save voice-over URL"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
                
            self.content_creation.update_one(
                {
                    "group_id": object_id,
                    "series_name": series_name,
                    "theme_name": theme_name
                },
                {
                    "$set": {
                        "voice_over_url": voice_over_url,
                        "video_title": video_title,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as e:
            print(f"❌ Error saving voice-over URL: {e}")
            return False

    def get_top_video_urls_sync(self, group_id: str, series_name: str, theme_name: str, limit: int = 3) -> List[str]:
        """Get top video URLs for a series and theme - matches Discord bot's approach"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            # Use the same aggregation pipeline as Discord bot
            pipeline = [
                {'$match': {'_id': object_id}},
                {'$project': {
                    'all_series_data': {
                        '$concatArrays': [
                            '$competitors.series_data',
                            ['$main_channel_data.series_data']
                        ]
                    }
                }},
                {'$unwind': '$all_series_data'},
                {'$unwind': '$all_series_data'},
                {'$match': {
                    'all_series_data.name': series_name,
                    'all_series_data.themes.name': theme_name
                }},
                {'$unwind': '$all_series_data.themes'},
                {'$match': {'all_series_data.themes.name': theme_name}},
                {'$unwind': '$all_series_data.themes.topics'},
                {'$sort': {'all_series_data.themes.topics.views': -1}},
                {'$limit': limit},
                {'$project': {'video_id': '$all_series_data.themes.topics.id'}}
            ]
            
            result = list(self.competitor_groups.aggregate(pipeline))
            video_ids = [doc['video_id'] for doc in result if 'video_id' in doc]
            
            print(f"✅ Found {len(video_ids)} video URLs for {series_name} - {theme_name}")
            return video_ids
            
        except Exception as e:
            print(f"❌ Error getting top video URLs: {e}")
            return []

    def get_all_series_thumbnails_sync(self, group_id: str, series_name: str) -> List[str]:
        """Get ALL thumbnail URLs for an entire series (for <12 fallback) - synchronous version"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            cursor = self.competitor_groups.find_one(
                {"_id": object_id},
                {"analysis_result.video_data": 1}
            )
            
            if not cursor or "analysis_result" not in cursor:
                return []
            
            videos = cursor["analysis_result"].get("video_data", [])
            
            # Filter by series only (all themes), get thumbnails
            series_thumbnails = []
            for video in videos:
                if (video.get("series", "").lower() == series_name.lower() and 
                    video.get("thumbnail_url")):
                    series_thumbnails.append(video["thumbnail_url"])
            
            # Remove duplicates while preserving order
            unique_thumbnails = list(dict.fromkeys(series_thumbnails))
            
            print(f"✅ Found {len(unique_thumbnails)} series thumbnails for {series_name}")
            return unique_thumbnails
            
        except Exception as e:
            print(f"❌ Error getting all series thumbnails: {e}")
            return []
            
    def get_video_data_sync(self, group_id: str, video_id: str) -> Dict:
        """Get video data including transcript and metadata - synchronous version with YouTube fallback"""
        try:
            if isinstance(group_id, str):
                object_id = ObjectId(group_id)
            else:
                object_id = group_id
            
            cursor = self.competitor_groups.find_one(
                {"_id": object_id},
                {"analysis_result.video_data": 1}
            )
            
            video_data = {}
            
            # First, try to get data from database
            if cursor and "analysis_result" in cursor:
                videos = cursor["analysis_result"].get("video_data", [])
                
                for video in videos:
                    if video.get("id") == video_id or video.get("url") == video_id:
                        video_data = {
                            "id": video.get("id", video_id),
                            "title": video.get("title", ""),
                            "description": video.get("description", ""),
                            "duration": video.get("duration", 600),
                            "transcript": video.get("transcript", ""),
                            "views": video.get("views", 0),
                            "thumbnail_url": video.get("thumbnail_url", "")
                        }
                        break
            
            # If no transcript found in database, try YouTube service as fallback
            if not video_data.get("transcript") or len(video_data.get("transcript", "").strip()) < 50:
                try:
                    # Import simplified YouTube wrapper
                    from services.youtube_wrapper import youtube_wrapper
                    
                    print(f"🔍 Fetching real video data from YouTube for {video_id}")
                    
                    # Get transcript from YouTube
                    transcript = youtube_wrapper.get_video_transcript(video_id)
                    duration = youtube_wrapper.get_video_duration(video_id)
                    video_info = youtube_wrapper.get_video_info(video_id)
                    
                    if transcript:
                        # Update with real YouTube data
                        video_data.update({
                            "id": video_id,
                            "transcript": transcript,
                            "duration": duration or 600,
                            "title": video_info.get("title", video_data.get("title", "")),
                            "description": video_info.get("description", video_data.get("description", "")),
                            "views": video_data.get("views", 0),
                            "thumbnail_url": video_data.get("thumbnail_url", "")
                        })
                        print(f"✅ Retrieved real transcript ({len(transcript)} chars) for {video_id}")
                    else:
                        print(f"⚠️ No transcript available from YouTube for {video_id}")
                        
                except Exception as yt_error:
                    print(f"⚠️ YouTube service fallback failed for {video_id}: {yt_error}")
            
            return video_data if video_data else {}
            
        except Exception as e:
            print(f"❌ Error getting video data: {e}")
            return {}

    # YouTube Channel Management Methods
    def get_user_youtube_channels_sync(self, user_id):
        """Get all YouTube channels connected by a specific user - synchronous version"""
        return asyncio.run(self.get_user_youtube_channels(user_id))
    
    async def get_user_youtube_channels(self, user_id):
        """Get all YouTube channels connected by a specific user"""
        try:
            # Try to look up by ObjectId first (if user_id is MongoDB ObjectId)
            try:
                user = self.web_users.find_one({"_id": ObjectId(user_id)})
            except:
                # If that fails, try by Discord ID
                user = self.web_users.find_one({"discord_id": user_id})
            
            if not user:
                return []
            return user.get("youtube_channels", [])
        except Exception as e:
            print(f"Error getting user YouTube channels: {e}")
            return []
    
    def save_channel_oauth_credentials_sync(self, user_id, channel_id, credentials, channel_title=None):
        """Save YouTube OAuth credentials - synchronous version"""
        return asyncio.run(self.save_channel_oauth_credentials(user_id, channel_id, credentials, channel_title))
    
    async def save_channel_oauth_credentials(self, user_id, channel_id, credentials, channel_title=None):
        """Save YouTube OAuth credentials for a specific user's channel"""
        try:
            from datetime import datetime, timezone
            
            # Format the data with timestamps
            channel_oauth = {
                "channel_id": channel_id,
                "title": channel_title,
                "oauth_data": credentials,
                "connected_at": datetime.now(timezone.utc)
            }
            
            # First, try to get the user by Discord ID (users collection)
            # This is the same method used in auth.py
            user_from_users = None
            try:
                user_from_users = self.users.find_one({"discord_id": str(user_id)})
            except:
                pass
            
            # Determine which collection to use and build query
            # Try ObjectId first (if user_id is MongoDB ObjectId)
            try:
                user_query = {"_id": ObjectId(user_id)}
                user = self.web_users.find_one(user_query)
            except:
                # If that fails, try by Discord ID
                # First check if user exists in users collection (Discord bot users)
                if user_from_users:
                    # User exists in users collection, check if they exist in web_users
                    # by Discord ID or by their _id
                    user_query = {"discord_id": str(user_id)}
                    user = self.web_users.find_one(user_query)
                    
                    # If user doesn't exist in web_users, create them there
                    if not user:
                        print(f"📝 Creating web_users entry for Discord user {user_id}")
                        web_user_data = {
                            "discord_id": str(user_id),
                            "username": user_from_users.get("username", "Unknown"),
                            "youtube_channels": []
                        }
                        self.web_users.insert_one(web_user_data)
                        user = self.web_users.find_one(user_query)
                else:
                    # Try direct lookup by Discord ID in web_users
                    user_query = {"discord_id": str(user_id)}
                    user = self.web_users.find_one(user_query)
            
            # Verify user exists
            if not user:
                print(f"❌ User not found in web_users: {user_id}")
                return False
            
            # Check if this channel is already connected for this web user
            result = self.web_users.update_one(
                {
                    **user_query,
                    "youtube_channels.channel_id": channel_id
                },
                {"$set": {"youtube_channels.$.oauth_data": credentials}}
            )
            
            # If channel wasn't found, add it as a new entry
            if result.matched_count == 0:
                result = self.web_users.update_one(
                    user_query,
                    {"$push": {"youtube_channels": channel_oauth}}
                )
                # Verify the push actually succeeded
                if result.matched_count == 0:
                    print(f"❌ Failed to add channel - user not found: {user_id}")
                    return False
            
            print(f"✅ Saved OAuth credentials for channel {channel_id} for user {user_id}")
            return True
            
        except Exception as e:
            print(f"Error saving channel OAuth credentials: {e}")
            return False
    
    def get_channel_oauth_credentials_sync(self, user_id, channel_id):
        """Get YouTube OAuth credentials - synchronous version"""
        return asyncio.run(self.get_channel_oauth_credentials(user_id, channel_id))
    
    async def get_channel_oauth_credentials(self, user_id, channel_id):
        """Get YouTube OAuth credentials for a specific channel"""
        try:
            # Look up web user by ID
            user = self.web_users.find_one({"_id": ObjectId(user_id)})
            if user and "youtube_channels" in user:
                for channel in user.get("youtube_channels", []):
                    if channel.get("channel_id") == channel_id:
                        return channel.get("oauth_data")
            
            # Fallback to old method (group-based credentials)
            # This is for backward compatibility during migration
            group = self.competitor_groups.find_one(
                {"connected_channels.channel_id": channel_id}
            )
            if group:
                for channel in group.get("connected_channels", []):
                    if channel.get("channel_id") == channel_id:
                        return channel.get("oauth_data")
            
            return None
        except Exception as e:
            print(f"Error getting channel OAuth credentials: {e}")
            return None

    # DISCORD BOT COMPATIBILITY METHODS (synchronous versions)
    def create_competitor_group(self, group_data: Dict):
        """Synchronous version of Discord bot's create_competitor_group"""
        if 'name' not in group_data:
            group_data['name'] = f"Unnamed Group {str(ObjectId())[-6:]}"
        group_data['createdAt'] = datetime.utcnow()
        group_data['lastUpdated'] = datetime.utcnow()
        group_data['is_premium'] = group_data.get('is_premium', False)
        group_data['is_public'] = group_data.get('is_admin', False) and not group_data['is_premium']
        group_data['allowed_users'] = [group_data['user_id']]  # Creator always has access
        group_data['main_channel_data'] = group_data.get('main_channel_data', {})
        group_data['main_channel_data']['videos'] = group_data.get('videos', [])
        result = self.competitor_groups.insert_one(group_data)
        return str(result.inserted_id)

    def update_competitor_group(self, group_id: str, update_data: Dict):
        """Synchronous version of Discord bot's update_competitor_group"""
        if isinstance(group_id, str):
            group_id = ObjectId(group_id)
        update_data['lastUpdated'] = datetime.utcnow()
        result = self.competitor_groups.update_one(
            {"_id": group_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    def get_competitor_group(self, group_id: str) -> Dict:
        """Synchronous version of Discord bot's get_competitor_group"""
        if isinstance(group_id, str):
            group_id = ObjectId(group_id)
        return self.competitor_groups.find_one({"_id": group_id})

    def add_competitor_to_group(self, group_id: str, competitor: Dict) -> bool:
        """Synchronous version of Discord bot's add_competitor_to_group (for competitor objects)"""
        try:
            if isinstance(group_id, str):
                group_id = ObjectId(group_id)
            
            result = self.competitor_groups.update_one(
                {'_id': group_id},
                {'$addToSet': {'competitors': competitor}}
            )
            
            if result.modified_count > 0:
                print(f"✅ Added competitor {competitor.get('channel_id')} to group {group_id}")
                return True
            else:
                print(f"⚠️ Competitor {competitor.get('channel_id')} was not added to group {group_id} (possibly already exists)")
                return False
        except Exception as e:
            print(f"❌ Error adding competitor to group: {str(e)}")
            return False

    # ========================================
    # INSTAGRAM STUDIO DATABASE METHODS
    # ========================================
    
    def add_instagram_account(self, user_id: str, username: str, password: str, account_type: str, niche: str = 'general') -> bool:
        """Add Instagram account with encrypted credentials"""
        try:
            import base64
            # Encrypt password (use proper encryption in production)
            encrypted_password = base64.b64encode(password.encode()).decode()
            
            account_data = {
                "user_id": user_id,
                "username": username,
                "password": encrypted_password,
                "account_type": account_type,  # 'source', 'target', or 'both'
                "niche": niche,  # Content niche for targeted uploads
                "status": "active",
                "follower_count": "0",  # Will be updated when we fetch account info
                "created_at": datetime.utcnow(),
                "last_used": None
            }
            
            result = self.instagram_accounts.insert_one(account_data)
            return result.inserted_id is not None
        except Exception as e:
            print(f"Error adding Instagram account: {e}")
            return False
    
    def get_instagram_accounts(self, user_id: str) -> List[Dict]:
        """Get user's Instagram accounts"""
        try:
            accounts = list(self.instagram_accounts.find({"user_id": user_id}))
            
            # Don't decrypt passwords for security, just mark as encrypted
            for account in accounts:
                account["password"] = "***ENCRYPTED***"
                account["_id"] = str(account["_id"])
                account["id"] = str(account["_id"])
            
            return accounts
        except Exception as e:
            print(f"Error getting Instagram accounts: {e}")
            return []
    
    def create_instagram_job(self, user_id: str, job_type: str, status: str = 'pending', **kwargs) -> str:
        """Create Instagram processing job"""
        try:
            job_data = {
                "user_id": user_id,
                "job_type": job_type,  # 'download_all', 'download_from_url', 'process_videos', 'bulk_upload'
                "status": status,
                "progress": 0,
                "step": "Initializing...",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                **kwargs  # Additional job-specific data
            }
            
            result = self.instagram_jobs.insert_one(job_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating Instagram job: {e}")
            return None
    
    def get_instagram_jobs(self, user_id: str) -> List[Dict]:
        """Get user's Instagram processing jobs"""
        try:
            jobs = list(self.instagram_jobs.find({"user_id": user_id}).sort("created_at", -1).limit(20))
            
            for job in jobs:
                job["_id"] = str(job["_id"])
                job["id"] = str(job["_id"])
                # Format job title based on type
                if job["job_type"] == "download_all":
                    job["title"] = f"Download from account"
                elif job["job_type"] == "download_from_url":
                    job["title"] = f"Download from @{job.get('target_username', 'unknown')}"
                elif job["job_type"] == "process_videos":
                    job["title"] = f"Process {len(job.get('video_ids', []))} videos"
                elif job["job_type"] == "bulk_upload":
                    job["title"] = f"Upload {len(job.get('video_ids', []))} videos"
                else:
                    job["title"] = job["job_type"].replace('_', ' ').title()
            
            return jobs
        except Exception as e:
            print(f"Error getting Instagram jobs: {e}")
            return []
    
    def add_instagram_video(self, user_id: str, video_data: Dict) -> str:
        """Add downloaded Instagram video"""
        try:
            video_data.update({
                "user_id": user_id,
                "status": "downloaded",  # 'pending', 'downloaded', 'processed', 'uploaded'
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            
            result = self.instagram_videos.insert_one(video_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error adding Instagram video: {e}")
            return None
    
    def get_instagram_videos(self, user_id: str) -> List[Dict]:
        """Get user's Instagram videos"""
        try:
            videos = list(self.instagram_videos.find({"user_id": user_id}).sort("created_at", -1))
            
            for video in videos:
                video["_id"] = str(video["_id"])
                video["id"] = str(video["_id"])
            
            return videos
        except Exception as e:
            print(f"Error getting Instagram videos: {e}")
            return []
    
    def update_instagram_video_status(self, video_id: str, status: str, **kwargs) -> bool:
        """Update Instagram video status"""
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow(),
                **kwargs
            }
            
            result = self.instagram_videos.update_one(
                {"_id": ObjectId(video_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating Instagram video status: {e}")
            return False
    
    def update_instagram_job(self, job_id: str, **kwargs) -> bool:
        """Update Instagram job progress"""
        try:
            update_data = {
                "updated_at": datetime.utcnow(),
                **kwargs
            }
            
            result = self.instagram_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating Instagram job: {e}")
            return False
    
    def create_posting_schedule(self, user_id: str, account_id: str, video_ids: List[str], posts_per_day: int = 3) -> str:
        """Create optimized posting schedule"""
        try:
            from services.instagram_scheduler import InstagramScheduler
            scheduler = InstagramScheduler()
            
            # Generate optimal schedule
            schedule_items = scheduler.create_posting_schedule(account_id, video_ids, posts_per_day)
            
            schedule_data = {
                "user_id": user_id,
                "account_id": account_id,
                "posts_per_day": posts_per_day,
                "total_videos": len(video_ids),
                "schedule_items": schedule_items,
                "status": "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = self.instagram_schedule.insert_one(schedule_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating posting schedule: {e}")
            return None
    
    def get_posting_schedule(self, user_id: str, account_id: str = None) -> List[Dict]:
        """Get posting schedule for user/account"""
        try:
            query = {"user_id": user_id}
            if account_id:
                query["account_id"] = account_id
            
            schedules = list(self.instagram_schedule.find(query).sort("created_at", -1))
            
            for schedule in schedules:
                schedule["_id"] = str(schedule["_id"])
                schedule["id"] = str(schedule["_id"])
            
            return schedules
        except Exception as e:
            print(f"Error getting posting schedule: {e}")
            return []
    
    def get_pending_posts(self) -> List[Dict]:
        """Get posts scheduled for now or past due"""
        try:
            now = datetime.utcnow()
            
            # Find all active schedules with pending posts
            schedules = list(self.instagram_schedule.find({"status": "active"}))
            
            pending_posts = []
            for schedule in schedules:
                for item in schedule.get("schedule_items", []):
                    if item.get("status") == "scheduled":
                        scheduled_time = item.get("scheduled_time")
                        if isinstance(scheduled_time, datetime) and scheduled_time <= now:
                            pending_posts.append({
                                "schedule_id": str(schedule["_id"]),
                                "video_id": item["video_id"],
                                "account_id": item["account_id"],
                                "scheduled_time": scheduled_time,
                                "user_id": schedule["user_id"]
                            })
            
            return pending_posts
        except Exception as e:
            print(f"Error getting pending posts: {e}")
            return []
    
    def mark_post_as_uploaded(self, schedule_id: str, video_id: str) -> bool:
        """Mark a scheduled post as uploaded"""
        try:
            result = self.instagram_schedule.update_one(
                {"_id": ObjectId(schedule_id), "schedule_items.video_id": video_id},
                {"$set": {"schedule_items.$.status": "uploaded", "schedule_items.$.uploaded_at": datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error marking post as uploaded: {e}")
            return False
    
    # ===== VFX METHODS =====
    
    def save_vfx_guidelines(self, group_id: str, series_name: str, theme_name: str, guidelines: Dict) -> bool:
        """Save VFX guidelines for a series/theme (similar to thumbnail guidelines)"""
        try:
            document = {
                'group_id': group_id,
                'series_name': series_name,
                'theme_name': theme_name,
                'guidelines': guidelines,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            # Upsert - update if exists, create if not
            result = self.vfx_guidelines.update_one(
                {
                    'group_id': group_id,
                    'series_name': series_name,
                    'theme_name': theme_name
                },
                {'$set': document},
                upsert=True
            )
            
            return True
        except Exception as e:
            print(f"Error saving VFX guidelines: {e}")
            return False
    
    def get_vfx_guidelines(self, group_id: str, series_name: str, theme_name: str) -> Optional[Dict]:
        """Get VFX guidelines for a series/theme"""
        try:
            result = self.vfx_guidelines.find_one({
                'group_id': group_id,
                'series_name': series_name,
                'theme_name': theme_name
            })
            
            if result:
                return result.get('guidelines')
            return None
        except Exception as e:
            print(f"Error getting VFX guidelines: {e}")
            return None
    
    def save_vfx_breakdown(self, user_id: str, group_id: str, series_name: str, theme_name: str, 
                          script_breakdown_id: str, vfx_breakdown: List[Dict]) -> Optional[str]:
        """Save VFX breakdown for a specific script"""
        try:
            document = {
                'user_id': user_id,
                'group_id': group_id,
                'series_name': series_name,
                'theme_name': theme_name,
                'script_breakdown_id': script_breakdown_id,
                'vfx_breakdown': vfx_breakdown,
                'created_at': datetime.utcnow(),
                'status': 'generated'
            }
            
            result = self.vfx_breakdowns.insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error saving VFX breakdown: {e}")
            return None
    
    # ===== ADMIN METHODS =====
    
    def get_all_groups_sync(self, include_private=False) -> List[Dict]:
        """Get all competitor groups with optional private filter"""
        try:
            query = {}
            if not include_private:
                query['is_public'] = True
            return list(self.competitor_groups.find(query))
        except Exception as e:
            print(f"Error getting all groups: {e}")
            return []
    
    def get_all_users_sync(self) -> List[Dict]:
        """Get all users from database"""
        try:
            return list(self.users.find({}))
        except Exception as e:
            print(f"Error getting all users: {e}")
            return []
    
    def get_group_by_id_sync(self, group_id: str, full_document=False) -> Optional[Dict]:
        """Get group by ID with option for full document"""
        try:
            if full_document:
                return self.competitor_groups.find_one({'_id': ObjectId(group_id)})
            else:
                # Return basic info only
                return self.competitor_groups.find_one(
                    {'_id': ObjectId(group_id)},
                    {'name': 1, 'is_public': 1, 'is_premium': 1, 'price': 1, 'created_at': 1}
                )
        except Exception as e:
            print(f"Error getting group by ID: {e}")
            return None
    
    def get_user_by_id_sync(self, user_id: str) -> Optional[Dict]:
        """Get user by MongoDB ObjectId"""
        try:
            return self.users.find_one({'_id': ObjectId(user_id)})
        except Exception as e:
            print(f"Error getting user by ID: {e}")
            return None
    
    def update_user_sync(self, user_id: str, update_data: Dict) -> bool:
        """Update user information"""
        try:
            result = self.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating user: {e}")
            return False
    
    def assign_private_group_to_user_sync(self, user_id: str, group_id: str) -> bool:
        """Assign a private group to a user"""
        try:
            # Add user to group's assigned_users
            group_result = self.competitor_groups.update_one(
                {'_id': ObjectId(group_id)},
                {'$addToSet': {'assigned_users': user_id}}
            )
            
            # Add group to user's groups
            user_result = self.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$addToSet': {'groups': group_id}}
            )
            
            return group_result.modified_count > 0 or user_result.modified_count > 0
        except Exception as e:
            print(f"Error assigning group to user: {e}")
            return False
    
    def get_high_potential_channels_sync(self) -> List[Dict]:
        """Get all high potential channels"""
        try:
            return list(self.db['high_potential_channels'].find({}))
        except Exception as e:
            print(f"Error getting high potential channels: {e}")
            return []
    
    def delete_high_potential_channel_sync(self, channel_id: str) -> bool:
        """Delete a high potential channel"""
        try:
            result = self.db['high_potential_channels'].delete_one({'channel_id': channel_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting high potential channel: {e}")
            return False
    
    def clear_high_potential_channels_sync(self) -> int:
        """Clear all high potential channels and return count deleted"""
        try:
            result = self.db['high_potential_channels'].delete_many({})
            return result.deleted_count
        except Exception as e:
            print(f"Error clearing high potential channels: {e}")
            return 0
    
    def get_vfx_breakdown(self, breakdown_id: str) -> Optional[Dict]:
        """Get VFX breakdown by ID"""
        try:
            result = self.vfx_breakdowns.find_one({'_id': ObjectId(breakdown_id)})
            if result:
                result['_id'] = str(result['_id'])
            return result
        except Exception as e:
            print(f"Error getting VFX breakdown: {e}")
            return None
    
    def save_sora_generation(self, user_id: str, vfx_breakdown_id: str, scene_id: str, 
                           sora_prompt: str, video_url: Optional[str] = None, 
                           status: str = 'pending') -> Optional[str]:
        """Save Sora generation request/result"""
        try:
            document = {
                'user_id': user_id,
                'vfx_breakdown_id': vfx_breakdown_id,
                'scene_id': scene_id,
                'sora_prompt': sora_prompt,
                'video_url': video_url,
                'status': status,  # pending, generating, completed, failed
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = self.sora_generations.insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error saving Sora generation: {e}")
            return None
    
    def update_sora_generation(self, generation_id: str, video_url: str, status: str) -> bool:
        """Update Sora generation with result"""
        try:
            result = self.sora_generations.update_one(
                {'_id': ObjectId(generation_id)},
                {
                    '$set': {
                        'video_url': video_url,
                        'status': status,
                        'updated_at': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating Sora generation: {e}")
            return False
    
    def get_user_vfx_breakdowns(self, user_id: str) -> List[Dict]:
        """Get all VFX breakdowns for a user"""
        try:
            results = list(self.vfx_breakdowns.find(
                {'user_id': user_id},
                sort=[('created_at', -1)]
            ))
            
            for result in results:
                result['_id'] = str(result['_id'])
            
            return results
        except Exception as e:
            print(f"Error getting user VFX breakdowns: {e}")
            return []
    
    # ========================================
    # CAMPAIGN SYSTEM METHODS (NEW)
    # ========================================
    
    def _create_campaign_indexes(self):
        """Create indexes for campaign collections"""
        try:
            # Campaigns indexes
            self.campaigns.create_index([('user_id', 1)])
            self.campaigns.create_index([('status', 1)])
            self.campaigns.create_index([('created_at', -1)])
            self.campaigns.create_index([('user_id', 1), ('status', 1)])
            
            # Campaign channels indexes
            self.campaign_channels.create_index([('campaign_id', 1)])
            self.campaign_channels.create_index([('user_id', 1)])
            self.campaign_channels.create_index([('youtube_channel_id', 1)])
            self.campaign_channels.create_index([('status', 1)])
            self.campaign_channels.create_index([('platform', 1)])
            self.campaign_channels.create_index([('campaign_id', 1), ('status', 1)])
            
            # Campaign analytics indexes
            self.campaign_analytics.create_index([('campaign_id', 1), ('date', -1)])
            self.campaign_analytics.create_index([('channel_id', 1), ('date', -1)])
            self.campaign_analytics.create_index([('date', -1)])
        except Exception as e:
            print(f"Note: Campaign indexes may already exist: {e}")
    
    def _create_product_indexes(self):
        """Create indexes for products collection"""
        try:
            self.products.create_index([('user_id', 1)])
            self.products.create_index([('created_at', -1)])
        except Exception as e:
            print(f"Note: Product indexes may already exist: {e}")
    
    def _create_ig_tiktok_indexes(self):
        """Create indexes for ig_tiktok_groups collection"""
        try:
            self.ig_tiktok_groups.create_index([('user_id', 1)])
            self.ig_tiktok_groups.create_index([('platform', 1)])
            self.ig_tiktok_groups.create_index([('main_account_username', 1)])
            self.ig_tiktok_groups.create_index([('createdAt', -1)])
            self.ig_tiktok_groups.create_index([('user_id', 1), ('platform', 1)])
        except Exception as e:
            print(f"Note: IG/TikTok indexes may already exist: {e}")
    
    # Product Management Methods
    def create_product(self, user_id: str, name: str, url: str, **kwargs) -> Optional[str]:
        """Create a new product for a user"""
        try:
            # Handle user_id - convert to ObjectId if needed
            try:
                if isinstance(user_id, ObjectId):
                    user_id_obj = user_id
                elif isinstance(user_id, str) and len(user_id) == 24:
                    user_id_obj = ObjectId(user_id)
                else:
                    # Find user by Discord ID
                    user = self.users.find_one({"discord_id": str(user_id)})
                    if user:
                        user_id_obj = user['_id']
                    else:
                        user = self.web_users.find_one({"discord_id": str(user_id)})
                        if user:
                            user_id_obj = user['_id']
                        else:
                            print(f"❌ User not found for product creation: {user_id}")
                            return None
            except Exception as e:
                print(f"❌ Error converting user_id to ObjectId: {e}")
                return None
            
            product_data = {
                'user_id': user_id_obj,
                'name': name,
                'url': url,
                'product_type': kwargs.get('product_type', 'physical_product'),  # 'physical_product' or 'cpa_offer'
                'image_url': kwargs.get('image_url', ''),  # Product image for visual content
                'offer_url': kwargs.get('offer_url', ''),  # For CPA offers
                'price': kwargs.get('price'),
                'price_text': kwargs.get('price_text', ''),
                'description': kwargs.get('description', ''),
                'cpa_network': kwargs.get('cpa_network', ''),
                'cpa_offer_id': kwargs.get('cpa_offer_id', ''),
                'cpa_payout': kwargs.get('cpa_payout'),  # Expected payout per conversion
                'conversion_action': kwargs.get('conversion_action', 'purchase'),  # 'purchase', 'signup', 'install', 'trial'
                'tracking_url': kwargs.get('tracking_url', ''),
                'category': kwargs.get('category', ''),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = self.products.insert_one(product_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating product: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_user_products(self, user_id: str) -> List[Dict]:
        """Get all products for a user"""
        try:
            # Handle user_id lookup (same as campaigns)
            try:
                if isinstance(user_id, ObjectId):
                    user_id_obj = user_id
                elif isinstance(user_id, str) and len(user_id) == 24:
                    user_id_obj = ObjectId(user_id)
                else:
                    user = self.users.find_one({"discord_id": str(user_id)})
                    if user:
                        user_id_obj = user['_id']
                    else:
                        user = self.web_users.find_one({"discord_id": str(user_id)})
                        if user:
                            user_id_obj = user['_id']
                        else:
                            return []
            except Exception as e:
                print(f"❌ Error converting user_id to ObjectId: {e}")
                return []
            
            products = list(self.products.find({'user_id': user_id_obj}).sort('created_at', -1))
            for product in products:
                product['_id'] = str(product['_id'])
                product['user_id'] = str(product['user_id'])
            return products
        except Exception as e:
            print(f"Error getting user products: {e}")
            return []
    
    def get_product(self, product_id: str) -> Optional[Dict]:
        """Get product by ID"""
        try:
            product = self.products.find_one({'_id': ObjectId(product_id)})
            if product:
                product['_id'] = str(product['_id'])
                product['user_id'] = str(product['user_id'])
            return product
        except Exception as e:
            print(f"Error getting product: {e}")
            return None
    
    def update_product(self, product_id: str, updates: Dict) -> bool:
        """Update product"""
        try:
            updates['updated_at'] = datetime.utcnow()
            result = self.products.update_one(
                {'_id': ObjectId(product_id)},
                {'$set': updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating product: {e}")
            return False
    
    def delete_product(self, product_id: str) -> bool:
        """Delete product"""
        try:
            result = self.products.delete_one({'_id': ObjectId(product_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting product: {e}")
            return False
    
    # Campaign CRUD Methods
    def create_campaign(self, user_id: str, name: str, objective: str, **kwargs) -> Optional[str]:
        """Create a new campaign"""
        try:
            # Handle user_id - convert to ObjectId if it's a valid ObjectId string
            try:
                if isinstance(user_id, ObjectId):
                    user_id_obj = user_id
                elif isinstance(user_id, str) and len(user_id) == 24:
                    # Try to convert to ObjectId (MongoDB ObjectId is 24 hex chars)
                    user_id_obj = ObjectId(user_id)
                else:
                    # If not a valid ObjectId format, try to find user by Discord ID or other identifier
                    print(f"⚠️ user_id '{user_id}' is not a valid ObjectId format, attempting to find user...")
                    user = self.users.find_one({"discord_id": str(user_id)})
                    if user:
                        user_id_obj = user['_id']
                        print(f"✅ Found user by Discord ID, using MongoDB _id: {user_id_obj}")
                    else:
                        # Try web_users collection
                        user = self.web_users.find_one({"discord_id": str(user_id)})
                        if user:
                            user_id_obj = user['_id']
                            print(f"✅ Found user in web_users, using MongoDB _id: {user_id_obj}")
                        else:
                            print(f"❌ User not found with ID: {user_id}")
                            return None
            except Exception as e:
                print(f"❌ Error converting user_id to ObjectId: {e}")
                return None
            
            campaign_data = {
                'user_id': user_id_obj,
                'name': name,
                'objective': objective,  # 'product_sales', 'cashcow', 'brand_awareness', 'ecommerce' (legacy)
                'status': kwargs.get('status', 'active'),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                
                # Product info (for product_sales/ecommerce)
                'products': kwargs.get('products', []),
                
                # Product research (auto-detected from product URL)
                'product_research': kwargs.get('product_research', {}),
                
                # Default content strategy (from product research)
                'default_content_strategy': kwargs.get('default_content_strategy', {}),
                
                # Target demographics
                'target_demographics': kwargs.get('target_demographics', {}),
                
                # Lifecycle automation
                'lifecycle_automation_enabled': kwargs.get('lifecycle_automation_enabled', False),
                'lifecycle_rules': kwargs.get('lifecycle_rules', {
                    'testing_duration_days': 30,
                    'min_views_threshold': 1000,
                    'min_watch_time_percentage': 40
                }),
                
                # Budget & tracking
                'budget': kwargs.get('budget', {
                    'api_cost_limit': 500,
                    'target_revenue': 5000
                }),
                
                # Analytics (initialized)
                'total_api_cost': 0,
                'total_revenue': 0,
                'total_views': 0,
                'total_channels': 0
            }
            
            result = self.campaigns.insert_one(campaign_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating campaign: {e}")
            return None
    
    def get_campaign(self, campaign_id: str) -> Optional[Dict]:
        """Get campaign by ID"""
        try:
            campaign = self.campaigns.find_one({'_id': ObjectId(campaign_id)})
            if campaign:
                campaign['_id'] = str(campaign['_id'])
                campaign['user_id'] = str(campaign['user_id'])
            return campaign
        except Exception as e:
            print(f"Error getting campaign: {e}")
            return None
    
    def get_user_campaigns(self, user_id: str, status: Optional[str] = None) -> List[Dict]:
        """Get all campaigns for a user"""
        try:
            # Handle user_id - convert to ObjectId if it's a valid ObjectId string
            try:
                if isinstance(user_id, ObjectId):
                    user_id_obj = user_id
                elif isinstance(user_id, str) and len(user_id) == 24:
                    # Try to convert to ObjectId (MongoDB ObjectId is 24 hex chars)
                    user_id_obj = ObjectId(user_id)
                else:
                    # If not a valid ObjectId format, try to find user by Discord ID
                    user = self.users.find_one({"discord_id": str(user_id)})
                    if user:
                        user_id_obj = user['_id']
                    else:
                        # Try web_users collection
                        user = self.web_users.find_one({"discord_id": str(user_id)})
                        if user:
                            user_id_obj = user['_id']
                        else:
                            print(f"❌ User not found with ID: {user_id}")
                            return []
            except Exception as e:
                print(f"❌ Error converting user_id to ObjectId: {e}")
                return []
            
            query = {'user_id': user_id_obj}
            if status:
                query['status'] = status
            
            campaigns = list(self.campaigns.find(query).sort('created_at', -1))
            
            for campaign in campaigns:
                campaign['_id'] = str(campaign['_id'])
                campaign['user_id'] = str(campaign['user_id'])
            
            return campaigns
        except Exception as e:
            print(f"Error getting user campaigns: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def update_campaign(self, campaign_id: str, updates: Dict) -> bool:
        """Update campaign"""
        try:
            updates['updated_at'] = datetime.utcnow()
            result = self.campaigns.update_one(
                {'_id': ObjectId(campaign_id)},
                {'$set': updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating campaign: {e}")
            return False
    
    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete campaign and all associated channels"""
        try:
            # Delete associated channels
            self.campaign_channels.delete_many({'campaign_id': ObjectId(campaign_id)})
            # Delete associated analytics
            self.campaign_analytics.delete_many({'campaign_id': ObjectId(campaign_id)})
            # Delete campaign
            result = self.campaigns.delete_one({'_id': ObjectId(campaign_id)})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting campaign: {e}")
            return False
    
    # Campaign Channel Methods
    def add_channel_to_campaign(self, campaign_id: str, user_id: str, youtube_channel_id: str, 
                                channel_name: str, **kwargs) -> Optional[str]:
        """Add a channel to a campaign"""
        try:
            platform = kwargs.get('platform', 'youtube')
            content_type = kwargs.get('content_type', 'video')
            
            # Build platform-specific channel ID field
            channel_id_field = {}
            if platform == 'youtube':
                channel_id_field['youtube_channel_id'] = youtube_channel_id
            elif platform == 'tiktok':
                channel_id_field['tiktok_username'] = kwargs.get('tiktok_username', youtube_channel_id)
            elif platform == 'instagram':
                channel_id_field['instagram_username'] = kwargs.get('instagram_username', youtube_channel_id)
            
            channel_data = {
                'campaign_id': ObjectId(campaign_id),
                'user_id': ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id,
                'channel_name': channel_name,
                'platform': platform,
                'content_type': content_type,
                **channel_id_field,
                
                # Connected group for competitor intelligence
                'group_id': ObjectId(kwargs['group_id']) if kwargs.get('group_id') else None,
                
                # Content strategy (new structure)
                'content_strategy': kwargs.get('content_strategy', {
                    'source': kwargs.get('content_strategy_source', 'campaign_default'),
                    'group_id': ObjectId(kwargs['group_id']) if kwargs.get('group_id') else None,
                    'content_style_id': ObjectId(kwargs['content_style_id']) if kwargs.get('content_style_id') else None,
                    'series': kwargs.get('series', []),
                    'themes': kwargs.get('themes', []),
                    'strategy_locked': kwargs.get('strategy_locked', False),
                    'notes': kwargs.get('strategy_notes', '')
                }),
                
                # Legacy fields (for backward compatibility)
                'series': kwargs.get('series', []),
                'themes': kwargs.get('themes', []),
                'content_style_id': ObjectId(kwargs['content_style_id']) if kwargs.get('content_style_id') else None,
                
                # Production settings
                'upload_frequency': kwargs.get('upload_frequency', 'daily'),
                'videos_per_day': kwargs.get('videos_per_day'),  # New: videos per day (1-10)
                'daily_production_spend': kwargs.get('daily_production_spend', 0),  # Daily budget limit
                'production_cost': 0,  # Daily running total (resets at midnight)
                'total_production_cost': 0,  # Lifetime total
                'total_videos_produced': 0,  # Total videos produced
                'visual_style': kwargs.get('visual_style', 'black_rain'),
                'voice': kwargs.get('voice', 'af_nicole'),
                'research_enabled': kwargs.get('research_enabled', False),
                
                # Content type specific settings
                'video_duration': kwargs.get('video_duration') if content_type in ['video', 'reels'] else None,
                'slide_count': kwargs.get('slide_count') if content_type == 'slideshow' else None,
                
                # Performance metrics (initialized)
                'status': kwargs.get('status', 'testing'),
                'total_views': 0,
                'avg_views_per_video': 0,
                'watch_time_percentage': 0,
                'estimated_revenue': 0,
                'api_cost_spent': 0,
                
                # Lifecycle tracking
                'testing_start_date': datetime.utcnow(),
                'days_in_testing': 0,
                'videos_published': 0,
                
                'created_at': datetime.utcnow(),
                'last_upload': None
            }
            
            result = self.campaign_channels.insert_one(channel_data)
            
            # Update campaign total_channels count
            self.campaigns.update_one(
                {'_id': ObjectId(campaign_id)},
                {'$inc': {'total_channels': 1}}
            )
            
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error adding channel to campaign: {e}")
            return None
    
    def get_campaign_channels(self, campaign_id: str, status: Optional[str] = None) -> List[Dict]:
        """Get all channels for a campaign"""
        try:
            query = {'campaign_id': ObjectId(campaign_id)}
            if status:
                query['status'] = status
            
            channels = list(self.campaign_channels.find(query).sort('created_at', -1))
            
            for channel in channels:
                channel['_id'] = str(channel['_id'])
                channel['campaign_id'] = str(channel['campaign_id'])
                channel['user_id'] = str(channel['user_id'])
                if channel.get('group_id'):
                    channel['group_id'] = str(channel['group_id'])
                if channel.get('content_style_id'):
                    channel['content_style_id'] = str(channel['content_style_id'])
            
            return channels
        except Exception as e:
            print(f"Error getting campaign channels: {e}")
            return []
    
    def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """Get channel by ID"""
        try:
            channel = self.campaign_channels.find_one({'_id': ObjectId(channel_id)})
            if channel:
                channel['_id'] = str(channel['_id'])
                channel['campaign_id'] = str(channel['campaign_id'])
                channel['user_id'] = str(channel['user_id'])
                if channel.get('group_id'):
                    channel['group_id'] = str(channel['group_id'])
                if channel.get('content_style_id'):
                    channel['content_style_id'] = str(channel['content_style_id'])
            return channel
        except Exception as e:
            print(f"Error getting channel: {e}")
            return None
    
    def update_campaign_channel(self, channel_id: str, updates: Dict) -> bool:
        """Update campaign channel"""
        try:
            result = self.campaign_channels.update_one(
                {'_id': ObjectId(channel_id)},
                {'$set': updates}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating campaign channel: {e}")
            return False
    
    def update_channel_status(self, channel_id: str, status: str) -> bool:
        """Update channel status (testing, scaling, paused, archived)"""
        try:
            result = self.campaign_channels.update_one(
                {'_id': ObjectId(channel_id)},
                {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating channel status: {e}")
            return False
    
    # Campaign Analytics Methods
    def log_campaign_analytics(self, campaign_id: str, channel_id: Optional[str] = None, **kwargs) -> bool:
        """Log analytics data for campaign/channel"""
        try:
            analytics_data = {
                'campaign_id': ObjectId(campaign_id),
                'channel_id': ObjectId(channel_id) if channel_id else None,
                'date': kwargs.get('date', datetime.utcnow()),
                
                # Daily metrics
                'views': kwargs.get('views', 0),
                'watch_time_minutes': kwargs.get('watch_time_minutes', 0),
                'revenue': kwargs.get('revenue', 0),
                'api_costs': kwargs.get('api_costs', {
                    'anthropic': 0,
                    'elevenlabs': 0,
                    'replicate': 0,
                    'total': 0
                }),
                
                # Video-level data (optional)
                'video_id': kwargs.get('video_id'),
                'video_title': kwargs.get('video_title'),
                'video_production_cost': kwargs.get('video_production_cost', 0)
            }
            
            self.campaign_analytics.insert_one(analytics_data)
            
            # Update campaign totals
            self.campaigns.update_one(
                {'_id': ObjectId(campaign_id)},
                {
                    '$inc': {
                        'total_views': analytics_data['views'],
                        'total_revenue': analytics_data['revenue'],
                        'total_api_cost': analytics_data['api_costs'].get('total', 0)
                    }
                }
            )
            
            return True
        except Exception as e:
            print(f"Error logging campaign analytics: {e}")
            return False
    
    def get_campaign_analytics(self, campaign_id: str, days: int = 30) -> List[Dict]:
        """Get campaign analytics for the last N days"""
        try:
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days)
            
            analytics = list(self.campaign_analytics.find({
                'campaign_id': ObjectId(campaign_id),
                'date': {'$gte': start_date}
            }).sort('date', -1))
            
            for record in analytics:
                record['_id'] = str(record['_id'])
                record['campaign_id'] = str(record['campaign_id'])
                if record.get('channel_id'):
                    record['channel_id'] = str(record['channel_id'])
            
            return analytics
        except Exception as e:
            print(f"Error getting campaign analytics: {e}")
            return []
    
    def get_campaign_cost_breakdown(self, campaign_id: str, days: int = 30) -> Dict:
        """Get cost breakdown by service for a campaign"""
        try:
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days)
            
            pipeline = [
                {
                    '$match': {
                        'campaign_id': ObjectId(campaign_id),
                        'date': {'$gte': start_date}
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'anthropic_total': {'$sum': '$api_costs.anthropic'},
                        'elevenlabs_total': {'$sum': '$api_costs.elevenlabs'},
                        'replicate_total': {'$sum': '$api_costs.replicate'},
                        'total_cost': {'$sum': '$api_costs.total'}
                    }
                }
            ]
            
            result = list(self.campaign_analytics.aggregate(pipeline))
            
            if result:
                return {
                    'anthropic': result[0]['anthropic_total'],
                    'elevenlabs': result[0]['elevenlabs_total'],
                    'replicate': result[0]['replicate_total'],
                    'total': result[0]['total_cost']
                }
            return {'anthropic': 0, 'elevenlabs': 0, 'replicate': 0, 'total': 0}
        except Exception as e:
            print(f"Error getting cost breakdown: {e}")
            return {'anthropic': 0, 'elevenlabs': 0, 'replicate': 0, 'total': 0}
    
    def get_channel_analytics(self, channel_id: str, days: int = 30) -> List[Dict]:
        """Get analytics for a specific channel"""
        try:
            from datetime import timedelta
            start_date = datetime.utcnow() - timedelta(days=days)
            
            analytics = list(self.campaign_analytics.find({
                'channel_id': ObjectId(channel_id),
                'date': {'$gte': start_date}
            }).sort('date', -1))
            
            for record in analytics:
                record['_id'] = str(record['_id'])
                record['campaign_id'] = str(record['campaign_id'])
                record['channel_id'] = str(record['channel_id'])
            
            return analytics
        except Exception as e:
            print(f"Error getting channel analytics: {e}")
            return []
    
    def get_content_style(self, style_id: str):
        """Get content style by ID from either database"""
        try:
            # Try web app database first
            if self.db['content_styles'] is not None:
                try:
                    style = self.db['content_styles'].find_one({'_id': ObjectId(style_id)})
                    if style:
                        style['_id'] = str(style['_id'])
                        return style
                except:
                    pass
            
            # Try VFX database
            if self.vfx_content_styles is not None:
                try:
                    style = self.vfx_content_styles.find_one({'_id': ObjectId(style_id)})
                    if style:
                        style['_id'] = str(style['_id'])
                        return style
                except:
                    pass
            
            return None
        except Exception as e:
            print(f"Error getting content style: {e}")
            return None
    
    def get_all_content_styles(self, user_id: str = None):
        """Get all content styles from both databases, optionally filtered by user"""
        all_styles = []
        
        try:
            # Get from web app database (niche_research.content_styles)
            if self.db['content_styles'] is not None:
                query = {}
                if user_id:
                    # Try both created_by as string and ObjectId
                    try:
                        query['created_by'] = ObjectId(user_id)
                    except:
                        query['created_by'] = user_id
                
                web_styles = list(self.db['content_styles'].find(query).sort('created_at', -1))
                for style in web_styles:
                    style['_id'] = str(style['_id'])
                    style['source'] = 'web_app'
                    all_styles.append(style)
        except Exception as e:
            print(f"Error getting content styles from web app database: {e}")
        
        try:
            # Get from VFX database (vfx_analysis_results.ai_animation_styles)
            if self.vfx_content_styles is not None:
                query = {}
                if user_id:
                    # VFX database uses created_by as string
                    query['created_by'] = user_id
                
                vfx_styles = list(self.vfx_content_styles.find(query).sort('created_at', -1))
                for style in vfx_styles:
                    style['_id'] = str(style['_id'])
                    style['source'] = 'vfx_service'
                    # Ensure display_name exists
                    if 'display_name' not in style:
                        style['display_name'] = style.get('name', 'Unknown')
                    all_styles.append(style)
        except Exception as e:
            print(f"Error getting content styles from VFX database: {e}")
        
        # Deduplicate by name/slug to avoid showing same style twice (from web app + VFX DB)
        seen_styles = {}
        deduplicated_styles = []
        for style in all_styles:
            # Use name (slug) as unique identifier
            style_key = style.get('name') or style.get('display_name', '').lower()
            if style_key and style_key not in seen_styles:
                seen_styles[style_key] = True
                deduplicated_styles.append(style)
            elif not style_key:
                # If no name, include it anyway (shouldn't happen)
                deduplicated_styles.append(style)
        
        # Sort by created_at descending
        deduplicated_styles.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        return deduplicated_styles

    # ==========================================
    # GROUP CREATION LIMITS (EXACT same as Discord bot)
    # ==========================================
    
    def get_user_group_limit_sync(self, user_id: str) -> int:
        """
        Get user's group limit based on their plan - EXACT same logic as Discord bot get_user_group_limit
        """
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return 0
            
            if user.get('is_admin'):
                return float('inf')  # No limit for admins
            elif user.get('is_premium'):
                return user.get('max_groups', 3)  # Default 3 groups for premium
            elif user.get('is_beta'):
                return 1  # Beta users get 1 group
            return 0  # Free users get no groups
        except Exception as e:
            print(f"Error getting user group limit: {e}")
            return 0
    
    def can_create_group_sync(self, user_id: str) -> tuple:
        """
        Check if user can create a group - EXACT same logic as Discord bot can_create_group
        Returns (can_create: bool, message: str)
        """
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, "User not found"
            
            # Check if user has permission to create groups (premium, beta, or admin)
            if not (user.get('is_premium') or user.get('is_beta') or user.get('is_admin')):
                return False, "Creating new groups is a premium feature. Please upgrade to access this functionality."
            
            # Get current group count
            current_groups = self.get_user_groups_sync(str(user.get('discord_id', '')))
            group_count = len(current_groups) if current_groups else 0
            
            # Get user's group limit
            group_limit = self.get_user_group_limit_sync(user_id)
            
            if group_count >= group_limit:
                return False, f"You've reached your limit of {group_limit} groups"
            
            return True, ""
        except Exception as e:
            print(f"Error checking can_create_group: {e}")
            return False, f"Error checking group creation: {str(e)}"


    # ==========================================
    # THUMBNAIL STUDIO METHODS
    # ==========================================
    
    def check_trained_model_exists_sync(self, group_id, series_name: str, theme_name: str) -> bool:
        """Check if a trained model exists for the series and theme - sync version for Flask"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return False
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return False
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            content_creation = group.get('content_creation', {})
            series_data = content_creation.get(safe_series, {})
            theme_data = series_data.get(safe_theme, {})
            
            return bool(theme_data.get('trained_model_version'))
        except Exception as e:
            print(f"Error checking trained model: {str(e)}")
            return False
    
    def get_thumbnail_urls_sync(self, group_id, series_name: str, theme_name: str) -> List[Dict]:
        """Get thumbnail URLs for training - sync version for Flask"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return []
            
            # Get all competitors
            competitors = group.get('competitors', [])
            thumbnails = []
            
            for competitor in competitors:
                series_data = competitor.get('series_data', [])
                for series in series_data:
                    if series.get('name', '').lower() == series_name.lower():
                        for theme in series.get('themes', []):
                            if theme.get('name', '').lower() == theme_name.lower():
                                for topic in theme.get('topics', []):
                                    if topic.get('thumbnail_url'):
                                        thumbnails.append({
                                            'url': topic['thumbnail_url'],
                                            'video_id': topic.get('video_id', ''),
                                            'title': topic.get('title', '')
                                        })
            
            return thumbnails
        except Exception as e:
            print(f"Error getting thumbnail URLs: {str(e)}")
            return []
    
    def get_all_series_thumbnails_sync(self, group_id, series_name: str) -> List[Dict]:
        """Get all thumbnails from a series (across all themes) - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return []
            
            competitors = group.get('competitors', [])
            thumbnails = []
            
            for competitor in competitors:
                series_data = competitor.get('series_data', [])
                for series in series_data:
                    if series.get('name', '').lower() == series_name.lower():
                        for theme in series.get('themes', []):
                            for topic in theme.get('topics', []):
                                if topic.get('thumbnail_url'):
                                    thumbnails.append({
                                        'url': topic['thumbnail_url'],
                                        'video_id': topic.get('video_id', ''),
                                        'title': topic.get('title', '')
                                    })
            
            return thumbnails
        except Exception as e:
            print(f"Error getting all series thumbnails: {str(e)}")
            return []
    
    def get_thumbnail_guidelines_sync(self, group_id, series_name: str, theme_name: str) -> Optional[str]:
        """Get thumbnail guidelines for a series/theme - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return None
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return None
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            content_creation = group.get('content_creation', {})
            series_data = content_creation.get(safe_series, {})
            theme_data = series_data.get(safe_theme, {})
            
            return theme_data.get('thumbnail_guidelines')
        except Exception as e:
            print(f"Error getting thumbnail guidelines: {str(e)}")
            return None
    
    def save_thumbnail_guidelines_sync(self, group_id, series_name: str, theme_name: str, guidelines: str) -> bool:
        """Save thumbnail guidelines - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return False
            else:
                object_id = group_id
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            self.competitor_groups.update_one(
                {"_id": object_id},
                {"$set": {f"content_creation.{safe_series}.{safe_theme}.thumbnail_guidelines": guidelines}}
            )
            return True
        except Exception as e:
            print(f"Error saving thumbnail guidelines: {str(e)}")
            return False
    
    def save_trained_model_info_sync(self, group_id, series_name: str, theme_name: str, model_info: dict) -> bool:
        """Save trained model information - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return False
            else:
                object_id = group_id
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            self.competitor_groups.update_one(
                {"_id": object_id},
                {"$set": {
                    f"content_creation.{safe_series}.{safe_theme}.trained_model_version": model_info.get("version"),
                    f"content_creation.{safe_series}.{safe_theme}.weights_url": model_info.get("weights_url"),
                    f"content_creation.{safe_series}.{safe_theme}.trigger_word": model_info.get("trigger_word"),
                    f"content_creation.{safe_series}.{safe_theme}.model_trained_at": datetime.utcnow()
                }}
            )
            return True
        except Exception as e:
            print(f"Error saving trained model info: {str(e)}")
            return False
    
    def get_trained_model_info_sync(self, group_id, series_name: str, theme_name: str) -> Optional[Dict]:
        """Get trained model info - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return None
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return None
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            content_creation = group.get('content_creation', {})
            series_data = content_creation.get(safe_series, {})
            theme_data = series_data.get(safe_theme, {})
            
            if theme_data.get('trained_model_version'):
                return {
                    'version': theme_data.get('trained_model_version'),
                    'weights_url': theme_data.get('weights_url'),
                    'trigger_word': theme_data.get('trigger_word'),
                    'model_trained_at': theme_data.get('model_trained_at')
                }
            return None
        except Exception as e:
            print(f"Error getting trained model info: {str(e)}")
            return None
    
    def save_thumbnail_concepts_sync(self, group_id, series_name: str, theme_name: str, title: str, concepts: List[str]) -> bool:
        """Save thumbnail concepts - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return False
            else:
                object_id = group_id
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            safe_title = title.replace('.', '_').replace(' ', '_')[:50]
            
            self.competitor_groups.update_one(
                {"_id": object_id},
                {"$set": {
                    f"content_creation.{safe_series}.{safe_theme}.thumbnails.{safe_title}.concepts": concepts,
                    f"content_creation.{safe_series}.{safe_theme}.thumbnails.{safe_title}.created_at": datetime.utcnow()
                }}
            )
            return True
        except Exception as e:
            print(f"Error saving thumbnail concepts: {str(e)}")
            return False
    
    def save_thumbnail_url_sync(self, group_id, series_name: str, theme_name: str, title: str, url: str, metadata: dict = None) -> bool:
        """Save generated thumbnail URL - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return False
            else:
                object_id = group_id
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            safe_title = title.replace('.', '_').replace(' ', '_')[:50]
            
            thumbnail_data = {
                'url': url,
                'created_at': datetime.utcnow(),
                **(metadata or {})
            }
            
            self.competitor_groups.update_one(
                {"_id": object_id},
                {"$push": {
                    f"content_creation.{safe_series}.{safe_theme}.thumbnails.{safe_title}.generated": thumbnail_data
                }}
            )
            return True
        except Exception as e:
            print(f"Error saving thumbnail URL: {str(e)}")
            return False
    
    def get_generated_thumbnails_sync(self, group_id, series_name: str, theme_name: str, title: str = None) -> List[Dict]:
        """Get generated thumbnails - sync version"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return []
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return []
            
            safe_series = series_name.replace('.', '_').replace(' ', '_')
            safe_theme = theme_name.replace('.', '_').replace(' ', '_')
            
            content_creation = group.get('content_creation', {})
            series_data = content_creation.get(safe_series, {})
            theme_data = series_data.get(safe_theme, {})
            thumbnails_data = theme_data.get('thumbnails', {})
            
            if title:
                safe_title = title.replace('.', '_').replace(' ', '_')[:50]
                title_data = thumbnails_data.get(safe_title, {})
                return title_data.get('generated', [])
            else:
                # Return all generated thumbnails
                all_thumbnails = []
                for title_key, title_data in thumbnails_data.items():
                    generated = title_data.get('generated', [])
                    for thumb in generated:
                        thumb['title'] = title_key.replace('_', ' ')
                        all_thumbnails.append(thumb)
                return all_thumbnails
        except Exception as e:
            print(f"Error getting generated thumbnails: {str(e)}")
            return []
    
    def get_group_series_and_themes_sync(self, group_id) -> Dict:
        """Get all series and their themes for a group - for Thumbnail Studio dropdowns"""
        try:
            # Convert string ID to ObjectId
            if isinstance(group_id, str):
                try:
                    object_id = ObjectId(group_id)
                except Exception:
                    return {}
            else:
                object_id = group_id
            
            group = self.competitor_groups.find_one({"_id": object_id})
            if not group:
                return {}
            
            result = {}
            
            # Get from competitors data
            competitors = group.get('competitors', [])
            for competitor in competitors:
                series_data = competitor.get('series_data', [])
                for series in series_data:
                    series_name = series.get('name', '')
                    if series_name and series_name not in result:
                        result[series_name] = []
                    
                    for theme in series.get('themes', []):
                        theme_name = theme.get('name', '')
                        if theme_name and theme_name not in result.get(series_name, []):
                            result[series_name].append(theme_name)
            
            # Also check main_channel_data
            main_channel = group.get('main_channel_data', {})
            for series in main_channel.get('series_data', []):
                series_name = series.get('name', '')
                if series_name and series_name not in result:
                    result[series_name] = []
                
                for theme in series.get('themes', []):
                    theme_name = theme.get('name', '')
                    if theme_name and theme_name not in result.get(series_name, []):
                        result[series_name].append(theme_name)
            
            return result
        except Exception as e:
            print(f"Error getting group series and themes: {str(e)}")
            return {}


def init_db(app):
    """Initialize database for Flask app"""
    # Create database instance and store in app config
    db = Database()
    app.config['database'] = db
    
    @app.teardown_appcontext
    def close_db(error):
        # MongoDB connections are handled automatically
        pass
