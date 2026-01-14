"""
Authentication module for Nicole Web Suite
Discord OAuth Integration for Production Use
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import UserMixin, login_user, logout_user, current_user, login_required
import hashlib
import requests
import os
from urllib.parse import quote
from datetime import datetime
from .database import Database

# Create auth blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

# Initialize database
db = Database()

# Discord OAuth Configuration
DISCORD_CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
DISCORD_CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_REDIRECT_URI = os.getenv('DISCORD_REDIRECT_URI', 'http://127.0.0.1:5000/auth/discord/callback')
DISCORD_API_ENDPOINT = 'https://discord.com/api/v10'

# Debug: Check if Discord OAuth is configured
print(f"[AUTH] Discord OAuth Config:")
print(f"  DISCORD_CLIENT_ID: {DISCORD_CLIENT_ID}")
print(f"  DISCORD_CLIENT_SECRET: {'***SET***' if DISCORD_CLIENT_SECRET else 'NOT SET'}")
print(f"  DISCORD_REDIRECT_URI: {DISCORD_REDIRECT_URI}")

# URL-encode redirect URI for OAuth URL
DISCORD_OAUTH_URL = f'https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={quote(DISCORD_REDIRECT_URI, safe="")}&response_type=code&scope=identify'

# Owner Discord ID for admin privileges
OWNER_DISCORD_ID = os.getenv('OWNER_DISCORD_ID', '528049173178875924')

class User(UserMixin):
    """User class for Flask-Login - Discord Based Authentication"""
    
    def __init__(self, user_id, username, discord_id, is_admin=False, is_premium=False, is_beta=False, avatar=None):
        self.id = user_id
        self.username = username
        self.discord_id = discord_id
        self.avatar = avatar
        # Don't override Flask-Login properties - they're already defined in UserMixin
        self.is_admin = is_admin
        self.is_premium = is_premium
        self.is_beta = is_beta
        
    @property
    def is_active(self):
        return True
        
    @property
    def is_anonymous(self):
        return False
    
    @property
    def avatar_url(self):
        """Get Discord avatar URL"""
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.discord_id}/{self.avatar}.png"
        else:
            # Use default Discord avatar
            return "https://cdn.discordapp.com/embed/avatars/0.png"

def load_user(user_id):
    """Load user for Flask-Login - Discord Based System"""
    # print(f"load_user called with user_id: {user_id}")  # Commented out - too noisy
    
    # Handle owner user specifically
    if user_id == OWNER_DISCORD_ID:
        return User(
            user_id=OWNER_DISCORD_ID,
            username='Owner',
            discord_id=OWNER_DISCORD_ID,
            is_admin=True,
            is_premium=True,
            is_beta=True
        )
    
    # Try to load from database for real users
    try:
        print(f"Looking up real user in database: {user_id}")
        user_data = db.get_user_by_id(user_id)
        if user_data:
            print(f"Found user in database: {user_data.get('username')}")
            return User(
                user_id=user_data.get('_id') or user_data.get('id'),
                username=user_data.get('username'),
                discord_id=user_data.get('discord_id'),
                is_admin=user_data.get('is_admin', False),
                is_premium=user_data.get('is_premium', False),
                is_beta=user_data.get('is_beta', False),
                avatar=user_data.get('avatar')
            )
        else:
            print(f"User {user_id} not found in database")
    except Exception as e:
        print(f"Error loading user {user_id}: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"Returning None for user_id: {user_id}")
    return None

def get_current_user():
    """Get current authenticated user"""
    return current_user

@auth_bp.route('/login')
def login():
    """Login page - Discord OAuth"""
    # For development/testing, allow direct owner login
    if request.args.get('dev') == 'owner' and OWNER_DISCORD_ID:
        user = User(
            user_id=OWNER_DISCORD_ID,
            username='Owner',
            discord_id=OWNER_DISCORD_ID,
            is_admin=True,
            is_premium=True,
            is_beta=True
        )
        login_user(user, remember=True)
        print(f"✅ Dev login as OWNER with Discord ID: {OWNER_DISCORD_ID}")
        return redirect(url_for('dashboard.main'))
    
    # Show Discord OAuth login page
    return render_template('auth/login.html', discord_oauth_url=DISCORD_OAUTH_URL)

@auth_bp.route('/discord')
def discord_oauth():
    """Redirect to Discord OAuth"""
    if not DISCORD_CLIENT_ID:
        flash('Discord OAuth not configured', 'error')
        return redirect(url_for('auth.login'))
    return redirect(DISCORD_OAUTH_URL)

@auth_bp.route('/discord/callback')
def discord_callback():
    """Handle Discord OAuth callback"""
    code = request.args.get('code')
    if not code:
        flash('Discord login failed - no authorization code', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # Exchange code for access token
        token_data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': DISCORD_REDIRECT_URI
        }
        
        token_response = requests.post(
            f'{DISCORD_API_ENDPOINT}/oauth2/token',
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if token_response.status_code != 200:
            flash('Discord login failed - could not get access token', 'error')
            return redirect(url_for('auth.login'))
        
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        
        # Get user info from Discord
        user_response = requests.get(
            f'{DISCORD_API_ENDPOINT}/users/@me',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if user_response.status_code != 200:
            flash('Discord login failed - could not get user info', 'error')
            return redirect(url_for('auth.login'))
        
        discord_user = user_response.json()
        discord_id = discord_user['id']
        username = discord_user['username']
        avatar = discord_user.get('avatar')  # Get Discord avatar hash
        
        # Check if user is owner
        is_admin = (discord_id == OWNER_DISCORD_ID)
        
        # Check if user exists in database
        user_data = db.get_user_by_discord_id_sync(discord_id)
        
        if not user_data:
            # Create new user in database
            user_data = {
                'discord_id': discord_id,
                'username': username,
                'avatar': avatar,
                'is_admin': is_admin,
                'is_premium': False,  # Set based on payment status
                'is_beta': True,     # For now, all users get beta access
                'created_at': datetime.utcnow()
            }
            db.create_discord_user(user_data)
        else:
            # Update avatar in case it changed
            db.update_user_sync(str(user_data['_id']), {'avatar': avatar})
        
        # Create Flask-Login user
        user = User(
            user_id=discord_id,
            username=username,
            discord_id=discord_id,
            is_admin=user_data.get('is_admin', is_admin),
            is_premium=user_data.get('is_premium', False),
            is_beta=user_data.get('is_beta', True),
            avatar=avatar
        )
        
        login_user(user, remember=True)
        
        if is_admin:
            flash(f'Welcome back, Owner {username}! 👑', 'success')
        else:
            flash(f'Welcome {username}! 🚀', 'success')
        
        print(f"✅ Discord login successful: {username} (ID: {discord_id}, Admin: {is_admin})")
        return redirect(url_for('dashboard.main'))
        
    except Exception as e:
        print(f"Discord OAuth error: {e}")
        import traceback
        traceback.print_exc()
        flash('Discord login failed - please try again', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/discord_login/<discord_id>')
def direct_discord_login(discord_id):
    """Direct Discord login endpoint"""
    try:
        user_data = db.get_user_by_discord_id_sync(discord_id)
        if user_data:
            user = User(
                user_id=user_data.get('_id') or user_data.get('id'),
                username=user_data.get('username'),
                discord_id=user_data.get('discord_id'),
                is_admin=user_data.get('is_admin', False),
                is_premium=user_data.get('is_premium', False),
                is_beta=user_data.get('is_beta', False)
            )
            login_user(user, remember=True)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard.main'))
        else:
            flash('Discord account not found', 'error')
    except Exception as e:
        print(f"Discord login error: {e}")
        flash('Login error', 'error')
    
    return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if request.method == 'POST':
        username = request.form.get('username')
        discord_id = request.form.get('discord_id') or request.form.get('password')  # Use password field for Discord ID
        
        if not username:
            flash('Please enter a username', 'error')
            return render_template('auth/register.html')
        
        try:
            # Create user account
            user_data = db.create_user(username, discord_id or f"web_{username}")
            if user_data:
                flash('Account created successfully! Please log in.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Registration error - please try again', 'error')
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration error - please try again', 'error')
    
    return render_template('auth/register.html') 
