import flask
from flask import Flask, jsonify, render_template, redirect, g
import requests
import threading
import time
import sqlite3
import yaml
import os
import logging

# --- Basic Setup ---
app = Flask(__name__)
DATABASE = 'status.db'
CONFIG_FILE = 'config.yaml'

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load Configuration ---
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

config = load_config()
SITES = {site['name']: site['url'] for site in config['sites']}
CHECK_INTERVAL = config['check_interval']

# --- Database Handling ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                status TEXT DEFAULT 'Unknown',
                last_change REAL DEFAULT 0,
                last_checked TEXT DEFAULT 'Never',
                total_uptime REAL DEFAULT 0,
                total_downtime REAL DEFAULT 0,
                response_time_ms REAL DEFAULT -1
            )
        ''')
        # Add new sites from config if they don't exist
        for name, url in SITES.items():
            cursor.execute("INSERT OR IGNORE INTO sites (name, url, last_change) VALUES (?, ?, ?)", (name, url, time.time()))
        db.commit()

# --- Helper Functions ---
def format_duration(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hrs, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hrs}h {mins}m"
    return f"{hrs}h {mins}m {secs}s"

# --- Background Worker ---
def check_sites():
    logging.info("Background site checker thread started.")
    while True:
        with app.app_context():
            db = get_db()
            cursor = db.cursor()
            sites_to_check = cursor.execute("SELECT * FROM sites").fetchall()
            
            for site in sites_to_check:
                current_time = time.time()
                name = site['name']
                url = site['url']
                
                # --- Improved Uptime/Downtime Calculation ---
                # 1. Calculate time since the last status change
                duration_since_change = current_time - site['last_change']
                
                # 2. Add this duration to the correct counter based on the *current* status
                if site['status'] == "Online":
                    new_total_uptime = site['total_uptime'] + duration_since_change
                    new_total_downtime = site['total_downtime']
                elif site['status'] == "Down":
                    new_total_downtime = site['total_downtime'] + duration_since_change
                    new_total_uptime = site['total_uptime']
                else: # 'Unknown' status
                    new_total_uptime = site['total_uptime']
                    new_total_downtime = site['total_downtime']

                # 3. Perform the new check
                try:
                    res = requests.get(url, timeout=10)
                    response_time = res.elapsed.total_seconds() * 1000  # in ms
                    new_status = "Online" if 200 <= res.status_code < 300 else "Down"
                except requests.exceptions.RequestException as e:
                    logging.warning(f"Check failed for {name} ({url}): {e}")
                    new_status = "Down"
                    response_time = -1

                # 4. If status changed, update the 'last_change' time. Otherwise, it stays the same.
                # We always update the total uptime/downtime counters.
                new_last_change = current_time if new_status != site['status'] else site['last_change']
                
                # 5. Update DB
                cursor.execute('''
                    UPDATE sites
                    SET status = ?, last_change = ?, last_checked = ?, 
                        total_uptime = ?, total_downtime = ?, response_time_ms = ?
                    WHERE name = ?
                ''', (new_status, new_last_change, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time)),
                      new_total_uptime, new_total_downtime, response_time, name))
            
            db.commit()
        time.sleep(CHECK_INTERVAL)

# --- Flask Routes ---
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/status")
def get_status():
    db = get_db()
    cursor = db.cursor()
    sites_data = cursor.execute("SELECT * FROM sites").fetchall()
    
    data = {"sites": {}}
    all_operational = True
    
    for site in sites_data:
        total_time = site['total_uptime'] + site['total_downtime']
        uptime_pct = (site['total_uptime'] / total_time * 100) if total_time > 0 else 100
        
        if site['status'] != "Online":
            all_operational = False
            
        data["sites"][site['name']] = {
            "status": site['status'],
            "uptime": format_duration(site['total_uptime']),
            "downtime": format_duration(site['total_downtime']),
            "uptime_percent": f"{uptime_pct:.3f}%",
            "last_checked": site['last_checked'],
            "response_time_ms": site['response_time_ms']
        }
        
    data["overall_status"] = "All systems operational" if all_operational else "Some systems are experiencing issues"
    return jsonify(data)

@app.route("/badge/<site_name>")
def badge(site_name):
    db = get_db()
    cursor = db.cursor()
    site = cursor.execute("SELECT status FROM sites WHERE name = ?", (site_name,)).fetchone()
    
    if site:
        status = site['status']
        color = "brightgreen" if status == "Online" else "red"
        # Shields.io requires spaces to be replaced with underscores
        label = site_name.replace(' ', '_')
        return redirect(f"https://img.shields.io/badge/{label}-{status}-{color}", code=302)
    
    return "Site not found", 404

# --- Main Execution ---
if __name__ == "__main__":
    init_db()  # Initialize the database and table on startup
    # Start the background checker thread
    threading.Thread(target=check_sites, daemon=True).start()
    # Run the Flask app
    app.run(host="0.0.0.0", port=8080, debug=True)
