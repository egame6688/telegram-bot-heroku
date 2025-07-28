import os
import threading
import time
import logging
from flask import Flask, render_template_string, request, jsonify

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

# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Bot 狀態監控</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 1.1em;
        }
        .content {
            padding: 40px;
        }
        .status-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 25px;
            border-left: 5px solid #28a745;
        }
        .status-card.error {
            border-left-color: #dc3545;
        }
        .status-card.stopped {
            border-left-color: #ffc107;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
            background-color: #28a745;
        }
        .status-indicator.error {
            background-color: #dc3545;
        }
        .status-indicator.stopped {
            background-color: #ffc107;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        .info-item {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        .info-item h3 {
            margin: 0 0 10px 0;
            color: #495057;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .info-item p {
            margin: 0;
            font-size: 1.4em;
            font-weight: 600;
            color: #212529;
        }
        .bot-link {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            margin-top: 20px;
            transition: transform 0.2s;
        }
        .bot-link:hover {
            transform: translateY(-2px);
            text-decoration: none;
            color: white;
        }
        .actions {
            margin-top: 30px;
            text-align: center;
        }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            margin: 0 10px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #007bff;
            color: white;
        }
        .btn-primary:hover {
            background: #0056b3;
            color: white;
            text-decoration: none;
        }
        .btn-success {
            background: #28a745;
            color: white;
        }
        .btn-success:hover {
            background: #1e7e34;
            color: white;
            text-decoration: none;
        }
        .footer {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }
        @media (max-width: 600px) {
            .header h1 {
                font-size: 2em;
            }
            .content {
                padding: 20px;
            }
            .info-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
    <script>
        function refreshStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    location.reload();
                })
                .catch(error => console.error('Error:', error));
        }
        
        function restartBot() {
            fetch('/api/restart', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    setTimeout(() => location.reload(), 2000);
                })
                .catch(error => console.error('Error:', error));
        }
        
        // 自動刷新
        setInterval(refreshStatus, 30000);
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Telegram Bot</h1>
            <p>看片機器人狀態監控面板</p>
        </div>
        
        <div class="content">
            <div class="status-card {{ 'error' if status.error else ('stopped' if not status.running else '') }}">
                <h2>
                    <span class="status-indicator {{ 'error' if status.error else ('stopped' if not status.running else '') }}"></span>
                    Bot狀態：
                    {% if status.error %}
                        🔴 錯誤
                    {% elif status.running %}
                        🟢 正在運行中
                    {% else %}
                        🟡 已停止
                    {% endif %}
                </h2>
                {% if status.error %}
                    <p><strong>錯誤訊息：</strong> {{ status.error }}</p>
                {% endif %}
                {% if status.start_time %}
                    <p><strong>啟動時間：</strong> {{ status.start_time }}</p>
                {% endif %}
            </div>
            
            <div class="info-grid">
                <div class="info-item">
                    <h3>Bot用戶名</h3>
                    <p>@wink666_bot</p>
                </div>
                <div class="info-item">
                    <h3>部署平台</h3>
                    <p>Heroku</p>
                </div>
                <div class="info-item">
                    <h3>運行狀態</h3>
                    <p>{{ '正常運行' if status.running else '已停止' }}</p>
                </div>
                <div class="info-item">
                    <h3>管理員</h3>
                    <p>@uplusluke</p>
                </div>
            </div>
            
            <div class="actions">
                <a href="https://t.me/wink666_bot" class="bot-link" target="_blank">
                    🚀 開啟Bot
                </a>
                <br><br>
                <button onclick="refreshStatus()" class="btn btn-primary">🔄 刷新狀態</button>
                <button onclick="restartBot()" class="btn btn-success">🔄 重啟Bot</button>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2025 Telegram Bot | Powered by Heroku</p>
            <p>最後更新：{{ current_time }}</p>
        </div>
    </div>
</body>
</html>
'''

def run_bot():
    """在背景執行Bot"""
    try:
        logger.info("Starting bot in background thread...")
        bot_status['running'] = True
        bot_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        bot_status['error'] = None
        
        # 動態導入Bot模組
        import heroku_bot
        heroku_bot.main()
        
    except Exception as e:
        logger.error(f"Bot error: {e}")
        bot_status['running'] = False
        bot_status['error'] = str(e)

@app.route('/')
def index():
    """首頁"""
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    return render_template_string(HTML_TEMPLATE, 
                                status=bot_status, 
                                current_time=current_time)

@app.route('/api/status')
def api_status():
    """API：獲取Bot狀態"""
    return jsonify(bot_status)

@app.route('/api/restart', methods=['POST'])
def api_restart():
    """API：重啟Bot"""
    try:
        # 這裡可以添加重啟邏輯
        return jsonify({'success': True, 'message': 'Bot重啟指令已發送'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/health')
def health_check():
    """健康檢查端點"""
    return jsonify({
        'status': 'healthy',
        'bot_running': bot_status['running'],
        'timestamp': time.time()
    })

if __name__ == '__main__':
    # 在背景執行Bot
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # 啟動Flask應用
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
