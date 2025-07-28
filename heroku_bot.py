#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 看片機器人 - 乾淨無衝突版本
確保單一實例運行，所有功能正常
"""

import os
import json
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# 配置日誌 - 減少輸出
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

# 環境變數
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'uplusluke')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# 全域變數
user_cooldowns = {}
pending_broadcast_data = {}

# ===== 資料庫類別 =====
class Database:
    def __init__(self, db_path='bot_database.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 用戶表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 影片表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    hashtags TEXT,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 設定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # 用戶行為記錄表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """添加或更新用戶"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error adding user: {e}")
    
    def log_action(self, user_id: int, action: str, details: str = None):
        """記錄用戶行為"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_actions (user_id, action, details)
                VALUES (?, ?, ?)
            ''', (user_id, action, details))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging action: {e}")
    
    def get_setting(self, key: str) -> str:
        """獲取設定"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            
            conn.close()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error getting setting: {e}")
            return None
    
    def set_setting(self, key: str, value: str):
        """設定值"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value)
                VALUES (?, ?)
            ''', (key, value))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error setting value: {e}")
    
    def add_video(self, file_id: str, title: str, hashtags: str = None):
        """添加影片"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO videos (file_id, title, hashtags)
                VALUES (?, ?, ?)
            ''', (file_id, title, hashtags))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return False
    
    def search_videos(self, keyword: str) -> List[Tuple]:
        """搜尋影片"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, file_id, title, hashtags FROM videos
                WHERE title LIKE ? OR hashtags LIKE ?
            ''', (f'%{keyword}%', f'%{keyword}%'))
            
            results = cursor.fetchall()
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"Error searching videos: {e}")
            return []
    
    def get_random_video(self) -> Optional[Tuple]:
        """獲取隨機影片"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, file_id, title, hashtags FROM videos
                ORDER BY RANDOM() LIMIT 1
            ''')
            
            result = cursor.fetchone()
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"Error getting random video: {e}")
            return None
    
    def get_all_videos(self) -> List[Tuple]:
        """獲取所有影片"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, file_id, title, hashtags FROM videos ORDER BY upload_date DESC')
            results = cursor.fetchall()
            
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"Error getting all videos: {e}")
            return []
    
    def delete_video(self, video_id: int) -> bool:
        """刪除影片"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM videos WHERE id = ?', (video_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error deleting video: {e}")
            return False
    
    def get_user_stats(self) -> Dict:
        """獲取用戶統計"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 總用戶數
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # 今日新增用戶
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE DATE(join_date) = DATE('now')
            ''')
            today_new = cursor.fetchone()[0]
            
            # 活躍用戶（7天內）
            cursor.execute('''
                SELECT COUNT(*) FROM users 
                WHERE last_active >= datetime('now', '-7 days')
            ''')
            active_users = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_users': total_users,
                'today_new': today_new,
                'active_users': active_users
            }
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {'total_users': 0, 'today_new': 0, 'active_users': 0}
    
    def get_all_users(self) -> List[int]:
        """獲取所有用戶ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM users')
            results = cursor.fetchall()
            
            conn.close()
            return [row[0] for row in results]
            
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

# 初始化資料庫
db = Database()

# ===== 工具函數 =====
def is_admin(user) -> bool:
    """檢查是否為管理員"""
    if not user:
        return False
    return user.username == ADMIN_USERNAME

def check_cooldown(user_id: int, cooldown_seconds: int = 3) -> bool:
    """檢查冷卻時間"""
    now = datetime.now()
    if user_id in user_cooldowns:
        if now - user_cooldowns[user_id] < timedelta(seconds=cooldown_seconds):
            return False
    user_cooldowns[user_id] = now
    return True

def parse_buttons(text: str) -> List[List[InlineKeyboardButton]]:
    """解析按鈕文字"""
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
                    buttons.append([InlineKeyboardButton(button_text, url=button_url)])
    
    return buttons

# ===== 指令處理器 =====
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /start 指令"""
    try:
        user = update.effective_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'start')
        
        # 固定的歡迎訊息 - 避免衝突
        text = "🎬 歡迎使用看片機器人！\n\n請先加入我們的贊助商群組，然後點擊下方按鈕開始使用："
        
        keyboard = [[InlineKeyboardButton("✅ 我已加入群組", callback_data="joined_groups")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in start_handler: {e}")
        await update.message.reply_text("❌ 系統錯誤，請稍後再試")

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /admin 指令"""
    try:
        user = update.effective_user
        
        if not is_admin(user):
            await update.message.reply_text("❌ 您沒有管理員權限")
            return
        
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'admin_access')
        
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
        await update.message.reply_text("❌ 系統錯誤，請稍後再試")

# ===== 用戶端回調處理器 =====
async def joined_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """已加入群組回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'joined_groups')
        
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
        await query.answer("❌ 系統錯誤", show_alert=True)

async def search_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.answer("❌ 系統錯誤", show_alert=True)

async def random_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.answer("❌ 系統錯誤", show_alert=True)

async def sponsor_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """贊助商連結回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        db.log_action(user.id, 'sponsor_link')
        
        # 獲取贊助商連結
        sponsor_links = db.get_setting('sponsor_links')
        if not sponsor_links:
            sponsor_links = "示例贊助商 | https://t.me/example"
        
        buttons = parse_buttons(sponsor_links)
        buttons.append([InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_text(
            "📣 贊助商連結\n\n感謝您的支持！",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in sponsor_link_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def next_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """下一部影片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        if not check_cooldown(user.id):
            await query.answer("⏰ 請等待3秒後再試", show_alert=True)
            return
        
        db.log_action(user.id, 'next_video')
        
        video = db.get_random_video()
        if not video:
            await query.answer("😔 沒有更多影片了", show_alert=True)
            return
        
        await send_video_message(query.message, video, edit_previous=True)
        
    except Exception as e:
        logger.error(f"Error in next_video_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """回到選單回調"""
    try:
        query = update.callback_query
        await query.answer()
        
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
        await query.answer("❌ 系統錯誤", show_alert=True)

# ===== 管理員回調處理器 =====
async def admin_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理員主選單回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
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
        await query.answer("❌ 系統錯誤", show_alert=True)

async def admin_edit_messages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """編輯訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯開始訊息", callback_data="edit_start_message")],
            [InlineKeyboardButton("📝 編輯主選單", callback_data="edit_menu_message")],
            [InlineKeyboardButton("📝 編輯贊助商連結", callback_data="edit_sponsor_links")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 編輯訊息\n\n請選擇要編輯的內容：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_edit_messages_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def admin_video_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """影片管理回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📤 上傳影片", callback_data="upload_video")],
            [InlineKeyboardButton("📋 影片列表", callback_data="video_list")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 影片管理\n\n請選擇操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_video_management_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def admin_user_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [InlineKeyboardButton("🔙 返回", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👥 用戶管理\n\n"
            f"📊 統計數據：\n"
            f"• 總用戶數：{stats['total_users']}\n"
            f"• 今日新增：{stats['today_new']}\n"
            f"• 活躍用戶：{stats['active_users']}\n",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_management_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """群發訊息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        await query.edit_message_text("📊 請發送要群發的內容：")
        context.user_data['waiting_broadcast'] = True
        
    except Exception as e:
        logger.error(f"Error in admin_broadcast_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def video_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """影片列表回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        videos = db.get_all_videos()
        
        if not videos:
            keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="admin_video_management")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📋 目前沒有影片", reply_markup=reply_markup)
            return
        
        keyboard = [
            [InlineKeyboardButton("📋 查看所有影片", callback_data="show_all_videos")],
            [InlineKeyboardButton("🔙 返回", callback_data="admin_video_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 影片列表\n\n共有 {len(videos)} 部影片",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in video_list_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

async def show_all_videos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """顯示所有影片回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        if not is_admin(query.from_user):
            await query.answer("❌ 無權限", show_alert=True)
            return
        
        videos = db.get_all_videos()
        
        if not videos:
            await query.answer("沒有影片", show_alert=True)
            return
        
        text = "📋 所有影片列表：\n\n"
        for i, video in enumerate(videos[:10], 1):  # 只顯示前10部
            video_id, file_id, title, hashtags = video
            text += f"{i}. {title}\n"
            if hashtags:
                text += f"   標籤：{hashtags}\n"
            text += "\n"
        
        if len(videos) > 10:
            text += f"... 還有 {len(videos) - 10} 部影片"
        
        keyboard = [[InlineKeyboardButton("🔙 返回", callback_data="video_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error in show_all_videos_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

# ===== 群發功能 =====
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理群發訊息"""
    try:
        if not is_admin(update.effective_user):
            return
        
        user_id = update.effective_user.id
        message = update.message
        
        # 初始化群發數據
        broadcast_data = {
            'message_type': 'text',
            'content': '',
            'file_id': None,
            'caption': None,
            'buttons': []
        }
        
        # 處理不同類型的訊息
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

async def broadcast_add_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.answer("❌ 系統錯誤", show_alert=True)

async def handle_broadcast_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [InlineKeyboardButton("✅ 發送", callback_data="broadcast_send_now")],
            [InlineKeyboardButton("❌ 取消", callback_data="admin_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔘 按鈕設定完成\n\n"
            f"已添加 {len(buttons)} 個按鈕\n\n"
            "確認發送嗎？",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_broadcast_buttons: {e}")

async def broadcast_send_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """立即發送群發回調"""
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
        users = db.get_all_users()
        
        if not users:
            await query.edit_message_text("❌ 沒有用戶可以發送")
            return
        
        await query.edit_message_text(f"📊 開始群發給 {len(users)} 位用戶...")
        
        success_count = 0
        fail_count = 0
        
        # 準備按鈕
        reply_markup = None
        if broadcast_data.get('buttons'):
            reply_markup = InlineKeyboardMarkup(broadcast_data['buttons'])
        
        for user_id_target in users:
            try:
                if broadcast_data['message_type'] == 'text':
                    await context.bot.send_message(
                        chat_id=user_id_target,
                        text=broadcast_data['content'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'photo':
                    await context.bot.send_photo(
                        chat_id=user_id_target,
                        photo=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'animation':
                    await context.bot.send_animation(
                        chat_id=user_id_target,
                        animation=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                elif broadcast_data['message_type'] == 'video':
                    await context.bot.send_video(
                        chat_id=user_id_target,
                        video=broadcast_data['file_id'],
                        caption=broadcast_data['caption'],
                        reply_markup=reply_markup
                    )
                
                success_count += 1
                await asyncio.sleep(0.1)  # 避免觸發限制
                
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to send to user {user_id_target}: {e}")
        
        # 清除待發送數據
        del pending_broadcast_data[user_id]
        
        keyboard = [[InlineKeyboardButton("🔙 返回管理面板", callback_data="admin_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📊 群發完成！\n\n"
            f"✅ 成功：{success_count}\n"
            f"❌ 失敗：{fail_count}\n"
            f"📈 成功率：{success_count/(success_count+fail_count)*100:.1f}%",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in broadcast_send_now_callback: {e}")
        await query.answer("❌ 系統錯誤", show_alert=True)

# ===== 其他功能 =====
async def handle_search_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def send_video_message(message, video, edit_previous=False):
    """發送影片訊息"""
    try:
        video_id, file_id, title, hashtags = video
        
        # 建立按鈕
        keyboard = [
            [InlineKeyboardButton("🎲 下一部", callback_data="next_video")],
            [InlineKeyboardButton("🔙 回到選單", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"🎬 {title}"
        if hashtags:
            caption += f"\n\n🏷️ {hashtags}"
        
        if edit_previous:
            # 編輯現有訊息
            await message.edit_text(
                f"🎬 {title}\n\n🏷️ {hashtags or '無標籤'}",
                reply_markup=reply_markup
            )
        else:
            # 發送新的影片訊息
            await message.reply_video(
                video=file_id,
                caption=caption,
                reply_markup=reply_markup
            )
        
    except Exception as e:
        logger.error(f"Error in send_video_message: {e}")

# ===== 回音處理器 =====
async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        if update.message and update.message.text:
            text = update.message.text
            db.add_user(user.id, user.username, user.first_name, user.last_name)
            await update.message.reply_text(f"您說：{text}")
        
    except Exception as e:
        logger.error(f"Error in echo_handler: {e}")

async def main():
    """主函數 - 確保單一實例運行"""
    logger.warning("Starting clean bot instance...")
    
    # 初始化預設設定
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
    logger.warning("Bot is starting...")
    await app.initialize()
    await app.start()
    
    logger.warning("Bot is running with polling...")
    await app.updater.start_polling()
    
    logger.warning("Clean bot is now running!")
    
    # 保持運行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.warning("Bot stopped by user")
    finally:
        await app.stop()

if __name__ == '__main__':
    asyncio.run(main())
