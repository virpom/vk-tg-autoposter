#!/usr/bin/env python3
"""VK-TG Auto Poster Bot v2 - Button-based UI with setup wizard."""

import os
import sys
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, Defaults
)
from telegram.request import HTTPXRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

sys.path.append(str(Path(__file__).parent.parent))
from database.init_db import DB_PATH, init_database
from scripts.settings import Settings

# Config from env
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_CHANNEL_ID = os.getenv('TG_CHANNEL_ID', '')
TG_ADMIN_ID = int(os.getenv('TG_ADMIN_ID', '0'))
QUEUE_PATH = os.getenv('QUEUE_PATH', '/app/photos/queue')

scheduler = None
waiting_for = {}  # user_id -> {'type': 'setting_name', 'callback': 'menu_to_return'}


def calculate_hash(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def is_admin(user_id: int) -> bool:
    return user_id == TG_ADMIN_ID


def kb(buttons):
    """Helper to create keyboard."""
    return InlineKeyboardMarkup(buttons)


# ==================== MAIN MENU ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point - show main menu."""
    await show_main_menu(update.message, update.effective_user.id)


async def show_main_menu(message_or_query, user_id, edit=False):
    """Show main menu with buttons."""
    if is_admin(user_id):
        # Get stats
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM queue WHERE posted = 0')
        queue_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM queue WHERE posted = 1')
        posted_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM pending_suggestions')
        pending = cursor.fetchone()[0]
        conn.close()
        
        paused = "⏸" if Settings.is_paused() else "▶️"
        
        text = f"🤖 **VK-TG Auto Poster**\n\n"
        text += f"📦 В очереди: **{queue_count}**\n"
        text += f"✅ Опубликовано: **{posted_count}**\n"
        text += f"📬 Предложки: **{pending}**\n"
        text += f"Статус: {paused}\n"
        text += f"\n{Settings.get_schedule_info()}"
        
        buttons = [
            [InlineKeyboardButton("🚀 Опубликовать сейчас", callback_data="action:post_now")],
            [
                InlineKeyboardButton("👁 Превью", callback_data="action:preview"),
                InlineKeyboardButton("📊 Статистика", callback_data="action:stats"),
            ],
            [InlineKeyboardButton(f"📬 Предложки ({pending})", callback_data="menu:suggestions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings")],
            [
                InlineKeyboardButton("⏸ Пауза" if not Settings.is_paused() else "▶️ Продолжить", 
                                   callback_data="action:toggle_pause"),
            ],
        ]
    else:
        text = "👋 **Привет!**\n\nОтправь мне фото для предложки в канал."
        buttons = []
    
    if edit and hasattr(message_or_query, 'edit_text'):
        await message_or_query.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')
    elif hasattr(message_or_query, 'reply_text'):
        await message_or_query.reply_text(text, reply_markup=kb(buttons), parse_mode='Markdown')
    elif hasattr(message_or_query, 'message'):
        await message_or_query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


# ==================== SETTINGS MENU ====================

async def show_settings_menu(query):
    """Show settings menu."""
    text = "⚙️ **Настройки**\n\nВыберите категорию:"
    
    buttons = [
        [InlineKeyboardButton("📅 Расписание", callback_data="settings:schedule")],
        [InlineKeyboardButton("🖼 Посты", callback_data="settings:posts")],
        [InlineKeyboardButton("✏️ Подпись к постам", callback_data="settings:caption")],
        [InlineKeyboardButton("🔘 Кнопка под постом", callback_data="settings:button")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data="settings:notify")],
        [InlineKeyboardButton("🔧 Система", callback_data="settings:system")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_schedule_settings(query):
    """Schedule settings."""
    mode = Settings.get('schedule_mode', 'fixed')
    times = Settings.get('fixed_times', '06:00,15:00,22:00')
    interval = Settings.get('interval_hours', '4')
    quiet_start = Settings.get('quiet_hours_start', '23')
    quiet_end = Settings.get('quiet_hours_end', '6')
    tz = Settings.get('timezone_offset', '7')
    
    text = "📅 **Настройки расписания**\n\n"
    text += f"Режим: **{'Фиксированное время' if mode == 'fixed' else 'Интервал'}**\n"
    if mode == 'fixed':
        text += f"Время: **{times}**\n"
    else:
        text += f"Интервал: **каждые {interval}ч**\n"
    text += f"Тихие часы: **{quiet_start}:00 — {quiet_end}:00**\n"
    text += f"Часовой пояс: **UTC+{tz}**"
    
    buttons = [
        [
            InlineKeyboardButton("Фикс. время" + (" ✅" if mode == 'fixed' else ""), 
                               callback_data="set:schedule_mode:fixed"),
            InlineKeyboardButton("Интервал" + (" ✅" if mode == 'interval' else ""), 
                               callback_data="set:schedule_mode:interval"),
        ],
        [InlineKeyboardButton("⏰ Изменить время постинга", callback_data="input:fixed_times")],
        [InlineKeyboardButton("⏱ Изменить интервал (часы)", callback_data="input:interval_hours")],
        [InlineKeyboardButton("🌙 Тихие часы", callback_data="input:quiet_hours")],
        [InlineKeyboardButton("🌍 Часовой пояс (UTC+)", callback_data="input:timezone_offset")],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_posts_settings(query):
    """Posts settings."""
    photos = Settings.get('photos_per_post', '6')
    order = Settings.get('post_order', 'priority')
    
    text = "🖼 **Настройки постов**\n\n"
    text += f"Фото в посте: **{photos}**\n"
    text += f"Порядок: **{'По приоритету' if order == 'priority' else 'Случайный'}**\n\n"
    text += "_Приоритет: предложки → VK → архив_"
    
    buttons = [
        [
            InlineKeyboardButton("1", callback_data="set:photos_per_post:1"),
            InlineKeyboardButton("3", callback_data="set:photos_per_post:3"),
            InlineKeyboardButton("6", callback_data="set:photos_per_post:6"),
            InlineKeyboardButton("10", callback_data="set:photos_per_post:10"),
        ],
        [InlineKeyboardButton("✏️ Ввести своё число", callback_data="input:photos_per_post")],
        [
            InlineKeyboardButton("Приоритет" + (" ✅" if order == 'priority' else ""), 
                               callback_data="set:post_order:priority"),
            InlineKeyboardButton("Случайный" + (" ✅" if order == 'random' else ""), 
                               callback_data="set:post_order:random"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_caption_settings(query):
    """Caption settings."""
    mode = Settings.get('caption_mode', 'never')
    caption = Settings.get('caption_text', '') or '(не задан)'
    interval = Settings.get('caption_interval', '5')
    
    mode_names = {
        'never': 'Отключено', 
        'always': 'Всегда', 
        'every_n': f'Каждый {interval}-й пост', 
        'once_daily': 'Раз в день'
    }
    
    text = "✏️ **Подпись к постам**\n\n"
    text += f"Режим: **{mode_names.get(mode, mode)}**\n"
    text += f"Текст:\n`{caption[:100]}{'...' if len(caption) > 100 else ''}`\n\n"
    text += "_Поддерживается HTML: <b>жирный</b>, <a href='url'>ссылка</a>_"
    
    buttons = [
        [
            InlineKeyboardButton("Откл" + (" ✅" if mode == 'never' else ""), callback_data="set:caption_mode:never"),
            InlineKeyboardButton("Всегда" + (" ✅" if mode == 'always' else ""), callback_data="set:caption_mode:always"),
        ],
        [
            InlineKeyboardButton(f"Каждый N" + (" ✅" if mode == 'every_n' else ""), callback_data="set:caption_mode:every_n"),
            InlineKeyboardButton("1/день" + (" ✅" if mode == 'once_daily' else ""), callback_data="set:caption_mode:once_daily"),
        ],
        [InlineKeyboardButton("✏️ Изменить текст подписи", callback_data="input:caption_text")],
        [InlineKeyboardButton("🔢 Интервал N (каждый N-й пост)", callback_data="input:caption_interval")],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_button_settings(query):
    """Inline button settings."""
    btn_text = Settings.get('inline_button_text', '') or '(не задан)'
    btn_url = Settings.get('inline_button_url', '') or '(не задан)'
    
    enabled = bool(Settings.get('inline_button_text', ''))
    
    text = "🔘 **Кнопка под постом**\n\n"
    text += f"Статус: **{'Включена' if enabled else 'Отключена'}**\n"
    text += f"Текст: `{btn_text}`\n"
    text += f"URL: `{btn_url}`"
    
    buttons = [
        [InlineKeyboardButton("✏️ Текст кнопки", callback_data="input:inline_button_text")],
        [InlineKeyboardButton("🔗 URL кнопки", callback_data="input:inline_button_url")],
        [InlineKeyboardButton("🗑 Отключить кнопку", callback_data="set:inline_button_text:")],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_notify_settings(query):
    """Notification settings."""
    notify = Settings.get_bool('notify_on_post', False)
    
    text = "🔔 **Уведомления**\n\n"
    text += f"После каждого поста: **{'Да' if notify else 'Нет'}**"
    
    buttons = [
        [
            InlineKeyboardButton("Включить" + (" ✅" if notify else ""), callback_data="set:notify_on_post:true"),
            InlineKeyboardButton("Отключить" + (" ✅" if not notify else ""), callback_data="set:notify_on_post:false"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def show_system_settings(query):
    """System settings."""
    channel = TG_CHANNEL_ID or '(не задан)'
    admin = TG_ADMIN_ID or '(не задан)'
    vk_group = os.getenv('VK_GROUP_DOMAIN', 'не задан')
    
    text = "🔧 **Системные настройки**\n\n"
    text += f"Канал: `{channel}`\n"
    text += f"Админ ID: `{admin}`\n"
    text += f"VK паблик: `{vk_group}`\n\n"
    text += "_Для изменения отредактируйте .env файл и перезапустите бота_"
    
    buttons = [
        [InlineKeyboardButton("🔄 Обновить расписание", callback_data="action:reschedule")],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu:settings")],
    ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


# ==================== SUGGESTIONS ====================

async def show_suggestions_menu(query):
    """Show suggestions management."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM pending_suggestions')
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        text = "📬 **Предложки**\n\nНет ожидающих предложек."
        buttons = [[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]]
    else:
        text = f"📬 **Предложки: {count}**\n\nВыберите действие:"
        buttons = [
            [InlineKeyboardButton(f"👁 Просмотреть по одной", callback_data="sugg:view:0")],
            [InlineKeyboardButton("✅ Одобрить все", callback_data="sugg:approve_all")],
            [InlineKeyboardButton("❌ Отклонить все", callback_data="sugg:reject_all")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")],
        ]
    
    await query.message.edit_text(text, reply_markup=kb(buttons), parse_mode='Markdown')


async def view_suggestion_at(query, offset):
    """View suggestion at offset."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_path, username FROM pending_suggestions ORDER BY id LIMIT 1 OFFSET ?', (offset,))
    row = cursor.fetchone()
    cursor.execute('SELECT COUNT(*) FROM pending_suggestions')
    total = cursor.fetchone()[0]
    conn.close()
    
    if not row:
        await show_suggestions_menu(query)
        return
    
    sugg_id, file_path, username = row
    
    buttons = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"sugg:approve:{sugg_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"sugg:reject:{sugg_id}"),
        ],
        [
            InlineKeyboardButton("◀️", callback_data=f"sugg:view:{max(0, offset-1)}"),
            InlineKeyboardButton(f"{offset+1}/{total}", callback_data="noop"),
            InlineKeyboardButton("▶️", callback_data=f"sugg:view:{min(total-1, offset+1)}"),
        ],
        [InlineKeyboardButton("📬 К списку", callback_data="menu:suggestions")],
    ]
    
    if os.path.exists(file_path):
        try:
            await query.message.delete()
        except:
            pass
        await query.message.chat.send_photo(
            photo=open(file_path, 'rb'),
            caption=f"📸 От: @{username}" if username else "📸 Предложка",
            reply_markup=kb(buttons)
        )
    else:
        # File missing, delete from DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
        conn.commit()
        conn.close()
        await view_suggestion_at(query, offset)


async def approve_suggestion_by_id(query, sugg_id):
    """Approve suggestion by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM pending_suggestions WHERE id = ?', (sugg_id,))
    row = cursor.fetchone()
    
    if not row:
        try:
            await query.edit_message_caption(caption="❌ Не найдено")
        except:
            pass
        conn.close()
        return
    
    file_path = row[0]
    
    if not os.path.exists(file_path):
        cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
        conn.commit()
        try:
            await query.edit_message_caption(caption="❌ Файл не найден")
        except:
            pass
        conn.close()
        return
    
    file_hash = calculate_hash(file_path)
    
    # Check duplicate
    cursor.execute('SELECT id FROM queue WHERE file_hash = ?', (file_hash,))
    if cursor.fetchone():
        cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
        conn.commit()
        os.remove(file_path)
        try:
            await query.edit_message_caption(caption="⚠️ Дубликат")
        except:
            pass
        conn.close()
        return
    
    # Add to queue
    cursor.execute('''
        INSERT INTO queue (file_path, file_hash, source, status)
        VALUES (?, ?, 'suggestion', 'approved')
    ''', (file_path, file_hash))
    cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
    conn.commit()
    conn.close()
    
    try:
        await query.edit_message_caption(caption="✅ Одобрено и добавлено в очередь!")
    except:
        pass


async def reject_suggestion_by_id(query, sugg_id):
    """Reject suggestion by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM pending_suggestions WHERE id = ?', (sugg_id,))
    row = cursor.fetchone()
    
    if row and os.path.exists(row[0]):
        os.remove(row[0])
    
    cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
    conn.commit()
    conn.close()
    
    try:
        await query.edit_message_caption(caption="❌ Отклонено")
    except:
        pass


async def approve_all_suggestions(query):
    """Approve all."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_path FROM pending_suggestions')
    suggestions = cursor.fetchall()
    
    approved = 0
    skipped = 0
    
    for sugg_id, file_path in suggestions:
        if not os.path.exists(file_path):
            cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
            skipped += 1
            continue
        
        file_hash = calculate_hash(file_path)
        cursor.execute('SELECT id FROM queue WHERE file_hash = ?', (file_hash,))
        if cursor.fetchone():
            cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
            os.remove(file_path)
            skipped += 1
            continue
        
        cursor.execute('''
            INSERT INTO queue (file_path, file_hash, source, status)
            VALUES (?, ?, 'suggestion', 'approved')
        ''', (file_path, file_hash))
        cursor.execute('DELETE FROM pending_suggestions WHERE id = ?', (sugg_id,))
        approved += 1
    
    conn.commit()
    conn.close()
    
    await query.message.edit_text(
        f"✅ Одобрено: {approved}\n⏭ Пропущено (дубли): {skipped}",
        reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])
    )


async def reject_all_suggestions(query):
    """Reject all."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM pending_suggestions')
    for row in cursor.fetchall():
        if os.path.exists(row[0]):
            os.remove(row[0])
    cursor.execute('DELETE FROM pending_suggestions')
    conn.commit()
    conn.close()
    
    await query.message.edit_text(
        "❌ Все предложки отклонены",
        reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])
    )


# ==================== ACTIONS ====================

async def do_post_now(query, context):
    """Post now."""
    await query.message.edit_text("🚀 Публикую...")
    
    count = Settings.get_int('photos_per_post', 6)
    photos = await get_next_photos(count)
    
    if not photos:
        await query.message.edit_text(
            "📭 Очередь пуста",
            reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])
        )
        return
    
    success = await do_post(context.bot, photos)
    
    if success:
        await query.message.edit_text(
            f"✅ Опубликовано {len(photos)} фото!",
            reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])
        )
    else:
        await query.message.edit_text(
            "❌ Ошибка публикации. Проверьте права бота в канале.",
            reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]])
        )


async def do_preview(query):
    """Show preview."""
    count = Settings.get_int('photos_per_post', 6)
    photos = await get_next_photos(count)
    
    if not photos:
        await query.answer("📭 Очередь пуста", show_alert=True)
        return
    
    media_group = []
    sources = []
    for i, (photo_id, file_path, source) in enumerate(photos):
        if os.path.exists(file_path):
            sources.append(source)
            caption_text = None
            if i == 0:
                # Show caption preview if enabled
                if Settings.should_add_caption():
                    caption_text = Settings.get('caption_text', '')[:200]
            media_group.append(InputMediaPhoto(media=open(file_path, 'rb'), caption=caption_text, parse_mode='HTML'))
    
    if media_group:
        source_str = ', '.join(set(sources))
        await query.message.reply_text(f"👁 **Превью** ({len(media_group)} фото из: {source_str}):", parse_mode='Markdown')
        await query.message.reply_media_group(media=media_group)


async def do_stats(query):
    """Show detailed stats."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT source, COUNT(*) FROM queue WHERE posted = 0 GROUP BY source')
    pending = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) FROM queue WHERE posted = 1')
    posted = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM queue')
    total = cursor.fetchone()[0]
    
    conn.close()
    
    text = "📊 **Подробная статистика**\n\n"
    text += "**В очереди:**\n"
    queue_total = 0
    for source, cnt in pending:
        emoji = {'suggestion': '💡', 'vk': '🔵', 'archive': '📂'}.get(source, '❓')
        text += f"  {emoji} {source}: {cnt}\n"
        queue_total += cnt
    
    text += f"\n**Всего в очереди:** {queue_total}\n"
    text += f"**Опубликовано:** {posted}\n"
    text += f"**Всего в базе:** {total}\n"
    
    # Days remaining
    photos_per_post = Settings.get_int('photos_per_post', 6)
    mode = Settings.get('schedule_mode', 'fixed')
    if mode == 'fixed':
        posts_per_day = len(Settings.get_fixed_times())
    else:
        posts_per_day = Settings.get_int('posts_per_day', 3)
    
    photos_per_day = photos_per_post * posts_per_day
    if photos_per_day > 0 and queue_total > 0:
        days = queue_total // photos_per_day
        text += f"\n📅 **Контента на ~{days} дней**"
    
    await query.message.edit_text(
        text,
        reply_markup=kb([[InlineKeyboardButton("◀️ Главное меню", callback_data="menu:main")]]),
        parse_mode='Markdown'
    )


# ==================== POSTING LOGIC ====================

async def get_next_photos(count: int) -> list:
    """Get next photos."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    order = Settings.get('post_order', 'priority')
    
    if order == 'random':
        cursor.execute('''
            SELECT id, file_path, source FROM queue
            WHERE posted = 0 AND status IN ('pending', 'approved')
            ORDER BY RANDOM()
            LIMIT ?
        ''', (count,))
    else:
        cursor.execute('''
            SELECT id, file_path, source FROM queue
            WHERE posted = 0 AND status IN ('pending', 'approved')
            ORDER BY 
                CASE source 
                    WHEN 'suggestion' THEN 1
                    WHEN 'vk' THEN 2
                    WHEN 'archive' THEN 3
                END,
                created_at ASC
            LIMIT ?
        ''', (count,))
    
    photos = cursor.fetchall()
    conn.close()
    return photos


async def do_post(bot, photos) -> bool:
    """Actually post photos to channel."""
    print(f"📤 do_post called with {len(photos) if photos else 0} photos")
    
    if not photos:
        print("❌ No photos provided")
        return False
    
    media_group = []
    photo_ids = []
    
    # Caption
    caption = None
    if Settings.should_add_caption():
        caption = Settings.get('caption_text', '')
        Settings.increment_caption_counter()
    
    for i, (photo_id, file_path, source) in enumerate(photos):
        print(f"  📷 Photo {i}: {file_path} (exists: {os.path.exists(file_path)})")
        if not os.path.exists(file_path):
            continue
        photo_caption = caption if i == 0 and caption else None
        media_group.append(InputMediaPhoto(
            media=open(file_path, 'rb'), 
            caption=photo_caption,
            parse_mode='HTML'
        ))
        photo_ids.append(photo_id)
    
    if not media_group:
        print("❌ No valid media files found")
        return False
    
    print(f"📦 Sending {len(media_group)} photos to {TG_CHANNEL_ID}")
    
    try:
        await bot.send_media_group(chat_id=TG_CHANNEL_ID, media=media_group)
        
        # Inline button
        btn_text = Settings.get('inline_button_text', '')
        btn_url = Settings.get('inline_button_url', '')
        if btn_text and btn_url:
            await bot.send_message(
                chat_id=TG_CHANNEL_ID,
                text="​",  # Zero-width space
                reply_markup=kb([[InlineKeyboardButton(btn_text, url=btn_url)]])
            )
        
        # Mark posted
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(photo_ids))
        cursor.execute(f'UPDATE queue SET posted = 1 WHERE id IN ({placeholders})', photo_ids)
        conn.commit()
        conn.close()
        
        # Notify admin
        if Settings.get_bool('notify_on_post', False):
            try:
                await bot.send_message(chat_id=TG_ADMIN_ID, text=f"✅ Опубликовано {len(photo_ids)} фото")
            except:
                pass
        
        print(f"✅ Posted {len(photo_ids)} photos")
        return True
        
    except Exception as e:
        import traceback
        print(f"❌ Error posting: {e}")
        traceback.print_exc()
        return False


async def scheduled_post(context):
    """Scheduled posting."""
    if Settings.is_paused():
        print("⏸ Paused, skipping")
        return
    
    if Settings.is_quiet_hours():
        print("🌙 Quiet hours, skipping")
        return
    
    count = Settings.get_int('photos_per_post', 6)
    photos = await get_next_photos(count)
    
    if photos:
        await do_post(context.bot, photos)
    else:
        print("⚠️ No photos in queue")


# ==================== PHOTO HANDLER ====================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photo."""
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    
    file = await context.bot.get_file(photo.file_id)
    filename = f"suggestion_{user_id}_{int(datetime.now().timestamp())}.jpg"
    save_path = os.path.join(QUEUE_PATH, filename)
    
    os.makedirs(QUEUE_PATH, exist_ok=True)
    await file.download_to_drive(save_path)
    
    # Save to pending
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO pending_suggestions (file_path, user_id, username) VALUES (?, ?, ?)',
        (save_path, user_id, update.effective_user.username)
    )
    sugg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Notify admin
    buttons = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"sugg:approve:{sugg_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"sugg:reject:{sugg_id}"),
        ]
    ]
    
    username = update.effective_user.username or update.effective_user.first_name
    await context.bot.send_photo(
        chat_id=TG_ADMIN_ID,
        photo=open(save_path, 'rb'),
        caption=f"📸 Предложка от @{username}",
        reply_markup=kb(buttons)
    )
    
    await update.message.reply_text("✅ Фото отправлено на модерацию!")


# ==================== TEXT INPUT HANDLER ====================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for settings."""
    user_id = update.effective_user.id
    
    if user_id not in waiting_for:
        return
    
    wait_info = waiting_for.pop(user_id)
    key = wait_info['type']
    value = update.message.text.strip()
    
    # Special handling
    if key == 'quiet_hours' and '-' in value:
        start, end = value.split('-')
        Settings.set('quiet_hours_start', start.strip())
        Settings.set('quiet_hours_end', end.strip())
    elif key == 'photos_per_post':
        try:
            val = int(value)
            if 1 <= val <= 10:
                Settings.set(key, str(val))
            else:
                await update.message.reply_text("❌ Введите число от 1 до 10")
                return
        except:
            await update.message.reply_text("❌ Введите число")
            return
    else:
        Settings.set(key, value)
    
    # Reschedule if needed
    if key in ('fixed_times', 'interval_hours', 'schedule_mode', 'timezone_offset'):
        await reschedule(context.application)
    
    await update.message.reply_text("✅ Сохранено!")
    
    # Show menu
    buttons = [[InlineKeyboardButton("◀️ К настройкам", callback_data="menu:settings")]]
    await update.message.reply_text("Продолжить?", reply_markup=kb(buttons))


# ==================== CALLBACK ROUTER ====================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback router."""
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    if not is_admin(user_id) and not data.startswith("noop"):
        await query.answer("⛔ Только для админа", show_alert=True)
        return
    
    await query.answer()
    
    # Menu navigation
    if data == "menu:main":
        await show_main_menu(query, user_id, edit=True)
    elif data == "menu:settings":
        await show_settings_menu(query)
    elif data == "menu:suggestions":
        await show_suggestions_menu(query)
    
    # Settings submenus
    elif data == "settings:schedule":
        await show_schedule_settings(query)
    elif data == "settings:posts":
        await show_posts_settings(query)
    elif data == "settings:caption":
        await show_caption_settings(query)
    elif data == "settings:button":
        await show_button_settings(query)
    elif data == "settings:notify":
        await show_notify_settings(query)
    elif data == "settings:system":
        await show_system_settings(query)
    
    # Direct setting
    elif data.startswith("set:"):
        _, key, value = data.split(":", 2)
        Settings.set(key, value)
        
        if key in ('schedule_mode', 'fixed_times', 'interval_hours', 'timezone_offset'):
            await reschedule(context.application)
        
        # Refresh menu
        if key == 'schedule_mode' or key.startswith('quiet') or key == 'interval_hours' or key == 'timezone_offset':
            await show_schedule_settings(query)
        elif key in ('photos_per_post', 'post_order'):
            await show_posts_settings(query)
        elif key.startswith('caption'):
            await show_caption_settings(query)
        elif key.startswith('inline_button'):
            await show_button_settings(query)
        elif key == 'notify_on_post':
            await show_notify_settings(query)
        else:
            await show_settings_menu(query)
    
    # Input request
    elif data.startswith("input:"):
        key = data.split(":")[1]
        waiting_for[user_id] = {'type': key}
        
        hints = {
            'fixed_times': 'Введите время постинга через запятую:\n\nПример: `06:00,15:00,22:00`',
            'interval_hours': 'Введите интервал в часах (1-24):',
            'quiet_hours': 'Введите тихие часы:\n\nФормат: `начало-конец`\nПример: `23-6`',
            'timezone_offset': 'Введите часовой пояс (число):\n\nКрасноярск = 7\nМосква = 3',
            'photos_per_post': 'Введите количество фото в посте (1-10):',
            'caption_text': 'Введите текст подписи:\n\nПоддерживается HTML:\n`<b>жирный</b>`\n`<a href="url">ссылка</a>`',
            'caption_interval': 'Введите интервал (каждые N постов):',
            'inline_button_text': 'Введите текст кнопки:',
            'inline_button_url': 'Введите URL кнопки:',
        }
        
        await query.message.edit_text(
            f"✏️ **Введите значение**\n\n{hints.get(key, 'Введите значение:')}",
            parse_mode='Markdown'
        )
    
    # Actions
    elif data == "action:post_now":
        await do_post_now(query, context)
    elif data == "action:preview":
        await do_preview(query)
    elif data == "action:stats":
        await do_stats(query)
    elif data == "action:toggle_pause":
        paused = Settings.is_paused()
        Settings.set('is_paused', 'false' if paused else 'true')
        await show_main_menu(query, user_id, edit=True)
    elif data == "action:reschedule":
        await reschedule(context.application)
        await query.answer("✅ Расписание обновлено", show_alert=True)
    
    # Suggestions
    elif data.startswith("sugg:view:"):
        offset = int(data.split(":")[2])
        await view_suggestion_at(query, offset)
    elif data.startswith("sugg:approve:"):
        sugg_id = int(data.split(":")[2])
        await approve_suggestion_by_id(query, sugg_id)
    elif data.startswith("sugg:reject:"):
        sugg_id = int(data.split(":")[2])
        await reject_suggestion_by_id(query, sugg_id)
    elif data == "sugg:approve_all":
        await approve_all_suggestions(query)
    elif data == "sugg:reject_all":
        await reject_all_suggestions(query)
    
    elif data == "noop":
        pass


# ==================== SCHEDULER ====================

async def reschedule(app):
    """Reschedule posting jobs."""
    global scheduler
    
    # Remove existing
    for job in scheduler.get_jobs():
        if job.id.startswith('posting'):
            job.remove()
    
    mode = Settings.get('schedule_mode', 'fixed')
    tz_offset = Settings.get_int('timezone_offset', 7)
    
    if mode == 'fixed':
        times = Settings.get_fixed_times()
        for hour, minute in times:
            utc_hour = (hour - tz_offset) % 24
            scheduler.add_job(
                scheduled_post,
                CronTrigger(hour=utc_hour, minute=minute),
                args=[app],
                id=f'posting_{hour}_{minute}'
            )
            print(f"📅 Scheduled: {hour:02d}:{minute:02d} local = {utc_hour:02d}:{minute:02d} UTC")
    else:
        interval = Settings.get_int('interval_hours', 4)
        scheduler.add_job(
            scheduled_post,
            IntervalTrigger(hours=interval),
            args=[app],
            id='posting_interval'
        )
        print(f"⏱ Scheduled: every {interval} hours")


def main():
    global scheduler
    
    if not TG_BOT_TOKEN:
        print("❌ TG_BOT_TOKEN not set")
        return
    
    init_database()
    
    # Increase timeout for large file uploads
    request = HTTPXRequest(
        read_timeout=60,
        write_timeout=60,
        connect_timeout=30,
    )
    
    app = Application.builder().token(TG_BOT_TOKEN).request(request).build()
    
    # Handlers
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Scheduler
    scheduler = AsyncIOScheduler()
    
    mode = Settings.get('schedule_mode', 'fixed')
    tz_offset = Settings.get_int('timezone_offset', 7)
    
    if mode == 'fixed':
        for hour, minute in Settings.get_fixed_times():
            utc_hour = (hour - tz_offset) % 24
            scheduler.add_job(
                scheduled_post,
                CronTrigger(hour=utc_hour, minute=minute),
                args=[app],
                id=f'posting_{hour}_{minute}'
            )
            print(f"📅 Scheduled: {hour:02d}:{minute:02d} local")
    else:
        interval = Settings.get_int('interval_hours', 4)
        scheduler.add_job(
            scheduled_post,
            IntervalTrigger(hours=interval),
            args=[app],
            id='posting_interval'
        )
        print(f"⏱ Scheduled: every {interval}h")
    
    scheduler.start()
    
    print(f"✅ Bot started")
    print(f"   Channel: {TG_CHANNEL_ID}")
    print(f"   Admin: {TG_ADMIN_ID}")
    
    app.run_polling()


if __name__ == '__main__':
    main()
