#!/usr/bin/env python3
"""Database initialization script."""

import sqlite3
import os


DB_PATH = os.getenv('DB_PATH', '/app/data/queue.db')


def init_database():
    """Create database and tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create queue table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            vk_post_id INTEGER,
            status TEXT DEFAULT 'pending',
            posted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Create pending suggestions table (for moderation queue)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            user_id INTEGER,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_posted ON queue(posted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON queue(source)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON queue(file_hash)')
    
    # Insert default settings
    default_settings = [
        ('schedule_mode', 'fixed'),           # fixed or interval
        ('fixed_times', '06:00,15:00,22:00'), # comma-separated times (local timezone)
        ('interval_hours', '4'),              # hours between posts (if interval mode)
        ('posts_per_day', '3'),               # max posts per day (if interval mode)
        ('quiet_hours_start', '23'),          # don't post from this hour
        ('quiet_hours_end', '6'),             # until this hour
        ('timezone_offset', '7'),             # Krasnoyarsk = UTC+7
        ('photos_per_post', '6'),             # 1-10
        ('caption_text', ''),                 # text/link to add
        ('caption_mode', 'never'),            # never, always, every_n, once_daily
        ('caption_interval', '5'),            # every N posts (if every_n)
        ('inline_button_text', ''),           # button text (empty = no button)
        ('inline_button_url', ''),            # button URL
        ('post_order', 'priority'),           # priority or random
        ('notify_on_post', 'false'),          # notify admin after each post
        ('is_paused', 'false'),               # pause posting
        ('posts_today', '0'),                 # counter for today
        ('last_post_date', ''),               # date of last post
        ('caption_counter', '0'),             # counter for caption interval
    ]
    
    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")


if __name__ == '__main__':
    init_database()
