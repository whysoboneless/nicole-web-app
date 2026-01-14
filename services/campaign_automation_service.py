"""
Campaign Automation Service
Handles auto series/theme selection, retention optimization, and lifecycle management
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from core.database import Database
import random

db = Database()

class CampaignAutomationService:
    """Service for automating campaign operations"""
    
    def __init__(self):
        self.db = Database()
    
    # ========================================
    # AUTO SERIES/THEME SELECTION
    # ========================================
    
    def auto_select_series_themes(self, campaign_id: str, channel_id: str, group_id: str) -> Dict:
        """
        Automatically select series and themes for a channel based on:
        - Campaign objective
        - Competitor group analysis
        - Trend discovery data
        - Content strategy (mix of established + emerging)
        """
        try:
            # Get campaign details
            campaign = self.db.get_campaign(campaign_id)
            if not campaign:
                return {'success': False, 'error': 'Campaign not found'}
            
            # Get group (competitor intelligence)
            group = self.db.get_group(group_id)
            if not group:
                return {'success': False, 'error': 'Group not found'}
            
            # Get trend discovery data for this group
            # This would call the existing trend discovery analysis
            top_series = self._get_top_performing_series(group_id, limit=10)
            top_themes = self._get_top_performing_themes(group_id, limit=10)
            
            # Content strategy: Mix established + emerging
            selected_series = []
            selected_themes = []
            
            # 70% from established creators (proven content)
            # 30% from emerging channels (fresh trends)
            established_series = [s for s in top_series if s.get('source_type') == 'established'][:3]
            emerging_series = [s for s in top_series if s.get('source_type') == 'emerging'][:2]
            
            selected_series = established_series + emerging_series
            
            # Similar for themes
            established_themes = [t for t in top_themes if t.get('source_type') == 'established'][:3]
            emerging_themes = [t for t in top_themes if t.get('source_type') == 'emerging'][:2]
            
            selected_themes = established_themes + emerging_themes
            
            # Update channel with selected series/themes
            self.db.update_campaign_channel(channel_id, {
                'series': [s.get('name') for s in selected_series],
                'themes': [t.get('name') for t in selected_themes],
                'auto_selected': True,
                'last_selection_update': datetime.utcnow()
            })
            
            return {
                'success': True,
                'series': selected_series,
                'themes': selected_themes,
                'message': f'Auto-selected {len(selected_series)} series and {len(selected_themes)} themes'
            }
            
        except Exception as e:
            print(f"Error auto-selecting series/themes: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_top_performing_series(self, group_id: str, limit: int = 10) -> List[Dict]:
        """Get top performing series from group's trend analysis"""
        # TODO: Integrate with existing trend_discovery analysis
        # For now, return mock data structure
        return []
    
    def _get_top_performing_themes(self, group_id: str, limit: int = 10) -> List[Dict]:
        """Get top performing themes from group's trend analysis"""
        # TODO: Integrate with existing trend_discovery analysis
        return []
    
    # ========================================
    # AUDIENCE RETENTION OPTIMIZATION
    # ========================================
    
    def auto_optimize_retention(self, channel_id: str, series: str, theme: str) -> Dict:
        """
        Automatically optimize script breakdown based on YouTube Analytics retention data
        Triggers after 3+ videos in same series/theme
        """
        try:
            channel = self.db.get_channel_by_id(channel_id)
            if not channel:
                return {'success': False, 'error': 'Channel not found'}
            
            # Check if we have enough videos (3+) for this series/theme
            videos_count = self._count_videos_for_series_theme(
                channel['youtube_channel_id'], 
                series, 
                theme
            )
            
            if videos_count < 3:
                return {
                    'success': False,
                    'error': f'Need at least 3 videos (currently {videos_count})'
                }
            
            # Pull YouTube Analytics retention data
            retention_data = self._get_youtube_retention_data(
                channel['youtube_channel_id'],
                series,
                theme
            )
            
            if not retention_data:
                return {'success': False, 'error': 'No retention data available'}
            
            # Get current script breakdown for this series/theme
            current_breakdown = self._get_current_breakdown(series, theme)
            
            # Analyze retention drop-off points
            optimization_suggestions = self._analyze_retention_dropoffs(
                retention_data,
                current_breakdown
            )
            
            # Apply optimizations to breakdown
            optimized_breakdown = self._apply_retention_optimizations(
                current_breakdown,
                optimization_suggestions
            )
            
            # Save optimized breakdown
            self.db.update_script_breakdown(series, theme, optimized_breakdown)
            
            return {
                'success': True,
                'optimizations_applied': len(optimization_suggestions),
                'message': 'Script breakdown optimized based on retention data'
            }
            
        except Exception as e:
            print(f"Error optimizing retention: {e}")
            return {'success': False, 'error': str(e)}
    
    def _count_videos_for_series_theme(self, youtube_channel_id: str, series: str, theme: str) -> int:
        """Count videos published for specific series/theme"""
        # TODO: Query videos collection
        return 0
    
    def _get_youtube_retention_data(self, youtube_channel_id: str, series: str, theme: str) -> Optional[Dict]:
        """Pull retention data from YouTube Analytics API"""
        # TODO: Implement YouTube Analytics API integration
        return None
    
    def _get_current_breakdown(self, series: str, theme: str) -> Dict:
        """Get current script breakdown template"""
        # TODO: Get from vfx_breakdowns or content_styles
        return {}
    
    def _analyze_retention_dropoffs(self, retention_data: Dict, breakdown: Dict) -> List[Dict]:
        """Analyze where viewers drop off and suggest fixes"""
        suggestions = []
        # TODO: Implement retention analysis logic
        return suggestions
    
    def _apply_retention_optimizations(self, breakdown: Dict, suggestions: List[Dict]) -> Dict:
        """Apply retention optimizations to breakdown"""
        # TODO: Implement optimization application
        return breakdown
    
    # ========================================
    # LIFECYCLE AUTOMATION
    # ========================================
    
    def evaluate_channel_performance(self, channel_id: str) -> Dict:
        """
        Evaluate channel performance and recommend lifecycle action
        - If testing + criteria met → scale
        - If testing + criteria not met → pause
        - If scaling + performance drops → pause
        """
        try:
            channel = self.db.get_channel_by_id(channel_id)
            if not channel:
                return {'success': False, 'error': 'Channel not found'}
            
            campaign = self.db.get_campaign(str(channel['campaign_id']))
            if not campaign or not campaign.get('lifecycle_automation_enabled'):
                return {'success': False, 'error': 'Lifecycle automation not enabled'}
            
            # Get lifecycle rules
            rules = campaign.get('lifecycle_rules', {})
            testing_duration = rules.get('testing_duration_days', 30)
            min_views = rules.get('min_views_threshold', 1000)
            min_watch_time = rules.get('min_watch_time_percentage', 40)
            
            # Calculate days in testing
            testing_start = channel.get('testing_start_date')
            if testing_start:
                days_in_testing = (datetime.utcnow() - testing_start).days
            else:
                days_in_testing = 0
            
            # Get performance metrics
            total_views = channel.get('total_views', 0)
            watch_time_pct = channel.get('watch_time_percentage', 0)
            videos_published = channel.get('videos_published', 0)
            
            # Average views per video
            avg_views = total_views / videos_published if videos_published > 0 else 0
            
            # Evaluation logic
            status = channel.get('status')
            recommendation = None
            reason = None
            
            if status == 'testing':
                if days_in_testing >= testing_duration:
                    # Testing period complete - evaluate
                    if avg_views >= min_views and watch_time_pct >= min_watch_time:
                        recommendation = 'scale'
                        reason = f'Passed testing: {avg_views:.0f} avg views (>{min_views}), {watch_time_pct:.1f}% watch time (>{min_watch_time}%)'
                    else:
                        recommendation = 'pause'
                        reason = f'Failed testing: {avg_views:.0f} avg views (<{min_views}) or {watch_time_pct:.1f}% watch time (<{min_watch_time}%)'
                else:
                    recommendation = 'continue_testing'
                    reason = f'Still in testing phase: {days_in_testing}/{testing_duration} days'
            
            elif status == 'scaling':
                # Check if performance is maintained
                if avg_views < min_views * 0.7 or watch_time_pct < min_watch_time * 0.7:
                    recommendation = 'pause'
                    reason = 'Performance dropped below 70% of threshold'
                else:
                    recommendation = 'continue_scaling'
                    reason = 'Performance maintained'
            
            return {
                'success': True,
                'recommendation': recommendation,
                'reason': reason,
                'metrics': {
                    'days_in_testing': days_in_testing,
                    'avg_views': avg_views,
                    'watch_time_pct': watch_time_pct,
                    'videos_published': videos_published
                }
            }
            
        except Exception as e:
            print(f"Error evaluating channel: {e}")
            return {'success': False, 'error': str(e)}
    
    def execute_lifecycle_action(self, channel_id: str, action: str) -> bool:
        """Execute lifecycle action (scale/pause)"""
        try:
            if action == 'scale':
                return self.db.update_channel_status(channel_id, 'scaling')
            elif action == 'pause':
                return self.db.update_channel_status(channel_id, 'paused')
            return False
        except Exception as e:
            print(f"Error executing lifecycle action: {e}")
            return False
    
    # ========================================
    # CAMPAIGN CONTENT SCHEDULING
    # ========================================
    
    def schedule_campaign_content(self, campaign_id: str) -> Dict:
        """
        Coordinate content scheduling across all campaign channels
        Avoid upload conflicts, optimize for maximum reach
        """
        try:
            channels = self.db.get_campaign_channels(campaign_id)
            
            # Build schedule for next 30 days
            schedule = []
            
            for channel in channels:
                if channel['status'] not in ['testing', 'scaling']:
                    continue
                
                frequency = channel.get('upload_frequency', 'daily')
                
                # Calculate upload times for this channel
                channel_schedule = self._calculate_upload_schedule(
                    channel_id=channel['_id'],
                    frequency=frequency,
                    days=30
                )
                
                schedule.extend(channel_schedule)
            
            # Sort by date and check for conflicts
            schedule.sort(key=lambda x: x['scheduled_time'])
            
            # Resolve conflicts (same channel uploading too close together)
            resolved_schedule = self._resolve_scheduling_conflicts(schedule)
            
            return {
                'success': True,
                'schedule': resolved_schedule,
                'message': f'Generated schedule for {len(channels)} channels'
            }
            
        except Exception as e:
            print(f"Error scheduling campaign content: {e}")
            return {'success': False, 'error': str(e)}
    
    def _calculate_upload_schedule(self, channel_id: str, frequency: str, days: int) -> List[Dict]:
        """Calculate upload times for a channel"""
        schedule = []
        # TODO: Implement scheduling logic
        return schedule
    
    def _resolve_scheduling_conflicts(self, schedule: List[Dict]) -> List[Dict]:
        """Resolve scheduling conflicts"""
        # TODO: Implement conflict resolution
        return schedule

# Singleton instance
campaign_automation = CampaignAutomationService()

