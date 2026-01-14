#!/bin/bash
# =============================================================================
# Nicole Web Suite - VPS Deployment Script
# Run this on your VPS after uploading the project
# =============================================================================

set -e  # Exit on any error

echo "=========================================="
echo "  Nicole Web Suite - VPS Setup"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration - EDIT THESE
APP_NAME="nicole"
APP_DIR="/var/www/nicole_web_suite"
DOMAIN=""  # Will be set interactively

# Get domain from user
echo ""
read -p "Enter your domain (e.g., app.yourdomain.com) or press Enter for IP-only: " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo -e "${YELLOW}No domain entered - will configure for IP access only${NC}"
fi

echo ""
echo -e "${GREEN}Step 1: Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev nginx certbot python3-certbot-nginx ffmpeg git curl

echo ""
echo -e "${GREEN}Step 2: Creating application directory...${NC}"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

echo ""
echo -e "${GREEN}Step 3: Setting up Python virtual environment...${NC}"
cd $APP_DIR/nicole_web_suite_template
python3 -m venv venv
source venv/bin/activate

echo ""
echo -e "${GREEN}Step 4: Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo ""
echo -e "${GREEN}Step 5: Creating .env file template...${NC}"
if [ ! -f .env ]; then
    cp deploy/env.template .env
    echo -e "${YELLOW}IMPORTANT: Edit .env file with your actual values!${NC}"
    echo "Run: nano $APP_DIR/nicole_web_suite_template/.env"
else
    echo ".env file already exists, skipping..."
fi

echo ""
echo -e "${GREEN}Step 6: Setting up Nginx...${NC}"
sudo cp deploy/nginx.conf /etc/nginx/sites-available/$APP_NAME

# Replace placeholders in nginx config
if [ -n "$DOMAIN" ]; then
    sudo sed -i "s/YOUR_DOMAIN_OR_IP/$DOMAIN/g" /etc/nginx/sites-available/$APP_NAME
else
    # Get server IP
    SERVER_IP=$(curl -s ifconfig.me)
    sudo sed -i "s/YOUR_DOMAIN_OR_IP/$SERVER_IP/g" /etc/nginx/sites-available/$APP_NAME
fi

sudo sed -i "s|APP_DIR_PLACEHOLDER|$APP_DIR/nicole_web_suite_template|g" /etc/nginx/sites-available/$APP_NAME

# Enable site
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Remove default site

# Test nginx config
sudo nginx -t

echo ""
echo -e "${GREEN}Step 7: Setting up systemd service...${NC}"
sudo cp deploy/nicole.service /etc/systemd/system/
sudo sed -i "s|APP_DIR_PLACEHOLDER|$APP_DIR/nicole_web_suite_template|g" /etc/systemd/system/nicole.service
sudo systemctl daemon-reload

echo ""
echo -e "${GREEN}Step 8: Setting permissions...${NC}"
sudo chown -R www-data:www-data $APP_DIR
sudo chmod -R 755 $APP_DIR

# Create logs directory
sudo mkdir -p $APP_DIR/nicole_web_suite_template/logs
sudo chown www-data:www-data $APP_DIR/nicole_web_suite_template/logs

echo ""
echo "=========================================="
echo -e "${GREEN}  Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit your .env file with real values:"
echo "   sudo nano $APP_DIR/nicole_web_suite_template/.env"
echo ""
echo "2. Start the application:"
echo "   sudo systemctl start nicole"
echo "   sudo systemctl enable nicole"
echo ""
echo "3. Start Nginx:"
echo "   sudo systemctl restart nginx"
echo ""
if [ -n "$DOMAIN" ]; then
    echo "4. Set up SSL (after DNS is configured):"
    echo "   sudo certbot --nginx -d $DOMAIN"
    echo ""
    echo "Your app will be available at: https://$DOMAIN"
else
    SERVER_IP=$(curl -s ifconfig.me)
    echo "Your app will be available at: http://$SERVER_IP"
fi
echo ""
echo "Useful commands:"
echo "  View logs:    sudo journalctl -u nicole -f"
echo "  Restart app:  sudo systemctl restart nicole"
echo "  App status:   sudo systemctl status nicole"
echo ""
