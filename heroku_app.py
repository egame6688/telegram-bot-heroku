import os
import threading
import time
import logging
from flask import Flask, jsonify

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Bot狀態
bot_status = {
    'running': False,
    'start_time': None,
    'error': None
}

def run_bot():
    """在背景執行Bot"""
    try:
        logger.info("Starting bot...")
        bot_status['running'] = True
        bot_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        bot_status['error'] = None
        
        # 嘗試導入並啟動Bot
        import heroku_bot
        heroku_bot.main()
        
    except Exception as e:
        logger.error(f"Bot error: {e}")
        bot_status['running'] = False
        bot_status['error'] = str(e)

@app.route('/')
def index():
    """首頁"""
    return f"""
    <html>
    <head>
        <title>Telegram Bot Status</title>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>🤖 Telegram Bot Status</h1>
        <p><strong>Status:</strong> {'🟢 Running' if bot_status['running'] else '🔴 Stopped'}</p>
        <p><strong>Start Time:</strong> {bot_status['start_time'] or 'Not started'}</p>
        <p><strong>Error:</strong> {bot_status['error'] or 'None'}</p>
        <p><strong>Bot:</strong> @wink666_bot</p>
        <p><strong>Admin:</strong> @uplusluke</p>
        <p><strong>Time:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <br>
        <a href="https://t.me/wink666_bot" target="_blank" style="background: #0088cc; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Open Bot</a>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    """健康檢查端點"""
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_status['running'],
        'timestamp': time.time()
    })

@app.route('/api/status')
def api_status():
    """API：獲取Bot狀態"""
    return jsonify(bot_status)

if __name__ == '__main__':
    # 在背景執行Bot
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # 啟動Flask應用
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
