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
    # Create a default config if it doesn't exist
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            'check_interval': 60,
            'sites': [
                {'name': 'Google', 'url': 'https://www.google.com'},
                {'name': 'GitHub', 'url': 'https://www.github.com'}
            ]
        }
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(default_config, f)
        logging.info(f"Created default configuration file: {CONFIG_FILE}")

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
                previous_status = site['status']

                # Uptime/Downtime calculation
                time_since_last_check = current_time - site['last_change']
                new_total_uptime = site['total_uptime']
                new_total_downtime = site['total_downtime']

                if previous_status == "Online":
                    new_total_uptime += time_since_last_check
                elif previous_status == "Down":
                    new_total_downtime += time_since_last_check

                # Check status
                try:
                    res = requests.get(url, timeout=10)
                    new_status = "Online" if 200 <= res.status_code < 300 else "Down"
                except requests.exceptions.RequestException as e:
                    logging.warning(f"Check failed for {name} ({url}): {e}")
                    new_status = "Down"

                cursor.execute('''
                    UPDATE sites
                    SET status = ?, last_change = ?, last_checked = ?, 
                        total_uptime = ?, total_downtime = ?
                    WHERE name = ?
                ''', (new_status, current_time, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time)),
                      new_total_uptime, new_total_downtime, name))

            db.commit()
        time.sleep(CHECK_INTERVAL)

# --- Flask Routes ---
@app.route("/")
def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CoRamTix Hosting System Status</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #f9fafd; }
            .container { max-width: 900px; margin: auto; padding: 26px; background: #fff; border-radius: 8px; box-shadow: 0 2px 18px rgba(100,120,170,0.08);}
            h1 { color: #1d3557; }
            .site { border: 1px solid #e3e8ee; padding: 14px; margin-bottom: 16px; border-radius: 6px; }
            .status-Online { border-left: 6px solid #33a16a; }
            .status-Down { border-left: 6px solid #e04343; }
            .status-Unknown { border-left: 6px solid #666; }
            .brand { font-family: 'Segoe UI Semibold', sans-serif; color: #3866b2; font-size: 2em; margin-bottom: 4px;}
            .footer { margin-top: 44px; font-size: 0.92em; color: #888;}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="brand">CoRamTix Hosting</div>
            <h1>System Status</h1>
            <h2 id="overall-status">Loading...</h2>
            <div id="sites-container"></div>
            <div class="footer">&copy; 2024 CoRamTix Hosting. All Rights Reserved.</div>
        </div>
        <script>
            function updateStatus() {
                fetch('/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('overall-status').textContent = data.overall_status;
                        const container = document.getElementById('sites-container');
                        container.innerHTML = '';
                        for (const name in data.sites) {
                            const site = data.sites[name];
                            const siteDiv = document.createElement('div');
                            siteDiv.className = 'site status-' + site.status;
                            siteDiv.innerHTML = `
                                <h3>${name} - <span style="color:${site.status === 'Online' ? '#33a16a' : '#e04343'}">${site.status}</span></h3>
                                <p><strong>Uptime:</strong> ${site.uptime_percent}</p>
                                <p><strong>Total Uptime:</strong> ${site.uptime}</p>
                                <p><strong>Total Downtime:</strong> ${site.downtime}</p>
                                <p><em>Last Checked: ${site.last_checked}</em></p>
                            `;
                            container.appendChild(siteDiv);
                        }
                    });
            }
            setInterval(updateStatus, 5000); // Refresh every 5 seconds
            updateStatus(); // Initial load
        </script>
    </body>
    </html>
    """
    if os.path.exists('templates/index.html'):
        return render_template("index.html")
    else:
        return html_content

@app.route("/status")
def get_status():
    db = get_db()
    cursor = db.cursor()
    sites_data = cursor.execute("SELECT * FROM sites").fetchall()

    data = {"sites": {}}
    all_operational = True
    current_time = time.time()

    for site in sites_data:
        time_since_last_db_update = current_time - site['last_change']
        display_uptime = site['total_uptime']
        display_downtime = site['total_downtime']

        if site['status'] == 'Online':
            display_uptime += time_since_last_db_update
        elif site['status'] == 'Down':
            display_downtime += time_since_last_db_update

        total_time = display_uptime + display_downtime
        uptime_pct = (display_uptime / total_time * 100) if total_time > 0 else 100

        if site['status'] != "Online":
            all_operational = False

        data["sites"][site['name']] = {
            "status": site['status'],
            "uptime": format_duration(display_uptime),
            "downtime": format_duration(display_downtime),
            "uptime_percent": f"{uptime_pct:.3f}%",
            "last_checked": site['last_checked']
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
        label = site_name.replace(' ', '_')
        return redirect(f"https://img.shields.io/badge/{label}-{status}-{color}", code=302)

    return "Site not found", 404

# --- Main Execution ---
if __name__ == "__main__":
    init_db()  # Initialize the database and table on startup
    # Start the background checker thread
    threading.Thread(target=check_sites, daemon=True).start()
    # Run the Flask app
    app.run(host="0.0.0.0", port=8080, debug=False) # Debug mode should be False in production
