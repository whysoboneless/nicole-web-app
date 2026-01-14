"""
Dashboard routes for Nicole Web Suite
REAL Discord bot dashboard functionality - NO MOCK DATA
"""

import sys
import os
# Add Discord bot path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from core.database import Database
from core.analysis_service import AnalysisService
from core.user_api_middleware import api_key_required, patch_api_clients, set_user_context
from datetime import datetime
from bson import ObjectId
import asyncio
import threading
import time

# Import Discord bot modules directly
try:
    from utils.ai_utils import *  # All AI utilities from Discord bot
    from database import Database as DiscordDatabase  # Discord bot database
    from channel_discovery_app.channel_discovery_service import ChannelDiscoveryService  # Channel discovery logic
    DISCORD_BOT_AVAILABLE = True
except ImportError as e:
    # print(f"Discord bot modules not available: {e}")  # Commented - too noisy
    DISCORD_BOT_AVAILABLE = False
import asyncio

def format_views(views):
    """Format view counts to human readable format (e.g., 1.2M, 500K)"""
    if not views or views == 0:
        return '0'
    
    try:
        num = int(float(views))
        if num >= 1000000000:
            return f"{num / 1000000000:.1f}B"
        elif num >= 1000000:
            return f"{num / 1000000:.1f}M"
        elif num >= 1000:
            return f"{num / 1000:.1f}K"
        else:
            return f"{num:,}"
    except (ValueError, TypeError):
        return '0'

# Create blueprint with explicit template folder
dashboard_bp = Blueprint('dashboard', __name__, 
                        template_folder='templates',
                        static_folder='static')

# Register custom filters
dashboard_bp.add_app_template_filter(format_views, 'format_views')

# Initialize REAL services
db = Database()
analysis_service = AnalysisService()

@dashboard_bp.route('/')
def root():
    """Root route - redirect to login if not authenticated, otherwise dashboard"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.main'))
    else:
        return redirect('/auth/login')  # Use direct URL instead of url_for

@dashboard_bp.route('/dashboard')
@login_required
def main():
    """Main dashboard - Discord Based System"""
    try:
        
        print(f"🔑 Current user authenticated: {current_user.is_authenticated}")
        print(f"👤 Current user: {current_user.id} - {current_user.username}")
        print(f"👑 Is admin: {getattr(current_user, 'is_admin', False)}")
        print(f"🆔 Discord ID: {getattr(current_user, 'discord_id', 'None')}")
        
        # Use Discord ID methods
        user_groups = db.get_user_groups_sync(str(current_user.discord_id))
        available_groups = db.get_available_groups_sync(str(current_user.discord_id))
        
        # Add competitor_channels field to each group for template compatibility
        for group in user_groups + available_groups:
            if 'competitor_channels' not in group:
                group['competitor_channels'] = group.get('competitors', [])
        
        print(f"✅ Loaded {len(user_groups)} user groups, {len(available_groups)} available groups from REAL database")
        
        # Debug: Let's see what we actually got
        print(f"🔍 User groups debug: {[g.get('name', 'Unnamed') for g in user_groups]}")
        print(f"🔍 Available groups debug: {[g.get('name', 'Unnamed') for g in available_groups]}")
        
        # Get user's MongoDB _id for proper comparison
        user_doc = db.get_user_by_discord_id_sync(str(current_user.discord_id))
        user_object_id = user_doc['_id'] if user_doc else None
        
        # Create stats for template (fix the owned_groups calculation)
        stats = {
            'total_groups': len(user_groups),
            'owned_groups': len([g for g in user_groups if g.get('owner_id') == user_object_id]),
            'available_groups': len(available_groups)
        }
        
        print(f"📊 Stats calculated: {stats}")
        
        # Check if user wants modern UI (you can add this as a user preference later)
        use_modern = request.args.get('modern', 'true').lower() == 'true'
        
        if use_modern:
            return render_template('modern_dashboard.html', 
                                 user_groups=user_groups,
                                 available_groups=available_groups,
                                 current_user=current_user,
                                 user=current_user,
                                 stats=stats,
                                 show_admin_panel=getattr(current_user, 'is_admin', False))
        else:
            return render_template('dashboard.html', 
                                 user_groups=user_groups,
                                 available_groups=available_groups,
                                 current_user=current_user,
                                 user=current_user,  # Add user variable for template compatibility
                                 stats=stats,  # Add stats for template
                                 show_admin_panel=getattr(current_user, 'is_admin', False))
        
    except Exception as e:
        print(f"❌ Error loading REAL dashboard data: {e}")
        import traceback
        traceback.print_exc()
        raise e

@dashboard_bp.route('/create_group')
@login_required
def create_group():
    """Create New Project - Modern UI for creating market intelligence projects"""
    try:
        
        # print(f"👤 Current user: {current_user.id} - {current_user.username}")  # Commented - too noisy
        
        # Check for required API keys and pass status to template
        discord_id = str(current_user.discord_id)
        required_api_keys = ['Anthropic Claude']
        missing_keys = []
        
        for service in required_api_keys:
            api_key = db.get_user_api_key(discord_id, service)
            if not api_key:
                missing_keys.append(service)
        
        api_keys_status = {
            'missing_keys': missing_keys,
            'has_all_keys': len(missing_keys) == 0
        }
        
        return render_template('modern/create_group.html', api_keys_status=api_keys_status)
        
    except Exception as e:
        print(f"❌ Error loading create group page: {e}")
        import traceback
        traceback.print_exc()
        return render_template('modern/create_group.html')
    
@dashboard_bp.route('/create_group', methods=['POST'])
@login_required
@api_key_required
def create_group_post():
    """Handle project creation - EXACT same logic as Discord bot CreateGroupModal"""
    try:
        # Get data from request
        if request.is_json:
            data = request.get_json()
            group_name = data.get('group_name')
            channel_url = data.get('channel_url')
        else:
            group_name = request.form.get('group_name')
            channel_url = request.form.get('channel_url')
            
        if not all([group_name, channel_url]):
            return jsonify({'success': False, 'error': 'Group name and channel URL are required'}), 400
        
        print(f"🎯 Creating group: {group_name} with channel: {channel_url}")
        
        # Get current user's Discord ID and MongoDB _id (same as manual production)
        discord_id = str(current_user.discord_id)
        user_doc = db.users.find_one({"discord_id": discord_id})
        
        if not user_doc:
            return jsonify({'success': False, 'error': 'User not found'}), 400
        
        user_mongodb_id = user_doc['_id']
        print(f"✅ Found user {user_doc.get('username', 'Unknown')} with MongoDB _id: {user_mongodb_id}")
        
        # CHECK GROUP CREATION LIMITS - EXACT same as Discord bot CreateGroupModal
        can_create, limit_message = db.can_create_group_sync(str(user_mongodb_id))
        if not can_create:
            print(f"❌ User cannot create group: {limit_message}")
            return jsonify({'success': False, 'error': limit_message}), 400
        
        print("✅ User can create group (within limits)")
        
        # PREVENTATIVE MEASURE: Check for required API keys before starting group creation
        required_api_keys = ['Anthropic Claude']  # Add more as needed
        missing_keys = []
        
        for service in required_api_keys:
            api_key = db.get_user_api_key(discord_id, service)
            if not api_key:
                missing_keys.append(service)
        
        if missing_keys:
            missing_services = ', '.join(missing_keys)
            error_msg = f"Required API keys missing: {missing_services}. Please add them in the API Keys section before creating groups."
            print(f"❌ {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        print("✅ All required API keys are present")
        
        # Create progress tracking
        progress_id = f"group_creation_{user_mongodb_id}_{int(time.time())}"
        
        # Initialize progress
        progress_data = {
            "progress": 0,
            "step": "Starting analysis...",
            "status": "running"
        }
        
        # Store progress in database for tracking
        db.progress_tracking = getattr(db, 'progress_tracking', {})
        db.progress_tracking[progress_id] = progress_data
        
        def run_background_group_creation():
            """Run LOCAL group creation using WebAnalysisService - same as Discord bot"""
            try:
                print(f"🚀 Starting LOCAL group creation for {group_name}")
                
                # Create asyncio event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Import WebAnalysisService for local analysis
                    from dashboard.web_analysis_service import WebAnalysisService
                    
                    # Set user context for API middleware using the Discord ID we captured
                    set_user_context(discord_id, db)
                    
                    # Initialize the analysis service
                    analysis_service_local = WebAnalysisService(db)
                    
                    # Update progress: Step 1
                    db.progress_tracking[progress_id]["progress"] = 25
                    db.progress_tracking[progress_id]["step"] = "Analyzing channel content DNA..."
                    
                    # Run the niche analysis (EXACT same as Discord bot)
                    result = loop.run_until_complete(
                        analysis_service_local.perform_niche_analysis(
                            channel_url=channel_url,
                            group_name=group_name,
                            user_id=str(user_mongodb_id),
                            is_public=False,
                            discord_id=discord_id,
                            user_doc=user_doc
                        )
                    )
                    
                    # Update progress: Step 2  
                    db.progress_tracking[progress_id]["progress"] = 75
                    db.progress_tracking[progress_id]["step"] = "Finding similar competitor channels..."
                    
                    # Update group with proper owner
                    if "error" not in result and result.get("group_id"):
                        group_id = result["group_id"]
                        db.update_competitor_group(group_id, {
                            "owner_id": user_mongodb_id,
                            "user_id": str(user_mongodb_id)
                        })
                        
                        # Update progress: Complete
                        db.progress_tracking[progress_id]["progress"] = 100
                        db.progress_tracking[progress_id]["step"] = "Analysis complete! Building competitive intelligence group..."
                        db.progress_tracking[progress_id]["status"] = "complete"
                        db.progress_tracking[progress_id]["group_id"] = group_id
                        
                        print(f"✅ Local analysis completed successfully for group {group_id}")
                        return {"success": True, "group_id": group_id}
                    else:
                        error_msg = result.get("error", "Unknown analysis error")
                        db.progress_tracking[progress_id]["status"] = "error"
                        db.progress_tracking[progress_id]["step"] = f"Error: {error_msg}"
                        return {"error": error_msg}
                    
                finally:
                    loop.close()
                        
            except Exception as e:
                print(f"❌ Local analysis error: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Update progress with error
                db.progress_tracking[progress_id]["status"] = "error"
                db.progress_tracking[progress_id]["step"] = f"Error: {str(e)}"
                
                return {"error": str(e)}
        
        # Run in background thread
        thread = threading.Thread(target=run_background_group_creation)
        thread.start()
        # print(f"✅ Background thread started for group creation")  # Debug - commented
        
        # Return immediately with progress tracking ID
        return jsonify({
            'success': True, 
            'message': f'Group creation started for "{group_name}". This may take 2-3 minutes for analysis to complete.',
            'progress_id': progress_id,  # For real progress tracking
            'redirect_to_competitors': True
        })
                    
    except Exception as e:
        print(f"❌ Error in create_group_post: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/check-progress/<progress_id>')
@login_required
def check_progress(progress_id):
    """Check real progress of group creation"""
    try:
        progress_data = getattr(db, 'progress_tracking', {}).get(progress_id)
        
        if not progress_data:
            return jsonify({'success': False, 'error': 'Progress not found'}), 404
        
        return jsonify({
            'success': True,
            'progress': progress_data.get('progress', 0),
            'step': progress_data.get('step', ''),
            'status': progress_data.get('status', 'running'),
            'group_id': progress_data.get('group_id')
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/competitor-selection')
@login_required
def competitor_selection():
    """Competitor selection page - for creating new groups or editing existing ones"""
    try:
        group_id = request.args.get('group_id')
        
        if group_id:
            # Editing existing group - get group details
            group = db.get_group_sync(group_id)
            if not group:
                flash('Group not found.', 'error')
                return redirect(url_for('dashboard.my_groups'))
            
            # Get current competitors
            current_competitors = db.get_competitors_sync(group_id)
            
            return render_template('modern/competitor_selection.html', 
                                 group=group,
                                 group_id=group_id,
                                 current_competitors=current_competitors,
                                 editing_mode=True)
        else:
            # Creating new group
            return render_template('modern/competitor_selection.html', editing_mode=False)
            
    except Exception as e:
        print(f"❌ Error loading competitor selection: {e}")
        flash('Error loading competitor selection.', 'error')
        return redirect(url_for('dashboard.my_groups'))

@dashboard_bp.route('/api/get-potential-competitors', methods=['GET'])
@login_required
def get_potential_competitors():
    """Get potential competitors for a group"""
    try:
        group_id = request.args.get('group_id')
        if not group_id:
            return jsonify({'success': False, 'error': 'Group ID required'}), 400
        
        # Get group with potential competitors
        group = db.competitor_groups.find_one({"_id": ObjectId(group_id)})
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'}), 404
        
        potential_competitors = group.get('potential_competitors', {})
        
        return jsonify({
            'success': True,
            'potential_competitors': potential_competitors,
            'group_name': group.get('name')
        })
            
    except Exception as e:
        print(f"❌ Error getting potential competitors: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/get-group-competitors', methods=['GET'])
@login_required
def get_group_competitors():
    """Get existing competitors for a group"""
    try:
        group_id = request.args.get('group_id')
        if not group_id:
            return jsonify({'success': False, 'error': 'Group ID required'}), 400
        
        # Verify user owns this group
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        
        if group_id not in user_group_ids:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Get existing competitors
        competitors = db.get_competitors_sync(group_id)
        
        return jsonify({
            'success': True,
            'competitors': competitors
        })
            
    except Exception as e:
        print(f"❌ Error getting group competitors: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/finalize-group', methods=['POST'])
@login_required
def finalize_group():
    """Finalize group with selected competitors"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        selected_competitors = data.get('selected_competitors', [])
        
        if not all([group_id, selected_competitors]):
            return jsonify({'success': False, 'error': 'Group ID and competitors required'}), 400
        
        def run_background_finalization():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Use web analysis service (no circular imports)
                from dashboard.web_analysis_service import WebAnalysisService
                analysis_service = WebAnalysisService(db)
                
                # Add each selected competitor to the group with full analysis
                for competitor_id in selected_competitors:
                    # Use the same logic as individual competitor addition
                    try:
                        result = loop.run_until_complete(
                            analysis_service.add_competitor_to_group(
                                group_id, 
                                competitor_id, 
                                "Manual Addition",  # matching_title
                                []  # matching_series - will be analyzed
                            )
                        )
                        if result:
                            print(f"✅ Added competitor {competitor_id} to group {group_id}")
                        else:
                            print(f"⚠️ Failed to add competitor {competitor_id} to group {group_id}")
                    except Exception as e:
                        print(f"❌ Error adding competitor {competitor_id}: {e}")
                        continue
                
                    # Mark group as finalized
                    db.update_competitor_group(group_id, {
                        "status": "finalized",
                        "competitors_count": len(selected_competitors)
                    })
                    
                    # Trigger FULL competitor analysis after all competitors are added
                    print(f"🚀 Starting FULL competitor analysis for finalized group {group_id}...")
                    
                    # Use the web app's own analysis service to avoid circular imports
                    try:
                        from core.analysis_service import AnalysisService
                        real_analysis_service = AnalysisService()
                        
                        # This calls the EXACT analyze_competitor_channels from Discord bot
                        analysis_result = real_analysis_service.analyze_competitor_channels_sync(group_id)
                        
                        if analysis_result and not isinstance(analysis_result, dict) or (isinstance(analysis_result, dict) and "error" not in analysis_result):
                            print(f"✅ FULL competitor analysis completed for finalized group {group_id}")
                        else:
                            error_msg = analysis_result.get("error", "Unknown error") if isinstance(analysis_result, dict) else "Analysis failed"
                            print(f"⚠️ Competitor analysis had issues: {error_msg}")
                            
                    except ImportError as import_error:
                        print(f"⚠️ Could not import Discord bot analysis service: {import_error}")
                        print(f"✅ Competitors added successfully, but full analysis will need to be run manually")
                    except Exception as analysis_error:
                        print(f"⚠️ Error during competitor analysis: {analysis_error}")
                        print(f"✅ Competitors added successfully, but analysis failed")
                    
                    print(f"✅ Finalized group {group_id} with {len(selected_competitors)} competitors")
            
            except Exception as e:
                print(f"❌ Error finalizing group: {str(e)}")
        
        # Run in background
        thread = threading.Thread(target=run_background_finalization)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Group finalization started with {len(selected_competitors)} competitors'
        })
        
    except Exception as e:
        print(f"❌ Error in finalize_group: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/add-competitor-to-group', methods=['POST'])
@login_required
def add_competitor_to_group():
    """Add a single competitor to an existing group"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        channel_url = data.get('channel_url')
        
        if not all([group_id, channel_url]):
            return jsonify({'success': False, 'error': 'Group ID and channel URL required'}), 400
        
        # Get user ID
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Verify user owns this group
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        
        if group_id not in user_group_ids:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        def run_background_competitor_addition():
            """Add competitor in background using existing analysis service"""
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Use the existing web analysis service (correct import path)
                from dashboard.web_analysis_service import WebAnalysisService
                analysis_service = WebAnalysisService(db)
                
                # Extract channel ID from URL
                import re
                channel_id_match = re.search(r'(?:channel/|c/|@)([^/?]+)', channel_url)
                if not channel_id_match:
                    print(f"❌ Could not extract channel ID from URL: {channel_url}")
                    return {"error": "Invalid channel URL"}
                
                channel_identifier = channel_id_match.group(1)
                
                # Check if competitor already exists in the group
                existing_competitors = db.get_competitors_sync(group_id)
                if existing_competitors:
                    for competitor in existing_competitors:
                        # Check both channel_id and channel_identifier (handle @ usernames vs IDs)
                        existing_id = competitor.get('channel_id', '')
                        existing_username = competitor.get('username', '')
                        competitor_title = competitor.get('title', '')
                        
                        if (channel_identifier == existing_id or 
                            channel_identifier == existing_username or
                            channel_identifier.lstrip('@') == existing_username.lstrip('@')):
                            print(f"⚠️ Competitor '{competitor_title}' already exists in group {group_id}")
                            return {"error": f"Competitor '{competitor_title}' is already in this group"}
                
                print(f"✅ Competitor not found in group, proceeding with addition...")
                
                # Add competitor 
                result = loop.run_until_complete(
                    analysis_service.add_competitor_to_group(
                        group_id, 
                        channel_identifier, 
                        "Manual Addition",  # matching_title
                        []  # matching_series - will be analyzed
                    )
                )
                
                # If competitor was added successfully, trigger FULL competitor analysis
                # This is the EXACT same as Discord bot's "Outlier Analysis" button
                if result:
                    print(f"✅ Competitor added successfully!")
                    print(f"🚀 Starting FULL competitor analysis for group {group_id}...")
                    
                    # Use the REAL Discord bot analysis service - EXACT same code
                    from core.analysis_service import AnalysisService
                    real_analysis_service = AnalysisService()
                    
                    # This calls the EXACT analyze_competitor_channels from Discord bot
                    analysis_result = real_analysis_service.analyze_competitor_channels_sync(group_id)
                    
                    if analysis_result and not isinstance(analysis_result, dict) or (isinstance(analysis_result, dict) and "error" not in analysis_result):
                        print(f"✅ FULL competitor analysis completed for group {group_id}")
                    else:
                        error_msg = analysis_result.get("error", "Unknown error") if isinstance(analysis_result, dict) else "Analysis failed"
                        print(f"⚠️ Competitor analysis had issues: {error_msg}")
                
                if result:
                    print(f"✅ Successfully added competitor to group {group_id}")
                    return {"success": True, "competitor": result}
                else:
                    return {"error": "Failed to add competitor"}
                    
            except Exception as e:
                print(f"❌ Error adding competitor: {e}")
                return {"error": str(e)}
            finally:
                loop.close()
        
        # Run in background
        import threading
        thread = threading.Thread(target=run_background_competitor_addition)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Adding competitor to group... This may take a moment for analysis.'
        })
        
    except Exception as e:
        print(f"❌ Error in add_competitor_to_group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/remove-competitor-from-group', methods=['POST'])
@login_required
def remove_competitor_from_group():
    """Remove a competitor from a group"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        competitor_id = data.get('competitor_id')
        
        if not all([group_id, competitor_id]):
            return jsonify({'success': False, 'error': 'Group ID and competitor ID required'}), 400
        
        # Get user ID and verify ownership
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        
        if group_id not in user_group_ids:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Remove competitor from group (updated to use 'competitors' field)
        result = db.competitor_groups.update_one(
            {"_id": ObjectId(group_id)},
            {"$pull": {"competitors": {"channel_id": competitor_id}}}
        )
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Competitor removed from group successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Competitor not found in group'}), 404
            
    except Exception as e:
        print(f"❌ Error removing competitor: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/analyze-competitors', methods=['POST'])
@login_required
def analyze_competitors():
    """Trigger full competitor analysis - equivalent to Discord bot's 'Outlier Analysis' button"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        
        if not group_id:
            return jsonify({'success': False, 'error': 'Group ID required'}), 400
        
        # Get user ID and verify ownership
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        
        if group_id not in user_group_ids:
            return jsonify({'success': False, 'error': 'Access denied - you can only analyze your own groups'}), 403
        
        # Get group name for feedback
        group = db.competitor_groups.find_one({"_id": ObjectId(group_id)})
        group_name = group.get('name', 'Unknown Group') if group else 'Unknown Group'
        
        def run_competitor_analysis():
            """Run full competitor analysis in background - EXACT same as Discord bot"""
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Use the REAL Discord bot analysis service
                    from core.analysis_service import AnalysisService
                    analysis_service = AnalysisService()
                    
                    print(f"🚀 Starting full competitor analysis for group '{group_name}' (ID: {group_id})")
                    
                    # This is the EXACT same call as Discord bot's "Outlier Analysis" button
                    result = analysis_service.analyze_competitor_channels_sync(group_id)
                    
                    if result and "error" not in result:
                        print(f"✅ Successfully analyzed competitors for group '{group_name}'")
                        return {"success": True, "message": f"Competitor analysis completed for '{group_name}'"}
                    else:
                        error_msg = result.get("error", "Unknown error") if result else "No result returned"
                        print(f"❌ Competitor analysis failed: {error_msg}")
                        return {"error": f"Analysis failed: {error_msg}"}
                        
                finally:
                    loop.close()
                    
            except Exception as e:
                print(f"❌ Error in competitor analysis: {e}")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}
        
        # Start background analysis
        import threading
        thread = threading.Thread(target=run_competitor_analysis)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Started competitor analysis for "{group_name}". This may take a few minutes...',
            'group_id': group_id,
            'analyzing': True
        })
        
    except Exception as e:
        print(f"❌ Error starting competitor analysis: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/remove-group', methods=['POST'])
@login_required
def remove_group():
    """Remove/delete a group completely"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        
        print(f"🗑️ Remove group request received for group_id: {group_id}")
        
        if not group_id:
            return jsonify({'success': False, 'error': 'Group ID required'}), 400
        
        # Get user ID and verify ownership
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        
        print(f"🔍 User {discord_id} owns groups: {user_group_ids}")
        print(f"🔍 Attempting to delete group: {group_id}")
        
        if group_id not in user_group_ids:
            print(f"❌ Access denied: User {discord_id} does not own group {group_id}")
            return jsonify({'success': False, 'error': 'Access denied - you can only delete your own groups'}), 403
        
        # Get group name for confirmation message
        group = db.competitor_groups.find_one({"_id": ObjectId(group_id)})
        group_name = group.get('name', 'Unknown Group') if group else 'Unknown Group'
        
        # Delete the group and all related data
        try:
            # Delete the main group document
            group_result = db.competitor_groups.delete_one({"_id": ObjectId(group_id)})
            
            # Delete related series data
            series_result = db.series.delete_many({"group_id": ObjectId(group_id)})
            
            # Delete related themes data
            themes_result = db.themes.delete_many({"group_id": ObjectId(group_id)})
            
            print(f"✅ Deleted group '{group_name}': {group_result.deleted_count} groups, {series_result.deleted_count} series, {themes_result.deleted_count} themes")
            
            return jsonify({
                'success': True,
                'message': f'Group "{group_name}" and all related data deleted successfully'
            })
            
        except Exception as delete_error:
            print(f"❌ Error deleting group data: {delete_error}")
            return jsonify({'success': False, 'error': f'Failed to delete group: {str(delete_error)}'}), 500
            
    except Exception as e:
        print(f"❌ Error removing group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/check-resources', methods=['POST'])
@login_required
def check_resources():
    """API endpoint to check if resources are ready for a specific series+theme"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        series_name = data.get('series_name')
        theme_name = data.get('theme_name')
        
        if not all([group_id, series_name, theme_name]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Check resources in the competitor_groups collection
        try:
            group_doc = db.competitor_groups.find_one({"_id": ObjectId(group_id)})
            has_script_breakdown = False
            has_thumbnail_model = False
            
            if group_doc and "content_creation" in group_doc:
                # Create safe names (replace spaces and dots with underscores)
                safe_series_name = series_name.replace('.', '_').replace(' ', '_')
                safe_theme_name = theme_name.replace('.', '_').replace(' ', '_')
                
                # Get theme data from content_creation
                theme_data = group_doc["content_creation"].get(safe_series_name, {}).get(safe_theme_name, {})
                
                # Check for script breakdown
                has_script_breakdown = bool(theme_data.get('script_breakdown'))
                
                # Check for thumbnail model (needs both trained_model_version AND thumbnail_guidelines)
                has_thumbnail_model = bool(
                    theme_data.get('trained_model_version') and 
                    theme_data.get('thumbnail_guidelines')
                )
            
            has_resources = has_script_breakdown and has_thumbnail_model
            
            return jsonify({
                'success': True,
                'has_resources': has_resources,
                'has_script_breakdown': has_script_breakdown,
                'has_thumbnail_model': has_thumbnail_model
            })
        
        except Exception as e:
            print(f"❌ Error checking resources: {e}")
            return jsonify({'success': False, 'error': 'Failed to check resources'}), 500
            
    except Exception as e:
        print(f"❌ Error in check_resources: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@dashboard_bp.route('/api/prepare-resources', methods=['POST'])
@login_required
def prepare_resources():
    """API endpoint to trigger async resource preparation for a series+theme combination"""
    import logging
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    
    # Set up detailed logging for production
    logger = logging.getLogger(__name__)
    
    # Create a unique task ID for tracking
    import uuid
    task_id = str(uuid.uuid4())[:8]
    
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        series_name = data.get('series_name') 
        theme_name = data.get('theme_name')
        
        # Comprehensive parameter validation
        if not all([group_id, series_name, theme_name]):
            missing = [k for k, v in [('group_id', group_id), ('series_name', series_name), ('theme_name', theme_name)] if not v]
            error_msg = f'Missing required parameters: {", ".join(missing)}'
            logger.error(f"Resource preparation failed - {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # Validate user permissions
        if not current_user.is_authenticated:
            logger.error(f"Unauthorized resource preparation attempt for group {group_id}")
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        
        logger.info(f"🚀 Starting resource preparation task {task_id} for user {current_user.id}: {series_name} - {theme_name} (Group: {group_id})")
        
        # Start async resource preparation in background
        if DISCORD_BOT_AVAILABLE:
            try:
                # Import the resource prep functions - REAL IMPLEMENTATIONS
                from utils_dir.ai_utils import breakdown_script, analyze_thumbnails_with_ai, train_model_with_replicate
                from utils_dir.ai_utils import create_training_captions, download_and_prepare_images
                import asyncio
                import json
                
                # Start background task for resource preparation
                def run_async_preparation():
                    """Run async resource preparation in background thread"""
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            prepare_resources_async(task_id, group_id, series_name, theme_name, current_user.id)
                        )
                    finally:
                        loop.close()
                
                # Start background thread
                preparation_thread = threading.Thread(target=run_async_preparation, daemon=True)
                preparation_thread.start()
                
                logger.info(f"✅ Background resource preparation started for task {task_id}")
                
                return jsonify({
                    'success': True, 
                    'message': 'Resource preparation started in background',
                    'task_id': task_id,
                    'status': 'preparing'
                })
                
            except Exception as prep_error:
                error_msg = f'Failed to start resource preparation: {str(prep_error)}'
                logger.error(f"❌ {error_msg}")
                
                return jsonify({
                    'success': False, 
                    'error': error_msg,
                    'task_id': task_id
                }), 500
                
        else:
            logger.error("❌ Discord bot modules not available - cannot prepare resources")
            return jsonify({'success': False, 'error': 'Discord bot integration not available'}), 500
            
    except Exception as e:
        error_msg = f'Internal server error during resource preparation'
        logger.error(f"❌ {error_msg}: {e}", exc_info=True)
        
        return jsonify({
            'success': False, 
            'error': error_msg
        }), 500

@dashboard_bp.route('/my_groups')
@login_required
def my_groups():
    """My groups page - REAL Discord bot integration with modern UI and accurate metrics"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Enhance groups with accurate competitor and video counts
        enhanced_groups = []
        for group in user_groups:
            group_id = str(group.get('_id'))
            
            # Get real-time competitor count
            competitors = db.get_competitors_sync(group_id)
            competitor_count = len(competitors) if competitors else 0
            
            # Get real-time video count from ALL competitors in the group
            total_videos = 0
            try:
                # Get all competitors for this group
                group_competitors = db.get_competitors_sync(group_id)
                
                # Count videos from each competitor
                for competitor in group_competitors:
                    # Add competitor's video count (from various possible fields)
                    competitor_videos = (
                        competitor.get('video_count', 0) or 
                        competitor.get('total_videos', 0) or 
                        competitor.get('videos_analyzed', 0) or
                        competitor.get('total_video_count', 0) or
                        0
                    )
                    total_videos += competitor_videos
                    
                print(f"✅ Counted {total_videos} total videos from {len(group_competitors)} competitors")
                        
            except Exception as e:
                print(f"❌ Error counting videos for group {group_id}: {e}")
                import traceback
                traceback.print_exc()
            
            # Create enhanced group data
            enhanced_group = dict(group)  # Copy original group data
            enhanced_group.update({
                'competitor_count': competitor_count,
                'video_count': total_videos,
                'competitor_channels': competitors,  # Full competitor data
                'analyzed_videos': []  # You can enhance this if needed
            })
            
            enhanced_groups.append(enhanced_group)
            print(f"✅ Group '{group.get('name')}': {competitor_count} competitors, {total_videos} videos")
        
        # Check if user wants modern UI (default to true for my_groups)
        use_modern = request.args.get('modern', 'true').lower() == 'true'
        
        if use_modern:
            return render_template('modern_my_groups.html', user_groups=enhanced_groups)
        else:
            return render_template('my_groups.html', user_groups=enhanced_groups)
    except Exception as e:
        print(f"❌ Error loading user groups: {e}")
        flash('Error loading your groups.', 'error')
        return redirect(url_for('dashboard.main'))

@dashboard_bp.route('/available_groups')
@login_required
def available_groups():
    """Available groups page - REAL Discord bot integration"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        available_groups = db.get_available_groups_sync(discord_id)
        return render_template('available_groups.html', available_groups=available_groups)
    except Exception as e:
        print(f"❌ Error loading available groups: {e}")
        flash('Error loading available groups.', 'error')
        return redirect(url_for('dashboard.main'))

@dashboard_bp.route('/view_group/<group_id>')
@login_required
def view_group(group_id):
    """View group details - REAL Discord bot integration"""
    try:
        group = db.get_group_sync(group_id)
        if not group:
            flash('Group not found.', 'error')
            return redirect(url_for('dashboard.main'))
        
        competitors = db.get_competitors_sync(group_id)
        group_stats = db.get_group_stats_sync(group_id)
        
        return render_template('view_group.html', 
                             group=group, 
                             competitors=competitors,
                             group_stats=group_stats)
    except Exception as e:
        print(f"❌ Error loading group: {e}")
        flash('Error loading group details.', 'error')
        return redirect(url_for('dashboard.main'))

@dashboard_bp.route('/api_keys')
@login_required
def api_keys():
    """API keys management page"""
    # Get user's API keys using Discord ID for consistency
    discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
    user_api_keys = db.get_user_api_keys(discord_id)
    return render_template('modern/api_keys.html', api_keys=user_api_keys)

@dashboard_bp.route('/api/save-api-key', methods=['POST'])
@login_required
def save_api_key():
    """Save or update a user's API key"""
    try:
        data = request.get_json()
        service = data.get('service')
        name = data.get('name')
        api_key = data.get('key')
        description = data.get('description', '')
        
        if not all([service, name, api_key]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Use Discord ID for consistency with database
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        success = db.save_user_api_key(
            user_id=discord_id,
            service=service,
            name=name,
            api_key=api_key,
            description=description
        )
        
        if success:
            return jsonify({'success': True, 'message': 'API key saved successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save API key'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/delete-api-key', methods=['POST'])
@login_required
def delete_api_key():
    """Delete a user's API key"""
    try:
        data = request.get_json()
        service = data.get('service')
        
        if not service:
            return jsonify({'success': False, 'error': 'Service name required'}), 400
        
        # Use Discord ID for consistency with database
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        success = db.delete_user_api_key(
            user_id=discord_id,
            service=service
        )
        
        if success:
            return jsonify({'success': True, 'message': 'API key deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete API key'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/test-api-key', methods=['POST'])
@login_required
def test_api_key():
    """Test a user's API key"""
    try:
        data = request.get_json()
        service = data.get('service')
        
        if not service:
            return jsonify({'success': False, 'error': 'Service name required'}), 400
        
        api_key = db.get_user_api_key(str(current_user.id), service)
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key not found'}), 404
        
        # Test the API key based on service
        if service == 'Anthropic Claude':
            # Test Claude API
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key)
            # Simple test - this will raise an exception if invalid
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Test"}]
                ))
                loop.close()
                return jsonify({'success': True, 'message': 'API key is valid and working'})
            except Exception as e:
                loop.close()
                return jsonify({'success': False, 'error': f'API key test failed: {str(e)}'}), 400
                
        elif service in ['YouTube Data API', 'YouTube Analytics API']:
            # Test YouTube API
            import requests
            test_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q=test&key={api_key}&maxResults=1"
            response = requests.get(test_url)
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'API key is valid and working'})
            else:
                return jsonify({'success': False, 'error': f'API key test failed: {response.status_code}'}), 400
        else:
            return jsonify({'success': True, 'message': 'API key saved (testing not implemented for this service)'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Tool routes
@dashboard_bp.route('/tools/trend_discovery')
@login_required
def trend_discovery():
    """Unified Trend Discovery - shows ALL series/themes from ALL user groups with filtering"""
    try:
        # Get all user groups
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Get filter from query params
        filter_group_id = request.args.get('group_id')
        
        # Collect all series+theme combinations from all groups (or filtered group) 
        all_theme_combinations = []
        all_competitors = []
        groups_data = []
        
        # OPTIMIZED: Process groups much faster
        print(f"🚀 FAST MODE: Loading trend data for {len(user_groups)} groups...")
        
        for group in user_groups:
            group_id = str(group.get('_id'))
            
            # If filtering by specific group, skip others
            if filter_group_id and filter_group_id != group_id:
                continue
                
            # Get group data - USE THE EXACT DISCORD BOT METHOD
            try:
                # Use the EXACT same method as Discord bot
                group_series = db.get_top_series_sync(group_id, limit=50)
                group_competitors = db.get_competitors_sync(group_id)
                
                # Calculate channel average for outlier detection
                channel_total_views = sum(s.get('total_views', 0) for s in group_series)
                channel_total_videos = sum(s.get('video_count', 0) for s in group_series)
                channel_avg_views = channel_total_views / channel_total_videos if channel_total_videos > 0 else 0
                
                # Process each series and flatten themes into individual combinations
                for series in group_series:
                    series_name = series.get('name')
                    if not series_name:
                        continue

                    # Get themes from series data
                    themes = series.get('themes', [])
                    
                    # Create individual entries for each theme
                    for theme in themes:
                        theme_name = theme.get('name', '')
                        theme_avg_views = theme.get('avg_views', 0)
                        theme_video_count = theme.get('video_count', 0)
                        theme_total_views = theme.get('total_views', 0)
                        
                        # Calculate outlier score (how much this theme outperforms channel average)
                        outlier_score = 0
                        if channel_avg_views > 0:
                            outlier_score = theme_avg_views / channel_avg_views
                        
                        # Determine outlier level
                        outlier_level = "standard"
                        if outlier_score >= 3.0:
                            outlier_level = "extreme"  # 3x+ above average
                        elif outlier_score >= 2.0:
                            outlier_level = "high"     # 2x+ above average
                        elif outlier_score >= 1.5:
                            outlier_level = "moderate" # 1.5x+ above average
                        
                        # Create theme combination data
                        theme_combo = {
                            'series_name': series_name,
                            'theme_name': theme_name,
                            'group_name': group.get('name', 'Unnamed Project'),
                            'group_id': group_id,
                            'channel_title': series.get('channel_title', ''),
                            'theme_avg_views': theme_avg_views,
                            'theme_total_views': theme_total_views,
                            'theme_video_count': theme_video_count,
                            'channel_avg_views': channel_avg_views,
                            'outlier_score': outlier_score,
                            'outlier_level': outlier_level,
                            'frequency': series.get('frequency', 'Weekly'),
                            'subscriberCount': series.get('subscriberCount', 0),
                            # For backwards compatibility with existing template
                            'name': f"{series_name} → {theme_name}",
                            'total_views': theme_total_views,
                            'avg_views': theme_avg_views,
                            'video_count': theme_video_count
                        }
                        all_theme_combinations.append(theme_combo)
                
                # Add group context to competitors
                for competitor in group_competitors:
                    competitor['group_name'] = group.get('name', 'Unnamed Project')
                    competitor['group_id'] = group_id
                    all_competitors.append(competitor)
                
                # Store group data for filter dropdown
                groups_data.append({
                    '_id': group_id,
                    'name': group.get('name', 'Unnamed Project'),
                    'series_count': len(group_series),
                    'competitors_count': len(group_competitors)
                })
                
            except Exception as e:
                print(f"❌ Error loading data for group {group_id}: {e}")
                continue
        
        # Sort by outlier score (highest outliers first)
        all_theme_combinations.sort(key=lambda x: x.get('outlier_score', 0), reverse=True)
        
        return render_template('modern_trend_discovery.html', 
                             all_series=all_theme_combinations,
                             all_competitors=all_competitors,
                             groups_data=groups_data,
                             current_filter=filter_group_id,
                             total_series=len(all_theme_combinations),
                             total_competitors=len(all_competitors))
                             
    except Exception as e:
        print(f"❌ Error loading trend discovery: {e}")
        flash('Error loading trend discovery tool.', 'error')
        return redirect(url_for('dashboard.main'))

@dashboard_bp.route('/tools/market_research')
@login_required
def market_research():
    """Market Research Tool"""
    return render_template('tools/market_research.html')

@dashboard_bp.route('/tools/mass_production')
@login_required
def mass_production():
    """Mass Production Tool"""
    return render_template('tools/mass_production.html')

@dashboard_bp.route('/tools/content_creation_legacy')
@login_required
def content_creation_legacy():
    """Individual Content Creation Tool (Legacy)"""
    return render_template('tools/content_creation.html')

@dashboard_bp.route('/tools/thumbnail_designer')
@login_required
def thumbnail_designer():
    """Thumbnail Studio - AI-powered thumbnail generation"""
    try:
        # Get user's projects for the dropdown
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Format projects for the template
        projects = []
        for group in user_groups:
            projects.append({
                'id': str(group.get('_id')),
                'name': group.get('name', 'Unnamed Project')
            })
        
        return render_template('modern/thumbnail_studio_new.html', projects=projects)
    except Exception as e:
        print(f"❌ Error loading thumbnail studio: {e}")
        flash('Error loading Thumbnail Studio.', 'error')
        return redirect(url_for('dashboard.main'))

@dashboard_bp.route('/tools/live_stream')
@login_required
def live_stream():
    """Live Stream Setup Tool"""
    return render_template('tools/live_stream.html')

@dashboard_bp.route('/intelligence')
@login_required
def intelligence():
    """Market Intelligence Dashboard"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        return render_template('modern/intelligence.html', user_groups=user_groups)
    except Exception as e:
        print(f"❌ Error loading intelligence: {e}")
        flash('Error loading intelligence dashboard.', 'error')
        return redirect(url_for('dashboard.main'))

# Campaign Management Routes
@dashboard_bp.route('/campaigns')
@login_required  
def campaigns():
    """Campaign Manager - like Facebook Ads Manager"""
    return render_template('modern/campaigns.html')

@dashboard_bp.route('/campaigns/create')
@login_required
def create_campaign():
    """Campaign Wizard - create new automation campaign"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        return render_template('modern/campaign_wizard.html', projects=user_groups)
    except Exception as e:
        print(f"❌ Error loading campaign wizard: {e}")
        flash('Error loading campaign wizard.', 'error')
        return redirect(url_for('dashboard.main'))

# New Modern UI Routes
@dashboard_bp.route('/channels')
@login_required
def channels():
    """My Channels Dashboard - manage connected YouTube channels"""
    try:
        # Get user's connected YouTube channels - use discord_id like production_view does
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_channels = db.get_user_youtube_channels_sync(discord_id)
        
        # Process channels to add lifecycle status and stats
        processed_channels = []
        for channel in user_channels:
            # Calculate basic stats (you can enhance this with real analytics)
            channel_data = {
                'id': channel.get('channel_id', ''),
                'name': channel.get('title', 'Unknown Channel'),
                'channel_id': channel.get('channel_id', ''),
                'title': channel.get('title', 'Unknown Channel'),
                'subscribers': '0',  # To be populated from YouTube API
                'lifecycle': 'testing',  # Default lifecycle
                'connected_at': channel.get('connected_at'),
                'oauth_data': channel.get('oauth_data', {}),
                # Mock stats for now - replace with real analytics
                'avgViews': 0,
                'growthRate': 0,
                'estimatedRevenue': 0,
                'activeAutomations': 0,
                'testingProgress': {'current': 0, 'total': 30, 'daysLeft': 30}
            }
            processed_channels.append(channel_data)
        
        return render_template('modern/channels.html', 
                             user_channels=processed_channels,
                             total_channels=len(processed_channels))
    except Exception as e:
        print(f"❌ Error loading channels: {e}")
        # Return empty state on error
        return render_template('modern/channels.html', 
                             user_channels=[],
                             total_channels=0)

@dashboard_bp.route('/analytics') 
@login_required
def analytics():
    """Channel Analytics Dashboard - KPIs and performance metrics"""
    return render_template('modern/analytics.html')

@dashboard_bp.route('/discover')
@login_required
def discover():
    """Channel Discovery - find profitable YouTube channels"""
    return render_template('modern/discover.html')

# Channel Discovery API Routes
@dashboard_bp.route('/api/discover/search', methods=['POST'])
@login_required
@api_key_required
def discover_search():
    """API endpoint for channel discovery search"""
    try:
        data = request.get_json()
        search_method = data.get('search_method')
        search_query = data.get('search_query', '')
        selected_preset = data.get('selected_preset', '')
        channel_url = data.get('channel_url', '')
        
        if not search_method:
            return jsonify({'success': False, 'error': 'Search method is required'}), 400
        
        # Initialize discovery service - add path to make imports work
        import sys
        import os
        channel_discovery_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'channel_discovery_app')
        if channel_discovery_path not in sys.path:
            sys.path.insert(0, channel_discovery_path)
        
        # Import after path is added
        from channel_discovery_service import ChannelDiscoveryService
        from youtube_service import YouTubeService
        from ai_utils import AnalysisService
        from database import Database as DiscoveryDB
        
        # Create discovery service instance with SAME database as web app
        discovery_db = DiscoveryDB()
        # Override the database name to match web app
        discovery_db.db = None  # Reset
        
        youtube_service = YouTubeService()
        analysis_service = AnalysisService()
        discovery_service = ChannelDiscoveryService(youtube_service, discovery_db, analysis_service)
        
        # Store user info for background thread
        user_web_id = str(current_user.id)
        
        # First, check for existing channels instantly (like the discovery app does)
        try:
            # Create separate database instance for instant check
            instant_discovery_db = DiscoveryDB()
            
            # Use a completely separate event loop for instant results
            def check_existing_channels():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Connect to SAME database as web app (niche_research, not channel_discovery)
                    from config import MONGODB_URI
                    import motor.motor_asyncio
                    
                    instant_discovery_db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
                    instant_discovery_db.db = instant_discovery_db.client['niche_research']  # Same as web app
                    
                    existing_channels = loop.run_until_complete(instant_discovery_db.get_high_potential_channels())
                    instant_discovery_db.client.close()
                    return existing_channels
                finally:
                    loop.close()
            
            existing_channels = check_existing_channels()
            
            # Filter existing channels by search criteria  
            filtered_channels = []
            for channel in existing_channels:
                if search_method == 'keyword':
                    title = channel.get('title', '').lower()
                    niche = channel.get('niche', '').lower()
                    search_keyword = channel.get('search_keyword', '').lower()
                    query_lower = search_query.lower()
                    
                    # EXACT match only - search keyword must match exactly
                    if query_lower == search_keyword:
                        filtered_channels.append(channel)
                        
                elif search_method == 'preset':
                    niche = channel.get('niche', '').lower()
                    if selected_preset in niche:
                        filtered_channels.append(channel)
            
            # If we have instant results, return them immediately
            if filtered_channels:
                print(f"✅ Found {len(filtered_channels)} existing channels instantly!")
                
                formatted_channels = []
                for channel in filtered_channels[:10]:
                    # Calculate proper RPM and revenue using your market research logic
                    def get_base_rpm(avg_video_duration_minutes):
                        base_rpm_data = {
                            "10-20": 3.5,
                            "20-45": 5.0,
                            "45-90": 6.5,
                            "90-180": 14.5,
                            "180+": 23.5
                        }
                        for category, rpm in base_rpm_data.items():
                            if "-" in category:
                                low, high = map(float, category.split("-"))
                                if low <= avg_video_duration_minutes < high:
                                    return rpm
                            elif avg_video_duration_minutes >= 180:
                                return rpm
                        return 3.5  # Default to lowest RPM
                    
                    def get_niche_multiplier(niche):
                        # Use your EXACT niche multipliers from public market research
                        niche_multipliers = {
                            "Finance": 1.29, "Technology": 1.04, "Education": 0.92,
                            "Entertainment": 0.77, "Lifestyle": 0.82, "Marketing": 1.18,
                            "Crypto": 1.49, "Real Estate": 1.82, "Investing": 1.08,
                            "Side Hustle": 1.19, "Entrepreneurship": 1.63, "Personal Finance": 1.29,
                            "Business": 0.95, "Vlogging": 1.03, "Dropshipping": 5.18,
                            "Affiliate Marketing": 0.87, "Print on Demand": 0.78,
                            "Filmmaking": 0.9, "Travel": 0.85, "Hustling": 1.15,
                            "Digital Products": 1.2, "Motherhood": 0.95, "Archery": 0.8,
                            "Hunting": 0.85, "Productivity": 1.05,
                            "Personal Development": 1.1, "Science": 0.95,
                            "Space": 1.0, "Geology": 0.9, "Paleontology": 0.85,
                            "Astronomy": 1.05, "History": 0.9, "Politics": 1.1,
                            "News": 1.2, "Gaming": 0.8, "Sports": 0.9,  # Gaming = 0.8x multiplier!
                            "Fitness": 1.0, "Cooking": 0.85, "Fashion": 0.95,
                            "Beauty": 1.0, "DIY": 0.9, "Home Improvement": 1.05,
                            "Gardening": 0.85, "Pets": 0.9, "Music": 0.8,
                            "Art": 0.85, "Photography": 0.95, "Writing": 0.9,
                            "Language Learning": 1.0, "Food": 0.9,
                            "Wine": 1.1, "Beer": 0.95, "Spirits": 1.05,
                            "Automotive": 1.1, "Motorcycles": 1.0, "Boats": 1.15,
                            "Aviation": 1.2, "Outdoors": 0.9, "Survival": 1.05,
                        }
                        for key, multiplier in niche_multipliers.items():
                            if key.lower() in niche.lower():
                                return multiplier
                        return 0.8  # Default to gaming/entertainment level for unknown niches
                    
                    # Get actual data from channel
                    avg_video_duration = channel.get('avg_video_duration', 0)
                    avg_video_duration_minutes = avg_video_duration / 60 if avg_video_duration > 0 else 10
                    niche = channel.get('niche', 'Unknown')
                    total_views = channel.get('total_views', 0)
                    channel_age_days = channel.get('channel_age_days', 1)
                    
                    # Calculate proper RPM using your market research logic
                    base_rpm = get_base_rpm(avg_video_duration_minutes)
                    niche_multiplier = get_niche_multiplier(niche)
                    final_rpm = base_rpm * niche_multiplier
                    
                    # Calculate monthly revenue based on current performance
                    if total_views > 0 and channel_age_days > 0:
                        daily_views = total_views / channel_age_days
                        monthly_views = daily_views * 30
                        monthly_revenue = (monthly_views / 1000) * final_rpm
                    else:
                        monthly_revenue = 0
                    
                    # Only show subscriber count if we have real data, otherwise hide it
                    subscriber_count = channel.get('subscriber_count', 0)
                    
                    formatted_channels.append({
                        'id': channel.get('channel_id', ''),
                        'name': channel.get('channel_name', 'Unknown Channel'),  # Use channel_name from your DB
                        'subscribers': format_subscriber_count(subscriber_count) if subscriber_count > 0 else 'Data Pending',
                        'monthly_revenue': f"${monthly_revenue:,.0f}",
                        'growth_rate': f"+{channel.get('estimated_rpm', 0):.0f} RPM",  # Show RPM instead of growth rate
                        'content_type': 'Script-based' if channel.get('needs_full_script') else 'Unknown',
                        'age_days': channel.get('channel_age_days', 0),
                        'automation_score': 95,  # High score since it passed all your filters
                        'channel_url': channel.get('channel_url', f"https://youtube.com/channel/{channel.get('channel_id', '')}"),
                        'thumbnail_url': channel.get('thumbnail_url', '')  # Add profile picture
                    })
                
                # Start background discovery for MORE channels while showing instant results
                progress_id = f"discovery_{user_web_id}_{int(time.time())}"
                
                def run_background_discovery_for_more():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        set_user_context(user_web_id, db)
                        
                        # Create a fresh discovery service with correct database connection
                        from config import MONGODB_URI
                        import motor.motor_asyncio
                        
                        fresh_discovery_db = DiscoveryDB()
                        fresh_discovery_db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
                        fresh_discovery_db.db = fresh_discovery_db.client['niche_research']  # Same as web app
                        
                        fresh_youtube_service = YouTubeService()
                        fresh_analysis_service = AnalysisService()
                        fresh_discovery_service = ChannelDiscoveryService(fresh_youtube_service, fresh_discovery_db, fresh_analysis_service)
                        
                        if search_method == 'keyword':
                            fresh_discovery_service.search_keywords = [search_query]
                            fresh_discovery_service.active_niches = []
                            fresh_discovery_service.custom_keywords = [search_query]
                        elif search_method == 'preset':
                            preset_mapping = {
                                'finance': '💰 Business & Finance > Personal Finance',
                                'crypto': '💰 Business & Finance > Cryptocurrency',
                                'ai-tools': '💻 Technology & Software > AI & Machine Learning',
                                'true-crime': '📺 Entertainment > True Crime',
                                'self-improvement': '🧠 Education & Learning > Personal Development'
                            }
                            niche_path = preset_mapping.get(selected_preset, '💰 Business & Finance > Personal Finance')
                            fresh_discovery_service.active_niches = [niche_path]
                            fresh_discovery_service.search_keywords = []
                        
                        # Run discovery for NEW channels with fresh service
                        loop.run_until_complete(fresh_discovery_service.discover_channels())
                        
                        # Update progress when new channels are found
                        db.progress_tracking[progress_id] = {
                            'status': 'completed',
                            'message': 'Background discovery completed - check for new channels!'
                        }
                        
                    except Exception as e:
                        print(f"❌ Background discovery error: {e}")
                        db.progress_tracking[progress_id] = {
                            'status': 'error',
                            'message': f'Background discovery failed: {str(e)}'
                        }
                    finally:
                        if fresh_discovery_db.client:
                            fresh_discovery_db.client.close()
                        loop.close()
                
                # Start background thread for MORE discoveries
                import threading
                thread = threading.Thread(target=run_background_discovery_for_more)
                thread.start()
                
                # Initialize progress tracking for background search
                db.progress_tracking = getattr(db, 'progress_tracking', {})
                db.progress_tracking[progress_id] = {
                    'status': 'searching_more',
                    'message': 'Finding additional channels in background...'
                }
                
                return jsonify({
                    'success': True,
                    'message': f'Found {len(formatted_channels)} channels instantly. Searching for more in background...',
                    'instant_results': True,
                    'results': formatted_channels,
                    'progress_id': progress_id,  # For checking background progress
                    'searching_more': True
                })
        
        except Exception as e:
            print(f"⚠️ Could not get instant results: {e}")
        
        print(f"🔍 No cached results found, starting new discovery...")
        
        # Start background discovery task
        def run_discovery_search():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Set user context for API middleware BEFORE using discovery service
                set_user_context(user_web_id, db)
                
                # Initialize discovery service with SAME database as web app
                from config import MONGODB_URI
                import motor.motor_asyncio
                
                discovery_db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
                discovery_db.db = discovery_db.client['niche_research']  # Same database as web app
                
                if search_method == 'keyword':
                    # Set search keywords and run discovery
                    discovery_service.search_keywords = [search_query]
                    discovery_service.active_niches = []
                    discovery_service.custom_keywords = [search_query]
                    
                    # Run the main discovery process
                    loop.run_until_complete(discovery_service.discover_channels())
                    
                    # Get discovered channels
                    channels = loop.run_until_complete(discovery_service.get_discovered_channels())
                    result = {'channels': channels[:10] if channels else []}  # Handle empty results
                    
                elif search_method == 'preset':
                    # Map preset values to niche paths
                    preset_mapping = {
                        'finance': '💰 Business & Finance > Personal Finance',
                        'crypto': '💰 Business & Finance > Cryptocurrency',
                        'ai-tools': '💻 Technology & Software > AI & Machine Learning',
                        'true-crime': '📺 Entertainment > True Crime',
                        'self-improvement': '🧠 Education & Learning > Personal Development'
                    }
                    
                    niche_path = preset_mapping.get(selected_preset, '💰 Business & Finance > Personal Finance')
                    discovery_service.active_niches = [niche_path]
                    discovery_service.search_keywords = []
                    
                    # Run the main discovery process
                    loop.run_until_complete(discovery_service.discover_channels())
                    
                    # Get discovered channels
                    channels = loop.run_until_complete(discovery_service.get_discovered_channels())
                    result = {'channels': channels[:10] if channels else []}  # Handle empty results
                    
                elif search_method == 'channel':
                    # For channel analysis, we'll use a different approach
                    # Extract channel ID from URL and analyze it
                    result = {'channels': [], 'message': 'Channel analysis not yet implemented'}
                    
                else:
                    result = {'error': 'Invalid search method'}
                
                # Store result in progress tracking for retrieval
                current_progress_id = f"discovery_{user_web_id}_{int(time.time())}"
                
                # Determine message based on results
                if result.get('channels'):
                    message = f"Found {len(result['channels'])} profitable channels"
                else:
                    message = "No channels found matching all criteria (180 days old, $5K+ revenue, script-based content)"
                
                db.progress_tracking[current_progress_id] = {
                    'status': 'completed',
                    'result': result,
                    'search_method': search_method,
                    'message': message
                }
                
                return result
            except Exception as e:
                print(f"❌ Discovery search error: {e}")
                current_progress_id = f"discovery_{user_web_id}_{int(time.time())}"
                db.progress_tracking[current_progress_id] = {
                    'status': 'error',
                    'result': {'error': str(e)},
                    'search_method': search_method
                }
                return {'error': str(e)}
            finally:
                # Close database connection
                if discovery_db.client:
                    loop.run_until_complete(discovery_db.close())
                loop.close()
        
        # Start search in background thread
        import threading
        progress_id = f"discovery_{user_web_id}_{int(time.time())}"
        
        # Initialize progress tracking
        db.progress_tracking = getattr(db, 'progress_tracking', {})
        db.progress_tracking[progress_id] = {
            'status': 'running',
            'progress': 0,
            'step': 'Starting channel discovery...'
        }
        
        thread = threading.Thread(target=run_discovery_search)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Channel discovery started',
            'progress_id': progress_id,
            'searching': True
        })
        
    except Exception as e:
        print(f"❌ Error in discover_search: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/discover/progress/<progress_id>')
@login_required
def discover_progress(progress_id):
    """Check progress of channel discovery"""
    try:
        progress_data = getattr(db, 'progress_tracking', {}).get(progress_id)
        
        if not progress_data:
            return jsonify({'success': False, 'error': 'Progress not found'}), 404
        
        response = {
            'success': True,
            'status': progress_data.get('status', 'running'),
            'progress': progress_data.get('progress', 0),
            'step': progress_data.get('step', ''),
        }
        
        # If completed, include the results
        if progress_data.get('status') == 'completed' and 'result' in progress_data:
            result = progress_data['result']
            
            # Format results for frontend
            if isinstance(result, dict) and 'channels' in result:
                formatted_channels = []
                for channel in result['channels'][:10]:  # Limit to 10 results
                    formatted_channels.append({
                        'id': channel.get('channel_id', ''),
                        'name': channel.get('title', 'Unknown Channel'),
                        'subscribers': format_subscriber_count(channel.get('subscriber_count', 0)),
                        'monthly_revenue': f"${channel.get('estimated_monthly_revenue', 0):,.0f}",
                        'growth_rate': f"+{channel.get('growth_rate', 0):.0f}%",
                        'content_type': channel.get('content_format', 'Unknown'),
                        'age_days': channel.get('channel_age_days', 0),
                        'automation_score': int(channel.get('automation_score', 0) * 100),
                        'channel_url': f"https://youtube.com/channel/{channel.get('channel_id', '')}"
                    })
                response['results'] = formatted_channels
            
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error checking discover progress: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/discover/create-project', methods=['POST'])
@login_required
@api_key_required
def discover_create_project():
    """Create a new project from discovered channel - uses same logic as create_group_post"""
    try:
        data = request.get_json()
        channel_data = data.get('channel_data')
        
        if not channel_data:
            return jsonify({'success': False, 'error': 'Channel data is required'}), 400
        
        # Extract channel URL and create project name
        channel_url = channel_data.get('channel_url', '')
        project_name = f"Discovered: {channel_data.get('name', 'Unknown Channel')}"
        
        if not channel_url:
            return jsonify({'success': False, 'error': 'Channel URL is required'}), 400
        
        print(f"🎯 Creating project from discovered channel: {project_name} with URL: {channel_url}")
        
        # Use web user ID instead of Discord ID
        web_user_id = str(current_user.id)
        print(f"✅ Using web user ID: {web_user_id} for user: {current_user.username}")
        
        # Create progress tracking (same as create_group_post)
        progress_id = f"group_creation_{web_user_id}_{int(time.time())}"
        
        # Initialize progress
        progress_data = {
            "progress": 0,
            "step": "Starting analysis of discovered channel...",
            "status": "running"
        }
        
        # Store progress in database for tracking
        db.progress_tracking = getattr(db, 'progress_tracking', {})
        db.progress_tracking[progress_id] = progress_data
        
        def run_background_group_creation():
            """Run EXACT same group creation logic as create_group_post"""
            try:
                print(f"🚀 Starting background group creation for discovered channel: {project_name}")
                
                # Create asyncio event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Import from the web app's services directory (same as create_group_post)
                    import sys
                    import os
                    sys.path.insert(0, os.path.dirname(__file__))
                    
                    from dashboard.web_analysis_service import WebAnalysisService
                    
                    # Set user context for API middleware (same as create_group_post)
                    set_user_context(web_user_id, db)
                    
                    analysis_service = WebAnalysisService(db)
                
                    # Update progress: Step 1 (same as create_group_post)
                    db.progress_tracking[progress_id]["progress"] = 25
                    db.progress_tracking[progress_id]["step"] = "Analyzing discovered channel content DNA..."
                    
                    # Use EXACT same perform_niche_analysis call as create_group_post
                    result = loop.run_until_complete(
                        analysis_service.perform_niche_analysis(
                            channel_url=channel_url,
                            group_name=project_name,
                            user_id=web_user_id,
                            is_public=False
                        )
                    )
                    
                    # Update progress: Step 2 (same as create_group_post)
                    db.progress_tracking[progress_id]["progress"] = 75
                    db.progress_tracking[progress_id]["step"] = "Finding similar competitor channels..."
                    
                    # Update group with proper owner (same as create_group_post)
                    if "error" not in result and result.get("group_id"):
                        group_id = result["group_id"]
                        db.update_competitor_group(group_id, {
                            "owner_id": web_user_id,
                            "user_id": web_user_id,
                            "source": "channel_discovery"  # Mark as discovered channel
                        })
                        
                        # Update progress: Complete (same as create_group_post)
                        db.progress_tracking[progress_id]["progress"] = 100
                        db.progress_tracking[progress_id]["step"] = "Building competitive intelligence project..."
                        db.progress_tracking[progress_id]["status"] = "complete"
                        db.progress_tracking[progress_id]["group_id"] = group_id
                    
                    return result
                    
                finally:
                    loop.close()
                        
            except Exception as e:
                print(f"❌ Background group creation error: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Update progress with error (same as create_group_post)
                if 'progress_id' in locals():
                    db.progress_tracking[progress_id]["status"] = "error"
                    db.progress_tracking[progress_id]["step"] = f"Error: {str(e)}"
                
                return {"error": str(e)}
        
        # Run in background thread (same as create_group_post)
        thread = threading.Thread(target=run_background_group_creation)
        thread.start()
        
        # Return immediately with progress tracking ID (same as create_group_post)
        return jsonify({
            'success': True, 
            'message': f'Project creation started for discovered channel "{channel_data.get("name")}". This may take 2-3 minutes for analysis to complete.',
            'progress_id': progress_id,  # For real progress tracking
            'redirect_to_competitors': True
        })
        
    except Exception as e:
        print(f"❌ Error in discover_create_project: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def format_subscriber_count(count):
    """Format subscriber count to human readable format"""
    try:
        num = int(count)
        if num >= 1000000:
            return f"{num / 1000000:.1f}M"
        elif num >= 1000:
            return f"{num / 1000:.0f}K"
        else:
            return str(num)
    except:
        return "0"

@dashboard_bp.route('/optimization/retention')
@login_required
def retention_optimization():
    """Audience Retention Optimization Tool"""
    return render_template('modern/retention_optimization.html')

@dashboard_bp.route('/tutorials')
@login_required
def tutorials():
    """Tutorials & Resources Page"""
    return render_template('modern/tutorials.html')

@dashboard_bp.route('/affiliates')
@login_required
def affiliates():
    """Affiliate Program Dashboard"""
    return render_template('modern/affiliates.html')

@dashboard_bp.route('/settings')
@login_required
def settings():
    """User Settings and Preferences"""
    return render_template('modern/settings.html')

@dashboard_bp.route('/live-streaming')
@login_required
def live_streaming():
    """Live Streaming Management"""
    return render_template('modern/live_streaming.html')

@dashboard_bp.route('/instagram_studio')
@login_required
def instagram_studio():
    """Instagram Studio - Mass redistribution platform (Admin Only)"""
    # Check if user is admin
    if not getattr(current_user, 'is_admin', False):
        flash('Instagram Studio is only available to administrators.', 'error')
        return redirect(url_for('dashboard.main'))
    return render_template('modern/instagram_studio.html')

@dashboard_bp.route('/video-editor')
@login_required
def video_editor():
    """Video Editor - VFX Templates and Autonomous Video Generation"""
    return render_template('modern/video_editor.html')

@dashboard_bp.route('/marketplace')
@login_required
def marketplace():
    """Project Marketplace - browse and purchase proven projects"""
    return render_template('modern/project_marketplace.html')

# Alternative route for marketplace (in case of routing issues)
@dashboard_bp.route('/project-marketplace')
@login_required
def project_marketplace():
    """Project Marketplace - browse and purchase proven projects (alternative route)"""
    return render_template('modern/project_marketplace.html')

@dashboard_bp.route('/content-creation')
@login_required
def content_creation():
    """Manual Content Creation - create videos manually with AI assistance"""
    return render_template('modern/content_creation.html')

@dashboard_bp.route('/content-creation/api/get-groups')
@login_required
def get_user_groups():
    """API endpoint to get user's groups for content creation"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        groups = db.get_user_groups_sync(discord_id)
        return jsonify({'success': True, 'groups': groups})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/content-creation/api/get-series/<group_id>')
@login_required
def get_group_series(group_id):
    """API endpoint to get series for a specific group"""
    try:
        series = db.get_all_series_sync(group_id)
        return jsonify({'success': True, 'series': series})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/content-creation/api/get-themes/<group_id>/<series_name>')
@login_required
def get_series_themes(group_id, series_name):
    """API endpoint to get themes for a specific series"""
    try:
        themes = db.get_series_themes_sync(group_id, series_name)
        return jsonify({'success': True, 'themes': themes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Add the API routes that manual_production.html is actually trying to call
@dashboard_bp.route('/trends/api/get-series/<group_id>')
@login_required
def get_trends_series(group_id):
    """API endpoint to get series for manual production - EXACT same method as manual_production route"""
    try:
        print(f"🎯 Getting series for group {group_id}")
        # print(f"👤 Current user: {current_user.username}")  # Commented - too noisy
        
        # Check if the group exists and user has access
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_groups = db.get_user_groups_sync(discord_id)
        user_group_ids = [str(g.get('_id')) for g in user_groups]
        print(f"🔍 User has access to groups: {user_group_ids}")
        
        if group_id not in user_group_ids:
            print(f"❌ Access denied: Group {group_id} not in user's groups")
            return jsonify({'success': False, 'error': 'Access denied or group not found'}), 403
        
        # Use the SAME method that works in the main route
        series = db.get_top_series_sync(group_id, timeframe='90d', limit=50)
        print(f"✅ Found {len(series)} series")
        
        # Debug the structure of the first series
        if series:
            first_series = series[0]
            print(f"🔍 First series structure: {list(first_series.keys())}")
            print(f"🏷️ First series themes count: {len(first_series.get('themes', []))}")
        
        return jsonify({'success': True, 'series': series})
    except Exception as e:
        print(f"❌ Error getting series: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/trends/api/get-themes/<group_id>')
@login_required
def get_trends_themes(group_id):
    """API endpoint to get themes for manual production"""
    try:
        series_name = request.args.get('series_name')
        print(f"🎯 Getting themes for group {group_id}, series {series_name}")
        themes = db.get_series_themes_sync(group_id, series_name)
        print(f"✅ Found {len(themes)} themes")
        return jsonify({'success': True, 'themes': themes})
    except Exception as e:
        print(f"❌ Error getting themes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# YouTube Channel Management API Routes
@dashboard_bp.route('/api/channels')
@login_required  
def get_channels():
    """API endpoint to get user's YouTube channels"""
    try:
        # Use discord_id like production_view does - channels are stored by Discord ID
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        user_channels = db.get_user_youtube_channels_sync(discord_id)
        return jsonify({
            'success': True,
            'channels': user_channels,
            'total': len(user_channels)
        })
    except Exception as e:
        print(f"❌ Error getting channels: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/channels/connect', methods=['POST'])
@login_required
def connect_channel():
    """API endpoint to initiate YouTube channel connection"""
    try:
        data = request.get_json()
        channel_url = data.get('channel_url', '').strip()
        
        if not channel_url:
            return jsonify({'success': False, 'error': 'Channel URL is required'}), 400
        
        # Import YouTube service to get channel ID
        try:
            from core.youtube_service import YouTubeService
            
            # Initialize YouTube service
            youtube_service = YouTubeService()
            
            # Extract channel ID from URL using sync method
            channel_id = youtube_service.get_channel_id_from_url_sync(channel_url)
            
            if not channel_id:
                return jsonify({
                    'success': False, 
                    'error': 'Invalid YouTube channel URL. Please provide a valid channel URL.'
                }), 400
            
            # Get channel info from YouTube API using sync method
            channel_data = youtube_service.fetch_channel_data_sync(channel_id)
            if not channel_data:
                return jsonify({
                    'success': False,
                    'error': 'Could not fetch channel information. Please check the URL and try again.'
                }), 400
            
            # Extract channel info from the data
            channel_info = {
                'title': channel_data.get('title', 'Unknown Channel'),
                'subscriber_count': channel_data.get('subscriber_count', 0)
            }
            
            # Generate OAuth URL for authorization
            client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
            import urllib.parse
            
            scopes = urllib.parse.quote_plus(" ".join([
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/yt-analytics.readonly", 
                "https://www.googleapis.com/auth/youtube.upload"
            ]))
            
            oauth_url = f"https://accounts.google.com/o/oauth2/auth?client_id={urllib.parse.quote_plus(client_id)}&redirect_uri=urn:ietf:wg:oauth:2.0:oob&scope={scopes}&response_type=code&access_type=offline"
            
            return jsonify({
                'success': True,
                'channel_info': {
                    'id': channel_id,
                    'title': channel_info.get('title', 'Unknown Channel'),
                    'subscriber_count': channel_info.get('subscriber_count', 0)
                },
                'oauth_url': oauth_url,
                'instructions': [
                    'Click the authorization link to open Google\'s authorization page',
                    'Allow access to your YouTube channel',
                    'Copy the authorization code you receive',
                    'Return here and enter the code to complete the connection'
                ]
            })
            
        except ImportError as ie:
            return jsonify({
                'success': False,
                'error': 'YouTube service not available. Please ensure all dependencies are installed.'
            }), 500
            
    except Exception as e:
        print(f"❌ Error in connect_channel: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@dashboard_bp.route('/api/channels/authorize', methods=['POST'])
@login_required
def authorize_channel():
    """API endpoint to complete OAuth authorization with code"""
    try:
        data = request.get_json()
        auth_code = data.get('auth_code', '').strip()
        channel_id = data.get('channel_id', '').strip()
        channel_title = data.get('channel_title', '')
        
        if not auth_code or not channel_id:
            return jsonify({'success': False, 'error': 'Authorization code and channel ID are required'}), 400
        
        # Exchange authorization code for tokens
        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')
        
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "authorization_code"
        }
        
        # Make token request
        import requests
        response = requests.post(token_url, data=payload)
        token_data = response.json()
        
        if "error" in token_data:
            return jsonify({
                'success': False,
                'error': f'Error exchanging code for tokens: {token_data["error"]}'
            }), 400
        
        # Prepare credentials object
        credentials = {
            "token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": [
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.upload"
            ]
        }
        
        # Save credentials to database - use discord_id like production_view does
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        print(f"💾 Saving OAuth credentials for channel {channel_id} for Discord user {discord_id}")
        
        success = db.save_channel_oauth_credentials_sync(
            discord_id,
            channel_id,
            credentials,
            channel_title
        )
        
        print(f"✅ Save result: {success}")
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Successfully connected {channel_title}!',
                'channel_id': channel_id
            })
        else:
            print(f"❌ Failed to save channel credentials for {channel_id}")
            return jsonify({
                'success': False,
                'error': 'Failed to save channel credentials'
            }), 500
            
    except Exception as e:
        import traceback
        print(f"❌ Error in authorize_channel: {e}")
        print(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False, 
            'error': f'Internal server error: {str(e)}'
        }), 500

@dashboard_bp.route('/studio')
@login_required
def manual_production():
    """Manual Production Studio - Content creation workflow matching Discord bot functionality"""
    try:
        
        # print(f"👤 Current user: {current_user.id} - {current_user.username}")  # Commented - too noisy
        print(f"📧 Email: {getattr(current_user, 'email', 'None')}")
        
        # Use Discord ID for group lookup (groups are owned by Discord users)
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        print(f"✅ Using Discord ID: {discord_id} for user: {current_user.username}")
        
        # Get user's MongoDB _id for proper group lookup
        user_doc = db.get_user_by_discord_id_sync(discord_id)
        if not user_doc:
            print(f"❌ User not found in database with Discord ID: {discord_id}")
            user_mongodb_id = discord_id  # Fallback
        else:
            user_mongodb_id = user_doc['_id']
            print(f"✅ Found user MongoDB _id: {user_mongodb_id}")
        
        # Get groups using MongoDB _id (EXACT same as Discord bot)
        query = {
            "$or": [
                {"owner_id": user_mongodb_id},
                {"owner_ids": user_mongodb_id}, 
                {"assigned_users": user_mongodb_id}
            ]
        }
        print(f"🔍 DEBUG: Group query: {query}")
        
        # Use the EXACT same method as the main dashboard that works
        user_groups = db.get_user_groups_sync(discord_id)
        
        # Add competitor_channels field to each group for template compatibility
        for group in user_groups:
            if 'competitor_channels' not in group:
                group['competitor_channels'] = group.get('competitors', [])
        
        print(f"✅ Loaded {len(user_groups)} user groups for manual production")
        print(f"🔍 User groups debug: {[g.get('name', 'Unnamed') for g in user_groups]}")
        print(f"🔍 Competitor counts: {[(g.get('name'), len(g.get('competitor_channels', []))) for g in user_groups]}")
        
        # Debug: Show what fields are in the first group
        if user_groups:
            first_group = user_groups[0]
            print(f"🔍 First group '{first_group.get('name')}' has fields: {list(first_group.keys())}")
            print(f"🔍 First group 'competitors' field type: {type(first_group.get('competitors'))}, length: {len(first_group.get('competitors', []))}")
            print(f"🔍 First group 'competitor_channels' field type: {type(first_group.get('competitor_channels'))}, length: {len(first_group.get('competitor_channels', []))}")
        
        # Collect series/themes from all groups like trend discovery does
        all_series_data = []
        groups_data = []
        
        # OPTIMIZED: Get all series data in bulk instead of one-by-one
        print(f"🚀 Loading series data for {len(user_groups)} groups...")
        
        for group in user_groups:
            group_id = str(group.get('_id'))
            try:
                # Use simplified series lookup to avoid the slow individual model checks
                group_series = db.get_all_series_themes_sync(group_id)
                
                # Convert the themes data to series format (much faster)
                for series_name, themes in group_series.items():
                    if not themes:  # Skip empty series
                        continue
                    
                    # Calculate aggregated stats from themes
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
                
                # Store group data for project selection
                groups_data.append({
                    '_id': group_id,
                    'name': group.get('name', 'Unnamed Project'),
                    'description': group.get('description', 'Market intelligence project'),
                    'series_count': len(group_series),
                    'competitor_channels': group.get('competitors', []),  # Fixed: Use 'competitors' field from database
                    'created_at': group.get('created_at')
                })
                
            except Exception as e:
                print(f"❌ Error loading data for group {group_id}: {e}")
                continue
        
        # OPTIMIZED: Bulk check for trained models and script breakdowns
        print(f"🔍 Checking resource status for {len(all_series_data)} series...")
        
        for series in all_series_data:
            if series.get('themes'):
                # Find the best theme (highest avg views)
                best_theme = max(series['themes'], key=lambda x: x.get('avg_views', 0))
                
                # Quick resource check (without individual DB calls)
                best_theme['has_script_breakdown'] = best_theme.get('script_breakdown') is not None
                best_theme['has_thumbnail_model'] = best_theme.get('trained_model') is not None
                best_theme['has_resources'] = best_theme['has_script_breakdown'] and best_theme['has_thumbnail_model']
                
                series['best_theme'] = best_theme
        
        # Sort by performance metrics
        all_series_data.sort(key=lambda x: x.get('total_views', 0), reverse=True)
        
        print(f"📊 Prepared {len(groups_data)} projects with {len(all_series_data)} total series in FAST mode")
        
        return render_template('modern/manual_production.html', 
                             user_groups=user_groups,
                             projects=groups_data,
                             all_series_data=all_series_data,
                             total_series=len(all_series_data))
        
    except Exception as e:
        print(f"❌ Error loading manual production data: {e}")
        import traceback
        traceback.print_exc()
        return render_template('modern/manual_production.html', 
                             user_groups=[], 
                             projects=[], 
                             all_series_data=[], 
                             total_series=0)

# ========================================
# INSTAGRAM STUDIO API ROUTES
# ========================================

# Import Instagram service
# Instagram Service Import - SIMPLIFIED AND BULLETPROOF
instagram_service = None
remotion_processor = None

def initialize_instagram_services():
    """Initialize Instagram services with multiple fallback methods"""
    global instagram_service, remotion_processor
    
    if instagram_service is not None:
        return True  # Already initialized
    
    try:
        # Method 1: Direct import (should work since we tested it)
        from services.instagram_service import InstagramService, RemotionProcessor
        instagram_service = InstagramService()
        remotion_processor = RemotionProcessor()
        print("[SUCCESS] Instagram services initialized via direct import")
        return True
        
    except Exception as e1:
        print(f"[DEBUG] Direct import failed: {e1}")
        
        try:
            # Method 2: Absolute file path import
            import importlib.util
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            service_file = os.path.join(parent_dir, 'services', 'instagram_service.py')
            
            print(f"[DEBUG] Trying absolute import from: {service_file}")
            
            if os.path.exists(service_file):
                spec = importlib.util.spec_from_file_location("instagram_service_module", service_file)
                instagram_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(instagram_module)
                
                InstagramService = getattr(instagram_module, 'InstagramService')
                RemotionProcessor = getattr(instagram_module, 'RemotionProcessor')
                
                instagram_service = InstagramService()
                remotion_processor = RemotionProcessor()
                print("[SUCCESS] Instagram services initialized via absolute file import")
                return True
            else:
                print(f"[ERROR] Service file not found: {service_file}")
                
        except Exception as e2:
            print(f"[ERROR] Absolute import failed: {e2}")
    
    print("[ERROR] All Instagram service import methods failed")
    return False

# VFX Service Import - Same pattern as Instagram
vfx_service = None

def initialize_vfx_service():
    """Initialize VFX service with multiple fallback methods"""
    global vfx_service
    
    if vfx_service is not None:
        return True  # Already initialized
    
    try:
        # Method 1: Direct import
        from services.vfx_service import VFXService
        vfx_service = VFXService()
        print("[SUCCESS] VFX service initialized via direct import")
        return True
        
    except Exception as e1:
        print(f"[DEBUG] VFX direct import failed: {e1}")
        
        try:
            # Method 2: Absolute file path import
            import importlib.util
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            service_file = os.path.join(parent_dir, 'services', 'vfx_service.py')
            
            print(f"[DEBUG] Trying VFX absolute import from: {service_file}")
            
            if os.path.exists(service_file):
                spec = importlib.util.spec_from_file_location("vfx_service_module", service_file)
                vfx_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(vfx_module)
                
                VFXService = getattr(vfx_module, 'VFXService')
                vfx_service = VFXService()
                print("[SUCCESS] VFX service initialized via absolute file import")
                return True
            else:
                print(f"[ERROR] VFX service file not found: {service_file}")
                
        except Exception as e2:
            print(f"[ERROR] VFX absolute import failed: {e2}")
            import traceback
            traceback.print_exc()
    
    print("[ERROR] All VFX service import methods failed")
    return False

# Initialize services immediately
try:
    initialize_instagram_services()
except Exception as e:
    print(f"[ERROR] Failed to initialize Instagram services: {e}")

try:
    initialize_vfx_service()
except Exception as e:
    print(f"[ERROR] Failed to initialize VFX service: {e}")

@dashboard_bp.route('/api/instagram/accounts')
@login_required
def get_instagram_accounts():
    """Get user's Instagram accounts"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        accounts = db.get_instagram_accounts(discord_id)
        return jsonify(accounts)
    except Exception as e:
        print(f"❌ Error getting Instagram accounts: {e}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/add-account', methods=['POST'])
@login_required
def add_instagram_account():
    """Add Instagram account with verification"""
    try:
        data = request.get_json()
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        username = data.get('username')
        password = data.get('password')
        verification_code = data.get('verification_code')  # 2FA code
        niche = data.get('niche')
        account_type = 'target'  # All accounts are upload accounts now
        
        if not all([username, password]):
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400
        
        # Ensure Instagram service is initialized
        if not instagram_service:
            initialize_instagram_services()
        
        # Verify Instagram account
        if instagram_service:
            import asyncio
            verification = asyncio.run(instagram_service.verify_account(username, password, verification_code))
            if not verification.get('success'):
                error_msg = verification.get('error', 'Unknown error')
                # Check if it's a 2FA challenge
                if verification.get('requires_2fa'):
                    return jsonify({'success': False, 'error': error_msg, 'requires_2fa': True}), 400
                return jsonify({'success': False, 'error': f"Instagram verification failed: {error_msg}"}), 400
        else:
            return jsonify({'success': False, 'error': 'Instagram API service not available. Please check server logs.'}), 500
        
        # Add to database
        success = db.add_instagram_account(
            user_id=discord_id,
            username=username,
            password=password,  # Will be encrypted
            account_type=account_type,
            niche=niche
        )
        
        if success:
            return jsonify({'success': True, 'message': f'Instagram account @{username} added successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to add account'}), 500
    except Exception as e:
        print(f"❌ Error adding Instagram account: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/delete-account', methods=['POST'])
@login_required
def delete_instagram_account():
    """Delete Instagram account"""
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'}), 400
        
        # Delete from database
        result = db.instagram_accounts.delete_one({
            "_id": ObjectId(account_id),
            "user_id": discord_id
        })
        
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Instagram account deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Account not found or not owned by user'}), 404
            
    except Exception as e:
        print(f"❌ Error deleting Instagram account: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/download-all', methods=['POST'])
@login_required
def download_all_instagram_videos():
    """Download all videos from an Instagram account"""
    try:
        data = request.get_json()
        account_id = data.get('account_id')
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Start background job for downloading
        job_id = db.create_instagram_job(
            user_id=discord_id,
            job_type='download_all',
            account_id=account_id,
            status='pending'
        )
        
        # TODO: Start background task for downloading
        # This would use Instagram API to download all videos
        
        return jsonify({'success': True, 'job_id': job_id, 'message': 'Download started'})
    except Exception as e:
        print(f"❌ Error starting download: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/download-from-url', methods=['POST'])
@login_required
def download_from_instagram_url():
    """Download videos from Instagram account URL"""
    try:
        data = request.get_json()
        account_url = data.get('account_url')
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Extract username from URL
        import re
        username_match = re.search(r'instagram\.com/([^/?]+)', account_url)
        if not username_match:
            return jsonify({'success': False, 'error': 'Invalid Instagram URL'}), 400
        
        username = username_match.group(1)
        
        # Ensure Instagram service is initialized
        if not instagram_service:
            initialize_instagram_services()
        
        # Check if Instagram service is available
        if not instagram_service:
            return jsonify({'success': False, 'error': 'Instagram API service not available. Please check server logs.'}), 500
        
        # Start background job for downloading
        job_id = db.create_instagram_job(
            user_id=discord_id,
            job_type='download_from_url',
            target_username=username,
            status='pending'
        )
        
        # Start background task for downloading
        def run_instagram_download():
            """Download videos from Instagram account in background"""
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Update job status
                db.update_instagram_job(job_id, status='downloading', step=f'Fetching videos from @{username}...')
                
                # Get videos from Instagram
                videos = loop.run_until_complete(instagram_service.get_account_videos(username, user_id=discord_id))
                
                # Save videos to database
                for i, video in enumerate(videos):
                    video_id = db.add_instagram_video(discord_id, video)
                    
                    # Update progress
                    progress = int((i + 1) / len(videos) * 100)
                    db.update_instagram_job(job_id, progress=progress, step=f'Downloaded {i+1}/{len(videos)} videos')
                
                # Complete job
                db.update_instagram_job(job_id, status='completed', progress=100, step=f'Downloaded {len(videos)} videos from @{username}')
                
            except Exception as e:
                print(f"❌ Instagram download error: {e}")
                db.update_instagram_job(job_id, status='error', step=f'Error: {str(e)}')
        
        # Run in background thread
        import threading
        thread = threading.Thread(target=run_instagram_download)
        thread.start()
        
        return jsonify({'success': True, 'job_id': job_id, 'message': f'Started downloading from @{username}'})
    except Exception as e:
        print(f"❌ Error starting URL download: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/process-videos', methods=['POST'])
@login_required
def process_instagram_videos():
    """Process videos with Remotion promo overlays"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])
        promo_template = data.get('promo_template')
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        if not video_ids:
            return jsonify({'success': False, 'error': 'No videos selected'}), 400
        
        # Get additional processing parameters
        overlay_duration = data.get('overlay_duration', 3)
        custom_video_path = data.get('custom_video_path')
        
        # Start background job for processing
        job_id = db.create_instagram_job(
            user_id=discord_id,
            job_type='process_videos',
            video_ids=video_ids,
            promo_template=promo_template,
            overlay_duration=overlay_duration,
            custom_video_path=custom_video_path,
            status='pending'
        )
        
        # Start background task for Remotion processing
        def run_video_processing():
            """Process videos with StakeUs! overlay in background"""
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Update job status
                db.update_instagram_job(job_id, status='processing', step='Preparing videos for StakeUs! overlay...')
                
                processed_count = 0
                for i, video_id in enumerate(video_ids):
                    # Get video from database
                    videos = db.get_instagram_videos(discord_id)
                    video = next((v for v in videos if v['id'] == video_id), None)
                    
                    if video:
                        # Prepare overlay config
                        overlay_config = {
                            'overlay_duration': overlay_duration,
                            'custom_video_path': custom_video_path,
                            'transition': 'fade'
                        }
                        
                        # Process with Remotion
                        result = loop.run_until_complete(
                            remotion_processor.process_video_with_overlay(
                                video.get('video_url', ''), 
                                overlay_config
                            )
                        )
                        
                        if result.get('success'):
                            # Update video status in database
                            db.update_instagram_video_status(
                                video_id, 
                                'processed',
                                processed_video_path=result.get('processed_video_path')
                            )
                            processed_count += 1
                        
                        # Update progress
                        progress = int((i + 1) / len(video_ids) * 100)
                        db.update_instagram_job(job_id, progress=progress, step=f'Processed {i+1}/{len(video_ids)} videos with StakeUs!')
                
                # Complete job
                db.update_instagram_job(job_id, status='completed', progress=100, step=f'Processed {processed_count} videos with StakeUs! overlay')
                
            except Exception as e:
                print(f"❌ Video processing error: {e}")
                db.update_instagram_job(job_id, status='error', step=f'Error: {str(e)}')
        
        # Run in background thread
        import threading
        thread = threading.Thread(target=run_video_processing)
        thread.start()
        
        return jsonify({'success': True, 'job_id': job_id, 'message': f'Started processing {len(video_ids)} videos with StakeUs!'})
    except Exception as e:
        print(f"❌ Error starting video processing: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/bulk-upload', methods=['POST'])
@login_required
def bulk_upload_instagram_videos():
    """Upload processed videos to Instagram accounts"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        if not video_ids:
            return jsonify({'success': False, 'error': 'No videos selected'}), 400
        
        # Start background job for uploading
        job_id = db.create_instagram_job(
            user_id=discord_id,
            job_type='bulk_upload',
            video_ids=video_ids,
            status='pending'
        )
        
        # TODO: Start background task for Instagram upload
        
        return jsonify({'success': True, 'job_id': job_id, 'message': f'Started uploading {len(video_ids)} videos'})
    except Exception as e:
        print(f"❌ Error starting bulk upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/videos')
@login_required
def get_instagram_videos():
    """Get user's Instagram videos"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        videos = db.get_instagram_videos(discord_id)
        return jsonify(videos)
    except Exception as e:
        print(f"❌ Error getting Instagram videos: {e}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/jobs')
@login_required
def get_instagram_jobs():
    """Get user's Instagram processing jobs"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        jobs = db.get_instagram_jobs(discord_id)
        return jsonify(jobs)
    except Exception as e:
        print(f"❌ Error getting Instagram jobs: {e}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/upload-overlay-video', methods=['POST'])
@login_required
def upload_overlay_video():
    """Upload custom StakeUs! overlay video"""
    try:
        if 'video' not in request.files:
            return jsonify({'success': False, 'error': 'No video file provided'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate file type
        if not file.content_type.startswith('video/'):
            return jsonify({'success': False, 'error': 'File must be a video'}), 400
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'uploads', 'overlays')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        import uuid
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"stakeus_overlay_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # Return the path for Remotion to use
        relative_path = f"/static/uploads/overlays/{unique_filename}"
        
        return jsonify({
            'success': True, 
            'video_path': relative_path,
            'filename': unique_filename,
            'message': 'StakeUs! overlay video uploaded successfully'
        })
        
    except Exception as e:
        print(f"❌ Error uploading overlay video: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/create-schedule', methods=['POST'])
@login_required
def create_instagram_schedule():
    """Create optimized posting schedule"""
    try:
        data = request.get_json()
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        account_id = data.get('account_id')
        video_ids = data.get('video_ids', [])
        posts_per_day = data.get('posts_per_day', 3)
        
        if not all([account_id, video_ids]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Create optimized schedule
        schedule_id = db.create_posting_schedule(discord_id, account_id, video_ids, posts_per_day)
        
        if schedule_id:
            return jsonify({
                'success': True, 
                'schedule_id': schedule_id,
                'message': f'Created posting schedule for {len(video_ids)} videos ({posts_per_day} posts/day)'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create schedule'}), 500
            
    except Exception as e:
        print(f"❌ Error creating schedule: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/schedule')
@login_required
def get_instagram_schedule():
    """Get user's posting schedules"""
    try:
        discord_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        schedules = db.get_posting_schedule(discord_id)
        return jsonify(schedules)
    except Exception as e:
        print(f"❌ Error getting schedule: {e}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/api/instagram/optimal-times')
@login_required
def get_optimal_times():
    """Get optimal posting times for next 7 days"""
    try:
        from services.instagram_scheduler import InstagramScheduler
        scheduler = InstagramScheduler()
        
        optimal_times = scheduler.get_next_optimal_times(days_ahead=7)
        
        return jsonify({
            'success': True,
            'optimal_times': optimal_times,
            'timezone': 'EST',
            'posts_per_day': 3,
            'total_slots': len(optimal_times)
        })
    except Exception as e:
        print(f"❌ Error getting optimal times: {e}")
        return jsonify({'error': str(e)}), 500


# ===== VFX BREAKDOWN ROUTES =====

@dashboard_bp.route('/api/vfx/analyze-series', methods=['POST'])
@login_required
async def analyze_series_vfx():
    """Analyze existing series videos to create VFX guidelines"""
    try:
        data = request.get_json()
        series_name = data.get('series_name')
        theme_name = data.get('theme_name')
        group_id = data.get('group_id')
        
        if not all([series_name, theme_name, group_id]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Get existing videos for this series/theme (you'll need to implement this)
        # For now, we'll use empty list and generate default guidelines
        video_urls = []  # TODO: Get from your existing video database
        
        # Use global VFX service
        global vfx_service
        if vfx_service is None:
            initialize_vfx_service()
        
        # Analyze VFX patterns
        vfx_guidelines = await vfx_service.analyze_series_vfx_patterns(
            series_name, theme_name, video_urls
        )
        
        # Save guidelines to database
        success = db.save_vfx_guidelines(group_id, series_name, theme_name, vfx_guidelines)
        
        if success:
            return jsonify({
                'success': True,
                'vfx_guidelines': vfx_guidelines,
                'message': f'VFX guidelines created for {series_name} - {theme_name}'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save VFX guidelines'}), 500
            
    except Exception as e:
        print(f"❌ Error analyzing series VFX: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/vfx/generate-breakdown', methods=['POST'])
@login_required
async def generate_vfx_breakdown():
    """Generate VFX breakdown from script breakdown"""
    try:
        data = request.get_json()
        script_breakdown = data.get('script_breakdown')
        series_name = data.get('series_name')
        theme_name = data.get('theme_name')
        group_id = data.get('group_id')
        script_breakdown_id = data.get('script_breakdown_id', 'manual')
        
        if not all([script_breakdown, series_name, theme_name, group_id]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Get user ID
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Use global VFX service
        global vfx_service
        if vfx_service is None:
            initialize_vfx_service()
        
        # Get or create VFX guidelines
        vfx_guidelines = db.get_vfx_guidelines(group_id, series_name, theme_name)
        if not vfx_guidelines:
            # Create default guidelines if none exist
            vfx_guidelines = await vfx_service.analyze_series_vfx_patterns(series_name, theme_name, [])
            db.save_vfx_guidelines(group_id, series_name, theme_name, vfx_guidelines)
        
        # Create VFX breakdown
        vfx_breakdown = await vfx_service.create_vfx_breakdown(script_breakdown, vfx_guidelines)
        
        # Save VFX breakdown to database
        breakdown_id = db.save_vfx_breakdown(
            user_id, group_id, series_name, theme_name, script_breakdown_id, vfx_breakdown
        )
        
        if breakdown_id:
            return jsonify({
                'success': True,
                'vfx_breakdown': vfx_breakdown,
                'breakdown_id': breakdown_id,
                'message': f'VFX breakdown created with {len(vfx_breakdown)} scenes'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save VFX breakdown'}), 500
            
    except Exception as e:
        print(f"❌ Error generating VFX breakdown: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/vfx/generate-sora-videos', methods=['POST'])
@login_required
def generate_sora_videos():
    """Generate Sora 2 videos from VFX breakdown"""
    try:
        data = request.get_json()
        breakdown_id = data.get('breakdown_id')
        selected_scenes = data.get('selected_scenes', [])  # Scene IDs to generate
        
        if not breakdown_id:
            return jsonify({'success': False, 'error': 'Missing breakdown ID'}), 400
        
        # Get user ID
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Get VFX breakdown
        vfx_breakdown_data = db.get_vfx_breakdown(breakdown_id)
        if not vfx_breakdown_data:
            return jsonify({'success': False, 'error': 'VFX breakdown not found'}), 404
        
        vfx_breakdown = vfx_breakdown_data.get('vfx_breakdown', [])
        
        # Use global VFX service
        global vfx_service
        if vfx_service is None:
            initialize_vfx_service()
        
        # Start background generation for selected scenes
        generation_jobs = []
        
        def run_sora_generation():
            """Generate Sora videos in background"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            for scene in vfx_breakdown:
                scene_id = scene.get('segment_id')
                
                # Skip if not selected (if selection provided)
                if selected_scenes and scene_id not in selected_scenes:
                    continue
                
                try:
                    # Save generation request
                    generation_id = db.save_sora_generation(
                        user_id, breakdown_id, str(scene_id), 
                        scene.get('sora_prompt', ''), status='generating'
                    )
                    
                    # Generate video with Sora
                    video_url = loop.run_until_complete(
                        vfx_service.generate_sora_video(
                            scene.get('sora_prompt', ''),
                            scene.get('duration', 5)
                        )
                    )
                    
                    # Update generation result
                    if video_url:
                        db.update_sora_generation(generation_id, video_url, 'completed')
                    else:
                        db.update_sora_generation(generation_id, '', 'failed')
                        
                except Exception as e:
                    print(f"❌ Error generating scene {scene_id}: {e}")
                    if 'generation_id' in locals():
                        db.update_sora_generation(generation_id, '', 'failed')
        
        # Start background thread
        import threading
        thread = threading.Thread(target=run_sora_generation)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Started Sora generation for {len(selected_scenes) if selected_scenes else len(vfx_breakdown)} scenes',
            'breakdown_id': breakdown_id,
            'total_scenes': len(vfx_breakdown)
        })
        
    except Exception as e:
        print(f"❌ Error starting Sora generation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/vfx/breakdowns', methods=['GET'])
@login_required
def get_user_vfx_breakdowns():
    """Get all VFX breakdowns for current user"""
    try:
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        breakdowns = db.get_user_vfx_breakdowns(user_id)
        
        return jsonify({
            'success': True,
            'breakdowns': breakdowns
        })
        
    except Exception as e:
        print(f"❌ Error getting VFX breakdowns: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/vfx/breakdown/<breakdown_id>', methods=['GET'])
@login_required
def get_vfx_breakdown_details(breakdown_id):
    """Get detailed VFX breakdown with generation status"""
    try:
        breakdown = db.get_vfx_breakdown(breakdown_id)
        if not breakdown:
            return jsonify({'success': False, 'error': 'Breakdown not found'}), 404
        
        # TODO: Add generation status for each scene
        # generations = db.get_sora_generations_by_breakdown(breakdown_id)
        
        return jsonify({
            'success': True,
            'breakdown': breakdown
        })
        
    except Exception as e:
        print(f"❌ Error getting breakdown details: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== SORA GENERATION ROUTES =====

@dashboard_bp.route('/api/sora/generate-storyboard', methods=['POST'])
@login_required
def generate_sora_storyboard():
    """Generate AI Director storyboard for Sora video generation"""
    try:
        data = request.get_json()
        title = data.get('title')
        series_name = data.get('series_name')
        theme_name = data.get('theme_name')
        group_id = data.get('group_id')
        format_type = data.get('format')  # 'short' or 'long'
        duration = int(data.get('duration'))  # Convert to int
        scene_count = int(data.get('scene_count'))  # Convert to int
        
        if not all([title, series_name, theme_name, group_id, format_type, duration, scene_count]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Get user ID
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Use global VFX service (initialized at module load)
        global vfx_service
        if vfx_service is None:
            initialize_vfx_service()
        
        if vfx_service is None:
            return jsonify({'success': False, 'error': 'VFX service not available'}), 500
        
        # Generate storyboard using AI Director
        # VFX service will automatically check for existing script breakdown or generate one
        # EXACT same logic as content_studio_routes.py
        import asyncio
        
        # Try to get existing loop, create new one only if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        storyboard_scenes = loop.run_until_complete(
            vfx_service.generate_sora_storyboard(
                title, series_name, theme_name, format_type, duration, scene_count, 
                script_breakdown=None,  # Let VFX service handle it
                group_id=group_id,
                db=db
            )
        )
        # Don't close the loop - other operations might need it
        
        if storyboard_scenes:
            # Save storyboard to database (reusing VFX breakdown structure)
            storyboard_id = db.save_vfx_breakdown(
                user_id, group_id, series_name, theme_name, 
                'sora_storyboard', storyboard_scenes
            )
            
            return jsonify({
                'success': True,
                'storyboard_scenes': storyboard_scenes,
                'storyboard_id': storyboard_id,
                'message': f'AI Director created storyboard with {len(storyboard_scenes)} scenes'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to generate storyboard'}), 500
            
    except Exception as e:
        print(f"❌ Error generating Sora storyboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/sora/generate-videos', methods=['POST'])
@login_required
def generate_sora_storyboard_videos():
    """Generate videos using Sora 2 API from storyboard"""
    try:
        data = request.get_json()
        storyboard_scenes = data.get('storyboard_scenes', [])
        total_duration = data.get('total_duration')
        format_type = data.get('format')
        
        if not storyboard_scenes:
            return jsonify({'success': False, 'error': 'No storyboard scenes provided'}), 400
        
        # Get user ID
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Use global VFX service
        global vfx_service
        if vfx_service is None:
            initialize_vfx_service()
        
        # Start background generation for each scene
        generation_jobs = []
        
        def run_sora_generation():
            """Generate Sora videos in background"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            for scene in storyboard_scenes:
                try:
                    scene_id = scene.get('scene_number', 1)
                    
                    # Save generation request to database
                    generation_id = db.save_sora_generation(
                        user_id, 'sora_storyboard', str(scene_id), 
                        scene.get('prompt', ''), status='generating'
                    )
                    
                    # Generate video with Sora
                    video_url = loop.run_until_complete(
                        vfx_service.generate_sora_video(
                            scene.get('prompt', ''),
                            scene.get('duration', 10)
                        )
                    )
                    
                    # Update generation result
                    if video_url:
                        db.update_sora_generation(generation_id, video_url, 'completed')
                        print(f"[SUCCESS] Generated Sora video for scene {scene_id}")
                    else:
                        db.update_sora_generation(generation_id, '', 'failed')
                        print(f"[FAILED] Sora generation failed for scene {scene_id}")
                        
                except Exception as e:
                    print(f"❌ Error generating scene {scene.get('scene_number', '?')}: {e}")
                    if 'generation_id' in locals():
                        db.update_sora_generation(generation_id, '', 'failed')
        
        # Start background thread
        import threading
        thread = threading.Thread(target=run_sora_generation)
        thread.daemon = True
        thread.start()
        
        estimated_cost = total_duration * 30  # $30 per second
        
        return jsonify({
            'success': True,
            'message': f'Started Sora generation for {len(storyboard_scenes)} scenes',
            'total_scenes': len(storyboard_scenes),
            'estimated_cost': estimated_cost,
            'format': format_type,
            'total_duration': total_duration
        })
        
    except Exception as e:
        print(f"❌ Error starting Sora generation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@dashboard_bp.route('/api/sora/generation-status', methods=['GET'])
@login_required
def get_sora_generation_status():
    """Get status of Sora video generation"""
    try:
        user_id = str(current_user.discord_id) if hasattr(current_user, 'discord_id') and current_user.discord_id else str(current_user.id)
        
        # Get recent Sora generations for this user
        # Note: We're reusing the sora_generations collection from the VFX system
        generations = list(db.sora_generations.find(
            {'user_id': user_id},
            sort=[('created_at', -1)],
            limit=20
        ))
        
        # Convert ObjectIds to strings
        for gen in generations:
            gen['_id'] = str(gen['_id'])
        
        return jsonify({
            'success': True,
            'generations': generations
        })
        
    except Exception as e:
        print(f"❌ Error getting Sora generation status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

