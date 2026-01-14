"""
Script to add TikTok and Instagram content styles to the database
Run this once to populate the content_styles collection
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from nicole_web_suite_template.core.database import Database
from datetime import datetime

def add_social_content_styles():
    """Add TikTok and Instagram content styles"""
    db = Database()
    
    # TikTok Content Styles
    tiktok_styles = [
        {
            'name': 'UGC Product Video',
            'platform': 'tiktok',
            'content_type': 'ugc_video',
            'description': 'Script-based short-form UGC-style product videos optimized for TikTok',
            'duration_range': '30-60s',
            'automation_ready': True,
            'requires_avatar': True,
            'requires_product_image': True,
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Product Showcase',
            'platform': 'tiktok',
            'content_type': 'product_showcase',
            'description': 'Static product images with music and text overlays',
            'duration_range': '15-30s',
            'automation_ready': True,
            'requires_avatar': False,
            'requires_product_image': True,
            'created_at': datetime.utcnow()
        }
    ]
    
    # Instagram Content Styles
    instagram_styles = [
        {
            'name': 'Carousel Post',
            'platform': 'instagram',
            'content_type': 'carousel',
            'description': 'Image carousel posts with product information and CTAs',
            'slide_count': '5-10',
            'automation_ready': True,
            'requires_avatar': False,
            'requires_product_image': True,
            'created_at': datetime.utcnow()
        },
        {
            'name': 'Reel',
            'platform': 'instagram',
            'content_type': 'reel',
            'description': 'Short-form video content similar to TikTok UGC style',
            'duration_range': '30-60s',
            'automation_ready': True,
            'requires_avatar': True,
            'requires_product_image': True,
            'created_at': datetime.utcnow()
        }
    ]
    
    # Insert TikTok styles
    print("Adding TikTok content styles...")
    for style in tiktok_styles:
        # Check if already exists
        existing = db.vfx_content_styles.find_one({
            'name': style['name'],
            'platform': 'tiktok'
        })
        
        if existing:
            print(f"  ✓ {style['name']} already exists")
        else:
            result = db.vfx_content_styles.insert_one(style)
            print(f"  ✓ Added {style['name']} (ID: {result.inserted_id})")
    
    # Insert Instagram styles
    print("Adding Instagram content styles...")
    for style in instagram_styles:
        # Check if already exists
        existing = db.vfx_content_styles.find_one({
            'name': style['name'],
            'platform': 'instagram'
        })
        
        if existing:
            print(f"  ✓ {style['name']} already exists")
        else:
            result = db.vfx_content_styles.insert_one(style)
            print(f"  ✓ Added {style['name']} (ID: {result.inserted_id})")
    
    print("\n✅ Social content styles setup complete!")
    print("\nTikTok Styles:")
    for style in tiktok_styles:
        print(f"  - {style['name']}: {style['description']}")
    
    print("\nInstagram Styles:")
    for style in instagram_styles:
        print(f"  - {style['name']}: {style['description']}")

if __name__ == '__main__':
    add_social_content_styles()

