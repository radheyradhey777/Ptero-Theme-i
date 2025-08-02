import flask
from flask import Flask, jsonify, render_template, g
import requests
import threading
import time
import sqlite3
import yaml
import os
import logging

# --- Basic Setup ---
# This sets up the Flask application and configures logging.
app = Flask(__name__)
DATABASE = 'status_dashboard.db'
CONFIG_FILE = 'config.yaml'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Load Configuration from YAML file ---
def load_config():
    """Reads the config.yaml file to get settings."""
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

config = load_config()
SITES = {site['name']: site['url'] for site in config['sites']}
CHECK_INTERVAL = config['check_interval']
HISTORY_SEGMENTS = config['history_segments']

# --- Database Handling ---
def get_db():
    """Opens a new database connection if one is not already open."""
    db = getattr(g, '_database', None)
    if db is None:
        # check_same_thread=False is needed because the background worker
        # and the web server run in different threads.
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database connection at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database by creating tables if they don't exist."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Main table for site information
        cursor.execute('CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY, name TEXT UNIQUE, url TEXT)')
        # History table for storing every individual check
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY, 
                site_id INTEGER, 
                status TEXT, 
                response_time_ms REAL, 
                timestamp REAL,
                FOREIGN KEY (site_id) REFERENCES sites (id)
            )
        ''')
        # An index makes searching for history faster
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_site_id_timestamp ON check_history (site_id, timestamp DESC)')
        
        # Add sites from the config file to the database
        for name, url in SITES.items():
            cursor.execute("INSERT OR IGNORE INTO sites (name, url) VALUES (?, ?)", (name, url))
        db.commit()
        logging.info("Database initialized successfully.")

# --- Background Worker Thread ---
def check_sites_worker():
    """This function runs in the background to check sites periodically."""
    logging.info(f"Background worker started. Checking sites every {CHECK_INTERVAL} seconds.")
    while True:
        with app.app_context():
            db = get_db()
            sites_to_check = db.execute("SELECT * FROM sites").fetchall()
            
            for site in sites_to_check:
                status, response_time = "Down", -1
                try:
                    # Perform the check
                    res = requests.get(site['url'], timeout=10)
                    response_time = res.elapsed.total_seconds() * 1000
                    status = "Online" if 200 <= res.status_code < 400 else "Down"
                except requests.exceptions.RequestException as e:
                    # If the request fails, mark the site as Down
                    logging.warning(f"Check failed for {site['name']}: {e}")
                
                # Save the result of this check into the database
                db.execute(
                    "INSERT INTO check_history (site_id, status, response_time_ms, timestamp) VALUES (?, ?, ?, ?)",
                    (site['id'], status, response_time, time.time())
                )
            
            # Clean up old data to keep the database from growing too large
            ninety_days_ago = time.time() - (90 * 24 * 60 * 60)
            db.execute("DELETE FROM check_history WHERE timestamp < ?", (ninety_days_ago,))
            db.commit()
            logging.info("Finished checking all sites.")
        
        time.sleep(CHECK_INTERVAL)

# --- API and Web Page Routes ---
@app.route("/")
def home():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.route("/status")
def get_status_api():
    """Provides the status data as a JSON API for the frontend."""
    db = get_db()
    sites_data = db.execute("SELECT * FROM sites").fetchall()
    
    response_data = {"sites": []}
    all_operational = True
    
    ninety_days_ago = time.time() - (90 * 24 * 60 * 60)
    
    for site in sites_data:
        # Calculate uptime percentage over the last 90 days
        uptime_checks = db.execute(
            "SELECT COUNT(*) FROM check_history WHERE site_id = ? AND status = 'Online' AND timestamp > ?",
            (site['id'], ninety_days_ago)
        ).fetchone()[0]
        total_checks = db.execute(
            "SELECT COUNT(*) FROM check_history WHERE site_id = ? AND timestamp > ?",
            (site['id'], ninety_days_ago)
        ).fetchone()[0]
        uptime_percent_90d = f"{(uptime_checks / total_checks * 100):.2f}%" if total_checks > 0 else "100.00%"
        
        # Get the most recent checks to display in the history bar
        history = db.execute(
            "SELECT status, timestamp FROM check_history WHERE site_id = ? ORDER BY timestamp DESC LIMIT ?",
            (site['id'], HISTORY_SEGMENTS)
        ).fetchall()
        
        # The frontend expects the data from oldest to newest for the bar
        history_list = [dict(row) for row in reversed(history)]

        # If the very last check was not 'Online', update the overall status message
        if history and history[0]['status'] != 'Online':
             all_operational = False
        
        response_data["sites"].append({
            "name": site['name'],
            "uptime_percent_90d": uptime_percent_90d,
            "history": history_list
        })
        
    response_data["overall_status"] = "All systems operational." if all_operational else "Some systems are experiencing issues."
    
    return jsonify(response_data)

# --- Main Execution ---
if __name__ == "__main__":
    init_db()
    # Start the background checker in a separate thread so it doesn't block the web server
    threading.Thread(target=check_sites_worker, daemon=True).start()
    # Run the Flask web server
    app.run(host="0.0.0.0", port=8080)

