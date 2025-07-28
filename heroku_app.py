#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask Wrapper for Telegram Bot
Fixed import issue
"""

import os
import asyncio
import threading
import logging
import sys
from flask import Flask, jsonify, render_template_string

# 配置日誌
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Bot運行狀態
bot_running = False
bot_thread = None
bot_task = None

def run_bot_async():
    """在新的事件循環中運行Bot"""
    global bot_running, bot_task
    try:
        # 動態導入heroku_bot模組 (修復：從clean_bot改為heroku_bot)
        import heroku_bot
        
        # 創建新的事件循環
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot_running = True
        logger.warning("Starting heroku bot in async thread...")
        
        # 運行Bot
        bot_task = loop.create_task(heroku_bot.main())
        loop.run_until_complete(bot_task)
        
    except ImportError as e:
        logger.error(f"Failed to import heroku_bot: {e}")
        bot_running = False
    except Exception as e:
        logger.error(f"Bot error: {e}")
        bot_running = False
    finally:
        try:
            loop.close()
        except:
            pass

@app.route('/')
def index():
    """主頁面"""
    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram 看片機器人</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                max-width: 800px; 
                margin: 0 auto; 
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .status {
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
                font-weight: bold;
            }
            .running { background-color: #d4edda; color: #155724; }
            .stopped { background-color: #f8d7da; color: #721c24; }
            .info { background-color: #d1ecf1; color: #0c5460; }
            h1 { color: #333; text-align: center; }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 5px;
            }
            .btn:hover { background-color: #0056b3; }
            .footer {
                text-align: center;
                margin-top: 30px;
                color: #666;
                font-size: 14px;
            }
        </style>
        <script>
            function refreshStatus() {
                fetch('/health')
                    .then(response => response.json())
                    .then(data => {
                        const statusDiv = document.getElementById('status');
                        if (data.bot_running) {
                            statusDiv.className = 'status running';
                            statusDiv.innerHTML = '🟢 Bot 正在運行中';
                        } else {
                            statusDiv.className = 'status stopped';
                            statusDiv.innerHTML = '🔴 Bot 已停止';
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        const statusDiv = document.getElementById('status');
                        statusDiv.className = 'status stopped';
                        statusDiv.innerHTML = '❌ 無法獲取狀態';
                    });
            }
            
            // 每30秒自動刷新狀態
            setInterval(refreshStatus, 30000);
            
            // 頁面載入時刷新狀態
            window.onload = refreshStatus;
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram 看片機器人</h1>
            
            <div id="status" class="status">
                🔄 檢查狀態中...
            </div>
            
            <div class="info">
                <h3>📊 系統資訊</h3>
                <p><strong>部署平台：</strong>Heroku</p>
                <p><strong>Python版本：</strong>{{ python_version }}</p>
                <p><strong>Bot Token：</strong>{{ bot_token_masked }}</p>
                <p><strong>管理員：</strong>@{{ admin_username }}</p>
            </div>
            
            <div class="info">
                <h3>🔗 相關連結</h3>
                <a href="/health" class="btn">健康檢查 API</a>
                <a href="/restart" class="btn">重啟 Bot</a>
                <a href="https://t.me/{{ bot_username }}" class="btn" target="_blank">開啟 Bot</a>
            </div>
            
            <div class="info">
                <h3>📋 使用說明</h3>
                <ol>
                    <li>確保 Bot 狀態顯示為 "正在運行中"</li>
                    <li>點擊 "開啟 Bot" 按鈕開始使用</li>
                    <li>如果 Bot 無回應，請點擊 "重啟 Bot"</li>
                    <li>管理員可使用 /admin 指令進入管理面板</li>
                </ol>
            </div>
            
            <div class="footer">
                <p>🚀 Powered by Heroku | 📱 Telegram Bot API</p>
                <p>如有問題請聯繫管理員 @{{ admin_username }}</p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    bot_token = os.environ.get('BOT_TOKEN', '8034089304:AAGTK_k3t1rmfo5JmUj9V8u1lYb9ji8k0Rg')
    bot_token_masked = bot_token[:10] + '...' + bot_token[-10:] if len(bot_token) > 20 else bot_token
    
    return render_template_string(html_template,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        bot_token_masked=bot_token_masked,
        admin_username=os.environ.get('ADMIN_USERNAME', 'uplusluke'),
        bot_username='wink666_bot'
    )

@app.route('/health')
def health():
    """健康檢查端點"""
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_running,
        'environment': 'production',
        'platform': 'heroku'
    })

@app.route('/restart')
def restart_bot():
    """重啟Bot"""
    global bot_thread, bot_running, bot_task
    
    try:
        # 如果Bot正在運行，先停止
        if bot_running and bot_task:
            try:
                bot_task.cancel()
            except:
                pass
            bot_running = False
        
        # 等待舊線程結束
        if bot_thread and bot_thread.is_alive():
            bot_thread.join(timeout=5)
        
        # 啟動新的Bot線程
        bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        bot_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Bot restarted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error restarting bot: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to restart bot: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    """404錯誤處理"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """500錯誤處理"""
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    # 自動啟動Bot
    logger.warning("Starting Flask app...")
    
    if not bot_running:
        bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        bot_thread.start()
    
    # 啟動Flask應用
    port = int(os.environ.get('PORT', 5000))
    logger.warning(f"Starting Flask app on port {port}")
    
    app.run(
        host='0.0.0.0', 
        port=port, 
        debug=False,
        threaded=True
    )
