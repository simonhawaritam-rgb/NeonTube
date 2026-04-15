import os, json, re, time
from flask import Flask, request, jsonify, send_from_directory, render_template, session
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
app.secret_key = 'neon-secret-stream'
CORS(app)

CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "site_title": "NeonHub",
    "broadcast_message": "",
    "maintenance_mode": "off",
    "maintenance_message": ""
}

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(DEFAULT_CONFIG, f)

stream_cache = {}
CACHE_TTL = 3600

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f)

def extract_video_id(url):
    patterns = [r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)', r'youtu\.be\/([0-9A-Za-z_-]{11})']
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

@app.route('/')
def index():
    cfg = load_config()
    if cfg.get('maintenance_mode') == 'on' and not session.get('admin'):
        return render_template('maintenance.html', message=cfg.get('maintenance_message', 'Under maintenance.'))
    return render_template('index.html')

@app.route('/config.json')
def get_config():
    response = send_from_directory('.', CONFIG_FILE)
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/api/settings/public')
def public_settings():
    cfg = load_config()
    return jsonify({
        'site_title': cfg.get('site_title', 'NeonHub'),
        'broadcast_message': cfg.get('broadcast_message', '')
    })

@app.route('/api/stream', methods=['POST'])
def stream():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    vid = extract_video_id(url)
    now = time.time()

    if vid and vid in stream_cache:
        cached = stream_cache[vid]
        if cached['expires_at'] > now:
            return jsonify({
                'title': cached['title'],
                'thumbnail': cached['thumbnail'],
                'duration': cached['duration'],
                'stream_url': cached['stream_url'],
                'cached': True
            })
        else:
            del stream_cache[vid]

    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            combined = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('height', 0) <= 720]
            if combined:
                best = max(combined, key=lambda f: f.get('height', 0))
                stream_url = best['url']
            else:
                stream_url = info.get('url')
            
            result = {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'stream_url': stream_url,
                'cached': False
            }
            
            if vid:
                stream_cache[vid] = {
                    'title': result['title'],
                    'thumbnail': result['thumbnail'],
                    'duration': result['duration'],
                    'stream_url': stream_url,
                    'expires_at': now + CACHE_TTL
                }
            return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- Admin Routes ----------
def admin_required(f):
    def wrap(*a, **k):
        if not session.get('admin'):
            return jsonify({'error': 'Admin required'}), 403
        return f(*a, **k)
    wrap.__name__ = f.__name__
    return wrap

@app.route('/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('password') == 'Rashid707':
        session['admin'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Wrong password'}), 401

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin', None)
    return jsonify({'success': True})

@app.route('/api/admin/check')
def admin_check():
    return jsonify({'admin': session.get('admin', False)})

@app.route('/api/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    cfg = load_config()
    if request.method == 'POST':
        data = request.json
        for k, v in data.items():
            cfg[k] = v
        save_config(cfg)
        return jsonify({'success': True})
    return jsonify(cfg)

@app.route('/api/admin/broadcast', methods=['POST'])
@admin_required
def admin_broadcast():
    msg = request.json.get('message', '')
    cfg = load_config()
    cfg['broadcast_message'] = msg
    save_config(cfg)
    return jsonify({'success': True})

@app.route('/api/admin/clear-stream-cache', methods=['POST'])
@admin_required
def clear_stream_cache():
    global stream_cache
    stream_cache.clear()
    return jsonify({'success': True, 'message': 'Stream cache cleared'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
