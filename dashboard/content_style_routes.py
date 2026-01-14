"""
Content Styles Management Routes

Provides web UI for:
- Browsing content styles library
- Creating new content styles (reverse engineering)
- Viewing VFX profiles
- Applying styles to series/themes
"""

from flask import Blueprint, render_template, request, jsonify, current_app, session
from flask_login import login_required, current_user
from functools import wraps
import aiohttp
import asyncio
import logging
import re
from datetime import datetime
from bson import ObjectId

logger = logging.getLogger(__name__)

# Create Blueprint
content_style_bp = Blueprint('content_styles', __name__, url_prefix='/content-styles')


def async_route(f):
    """Decorator to handle async routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return decorated_function


@content_style_bp.route('/')
@login_required
def index():
    """Content Styles Library - browse all styles"""
    
    try:
        db = current_app.config['database']
        user_id = str(current_user.id)
        
        # Get Discord ID for group lookup (same as manual production)
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Get user groups (same pattern as manual production)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Add competitor_channels field for template compatibility
        for group in user_groups:
            if 'competitor_channels' not in group:
                group['competitor_channels'] = group.get('competitors', [])
        
        # Collect series/themes from all groups (same as manual production)
        all_series_data = []
        groups_data = []
        
        for group in user_groups:
            group_id = str(group.get('_id'))
            try:
                # Get series/themes for this group
                group_series = db.get_all_series_themes_sync(group_id)
                
                # Convert to series format
                for series_name, themes in group_series.items():
                    if not themes:
                        continue
                    
                    total_views = sum(theme.get('total_views', 0) for theme in themes)
                    total_videos = sum(theme.get('video_count', 0) for theme in themes)
                    avg_views = total_views / total_videos if total_videos > 0 else 0
                    
                    series_data = {
                        'name': series_name,
                        'group_name': group.get('name', 'Unnamed Project'),
                        'group_id': group_id,
                        'total_views': total_views,
                        'avg_views': avg_views,
                        'video_count': total_videos,
                        'themes': themes
                    }
                    all_series_data.append(series_data)
                
                # Store group data
                groups_data.append({
                    '_id': group_id,
                    'name': group.get('name', 'Unnamed Project'),
                    'description': group.get('description', 'Market intelligence project'),
                    'series_count': len(group_series),
                    'competitor_channels': group.get('competitors', []),
                    'created_at': group.get('created_at')
                })
                
            except Exception as e:
                logger.error(f"Error loading data for group {group_id}: {e}")
                continue
        
        # Get content styles from both databases (web app + VFX service)
        try:
            styles = db.get_all_content_styles(user_id=user_id)
        except Exception as e:
            logger.error(f"Error loading content styles: {e}")
            styles = []
        
        return render_template('modern/content_styles.html', 
                             styles=styles,
                             user_groups=groups_data,
                             all_series_data=all_series_data)
        
    except Exception as e:
        logger.error(f"Error loading content styles: {str(e)}")
        import traceback
        traceback.print_exc()
        return render_template('modern/content_styles.html', 
                             styles=[], 
                             user_groups=[],
                             all_series_data=[],
                             error=str(e))


@content_style_bp.route('/api/extract-videos', methods=['POST'])
@login_required
def extract_videos():
    """Extract video URLs from selected group/series/theme"""
    try:
        db = current_app.config['database']
        data = request.json
        group_id = data.get('group_id')
        series_name = data.get('series_name')
        theme_name = data.get('theme_name')
        limit = data.get('limit', 3)
        
        if not group_id or not series_name or not theme_name:
            return jsonify({'error': 'Missing group_id, series_name, or theme_name'}), 400
        
        # Extract video URLs using database method
        video_urls = db.get_top_video_urls_sync(group_id, series_name, theme_name, limit=limit)
        
        if not video_urls:
            return jsonify({'error': 'No videos found for this series and theme'}), 404
        
        return jsonify({'video_urls': video_urls})
        
    except Exception as e:
        logger.error(f"Error extracting videos: {str(e)}")
        return jsonify({'error': str(e)}), 500


@content_style_bp.route('/create', methods=['GET'])
@login_required
def create_page():
    """Show create new content style page"""
    return render_template('modern/create_content_style.html')


@content_style_bp.route('/create', methods=['POST'])
@login_required
@async_route
async def create_style():
    """
    Create and analyze new content style
    
    Request: {
      name: str,
      description: str,
      group_id: str,
      series_name: str,
      theme_name: str
    }
    
    OR (legacy):
    {
      name: str,
      description: str,
      video_urls: ["https://youtube.com/..."]
    }
    
    Triggers analysis on VFX service (async background task)
    """
    
    try:
        db = current_app.config['database']
        data = request.json
        user_id = str(current_user.id)
        
        # Extract video URLs - either from group/series/theme OR from video_urls
        video_ids = []
        
        if data.get('group_id') and data.get('series_name') and data.get('theme_name'):
            # New method: Extract from group/series/theme
            video_urls = db.get_top_video_urls_sync(
                data['group_id'],
                data['series_name'],
                data['theme_name'],
                limit=3
            )
            
            if not video_urls:
                return jsonify({'error': 'No videos found for selected series and theme'}), 404
            
            # Extract video IDs from URLs
            for url in video_urls:
                video_id = extract_video_id(url)
                if video_id:
                    video_ids.append(video_id)
        else:
            # Legacy method: Extract from video_urls
            for url in data.get('video_urls', []):
                video_id = extract_video_id(url)
                if video_id:
                    video_ids.append(video_id)
        
        if not video_ids:
            return jsonify({'error': 'No valid video IDs provided'}), 400
        
        if len(video_ids) < 3:
            return jsonify({'error': 'At least 3 reference videos required'}), 400
        
        # Auto-generate name if not provided (generic, not tied to series/theme since styles are reusable)
        if not data.get('name') or not data['name'].strip():
            auto_name = f"Content Style {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            data['name'] = auto_name
            logger.info(f"✅ Auto-generated style name: {auto_name}")
        
        # Create slug from name
        name_slug = slugify(data['name'])
        
        # Get platform and content_format from request
        platform = data.get('platform', 'youtube')  # 'youtube', 'tiktok', 'instagram'
        content_format = data.get('content_format', 'video')  # 'video', 'slideshow', 'reels'
        
        # Create initial content style document
        style_data = {
            'name': name_slug,
            'display_name': data['name'],
            'description': data.get('description', ''),
            'platform': platform,
            'content_format': content_format,
            'reference_videos': [
                {
                    'video_id': vid,
                    'analyzed_at': None
                } for vid in video_ids
            ],
            'status': 'analyzing',
            'created_by': user_id,
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'analysis_version': '1.0'
        }
        
        # Initialize slideshow_config for slideshow content styles
        if content_format == 'slideshow':
            style_data['slideshow_config'] = {
                'image_count_range': [5, 10],
                'aspect_ratio': '9:16',
                'text_overlay': {
                    'position': 'center',
                    'font_style': 'tiktok_bold' if platform == 'tiktok' else 'instagram_minimal',
                    'max_lines': 3,
                    'background': 'solid'
                },
                'transition': 'fade',
                'image_style_guidelines': None  # Will be populated during analysis
            }
        
        # Insert content style directly into collection
        if hasattr(db, 'create_content_style'):
            style_id = await db.create_content_style(style_data)
        else:
            # Fallback: insert directly
            result = db.db['content_styles'].insert_one(style_data)
            style_id = result.inserted_id
        logger.info(f"✅ Created content style: {style_id}")
        
        # IMPORTANT: Also create in VFX database so VFX service can find and update it
        # Port 8085 is for VFX service, 8081 is for voice service
        vfx_service_url = current_app.config.get('VFX_SERVICE_URL', 'http://157.180.0.71:8085')
        logger.info(f"🔗 Connecting to VFX Analysis Service at: {vfx_service_url}")
        
        try:
            # First, create the style in VFX database so it exists for analysis
            async with aiohttp.ClientSession() as http_session:
                # Create in VFX database
                # VFX service expects reference_videos as list of strings (video IDs)
                create_data = {
                    'name': name_slug,
                    'display_name': data['name'],
                    'description': data.get('description', ''),
                    'reference_videos': video_ids,  # Already a list of video ID strings
                    'is_ai_animation': data.get('is_ai_animation', False),
                    'narration_type': data.get('narration_type', 'full'),
                    'duration_type': data.get('duration_type', 'medium'),
                    'platform': platform,
                    'content_format': content_format,
                    'created_by': user_id
                }
                
                logger.info(f"📤 Sending to VFX service: POST {vfx_service_url}/create-content-style")
                logger.info(f"   Payload: name={create_data['name']}, videos={len(create_data['reference_videos'])}")
                
                async with http_session.post(
                    f'{vfx_service_url}/create-content-style',
                    json=create_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as create_response:
                    if create_response.status == 200:
                        vfx_result = await create_response.json()
                        vfx_style_id = vfx_result.get('content_style_id')
                        logger.info(f"✅ Created style in VFX database: {vfx_style_id}")
                        logger.info(f"✅ VFX service confirmed receipt at {vfx_service_url}")
                        # Use VFX database ID for analysis (or keep web app ID - depends on how VFX service handles it)
                        style_id_for_analysis = vfx_style_id or str(style_id)
                    else:
                        error_text = await create_response.text()
                        logger.warning(f"⚠️ Failed to create in VFX DB: {create_response.status} - {error_text}")
                        logger.warning(f"⚠️ VFX service may not be accessible at {vfx_service_url}")
                        # Continue anyway - VFX service might create it if missing
                        style_id_for_analysis = str(style_id)
            
            # Now trigger analysis (fire and forget - will take 10-30 minutes)
            logger.info(f"🎬 Triggering VFX analysis for style {style_id_for_analysis} at {vfx_service_url}/analyze-content-style")
            asyncio.create_task(
                trigger_vfx_analysis(
                    vfx_service_url,
                    style_id_for_analysis,
                    video_ids,
                    name_slug,
                    platform=platform,
                    content_format=content_format,
                    post_urls=data.get('post_urls', []) if content_format == 'slideshow' else []
                )
            )
            
            logger.info(f"✅ VFX analysis task started (running in background)")
            
        except Exception as e:
            logger.error(f"Error creating in VFX DB or triggering analysis: {str(e)}")
            # Don't fail the request - analysis can be retried later
        
        return jsonify({
            'success': True,
            'style_id': str(style_id),
            'status': 'analyzing',
            'message': 'Content style created. Analysis will take 10-30 minutes.'
        })
        
    except Exception as e:
        logger.error(f"Error creating content style: {str(e)}")
        return jsonify({'error': str(e)}), 500


async def trigger_vfx_analysis(
    vfx_service_url: str,
    style_id: str,
    video_ids: list,
    style_name: str,
    platform: str = 'youtube',
    content_format: str = 'video',
    post_urls: list = None
):
    """Trigger VFX analysis in background"""
    
    try:
        content_type_label = "slideshow posts" if content_format == 'slideshow' else "videos"
        content_count = len(post_urls) if content_format == 'slideshow' else len(video_ids)
        logger.info(f"🎬 Starting VFX analysis for {content_count} {content_type_label}...")
        logger.info(f"   Service URL: {vfx_service_url}")
        logger.info(f"   Style ID: {style_id}")
        logger.info(f"   Platform: {platform}, Format: {content_format}")
        
        # Build request payload
        request_payload = {
            'content_style_id': style_id,
            'style_name': style_name,
            'platform': platform,
            'content_format': content_format,
            'model': 'gemini-2.0-flash-exp'  # FREE tier
        }
        
        # Add content-specific data
        if content_format == 'slideshow':
            request_payload['post_urls'] = post_urls or []
            logger.info(f"   Post URLs: {post_urls}")
        else:
            request_payload['video_ids'] = video_ids
            logger.info(f"   Video IDs: {video_ids}")
        
        # Create session inside the task to avoid premature closure
        logger.info(f"📤 Sending analysis request to VFX service: POST {vfx_service_url}/analyze-content-style")
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                f'{vfx_service_url}/analyze-content-style',
                json=request_payload,
                timeout=aiohttp.ClientTimeout(total=3600)  # 1 hour timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ VFX analysis request accepted by service")
                    logger.info(f"✅ VFX analysis complete: {result.get('status')}")
                    logger.info(f"   Response: {result}")
                else:
                    error_text = await response.text()
                    logger.error(f"❌ VFX analysis failed: HTTP {response.status} - {error_text}")
            
    except asyncio.TimeoutError:
        logger.error("VFX analysis timed out (1 hour)")
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error in VFX analysis: {str(e)}")
    except Exception as e:
        logger.error(f"Error in VFX analysis: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


@content_style_bp.route('/<style_id>')
@login_required
def view_style(style_id):
    """View detailed VFX profile for a content style"""
    
    try:
        db = current_app.config['database']
        # Use synchronous method (works with both databases)
        style = db.get_content_style(style_id)
        
        if not style:
            return render_template('modern/error.html', error='Content style not found'), 404
        
        return render_template('modern/view_content_style.html', style=style)
        
    except Exception as e:
        logger.error(f"Error viewing content style: {str(e)}")
        return render_template('modern/error.html', error=str(e)), 500


@content_style_bp.route('/<style_id>/apply', methods=['POST'])
@login_required
@async_route
async def apply_to_series(style_id):
    """
    Apply content style to a series/theme
    
    Links the style so it's used in production
    
    Request: {
      group_id: str,
      series: str,
      theme: str
    }
    """
    
    try:
        db = current_app.config['database']
        data = request.json
        
        # Validate content style exists (use synchronous method)
        style = db.get_content_style(style_id)
        if not style:
            return jsonify({'error': 'Content style not found'}), 404
        
        if style.get('status') != 'active':
            return jsonify({'error': 'Content style is not ready (still analyzing)'}), 400
        
        # Link style to series
        await db.update_series_content_style(
            group_id=data['group_id'],
            series_name=data['series'],
            theme_name=data['theme'],
            content_style_id=style_id
        )
        
        logger.info(f"✅ Applied style {style_id} to {data['series']} - {data['theme']}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error applying content style: {str(e)}")
        return jsonify({'error': str(e)}), 500


@content_style_bp.route('/api/list', methods=['GET'])
@login_required
@async_route
async def api_list_styles():
    """API endpoint to list all content styles"""
    
    try:
        db = current_app.config['database']
        user_id = str(current_user.id)
        
        # Get from both databases (synchronous method)
        styles = db.get_all_content_styles(user_id=user_id)
        
        return jsonify(styles)
        
    except Exception as e:
        logger.error(f"Error listing content styles: {str(e)}")
        return jsonify({'error': str(e)}), 500


@content_style_bp.route('/<style_id>/status', methods=['GET'])
@login_required
@async_route
async def check_status(style_id):
    """Check analysis status of a content style"""
    
    try:
        db = current_app.config['database']
        # Use synchronous method (works with both databases)
        style = db.get_content_style(style_id)
        
        if not style:
            return jsonify({'error': 'Content style not found'}), 404
        
        return jsonify({
            'status': style.get('status', 'unknown'),
            'confidence_score': style.get('vfx_profile', {}).get('confidence_score'),
            'components_generated': len(style.get('remotion_components', [])),
            'workflows_created': len(style.get('vfx_profile', {}).get('automation_workflows', {}))
        })
        
    except Exception as e:
        logger.error(f"Error checking status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@content_style_bp.route('/<style_id>', methods=['DELETE'])
@login_required
def delete_style(style_id):
    """Delete a content style"""
    
    try:
        db = current_app.config['database']
        user_id = str(current_user.id)
        
        # Try to delete from web app database
        deleted = False
        if db.db['content_styles'] is not None:
            result = db.db['content_styles'].delete_one({
                '_id': ObjectId(style_id),
                'created_by': user_id  # Only allow deleting own styles
            })
            if result.deleted_count > 0:
                deleted = True
                logger.info(f"✅ Deleted content style {style_id} from web app database")
        
        # Try to delete from VFX database
        if db.vfx_content_styles is not None:
            result = db.vfx_content_styles.delete_one({
                '_id': ObjectId(style_id),
                'created_by': user_id
            })
            if result.deleted_count > 0:
                deleted = True
                logger.info(f"✅ Deleted content style {style_id} from VFX database")
        
        if deleted:
            return jsonify({'success': True, 'message': 'Content style deleted'})
        else:
            return jsonify({'error': 'Content style not found or you do not have permission'}), 404
        
    except Exception as e:
        logger.error(f"Error deleting content style: {str(e)}")
        return jsonify({'error': str(e)}), 500


@content_style_bp.route('/<style_id>/retry', methods=['POST'])
@login_required
def retry_analysis(style_id):
    """Retry analysis for a content style"""
    
    try:
        logger.info(f"🔄 Retry request received for style {style_id}")
        print(f"🔄 RETRY REQUEST: style_id={style_id}, user={current_user.id}")
        db = current_app.config['database']
        style = db.get_content_style(style_id)
        
        if not style:
            logger.error(f"❌ Style {style_id} not found")
            return jsonify({'error': 'Content style not found'}), 404
        
        logger.info(f"✅ Found style: {style.get('display_name', style.get('name', 'Unknown'))}")
        
        # Get video IDs from reference videos
        video_ids = []
        for ref_video in style.get('reference_videos', []):
            if isinstance(ref_video, dict):
                video_id = ref_video.get('video_id')
            else:
                video_id = ref_video
            if video_id:
                video_ids.append(video_id)
        
        logger.info(f"📹 Found {len(video_ids)} video IDs: {video_ids}")
        
        if not video_ids:
            logger.error(f"❌ No reference videos found for style {style_id}")
            return jsonify({'error': 'No reference videos found'}), 400
        
        # Get VFX service URL
        vfx_service_url = current_app.config.get('VFX_SERVICE_URL', 'http://157.180.0.71:8085')
        logger.info(f"🔗 VFX Service URL: {vfx_service_url}")
        
        # Update status to analyzing
        if db.db['content_styles'] is not None:
            result = db.db['content_styles'].update_one(
                {'_id': ObjectId(style_id)},
                {'$set': {'status': 'analyzing', 'updated_at': datetime.now()}}
            )
            logger.info(f"✅ Updated web app DB status: {result.modified_count} documents modified")
        
        if db.vfx_content_styles is not None:
            result = db.vfx_content_styles.update_one(
                {'_id': ObjectId(style_id)},
                {'$set': {'status': 'analyzing', 'updated_at': datetime.now()}}
            )
            logger.info(f"✅ Updated VFX DB status: {result.modified_count} documents modified")
        
        # Trigger analysis
        name_slug = style.get('name', '')
        platform = style.get('platform', 'youtube')
        content_format = style.get('content_format', 'video')
        
        logger.info(f"🎬 Triggering VFX analysis: style_id={style_id}, videos={len(video_ids)}, platform={platform}")
        
        # Run in background task
        import threading
        def run_analysis():
            asyncio.run(trigger_vfx_analysis(
                vfx_service_url,
                style_id,
                video_ids,
                name_slug,
                platform=platform,
                content_format=content_format
            ))
        
        thread = threading.Thread(target=run_analysis, daemon=True)
        thread.start()
        
        logger.info(f"✅ Retry task started for style {style_id}")
        print(f"✅ RETRY SUCCESS: Analysis task started in background")
        
        return jsonify({
            'success': True,
            'message': 'Analysis restarted',
            'style_id': style_id
        })
        
    except Exception as e:
        logger.error(f"❌ Error retrying analysis: {str(e)}")
        print(f"❌ RETRY ERROR: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# Helper functions

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL"""
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'  # Plain ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    
    # Replace spaces with underscores
    text = re.sub(r'\s+', '_', text)
    
    # Remove multiple underscores
    text = re.sub(r'_+', '_', text)
    
    return text.strip('_')

