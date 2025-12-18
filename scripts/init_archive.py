#!/usr/bin/env python3
"""Initialize archive: scan folder and add photos to database."""

import os
import sys
import hashlib
import sqlite3
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from database.init_db import DB_PATH, init_database


ARCHIVE_PATH = os.getenv('ARCHIVE_PATH', '/app/photos/archive')
SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic')


def calculate_hash(file_path):
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def scan_archive():
    """Scan archive folder and add photos to database."""
    if not os.path.exists(ARCHIVE_PATH):
        print(f"❌ Archive path does not exist: {ARCHIVE_PATH}")
        return
    
    # Ensure database exists
    init_database()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    added = 0
    skipped = 0
    errors = 0
    
    print(f"📂 Scanning archive: {ARCHIVE_PATH}")
    
    for root, dirs, files in os.walk(ARCHIVE_PATH):
        for filename in files:
            if not filename.lower().endswith(SUPPORTED_FORMATS):
                continue
            
            file_path = os.path.join(root, filename)
            
            try:
                # Calculate hash
                file_hash = calculate_hash(file_path)
                
                # Check if already in database
                cursor.execute('SELECT id FROM queue WHERE file_hash = ?', (file_hash,))
                if cursor.fetchone():
                    skipped += 1
                    continue
                
                # Add to database
                cursor.execute('''
                    INSERT INTO queue (file_path, file_hash, source, status)
                    VALUES (?, ?, 'archive', 'pending')
                ''', (file_path, file_hash))
                
                added += 1
                
                if added % 100 == 0:
                    print(f"  ⏳ Processed {added} photos...")
                    conn.commit()
                
            except Exception as e:
                print(f"  ⚠️  Error processing {filename}: {e}")
                errors += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Archive scan complete:")
    print(f"   Added: {added}")
    print(f"   Skipped (duplicates): {skipped}")
    print(f"   Errors: {errors}")


if __name__ == '__main__':
    scan_archive()
