# 🚀 Quick Start Guide - Admin Dashboard

Get your admin dashboard up and running in 5 minutes!

## Step 1: Make Yourself an Admin (MongoDB)

Run this in your MongoDB shell or Compass:

```javascript
// Replace with your Discord ID
db.users.updateOne(
  { discord_id: "YOUR_DISCORD_ID" },
  { $set: { is_admin: true } }
)
```

**Finding your Discord ID:**
1. Go to Discord User Settings
2. Click "Advanced"
3. Enable "Developer Mode"
4. Right-click your name and select "Copy ID"

## Step 2: Start Your Web App

```bash
cd nicole_web_suite_template
python start.py
```

Or if using the clean version:
```bash
python run_clean.py
```

## Step 3: Login and Access

1. Go to `http://localhost:5000` (or your configured URL)
2. Login with Discord OAuth
3. Click your **username in the top right** (you'll see a yellow "Admin" badge)
4. In the dropdown menu, click **"Admin Dashboard"** (with the crown icon 👑)

## Step 4: Explore!

### 🎯 Quick Actions

**View Statistics:**
- See total users, groups, premium users at a glance

**Manage Groups:**
1. Click "Manage Groups"
2. Use filters to find specific groups
3. Click on a group to edit or view details

**Manage Users:**
1. Click "Manage Users"
2. Search by username or Discord ID
3. Click "View" to edit permissions

**Send Broadcast:**
1. Click "Send Broadcast"
2. Write your message
3. Select target audience
4. Preview and send

**View Discovered Channels:**
1. Click "High RPM Discovery"
2. Browse channels found by your crawler
3. Create groups or delete channels

## 🎨 Dashboard Tour

### Main Dashboard
- **Statistics Cards**: Users, Groups, Premium counts
- **Recent Activity**: Latest groups and users
- **Quick Actions**: One-click access to main features

### Group Management
- **Filters**: Public, Private, Premium
- **Search**: Find groups by name
- **Actions**: View, Edit, Delete

### User Management
- **Filters**: Admin, Premium, Beta, Designer
- **Search**: By username or Discord ID
- **Actions**: View, Edit permissions, Grant access

### Broadcast
- **Compose**: Title + Message
- **Target**: All, Premium, Beta, or Free users
- **Preview**: See how it looks before sending

## 🔑 Permission Types

When editing users, you can toggle:

- **Admin** 👑 - Full system access (like you!)
- **Premium** 💎 - Access to premium features
- **Beta** ⭐ - Early access to new features
- **Designer** 🎨 - Access to design tools

## ⚡ Pro Tips

1. **Bookmark** the admin dashboard: `/admin/`
2. **Use keyboard shortcuts** when available
3. **Filter before searching** for better performance
4. **Always preview** broadcasts before sending
5. **Check stats** regularly for growth insights

## 🐛 Troubleshooting

**Can't see "Admin" badge or Admin Dashboard option?**
- Make sure you set `is_admin: true` in MongoDB
- Logout and login again (to refresh your session)
- Clear browser cache
- Check that you see a yellow "Admin" badge next to your username

**Getting "Permission Denied"?**
- Check your database user record
- Verify `is_admin` field is `true` (boolean, not string)
- Ensure you're logged in with the correct account

**Groups/Users not showing?**
- Check your MongoDB connection
- Verify data exists in collections
- Check console for errors

## 📚 Learn More

- **Full Documentation**: See `ADMIN_DASHBOARD.md`
- **Implementation Details**: See `ADMIN_IMPLEMENTATION_SUMMARY.md`
- **Database Methods**: Check `core/database.py`
- **Routes**: Review `dashboard/admin_routes.py`

## 🎉 You're Ready!

You now have full control over your NICOLE platform through an intuitive web interface. Start managing groups, users, and growing your community!

---

**Questions?** Check the main documentation or review the inline code comments.

