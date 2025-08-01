from flask import Flask, jsonify
import requests
import threading
import time

app = Flask(__name__)

# List of sites to monitor
sites = {
    "Game Panel": "https://gamep.cloudcrash.shop/",
    "In Node": "https://ccin1.cloudcrash.shop/",
    "Se Node": "http://your-vps-ip-or-domain"
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
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>CoramTix Uptime</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌐</text></svg>">
    </head>
    <body class="bg-gray-950 text-white font-sans">
        <div class="min-h-screen flex items-center justify-center px-4">
            <div class="w-full max-w-2xl bg-gray-900 p-6 rounded-2xl shadow-2xl border border-gray-700">
                <h1 class="text-3xl font-bold text-center mb-6 text-indigo-400">🌐 CoramTix Uptime</h1>
                <div id="data" class="space-y-4 text-lg text-white text-center">
                    Loading...
                </div>
                <p class="mt-6 text-sm text-gray-400 text-center">Updated every 30 seconds</p>
            </div>
        </div>

        <script>
        async function updateStatus() {
            const res = await fetch('/status');
            const json = await res.json();
            document.getElementById('data').innerHTML = Object.entries(json).map(([k, v]) => {
                let statusIcon = v.includes("Online") ? "🟢" : "🔴";
                return `<div class="bg-gray-800 rounded-xl p-4 shadow flex justify-between items-center">
                    <span class="font-semibold">${k}</span>
                    <span class="text-xl">${statusIcon} ${v.replace("🟢", "").replace("🔴", "")}</span>
                </div>`;
            }).join('');
        }

        setInterval(updateStatus, 3000);
        updateStatus();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
