# Quick Start - Deploy to Vercel in 5 Minutes

## First Time Setup

### 1. Install Vercel CLI
```bash
npm install -g vercel
```

### 2. Login to Vercel
```bash
vercel login
```

### 3. Initial Deploy
Double-click **`deploy.bat`** or run:
```bash
vercel --prod
```

Vercel will ask you some questions:
- **Set up and deploy?** → Yes
- **Which scope?** → Your account/team
- **Link to existing project?** → No
- **What's your project's name?** → nicole-web-suite (or your choice)
- **In which directory is your code located?** → ./

### 4. Add Environment Variables

Go to your Vercel dashboard:
1. Click on your project
2. Go to **Settings** → **Environment Variables**
3. Add these required variables:

```
SECRET_KEY=your-secret-key-here
MONGODB_URI=mongodb+srv://...
ANTHROPIC_API_KEY=your-anthropic-key
YOUTUBE_API_KEY=your-youtube-key
OWNER_ID=your-discord-id
```

Click **Save** and **Redeploy** your project.

---

## Future Deployments

Just double-click **`deploy.bat`** - that's it! 🚀

---

## Testing Before Production

Want to test changes first?
- Double-click **`deploy-preview.bat`** to deploy to a preview URL
- Test your changes
- If good, run **`deploy.bat`** to push to production

---

## Troubleshooting

### "vercel: command not found"
Install the Vercel CLI:
```bash
npm install -g vercel
```

### "Authentication error"
Login to Vercel:
```bash
vercel login
```

### Build fails
Check the full deployment guide: **VERCEL_DEPLOYMENT.md**

---

Need detailed instructions? See **VERCEL_DEPLOYMENT.md**

