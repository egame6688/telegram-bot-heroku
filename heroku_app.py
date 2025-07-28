import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return """
    <html>
    <head>
        <title>Basic Flask Test</title>
    </head>
    <body>
        <h1>🚀 Flask App is Running!</h1>
        <p>This is a minimal Flask application test.</p>
        <p>If you can see this, the basic Flask setup is working.</p>
        <p>Time: <span id="time"></span></p>
        <script>
            document.getElementById('time').textContent = new Date().toLocaleString();
        </script>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {'status': 'ok', 'message': 'Flask app is running'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
