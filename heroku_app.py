#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update
)
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, 
    MessageHandler, filters, ConversationHandler
)
from telegram.error import Forbidden

# 配置日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

# Bot配置 - 從環境變數獲取或使用預設值
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'uplusluke')

# 全域變數
user_cooldowns = {}
pending_broadcast_data = {}

# 對話狀態
BROADCAST_MESSAGE, BROADCAST_BUTTONS, BROADCAST_CONFIRM = range(3)

class DatabaseManager:
    def __init__(self, db_path="bot_database.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """獲取資料庫連接"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """初始化資料庫"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 用戶表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # 影片表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    hashtags TEXT,
                    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    views INTEGER DEFAULT 0
                )
            ''')
            
            # 用戶行為表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action_type TEXT,
                    action_data TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 設定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # 群發日誌表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS broadcast_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    message_type TEXT,
                    content TEXT,
                    total_users INTEGER,
                    success_count INTEGER,
                    failed_count INTEGER,
                    broadcast_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 添加索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_hashtags ON videos(hashtags)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_user_id ON user_actions(user_id)')
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    def add_user(self, user_id, username=None, first_name=None, last_name=None):
        """添加或更新用戶"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding user: {e}")
    
    def log_action(self, user_id, action_type, action_data=None):
        """記錄用戶行為"""
        try:
            if action_type in ['start', 'search', 'random_video', 'sponsor_click']:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO user_actions (user_id, action_type, action_data)
                    VALUES (?, ?, ?)
                ''', (user_id, action_type, action_data))
                
                cursor.execute('''
                    UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?
                ''', (user_id,))
                
                conn.commit()
                conn.close()
        except Exception as e:
            logger.error(f"Error logging action: {e}")
    
    def get_setting(self, key):
        """獲取設定"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting setting: {e}")
            return None
    
    def set_setting(self, key, value):
        """設定配置"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
            ''', (key, value))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error setting config: {e}")
    
    def add_video(self, file_id, title, hashtags=None):
        """添加影片"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO videos (file_id, title, hashtags)
                VALUES (?, ?, ?)
            ''', (file_id, title, hashtags))
            
            video_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return video_id
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return None
    
    def delete_video(self, video_id):
        """刪除影片"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM videos WHERE id = ?', (video_id,))
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            return deleted
        except Exception as e:
            logger.error(f"Error deleting video: {e}")
            return False
    
    def search_videos(self, keyword):
        """搜尋影片"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, file_id, title, hashtags FROM videos
                WHERE title LIKE ? OR hashtags LIKE ?
                ORDER BY upload_time DESC LIMIT 20
            ''', (f'%{keyword}%', f'%{keyword}%'))
            
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error searching videos: {e}")
            return []
    
    def get_random_video(self):
        """獲取隨機影片"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, file_id, title, hashtags FROM videos ORDER BY RANDOM() LIMIT 1')
            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Error getting random video: {e}")
            return None
    
    def get_videos_page(self, page=1, per_page=10, hashtag=None):
        """分頁獲取影片列表"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            offset = (page - 1) * per_page
            
            if hashtag:
                cursor.execute('''
                    SELECT id, title, hashtags, upload_time FROM videos
                    WHERE hashtags LIKE ?
                    ORDER BY upload_time DESC LIMIT ? OFFSET ?
                ''', (f'%{hashtag}%', per_page, offset))
                
                results = cursor.fetchall()
                
                cursor.execute('SELECT COUNT(*) FROM videos WHERE hashtags LIKE ?', (f'%{hashtag}%',))
                total = cursor.fetchone()[0]
            else:
                cursor.execute('''
                    SELECT id, title, hashtags, upload_time FROM videos
                    ORDER BY upload_time DESC LIMIT ? OFFSET ?
                ''', (per_page, offset))
                
                results = cursor.fetchall()
                
                cursor.execute('SELECT COUNT(*) FROM videos')
                total = cursor.fetchone()[0]
            
            conn.close()
            return results, total
        except Exception as e:
            logger.error(f"Error getting videos page: {e}")
            return [], 0
    
    def get_all_hashtags(self):
        """獲取所有hashtag"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT DISTINCT hashtags FROM videos WHERE hashtags IS NOT NULL AND hashtags != ""')
            results = cursor.fetchall()
            
            hashtags = set()
            for row in results:
                if row[0]:
                    tags = re.findall(r'#\w+', row[0])
                    hashtags.update(tags)
            
            conn.close()
            return sorted(list(hashtags))
        except Exception as e:
            logger.error(f"Error getting hashtags: {e}")
            return []
    
    def get_user_stats(self):
        """獲取用戶統計"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN DATE(created_at) = DATE('now') THEN 1 ELSE 0 END) as today_new,
                    SUM(CASE WHEN DATE(last_active) = DATE('now') THEN 1 ELSE 0 END) as today_active,
                    SUM(CASE WHEN last_active >= DATE('now', '-7 days') THEN 1 ELSE 0 END) as week_active
                FROM users
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            return {
                'total_users': result[0],
                'today_new': result[1],
                'today_active': result[2],
                'week_active': result[3]
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {
                'total_users': 0,
                'today_new': 0,
                'today_active': 0,
                'week_active': 0
            }
    
    def get_all_active_users(self):
        """獲取所有活躍用戶ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM users WHERE is_active = 1')
            results = cursor.fetchall()
            conn.close()
            
            return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []
    
    def log_broadcast(self, admin_id, message_type, content, total_users, success_count, failed_count):
        """記錄群發日誌"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO broadcast_logs 
                (admin_id, message_type, content, total_users, success_count, failed_count, broadcast_time)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (admin_id, message_type, content, total_users, success_count, failed_count))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging broadcast: {e}")

# 初始化資料庫
db = DatabaseManager()

def is_admin(user):
    """檢查是否為管理員"""
    if not user:
        return False
    return user.username == ADMIN_USERNAME

def check_cooldown(user_id):
    """檢查冷卻時間"""
    current_time = time.time()
    if user_id in user_cooldowns:
        if current_time - user_cooldowns[user_id] < 3:
            return False
    user_cooldowns[user_id] = current_time
    return True

def parse_buttons(text):
    """解析按鈕格式"""
    buttons = []
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if '|' in line:
            parts = line.split('|', 1)
            if len(parts) == 2:
                button_text = parts[0].strip()
                button_url = parts[1].strip()
                if button_text and button_url:
                    buttons.append({
                        'text': button_text,
                        'url': button_url
                    })
    
    return buttons

def get_sponsor_buttons():
    """獲取贊助商按鈕"""
    sponsor_links = db.get_setting('sponsor_links') or ''
    return parse_buttons(sponsor_links)

# ===== 指令處理器 =====
async def start_handler(update: Update, context):
    """處理 /start 指令"""
    try:
        user = update.effective_user
        
        # 記錄用戶
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'start')
        
        # 獲取開始訊息配置
        start_config = db.get_setting('start_message_config')
        if start_config:
            try:
                config = json.loads(start_config)
                text = config.get('text', '🎬 歡迎使用看片機器人！')
                custom_buttons = config.get('buttons', [])
            except:
                text = '🎬 歡迎使用看片機器人！'
                custom_buttons = []
        else:
            text = '🎬 歡迎使用看片機器人！'
            custom_buttons = []
        
        # 建立按鈕
        keyboard = []
        
        # 添加自定義按鈕
        for button in custom_buttons:
            keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
        
        # 添加主要按鈕
        keyboard.append([InlineKeyboardButton("✅ 我已加入群組", callback_data="joined_groups")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in start_handler: {e}")

async def admin_handler(update: Update, context):
    """處理 /admin 指令"""
    try:
        user = update.effective_user
        
        if not is_admin(user):
            await update.message.reply_text("❌ 您沒有管理員權限")
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯訊息", callback_data="admin_edit_messages")],
            [InlineKeyboardButton("🎬 影片管理", callback_data="admin_video_management")],
            [InlineKeyboardButton("👥 用戶管理", callback_data="admin_user_management")],
            [InlineKeyboardButton("📊 發送訊息", callback_data="admin_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔐 管理員面板\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_handler: {e}")

# ===== 回調處理器 =====
async def joined_groups_callback(update: Update, context):
    """處理加入群組回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.log_action(user.id, 'joined_groups')
        
        keyboard = [
            [InlineKeyboardButton("🔍 搜尋影片", callback_data="search_videos")],
            [InlineKeyboardButton("🎲 隨機看片", callback_data="random_video")],
            [InlineKeyboardButton("📣 贊助商連結", callback_data="sponsor_links")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 歡迎使用看片機器人！\n\n請選擇您想要的功能：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in joined_groups_callback: {e}")

async def search_videos_callback(update: Update, context):
    """處理搜尋影片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "🔍 請輸入您想搜尋的關鍵字：",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Error in search_videos_callback: {e}")

async def random_video_callback(update: Update, context):
    """處理隨機看片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.log_action(user.id, 'random_video')
        
        video = db.get_random_video()
        if video:
            video_id, file_id, title, hashtags = video
            
            keyboard = [
                [InlineKeyboardButton("🎲 再來一部", callback_data="random_video")],
                [InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            caption = f"🎬 {title}"
            if hashtags:
                caption += f"\n\n{hashtags}"
            
            await query.message.reply_video(
                video=file_id,
                caption=caption,
                reply_markup=reply_markup
            )
            
            await query.delete_message()
        else:
            await query.edit_message_text(
                "😅 目前沒有可用的影片，請稍後再試。",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")
                ]])
            )
        
    except Exception as e:
        logger.error(f"Error in random_video_callback: {e}")

async def sponsor_links_callback(update: Update, context):
    """處理贊助商連結回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.log_action(user.id, 'sponsor_click')
        
        sponsor_buttons = get_sponsor_buttons()
        
        if sponsor_buttons:
            keyboard = []
            for button in sponsor_buttons:
                keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
            
            keyboard.append([InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📣 贊助商連結\n\n感謝您的支持！",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                "📣 目前沒有可用的贊助商連結。",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")
                ]])
            )
        
    except Exception as e:
        logger.error(f"Error in sponsor_links_callback: {e}")

# ===== 管理員功能處理器 =====
async def admin_edit_messages_callback(update: Update, context):
    """編輯訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯開始訊息", callback_data="edit_start_message")],
            [InlineKeyboardButton("📣 編輯贊助商連結", callback_data="edit_sponsor_links")],
            [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 編輯訊息\n\n請選擇要編輯的內容：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_edit_messages_callback: {e}")

async def admin_video_management_callback(update: Update, context):
    """影片管理回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("📤 上傳影片", callback_data="upload_video")],
            [InlineKeyboardButton("📋 影片列表", callback_data="video_list")],
            [InlineKeyboardButton("🏷️ 標籤管理", callback_data="hashtag_management")],
            [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 影片管理\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_video_management_callback: {e}")

async def admin_user_management_callback(update: Update, context):
    """用戶管理回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        stats = db.get_user_stats()
        
        text = f"""👥 用戶管理

📊 用戶統計：
• 總用戶數：{stats['total_users']}
• 今日新增：{stats['today_new']}
• 今日活躍：{stats['today_active']}
• 本週活躍：{stats['week_active']}"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in admin_user_management_callback: {e}")

async def admin_broadcast_callback(update: Update, context):
    """群發訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "📊 群發訊息\n\n請發送要群發的內容：",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消", callback_data="back_to_admin")
            ]])
        )
        
        return BROADCAST_MESSAGE
        
    except Exception as e:
        logger.error(f"Error in admin_broadcast_callback: {e}")

async def back_to_admin_callback(update: Update, context):
    """返回管理面板"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯訊息", callback_data="admin_edit_messages")],
            [InlineKeyboardButton("🎬 影片管理", callback_data="admin_video_management")],
            [InlineKeyboardButton("👥 用戶管理", callback_data="admin_user_management")],
            [InlineKeyboardButton("📊 發送訊息", callback_data="admin_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔐 管理員面板\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in back_to_admin_callback: {e}")

# ===== 群發功能 =====
async def broadcast_message_handler(update: Update, context):
    """處理群發訊息"""
    try:
        user = update.effective_user
        
        if not is_admin(user):
            return ConversationHandler.END
        
        message = update.message
        
        # 儲存群發內容
        pending_broadcast_data[user.id] = {
            'message': message,
            'buttons': []
        }
        
        keyboard = [
            [InlineKeyboardButton("✅ 直接發送", callback_data="broadcast_send")],
            [InlineKeyboardButton("🔘 添加按鈕", callback_data="broadcast_add_buttons")],
            [InlineKeyboardButton("❌ 取消", callback_data="broadcast_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            "📊 群發預覽\n\n您要如何處理這則訊息？",
            reply_markup=reply_markup
        )
        
        return BROADCAST_CONFIRM
        
    except Exception as e:
        logger.error(f"Error in broadcast_message_handler: {e}")
        return ConversationHandler.END

async def broadcast_send_callback(update: Update, context):
    """執行群發"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        if user.id not in pending_broadcast_data:
            await query.edit_message_text("❌ 沒有找到要群發的內容")
            return ConversationHandler.END
        
        broadcast_data = pending_broadcast_data[user.id]
        message = broadcast_data['message']
        buttons = broadcast_data.get('buttons', [])
        
        # 獲取所有用戶
        user_ids = db.get_all_active_users()
        
        if not user_ids:
            await query.edit_message_text("❌ 沒有找到活躍用戶")
            return ConversationHandler.END
        
        await query.edit_message_text(f"📊 開始群發給 {len(user_ids)} 位用戶...")
        
        success_count = 0
        failed_count = 0
        
        # 建立按鈕
        reply_markup = None
        if buttons:
            keyboard = []
            for button in buttons:
                keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 群發訊息
        for user_id in user_ids:
            try:
                if message.text:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message.text,
                        reply_markup=reply_markup
                    )
                elif message.photo:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=message.photo[-1].file_id,
                        caption=message.caption,
                        reply_markup=reply_markup
                    )
                elif message.video:
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=message.video.file_id,
                        caption=message.caption,
                        reply_markup=reply_markup
                    )
                
                success_count += 1
                await asyncio.sleep(0.1)  # 避免觸發限制
                
            except Forbidden:
                failed_count += 1
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                failed_count += 1
        
        # 記錄群發日誌
        message_type = "text"
        if message.photo:
            message_type = "photo"
        elif message.video:
            message_type = "video"
        
        content = message.text or message.caption or ""
        db.log_broadcast(user.id, message_type, content, len(user_ids), success_count, failed_count)
        
        # 清理暫存資料
        del pending_broadcast_data[user.id]
        
        result_text = f"""📊 群發完成！

✅ 成功發送：{success_count}
❌ 發送失敗：{failed_count}
📊 總用戶數：{len(user_ids)}"""
        
        await query.edit_message_text(result_text)
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in broadcast_send_callback: {e}")
        return ConversationHandler.END

async def broadcast_cancel_callback(update: Update, context):
    """取消群發"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        
        if user.id in pending_broadcast_data:
            del pending_broadcast_data[user.id]
        
        await query.edit_message_text("❌ 群發已取消")
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in broadcast_cancel_callback: {e}")
        return ConversationHandler.END

# ===== 訊息處理器 =====
async def text_message_handler(update: Update, context):
    """處理文字訊息"""
    try:
        user = update.effective_user
        message = update.message
        
        # 檢查冷卻時間
        if not check_cooldown(user.id):
            return
        
        # 搜尋影片
        keyword = message.text.strip()
        videos = db.search_videos(keyword)
        
        if videos:
            db.log_action(user.id, 'search', keyword)
            
            # 發送第一個搜尋結果
            video = videos[0]
            video_id, file_id, title, hashtags = video
            
            keyboard = [
                [InlineKeyboardButton("🔍 更多搜尋結果", callback_data=f"search_more_{keyword}")],
                [InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            caption = f"🔍 搜尋結果：{title}"
            if hashtags:
                caption += f"\n\n{hashtags}"
            
            await message.reply_video(
                video=file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🎲 隨機看片", callback_data="random_video")],
                [InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(
                f"😅 沒有找到與「{keyword}」相關的影片。\n\n要不要試試隨機看片？",
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error in text_message_handler: {e}")

async def video_message_handler(update: Update, context):
    """處理影片訊息（管理員上傳）"""
    try:
        user = update.effective_user
        
        if not is_admin(user):
            return
        
        message = update.message
        video = message.video
        
        if not video:
            return
        
        # 提取標題和hashtags
        caption = message.caption or ""
        title = caption.split('\n')[0] if caption else f"影片_{int(time.time())}"
        hashtags = ' '.join(re.findall(r'#\w+', caption))
        
        # 儲存影片
        video_id = db.add_video(video.file_id, title, hashtags)
        
        if video_id:
            await message.reply_text(f"✅ 影片已成功上傳！\n\n📝 標題：{title}\n🏷️ 標籤：{hashtags or '無'}")
        else:
            await message.reply_text("❌ 影片上傳失敗，請稍後再試。")
        
    except Exception as e:
        logger.error(f"Error in video_message_handler: {e}")

def main():
    """主函數"""
    try:
        # 創建應用
        application = Application.builder().token(BOT_TOKEN).build()
        
        # 群發對話處理器
        broadcast_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$")],
            states={
                BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message_handler)],
                BROADCAST_CONFIRM: [
                    CallbackQueryHandler(broadcast_send_callback, pattern="^broadcast_send$"),
                    CallbackQueryHandler(broadcast_cancel_callback, pattern="^broadcast_cancel$")
                ]
            },
            fallbacks=[CallbackQueryHandler(broadcast_cancel_callback, pattern="^broadcast_cancel$")]
        )
        
        # 添加處理器
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("admin", admin_handler))
        
        # 回調處理器
        application.add_handler(CallbackQueryHandler(joined_groups_callback, pattern="^joined_groups$"))
        application.add_handler(CallbackQueryHandler(search_videos_callback, pattern="^search_videos$"))
        application.add_handler(CallbackQueryHandler(random_video_callback, pattern="^random_video$"))
        application.add_handler(CallbackQueryHandler(sponsor_links_callback, pattern="^sponsor_links$"))
        
        # 管理員回調處理器
        application.add_handler(CallbackQueryHandler(admin_edit_messages_callback, pattern="^admin_edit_messages$"))
        application.add_handler(CallbackQueryHandler(admin_video_management_callback, pattern="^admin_video_management$"))
        application.add_handler(CallbackQueryHandler(admin_user_management_callback, pattern="^admin_user_management$"))
        application.add_handler(CallbackQueryHandler(back_to_admin_callback, pattern="^back_to_admin$"))
        
        # 群發處理器
        application.add_handler(broadcast_conv_handler)
        
        # 訊息處理器
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
        application.add_handler(MessageHandler(filters.VIDEO, video_message_handler))
        
        # 啟動Bot
        logger.warning("Bot starting...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == '__main__':
    main()
