"""
Slideshow Generator Service
Generates Instagram/TikTok slideshow content (image carousels with text overlays)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import Dict, List, Optional
from core.database import Database
import logging

logger = logging.getLogger(__name__)

class SlideshowGenerator:
    """Service for generating slideshow content (image carousels with text overlays)"""
    
    def __init__(self):
        self.db = Database()
    
    def generate_slideshow(self, 
                          series_name: str, 
                          theme_name: str, 
                          content_style_id: str, 
                          slide_count: int = 5,
                          group_id: Optional[str] = None) -> Dict:
        """
        Generate a slideshow (image carousel) for a series/theme
        
        Args:
            series_name: Series name from group
            theme_name: Theme name from group
            content_style_id: Content style ID (must be slideshow format)
            slide_count: Number of slides to generate
            group_id: Optional group ID for context
        
        Returns:
            {
                'success': bool,
                'slides': [
                    {
                        'image_path': str,
                        'text_overlay': str,
                        'slide_number': int
                    }
                ],
                'carousel_path': str  # Path to combined carousel
            }
        """
        try:
            # Get content style
            content_style = self.db.db['content_styles'].find_one({'_id': content_style_id})
            if not content_style:
                return {'success': False, 'error': 'Content style not found'}
            
            if content_style.get('content_format') != 'slideshow':
                return {'success': False, 'error': 'Content style is not a slideshow format'}
            
            slideshow_config = content_style.get('slideshow_config', {})
            
            # Get theme/script data for text content
            script_text = self._get_script_for_theme(group_id, series_name, theme_name)
            
            # Split script into slides
            slide_texts = self._split_script_into_slides(script_text, slide_count)
            
            # Generate slides
            slides = []
            for i, slide_text in enumerate(slide_texts):
                slide = self._generate_slide(
                    slide_text,
                    slide_number=i + 1,
                    total_slides=slide_count,
                    slideshow_config=slideshow_config,
                    content_style=content_style
                )
                slides.append(slide)
            
            # Combine into carousel format
            carousel_path = self._combine_slides_to_carousel(slides, content_style)
            
            return {
                'success': True,
                'slides': slides,
                'carousel_path': carousel_path,
                'slide_count': len(slides)
            }
            
        except Exception as e:
            logger.error(f"Error generating slideshow: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def _get_script_for_theme(self, group_id: Optional[str], series_name: str, theme_name: str) -> str:
        """Get script text for theme (for slideshow text content)"""
        try:
            if group_id:
                script_data = self.db.get_full_script_sync(group_id, series_name, theme_name)
                if script_data:
                    return script_data
            # Fallback: return theme name as text
            return f"{series_name}: {theme_name}"
        except Exception as e:
            logger.warning(f"Could not get script for theme: {e}")
            return f"{series_name}: {theme_name}"
    
    def _split_script_into_slides(self, script_text: str, slide_count: int) -> List[str]:
        """Split script text into slide-sized chunks"""
        # Simple split by sentences
        sentences = script_text.split('. ')
        sentences_per_slide = max(1, len(sentences) // slide_count)
        
        slides = []
        for i in range(0, len(sentences), sentences_per_slide):
            slide_text = '. '.join(sentences[i:i + sentences_per_slide])
            if slide_text:
                slides.append(slide_text)
            if len(slides) >= slide_count:
                break
        
        # Pad if needed
        while len(slides) < slide_count:
            slides.append(slides[-1] if slides else "Content slide")
        
        return slides[:slide_count]
    
    def _generate_slide(self, 
                              slide_text: str,
                              slide_number: int,
                              total_slides: int,
                              slideshow_config: Dict,
                              content_style: Dict) -> Dict:
        """Generate a single slide (image + text overlay)"""
        try:
            # Generate base image using Flux
            image_path = self._generate_slide_image(
                slide_text,
                slideshow_config,
                content_style,
                slide_number
            )
            
            # Add text overlay
            final_image_path = self._add_text_overlay(
                image_path,
                slide_text,
                slideshow_config.get('text_overlay', {}),
                content_style.get('platform', 'tiktok')
            )
            
            return {
                'image_path': final_image_path,
                'text_overlay': slide_text,
                'slide_number': slide_number,
                'total_slides': total_slides
            }
        except Exception as e:
            logger.error(f"Error generating slide {slide_number}: {e}")
            raise
    
    def _generate_slide_image(self, 
                              slide_text: str,
                              slideshow_config: Dict,
                              content_style: Dict,
                              slide_number: int) -> str:
        """Generate base image for slide using Flux"""
        # TODO: Integrate with Flux service
        # For now, return placeholder
        logger.info(f"Generating image for slide: {slide_text[:50]}...")
        
        # Get image style guidelines from content style
        image_guidelines = slideshow_config.get('image_style_guidelines', {})
        prompt_template = image_guidelines.get('prompt_template', '{text}')
        
        # Generate Flux prompt
        flux_prompt = prompt_template.format(text=slide_text)
        
        # TODO: Call Flux API
        # For now, return placeholder path
        return f"/tmp/slide_image_{slide_number}.png"
    
    def _add_text_overlay(self,
                          image_path: str,
                          text: str,
                          text_overlay_config: Dict,
                          platform: str) -> str:
        """Add text overlay to image with TikTok/Instagram styling"""
        # TODO: Use PIL/Pillow to add text overlay
        # Apply text overlay rules from config:
        # - Position (top/center/bottom)
        # - Font style (TikTok bold / Instagram minimal)
        # - Background (solid/gradient/blur)
        # - Max lines
        
        logger.info(f"Adding text overlay to {image_path}")
        
        # TODO: Implement text overlay using PIL
        # For now, return original path
        return image_path
    
    def _combine_slides_to_carousel(self, slides: List[Dict], content_style: Dict) -> str:
        """Combine slides into carousel format for Instagram/TikTok"""
        # TODO: Combine images into carousel format
        # For Instagram: Create multi-image post
        # For TikTok: Create carousel format
        
        logger.info(f"Combining {len(slides)} slides into carousel")
        
        # TODO: Implement carousel combination
        return "/tmp/carousel.zip"

# Singleton instance
slideshow_generator = SlideshowGenerator()

