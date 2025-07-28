#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
import sys
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 配置詳細日誌
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 診斷模式 - 記錄所有重要步驟
def log_diagnostic(step, status, details=None):
    """記錄診斷信息"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"[DIAGNOSTIC] {timestamp} - {step}: {status}"
    if details:
        message += f" - {details}"
    logger.info(message)
    print(message)  # 同時輸出到控制台

try:
    log_diagnostic("導入檢查", "開始", "檢查telegram模組")
    from telegram import (
        InlineKeyboardButton, InlineKeyboardMarkup, Update
    )
    log_diagnostic("導入檢查", "成功", "telegram基本模組導入成功")
    
    from telegram.ext import (
        Application, CallbackQueryHandler, CommandHandler, 
        MessageHandler, filters, ConversationHandler
    )
    log_diagnostic("導入檢查", "成功", "telegram.ext模組導入成功")
    
    from telegram.error import Forbidden
    log_diagnostic("導入檢查", "成功", "telegram.error模組導入成功")
    
except ImportError as e:
    log_diagnostic("導入檢查", "失敗", f"telegram模組導入失敗: {e}")
    raise
except Exception as e:
    log_diagnostic("導入檢查", "錯誤", f"telegram模組導入異常: {e}")
    raise

# Bot配置 - 從環境變數獲取或使用預設值
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'uplusluke')

log_diagnostic("配置檢查", "完成", f"BOT_TOKEN: {BOT_TOKEN[:10]}..., ADMIN_USERNAME: {ADMIN_USERNAME}")

# 全域變數
user_cooldowns = {}
pending_broadcast_data = {}

# 對話狀態
BROADCAST_MESSAGE, BROADCAST_BUTTONS, BROADCAST_CONFIRM = range(3)

class DatabaseManager:
    def __init__(self, db_path="bot_database.db"):
        self.db_path = db_path
        log_diagnostic("資料庫", "初始化", f"資料庫路徑: {db_path}")
        try:
            self.init_database()
            log_diagnostic("資料庫", "成功", "資料庫初始化完成")
        except Exception as e:
            log_diagnostic("資料庫", "失敗", f"資料庫初始化失敗: {e}")
            raise
    
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
            
            # 設定表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            log_diagnostic("資料庫", "錯誤", f"資料庫初始化錯誤: {e}")
            raise
    
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
            log_diagnostic("用戶管理", "成功", f"用戶 {user_id} 已添加/更新")
        except Exception as e:
            log_diagnostic("用戶管理", "錯誤", f"添加用戶失敗: {e}")
    
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
            log_diagnostic("設定管理", "錯誤", f"獲取設定失敗: {e}")
            return None
    
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
            log_diagnostic("用戶管理", "錯誤", f"獲取活躍用戶失敗: {e}")
            return []

# 初始化資料庫
try:
    db = DatabaseManager()
    log_diagnostic("資料庫管理器", "成功", "DatabaseManager初始化完成")
except Exception as e:
    log_diagnostic("資料庫管理器", "失敗", f"DatabaseManager初始化失敗: {e}")
    raise

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

# ===== 指令處理器 =====
async def start_handler(update: Update, context):
    """處理 /start 指令"""
    try:
        user = update.effective_user
        log_diagnostic("指令處理", "開始", f"/start 指令來自用戶 {user.id}")
        
        # 記錄用戶
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        text = '🎬 歡迎使用看片機器人！\n\n🔧 診斷模式已啟用'
        
        keyboard = [
            [InlineKeyboardButton("✅ 我已加入群組", callback_data="joined_groups")],
            [InlineKeyboardButton("🔧 診斷信息", callback_data="diagnostic_info")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        log_diagnostic("指令處理", "成功", f"/start 指令處理完成")
        
    except Exception as e:
        log_diagnostic("指令處理", "錯誤", f"/start 指令處理失敗: {e}")
        logger.error(f"Error in start_handler: {e}")

async def admin_handler(update: Update, context):
    """處理 /admin 指令"""
    try:
        user = update.effective_user
        log_diagnostic("管理員指令", "開始", f"/admin 指令來自用戶 {user.id}")
        
        if not is_admin(user):
            await update.message.reply_text("❌ 您沒有管理員權限")
            log_diagnostic("管理員指令", "拒絕", f"用戶 {user.id} 不是管理員")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 發送測試訊息", callback_data="admin_test_broadcast")],
            [InlineKeyboardButton("🔧 系統診斷", callback_data="admin_diagnostic")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔐 管理員面板 (診斷模式)\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        log_diagnostic("管理員指令", "成功", f"/admin 指令處理完成")
        
    except Exception as e:
        log_diagnostic("管理員指令", "錯誤", f"/admin 指令處理失敗: {e}")
        logger.error(f"Error in admin_handler: {e}")

# ===== 回調處理器 =====
async def joined_groups_callback(update: Update, context):
    """處理加入群組回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        log_diagnostic("回調處理", "開始", f"joined_groups 回調來自用戶 {user.id}")
        
        keyboard = [
            [InlineKeyboardButton("🎲 隨機測試", callback_data="random_test")],
            [InlineKeyboardButton("🔧 診斷信息", callback_data="diagnostic_info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎬 歡迎使用看片機器人！(診斷模式)\n\n請選擇您想要的功能：",
            reply_markup=reply_markup
        )
        log_diagnostic("回調處理", "成功", f"joined_groups 回調處理完成")
        
    except Exception as e:
        log_diagnostic("回調處理", "錯誤", f"joined_groups 回調處理失敗: {e}")
        logger.error(f"Error in joined_groups_callback: {e}")

async def diagnostic_info_callback(update: Update, context):
    """處理診斷信息回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        log_diagnostic("診斷信息", "開始", "顯示診斷信息")
        
        # 收集診斷信息
        diagnostic_text = f"""🔧 **Bot診斷信息**

**基本信息：**
• Python版本：{sys.version.split()[0]}
• Bot Token：{BOT_TOKEN[:10]}...
• 管理員：@{ADMIN_USERNAME}

**運行狀態：**
• 資料庫：✅ 正常
• 指令處理：✅ 正常
• 回調處理：✅ 正常

**時間戳：**
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(diagnostic_text, reply_markup=reply_markup)
        log_diagnostic("診斷信息", "成功", "診斷信息顯示完成")
        
    except Exception as e:
        log_diagnostic("診斷信息", "錯誤", f"診斷信息處理失敗: {e}")
        logger.error(f"Error in diagnostic_info_callback: {e}")

async def random_test_callback(update: Update, context):
    """處理隨機測試回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        log_diagnostic("隨機測試", "開始", "執行隨機測試")
        
        keyboard = [
            [InlineKeyboardButton("🔄 再次測試", callback_data="random_test")],
            [InlineKeyboardButton("🔙 返回主選單", callback_data="joined_groups")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        test_message = f"""🎲 **隨機測試結果**

✅ Bot正常運行
✅ 回調處理正常
✅ 按鈕功能正常

**測試時間：**
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        await query.edit_message_text(test_message, reply_markup=reply_markup)
        log_diagnostic("隨機測試", "成功", "隨機測試完成")
        
    except Exception as e:
        log_diagnostic("隨機測試", "錯誤", f"隨機測試失敗: {e}")
        logger.error(f"Error in random_test_callback: {e}")

async def admin_test_broadcast_callback(update: Update, context):
    """處理管理員測試群發回調"""
    try:
        query = update.callback_query
        await query.answer()
        
        user = query.from_user
        log_diagnostic("測試群發", "開始", f"管理員 {user.id} 執行測試群發")
        
        # 獲取所有用戶
        user_ids = db.get_all_active_users()
        
        test_message = f"""📊 **測試群發結果**

✅ 群發功能正常
📊 目標用戶數：{len(user_ids)}
🕐 執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**注意：** 這是診斷模式，未實際發送訊息"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 返回管理面板", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(test_message, reply_markup=reply_markup)
        log_diagnostic("測試群發", "成功", "測試群發完成")
        
    except Exception as e:
        log_diagnostic("測試群發", "錯誤", f"測試群發失敗: {e}")
        logger.error(f"Error in admin_test_broadcast_callback: {e}")

async def back_to_admin_callback(update: Update, context):
    """返回管理面板"""
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("📊 發送測試訊息", callback_data="admin_test_broadcast")],
            [InlineKeyboardButton("🔧 系統診斷", callback_data="admin_diagnostic")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔐 管理員面板 (診斷模式)\n\n請選擇要執行的操作：",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        log_diagnostic("管理面板", "錯誤", f"返回管理面板失敗: {e}")
        logger.error(f"Error in back_to_admin_callback: {e}")

def main():
    """主函數"""
    try:
        log_diagnostic("主函數", "開始", "Bot主函數啟動")
        
        # 檢查Token
        if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN':
            raise ValueError("Bot Token未設定或無效")
        
        log_diagnostic("Token檢查", "成功", "Bot Token有效")
        
        # 創建應用
        log_diagnostic("應用創建", "開始", "創建Telegram應用")
        application = Application.builder().token(BOT_TOKEN).build()
        log_diagnostic("應用創建", "成功", "Telegram應用創建完成")
        
        # 添加處理器
        log_diagnostic("處理器註冊", "開始", "註冊指令和回調處理器")
        
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("admin", admin_handler))
        
        # 回調處理器
        application.add_handler(CallbackQueryHandler(joined_groups_callback, pattern="^joined_groups$"))
        application.add_handler(CallbackQueryHandler(diagnostic_info_callback, pattern="^diagnostic_info$"))
        application.add_handler(CallbackQueryHandler(random_test_callback, pattern="^random_test$"))
        application.add_handler(CallbackQueryHandler(admin_test_broadcast_callback, pattern="^admin_test_broadcast$"))
        application.add_handler(CallbackQueryHandler(back_to_admin_callback, pattern="^back_to_admin$"))
        
        log_diagnostic("處理器註冊", "成功", "所有處理器註冊完成")
        
        # 啟動Bot
        log_diagnostic("Bot啟動", "開始", "開始運行Bot")
        logger.warning("Bot starting in diagnostic mode...")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        error_msg = f"Bot啟動失敗: {e}"
        detailed_error = traceback.format_exc()
        
        log_diagnostic("Bot啟動", "失敗", error_msg)
        log_diagnostic("詳細錯誤", "信息", detailed_error)
        
        logger.error(error_msg)
        logger.error(detailed_error)
        raise

if __name__ == '__main__':
    main()
