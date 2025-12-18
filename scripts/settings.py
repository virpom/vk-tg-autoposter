#!/usr/bin/env python3
"""Settings manager for bot configuration."""

import os
import sqlite3
from typing import Any, Optional
from datetime import datetime, timedelta

DB_PATH = os.getenv('DB_PATH', '/app/data/queue.db')


class Settings:
    """Settings manager with caching."""
    
    _cache: dict = {}
    _cache_time: datetime = None
    _cache_ttl: int = 60  # seconds
    
    @classmethod
    def _get_conn(cls):
        return sqlite3.connect(DB_PATH)
    
    @classmethod
    def _refresh_cache(cls):
        """Refresh cache from database."""
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        cls._cache = {row[0]: row[1] for row in cursor.fetchall()}
        cls._cache_time = datetime.now()
        conn.close()
    
    @classmethod
    def get(cls, key: str, default: str = '') -> str:
        """Get setting value."""
        # Refresh cache if stale
        if cls._cache_time is None or \
           (datetime.now() - cls._cache_time).seconds > cls._cache_ttl:
            cls._refresh_cache()
        
        return cls._cache.get(key, default)
    
    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Get setting as integer."""
        try:
            return int(cls.get(key, str(default)))
        except ValueError:
            return default
    
    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Get setting as boolean."""
        return cls.get(key, str(default).lower()) == 'true'
    
    @classmethod
    def set(cls, key: str, value: Any):
        """Set setting value."""
        conn = cls._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            (key, str(value))
        )
        conn.commit()
        conn.close()
        
        # Update cache
        cls._cache[key] = str(value)
    
    @classmethod
    def get_all(cls) -> dict:
        """Get all settings."""
        cls._refresh_cache()
        return cls._cache.copy()
    
    # Convenience methods
    
    @classmethod
    def get_fixed_times(cls) -> list:
        """Get list of fixed posting times as (hour, minute) tuples."""
        times_str = cls.get('fixed_times', '06:00,15:00,22:00')
        times = []
        for t in times_str.split(','):
            t = t.strip()
            if ':' in t:
                hour, minute = t.split(':')
                times.append((int(hour), int(minute)))
        return times
    
    @classmethod
    def set_fixed_times(cls, times: list):
        """Set fixed posting times from list of (hour, minute) tuples or strings."""
        if isinstance(times[0], tuple):
            times_str = ','.join(f'{h:02d}:{m:02d}' for h, m in times)
        else:
            times_str = ','.join(times)
        cls.set('fixed_times', times_str)
    
    @classmethod
    def is_quiet_hours(cls) -> bool:
        """Check if current time is in quiet hours."""
        tz_offset = cls.get_int('timezone_offset', 7)
        now = datetime.utcnow() + timedelta(hours=tz_offset)
        current_hour = now.hour
        
        start = cls.get_int('quiet_hours_start', 23)
        end = cls.get_int('quiet_hours_end', 6)
        
        if start > end:  # e.g., 23:00 to 06:00
            return current_hour >= start or current_hour < end
        else:  # e.g., 01:00 to 05:00
            return start <= current_hour < end
    
    @classmethod
    def is_paused(cls) -> bool:
        """Check if posting is paused."""
        return cls.get_bool('is_paused', False)
    
    @classmethod
    def should_add_caption(cls) -> bool:
        """Check if caption should be added to next post."""
        mode = cls.get('caption_mode', 'never')
        caption_text = cls.get('caption_text', '')
        
        if not caption_text or mode == 'never':
            return False
        
        if mode == 'always':
            return True
        
        if mode == 'every_n':
            counter = cls.get_int('caption_counter', 0)
            interval = cls.get_int('caption_interval', 5)
            return counter >= interval - 1
        
        if mode == 'once_daily':
            tz_offset = cls.get_int('timezone_offset', 7)
            today = (datetime.utcnow() + timedelta(hours=tz_offset)).strftime('%Y-%m-%d')
            last_caption_date = cls.get('last_caption_date', '')
            return last_caption_date != today
        
        return False
    
    @classmethod
    def increment_caption_counter(cls):
        """Increment caption counter and reset if needed."""
        mode = cls.get('caption_mode', 'never')
        
        if mode == 'every_n':
            counter = cls.get_int('caption_counter', 0) + 1
            interval = cls.get_int('caption_interval', 5)
            if counter >= interval:
                counter = 0
            cls.set('caption_counter', counter)
        
        elif mode == 'once_daily':
            tz_offset = cls.get_int('timezone_offset', 7)
            today = (datetime.utcnow() + timedelta(hours=tz_offset)).strftime('%Y-%m-%d')
            cls.set('last_caption_date', today)
    
    @classmethod
    def get_schedule_info(cls) -> str:
        """Get human-readable schedule info."""
        mode = cls.get('schedule_mode', 'fixed')
        tz_offset = cls.get_int('timezone_offset', 7)
        
        if mode == 'fixed':
            times = cls.get('fixed_times', '06:00,15:00,22:00')
            return f"📅 Фиксированное время: {times} (UTC+{tz_offset})"
        else:
            interval = cls.get_int('interval_hours', 4)
            # Calculate posts_per_day from interval and quiet hours
            quiet_start = cls.get_int('quiet_hours_start', 23)
            quiet_end = cls.get_int('quiet_hours_end', 6)
            if quiet_start <= quiet_end:
                quiet_duration = quiet_end - quiet_start
            else:
                quiet_duration = (24 - quiet_start) + quiet_end
            active_hours = 24 - quiet_duration
            posts_per_day = active_hours // interval
            return f"⏱ Интервал: каждые {interval}ч, ~{posts_per_day} постов/день"
    
    @classmethod
    def get_quiet_hours_info(cls) -> str:
        """Get human-readable quiet hours info."""
        start = cls.get_int('quiet_hours_start', 23)
        end = cls.get_int('quiet_hours_end', 6)
        return f"🌙 Тихие часы: {start:02d}:00 — {end:02d}:00"


# Default settings descriptions (for UI)
SETTINGS_INFO = {
    'schedule_mode': {
        'name': '📅 Режим расписания',
        'options': [('fixed', 'Фиксированное время'), ('interval', 'Интервал')],
    },
    'fixed_times': {
        'name': '⏰ Время постинга',
        'hint': 'Через запятую: 06:00,15:00,22:00',
    },
    'interval_hours': {
        'name': '⏱ Интервал (часы)',
        'hint': 'Число от 1 до 24',
    },
    'posts_per_day': {
        'name': '📊 Постов в день',
        'hint': 'Максимум постов за день',
    },
    'quiet_hours_start': {
        'name': '🌙 Тихие часы: начало',
        'hint': 'Час (0-23)',
    },
    'quiet_hours_end': {
        'name': '🌙 Тихие часы: конец',
        'hint': 'Час (0-23)',
    },
    'photos_per_post': {
        'name': '🖼 Фото в посте',
        'hint': 'От 1 до 10',
    },
    'caption_text': {
        'name': '✏️ Текст к посту',
        'hint': 'Текст или ссылка',
    },
    'caption_mode': {
        'name': '📝 Режим подписи',
        'options': [
            ('never', 'Никогда'),
            ('always', 'Всегда'),
            ('every_n', 'Каждый N-й пост'),
            ('once_daily', 'Раз в день'),
        ],
    },
    'caption_interval': {
        'name': '🔢 Интервал подписи',
        'hint': 'Каждые N постов',
    },
    'inline_button_text': {
        'name': '🔘 Текст кнопки',
        'hint': 'Оставьте пустым чтобы отключить',
    },
    'inline_button_url': {
        'name': '🔗 URL кнопки',
        'hint': 'Ссылка для кнопки',
    },
    'post_order': {
        'name': '🔀 Порядок постов',
        'options': [('priority', 'По приоритету'), ('random', 'Случайный')],
    },
    'notify_on_post': {
        'name': '🔔 Уведомления',
        'options': [('true', 'Включено'), ('false', 'Отключено')],
    },
}
