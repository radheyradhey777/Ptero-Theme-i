import yaml
import requests
import time
from flask import Flask, render_template, jsonify

# Initialize the Flask application
app = Flask(__name__, template_folder='.')

def load_config():
    """Loads the list of monitors from the config.yaml file."""
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    return config.get('monitors', [])

def check_site(monitor):
    """
    Checks a single site's status, status code, and latency.
    Returns a dictionary with the results.
    """
    result = {
        'name': monitor['name'],
        'url': monitor['url'],
        'status': 'Down',
        'status_code': None,
        'latency_ms': None
    }
    try:
        start_time = time.time()
        # Set a timeout to prevent the check from hanging indefinitely
        response = requests.get(monitor['url'], timeout=10)
        end_time = time.time()

        # Calculate latency in milliseconds
        latency = (end_time - start_time) * 1000
        result['latency_ms'] = f"{latency:.0f}"
        result['status_code'] = response.status_code

        # Consider any 2xx or 3xx status code as 'Up'
        if 200 <= response.status_code < 400:
            result['status'] = 'Up'
        else:
            result['status'] = 'Down'

    except requests.exceptions.RequestException as e:
        # Handle network errors (e.g., DNS failure, connection refused)
        result['status'] = 'Error'
        # To keep the UI clean, we can truncate the long error message
        result['status_code'] = str(e.__class__.__name__)

    return result

@app.route('/')
def index():
    """Renders the main HTML page."""
    # The actual data loading will be done via JavaScript (AJAX)
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """
    API endpoint that returns the status of all monitored sites as JSON.
    This is called by the frontend to get real-time data.
    """
    monitors = load_config()
    results = [check_site(monitor) for monitor in monitors]
    return jsonify(results)

if __name__ == '__main__':
    # Run the app in debug mode for development
    # For production, use a proper WSGI server like Gunicorn or Waitress
    app.run(host='0.0.0.0', port=5000, debug=True)

