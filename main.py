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
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CoRamTix Hosting - System Status</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }

            .status-container {
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(20px);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                width: 100%;
                max-width: 800px;
                text-align: center;
            }

            .brand {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 10px;
            }

            .subtitle {
                color: #666;
                font-size: 1.1rem;
                margin-bottom: 40px;
                font-weight: 400;
            }

            .status-bar-container {
                margin: 30px 0;
                padding: 0 20px;
            }

            .status-bar {
                display: flex;
                gap: 4px;
                justify-content: center;
                align-items: center;
                padding: 20px 0;
            }

            .status-segment {
                width: 20px;
                height: 40px;
                border-radius: 20px;
                background: #e2e8f0;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }

            .status-segment.active {
                background: linear-gradient(135deg, #10b981, #34d399);
                box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
                transform: scaleY(1.1);
            }

            .status-segment::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(45deg, rgba(255, 255, 255, 0.3), transparent);
                opacity: 0;
                transition: opacity 0.3s ease;
            }

            .status-segment.active::before {
                opacity: 1;
            }

            .overall-status {
                font-size: 1.8rem;
                font-weight: 600;
                margin: 30px 0;
                color: #1f2937;
            }

            .overall-status.operational {
                color: #10b981;
            }

            .overall-status.issues {
                color: #ef4444;
            }

            .services-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 20px;
                margin: 40px 0;
            }

            .service-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                border-left: 4px solid #e2e8f0;
                transition: all 0.3s ease;
                text-align: left;
            }

            .service-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            }

            .service-card.online {
                border-left-color: #10b981;
            }

            .service-card.down {
                border-left-color: #ef4444;
            }

            .service-card.unknown {
                border-left-color: #9ca3af;
            }

            .service-name {
                font-size: 1.2rem;
                font-weight: 600;
                margin-bottom: 8px;
                color: #1f2937;
            }

            .service-status {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                font-weight: 500;
                margin-bottom: 12px;
            }

            .status-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #e2e8f0;
            }

            .status-dot.online {
                background: #10b981;
                box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
                animation: pulse-green 2s infinite;
            }

            .status-dot.down {
                background: #ef4444;
                box-shadow: 0 0 8px rgba(239, 68, 68, 0.4);
                animation: pulse-red 2s infinite;
            }

            .status-dot.unknown {
                background: #9ca3af;
            }

            @keyframes pulse-green {
                0%, 100% { transform: scale(1); opacity: 1; }
                50% { transform: scale(1.2); opacity: 0.8; }
            }

            @keyframes pulse-red {
                0%, 100% { transform: scale(1); opacity: 1; }
                50% { transform: scale(1.2); opacity: 0.8; }
            }

            .service-details {
                font-size: 0.9rem;
                color: #6b7280;
                line-height: 1.6;
            }

            .service-details div {
                margin-bottom: 4px;
            }

            .uptime {
                font-weight: 600;
                color: #10b981;
            }

            .downtime {
                font-weight: 600;
                color: #ef4444;
            }

            .last-updated {
                text-align: center;
                color: #9ca3af;
                font-size: 0.9rem;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e5e7eb;
            }

            .footer {
                text-align: center;
                color: #9ca3af;
                font-size: 0.85rem;
                margin-top: 20px;
            }

            .loading {
                opacity: 0.6;
                pointer-events: none;
            }

            .error-message {
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #991b1b;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                text-align: center;
            }

            .summary-stats {
                display: flex;
                justify-content: center;
                gap: 30px;
                margin: 20px 0;
                flex-wrap: wrap;
            }

            .stat-item {
                text-align: center;
            }

            .stat-number {
                font-size: 2rem;
                font-weight: 700;
                color: #1f2937;
            }

            .stat-label {
                font-size: 0.9rem;
                color: #6b7280;
                margin-top: 4px;
            }

            .stat-number.online {
                color: #10b981;
            }

            .stat-number.down {
                color: #ef4444;
            }

            @media (max-width: 640px) {
                .status-container {
                    padding: 20px;
                }
                
                .brand {
                    font-size: 2rem;
                }
                
                .services-grid {
                    grid-template-columns: 1fr;
                }
                
                .summary-stats {
                    gap: 20px;
                }
            }
        </style>
    </head>
    <body>
        <div class="status-container">
            <div class="brand">CoRamTix Hosting</div>
            <div class="subtitle">System Status Dashboard</div>
            
            <div class="status-bar-container">
                <div class="status-bar" id="statusBar">
                    <!-- Status segments will be generated by JavaScript -->
                </div>
            </div>
            
            <div class="overall-status operational" id="overallStatus">
                Loading system status...
            </div>

            <div class="summary-stats" id="summaryStats">
                <!-- Summary statistics will be generated by JavaScript -->
            </div>
            
            <div class="services-grid" id="servicesGrid">
                <!-- Service cards will be generated by JavaScript -->
            </div>
            
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
                const activeSegments = totalCount === 0 ? 0 : Math.round((onlineCount / totalCount) * totalSegments);
                
                statusBar.innerHTML = '';
                
                for (let i = 0; i < totalSegments; i++) {
                    const segment = document.createElement('div');
                    segment.className = 'status-segment';
                    
                    if (i < activeSegments) {
                        segment.classList.add('active');
                    }
                    
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
                if (existingError) {
                    existingError.remove();
                }
                
                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-message';
                errorDiv.textContent = message;
                container.insertBefore(errorDiv, document.getElementById('servicesGrid'));
            }

            function hideError() {
                const existingError = document.querySelector('.error-message');
                if (existingError) {
                    existingError.remove();
                }
            }

            function setLoadingState(loading) {
                isLoading = loading;
                const container = document.querySelector('.status-container');
                if (loading) {
                    container.classList.add('loading');
                } else {
                    container.classList.remove('loading');
                }
            }

            function updateStatus() {
                if (isLoading) return;
                
                setLoadingState(true);
                
                fetch('/status')
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        hideError();
                        
                        const total = Object.keys(data.sites).length;
                        const online = Object.values(data.sites).filter(site => site.status === 'Online').length;
                        const down = Object.values(data.sites).filter(site => site.status === 'Down').length;
                        const allOperational = data.overall_status === "All systems operational";
                        
                        // Update status bar
                        generateStatusBar(online, total);
                        
                        // Update overall status
                        updateOverallStatus(data.overall_status, allOperational);
                        
                        // Update summary stats
                        generateSummaryStats(online, down, total);
                        
                        // Update service cards
                        generateServiceCards(data.sites);
                        
                        // Update timestamp
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
                // Show loading state initially
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

            // Initialize dashboard
            initializePlaceholder();
            updateStatus();
            
            // Update every 5 seconds (matching your original interval)
            setInterval(updateStatus, 5000);
            
            // Update timestamp every second for real-time feel
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
    """API endpoint to get all monitored sites"""
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
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0"
    })

if __name__ == "__main__":
    print("🚀 Starting CoRamTix Status System...")
    print(f"📊 Monitoring {len(SITES)} sites")
    print(f"⏱️  Check interval: {CHECK_INTERVAL} seconds")
    print(f"🌐 Server will be available at: http://localhost:8080")
    
    init_db()
    
    # Start the background site checking thread
    monitoring_thread = threading.Thread(target=check_sites, daemon=True)
    monitoring_thread.start()
    print("✅ Background monitoring started")
    
    # Start the Flask app
    try:
        app.run(host="0.0.0.0", port=8080, debug=False)
    except KeyboardInterrupt:
        print("\n⛔ Shutting down CoRamTix Status System...")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
