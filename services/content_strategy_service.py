"""
Content Strategy Service
Handles content strategy assignment, niche adaptation, and strategy recommendations
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ContentStrategyService:
    """
    Service for managing content strategies for campaigns and channels
    Handles niche adaptation and strategy recommendations
    """
    
    def __init__(self, db):
        self.db = db
    
    def find_closest_niche(self, product_audience: Dict, user_groups: List[Dict]) -> Optional[Dict]:
        """
        Find closest matching niche from existing groups
        
        Args:
            product_audience: Audience data from product research
            user_groups: User's existing groups
        
        Returns:
            Best matching group or None
        """
        
        if not user_groups:
            return None
        
        best_match = None
        best_score = 0
        
        product_interests = product_audience.get('interests', [])
        product_content_types = product_audience.get('content_preferences', {}).get('content_types', [])
        
        for group in user_groups:
            score = 0
            
            # Check group name for matches
            group_name_lower = group.get('name', '').lower()
            for interest in product_interests:
                if interest.lower() in group_name_lower:
                    score += 10
            
            # Check group description
            group_desc = group.get('description', '').lower()
            for content_type in product_content_types:
                if any(word in group_desc for word in content_type.lower().split()):
                    score += 5
            
            # Check competitor channels in group
            competitors = group.get('competitors', [])
            for competitor in competitors[:5]:  # Check first 5
                competitor_name = competitor.get('name', '').lower()
                for interest in product_interests:
                    if interest.lower() in competitor_name:
                        score += 3
            
            if score > best_score:
                best_score = score
                best_match = group
        
        # Only return if score is above threshold
        if best_score >= 5:
            return {
                'group': best_match,
                'match_score': best_score,
                'adaptation_strategy': f"Adapt existing '{best_match.get('name')}' group with focus on product"
            }
        
        return None
    
    def recommend_strategy(self, campaign_research: Dict, platform: str = 'youtube') -> Dict:
        """
        Recommend content strategy from campaign research
        
        Args:
            campaign_research: Product research data from campaign
            platform: 'youtube', 'instagram', or 'tiktok'
        
        Returns:
            Recommended strategy dict
        """
        
        content_preferences = campaign_research.get('content_preferences', {})
        content_types = content_preferences.get('content_types', [])
        target_audience = campaign_research.get('target_audience', {})
        
        # Platform-specific adaptations
        if platform == 'tiktok' or platform == 'instagram':
            # UGC-based content styles
            recommended_styles = ['ugc_review', 'ugc_unboxing', 'ugc_tutorial']
            content_format = 'short_form'
        else:
            # YouTube: Traditional content styles
            recommended_styles = self._map_content_types_to_styles(content_types)
            content_format = 'long_form'
        
        return {
            'content_types': content_types[:5],
            'recommended_content_styles': recommended_styles[:3],
            'target_series': self._generate_series_suggestions(content_types),
            'target_themes': [target_audience.get('primary_buyers', ['customers'])[0].title()],
            'platform': platform,
            'content_format': content_format,
            'niche_adaptation': campaign_research.get('recommended_strategy', {}).get('niche_adaptation', '')
        }
    
    def _map_content_types_to_styles(self, content_types: List[str]) -> List[str]:
        """Map content types to content style names"""
        
        mapping = {
            'buying guides': 'top_10_countdown',
            'tutorials': 'educational_documentary',
            'reviews': 'product_review',
            'comparisons': 'top_10_countdown',
            'market trends': 'news_commentary',
            'investment advice': 'news_commentary',
            'restoration': 'documentary_educational',
            'maintenance': 'tutorial_educational',
            'unboxing': 'product_review',
            'explanations': 'educational_documentary'
        }
        
        styles = []
        for content_type in content_types:
            content_lower = content_type.lower()
            for keyword, style in mapping.items():
                if keyword in content_lower:
                    if style not in styles:
                        styles.append(style)
        
        return styles[:3] if styles else ['top_10_countdown']
    
    def _generate_series_suggestions(self, content_types: List[str]) -> List[str]:
        """Generate series name suggestions from content types"""
        
        suggestions = []
        
        if any('guide' in ct.lower() for ct in content_types):
            suggestions.append('Buying Guides')
        if any('review' in ct.lower() for ct in content_types):
            suggestions.append('Product Reviews')
        if any('tutorial' in ct.lower() for ct in content_types):
            suggestions.append('How-To Tutorials')
        if any('trend' in ct.lower() for ct in content_types):
            suggestions.append('Market Trends')
        if any('comparison' in ct.lower() for ct in content_types):
            suggestions.append('Product Comparisons')
        
        return suggestions[:3] if suggestions else ['Product Content']
    
    async def create_strategy_from_campaign_default(self, campaign_id: str, platform: str = 'youtube') -> Dict:
        """
        Create content strategy using campaign's default strategy
        
        Args:
            campaign_id: Campaign ID
            platform: Target platform
        
        Returns:
            Strategy dict ready for channel assignment
        """
        
        campaign = self.db.get_campaign(campaign_id)
        if not campaign:
            return {'success': False, 'error': 'Campaign not found'}
        
        product_research = campaign.get('product_research', {})
        if not product_research:
            return {'success': False, 'error': 'No product research found'}
        
        recommended_strategy = self.recommend_strategy(product_research, platform)
        
        return {
            'success': True,
            'source': 'campaign_default',
            'strategy': recommended_strategy,
            'group_id': None,  # Will be auto-created if needed
            'content_style_id': None  # Will be selected based on recommendations
        }
    
    def validate_strategy(self, strategy: Dict) -> Dict:
        """
        Validate content strategy completeness
        
        Args:
            strategy: Strategy dict to validate
        
        Returns:
            Validation result with missing fields
        """
        
        required_fields = ['content_style_id']
        missing = []
        
        for field in required_fields:
            if not strategy.get(field):
                missing.append(field)
        
        is_valid = len(missing) == 0
        
        return {
            'valid': is_valid,
            'missing_fields': missing,
            'errors': [] if is_valid else [f'Missing required field: {field}' for field in missing]
        }


# Factory function
def get_content_strategy_service(db):
    return ContentStrategyService(db)

