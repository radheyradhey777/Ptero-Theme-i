#!/bin/bash
# GitHub DDoS Protection Report Generator
# Creates daily reports of blocked attacks

REPORT_DIR="/var/log/github_protection/reports"
mkdir -p "$REPORT_DIR"
TODAY=$(date +%Y-%m-%d)
REPORT_FILE="$REPORT_DIR/report_$TODAY.txt"

echo "GitHub DDoS Protection Daily Report - $TODAY" > "$REPORT_FILE"
echo "==========================================" >> "$REPORT_FILE"

# Summary of blocked IPs
echo -e "\nBlocked IP Addresses:" >> "$REPORT_FILE"
grep "Blocking IP" /var/log/github_protection/block.log | \
    awk '{print $1,$2,$6}' | sort | uniq -c >> "$REPORT_FILE"

# Traffic statistics
echo -e "\nTraffic Statistics:" >> "$REPORT_FILE"
echo "Top 10 IPs by request volume:" >> "$REPORT_FILE"
netstat -ntu | awk '{print $5}' | cut -d: -f1 | sort | uniq -c | \
    sort -nr | head -10 >> "$REPORT_FILE"

# System status
echo -e "\nSystem Status:" >> "$REPORT_FILE"
echo "Memory Usage:" >> "$REPORT_FILE"
free -h >> "$REPORT_FILE"
echo -e "\nCPU Load:" >> "$REPORT_FILE"
uptime >> "$REPORT_FILE"

echo -e "\nReport generated at $(date)" >> "$REPORT_FILE"
