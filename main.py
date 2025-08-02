import flask
from flask import Flask, jsonify, render_template, g, request, Response
import requests
import threading
import time
import sqlite3
import yaml
import os
import logging
from functools import wraps

# --- Basic Setup ---
app = Flask(__name__)
DATABASE = 'status_dashboard.db'
CONFIG_FILE = 'config.yaml'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load Configuration ---
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

config = load_config()
SITES = {site['name']: site['url'] for site in config['sites']}
CHECK_INTERVAL = config['check_interval']
HISTORY_SEGMENTS = config['history_segments']

# --- AUTHENTICATION SETUP ---
# Load credentials from environment variables. Use default 'admin' if not set.
AUTH_USERNAME = os.getenv('STATUS_USERNAME', 'admin')
AUTH_PASSWORD = os.getenv('STATUS_PASSWORD', 'admin')

def check_auth(username, password):
    """This function is called to check if a username / password combination is valid."""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Database Handling ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY, name TEXT UNIQUE, url TEXT)')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY, site_id INTEGER, status TEXT, response_time_ms REAL, timestamp REAL,
                FOREIGN KEY (site_id) REFERENCES sites (id))
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_site_id_timestamp ON check_history (site_id, timestamp DESC)')
        for name, url in SITES.items():
            cursor.execute("INSERT OR IGNORE INTO sites (name, url) VALUES (?, ?)", (name, url))
        db.commit()
        logging.info("Database initialized successfully.")

# --- Background Worker ---
def check_sites_worker():
    logging.info(f"Background worker started. Checking sites every {CHECK_INTERVAL} seconds.")
    while True:
        with app.app_context():
            db = get_db()
            sites_to_check = db.execute("SELECT * FROM sites").fetchall()
            for site in sites_to_check:
                status, response_time = "Down", -1
                try:
                    res = requests.get(site['url'], timeout=10)
                    response_time = res.elapsed.total_seconds() * 1000
                    status = "Online" if 200 <= res.status_code < 400 else "Down"
                except requests.exceptions.RequestException as e:
                    logging.warning(f"Check failed for {site['name']}: {e}")
                db.execute("INSERT INTO check_history (site_id, status, response_time_ms, timestamp) VALUES (?, ?, ?, ?)",
                           (site['id'], status, response_time, time.time()))
            ninety_days_ago = time.time() - (90 * 24 * 60 * 60)
            db.execute("DELETE FROM check_history WHERE timestamp < ?", (ninety_days_ago,))
            db.commit()
        time.sleep(CHECK_INTERVAL)

# --- Flask Routes (Now Protected) ---
@app.route("/")
@require_auth
def home():
    return render_template("index.html")

@app.route("/status")
@require_auth
def get_status_api():
    db = get_db()
    sites_data = db.execute("SELECT * FROM sites").fetchall()
    response_data = {"sites": []}
    all_operational = True
    ninety_days_ago = time.time() - (90 * 24 * 60 * 60)
    for site in sites_data:
        uptime_checks = db.execute("SELECT COUNT(*) FROM check_history WHERE site_id = ? AND status = 'Online' AND timestamp > ?", (site['id'], ninety_days_ago)).fetchone()[0]
        total_checks = db.execute("SELECT COUNT(*) FROM check_history WHERE site_id = ? AND timestamp > ?", (site['id'], ninety_days_ago)).fetchone()[0]
        uptime_percent_90d = f"{(uptime_checks / total_checks * 100):.2f}%" if total_checks > 0 else "100.00%"
        history = db.execute("SELECT status, timestamp FROM check_history WHERE site_id = ? ORDER BY timestamp DESC LIMIT ?", (site['id'], HISTORY_SEGMENTS)).fetchall()
        history_list = [dict(row) for row in reversed(history)]
        if history and history[0]['status'] != 'Online':
             all_operational = False
        response_data["sites"].append({"name": site['name'], "uptime_percent_90d": uptime_percent_90d, "history": history_list})
    response_data["overall_status"] = "All systems operational." if all_operational else "Some systems are experiencing issues."
    return jsonify(response_data)

# --- Main Execution ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=check_sites_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)

