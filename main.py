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
                {'name': 'GitHub', 'url': 'https://www.github.com'},
                {'name': 'CloudFlare', 'url': 'https://www.cloudflare.com'},
                {'name': 'AWS', 'url': 'https://aws.amazon.com'},
                {'name': 'DigitalOcean', 'url': 'https://www.digitalocean.com'},
                {'name': 'Netlify', 'url': 'https://www.netlify.com'}
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
            cursor.execute(
                "INSERT OR IGNORE INTO sites (name, url, last_change) VALUES (?, ?, ?)",
                (name, url, time.time()))
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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CoRamTix Hosting - System Status</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .status-container {
            background: rgba(255,255,255,0.99);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 24px 40px rgba(37,99,235,0.08), 0 1.5px 6px rgba(0,0,0,0.03);
            width: 100%;
            max-width: 800px;
            text-align: center;
        }

        .brand {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(45deg, #2563eb, #1e40af 80%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }
        .subtitle{color:#4266b1;font-size:1.1rem;margin-bottom:36px;font-weight:400;letter-spacing:.2px}
        .status-bar{display:flex;gap:4px;justify-content:center;align-items:center;padding:20px 0}
        .status-segment{width:22px;height:40px;border-radius:16px;background:#e5edfd;transition:all .3s;position:relative}
        .status-segment.active{background:linear-gradient(120deg,#36c5f0 0%,#2563eb 100%);box-shadow:0 0 14px #2563eb33;transform:scaleY(1.1)}
        .overall-status{font-size:1.7rem;font-weight:600;margin:20px 0 32px 0;color:#183b77;transition:color .3s}
        .overall-status.operational{color:#36c5f0}
        .overall-status.issues{color:#ef4444}
        .services-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;margin:32px 0}
        .service-card{background:#f7fafe;border-radius:14px;padding:18px;box-shadow:0 4px 12px rgba(37,99,235,.07);border-left:4px solid #e0e7ef;transition:all .2s;text-align:left}
        .service-card.online{border-left-color:#36c5f0}
        .service-card.down{border-left-color:#ef4444}
        .service-card.unknown{border-left-color:#d1d5db}
        .service-card:hover{box-shadow:0 8px 22px rgba(30,64,175,.13);transform:translateY(-3px) scale(1.01)}
        .service-name{font-size:1.1rem;font-weight:600;margin-bottom:7px;color:#16325c}
        .service-status{display:inline-flex;align-items:center;gap:8px;font-weight:500;margin-bottom:10px}
        .status-dot{width:12px;height:12px;border-radius:50%;background:#e5edfd}
        .status-dot.online{background:#2563eb;box-shadow:0 0 7px #2563eb55;animation:pulse-blue 2s infinite}
        .status-dot.down{background:#ef4444;box-shadow:0 0 8px #ef444488;animation:pulse-red 2s infinite}
        .status-dot.unknown{background:#a0aec0}
        @keyframes pulse-blue{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.15);opacity:.85}}
        @keyframes pulse-red{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.18);opacity:.83}}
        .service-details{font-size:.93rem;color:#384c6f;line-height:1.5}
        .uptime{font-weight:600;color:#2563eb}
        .downtime{font-weight:600;color:#ef4444}
        .last-updated{text-align:center;color:#94a3b8;font-size:.89rem;margin-top:25px;padding-top:16px;border-top:1px solid #dbeafe}
        .footer{text-align:center;color:#bacdee;font-size:.84rem;margin-top:14px}
        .summary-stats{display:flex;justify-content:center;gap:34px;margin:14px 0;flex-wrap:wrap}
        .stat-item{text-align:center}
        .stat-number{font-size:1.7rem;font-weight:700;color:#1e40af}
        .stat-number.online{color:#2563eb}
        .stat-number.down{color:#ef4444}
        .stat-label{font-size:.95rem;color:#64748b;margin-top:3px}
        @media(max-width:640px){.status-container{padding:18px}.brand{font-size:1.6rem}.services-grid{grid-template-columns:1fr}.summary-stats{gap:17px}}
    </style>
</head>
<body>
<div class="status-container">
    <div class="brand">CoRamTix Hosting</div>
    <div class="subtitle">System Status Dashboard</div>
    <div class="status-bar-container">
        <div class="status-bar" id="statusBar"></div>
    </div>
    <div class="overall-status operational" id="overallStatus">
        Loading system status...
    </div>
    <div class="summary-stats" id="summaryStats"></div>
    <div class="services-grid" id="servicesGrid"></div>
    <div class="last-updated" id="lastUpdated">
        Last updated: --
    </div>
    <div class="footer">&copy; 2024 CoRamTix Hosting. All Rights Reserved.</div>
</div>

<script>
let isLoading = false;
function generateStatusBar(onlineCount, totalCount) {
    const statusBar = document.getElementById('statusBar');
    const totalSegments = 20;
    const activeSegments = (totalCount === 0) ? 0 : Math.round((onlineCount / totalCount) * totalSegments);
    statusBar.innerHTML = '';
    for (let i = 0; i < totalSegments; i++) {
        const segment = document.createElement('div');
        segment.className = 'status-segment';
        if (i < activeSegments) segment.classList.add('active');
        statusBar.appendChild(segment);
    }
}
function updateOverallStatus(statusText, allOperational) {
    const statusElement = document.getElementById('overallStatus');
    statusElement.textContent = statusText;
    statusElement.className = allOperational ? 'overall-status operational' : 'overall-status issues';
}
function generateSummaryStats(onlineCount, downCount, totalCount) {
    const summaryStats = document.getElementById('summaryStats');
    summaryStats.innerHTML = `
        <div class="stat-item">
            <div class="stat-number online">${onlineCount}</div>
            <div class="stat-label">Online</div>
        </div>
        <div class="stat-item">
            <div class="stat-number down">${downCount}</div>
            <div class="stat-label">Down</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">${totalCount}</div>
            <div class="stat-label">Total Services</div>
        </div>
    `;
}
function generateServiceCards(sites) {
    const grid = document.getElementById('servicesGrid');
    grid.innerHTML = '';
    for (const name in sites) {
        const site = sites[name];
        const card = document.createElement('div');
        const statusClass = site.status.toLowerCase();
        card.className = `service-card ${statusClass}`;
        card.innerHTML = `
            <div class="service-name">${name}</div>
            <div class="service-status">
                <div class="status-dot ${statusClass}"></div>
                ${site.status}
            </div>
            <div class="service-details">
                <div>Uptime: <span class="uptime">${site.uptime_percent}</span></div>
                <div>Total Uptime: <span class="uptime">${site.uptime}</span></div>
                <div>Total Downtime: <span class="downtime">${site.downtime}</span></div>
                <div style="font-style: italic; margin-top: 8px; color: #9ca3af;">
                    Last Checked: ${site.last_checked}
                </div>
            </div>
        `;
        grid.appendChild(card);
    }
}
function updateLastUpdated() {
    const now = new Date();
    document.getElementById('lastUpdated').textContent =
        `Last updated: ${now.toLocaleString()}`;
}
function showError(message) {
    const container = document.querySelector('.status-container');
    const existingError = container.querySelector('.error-message');
    if (existingError) existingError.remove();
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    container.insertBefore(errorDiv, document.getElementById('servicesGrid'));
}
function hideError() {
    const existingError = document.querySelector('.error-message');
    if (existingError) existingError.remove();
}
function setLoadingState(loading) {
    isLoading = loading;
    const container = document.querySelector('.status-container');
    if (loading) container.classList.add('loading');
    else container.classList.remove('loading');
}
function updateStatus() {
    if (isLoading) return;
    setLoadingState(true);
    fetch('/status')
        .then(response => {
            if (!response.ok)
                throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            hideError();
            const total = Object.keys(data.sites).length;
            const online = Object.values(data.sites).filter(site => site.status === 'Online').length;
            const down = Object.values(data.sites).filter(site => site.status === 'Down').length;
            const allOperational = data.overall_status === "All systems operational";
            generateStatusBar(online, total);
            updateOverallStatus(data.overall_status, allOperational);
            generateSummaryStats(online, down, total);
            generateServiceCards(data.sites);
            updateLastUpdated();
            setLoadingState(false);
        })
        .catch(error => {
            console.error('Error fetching status:', error);
            showError('Failed to load system status. Retrying...');
            document.getElementById('overallStatus').textContent = 'Error loading status';
            document.getElementById('overallStatus').className = 'overall-status issues';
            setLoadingState(false);
        });
}
function initializePlaceholder() {
    generateStatusBar(0, 1);
    document.getElementById('summaryStats').innerHTML = `
        <div class="stat-item">
            <div class="stat-number">--</div>
            <div class="stat-label">Online</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">--</div>
            <div class="stat-label">Down</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">--</div>
            <div class="stat-label">Total Services</div>
        </div>
    `;
}
initializePlaceholder();
updateStatus();
setInterval(updateStatus, 5000);
setInterval(updateLastUpdated, 1000);
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
            "uptime_percent": f"{uptime_pct:.2f}%",
            "last_checked": site['last_checked']
        }
    data["overall_status"] = "All systems operational" if all_operational else "Some systems are experiencing issues"
    data["timestamp"] = time.time()
    return jsonify(data)

@app.route("/api/sites")
def get_sites():
    db = get_db()
    cursor = db.cursor()
    sites_data = cursor.execute("SELECT name, url, status, last_checked FROM sites").fetchall()
    sites = []
    for site in sites_data:
        sites.append({
            "name": site['name'],
            "url": site['url'],
            "status": site['status'],
            "last_checked": site['last_checked']
        })
    return jsonify({"sites": sites})

@app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0"
    })

if __name__ == "__main__":
    print("🚀 Starting CoRamTix Status System...")
    print(f"📊 Monitoring {len(SITES)} sites")
    print(f"⏱️  Check interval: {CHECK_INTERVAL} seconds")
    print("🌐 Server will be available at: http://localhost:8080")
    init_db()
    monitoring_thread = threading.Thread(target=check_sites, daemon=True)
    monitoring_thread.start()
    print("✅ Background monitoring started")
    try:
        app.run(host="0.0.0.0", port=8080, debug=False)
    except KeyboardInterrupt:
        print("\n⛔ Shutting down CoRamTix Status System...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
