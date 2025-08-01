from flask import Flask, jsonify
import requests
import threading
import time

app = Flask(__name__)

# List of sites to monitor
sites = {
    "Google": "https://www.google.com",
    "GitHub": "https://github.com",
    "My VPS": "http://your-vps-ip-or-domain"
}

status = {}

# Function to ping all sites
def check_sites():
    while True:
        for name, url in sites.items():
            try:
                response = requests.get(url, timeout=5)
                status[name] = "🟢 Online" if response.status_code == 200 else "🔴 Down"
            except:
                status[name] = "🔴 Down"
        time.sleep(30)  # check every 30 seconds

# Run the checker in the background
threading.Thread(target=check_sites, daemon=True).start()

@app.route("/status")
def get_status():
    return jsonify(status)

@app.route("/")
def home():
    return """
    <html><head><title>Uptime Monitor</title></head>
    <body style='font-family: sans-serif; text-align: center'>
    <h1>🌐 Uptime Monitor</h1>
    <div id="data">Loading...</div>
    <script>
    setInterval(async () => {
        let res = await fetch('/status');
        let json = await res.json();
        document.getElementById('data').innerHTML = 
            Object.entries(json).map(([k, v]) => `<p><b>${k}:</b> ${v}</p>`).join('');
    }, 3000);
    </script>
    </body></html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
