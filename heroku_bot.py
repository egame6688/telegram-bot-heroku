#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot for Movie Sharing
Compatible with Heroku deployment
"""

import os
import asyncio
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# 配置日誌
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# 狀態常量
WAITING_BROADCAST_MESSAGE, WAITING_BUTTON_TEXT, WAITING_BUTTON_URL = range(3)

class TelegramBot:
    def __init__(self):
        self.bot_token = os.environ.get('BOT_TOKEN', '8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg')
        self.admin_username = os.environ.get('ADMIN_USERNAME', 'uplusluke')
        self.db_path = 'bot_database.db'
        self.init_database()
        
    def init_database(self):
        """初始化資料庫"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 創建用戶表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 創建影片表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    hashtags TEXT,
                    file_id TEXT,
                    file_type TEXT,
                    thumbnail_id TEXT,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    uploader_id INTEGER
                )
            ''')
            
            # 創建設定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # 插入預設設定
            default_settings = [
                ('welcome_message', '🎬 歡迎使用看片機器人！\n\n請先加入我們的贊助商群組，然後點擊下方按鈕開始使用。'),
                ('sponsor_link', 'https://t.me/your_sponsor_group'),
                ('sponsor_text', '📣 贊助商群組')
            ]
            
            for key, value in default_settings:
                cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
            
            conn.commit()
            conn.close()
            logger.warning("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")

    def get_setting(self, key, default=''):
        """獲取設定值"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else default
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return default

    def set_setting(self, key, value):
        """設定值"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            return False

    def add_user(self, user_id, username, first_name, last_name):
        """添加或更新用戶"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    def is_admin(self, username):
        """檢查是否為管理員"""
        return username == self.admin_username

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理 /start 指令"""
        user = update.effective_user
        self.add_user(user.id, user.username, user.first_name, user.last_name)
        
        welcome_message = self.get_setting('welcome_message', '🎬 歡迎使用看片機器人！')
        
        keyboard = [[InlineKeyboardButton("✅ 我已加入群組", callback_data="joined_group")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)

    async def joined_group_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理加入群組回調"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🔍 搜尋影片", callback_data="search_video")],
            [InlineKeyboardButton("🎲 隨機看片", callback_data="random_video")],
            [InlineKeyboardButton("📣 贊助商連結", callback_data="sponsor_link")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("🎬 主選單\n\n請選擇您要使用的功能：", reply_markup=reply_markup)

    async def search_video_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理搜尋影片回調"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🔍 請輸入關鍵字搜尋影片：")

    async def random_video_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理隨機看片回調"""
        query = update.callback_query
        await query.answer()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM videos ORDER BY RANDOM() LIMIT 1')
            video = cursor.fetchone()
            conn.close()
            
            if video:
                await query.edit_message_text(f"🎬 隨機影片\n\n標題：{video[1]}\n描述：{video[2] or '無描述'}")
            else:
                await query.edit_message_text("❌ 目前沒有可用的影片")
                
        except Exception as e:
            logger.error(f"Random video error: {e}")
            await query.edit_message_text("❌ 獲取影片時發生錯誤")

    async def sponsor_link_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理贊助商連結回調"""
        query = update.callback_query
        await query.answer()
        
        sponsor_link = self.get_setting('sponsor_link', 'https://t.me/your_sponsor_group')
        sponsor_text = self.get_setting('sponsor_text', '📣 贊助商群組')
        
        keyboard = [[InlineKeyboardButton(sponsor_text, url=sponsor_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("📣 贊助商連結", reply_markup=reply_markup)

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理 /admin 指令"""
        user = update.effective_user
        
        if not self.is_admin(user.username):
            await update.message.reply_text("❌ 您沒有管理員權限")
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯訊息", callback_data="admin_edit_messages")],
            [InlineKeyboardButton("🎬 影片管理", callback_data="admin_video_management")],
            [InlineKeyboardButton("👥 用戶管理", callback_data="admin_user_management")],
            [InlineKeyboardButton("📊 發送訊息", callback_data="admin_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("🔐 管理員面板\n\n請選擇管理功能：", reply_markup=reply_markup)

    async def admin_edit_messages_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理編輯訊息回調"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("✏️ 編輯歡迎訊息", callback_data="edit_welcome")],
            [InlineKeyboardButton("🔗 編輯贊助商連結", callback_data="edit_sponsor")],
            [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("📝 編輯訊息\n\n請選擇要編輯的內容：", reply_markup=reply_markup)

    async def admin_video_management_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理影片管理回調"""
        query = update.callback_query
        await query.answer()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM videos')
            video_count = cursor.fetchone()[0]
            conn.close()
            
            keyboard = [
                [InlineKeyboardButton("➕ 添加影片", callback_data="add_video")],
                [InlineKeyboardButton("📋 影片列表", callback_data="list_videos")],
                [InlineKeyboardButton("🗑️ 刪除影片", callback_data="delete_video")],
                [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(f"🎬 影片管理\n\n目前共有 {video_count} 部影片\n\n請選擇操作：", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Video management error: {e}")
            await query.edit_message_text("❌ 獲取影片資訊時發生錯誤")

    async def admin_user_management_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理用戶管理回調"""
        query = update.callback_query
        await query.answer()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]
            conn.close()
            
            keyboard = [
                [InlineKeyboardButton("📊 用戶統計", callback_data="user_stats")],
                [InlineKeyboardButton("📋 用戶列表", callback_data="user_list")],
                [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(f"👥 用戶管理\n\n目前共有 {user_count} 位用戶\n\n請選擇操作：", reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"User management error: {e}")
            await query.edit_message_text("❌ 獲取用戶資訊時發生錯誤")

    async def admin_broadcast_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理群發訊息回調"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text("📊 群發訊息\n\n請發送要群發的內容：")
        return WAITING_BROADCAST_MESSAGE

    async def back_to_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """返回管理面板"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("📝 編輯訊息", callback_data="admin_edit_messages")],
            [InlineKeyboardButton("🎬 影片管理", callback_data="admin_video_management")],
            [InlineKeyboardButton("👥 用戶管理", callback_data="admin_user_management")],
            [InlineKeyboardButton("📊 發送訊息", callback_data="admin_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("🔐 管理員面板\n\n請選擇管理功能：", reply_markup=reply_markup)

    async def handle_broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理群發訊息"""
        if not self.is_admin(update.effective_user.username):
            return ConversationHandler.END
        
        # 儲存訊息內容
        context.user_data['broadcast_message'] = update.message
        
        keyboard = [
            [InlineKeyboardButton("✅ 直接發送", callback_data="send_broadcast")],
            [InlineKeyboardButton("🔗 添加按鈕", callback_data="add_button")],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("📊 群發預覽\n\n請選擇操作：", reply_markup=reply_markup)
        return WAITING_BROADCAST_MESSAGE

    async def send_broadcast_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """發送群發訊息"""
        query = update.callback_query
        await query.answer()
        
        broadcast_message = context.user_data.get('broadcast_message')
        if not broadcast_message:
            await query.edit_message_text("❌ 沒有找到要發送的訊息")
            return ConversationHandler.END
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            users = cursor.fetchall()
            conn.close()
            
            success_count = 0
            fail_count = 0
            
            for user_tuple in users:
                user_id = user_tuple[0]
                try:
                    if broadcast_message.text:
                        await context.bot.send_message(chat_id=user_id, text=broadcast_message.text)
                    elif broadcast_message.photo:
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=broadcast_message.photo[-1].file_id,
                            caption=broadcast_message.caption
                        )
                    success_count += 1
                    await asyncio.sleep(0.1)  # 避免觸發限制
                except Exception as e:
                    fail_count += 1
                    logger.error(f"Failed to send to {user_id}: {e}")
            
            await query.edit_message_text(f"📊 群發完成\n\n✅ 成功：{success_count}\n❌ 失敗：{fail_count}")
            
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            await query.edit_message_text("❌ 群發時發生錯誤")
        
        return ConversationHandler.END

    async def cancel_broadcast_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """取消群發"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("❌ 群發已取消")
        return ConversationHandler.END

    def setup_handlers(self, application):
        """設定處理器"""
        # 指令處理器
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("admin", self.admin_command))
        
        # 回調處理器
        application.add_handler(CallbackQueryHandler(self.joined_group_callback, pattern="^joined_group$"))
        application.add_handler(CallbackQueryHandler(self.search_video_callback, pattern="^search_video$"))
        application.add_handler(CallbackQueryHandler(self.random_video_callback, pattern="^random_video$"))
        application.add_handler(CallbackQueryHandler(self.sponsor_link_callback, pattern="^sponsor_link$"))
        
        # 管理員回調處理器
        application.add_handler(CallbackQueryHandler(self.admin_edit_messages_callback, pattern="^admin_edit_messages$"))
        application.add_handler(CallbackQueryHandler(self.admin_video_management_callback, pattern="^admin_video_management$"))
        application.add_handler(CallbackQueryHandler(self.admin_user_management_callback, pattern="^admin_user_management$"))
        application.add_handler(CallbackQueryHandler(self.admin_broadcast_callback, pattern="^admin_broadcast$"))
        application.add_handler(CallbackQueryHandler(self.back_to_admin_callback, pattern="^back_to_admin$"))
        
        # 群發相關回調處理器
        application.add_handler(CallbackQueryHandler(self.send_broadcast_callback, pattern="^send_broadcast$"))
        application.add_handler(CallbackQueryHandler(self.cancel_broadcast_callback, pattern="^cancel_broadcast$"))
        
        # 群發對話處理器
        broadcast_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_broadcast_callback, pattern="^admin_broadcast$")],
            states={
                WAITING_BROADCAST_MESSAGE: [
                    MessageHandler(filters.TEXT | filters.PHOTO, self.handle_broadcast_message),
                    CallbackQueryHandler(self.send_broadcast_callback, pattern="^send_broadcast$"),
                    CallbackQueryHandler(self.cancel_broadcast_callback, pattern="^cancel_broadcast$")
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_broadcast_callback, pattern="^cancel_broadcast$")]
        )
        application.add_handler(broadcast_handler)

async def main():
    """主函數"""
    try:
        bot = TelegramBot()
        application = Application.builder().token(bot.bot_token).build()
        
        # 設定處理器
        bot.setup_handlers(application)
        
        logger.warning("Bot starting...")
        
        # 啟動Bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.warning("Bot is running...")
        
        # 保持運行
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
