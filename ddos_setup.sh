#!/bin/bash
# GitHub DDoS Protection Setup Script
# Installs required dependencies and configures system

# Check root
if [ "$(id -u)" != "0" ]; then
    echo "This script must be run as root" 1>&2
    exit 1
fi

echo "Installing required packages..."
apt-get update
apt-get install -y iptables-persistent net-tools inotify-tools

echo "Creating log directory..."
mkdir -p /var/log/github_protection
chmod 700 /var/log/github_protection

echo "Setting up iptables rules..."
# Basic protection rules
iptables -N GITHUB_PROTECT
iptables -A INPUT -p tcp --dport 80 -j GITHUB_PROTECT
iptables -A INPUT -p tcp --dport 443 -j GITHUB_PROTECT
iptables -A INPUT -p tcp --dport 22 -j GITHUB_PROTECT

# Save iptables rules
iptables-save > /etc/iptables/rules.v4

echo "Installation complete."
echo "Please configure the monitoring scripts with your repository path."
