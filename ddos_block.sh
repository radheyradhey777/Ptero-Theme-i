#!/bin/bash
# GitHub DDoS IP Blocker
# Blocks malicious IP addresses

if [ -z "$1" ]; then
    echo "Usage: $0 <IP_ADDRESS>"
    exit 1
fi

BLOCK_IP="$1"
BLOCK_LOG="/var/log/github_protection/block.log"
BLOCK_TIME=600  # 10 minutes in seconds

echo "$(date) Blocking IP: $BLOCK_IP" >> "$BLOCK_LOG"

# Check if IP is already blocked
if ! iptables -C INPUT -s "$BLOCK_IP" -j DROP 2>/dev/null; then
    iptables -A INPUT -s "$BLOCK_IP" -j DROP
    echo "$(date) Successfully blocked $BLOCK_IP" >> "$BLOCK_LOG"
    
    # Schedule unblock
    (
        sleep $BLOCK_TIME
        iptables -D INPUT -s "$BLOCK_IP" -j DROP
        echo "$(date) Unblocked $BLOCK_IP" >> "$BLOCK_LOG"
    ) &
else
    echo "$(date) IP $BLOCK_IP already blocked" >> "$BLOCK_LOG"
fi
