# 🚀 VPS Deployment Guide for Nicole Web Suite

## Quick Start (5 minutes)

### Step 1: Upload Project to VPS

**Option A: Using Git (Recommended)**
```bash
ssh your-user@your-vps-ip
cd /var/www
sudo git clone https://github.com/your-repo/nicole_web_suite.git
sudo chown -R $USER:$USER nicole_web_suite
```

**Option B: Using SCP/SFTP**
```bash
# From your local machine
scp -r nicole_web_suite_template/ your-user@your-vps-ip:/var/www/nicole_web_suite/
```

**Option C: Using FileZilla/WinSCP**
- Connect to your VPS
- Navigate to `/var/www/`
- Upload the `nicole_web_suite_template` folder

---

### Step 2: Run the Setup Script

```bash
ssh your-user@your-vps-ip
cd /var/www/nicole_web_suite/nicole_web_suite_template
chmod +x deploy/setup_vps.sh
./deploy/setup_vps.sh
```

The script will:
- Install system dependencies (nginx, python, ffmpeg, etc.)
- Create Python virtual environment
- Install all Python packages
- Set up Nginx configuration
- Create systemd service

---

### Step 3: Configure Environment Variables

```bash
sudo nano /var/www/nicole_web_suite/nicole_web_suite_template/.env
```

**Required variables:**
```
# Flask
SECRET_KEY=your-random-secret-key-here

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/niche_research

# AI (for group creation analysis)
ANTHROPIC_API_KEY=sk-ant-xxxxx

# YouTube (for channel data)
YOUTUBE_API_KEY=AIzaxxxxx

# Discord OAuth (REQUIRED for login)
DISCORD_CLIENT_ID=your-discord-app-client-id
DISCORD_CLIENT_SECRET=your-discord-app-client-secret
DISCORD_REDIRECT_URI=https://yourdomain.com/auth/discord/callback
OWNER_DISCORD_ID=your-discord-user-id
```

Save and exit: `Ctrl+X`, then `Y`, then `Enter`

### Step 3b: Configure Discord OAuth

1. Go to https://discord.com/developers/applications
2. Create a new application (or use existing)
3. Go to OAuth2 → General
4. Add redirect URL: `https://yourdomain.com/auth/discord/callback`
   - For IP access: `http://YOUR_VPS_IP/auth/discord/callback`
5. Copy Client ID and Client Secret to your `.env` file

---

### Step 4: Start Everything

```bash
# Start the application
sudo systemctl start nicole
sudo systemctl enable nicole  # Start on boot

# Start nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status nicole
```

---

### Step 5: Set Up SSL (if using domain)

First, make sure your domain's DNS A record points to your VPS IP.

```bash
sudo certbot --nginx -d yourdomain.com
```

Follow the prompts. Certbot will automatically configure HTTPS.

---

## Useful Commands

```bash
# View application logs
sudo journalctl -u nicole -f

# View nginx logs
sudo tail -f /var/log/nginx/error.log

# Restart application
sudo systemctl restart nicole

# Stop application
sudo systemctl stop nicole

# Check if app is running
sudo systemctl status nicole

# Check nginx status
sudo systemctl status nginx
```

---

## Troubleshooting

### App won't start
```bash
# Check logs
sudo journalctl -u nicole -n 100

# Try running manually to see errors
cd /var/www/nicole_web_suite/nicole_web_suite_template
source venv/bin/activate
python -c "from app import create_app; app = create_app(); print('OK')"
```

### 502 Bad Gateway
- App isn't running: `sudo systemctl start nicole`
- Check if port 5000 is in use: `sudo lsof -i :5000`
- Check app logs: `sudo journalctl -u nicole -f`

### Permission errors
```bash
sudo chown -R www-data:www-data /var/www/nicole_web_suite
sudo chmod -R 755 /var/www/nicole_web_suite
```

### MongoDB connection fails
- Check if your VPS IP is whitelisted in MongoDB Atlas
- Go to Atlas → Network Access → Add your VPS IP or allow 0.0.0.0/0

### Static files not loading
```bash
# Check nginx config
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

---

## Updating the Application

```bash
cd /var/www/nicole_web_suite/nicole_web_suite_template

# If using git
git pull origin main

# Reinstall dependencies (if requirements changed)
source venv/bin/activate
pip install -r requirements.txt

# Restart
sudo systemctl restart nicole
```

---

## Security Recommendations

1. **Firewall Setup**
```bash
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

2. **Fail2ban** (blocks brute force)
```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

3. **Auto-update SSL certificates** (certbot does this automatically)

4. **Regular backups** of your `.env` file and MongoDB database

---

## Resource Requirements

- **Minimum**: 1 CPU, 2GB RAM, 20GB storage
- **Recommended**: 2 CPU, 4GB RAM, 40GB storage
- **For heavy video processing**: 4 CPU, 8GB RAM

---

## Support

If you run into issues:
1. Check the logs first: `sudo journalctl -u nicole -f`
2. Make sure all environment variables are set
3. Verify MongoDB connection from VPS
