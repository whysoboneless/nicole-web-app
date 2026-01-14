"""
Video Editor module for Nicole Web Suite
"""

from flask import Blueprint

video_editor_bp = Blueprint('video_editor', __name__)

from . import routes
