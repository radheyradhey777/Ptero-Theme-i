from flask import Flask, jsonify, render_template_string
import requests
import threading
import time

app = Flask(__name__)

# Sites to monitor
sites = {
    "Game Panel": "https://gamep.cloudcrash.shop/",
    "In Node": "https://ccin1.cloudcrash.shop/",
    "Se Node": "http://your-vps-ip-or-domain"
}

status = {}
history = {}

# Initialize site data
for name in sites:
    history[name] = {
        "current_status": "Unknown",
        "last_change": time.time(),
        "total_uptime": 0,
        "total_downtime": 0,
        "last_checked": "Never"
    }

# Time formatter
def format_duration(seconds):
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    return f"{hrs}h {mins}m {secs}s"

# Background checker
def check_sites():
    while True:
        for name, url in sites.items():
            current_time = time.time()
            try:
                res = requests.get(url, timeout=5)
                new_status = "Online" if res.status_code == 200 else "Down"
            except:
                new_status = "Down"

            site_history = history[name]
            old_status = site_history["current_status"]

            # Update total uptime/downtime
            if old_status != "Unknown" and new_status != old_status:
                duration = current_time - site_history["last_change"]
                if old_status == "Online":
                    site_history["total_uptime"] += duration
                else:
                    site_history["total_downtime"] += duration
                site_history["last_change"] = current_time

            site_history["current_status"] = new_status
            site_history["last_checked"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time))
            status[name] = new_status

        time.sleep(10)  # check every 10 seconds

threading.Thread(target=check_sites, daemon=True).start()

@app.route("/status")
def get_status():
    data = {}
    for name, info in history.items():
        data[name] = {
            "status": info["current_status"],
            "uptime": format_duration(info["total_uptime"]),
            "downtime": format_duration(info["total_downtime"]),
            "last_checked": info["last_checked"]
        }
    return jsonify(data)

@app.route("/")
def home():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>CoramTix Monitor</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white font-sans">
        <div class="min-h-screen flex items-center justify-center px-4">
            <div class="w-full max-w-3xl bg-gray-900 p-6 rounded-2xl shadow-2xl border border-gray-700">
                <h1 class="text-3xl font-bold text-center mb-6 text-indigo-400">🌐 CoramTix Uptime Monitor</h1>
                <div id="data" class="space-y-4 text-lg text-white text-center">Loading...</div>
                <p class="mt-6 text-sm text-gray-400 text-center">Auto updates every 10s</p>
            </div>
        </div>

        <script>
        async function updateStatus() {
            const res = await fetch('/status');
            const json = await res.json();
            document.getElementById('data').innerHTML = Object.entries(json).map(([name, info]) => {
                const statusIcon = info.status === "Online" ? "🟢" : "🔴";
                return `<div class="bg-gray-800 rounded-xl p-4 shadow text-left">
                    <div class="flex justify-between items-center">
                        <span class="font-semibold text-xl">${name}</span>
                        <span class="text-xl">${statusIcon} ${info.status}</span>
                    </div>
                    <div class="text-sm text-gray-300 mt-2">
                        <p>🟢 Uptime: ${info.uptime}</p>
                        <p>🔴 Downtime: ${info.downtime}</p>
                        <p>🕒 Last Checked: ${info.last_checked}</p>
                    </div>
                </div>`;
            }).join('');
        }

        setInterval(updateStatus, 10000);
        updateStatus();
        </script>
    </body>
    </html>
    """)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
