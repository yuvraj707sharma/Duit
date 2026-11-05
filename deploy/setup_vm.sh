#!/bin/bash
set -e

echo "=========================================================="
echo " DUIT - Cloud VM Automated Setup (Oracle / DigitalOcean)  "
echo "=========================================================="

# 1. Update OS and install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw iptables-persistent

# 2. Install Docker & Docker Compose via official verified GPG repository
if ! command -v docker &> /dev/null; then
    echo "Installing Docker from verified official apt repository..."
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
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

