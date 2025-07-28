#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot - Heroku Production Version
Optimized for Heroku deployment with environment variables
"""

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
    MessageHandler, filters
)
from telegram.error import Forbidden

# 配置日誌 - Heroku環境優化
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot配置 - 從環境變數讀取
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'uplusluke')
DATABASE_URL = os.environ.get('DATABASE_URL', 'bot_database.db')

# 全域變數
user_cooldowns = {}
pending_broadcast_data = {}

class DatabaseManager:
    def __init__(self, db_path=None):
        # Heroku環境下使用環境變數指定的資料庫
        self.db_path = db_path or DATABASE_URL
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
            
            # 添加索引以提高查詢性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_hashtags ON videos(hashtags)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_user_id ON user_actions(user_id)')
            
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
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
            # 只記錄重要行為，減少資料庫寫入
            if action_type in ['start', 'search', 'random_video', 'sponsor_click']:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO user_actions (user_id, action_type, action_data)
                    VALUES (?, ?, ?)
                ''', (user_id, action_type, action_data))
                
                # 更新用戶最後活躍時間
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
            
            # 使用單一查詢獲取所有統計數據
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
        logger.info(f"Start command from user {user.id} (@{user.username})")
        
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
        
        logger.info(f"Admin command from user {user.id}")
        
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

# ===== 管理員功能處理器 =====
async def admin_edit_messages_callback(update: Update, context):
    """編輯訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯開始訊息", callback_data="edit_start_message")],
            [InlineKeyboardButton("📋 編輯主選單", callback_data="edit_menu_message")],
            [InlineKeyboardButton("🔗 編輯贊助商連結", callback_data="edit_sponsor_links")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 編輯訊息功能\n\n請選擇要編輯的項目：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_edit_messages_callback: {e}")

async def admin_video_management_callback(update: Update, context):
    """影片管理回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📤 上傳影片", callback_data="upload_video")],
            [InlineKeyboardButton("🗑️ 刪除影片", callback_data="delete_video")],
            [InlineKeyboardButton("📋 影片列表", callback_data="video_list")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 影片管理功能\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_video_management_callback: {e}")

async def admin_user_management_callback(update: Update, context):
    """用戶管理回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        # 獲取用戶統計
        stats = db.get_user_stats()
        
        keyboard = [
            [InlineKeyboardButton("📊 詳細統計", callback_data="detailed_stats")],
            [InlineKeyboardButton("📥 導出用戶", callback_data="export_users")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👥 用戶管理\n\n"
            f"📊 統計數據：\n"
            f"• 總用戶數：{stats['total_users']}\n"
            f"• 今日新增：{stats['today_new']}\n"
            f"• 今日活躍：{stats['today_active']}\n"
            f"• 週活躍：{stats['week_active']}\n\n"
            f"請選擇操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_management_callback: {e}")

async def video_list_callback(update: Update, context):
    """影片列表回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        # 獲取影片統計
        videos, total = db.get_videos_page(page=1, per_page=50)
        hashtags = db.get_all_hashtags()
        
        keyboard = [
            [InlineKeyboardButton(f"📋 全部影片 ({total})", callback_data="show_all_videos")]
        ]
        
        # 添加hashtag分類
        for hashtag in hashtags[:10]:  # 限制顯示數量
            keyboard.append([InlineKeyboardButton(f"🏷️ {hashtag}", callback_data=f"show_hashtag_{hashtag[1:]}")])
        
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="admin_video_management")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 影片列表\n\n"
            f"總影片數：{total}\n"
            f"標籤分類：{len(hashtags)}個\n\n"
            f"請選擇查看方式：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in video_list_callback: {e}")

async def show_all_videos_callback(update: Update, context):
    """顯示所有影片"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        videos, total = db.get_videos_page(page=1, per_page=20)
        
        if not videos:
            await query.edit_message_text(
                "📋 影片列表\n\n❌ 目前沒有影片",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data="video_list")]])
            )
            return
        
        text = f"📋 全部影片 (共{total}部)\n\n"
        for i, (video_id, title, hashtags, upload_time) in enumerate(videos, 1):
            text += f"{i}. ID:{video_id} | {title}\n"
            if hashtags:
                text += f"   🏷️ {hashtags}\n"
            text += "\n"
        
        keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="video_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in show_all_videos_callback: {e}")

# ===== 群發功能處理器 =====
async def admin_broadcast_callback(update: Update, context):
    """群發訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        await query.edit_message_text(
            "📊 群發訊息\n\n"
            "請發送要群發的內容：\n"
            "• 支援文字訊息\n"
            "• 支援圖片（含文字說明）\n"
            "• 支援GIF動圖（含文字說明）\n"
            "• 支援影片（含文字說明）\n\n"
            "發送後可選擇是否添加按鈕。"
        )
        
        # 設定等待群發訊息狀態
        context.user_data['waiting_broadcast'] = True
        
    except Exception as e:
        logger.error(f"Error in admin_broadcast_callback: {e}")

async def handle_broadcast_message(update: Update, context):
    """處理群發訊息內容"""
    try:
        if not is_admin(update.effective_user):
            return
        
        # 檢查是否在等待群發訊息狀態
        if not context.user_data.get('waiting_broadcast'):
            return
        
        user_id = update.effective_user.id
        message = update.message
        
        # 儲存訊息資料
        broadcast_data = {
            'message_type': 'text',
            'content': '',
            'file_id': None,
            'caption': None
        }
        
        # 正確處理不同類型的訊息
        if message.text:
            broadcast_data['message_type'] = 'text'
            broadcast_data['content'] = message.text
        elif message.photo:
            broadcast_data['message_type'] = 'photo'
            broadcast_data['file_id'] = message.photo[-1].file_id
            broadcast_data['caption'] = message.caption or ''
            broadcast_data['content'] = f"圖片訊息: {message.caption or '無說明文字'}"
        elif message.animation:
            broadcast_data['message_type'] = 'animation'
            broadcast_data['file_id'] = message.animation.file_id
            broadcast_data['caption'] = message.caption or ''
            broadcast_data['content'] = f"GIF動圖: {message.caption or '無說明文字'}"
        elif message.video:
            broadcast_data['message_type'] = 'video'
            broadcast_data['file_id'] = message.video.file_id
            broadcast_data['caption'] = message.caption or ''
            broadcast_data['content'] = f"影片訊息: {message.caption or '無說明文字'}"
        else:
            await update.message.reply_text("❌ 不支援的訊息類型")
            return
        
        # 儲存到全域變數
        pending_broadcast_data[user_id] = broadcast_data
        
        # 清除等待狀態
        context.user_data['waiting_broadcast'] = False
        
        keyboard = [
            [InlineKeyboardButton("✅ 直接發送", callback_data="broadcast_send_now")],
            [InlineKeyboardButton("🔘 添加按鈕", callback_data="broadcast_add_buttons")],
            [InlineKeyboardButton("❌ 取消", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📊 群發訊息預覽\n\n"
            f"訊息類型：{broadcast_data['message_type']}\n"
            f"內容：{broadcast_data['content'][:100]}{'...' if len(broadcast_data['content']) > 100 else ''}\n\n"
            "請選擇操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_broadcast_message: {e}")

async def broadcast_add_buttons_callback(update: Update, context):
    """添加按鈕回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        await query.edit_message_text(
            "🔘 添加按鈕\n\n"
            "請發送按鈕設定，格式：\n"
            "按鈕文字 | 按鈕網址\n\n"
            "範例：\n"
            "官方網站 | https://example.com\n"
            "聯絡我們 | https://t.me/example\n\n"
            "每行一個按鈕："
        )
        
        # 設定等待按鈕狀態
        context.user_data['waiting_broadcast_buttons'] = True
        
    except Exception as e:
        logger.error(f"Error in broadcast_add_buttons_callback: {e}")

async def handle_broadcast_buttons(update: Update, context):
    """處理群發按鈕設定"""
    try:
        if not is_admin(update.effective_user):
            return
        
        # 檢查是否在等待按鈕狀態
        if not context.user_data.get('waiting_broadcast_buttons'):
            return
        
        user_id = update.effective_user.id
        button_text = update.message.text.strip()
        
        if user_id not in pending_broadcast_data:
            await update.message.reply_text("❌ 請重新開始群發流程")
            return
        
        buttons = parse_buttons(button_text)
        pending_broadcast_data[user_id]['buttons'] = buttons
        
        # 清除等待狀態
        context.user_data['waiting_broadcast_buttons'] = False
        
        keyboard = [
            [InlineKeyboardButton("✅ 確認發送", callback_data="broadcast_send_now")],
            [InlineKeyboardButton("❌ 取消", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        button_preview = ""
        if buttons:
            button_preview = "\n\n按鈕預覽：\n"
            for i, btn in enumerate(buttons, 1):
                button_preview += f"{i}. {btn['text']} → {btn['url']}\n"
        else:
            button_preview = "\n\n❌ 沒有有效的按鈕格式"
        
        await update.message.reply_text(
            f"📊 群發訊息最終預覽\n\n"
            f"訊息類型：{pending_broadcast_data[user_id]['message_type']}\n"
            f"內容：{pending_broadcast_data[user_id]['content'][:100]}{'...' if len(pending_broadcast_data[user_id]['content']) > 100 else ''}"
            f"{button_preview}\n"
            "確認發送嗎？",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_broadcast_buttons: {e}")

async def broadcast_send_now_callback(update: Update, context):
    """立即發送群發訊息"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        user_id = query.from_user.id
        
        if user_id not in pending_broadcast_data:
            await query.answer("❌ 沒有待發送的訊息", show_alert=True)
            return
        
        broadcast_data = pending_broadcast_data[user_id]
        active_users = db.get_all_active_users()
        
        if not active_users:
            await query.edit_message_text("❌ 沒有活躍用戶")
            return
        
        await query.edit_message_text(
            f"📊 開始群發訊息...\n\n"
            f"目標用戶：{len(active_users)} 人\n"
            f"發送進度：0/{len(active_users)}"
        )
        
        # 準備按鈕
        reply_markup = None
        if broadcast_data.get('buttons'):
            keyboard = []
            for button in broadcast_data['buttons']:
                keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 開始群發
        success_count = 0
        failed_count = 0
        
        for i, target_user_id in enumerate(active_users):
            try:
                if broadcast_data['message_type'] == 'text':
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=broadcast_data['content'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'photo':
                    await context.bot.send_photo(
                        chat_id=target_user_id,
                        photo=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'animation':
                    await context.bot.send_animation(
                        chat_id=target_user_id,
                        animation=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'video':
                    await context.bot.send_video(
                        chat_id=target_user_id,
                        video=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                
                success_count += 1
                
                # 每10個用戶更新一次進度
                if (i + 1) % 10 == 0 or i == len(active_users) - 1:
                    try:
                        await query.edit_message_text(
                            f"📊 群發進度\n\n"
                            f"目標用戶：{len(active_users)} 人\n"
                            f"發送進度：{i + 1}/{len(active_users)}\n"
                            f"成功：{success_count}\n"
                            f"失敗：{failed_count}"
                        )
                    except:
                        pass
                
                # 避免發送過快
                await asyncio.sleep(0.05)
                
            except Forbidden:
                # 用戶封鎖了機器人
                failed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to send to user {target_user_id}: {e}")
        
        # 記錄群發日誌
        db.log_broadcast(
            user_id, 
            broadcast_data['message_type'], 
            broadcast_data['content'][:500], 
            len(active_users), 
            success_count, 
            failed_count
        )
        
        # 清理暫存資料
        del pending_broadcast_data[user_id]
        context.user_data.clear()
        
        # 發送完成報告
        keyboard = [[InlineKeyboardButton("🔙 返回管理面板", callback_data="admin_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ 群發完成！\n\n"
            f"📊 發送統計：\n"
            f"• 目標用戶：{len(active_users)} 人\n"
            f"• 成功發送：{success_count} 人\n"
            f"• 發送失敗：{failed_count} 人\n"
            f"• 成功率：{success_count/len(active_users)*100:.1f}%",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast_send_now_callback: {e}")

# ===== 管理員回調處理器 =====
async def admin_main_callback(update: Update, context):
    """返回管理員主面板"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        # 清理所有狀態
        context.user_data.clear()
        user_id = query.from_user.id
        if user_id in pending_broadcast_data:
            del pending_broadcast_data[user_id]
        
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
        logger.error(f"Error in admin_main_callback: {e}")

# ===== 用戶端回調處理器 =====
async def joined_groups_callback(update: Update, context):
    """已加入群組回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        # 簡化主選單
        keyboard = [
            [InlineKeyboardButton("🔍 搜尋影片", callback_data="search_video")],
            [InlineKeyboardButton("🎲 隨機看片", callback_data="random_video")],
            [InlineKeyboardButton("📣 贊助商連結", callback_data="sponsor_link")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 主選單\n\n請選擇您想要的功能：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in joined_groups_callback: {e}")

async def search_video_callback(update: Update, context):
    """搜尋影片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not check_cooldown(user.id):
            await query.answer("⏰ 請等待3秒後再試", show_alert=True)
            return
        
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        await query.edit_message_text("🔍 請輸入搜尋關鍵字：")
        context.user_data['waiting_search'] = True
        
    except Exception as e:
        logger.error(f"Error in search_video_callback: {e}")

async def handle_search_keyword(update: Update, context):
    """處理搜尋關鍵字"""
    try:
        if not context.user_data.get('waiting_search'):
            return
        
        keyword = update.message.text.strip()
        user = update.effective_user
        
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'search', keyword)
        
        videos = db.search_videos(keyword)
        
        context.user_data['waiting_search'] = False
        
        if not videos:
            keyboard = [[InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"😔 沒有找到包含「{keyword}」的影片",
                reply_markup=reply_markup
            )
            return
        
        import random
        video = random.choice(videos)
        await send_video_message(update.message, video)
        
    except Exception as e:
        logger.error(f"Error in handle_search_keyword: {e}")

async def random_video_callback(update: Update, context):
    """隨機看片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not check_cooldown(user.id):
            await query.answer("⏰ 請等待3秒後再試", show_alert=True)
            return
        
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'random_video')
        
        video = db.get_random_video()
        if not video:
            keyboard = [[InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("😔 目前沒有可用的影片", reply_markup=reply_markup)
            return
        
        await send_video_message(query.message, video, edit_previous=True)
        
    except Exception as e:
        logger.error(f"Error in random_video_callback: {e}")

async def send_video_message(message, video, edit_previous=False):
    """發送影片訊息"""
    try:
        video_id, file_id, title, hashtags = video
        
        # 建立按鈕
        keyboard = [
            [InlineKeyboardButton("🎲 下一部", callback_data="next_video")],
            [InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")]
        ]
        
        # 添加贊助商按鈕
        sponsor_buttons = get_sponsor_buttons()
        for button in sponsor_buttons:
            keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"🎬 {title}\n"
        if hashtags:
            caption += f"🏷️ {hashtags}"
        
        if edit_previous:
            from telegram import InputMediaVideo
            await message.edit_media(
                media=InputMediaVideo(media=file_id, caption=caption),
                reply_markup=reply_markup
            )
        else:
            await message.reply_video(
                video=file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error in send_video_message: {e}")

async def next_video_callback(update: Update, context):
    """下一部影片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not check_cooldown(user.id):
            await query.answer("⏰ 請等待3秒後再試", show_alert=True)
            return
        
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        video = db.get_random_video()
        if not video:
            await query.answer("😔 目前沒有可用的影片", show_alert=True)
            return
        
        await send_video_message(query.message, video, edit_previous=True)
        
    except Exception as e:
        logger.error(f"Error in next_video_callback: {e}")

async def back_to_menu_callback(update: Update, context):
    """回到選單回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("🔍 搜尋影片", callback_data="search_video")],
            [InlineKeyboardButton("🎲 隨機看片", callback_data="random_video")],
            [InlineKeyboardButton("📣 贊助商連結", callback_data="sponsor_link")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 主選單\n\n請選擇您想要的功能：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in back_to_menu_callback: {e}")

async def sponsor_link_callback(update: Update, context):
    """贊助商連結回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'sponsor_click')
        
        sponsor_buttons = get_sponsor_buttons()
        
        keyboard = []
        for button in sponsor_buttons:
            keyboard.append([InlineKeyboardButton(button['text'], url=button['url'])])
        
        keyboard.append([InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📣 感謝您支持我們的贊助商！",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in sponsor_link_callback: {e}")

# ===== 回音處理器 =====
async def echo_handler(update: Update, context):
    """回音處理器（處理所有非指令訊息）"""
    try:
        user = update.effective_user
        
        # 檢查是否在群發流程中
        if context.user_data.get('waiting_broadcast'):
            await handle_broadcast_message(update, context)
            return
        
        # 檢查是否在群發按鈕流程中
        if context.user_data.get('waiting_broadcast_buttons'):
            await handle_broadcast_buttons(update, context)
            return
        
        # 檢查是否在搜尋流程中
        if context.user_data.get('waiting_search'):
            await handle_search_keyword(update, context)
            return
        
        # 一般回音（簡化版本）
        if update.message.text:
            text = update.message.text
            db.add_user(user.id, user.username, user.first_name, user.last_name)
            await update.message.reply_text(f"您說：{text}")
        
    except Exception as e:
        logger.error(f"Error in echo_handler: {e}")

async def main():
    """主函數 - Heroku環境優化"""
    logger.info("Starting Heroku production bot...")
    
    # 初始化預設設定
    if not db.get_setting('start_message_config'):
        db.set_setting('start_message_config', json.dumps({
            'text': "🎬 歡迎使用看片機器人！\n\n請先加入我們的贊助商群組：",
            'buttons': []
        }, ensure_ascii=False))
    
    if not db.get_setting('menu_message_config'):
        db.set_setting('menu_message_config', json.dumps({
            'text': "🎬 主選單\n\n請選擇您想要的功能："
        }, ensure_ascii=False))
    
    if not db.get_setting('sponsor_links'):
        db.set_setting('sponsor_links', '示例贊助商 | https://t.me/example')
    
    # 建立應用
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 基本指令
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("admin", admin_handler))
    
    # 用戶端回調處理器
    app.add_handler(CallbackQueryHandler(joined_groups_callback, pattern="^joined_groups$"))
    app.add_handler(CallbackQueryHandler(search_video_callback, pattern="^search_video$"))
    app.add_handler(CallbackQueryHandler(random_video_callback, pattern="^random_video$"))
    app.add_handler(CallbackQueryHandler(next_video_callback, pattern="^next_video$"))
    app.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(sponsor_link_callback, pattern="^sponsor_link$"))
    
    # 管理員回調處理器
    app.add_handler(CallbackQueryHandler(admin_main_callback, pattern="^admin_main$"))
    app.add_handler(CallbackQueryHandler(admin_edit_messages_callback, pattern="^admin_edit_messages$"))
    app.add_handler(CallbackQueryHandler(admin_video_management_callback, pattern="^admin_video_management$"))
    app.add_handler(CallbackQueryHandler(admin_user_management_callback, pattern="^admin_user_management$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(broadcast_add_buttons_callback, pattern="^broadcast_add_buttons$"))
    app.add_handler(CallbackQueryHandler(broadcast_send_now_callback, pattern="^broadcast_send_now$"))
    app.add_handler(CallbackQueryHandler(video_list_callback, pattern="^video_list$"))
    app.add_handler(CallbackQueryHandler(show_all_videos_callback, pattern="^show_all_videos$"))
    
    # 處理所有訊息（包括媒體）
    app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.ANIMATION | filters.VIDEO, 
        echo_handler
    ))
    
    # 啟動Bot
    logger.info("Bot is starting...")
    await app.initialize()
    await app.start()
    
    logger.info("Bot is running with polling...")
    await app.updater.start_polling()
    
    logger.info("Heroku production bot is now running!")
    
    # 保持運行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())

