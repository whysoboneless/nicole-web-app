"""
Product Promotion Service
Generates 10-second product overlays/segments for video content
Integrates with Remotion for video generation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Dict, Optional
from core.database import Database
import json

db = Database()

class ProductPromotionService:
    """Service for generating product promotion content"""
    
    def __init__(self):
        self.db = Database()
    
    # ========================================
    # PRODUCT OVERLAY GENERATION
    # ========================================
    
    def generate_product_overlay(self, product_data: Dict) -> Dict:
        """
        Generate a 10-second product overlay video using Remotion
        
        Args:
            product_data: {
                'name': 'Product Name',
                'url': 'https://...',
                'description': '...',
                'promotion_type': 'overlay' or 'segment'
            }
        
        Returns:
            {
                'success': bool,
                'video_url': str,  # URL to generated overlay video
                'overlay_data': dict  # Data for Remotion composition
            }
        """
        try:
            product_name = product_data.get('name')
            product_url = product_data.get('url')
            description = product_data.get('description', '')
            promotion_type = product_data.get('promotion_type', 'overlay')
            
            if not product_name or not product_url:
                return {'success': False, 'error': 'Product name and URL required'}
            
            # Generate Remotion composition data
            if promotion_type == 'overlay':
                overlay_data = self._generate_overlay_composition(product_data)
            else:
                overlay_data = self._generate_segment_composition(product_data)
            
            # TODO: Call Remotion rendering service
            # This would integrate with existing remotion-video-editor project
            video_url = self._render_remotion_composition(overlay_data)
            
            return {
                'success': True,
                'video_url': video_url,
                'overlay_data': overlay_data,
                'message': f'Generated {promotion_type} for {product_name}'
            }
            
        except Exception as e:
            print(f"Error generating product overlay: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_overlay_composition(self, product_data: Dict) -> Dict:
        """
        Generate Remotion composition for non-intrusive overlay
        Appears in corner/bottom of video, doesn't interrupt content
        """
        return {
            'type': 'overlay',
            'duration': 10,  # seconds
            'position': 'bottom-right',
            'components': [
                {
                    'type': 'ProductCard',
                    'props': {
                        'productName': product_data['name'],
                        'productUrl': product_data['url'],
                        'description': product_data.get('description', '')[:100],
                        'animation': 'slide-in',
                        'backgroundColor': 'rgba(0, 0, 0, 0.8)',
                        'textColor': '#ffffff',
                        'ctaText': 'Learn More',
                        'ctaColor': '#6366f1'
                    },
                    'startFrame': 0,
                    'durationInFrames': 300  # 10 seconds at 30fps
                }
            ]
        }
    
    def _generate_segment_composition(self, product_data: Dict) -> Dict:
        """
        Generate Remotion composition for full 10-second segment
        Interrupts video briefly for product promotion
        """
        return {
            'type': 'segment',
            'duration': 10,
            'components': [
                {
                    'type': 'ProductShowcase',
                    'props': {
                        'productName': product_data['name'],
                        'productUrl': product_data['url'],
                        'description': product_data.get('description', ''),
                        'animation': 'fade-in-zoom',
                        'layout': 'centered',
                        'backgroundColor': '#6366f1',
                        'textColor': '#ffffff',
                        'ctaText': 'Check it out',
                        'showQRCode': True
                    },
                    'startFrame': 0,
                    'durationInFrames': 300
                },
                {
                    'type': 'VoiceOver',
                    'props': {
                        'text': f"Check out {product_data['name']} - link in description!",
                        'voice': 'af_nicole'
                    }
                }
            ]
        }
    
    def _render_remotion_composition(self, composition_data: Dict) -> str:
        """
        Render Remotion composition and return video URL
        TODO: Integrate with remotion-video-editor service
        """
        # Placeholder: Would call remotion rendering service
        # This would use the existing remotion-video-editor codebase
        return f"https://storage.example.com/promotions/{composition_data['type']}_placeholder.mp4"
    
    # ========================================
    # WORKFLOW INTEGRATION
    # ========================================
    
    def inject_promotion_into_workflow(self, content_style_id: str, product_data: Dict) -> Dict:
        """
        Inject product promotion into content style VFX workflow
        
        Modifies the workflow to include product overlay at optimal times:
        - For overlays: Non-intrusive, appears during low-intensity moments
        - For segments: Inserts 10-second break at natural transition points
        """
        try:
            # Get content style workflow
            content_style = self.db.get_content_style(content_style_id)
            if not content_style:
                return {'success': False, 'error': 'Content style not found'}
            
            # Generate promotion overlay
            promotion = self.generate_product_overlay(product_data)
            if not promotion['success']:
                return promotion
            
            # Modify workflow to include promotion
            workflow = content_style.get('vfx_workflow', {})
            promotion_type = product_data.get('promotion_type', 'overlay')
            
            if promotion_type == 'overlay':
                # Add overlay to workflow (appears throughout video)
                workflow['overlays'] = workflow.get('overlays', [])
                workflow['overlays'].append({
                    'type': 'product_promotion',
                    'video_url': promotion['video_url'],
                    'timing': 'continuous',  # Show throughout
                    'frequency': 'every_2_minutes',  # Show every 2 minutes
                    'duration': 10
                })
            else:
                # Insert segment at natural break points
                workflow['segments'] = workflow.get('segments', [])
                # Insert after intro (typically after first 2-3 minutes)
                workflow['segments'].insert(1, {
                    'type': 'product_segment',
                    'video_url': promotion['video_url'],
                    'duration': 10,
                    'position': 'after_intro'
                })
            
            # Save modified workflow
            self.db.update_content_style(content_style_id, {'vfx_workflow': workflow})
            
            return {
                'success': True,
                'workflow': workflow,
                'message': f'Injected {promotion_type} into workflow'
            }
            
        except Exception as e:
            print(f"Error injecting promotion: {e}")
            return {'success': False, 'error': str(e)}
    
    # ========================================
    # CAMPAIGN PRODUCT MANAGEMENT
    # ========================================
    
    def add_product_to_campaign(self, campaign_id: str, product_data: Dict) -> bool:
        """Add product to campaign and generate promotions"""
        try:
            campaign = self.db.get_campaign(campaign_id)
            if not campaign:
                return False
            
            # Generate promotion for this product
            promotion = self.generate_product_overlay(product_data)
            if not promotion['success']:
                return False
            
            # Add to campaign products
            products = campaign.get('products', [])
            product_data['promotion_video_url'] = promotion['video_url']
            products.append(product_data)
            
            # Update campaign
            self.db.update_campaign(campaign_id, {'products': products})
            
            # Apply to all campaign channels
            channels = self.db.get_campaign_channels(campaign_id)
            for channel in channels:
                if channel.get('content_style_id'):
                    self.inject_promotion_into_workflow(
                        str(channel['content_style_id']),
                        product_data
                    )
            
            return True
            
        except Exception as e:
            print(f"Error adding product to campaign: {e}")
            return False
    
    def get_campaign_products(self, campaign_id: str) -> list:
        """Get all products for a campaign"""
        try:
            campaign = self.db.get_campaign(campaign_id)
            if campaign:
                return campaign.get('products', [])
            return []
        except Exception as e:
            print(f"Error getting campaign products: {e}")
            return []
    
    # ========================================
    # CONTENT STYLE INTEGRATION
    # ========================================
    
    def get_content_style(self, content_style_id: str) -> Optional[Dict]:
        """Get content style (placeholder for actual implementation)"""
        # TODO: Implement or import from existing content style system
        return None
    
    def update_content_style(self, content_style_id: str, updates: Dict) -> bool:
        """Update content style (placeholder)"""
        # TODO: Implement
        return True

# Singleton instance
product_promotion = ProductPromotionService()

