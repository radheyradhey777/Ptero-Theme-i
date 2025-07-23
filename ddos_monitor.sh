#!/bin/bash
# GitHub Repository DDoS Monitor
# Monitors traffic and logs suspicious activity

LOG_DIR="/var/log/github_protection"
mkdir -p "$LOG_DIR"
MONITOR_LOG="$LOG_DIR/monitor.log"
TRAFFIC_LOG="$LOG_DIR/traffic.log"

# Configuration
GITHUB_REPO="/path/to/your/repo"  # Set your repo path
ALERT_THRESHOLD=100  # Requests per minute to trigger alert

echo "$(date) Starting GitHub DDoS Monitor" >> "$MONITOR_LOG"

# Continuous monitoring loop
while true; do
    # Log current connections
    netstat -ntu | awk '{print $5}' | cut -d: -f1 | sort | uniq -c >> "$TRAFFIC_LOG"
    
    # Check for suspicious activity
    while read -r line; do
        req=$(echo "$line" | awk '{print $1}')
        ip=$(echo "$line" | awk '{print $2}')
        
        if [ "$req" -gt "$ALERT_THRESHOLD" ]; then
            echo "$(date) ALERT: High traffic from $ip ($req requests)" >> "$MONITOR_LOG"
            ./github_ddos_block.sh "$ip"
        fi
    done <<< "$(netstat -ntu | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | sort -nr)"
    
    sleep 60
done
