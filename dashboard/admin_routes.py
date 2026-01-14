"""
Admin Dashboard Routes for Nicole Web Suite
Mirrors Discord bot admin functionality for web interface
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from core.database import Database
from core.analysis_service import AnalysisService
from datetime import datetime
from bson import ObjectId
import asyncio

# Create admin blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Initialize services
db = Database()
analysis_service = AnalysisService()

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        if not getattr(current_user, 'is_admin', False):
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard.main'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """Main admin dashboard"""
    try:
        # Get statistics
        all_groups = db.get_all_groups_sync(include_private=True)
        all_users = db.get_all_users_sync()
        
        # Count different types
        public_groups = sum(1 for g in all_groups if g.get('is_public', True))
        private_groups = sum(1 for g in all_groups if not g.get('is_public', True))
        premium_users = sum(1 for u in all_users if u.get('is_premium', False))
        beta_users = sum(1 for u in all_users if u.get('is_beta', False))
        
        stats = {
            'total_users': len(all_users),
            'total_groups': len(all_groups),
            'public_groups': public_groups,
            'private_groups': private_groups,
            'premium_users': premium_users,
            'beta_users': beta_users
        }
        
        # Get recent activity
        recent_groups = sorted(all_groups, key=lambda x: x.get('created_at', datetime.min), reverse=True)[:5]
        recent_users = sorted(all_users, key=lambda x: x.get('created_at', datetime.min), reverse=True)[:5]
        
        return render_template('admin/dashboard.html',
                             stats=stats,
                             recent_groups=recent_groups,
                             recent_users=recent_users)
    except Exception as e:
        print(f"❌ Error loading admin dashboard: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading dashboard data', 'error')
        return redirect(url_for('dashboard.main'))

@admin_bp.route('/groups')
@login_required
@admin_required
def manage_groups():
    """Group management page"""
    try:
        # Get all groups including private ones
        all_groups = db.get_all_groups_sync(include_private=True)
        
        # Get filter parameters
        filter_type = request.args.get('type', 'all')
        search_query = request.args.get('search', '')
        
        # Apply filters
        if filter_type == 'public':
            all_groups = [g for g in all_groups if g.get('is_public', True)]
        elif filter_type == 'private':
            all_groups = [g for g in all_groups if not g.get('is_public', True)]
        elif filter_type == 'premium':
            all_groups = [g for g in all_groups if g.get('is_premium', False)]
        
        # Apply search
        if search_query:
            all_groups = [g for g in all_groups if search_query.lower() in g.get('name', '').lower()]
        
        # Sort by creation date
        all_groups = sorted(all_groups, key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        return render_template('admin/manage_groups.html',
                             groups=all_groups,
                             filter_type=filter_type,
                             search_query=search_query)
    except Exception as e:
        print(f"❌ Error loading groups: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading groups', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/groups/<group_id>')
@login_required
@admin_required
def view_group(group_id):
    """View and edit a specific group"""
    try:
        group = db.get_group_by_id_sync(group_id, full_document=True)
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('admin.manage_groups'))
        
        # Get subscriber details
        subscribers = []
        for subscriber_id in group.get('subscribers', []):
            user = db.get_user_by_discord_id_sync(subscriber_id)
            if user:
                subscribers.append(user)
        
        return render_template('admin/view_group.html',
                             group=group,
                             subscribers=subscribers)
    except Exception as e:
        print(f"❌ Error loading group: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading group', 'error')
        return redirect(url_for('admin.manage_groups'))

@admin_bp.route('/groups/<group_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_group(group_id):
    """Edit group settings"""
    try:
        name = request.form.get('name')
        is_public = request.form.get('is_public') == 'true'
        is_premium = request.form.get('is_premium') == 'true'
        price = float(request.form.get('price', 0))
        whop_product_id = request.form.get('whop_product_id', '')
        
        update_data = {
            'name': name,
            'is_public': is_public,
            'is_premium': is_premium,
            'price': price if is_premium else 0,
            'whop_product_id': whop_product_id if is_premium else None,
            'is_purchasable': is_premium
        }
        
        db.update_group_sync(group_id, update_data)
        flash('Group updated successfully', 'success')
        
        return redirect(url_for('admin.view_group', group_id=group_id))
    except Exception as e:
        print(f"❌ Error updating group: {e}")
        flash('Error updating group', 'error')
        return redirect(url_for('admin.view_group', group_id=group_id))

@admin_bp.route('/groups/<group_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_group(group_id):
    """Delete a group"""
    try:
        db.delete_group_sync(group_id)
        flash('Group deleted successfully', 'success')
        return redirect(url_for('admin.manage_groups'))
    except Exception as e:
        print(f"❌ Error deleting group: {e}")
        flash('Error deleting group', 'error')
        return redirect(url_for('admin.manage_groups'))

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    """User management page"""
    try:
        # Get all users
        all_users = db.get_all_users_sync()
        
        # Get filter parameters
        filter_type = request.args.get('type', 'all')
        search_query = request.args.get('search', '')
        
        # Apply filters
        if filter_type == 'admin':
            all_users = [u for u in all_users if u.get('is_admin', False)]
        elif filter_type == 'premium':
            all_users = [u for u in all_users if u.get('is_premium', False)]
        elif filter_type == 'beta':
            all_users = [u for u in all_users if u.get('is_beta', False)]
        elif filter_type == 'designer':
            all_users = [u for u in all_users if u.get('is_thumbnail_designer', False)]
        
        # Apply search
        if search_query:
            all_users = [u for u in all_users 
                        if search_query.lower() in u.get('username', '').lower() 
                        or search_query.lower() in u.get('discord_id', '').lower()]
        
        # Sort by creation date
        all_users = sorted(all_users, key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        return render_template('admin/manage_users.html',
                             users=all_users,
                             filter_type=filter_type,
                             search_query=search_query)
    except Exception as e:
        print(f"❌ Error loading users: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading users', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/users/<user_id>')
@login_required
@admin_required
def view_user(user_id):
    """View and edit a specific user"""
    try:
        # Try to get user by Discord ID first, then by MongoDB ID
        user = db.get_user_by_discord_id_sync(user_id)
        if not user:
            user = db.get_user_by_id_sync(user_id)
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin.manage_users'))
        
        # Get user's groups
        user_groups = db.get_user_groups_sync(str(user.get('discord_id', '')))
        
        return render_template('admin/view_user.html',
                             user=user,
                             user_groups=user_groups)
    except Exception as e:
        print(f"❌ Error loading user: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading user', 'error')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/<user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user permissions"""
    try:
        is_admin = request.form.get('is_admin') == 'true'
        is_premium = request.form.get('is_premium') == 'true'
        is_beta = request.form.get('is_beta') == 'true'
        is_thumbnail_designer = request.form.get('is_thumbnail_designer') == 'true'
        
        # Get user first
        user = db.get_user_by_discord_id_sync(user_id)
        if not user:
            user = db.get_user_by_id_sync(user_id)
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin.manage_users'))
        
        update_data = {
            'is_admin': is_admin,
            'is_premium': is_premium,
            'is_beta': is_beta,
            'is_thumbnail_designer': is_thumbnail_designer
        }
        
        db.update_user_sync(str(user['_id']), update_data)
        flash('User permissions updated successfully', 'success')
        
        return redirect(url_for('admin.view_user', user_id=user_id))
    except Exception as e:
        print(f"❌ Error updating user: {e}")
        flash('Error updating user permissions', 'error')
        return redirect(url_for('admin.view_user', user_id=user_id))

@admin_bp.route('/users/<user_id>/grant-access', methods=['POST'])
@login_required
@admin_required
def grant_group_access(user_id):
    """Grant user access to a private group"""
    try:
        group_id = request.form.get('group_id')
        
        # Get user
        user = db.get_user_by_discord_id_sync(user_id)
        if not user:
            user = db.get_user_by_id_sync(user_id)
        
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin.manage_users'))
        
        # Assign group
        result = db.assign_private_group_to_user_sync(str(user['_id']), group_id)
        
        if result:
            flash('Group access granted successfully', 'success')
        else:
            flash('Failed to grant group access', 'error')
        
        return redirect(url_for('admin.view_user', user_id=user_id))
    except Exception as e:
        print(f"❌ Error granting group access: {e}")
        flash('Error granting group access', 'error')
        return redirect(url_for('admin.view_user', user_id=user_id))

@admin_bp.route('/broadcast')
@login_required
@admin_required
def broadcast():
    """Broadcast message page"""
    return render_template('admin/broadcast.html')

@admin_bp.route('/broadcast/send', methods=['POST'])
@login_required
@admin_required
def send_broadcast():
    """Send broadcast message to all users"""
    try:
        title = request.form.get('title')
        message = request.form.get('message')
        target_type = request.form.get('target_type', 'all')
        
        # Get target users
        all_users = db.get_all_users_sync()
        
        if target_type == 'premium':
            all_users = [u for u in all_users if u.get('is_premium', False)]
        elif target_type == 'beta':
            all_users = [u for u in all_users if u.get('is_beta', False)]
        elif target_type == 'free':
            all_users = [u for u in all_users if not u.get('is_premium', False)]
        
        # Store broadcast in database for users to see on next login
        broadcast_data = {
            'title': title,
            'message': message,
            'sent_by': current_user.username,
            'sent_at': datetime.utcnow(),
            'target_type': target_type,
            'user_ids': [str(u['_id']) for u in all_users]
        }
        
        db.db['broadcasts'].insert_one(broadcast_data)
        
        flash(f'Broadcast sent to {len(all_users)} users', 'success')
        return redirect(url_for('admin.broadcast'))
    except Exception as e:
        print(f"❌ Error sending broadcast: {e}")
        flash('Error sending broadcast', 'error')
        return redirect(url_for('admin.broadcast'))

@admin_bp.route('/discovery')
@login_required
@admin_required
def high_rpm_discovery():
    """High RPM channel discovery page"""
    try:
        # Get existing high potential channels from database
        channels = db.get_high_potential_channels_sync()
        
        return render_template('admin/high_rpm_discovery.html',
                             channels=channels)
    except Exception as e:
        print(f"❌ Error loading discovery page: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading discovery page', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/discovery/channels/<channel_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_potential_channel(channel_id):
    """Delete a potential channel"""
    try:
        db.delete_high_potential_channel_sync(channel_id)
        flash('Channel deleted successfully', 'success')
        return redirect(url_for('admin.high_rpm_discovery'))
    except Exception as e:
        print(f"❌ Error deleting channel: {e}")
        flash('Error deleting channel', 'error')
        return redirect(url_for('admin.high_rpm_discovery'))

@admin_bp.route('/discovery/clear', methods=['POST'])
@login_required
@admin_required
def clear_potential_channels():
    """Clear all potential channels"""
    try:
        count = db.clear_high_potential_channels_sync()
        flash(f'Cleared {count} channels', 'success')
        return redirect(url_for('admin.high_rpm_discovery'))
    except Exception as e:
        print(f"❌ Error clearing channels: {e}")
        flash('Error clearing channels', 'error')
        return redirect(url_for('admin.high_rpm_discovery'))

@admin_bp.route('/validate-niche')
@login_required
@admin_required
def validate_niche():
    """Niche validation page"""
    return render_template('admin/validate_niche.html')

@admin_bp.route('/api/statistics')
@login_required
@admin_required
def api_statistics():
    """API endpoint for dashboard statistics"""
    try:
        all_groups = db.get_all_groups_sync(include_private=True)
        all_users = db.get_all_users_sync()
        
        stats = {
            'total_users': len(all_users),
            'total_groups': len(all_groups),
            'public_groups': sum(1 for g in all_groups if g.get('is_public', True)),
            'private_groups': sum(1 for g in all_groups if not g.get('is_public', True)),
            'premium_users': sum(1 for u in all_users if u.get('is_premium', False)),
            'beta_users': sum(1 for u in all_users if u.get('is_beta', False))
        }
        
        return jsonify(stats)
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/groups')
@login_required
@admin_required
def api_groups():
    """API endpoint to get all groups for dropdown"""
    try:
        all_groups = db.get_all_groups_sync(include_private=True)
        
        # Convert ObjectId to string for JSON serialization
        groups_data = []
        for group in all_groups:
            groups_data.append({
                '_id': str(group['_id']),
                'name': group.get('name', 'Unnamed Group'),
                'is_premium': group.get('is_premium', False),
                'is_public': group.get('is_public', True)
            })
        
        return jsonify(groups_data)
    except Exception as e:
        print(f"❌ Error getting groups: {e}")
        return jsonify({'error': str(e)}), 500

