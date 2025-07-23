#!/bin/bash
# GitHub DDoS Protection Service Manager
# Start/stop/status control for protection services

case "$1" in
    start)
        echo "Starting GitHub DDoS Protection"
        nohup ./github_ddos_monitor.sh >/dev/null 2>&1 &
        echo $! > /var/run/github_ddos.pid
        ;;
    stop)
        echo "Stopping GitHub DDoS Protection"
        kill -9 $(cat /var/run/github_ddos.pid)
        rm /var/run/github_ddos.pid
        ;;
    status)
        if [ -f "/var/run/github_ddos.pid" ]; then
            echo "GitHub DDoS Protection is running (PID: $(cat /var/run/github_ddos.pid))"
        else
            echo "GitHub DDoS Protection is not running"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
