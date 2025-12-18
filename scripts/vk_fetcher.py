#!/usr/bin/env python3
"""Fetch new photos from VK group wall."""

import os
import sys
import time
import hashlib
import sqlite3
import requests
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from database.init_db import DB_PATH, init_database


VK_TOKEN = os.getenv('VK_TOKEN')
VK_GROUP_DOMAIN = os.getenv('VK_GROUP_DOMAIN', 'kot9ta_strah')
VK_API_VERSION = '5.131'
QUEUE_PATH = os.getenv('QUEUE_PATH', '/app/photos/queue')


def calculate_hash(file_path):
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def vk_api_request(method, params):
    """Make VK API request."""
    url = f'https://api.vk.com/method/{method}'
    params['access_token'] = VK_TOKEN
    params['v'] = VK_API_VERSION
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if 'error' in data:
        raise Exception(f"VK API error: {data['error']['error_msg']}")
    
    return data['response']


def download_photo(url, save_path):
    """Download photo from URL."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def fetch_vk_posts():
    """Fetch new posts from VK group wall."""
    if not VK_TOKEN:
        print("❌ VK_TOKEN not set")
        return
    
    # Ensure database and queue folder exist
    init_database()
    os.makedirs(QUEUE_PATH, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"🔍 Fetching posts from VK: {VK_GROUP_DOMAIN}")
    
    try:
        # Get latest 20 posts
        posts = vk_api_request('wall.get', {
            'domain': VK_GROUP_DOMAIN,
            'count': 20,
            'offset': 0
        })
        
        added = 0
        skipped = 0
        
        for post in posts['items']:
            post_id = post['id']
            
            # Check if we already processed this post
            cursor.execute('SELECT id FROM queue WHERE vk_post_id = ?', (post_id,))
            if cursor.fetchone():
                skipped += 1
                continue
            
            # Extract photos
            if 'attachments' not in post:
                continue
            
            for attachment in post['attachments']:
                if attachment['type'] != 'photo':
                    continue
                
                photo = attachment['photo']
                
                # Get highest quality photo URL
                photo_url = None
                for size_key in ['orig', 'w', 'z', 'y', 'x', 'm', 's']:
                    if size_key in photo['sizes'][-1]:
                        photo_url = photo['sizes'][-1]['url']
                        break
                
                if not photo_url:
                    # Fallback: get largest available size
                    photo_url = max(photo['sizes'], key=lambda x: x.get('width', 0) * x.get('height', 0))['url']
                
                # Download photo
                filename = f"vk_{post_id}_{photo['id']}.jpg"
                save_path = os.path.join(QUEUE_PATH, filename)
                
                try:
                    download_photo(photo_url, save_path)
                    
                    # Calculate hash
                    file_hash = calculate_hash(save_path)
                    
                    # Check if this exact file already exists
                    cursor.execute('SELECT id FROM queue WHERE file_hash = ?', (file_hash,))
                    if cursor.fetchone():
                        # Duplicate found, remove downloaded file
                        os.remove(save_path)
                        skipped += 1
                        continue
                    
                    # Add to database
                    cursor.execute('''
                        INSERT INTO queue (file_path, file_hash, source, vk_post_id, status)
                        VALUES (?, ?, 'vk', ?, 'pending')
                    ''', (save_path, file_hash, post_id))
                    
                    added += 1
                    print(f"  ✅ Added: {filename}")
                    
                except Exception as e:
                    print(f"  ⚠️  Error downloading {filename}: {e}")
                    if os.path.exists(save_path):
                        os.remove(save_path)
        
        conn.commit()
        print(f"\n✅ VK fetch complete: added {added}, skipped {skipped}")
        
    except Exception as e:
        print(f"❌ Error fetching VK posts: {e}")
    
    finally:
        conn.close()


if __name__ == '__main__':
    fetch_vk_posts()
