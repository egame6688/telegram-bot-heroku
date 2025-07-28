import os
import threading
import time
import logging
import traceback
import sys
from flask import Flask, render_template_string, request, jsonify

# 配置詳細日誌
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Bot狀態
bot_status = {
    'running': False,
    'start_time': None,
    'error': None,
    'detailed_error': None,
    'import_status': {},
    'environment_check': {},
    'bot_thread_alive': False
}

# HTML模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Bot 診斷工具</title>
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
            max-width: 1000px;
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
        .diagnostic-section {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .diagnostic-section h3 {
            margin-top: 0;
            color: #495057;
        }
        .check-item {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            padding: 10px;
            background: white;
            border-radius: 5px;
        }
        .check-status {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 12px;
        }
        .check-status.success {
            background-color: #28a745;
        }
        .check-status.error {
            background-color: #dc3545;
        }
        .check-status.warning {
            background-color: #ffc107;
            color: #333;
        }
        .error-details {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            border-radius: 5px;
            padding: 15px;
            margin-top: 15px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
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
        .btn-success {
            background: #28a745;
            color: white;
        }
        .btn-warning {
            background: #ffc107;
            color: #333;
        }
    </style>
    <script>
        function refreshStatus() {
            location.reload();
        }
        
        function runDiagnostic() {
            fetch('/api/diagnostic', {method: 'POST'})
                .then(response => response.json())
                .then(data => {
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
            <h1>🔧 Telegram Bot 診斷工具</h1>
            <p>詳細診斷Bot啟動問題</p>
        </div>
        
        <div class="content">
            <div class="status-card {{ 'error' if status.error else ('stopped' if not status.running else '') }}">
                <h2>
                    Bot狀態：
                    {% if status.error %}
                        🔴 錯誤
                    {% elif status.running %}
                        🟢 正在運行中
                    {% else %}
                        🟡 已停止
                    {% endif %}
                </h2>
                {% if status.start_time %}
                    <p><strong>啟動時間：</strong> {{ status.start_time }}</p>
                {% endif %}
                <p><strong>Bot線程狀態：</strong> {{ '活躍' if status.bot_thread_alive else '未運行' }}</p>
            </div>
            
            <div class="diagnostic-section">
                <h3>🔍 環境檢查</h3>
                {% for check, result in status.environment_check.items() %}
                <div class="check-item">
                    <div class="check-status {{ 'success' if result.status == 'ok' else 'error' if result.status == 'error' else 'warning' }}">
                        {{ '✓' if result.status == 'ok' else '✗' if result.status == 'error' else '!' }}
                    </div>
                    <div>
                        <strong>{{ check }}:</strong> {{ result.message }}
                        {% if result.value %}
                            <br><small>值: {{ result.value }}</small>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <div class="diagnostic-section">
                <h3>📦 模組導入檢查</h3>
                {% for module, result in status.import_status.items() %}
                <div class="check-item">
                    <div class="check-status {{ 'success' if result.status == 'ok' else 'error' }}">
                        {{ '✓' if result.status == 'ok' else '✗' }}
                    </div>
                    <div>
                        <strong>{{ module }}:</strong> {{ result.message }}
                        {% if result.version %}
                            <br><small>版本: {{ result.version }}</small>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            
            {% if status.error %}
            <div class="diagnostic-section">
                <h3>❌ 錯誤詳情</h3>
                <p><strong>錯誤訊息：</strong> {{ status.error }}</p>
                {% if status.detailed_error %}
                <div class="error-details">{{ status.detailed_error }}</div>
                {% endif %}
            </div>
            {% endif %}
            
            <div class="actions">
                <button onclick="refreshStatus()" class="btn btn-primary">🔄 刷新狀態</button>
                <button onclick="runDiagnostic()" class="btn btn-warning">🔧 重新診斷</button>
                <a href="https://t.me/wink666_bot" class="btn btn-success" target="_blank">🚀 測試Bot</a>
            </div>
        </div>
    </div>
</body>
</html>
'''

def check_environment():
    """檢查環境配置"""
    checks = {}
    
    # 檢查環境變數
    bot_token = os.environ.get('BOT_TOKEN')
    admin_username = os.environ.get('ADMIN_USERNAME')
    
    checks['BOT_TOKEN'] = {
        'status': 'ok' if bot_token else 'error',
        'message': '已設定' if bot_token else '未設定',
        'value': f"{bot_token[:10]}..." if bot_token else None
    }
    
    checks['ADMIN_USERNAME'] = {
        'status': 'ok' if admin_username else 'error',
        'message': '已設定' if admin_username else '未設定',
        'value': admin_username
    }
    
    # 檢查Python版本
    python_version = sys.version
    checks['Python版本'] = {
        'status': 'ok',
        'message': '正常',
        'value': python_version.split()[0]
    }
    
    # 檢查網路連接
    try:
        import urllib.request
        urllib.request.urlopen('https://api.telegram.org', timeout=5)
        checks['Telegram API連接'] = {
            'status': 'ok',
            'message': '可以連接',
            'value': None
        }
    except Exception as e:
        checks['Telegram API連接'] = {
            'status': 'error',
            'message': f'連接失敗: {str(e)}',
            'value': None
        }
    
    return checks

def check_imports():
    """檢查模組導入"""
    imports = {}
    
    # 檢查基本模組
    modules_to_check = [
        ('telegram', 'python-telegram-bot'),
        ('flask', 'Flask'),
        ('sqlite3', 'SQLite3'),
        ('asyncio', 'AsyncIO'),
        ('json', 'JSON'),
        ('logging', 'Logging')
    ]
    
    for module_name, display_name in modules_to_check:
        try:
            module = __import__(module_name)
            version = getattr(module, '__version__', '未知')
            imports[display_name] = {
                'status': 'ok',
                'message': '導入成功',
                'version': version
            }
        except ImportError as e:
            imports[display_name] = {
                'status': 'error',
                'message': f'導入失敗: {str(e)}',
                'version': None
            }
    
    # 檢查heroku_bot模組
    try:
        import heroku_bot
        imports['heroku_bot'] = {
            'status': 'ok',
            'message': '導入成功',
            'version': None
        }
    except ImportError as e:
        imports['heroku_bot'] = {
            'status': 'error',
            'message': f'導入失敗: {str(e)}',
            'version': None
        }
    except Exception as e:
        imports['heroku_bot'] = {
            'status': 'error',
            'message': f'其他錯誤: {str(e)}',
            'version': None
        }
    
    return imports

def run_bot():
    """在背景執行Bot"""
    try:
        logger.info("開始啟動Bot...")
        bot_status['running'] = True
        bot_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        bot_status['error'] = None
        bot_status['detailed_error'] = None
        
        # 執行環境檢查
        bot_status['environment_check'] = check_environment()
        bot_status['import_status'] = check_imports()
        
        # 嘗試導入並啟動Bot
        logger.info("嘗試導入heroku_bot模組...")
        import heroku_bot
        logger.info("heroku_bot模組導入成功，開始啟動main()...")
        heroku_bot.main()
        
    except Exception as e:
        error_msg = str(e)
        detailed_error = traceback.format_exc()
        
        logger.error(f"Bot啟動失敗: {error_msg}")
        logger.error(f"詳細錯誤: {detailed_error}")
        
        bot_status['running'] = False
        bot_status['error'] = error_msg
        bot_status['detailed_error'] = detailed_error
        
        # 重新執行檢查
        bot_status['environment_check'] = check_environment()
        bot_status['import_status'] = check_imports()

@app.route('/')
def index():
    """首頁"""
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # 檢查Bot線程狀態
    for thread in threading.enumerate():
        if thread.name.startswith('Thread') and thread.is_alive():
            if hasattr(thread, '_target') and thread._target == run_bot:
                bot_status['bot_thread_alive'] = True
                break
    else:
        bot_status['bot_thread_alive'] = False
    
    return render_template_string(HTML_TEMPLATE, 
                                status=bot_status, 
                                current_time=current_time)

@app.route('/api/status')
def api_status():
    """API：獲取Bot狀態"""
    return jsonify(bot_status)

@app.route('/api/diagnostic', methods=['POST'])
def api_diagnostic():
    """API：執行診斷"""
    try:
        # 重新執行檢查
        bot_status['environment_check'] = check_environment()
        bot_status['import_status'] = check_imports()
        
        return jsonify({'success': True, 'message': '診斷完成'})
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
