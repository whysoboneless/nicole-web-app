"""
Campaign Management Routes for Nicole Web Suite
Handles multi-channel campaign creation, management, and analytics
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from core.database import Database
from bson import ObjectId
from datetime import datetime, timedelta
import traceback

campaign_bp = Blueprint('campaigns', __name__, url_prefix='/campaigns')
db = Database()

def verify_campaign_ownership(campaign_id: str) -> tuple:
    """
    Verify that the current user owns the campaign.
    Returns: (is_owner: bool, campaign: dict or None, user_mongo_id: str or None)
    """
    try:
        campaign = db.get_campaign(campaign_id)
        if not campaign:
            return False, None, None
        
        # Get user's MongoDB _id (not Discord ID)
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        
        if not user_doc:
            return False, campaign, None
        
        user_mongo_id = str(user_doc['_id'])
        campaign_user_id = str(campaign.get('user_id', ''))
        
        # Compare MongoDB ObjectIds
        is_owner = (campaign_user_id == user_mongo_id)
        return is_owner, campaign, user_mongo_id
    except Exception as e:
        print(f"Error verifying campaign ownership: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None

# ========================================
# CAMPAIGN LIST & OVERVIEW
# ========================================

@campaign_bp.route('/')
@login_required
def campaigns_list():
    """Main campaigns dashboard - Ads Manager style"""
    try:
        user_id = str(current_user.id)
        
        # Get all user campaigns
        campaigns = db.get_user_campaigns(user_id)
        
        # Enrich each campaign with channel count and stats
        for campaign in campaigns:
            channels = db.get_campaign_channels(campaign['_id'])
            campaign['channel_count'] = len(channels)
            campaign['active_channels'] = len([c for c in channels if c['status'] == 'testing' or c['status'] == 'scaling'])
            campaign['paused_channels'] = len([c for c in channels if c['status'] == 'paused'])
        
        return render_template('modern/campaigns.html',
                             campaigns=campaigns,
                             total_campaigns=len(campaigns))
    except Exception as e:
        print(f"Error loading campaigns: {e}")
        traceback.print_exc()
        flash('Error loading campaigns', 'error')
        return render_template('modern/campaigns.html', campaigns=[], total_campaigns=0)

# ========================================
# CAMPAIGN CREATION WIZARD
# ========================================

@campaign_bp.route('/create')
@login_required
def create_campaign_page():
    """Campaign creation wizard page"""
    try:
        # Get user's groups for selection
        user_groups = db.get_user_groups_sync(str(current_user.discord_id) if hasattr(current_user, 'discord_id') else str(current_user.id))
        
        return render_template('modern/campaign_wizard.html',
                             user_groups=user_groups)
    except Exception as e:
        print(f"Error loading campaign creation page: {e}")
        traceback.print_exc()
        flash('Error loading page', 'error')
        return redirect(url_for('campaigns.campaigns_list'))

@campaign_bp.route('/research-product', methods=['POST'])
@login_required
def research_product():
    """Research product URL and identify target audience"""
    try:
        data = request.get_json()
        product_url = data.get('product_url')
        
        if not product_url:
            return jsonify({'success': False, 'error': 'Product URL required'}), 400
        
        # Import product research service
        from nicole_web_suite_template.services.product_research_service import product_research_service
        
        # Research product (run async)
        import asyncio
        import threading
        
        result_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        product_research_service.research_product(product_url)
                    )
                    result_container['value'] = result
                finally:
                    loop.close()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=30)
        
        if thread.is_alive():
            return jsonify({'success': False, 'error': 'Research timeout'}), 500
        
        if result_container['error']:
            return jsonify({'success': False, 'error': result_container['error']}), 500
        
        result = result_container['value']
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Research failed')}), 500
        
    except Exception as e:
        print(f"Error researching product: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/discover-channels', methods=['POST'])
@login_required
def discover_channels(campaign_id):
    """Discover channels for a campaign based on product research"""
    try:
        # Verify ownership
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        count = data.get('count', 5)
        
        # Get product research from campaign
        product_research = campaign.get('product_research')
        if not product_research:
            return jsonify({'success': False, 'error': 'Product research not found. Please research product first.'}), 400
        
        # Import and initialize channel discovery service
        from nicole_web_suite_template.services.campaign_channel_discovery import get_campaign_channel_discovery_service
        from nicole_web_suite_template.core.youtube_service import YouTubeService
        
        youtube_service = YouTubeService()
        discovery_service = get_campaign_channel_discovery_service(youtube_service, db)
        
        # Discover channels (run async)
        import asyncio
        import threading
        
        result_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        discovery_service.discover_channels_for_product(product_research, count)
                    )
                    result_container['value'] = result
                finally:
                    loop.close()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=120)  # 2 minute timeout
        
        if thread.is_alive():
            return jsonify({'success': False, 'error': 'Channel discovery timeout'}), 500
        
        if result_container['error']:
            return jsonify({'success': False, 'error': result_container['error']}), 500
        
        channels = result_container['value']
        
        return jsonify({
            'success': True,
            'channels': channels,
            'count': len(channels)
        })
        
    except Exception as e:
        print(f"Error discovering channels: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/discover-instagram-accounts', methods=['POST'])
@login_required
def discover_instagram_accounts(campaign_id):
    """Discover Instagram accounts for campaign based on product research"""
    try:
        # Verify ownership
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        count = data.get('count', 5)
        
        # Get product research
        product_research = campaign.get('product_research')
        if not product_research:
            return jsonify({'success': False, 'error': 'Product research not found'}), 400
        
        # Call ig-tiktok-analysis-service
        import requests as req
        response = req.post(
            'http://localhost:8087/discover-instagram-accounts',
            json={'product_research': product_research, 'count': count},
            timeout=120
        )
        
        return jsonify(response.json())
        
    except Exception as e:
        print(f"Error discovering Instagram accounts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/discover-tiktok-accounts', methods=['POST'])
@login_required
def discover_tiktok_accounts(campaign_id):
    """Discover TikTok accounts for campaign based on product research"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        count = data.get('count', 5)
        
        product_research = campaign.get('product_research')
        if not product_research:
            return jsonify({'success': False, 'error': 'Product research not found'}), 400
        
        import requests as req
        response = req.post(
            'http://localhost:8087/discover-tiktok-accounts',
            json={'product_research': product_research, 'count': count},
            timeout=120
        )
        
        return jsonify(response.json())
        
    except Exception as e:
        print(f"Error discovering TikTok accounts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/create-ig-group', methods=['POST'])
@login_required
def create_ig_group(campaign_id):
    """Create Instagram group from discovered account"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        username = data.get('username')
        
        if not username:
            return jsonify({'success': False, 'error': 'Username required'}), 400
        
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') else str(current_user.id)
        
        import requests as req
        response = req.post(
            'http://localhost:8087/create-instagram-group',
            json={
                'username': username,
                'group_name': f"{campaign.get('name', 'Campaign')} - {username}",
                'user_id': discord_id,
                'product_context': campaign.get('product_research')
            },
            timeout=300
        )
        
        result = response.json()
        
        # If successful, add to campaign channels
        if result.get('success'):
            group_id = result.get('group_id')
            series_data = result.get('series_data', [])
            
            # Add first series/theme as default
            if series_data and len(series_data) > 0:
                series = series_data[0]
                theme = series['themes'][0] if series.get('themes') else None
                
                if theme:
                    # Add to campaign_channels
                    channel_data = {
                        'campaign_id': ObjectId(campaign_id),
                        'user_id': ObjectId(user_mongo_id),
                        'platform': 'instagram',
                        'account_username': username,
                        'group_id': ObjectId(group_id),
                        'series_name': series['name'],
                        'theme_name': theme['name'],
                        'content_format': 'slideshow',
                        'status': 'pending',  # Will be activated when campaign starts
                        'upload_frequency': campaign.get('default_upload_frequency', 'weekly'),
                        'created_at': datetime.utcnow()
                    }
                    
                    db.campaign_channels.insert_one(channel_data)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error creating IG group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/create-tiktok-group', methods=['POST'])
@login_required
def create_tiktok_group(campaign_id):
    """Create TikTok group from discovered account"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        username = data.get('username')
        
        if not username:
            return jsonify({'success': False, 'error': 'Username required'}), 400
        
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') else str(current_user.id)
        
        import requests as req
        response = req.post(
            'http://localhost:8087/create-tiktok-group',
            json={
                'username': username,
                'group_name': f"{campaign.get('name', 'Campaign')} - {username}",
                'user_id': discord_id,
                'product_context': campaign.get('product_research')
            },
            timeout=300
        )
        
        result = response.json()
        
        # If successful, add to campaign channels
        if result.get('success'):
            group_id = result.get('group_id')
            series_data = result.get('series_data', [])
            
            if series_data and len(series_data) > 0:
                series = series_data[0]
                theme = series['themes'][0] if series.get('themes') else None
                
                if theme:
                    channel_data = {
                        'campaign_id': ObjectId(campaign_id),
                        'user_id': ObjectId(user_mongo_id),
                        'platform': 'tiktok',
                        'account_username': username,
                        'group_id': ObjectId(group_id),
                        'series_name': series['name'],
                        'theme_name': theme['name'],
                        'content_format': 'ugc',
                        'status': 'pending',
                        'upload_frequency': campaign.get('default_upload_frequency', 'weekly'),
                        'created_at': datetime.utcnow()
                    }
                    
                    db.campaign_channels.insert_one(channel_data)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error creating TikTok group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/api/user-groups', methods=['GET'])
@login_required
def api_user_groups():
    """Get user's groups for dropdowns"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Convert to simple format for dropdown
        groups_data = []
        for group in user_groups:
            groups_data.append({
                '_id': str(group['_id']),
                'name': group.get('name', 'Unnamed Group')
            })
        
        return jsonify({
            'success': True,
            'groups': groups_data
        })
    except Exception as e:
        print(f"Error getting user groups: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/available-channels', methods=['GET'])
@login_required
def get_available_channels():
    """Get user's connected YouTube channels that aren't in any campaign"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        
        if not user_doc:
            return jsonify({'success': False, 'error': 'User not found'}), 400
        
        # Get all user's connected YouTube channels
        user_channels = db.get_user_youtube_channels_sync(str(user_doc['_id']))
        
        # Get all channels currently in campaigns
        campaign_channels = list(db.campaign_channels.find({
            'user_id': ObjectId(user_doc['_id'])
        }))
        
        # Extract channel IDs that are in campaigns
        channels_in_campaigns = set()
        for cc in campaign_channels:
            if cc.get('youtube_channel_id'):
                channels_in_campaigns.add(cc['youtube_channel_id'])
        
        # Filter to only channels NOT in any campaign
        available_channels = []
        for channel in user_channels:
            channel_id = channel.get('channel_id') or channel.get('id')
            if channel_id and channel_id not in channels_in_campaigns:
                available_channels.append({
                    'channel_id': channel_id,
                    'channel_name': channel.get('channel_title') or channel.get('title', 'Unknown'),
                    'channel_url': f"https://youtube.com/channel/{channel_id}",
                    'subscriber_count': channel.get('subscriber_count', 0),
                    'video_count': channel.get('video_count', 0),
                    'source': 'connected'  # Mark as user's connected channel
                })
        
        return jsonify({
            'success': True,
            'channels': available_channels,
            'count': len(available_channels)
        })
        
    except Exception as e:
        print(f"Error getting available channels: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/create', methods=['POST'])
@login_required
def create_campaign():
    """Create a new campaign"""
    try:
        data = request.get_json() if request.is_json else request.form
        
        # Required fields
        name = data.get('name')
        objective = data.get('objective')  # 'ecommerce', 'cashcow', 'brand_awareness'
        
        if not name or not objective:
            return jsonify({'success': False, 'error': 'Name and objective are required'}), 400
        
        # Get user's MongoDB _id (not Discord ID) for campaign creation
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        
        if not user_doc:
            return jsonify({'success': False, 'error': 'User not found in database'}), 400
        
        user_id = str(user_doc['_id'])  # Use MongoDB ObjectId, not Discord ID
        
        # Build campaign data
        campaign_kwargs = {
            'status': 'active',
            'lifecycle_automation_enabled': data.get('lifecycle_automation_enabled', False) == 'true' or data.get('lifecycle_automation_enabled', False) == True,
        }
        
        # Product info - handle saved product selection OR new product URL
        if objective == 'product_sales' or objective == 'ecommerce':
            product_id = data.get('selected_product_id') or data.get('product_id')
            product_url = data.get('product_url')
            
            products = []
            if product_id:
                # Load saved product
                product = db.get_product(product_id)
                if product:
                    product_url = product.get('url') or product_url
                    products.append({
                        'product_id': product_id,
                        'name': product.get('name', ''),
                        'url': product_url,
                        'description': product.get('description', ''),
                        'price': product.get('price'),
                        'price_text': product.get('price_text', ''),
                        'cpa_network': product.get('cpa_network', ''),
                        'cpa_offer_id': product.get('cpa_offer_id', ''),
                        'tracking_url': product.get('tracking_url', '') or product_url,
                        'category': product.get('category', ''),
                        'promotion_type': data.get('promotion_type', 'overlay')
                    })
            elif product_url or data.get('product_name'):
                # Manual entry (backward compatibility)
                products.append({
                    'name': data.get('product_name', ''),
                    'url': product_url or '',
                    'description': data.get('product_description', ''),
                    'promotion_type': data.get('promotion_type', 'overlay')
                })
            
            campaign_kwargs['products'] = products
            
            # Research product if URL provided (either from saved product or manual entry)
            if product_url:
                product_research = None
                if data.get('product_research'):
                    product_research = data.get('product_research')
                else:
                    # Auto-research if not provided
                    try:
                        from nicole_web_suite_template.services.product_research_service import product_research_service
                        import asyncio
                        product_research = asyncio.run(product_research_service.research_product(product_url))
                    except Exception as e:
                        print(f"⚠️ Product research failed: {e}")
                
                if product_research and product_research.get('success'):
                    campaign_kwargs['product_research'] = product_research
                    # Merge research data with product data
                    if products:
                        products[0].update({
                            'name': product_research.get('product', {}).get('name', products[0].get('name', '')),
                            'description': product_research.get('product', {}).get('description', products[0].get('description', '')),
                            'price': product_research.get('product', {}).get('price') or products[0].get('price'),
                            'price_formatted': product_research.get('product', {}).get('price_formatted', '')
                        })
            
            # Generate default content strategy if product research available
            if campaign_kwargs.get('product_research'):
                from nicole_web_suite_template.services.content_strategy_service import get_content_strategy_service
                strategy_service = get_content_strategy_service(db)
                default_strategy = strategy_service.recommend_strategy(
                    campaign_kwargs.get('product_research'),
                    'youtube'
                )
                campaign_kwargs['default_content_strategy'] = {
                    'source': 'product_research',
                    'content_types': default_strategy.get('content_types', []),
                    'auto_created': True
                }
        
        # Target demographics
        target_demographics = {}
        if data.get('target_age_range'):
            target_demographics['age_range'] = data.get('target_age_range')
        if data.get('target_interests'):
            interests = data.get('target_interests')
            if isinstance(interests, str):
                interests = [i.strip() for i in interests.split(',')]
            target_demographics['interests'] = interests
        if data.get('target_geo'):
            geo = data.get('target_geo')
            if isinstance(geo, str):
                geo = [g.strip() for g in geo.split(',')]
            target_demographics['geo'] = geo
        
        if target_demographics:
            campaign_kwargs['target_demographics'] = target_demographics
        
        # Budget (Facebook Ads style: shared budget across all channels)
        budget = {}
        if data.get('api_cost_limit'):
            budget['amount'] = float(data.get('api_cost_limit'))
            budget['type'] = data.get('budget_type', 'monthly')  # 'daily' or 'monthly'
        if budget:
            campaign_kwargs['budget'] = budget
        
        # Channel count (for product sales campaigns)
        if objective == 'product_sales' or objective == 'ecommerce':
            channel_count = data.get('channel_count')
            if channel_count:
                try:
                    campaign_kwargs['channel_count'] = int(channel_count)
                except (ValueError, TypeError):
                    campaign_kwargs['channel_count'] = 1
        
        # Lifecycle rules (simplified - just testing thresholds)
        if data.get('testing_duration_days') or data.get('min_views_threshold'):
            lifecycle_rules = {}
            if data.get('testing_duration_days'):
                lifecycle_rules['testing_duration_days'] = int(data.get('testing_duration_days'))
            if data.get('min_views_threshold'):
                lifecycle_rules['min_views_threshold'] = int(data.get('min_views_threshold'))
            if data.get('min_watch_time_percentage'):
                lifecycle_rules['min_watch_time_percentage'] = float(data.get('min_watch_time_percentage'))
            if lifecycle_rules:
                campaign_kwargs['lifecycle_rules'] = lifecycle_rules
        
        # Create campaign
        print(f"📝 Creating campaign: {name} (objective: {objective})")
        print(f"📝 User ID: {user_id} (type: {type(user_id)})")
        print(f"📝 Campaign kwargs keys: {list(campaign_kwargs.keys())}")
        
        campaign_id = db.create_campaign(user_id, name, objective, **campaign_kwargs)
        
        if campaign_id:
            print(f"✅ Campaign created successfully: {campaign_id}")
            
            # Handle multi-platform channel setup
            channel_counts = data.get('channel_counts', {})
            if isinstance(channel_counts, str):
                import json
                channel_counts = json.loads(channel_counts)
            
            # Handle selected YouTube channels (from available channels or discovered channels)
            selected_channel_ids = data.get('selected_channel_ids')
            if isinstance(selected_channel_ids, str):
                import json
                selected_channel_ids = json.loads(selected_channel_ids)
            
            # Handle product images (for UGC/slideshow)
            product_images = data.get('product_images', [])
            if isinstance(product_images, str):
                import json
                product_images = json.loads(product_images)
            
            # Store product images in campaign
            if product_images:
                campaign_kwargs['product_images'] = product_images
                print(f"📸 Storing {len(product_images)} product images for campaign")
            
            # Add YouTube channels
            if selected_channel_ids:
                try:
                    if isinstance(selected_channel_ids, str):
                        import json
                        selected_channel_ids = json.loads(selected_channel_ids)
                    
                    # Add each selected channel to the campaign
                    for channel_id in selected_channel_ids:
                        try:
                            # Get channel data
                            from nicole_web_suite_template.core.youtube_service import YouTubeService
                            youtube_service = YouTubeService()
                            channel_data = youtube_service.fetch_channel_data_sync(channel_id)
                            
                            if channel_data:
                                channel_name = channel_data.get('title', 'Unknown Channel')
                                
                                # Add channel to campaign (status: testing, will need group/content style later)
                                db.add_channel_to_campaign(
                                    campaign_id,
                                    user_id,
                                    channel_id,
                                    channel_name,
                                    platform='youtube',
                                    content_type='video',
                                    status='testing'
                                )
                                print(f"✅ Added selected channel {channel_name} to campaign")
                        except Exception as e:
                            print(f"⚠️ Error adding channel {channel_id}: {e}")
                            continue
                except Exception as e:
                    print(f"⚠️ Error processing selected channels: {e}")
            
            # Add Instagram accounts as channels
            instagram_count = channel_counts.get('instagram', 0) or data.get('instagram_channel_count', 0)
            if instagram_count > 0:
                try:
                    discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
                    instagram_accounts = db.get_instagram_accounts(discord_id)
                    
                    # Add up to instagram_count accounts
                    for account in instagram_accounts[:int(instagram_count)]:
                        try:
                            db.add_channel_to_campaign(
                                campaign_id,
                                user_id,
                                account.get('username') or account.get('_id'),
                                f"@{account.get('username', 'Unknown')}",
                                platform='instagram',
                                content_type='slideshow',  # Instagram slideshow for product campaigns
                                status='testing'
                            )
                            print(f"✅ Added Instagram account @{account.get('username')} to campaign")
                        except Exception as e:
                            print(f"⚠️ Error adding Instagram account {account.get('username')}: {e}")
                            continue
                except Exception as e:
                    print(f"⚠️ Error processing Instagram accounts: {e}")
            
            # Add TikTok accounts as channels (stub - will need API integration)
            tiktok_count = channel_counts.get('tiktok', 0) or data.get('tiktok_channel_count', 0)
            if tiktok_count > 0:
                # TODO: Get TikTok accounts from request or database
                tiktok_accounts = data.get('tiktok_accounts', [])
                if isinstance(tiktok_accounts, str):
                    import json
                    tiktok_accounts = json.loads(tiktok_accounts)
                
                for account in tiktok_accounts[:int(tiktok_count)]:
                    try:
                        username = account.get('username') if isinstance(account, dict) else str(account)
                        db.add_channel_to_campaign(
                            campaign_id,
                            user_id,
                            username,
                            f"@{username}",
                            platform='tiktok',
                            content_type='reels',  # TikTok UGC/reels
                            status='testing'
                        )
                        print(f"✅ Added TikTok account @{username} to campaign")
                    except Exception as e:
                        print(f"⚠️ Error adding TikTok account {username}: {e}")
                        continue
            
            # Auto-trigger channel discovery for product sales campaigns (if no channels selected)
            total_channels = (len(selected_channel_ids) if selected_channel_ids else 0) + int(instagram_count) + int(tiktok_count)
            if (objective == 'product_sales' or objective == 'ecommerce') and campaign_kwargs.get('product_research') and total_channels == 0:
                try:
                    # Trigger channel discovery asynchronously (don't block response)
                    import threading
                    def discover_channels():
                        try:
                            from nicole_web_suite_template.services.campaign_channel_discovery import CampaignChannelDiscoveryService
                            discovery_service = CampaignChannelDiscoveryService(db)
                            import asyncio
                            asyncio.run(discovery_service.discover_channels_for_campaign(
                                campaign_id,
                                campaign_kwargs.get('product_research'),
                                campaign_kwargs.get('channel_count', 1)
                            ))
                        except Exception as e:
                            print(f"⚠️ Channel discovery failed: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    thread = threading.Thread(target=discover_channels, daemon=True)
                    thread.start()
                except Exception as e:
                    print(f"⚠️ Failed to trigger channel discovery: {e}")
            
            return jsonify({
                'success': True,
                'campaign_id': campaign_id,
                'message': f'Campaign "{name}" created successfully',
                'redirect': url_for('campaigns.campaign_detail', campaign_id=campaign_id)
            })
        else:
            print(f"❌ Failed to create campaign")
            return jsonify({'success': False, 'error': 'Failed to create campaign. Check server logs for details.'}), 500
            
    except Exception as e:
        print(f"❌ Error creating campaign: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Error creating campaign: {str(e)}'}), 500

# ========================================
# CHANNEL DISCOVERY
# ========================================
# Note: Route definition at line 153 to avoid duplicate route error

# ========================================
# CAMPAIGN DETAIL & MANAGEMENT
# ========================================

@campaign_bp.route('/<campaign_id>')
@login_required
def campaign_detail(campaign_id):
    """Single campaign dashboard with all channels"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        
        if not campaign:
            flash('Campaign not found', 'error')
            return redirect(url_for('campaigns.campaigns_list'))
        
        if not is_owner:
            flash('Unauthorized access', 'error')
            return redirect(url_for('campaigns.campaigns_list'))
        
        # Get all channels for this campaign
        channels = db.get_campaign_channels(campaign_id)
        
        # Get analytics summary (last 30 days)
        analytics_summary = {
            'total_views': campaign.get('total_views', 0),
            'total_revenue': campaign.get('total_revenue', 0),
            'total_cost': campaign.get('total_api_cost', 0),
            'roi': 0
        }
        
        if analytics_summary['total_cost'] > 0:
            analytics_summary['roi'] = ((analytics_summary['total_revenue'] - analytics_summary['total_cost']) / analytics_summary['total_cost']) * 100
        
        # Get cost breakdown
        cost_breakdown = db.get_campaign_cost_breakdown(campaign_id, days=30)
        
        return render_template('modern/campaign_dashboard.html',
                             campaign=campaign,
                             channels=channels,
                             analytics_summary=analytics_summary,
                             cost_breakdown=cost_breakdown)
    except Exception as e:
        print(f"Error loading campaign detail: {e}")
        traceback.print_exc()
        flash('Error loading campaign', 'error')
        return redirect(url_for('campaigns.campaigns_list'))

# ========================================
# CHANNEL MANAGEMENT
# ========================================

@campaign_bp.route('/<campaign_id>/default-strategy', methods=['GET'])
@login_required
def get_default_strategy(campaign_id):
    """Get campaign default strategy and user groups/styles"""
    try:
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get user groups
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Get content styles from both databases (web app + VFX service)
        content_styles = db.get_all_content_styles(user_id=str(current_user.id))
        for style in content_styles:
            style['id'] = str(style['_id'])
            style['display_name'] = style.get('display_name', style.get('name', 'Unknown'))
        
        return jsonify({
            'success': True,
            'default_strategy': campaign.get('default_content_strategy', {}),
            'user_groups': [{'id': str(g['_id']), 'name': g.get('name', 'Unknown')} for g in user_groups],
            'content_styles': content_styles
        })
    except Exception as e:
        print(f"Error getting default strategy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/channels/<channel_id>/edit-strategy', methods=['GET'])
@login_required
def edit_channel_strategy(campaign_id, channel_id):
    """Get channel strategy data for editing"""
    try:
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        channel = db.get_channel_by_id(channel_id)
        if not channel:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
        
        # Get user groups
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Get content styles
        content_styles = list(db.db['content_styles'].find({'user_id': ObjectId(str(current_user.id))}))
        for style in content_styles:
            style['id'] = str(style['_id'])
            style['display_name'] = style.get('display_name', style.get('name', 'Unknown'))
        
        # Get channel strategy
        strategy = channel.get('content_strategy', {})
        if not strategy:
            strategy = {
                'source': 'campaign_default',
                'group_id': None,
                'content_style_id': None,
                'series': [],
                'themes': []
            }
        
        # Add group name if available
        if strategy.get('group_id'):
            group = db.get_group(str(strategy['group_id']))
            if group:
                strategy['group_name'] = group.get('name', 'Unknown')
        
        # Add content style name if available
        if strategy.get('content_style_id'):
            style = db.db['content_styles'].find_one({'_id': strategy['content_style_id']})
            if style:
                strategy['content_style_name'] = style.get('display_name', style.get('name', 'Unknown'))
        
        return jsonify({
            'success': True,
            'strategy': strategy,
            'user_groups': [{'id': str(g['_id']), 'name': g.get('name', 'Unknown')} for g in user_groups],
            'content_styles': content_styles
        })
    except Exception as e:
        print(f"Error getting channel strategy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/channels/<channel_id>/set-strategy', methods=['POST'])
@login_required
def set_channel_strategy(campaign_id, channel_id):
    """Set content strategy for a channel"""
    try:
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        
        # Build strategy dict
        strategy = {
            'source': data.get('source', 'campaign_default'),
            'group_id': ObjectId(data['group_id']) if data.get('group_id') else None,
            'content_style_id': ObjectId(data['content_style_id']) if data.get('content_style_id') else None,
            'series': data.get('series', []),
            'themes': data.get('themes', []),
            'strategy_locked': data.get('strategy_locked', False),
            'notes': data.get('notes', '')
        }
        
        # Update channel
        result = db.db['campaign_channels'].update_one(
            {'_id': ObjectId(channel_id), 'campaign_id': ObjectId(campaign_id)},
            {'$set': {
                'content_strategy': strategy,
                'group_id': strategy['group_id'],  # Legacy
                'content_style_id': strategy['content_style_id'],  # Legacy
                'series': strategy['series'],  # Legacy
                'themes': strategy['themes']  # Legacy
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Strategy updated'})
        else:
            return jsonify({'success': False, 'error': 'Channel not found or no changes'}), 404
        
    except Exception as e:
        print(f"Error setting channel strategy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@campaign_bp.route('/<campaign_id>/discovered-groups', methods=['GET'])
@login_required
def get_discovered_groups(campaign_id):
    """Get discovered groups for a campaign (from channel discovery)"""
    try:
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not is_owner or not campaign:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Find groups linked to this campaign
        from bson import ObjectId
        groups = list(db.competitor_groups.find({
            'campaign_id': campaign_id
        }).sort('createdAt', -1))
        
        # Format groups
        formatted_groups = []
        for group in groups:
            formatted_groups.append({
                'id': str(group['_id']),
                'name': group.get('name', 'Unknown'),
                'main_channel': group.get('main_channel_data', {}).get('title', 'Unknown'),
                'match_type': group.get('match_type', 'direct'),
                'content_type': group.get('custom_niche', [])
            })
        
        return jsonify({
            'success': True,
            'groups': formatted_groups
        })
    except Exception as e:
        print(f"Error getting discovered groups: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/add-channel', methods=['POST'])
@login_required
def add_channel(campaign_id):
    """Add a new channel to campaign with full configuration"""
    try:
        data = request.get_json()
        
        # Verify campaign ownership
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Extract channel URL to get channel ID/username
        channel_url = data.get('channel_url', '')
        platform = data.get('platform', 'youtube')
        
        # Parse channel identifier from URL
        channel_id_field = None
        channel_name = None
        
        if platform == 'youtube':
            # Extract channel ID or username from URL
            import re
            # Try to match @username or channel ID patterns
            username_match = re.search(r'@([^/?]+)', channel_url)
            channel_id_match = re.search(r'/channel/([^/?]+)', channel_url)
            
            if username_match:
                channel_id_field = username_match.group(1)
                channel_name = f"@{channel_id_field}"
            elif channel_id_match:
                channel_id_field = channel_id_match.group(1)
                channel_name = channel_id_field
            else:
                return jsonify({'success': False, 'error': 'Invalid YouTube channel URL'}), 400
        elif platform == 'instagram' or platform == 'tiktok':
            # Extract username from URL
            import re
            username_match = re.search(r'@?([^/?]+)$', channel_url.rstrip('/'))
            if username_match:
                channel_id_field = username_match.group(1)
                channel_name = f"@{channel_id_field}"
            else:
                return jsonify({'success': False, 'error': f'Invalid {platform} URL'}), 400
        
        # Parse video duration from flexible format (30min, 1h, 8h30m, etc.)
        import re
        duration_str = str(data.get('video_duration', '30min')).lower().strip()
        hours = 0
        minutes = 0
        
        # Extract hours (e.g., 6h, 6 h, 6 hours)
        hour_match = re.search(r'(\d+)\s*h(?:ours?|r)?', duration_str)
        if hour_match:
            hours = int(hour_match.group(1))
        
        # Extract minutes (e.g., 30m, 30 min, 30 minutes)
        minute_match = re.search(r'(\d+)\s*m(?:inutes?|in)?', duration_str)
        if minute_match:
            minutes = int(minute_match.group(1))
        
        # If neither was found, try to interpret as a plain number
        if not hour_match and not minute_match:
            num_match = re.search(r'(\d+)', duration_str)
            if num_match:
                num = int(num_match.group(1))
                # If user entered a large number, treat as minutes
                if num >= 100:
                    minutes = num
                else:
                    # Default to minutes for small numbers
                    minutes = num
        
        # Calculate total minutes
        duration_minutes = (hours * 60) + minutes
        if duration_minutes <= 0:
            duration_minutes = 30  # Default to 30 minutes
        
        # Build channel kwargs based on platform
        channel_kwargs = {
            'platform': platform,
            'product_id': data.get('product_id'),
            'status': 'active',  # Start production immediately
            'research_enabled': True
        }
        
        # Videos per day (new) or legacy upload_frequency
        videos_per_day = data.get('videos_per_day')
        if videos_per_day:
            channel_kwargs['videos_per_day'] = int(videos_per_day)
        else:
            # Legacy support
            channel_kwargs['upload_frequency'] = data.get('upload_frequency', 'daily')
        
        # Daily production spend
        daily_spend = data.get('daily_production_spend')
        if daily_spend:
            channel_kwargs['daily_production_spend'] = float(daily_spend)
        
        # Platform-specific fields
        if platform == 'youtube':
            channel_kwargs.update({
                'video_duration': duration_minutes,  # Store as total minutes
                'voice_type': data.get('voice_type'),
                'voice': data.get('voice_id'),
                'voice_id': data.get('voice_id'),
                'group_id': data.get('group_id'),
                'content_style_id': data.get('content_style_id'),
                'content_type': 'video',
                'visual_style': 'black_rain'
            })
        elif platform == 'tiktok':
            channel_kwargs.update({
                'avatar_url': data.get('avatar_url', ''),
                'tiktok_content_style': data.get('tiktok_content_style', 'ugc_video'),
                'content_type': 'tiktok_' + data.get('tiktok_content_style', 'ugc_video'),
                'video_duration': 60  # TikTok videos are ~60 seconds
            })
        elif platform == 'instagram':
            channel_kwargs.update({
                'avatar_url': data.get('avatar_url', ''),
                'instagram_post_type': data.get('instagram_post_type', 'carousel'),
                'content_type': 'instagram_' + data.get('instagram_post_type', 'carousel'),
                'video_duration': 60 if data.get('instagram_post_type') == 'reel' else 0  # Reels ~60s, carousels no duration
            })
        
        # Store platform-specific channel ID
        if platform == 'youtube':
            channel_kwargs['youtube_channel_id'] = channel_id_field
        elif platform == 'tiktok':
            channel_kwargs['tiktok_username'] = channel_id_field
        elif platform == 'instagram':
            channel_kwargs['instagram_username'] = channel_id_field
        
        # Get user's MongoDB _id (not Discord ID)
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        if not user_doc:
            return jsonify({'success': False, 'error': 'User not found'}), 400
        
        user_mongo_id = str(user_doc['_id'])
        
        # Add channel to campaign
        channel_id = db.add_channel_to_campaign(
            campaign_id,
            user_mongo_id,
            channel_id_field,
            channel_name or channel_id_field,
            **channel_kwargs
        )
        
        if channel_id:
            return jsonify({
                'success': True,
                'channel_id': channel_id,
                'message': f'Channel added successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to add channel'}), 500
            
    except Exception as e:
        print(f"Error adding channel: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/status', methods=['PUT'])
@login_required
def update_channel_status(campaign_id, channel_id):
    """Update channel status (pause/resume/archive)"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status or new_status not in ['testing', 'scaling', 'paused', 'archived', 'active', 'disabled']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Update status
        success = db.update_channel_status(channel_id, new_status)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Channel status updated to {new_status}'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update status'}), 500
            
    except Exception as e:
        print(f"Error updating channel status: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/end', methods=['POST'])
@login_required
def end_channel(campaign_id, channel_id):
    """Permanently end a channel"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Update channel status to ended
        from bson import ObjectId
        result = db.channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {
                'status': 'ended',
                'ended_at': datetime.utcnow()
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error ending channel: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/update-product', methods=['PUT'])
@login_required
def update_channel_product(campaign_id, channel_id):
    """Update channel's product assignment"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': 'Product ID required'}), 400
        
        result = db.channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {'product_id': ObjectId(product_id), 'updated_at': datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error updating channel product: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/update-frequency', methods=['PUT'])
@login_required
def update_channel_frequency(campaign_id, channel_id):
    """Update channel's upload frequency (videos_per_day)"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        videos_per_day = data.get('videos_per_day')
        
        if videos_per_day is None:
            return jsonify({'success': False, 'error': 'Videos per day required'}), 400
        
        videos_per_day = int(videos_per_day)
        if videos_per_day < 1 or videos_per_day > 10:
            return jsonify({'success': False, 'error': 'Videos per day must be between 1 and 10'}), 400
        
        channels_collection = db.db['campaign_channels']
        result = channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {'videos_per_day': videos_per_day, 'updated_at': datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error updating channel frequency: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/update-spend', methods=['PUT'])
@login_required
def update_channel_spend(campaign_id, channel_id):
    """Update channel's daily production spend"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        daily_spend = data.get('daily_production_spend')
        
        if daily_spend is None:
            return jsonify({'success': False, 'error': 'Daily spend required'}), 400
        
        daily_spend = float(daily_spend)
        if daily_spend < 0:
            return jsonify({'success': False, 'error': 'Daily spend must be positive'}), 400
        
        channels_collection = db.db['campaign_channels']
        result = channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {'daily_production_spend': daily_spend, 'updated_at': datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error updating channel spend: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/update-voice', methods=['PUT'])
@login_required
def update_channel_voice(campaign_id, channel_id):
    """Update channel's voice settings (YouTube only)"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        voice_type = data.get('voice_type')
        voice_id = data.get('voice_id')
        
        if not voice_type or not voice_id:
            return jsonify({'success': False, 'error': 'Voice type and ID required'}), 400
        
        result = db.channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {
                'voice_type': voice_type,
                'voice_id': voice_id,
                'voice': voice_id,  # For compatibility
                'updated_at': datetime.utcnow()
            }}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error updating channel voice: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/update-avatar', methods=['PUT'])
@login_required
def update_channel_avatar(campaign_id, channel_id):
    """Update channel's avatar URL (TikTok/Instagram only)"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        avatar_url = data.get('avatar_url')
        
        result = db.channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {'$set': {'avatar_url': avatar_url or '', 'updated_at': datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
    except Exception as e:
        print(f"Error updating channel avatar: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========================================
# UGC PRODUCTION TEST
# ========================================

@campaign_bp.route('/test-ugc-production', methods=['POST'])
@login_required
def test_ugc_production():
    """
    Simple test endpoint for UGC production
    Just provide a product ID and it generates a video
    """
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': 'Product ID required'}), 400
        
        # Get product
        product = db.get_product(product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        # Create a test channel object with mock ID for persona saving
        from bson import ObjectId
        test_channel = {
            '_id': ObjectId(),  # Add ID so persona can save to DB
            'platform': 'tiktok',
            'username': '@test',
            'product_id': product_id,
            'avatar_url': data.get('avatar_url', 'https://i.pravatar.cc/300')  # Default avatar
        }
        
        # Import UGC service with fallback
        try:
            from services.ugc_sora_service import ugc_sora_service
        except ImportError:
            # Try absolute import
            import importlib.util
            import os
            service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'ugc_sora_service.py')
            spec = importlib.util.spec_from_file_location("ugc_sora_service", service_path)
            ugc_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ugc_module)
            ugc_sora_service = ugc_module.ugc_sora_service
        
        # Run async production
        import asyncio
        import threading
        
        result_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        ugc_sora_service.produce_ugc_video(test_channel, product)
                    )
                    result_container['value'] = result
                finally:
                    loop.close()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=600)  # 10 minute timeout
        
        if thread.is_alive():
            return jsonify({'success': False, 'error': 'Production timeout (videos take 2-3 min)'}), 500
        
        if result_container['error']:
            return jsonify({'success': False, 'error': result_container['error']}), 500
        
        result = result_container['value']
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'video_url': result['video_url'],
                'drive_file_id': result.get('drive_file_id'),
                'script': result.get('script'),
                'persona': result.get('persona'),
                'message': 'UGC video generated successfully!'
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 500
        
    except Exception as e:
        print(f"Error in test UGC production: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ========================================
# OAUTH ACCOUNT CONNECTION
# ========================================

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/connect-tiktok', methods=['GET'])
@login_required
def connect_tiktok_authorize(campaign_id, channel_id):
    """Initiate TikTok OAuth flow"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        from services.tiktok_posting_service import TikTokPostingService
        tiktok_service = TikTokPostingService()
        
        if not tiktok_service.client_key:
            return jsonify({'success': False, 'error': 'TikTok OAuth not configured. Please set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env'}), 400
        
        # Generate state with channel_id for callback
        import secrets
        state = f"{channel_id}:{secrets.token_urlsafe(16)}"
        
        # Store state in session for verification
        from flask import session
        session[f'tiktok_oauth_state_{channel_id}'] = state
        
        oauth_url = tiktok_service.get_oauth_url(state=state)
        
        return jsonify({
            'success': True,
            'oauth_url': oauth_url
        })
        
    except Exception as e:
        print(f"Error initiating TikTok OAuth: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/auth/tiktok/callback', methods=['GET'])
@login_required
def tiktok_oauth_callback():
    """Handle TikTok OAuth callback"""
    try:
        from flask import request, session, redirect, url_for
        from services.tiktok_posting_service import TikTokPostingService
        
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='TikTok authorization denied'))
        
        if not code or not state:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Missing OAuth parameters'))
        
        # Extract channel_id from state
        channel_id = state.split(':')[0] if ':' in state else None
        if not channel_id:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Invalid state parameter'))
        
        # Verify state
        session_key = f'tiktok_oauth_state_{channel_id}'
        if session_key not in session or session[session_key] != state:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Invalid state - possible CSRF attack'))
        
        # Exchange code for token (async)
        tiktok_service = TikTokPostingService()
        import asyncio
        token_data = asyncio.run(tiktok_service.exchange_code_for_token(code))
        
        if not token_data.get('access_token'):
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Failed to get access token'))
        
        # Get channel to find campaign_id
        channel = db.get_channel_by_id(channel_id)
        if not channel:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Channel not found'))
        
        campaign_id = channel.get('campaign_id')
        
        # Save token to channel
        from bson import ObjectId
        from datetime import datetime, timedelta
        
        channels_collection = db.db['campaign_channels']
        channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {
                '$set': {
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'tiktok_open_id': token_data.get('open_id'),
                    'token_expires_at': datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600)),
                    'oauth_connected_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Clear session state
        session.pop(session_key, None)
        
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id, success='TikTok account connected successfully'))
        
    except Exception as e:
        print(f"Error in TikTok OAuth callback: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('campaigns.view_campaign', campaign_id='', error=str(e)))

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/connect-instagram', methods=['GET'])
@login_required
def connect_instagram_authorize(campaign_id, channel_id):
    """Initiate Instagram OAuth flow"""
    try:
        is_owner, campaign, user_mongo_id = verify_campaign_ownership(campaign_id)
        if not is_owner:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        from services.instagram_posting_service import InstagramPostingService
        instagram_service = InstagramPostingService()
        
        if not instagram_service.app_id:
            return jsonify({'success': False, 'error': 'Instagram OAuth not configured. Please set INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET in .env'}), 400
        
        # Generate state with channel_id for callback
        import secrets
        state = f"{channel_id}:{secrets.token_urlsafe(16)}"
        
        # Store state in session for verification
        from flask import session
        session[f'instagram_oauth_state_{channel_id}'] = state
        
        oauth_url = instagram_service.get_oauth_url(state=state)
        
        return jsonify({
            'success': True,
            'oauth_url': oauth_url
        })
        
    except Exception as e:
        print(f"Error initiating Instagram OAuth: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@campaign_bp.route('/auth/instagram/callback', methods=['GET'])
@login_required
def instagram_oauth_callback():
    """Handle Instagram OAuth callback"""
    try:
        from flask import request, session, redirect, url_for
        from services.instagram_posting_service import InstagramPostingService
        import asyncio
        
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Instagram authorization denied'))
        
        if not code or not state:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Missing OAuth parameters'))
        
        # Extract channel_id from state
        channel_id = state.split(':')[0] if ':' in state else None
        if not channel_id:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Invalid state parameter'))
        
        # Verify state
        session_key = f'instagram_oauth_state_{channel_id}'
        if session_key not in session or session[session_key] != state:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Invalid state - possible CSRF attack'))
        
        # Exchange code for token (async)
        instagram_service = InstagramPostingService()
        token_data = asyncio.run(instagram_service.exchange_code_for_token(code))
        
        if not token_data.get('access_token'):
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Failed to get access token'))
        
        # Get channel to find campaign_id
        channel = db.get_channel_by_id(channel_id)
        if not channel:
            return redirect(url_for('campaigns.view_campaign', campaign_id='', error='Channel not found'))
        
        campaign_id = channel.get('campaign_id')
        
        # Save token to channel
        from bson import ObjectId
        from datetime import datetime, timedelta
        
        channels_collection = db.db['campaign_channels']
        channels_collection.update_one(
            {'_id': ObjectId(channel_id)},
            {
                '$set': {
                    'access_token': token_data.get('access_token'),
                    'ig_user_id': token_data.get('user_id'),
                    'token_expires_at': datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 5184000)),
                    'oauth_connected_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Clear session state
        session.pop(session_key, None)
        
        return redirect(url_for('campaigns.view_campaign', campaign_id=campaign_id, success='Instagram account connected successfully'))
        
    except Exception as e:
        print(f"Error in Instagram OAuth callback: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('campaigns.view_campaign', campaign_id='', error=str(e)))

@campaign_bp.route('/test-cpa-analysis', methods=['POST'])
@login_required
def test_cpa_analysis():
    """
    Test endpoint to see what CPA analysis extracts from landing page
    """
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'success': False, 'error': 'Product ID required'}), 400
        
        # Get product
        product = db.get_product(product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        # Import UGC service
        try:
            from services.ugc_sora_service import ugc_sora_service
        except ImportError:
            import importlib.util
            import os
            service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'ugc_sora_service.py')
            spec = importlib.util.spec_from_file_location("ugc_sora_service", service_path)
            ugc_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ugc_module)
            ugc_sora_service = ugc_module.ugc_sora_service
        
        # Run analysis
        import asyncio
        import threading
        
        result_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    analysis = loop.run_until_complete(
                        ugc_sora_service.analyze_product_or_offer(product)
                    )
                    result_container['value'] = analysis
                finally:
                    loop.close()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=60)
        
        if thread.is_alive():
            return jsonify({'success': False, 'error': 'Analysis timeout'}), 500
        
        if result_container['error']:
            return jsonify({'success': False, 'error': result_container['error']}), 500
        
        analysis = result_container['value']
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'what_they_offer': analysis.get('what_they_offer', 'NOT EXTRACTED'),
            'offer_type': analysis.get('offer_type', 'NOT EXTRACTED'),
            'conversion_action': analysis.get('conversion_action', 'NOT EXTRACTED'),
            'benefits': analysis.get('benefits', []),
            'target_audience': analysis.get('target_audience', 'NOT EXTRACTED'),
            'is_cpa_offer': analysis.get('is_cpa_offer', False)
        })
        
    except Exception as e:
        print(f"Error in CPA analysis test: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ========================================
# CAMPAIGN ANALYTICS
# ========================================

@campaign_bp.route('/<campaign_id>/analytics')
@login_required
def campaign_analytics(campaign_id):
    """Analytics dashboard for campaign"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            flash('Unauthorized access', 'error')
            return redirect(url_for('campaigns.campaigns_list'))
        
        # Get analytics data
        days = int(request.args.get('days', 30))
        analytics = db.get_campaign_analytics(campaign_id, days=days)
        cost_breakdown = db.get_campaign_cost_breakdown(campaign_id, days=days)
        
        # Get channels for per-channel breakdown
        channels = db.get_campaign_channels(campaign_id)
        
        return render_template('modern/campaign_analytics.html',
                             campaign=campaign,
                             analytics=analytics,
                             cost_breakdown=cost_breakdown,
                             channels=channels,
                             days=days)
    except Exception as e:
        print(f"Error loading analytics: {e}")
        traceback.print_exc()
        flash('Error loading analytics', 'error')
        return redirect(url_for('campaigns.campaign_detail', campaign_id=campaign_id))

# ========================================
# API ENDPOINTS FOR AJAX
# ========================================

@campaign_bp.route('/api/<campaign_id>/metrics')
@login_required
def get_campaign_metrics(campaign_id):
    """Get real-time campaign metrics (JSON API)"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        days = int(request.args.get('days', 7))
        analytics = db.get_campaign_analytics(campaign_id, days=days)
        
        # Calculate totals
        total_views = sum(a['views'] for a in analytics)
        total_revenue = sum(a['revenue'] for a in analytics)
        total_cost = sum(a['api_costs'].get('total', 0) for a in analytics)
        
        return jsonify({
            'success': True,
            'metrics': {
                'total_views': total_views,
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'roi': ((total_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0,
                'daily_data': analytics
            }
        })
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/api/<campaign_id>/cost-breakdown')
@login_required
def get_cost_breakdown(campaign_id):
    """Get API cost breakdown by service (JSON API)"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        days = int(request.args.get('days', 30))
        breakdown = db.get_campaign_cost_breakdown(campaign_id, days=days)
        
        return jsonify({
            'success': True,
            'breakdown': breakdown
        })
    except Exception as e:
        print(f"Error getting cost breakdown: {e}")
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/api/<campaign_id>/channels/<channel_id>/analytics')
@login_required
def get_channel_analytics(campaign_id, channel_id):
    """Get analytics for a specific channel (JSON API)"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        days = int(request.args.get('days', 30))
        analytics = db.get_channel_analytics(channel_id, days=days)
        
        return jsonify({
            'success': True,
            'analytics': analytics
        })
    except Exception as e:
        print(f"Error getting channel analytics: {e}")
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/api/upload-avatar-image', methods=['POST'])
@login_required
def upload_avatar_image():
    """Upload avatar image to Google Drive and return URL"""
    try:
        if 'avatar_image' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['avatar_image']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': 'Only PNG and JPG images allowed'}), 400
        
        # Read file data
        file_data = file.read()
        
        # Validate file size (10MB max)
        if len(file_data) > 10 * 1024 * 1024:
            return jsonify({'success': False, 'error': 'File too large (max 10MB)'}), 400
        
        # Upload to Google Drive
        import base64
        import asyncio
        
        # Convert to base64 for upload function
        base64_image = base64.b64encode(file_data).decode('utf-8')
        
        # Use the UGC service's image upload function
        try:
            from services.ugc_sora_service import ugc_sora_service
        except ImportError:
            import importlib.util
            import os
            service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'ugc_sora_service.py')
            spec = importlib.util.spec_from_file_location("ugc_sora_service", service_path)
            ugc_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ugc_module)
            ugc_sora_service = ugc_module.ugc_sora_service
        
        # Run async upload
        def run_async_upload():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    ugc_sora_service._upload_image_to_temp_storage(base64_image)
                )
                return result
            finally:
                loop.close()
        
        import threading
        result_container = {'url': None, 'error': None}
        
        def thread_func():
            try:
                result_container['url'] = run_async_upload()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=30)
        
        if thread.is_alive():
            return jsonify({'success': False, 'error': 'Upload timeout'}), 500
        
        if result_container['error']:
            return jsonify({'success': False, 'error': result_container['error']}), 500
        
        if not result_container['url']:
            return jsonify({'success': False, 'error': 'Upload failed'}), 500
        
        return jsonify({
            'success': True,
            'url': result_container['url']
        })
        
    except Exception as e:
        print(f"Error uploading avatar image: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ========================================
# CAMPAIGN ACTIONS
# ========================================

@campaign_bp.route('/<campaign_id>/pause', methods=['POST'])
@login_required
def pause_campaign(campaign_id):
    """Pause entire campaign"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Update campaign status
        success = db.update_campaign(campaign_id, {'status': 'paused'})
        
        if success:
            flash('Campaign paused successfully', 'success')
            return jsonify({'success': True, 'message': 'Campaign paused'})
        else:
            return jsonify({'error': 'Failed to pause campaign'}), 500
    except Exception as e:
        print(f"Error pausing campaign: {e}")
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/resume', methods=['POST'])
@login_required
def resume_campaign(campaign_id):
    """Resume paused campaign"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Update campaign status
        success = db.update_campaign(campaign_id, {'status': 'active'})
        
        if success:
            flash('Campaign resumed successfully', 'success')
            return jsonify({'success': True, 'message': 'Campaign resumed'})
        else:
            return jsonify({'error': 'Failed to resume campaign'}), 500
    except Exception as e:
        print(f"Error resuming campaign: {e}")
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_campaign(campaign_id):
    """Delete campaign and all associated data"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Delete campaign
        success = db.delete_campaign(campaign_id)
        
        if success:
            flash('Campaign deleted successfully', 'success')
            return jsonify({'success': True, 'message': 'Campaign deleted', 'redirect': url_for('campaigns.campaigns_list')})
        else:
            return jsonify({'error': 'Failed to delete campaign'}), 500
    except Exception as e:
        print(f"Error deleting campaign: {e}")
        return jsonify({'error': str(e)}), 500

# ========================================
# PRODUCTION ENDPOINTS
# ========================================

@campaign_bp.route('/<campaign_id>/start-production', methods=['POST'])
@login_required
def start_campaign_production(campaign_id):
    """Start production for all channels in campaign"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json() if request.is_json else request.form
        video_count = int(data.get('video_count', 10))
        
        # Import campaign production service
        from nicole_web_suite_template.services.campaign_production_service import campaign_production
        
        # Get channels
        channels = db.get_campaign_channels(campaign_id)
        
        if not channels:
            return jsonify({'error': 'No channels in campaign'}), 400
        
        # Start production for each channel (async) - Windows-safe
        import asyncio
        import threading
        
        async def start_production():
            tasks = []
            for channel in channels:
                if channel['status'] in ['testing', 'scaling']:
                    task = campaign_production.start_campaign_batch_production(
                        campaign_id,
                        str(channel['_id']),
                        video_count
                    )
                    tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        
        # Run in separate thread to avoid Windows socket issues
        results_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                # Create new event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(start_production())
                    results_container['value'] = results
                finally:
                    loop.close()
            except Exception as e:
                results_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=300)  # 5 minute timeout
        
        if thread.is_alive():
            return jsonify({'error': 'Production timeout'}), 500
        
        if results_container['error']:
            return jsonify({'error': results_container['error']}), 500
        
        results = results_container['value']
        
        return jsonify({
            'success': True,
            'message': f'Production started for {len(channels)} channels',
            'results': [str(r) if isinstance(r, Exception) else r for r in results]
        })
        
    except Exception as e:
        print(f"Error starting production: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@campaign_bp.route('/<campaign_id>/channels/<channel_id>/start-production', methods=['POST'])
@login_required
def start_channel_production(campaign_id, channel_id):
    """Start production for a specific channel"""
    try:
        # Verify ownership
        is_owner, campaign, _ = verify_campaign_ownership(campaign_id)
        if not campaign or not is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json() if request.is_json else request.form
        video_count = int(data.get('video_count', 1))
        
        # Import campaign production service
        from nicole_web_suite_template.services.campaign_production_service import campaign_production
        
        # Start production (Windows-safe async)
        import asyncio
        import threading
        
        # Run in separate thread to avoid Windows socket issues
        result_container = {'value': None, 'error': None}
        
        def run_async():
            try:
                # Create new event loop in this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        campaign_production.start_campaign_batch_production(
                            campaign_id,
                            channel_id,
                            video_count
                        )
                    )
                    result_container['value'] = result
                finally:
                    loop.close()
            except Exception as e:
                result_container['error'] = str(e)
        
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=300)  # 5 minute timeout
        
        if thread.is_alive():
            return jsonify({'error': 'Production timeout'}), 500
        
        if result_container['error']:
            return jsonify({'error': result_container['error']}), 500
        
        result = result_container['value']
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': f'Started production of {video_count} videos',
                'result': result
            })
        else:
            return jsonify({'error': result.get('error', 'Production failed')}), 500
        
    except Exception as e:
        print(f"Error starting channel production: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

