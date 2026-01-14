# 🎯 How to Access Admin Dashboard

## Super Simple Steps:

### 1. Make sure you're set as admin in MongoDB:
```javascript
db.users.updateOne(
  { discord_id: "528049173178875924" },
  { $set: { is_admin: true } }
)
```

### 2. Restart your web app and login:
```bash
cd nicole_web_suite_template
python start.py
```

### 3. Look at the TOP RIGHT of your screen:

You should see:
- **Your Discord Profile Picture** (circular)
- **Yellow "Admin" badge** next to it
- Click on your profile picture

### 4. A dropdown menu appears with:
- **👑 Admin Dashboard** ← Click this!
- 🔑 API Settings  
- Logout

## What You'll Get:

The admin dashboard looks exactly like your normal dashboard but with:
- **Yellow/orange theme** (instead of blue/purple)
- **Admin-specific sidebar** with:
  - Dashboard
  - Manage Groups
  - Manage Users
  - Send Broadcast
  - High RPM Discovery
  - Validate Niche
  - Back to User View

- **Same modern UI** - just admin tools instead of user tools

## Switch Back to User View:

Click your profile picture again and select **"🏠 User Dashboard"** or click the "Back to User View" link in the sidebar.

---

That's it! Your Discord account, Discord avatar, everything is preserved. It's just a different view of the same system! 🎉

