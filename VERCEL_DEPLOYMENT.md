# Deploy Nicole Web Suite to Vercel

## Prerequisites
1. A [Vercel account](https://vercel.com/signup)
2. [Vercel CLI](https://vercel.com/docs/cli) installed (optional but recommended)
3. Your MongoDB connection string
4. All required API keys (Anthropic, YouTube, etc.)

## Quick Deploy via Vercel Dashboard

### Step 1: Install Vercel CLI (Optional)
```bash
npm install -g vercel
```

### Step 2: Navigate to project directory
```bash
cd nicole_web_suite_template
```

### Step 3: Deploy
```bash
vercel
```

Or deploy via the Vercel Dashboard:
1. Go to https://vercel.com/new
2. Import your Git repository (GitHub/GitLab/Bitbucket)
3. Select the `nicole_web_suite_template` directory as root
4. Configure environment variables (see below)
5. Click **Deploy**

## Environment Variables

Add these environment variables in your Vercel project settings:

### Required Variables
```
SECRET_KEY=your-secret-key-here
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/database
FLASK_ENV=production
```

### API Keys (Add as needed)
```
ANTHROPIC_API_KEY=your-anthropic-key
YOUTUBE_API_KEY=your-youtube-key
OPENAI_API_KEY=your-openai-key
REPLICATE_API_TOKEN=your-replicate-token
OWNER_ID=your-discord-id
```

### Discord Bot (if using)
```
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_CLIENT_ID=your-client-id
DISCORD_CLIENT_SECRET=your-client-secret
```

## Setting Environment Variables

### Via Vercel CLI
```bash
vercel env add SECRET_KEY
vercel env add MONGODB_URI
vercel env add ANTHROPIC_API_KEY
# ... add all required variables
```

### Via Vercel Dashboard
1. Go to your project on Vercel
2. Click **Settings** → **Environment Variables**
3. Add each variable with:
   - **Name**: Variable name (e.g., `SECRET_KEY`)
   - **Value**: Your actual value
   - **Environment**: Select `Production`, `Preview`, and `Development`

## Post-Deployment Configuration

### 1. MongoDB Connection
- Ensure your MongoDB cluster allows connections from Vercel's IP ranges
- In MongoDB Atlas: **Network Access** → **Add IP Address** → **Allow Access from Anywhere** (or add Vercel IPs)

### 2. File Uploads (Important!)
Vercel serverless functions have a **10MB limit** for file uploads and responses. For video/image processing:
- Consider using external storage (S3, Cloudinary, etc.)
- Or use Vercel Blob Storage: https://vercel.com/docs/storage/vercel-blob

### 3. Background Jobs
Vercel functions have a **10-second execution limit** on Hobby plan, **60 seconds** on Pro.
- Long-running tasks (video generation, analysis) should use:
  - Vercel Cron Jobs
  - External queue service (AWS SQS, Redis Queue)
  - Webhook callbacks

## Troubleshooting

### Build Errors
If you get build errors:
1. Check that all dependencies in `requirements.txt` are compatible with Python 3.9+
2. Some packages (like `opencv-python`) may need the headless version: `opencv-python-headless`

Update `requirements.txt` if needed:
```bash
# Replace opencv-python with headless version
opencv-python-headless==4.8.1.78
```

### Function Timeout
If requests timeout:
1. Check Vercel function logs: **Deployments** → Select deployment → **Functions** tab
2. Optimize long-running operations
3. Consider upgrading to Vercel Pro for longer timeouts

### Static Files Not Loading
- Ensure `vercel.json` routes are correct
- Clear browser cache
- Check Vercel deployment logs

## Custom Domain

1. Go to **Settings** → **Domains**
2. Add your custom domain
3. Configure DNS records as instructed by Vercel

## Monitoring

- **Logs**: Vercel Dashboard → Your Project → Deployments → Select deployment → View Function Logs
- **Analytics**: Enable Vercel Analytics in project settings
- **Alerts**: Set up monitoring via Vercel integrations

## Development Workflow

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py

# Deploy to Vercel preview
vercel

# Deploy to production
vercel --prod
```

### Quick Deploy (Windows)

**Double-click to deploy:**
- **`deploy.bat`** - Deploy to production instantly
- **`deploy-preview.bat`** - Deploy to preview environment for testing

These batch files automatically:
1. Navigate to the correct directory
2. Run the Vercel CLI command
3. Show deployment progress
4. Pause so you can see the results

## Need Help?
- [Vercel Python Docs](https://vercel.com/docs/concepts/functions/serverless-functions/runtimes/python)
- [Flask on Vercel Guide](https://vercel.com/guides/using-flask-with-vercel)

