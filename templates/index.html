import flask
from flask import Flask, jsonify, g
import requests
import threading
import time
import sqlite3
import yaml
import os

app = Flask(__name__)
DATABASE = 'status.db'
CONFIG_FILE = 'config.yaml'

def load_config():
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
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

config = load_config()
SITES = {site['name']: site['url'] for site in config['sites']}
CHECK_INTERVAL = config['check_interval']

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
                total_downtime REAL DEFAULT 0
            )
        ''')
        for name, url in SITES.items():
            cursor.execute("INSERT OR IGNORE INTO sites (name, url, last_change) VALUES (?, ?, ?)", (name, url, time.time()))
        db.commit()

def format_duration(seconds):
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hrs, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hrs}h {mins}m"
    return f"{hrs}h {mins}m {secs}s"

def check_sites():
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
                time_since_last_check = current_time - site['last_change']
                new_total_uptime = site['total_uptime']
                new_total_downtime = site['total_downtime']
                if previous_status == "Online":
                    new_total_uptime += time_since_last_check
                elif previous_status == "Down":
                    new_total_downtime += time_since_last_check
                try:
                    res = requests.get(url, timeout=10)
                    new_status = "Online" if 200 <= res.status_code < 300 else "Down"
                except requests.exceptions.RequestException:
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

@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>CoRamTix Hosting System Status</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #f5f8fb; }
            .container { max-width: 860px; margin: auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 16px rgba(100,120,170,0.08); padding: 30px; }
            .brand { font-size: 2em; color: #2959d9; font-family: 'Segoe UI Semibold', sans-serif; }
            .statusbar-container { margin: 28px 0 24px 0; text-align: left;}
            #statusbar { display: flex; gap: 5px; padding: 6px 0;}
            .status-block { width: 18px; height: 36px; border-radius: 6px; background: #5a6275; transition: background 0.2s;}
            .status-block.active { background: #29d366; }
            h1 { margin-top:0; color: #12356f; }
            .site { border: 1px solid #eef2f9; padding: 14px; margin-bottom: 16px; border-radius: 7px; }
            .status-Online { border-left: 7px solid #29d366; }
            .status-Down { border-left: 7px solid #e63946; }
            .status-Unknown { border-left: 7px solid #888; }
            .footer { margin-top: 38px; font-size: 0.93em; color: #9aa; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="brand">CoRamTix Hosting</div>
            <div class="statusbar-container"><div id="statusbar"></div></div>
            <h1 id="overall-status">Loading...</h1>
            <div id="sites-container"></div>
            <div class="footer">&copy; 2024 CoRamTix Hosting. All Rights Reserved.</div>
        </div>
        <script>
            function drawStatusBar(segments, active) {
                const bar = document.getElementById('statusbar');
                bar.innerHTML = '';
                for(let i=0;i<segments;i++) {
                    const block = document.createElement('div');
                    block.className = 'status-block' + (i >= (segments-active) ? ' active' : '');
                    bar.appendChild(block);
                }
            }

            function updateStatus() {
                fetch('/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('overall-status').textContent = data.overall_status;
                        const total = Object.keys(data.sites).length;
                        const online = Object.values(data.sites).filter(site => site.status === 'Online').length;
                        const segments = 20;
                        const activeBlocks = total === 0 ? 0 : Math.round((online / total) * segments);
                        drawStatusBar(segments, activeBlocks);

                        const container = document.getElementById('sites-container');
                        container.innerHTML = '';
                        for (const name in data.sites) {
                            const site = data.sites[name];
                            const siteDiv = document.createElement('div');
                            siteDiv.className = 'site status-' + site.status;
                            siteDiv.innerHTML = `
                                <h3>${name} - <span style="color:${site.status === 'Online' ? '#29d366' : '#e63946'}">${site.status}</span></h3>
                                <p><strong>Uptime:</strong> ${site.uptime_percent}</p>
                                <p><strong>Total Uptime:</strong> ${site.uptime}</p>
                                <p><strong>Total Downtime:</strong> ${site.downtime}</p>
                                <p><em>Last Checked: ${site.last_checked}</em></p>
                            `;
                            container.appendChild(siteDiv);
                        }
                    });
            }
            setInterval(updateStatus, 5000);
            updateStatus();
        </script>
    </body>
    </html>
    """

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

if __name__ == "__main__":
    init_db()
    threading.Thread(target=check_sites, daemon=True).start()
    app.run(host="0.0.0.0", port=8080, debug=False)
