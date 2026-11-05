#!/bin/bash
set -e

echo "=========================================================="
echo " DUIT - Cloud VM Automated Setup (Oracle / DigitalOcean)  "
echo "=========================================================="

# 1. Update OS and install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw iptables-persistent

# 2. Install Docker & Docker Compose plugin if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
fi

# 3. Fix Oracle Cloud iptables (OCI Ubuntu drops ports 80/443 by default)
echo "Configuring firewall for HTTP (80) and HTTPS (443)..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT || true
sudo netfilter-persistent save || true

# Also configure UFW
sudo ufw allow 22/tcp || true
sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
sudo ufw --force enable || true

echo "=========================================================="
echo " Firewall and Docker configured successfully!            "
echo " Next Steps:                                              "
echo " 1. Configure your domain in deploy/.env.prod             "
echo "    echo 'DOMAIN=yourdomain.com' > deploy/.env.prod       "
echo " 2. Launch production stack:                              "
echo "    docker compose -f deploy/docker-compose.prod.yml up -d"
echo "=========================================================="
