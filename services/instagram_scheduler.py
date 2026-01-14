"""
Instagram Scheduler - Optimal posting times and scheduling system
"""

import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional
import pytz
import logging

logger = logging.getLogger(__name__)

class InstagramScheduler:
    """Handle Instagram posting schedules and optimal timing"""
    
    def __init__(self):
        # Optimal posting times for American audience (EST/PST)
        self.optimal_times = {
            'monday': [
                {'hour': 11, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 14, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 19, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'tuesday': [
                {'hour': 10, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 13, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 18, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'wednesday': [
                {'hour': 11, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 14, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 19, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'thursday': [
                {'hour': 10, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 13, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 18, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'friday': [
                {'hour': 9, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 13, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 16, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'saturday': [
                {'hour': 11, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 14, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 17, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ],
            'sunday': [
                {'hour': 12, 'minute': 0, 'timezone': 'EST', 'engagement': 'peak'},
                {'hour': 15, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'},
                {'hour': 18, 'minute': 0, 'timezone': 'EST', 'engagement': 'high'}
            ]
        }
    
    def get_next_optimal_times(self, days_ahead: int = 7) -> List[Dict]:
        """Get next optimal posting times for the specified number of days"""
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        
        scheduled_times = []
        
        for day_offset in range(days_ahead):
            target_date = now + timedelta(days=day_offset)
            day_name = target_date.strftime('%A').lower()
            
            if day_name in self.optimal_times:
                for time_slot in self.optimal_times[day_name]:
                    scheduled_time = target_date.replace(
                        hour=time_slot['hour'],
                        minute=time_slot['minute'],
                        second=0,
                        microsecond=0
                    )
                    
                    # Only include future times
                    if scheduled_time > now:
                        scheduled_times.append({
                            'datetime': scheduled_time,
                            'timestamp': scheduled_time.timestamp(),
                            'day': day_name.title(),
                            'time_str': scheduled_time.strftime('%I:%M %p EST'),
                            'engagement_level': time_slot['engagement'],
                            'date_str': scheduled_time.strftime('%Y-%m-%d'),
                            'is_peak': time_slot['engagement'] == 'peak'
                        })
        
        return sorted(scheduled_times, key=lambda x: x['timestamp'])
    
    def create_posting_schedule(self, account_id: str, video_ids: List[str], posts_per_day: int = 3) -> List[Dict]:
        """Create optimized posting schedule for videos"""
        try:
            optimal_times = self.get_next_optimal_times(days_ahead=30)  # 30 days of scheduling
            
            # Filter to get the requested number of posts per day
            daily_slots = {}
            for time_slot in optimal_times:
                date = time_slot['date_str']
                if date not in daily_slots:
                    daily_slots[date] = []
                
                if len(daily_slots[date]) < posts_per_day:
                    daily_slots[date].append(time_slot)
            
            # Flatten and sort by timestamp
            available_slots = []
            for date_slots in daily_slots.values():
                available_slots.extend(date_slots)
            
            available_slots.sort(key=lambda x: x['timestamp'])
            
            # Assign videos to time slots
            schedule = []
            for i, video_id in enumerate(video_ids):
                if i < len(available_slots):
                    slot = available_slots[i]
                    schedule.append({
                        'video_id': video_id,
                        'account_id': account_id,
                        'scheduled_time': slot['datetime'],
                        'time_str': slot['time_str'],
                        'day': slot['day'],
                        'engagement_level': slot['engagement_level'],
                        'is_peak': slot['is_peak'],
                        'status': 'scheduled'
                    })
            
            logger.info(f"Created posting schedule for {len(schedule)} videos across {len(set(s['day'] for s in schedule))} days")
            return schedule
            
        except Exception as e:
            logger.error(f"Error creating posting schedule: {e}")
            return []
    
    def get_schedule_summary(self, schedule: List[Dict]) -> Dict:
        """Get summary of posting schedule"""
        if not schedule:
            return {}
        
        total_posts = len(schedule)
        peak_time_posts = len([s for s in schedule if s['is_peak']])
        days_covered = len(set(s['day'] for s in schedule))
        
        # Group by day
        posts_by_day = {}
        for post in schedule:
            day = post['day']
            if day not in posts_by_day:
                posts_by_day[day] = 0
            posts_by_day[day] += 1
        
        return {
            'total_posts': total_posts,
            'peak_time_posts': peak_time_posts,
            'days_covered': days_covered,
            'posts_by_day': posts_by_day,
            'next_post': schedule[0] if schedule else None,
            'avg_posts_per_day': round(total_posts / days_covered, 1) if days_covered > 0 else 0
        }
    
    def get_optimal_times_for_day(self, day_name: str) -> List[Dict]:
        """Get optimal posting times for a specific day"""
        day_name = day_name.lower()
        return self.optimal_times.get(day_name, [])
    
    def is_optimal_time(self, target_datetime: datetime) -> Dict:
        """Check if a given time is optimal for posting"""
        day_name = target_datetime.strftime('%A').lower()
        target_hour = target_datetime.hour
        
        optimal_hours = [slot['hour'] for slot in self.optimal_times.get(day_name, [])]
        
        return {
            'is_optimal': target_hour in optimal_hours,
            'engagement_level': 'peak' if target_hour in [slot['hour'] for slot in self.optimal_times.get(day_name, []) if slot['engagement'] == 'peak'] else 'high' if target_hour in optimal_hours else 'low',
            'recommended_times': self.optimal_times.get(day_name, [])
        }
