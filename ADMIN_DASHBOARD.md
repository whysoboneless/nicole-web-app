# Admin Dashboard Documentation

## Overview

The Admin Dashboard provides comprehensive administrative controls for managing NICOLE's web interface. It mirrors the functionality from the Discord bot's admin dashboard but in a web-based format.

## Features

### 1. **Dashboard Home** (`/admin/`)
The main admin dashboard displays:
- Total Users
- Total Groups
- Public/Private Group counts
- Premium/Beta user counts
- Recent groups and users
- Quick action buttons for common tasks

### 2. **Group Management** (`/admin/groups`)
Manage all competitor groups:
- View all groups (public and private)
- Filter by type (public/private/premium)
- Search by name
- Edit group settings
- Delete groups
- Create new groups from the dashboard

**Features:**
- Set group visibility (public/private)
- Set premium status and pricing
- Configure Whop product IDs
- View subscriber lists
- View competitor channels

### 3. **User Management** (`/admin/users`)
Comprehensive user administration:
- View all users
- Filter by role (admin/premium/beta/designer)
- Search by username or Discord ID
- View user details and activity
- Edit user permissions
- Grant group access to specific users

**Permissions you can manage:**
- Admin status
- Premium status
- Beta tester status
- Thumbnail Designer status

### 4. **Broadcast Messages** (`/admin/broadcast`)
Send announcements to users:
- Compose broadcast messages
- Target specific user groups (all/premium/beta/free)
- Live preview of messages
- Confirmation before sending

### 5. **High RPM Discovery** (`/admin/discovery`)
View and manage discovered channels:
- View high-potential channels found by the crawler
- See channel metrics (revenue, views, RPM, age)
- Create groups from discovered channels
- Delete individual channels or clear all

### 6. **Niche Validator** (`/admin/validate-niche`)
Validate YouTube niches:
- Enter a channel URL
- Get niche qualification analysis
- View similar successful channels
- See series and themes
- Determine if niche is profitable

## Access Control

Only users with `is_admin = True` can access the admin dashboard.

### Granting Admin Access

Using MongoDB directly:
```javascript
db.users.updateOne(
  { discord_id: "USER_DISCORD_ID" },
  { $set: { is_admin: true } }
)
```

Or use the admin dashboard itself (if you already have one admin):
1. Go to Admin > Manage Users
2. Find the user
3. Click "View"
4. Toggle "Admin" permission
5. Save changes

## Navigation

When logged in as an admin, you'll see a new "Admin" section in the left sidebar with a link to the Admin Dashboard.

## API Endpoints

The admin dashboard uses these API endpoints:

- `GET /admin/api/statistics` - Get dashboard statistics
- `GET /admin/api/groups` - Get all groups for dropdowns
- `POST /admin/api/validate-niche` - Validate a niche (future implementation)

## Security

All admin routes are protected by the `@admin_required` decorator which:
1. Checks if user is authenticated
2. Verifies user has `is_admin = True`
3. Redirects unauthorized users to the main dashboard

## Database Methods

New synchronous methods added for admin operations:

```python
# Group methods
get_all_groups_sync(include_private=False)
get_group_by_id_sync(group_id, full_document=False)
update_group_sync(group_id, update_data)
delete_group_sync(group_id)

# User methods
get_all_users_sync()
get_user_by_id_sync(user_id)
update_user_sync(user_id, update_data)
assign_private_group_to_user_sync(user_id, group_id)

# Channel discovery methods
get_high_potential_channels_sync()
delete_high_potential_channel_sync(channel_id)
clear_high_potential_channels_sync()
```

## Templates

Admin dashboard templates are located in `templates/admin/`:

- `dashboard.html` - Main admin dashboard
- `manage_groups.html` - Group management interface
- `view_group.html` - Individual group details
- `manage_users.html` - User management interface
- `view_user.html` - Individual user details
- `broadcast.html` - Broadcast message composer
- `high_rpm_discovery.html` - Channel discovery interface
- `validate_niche.html` - Niche validation tool

## Customization

### Styling
All templates extend `modern_base.html` and use Bootstrap 5 for styling. The design matches the modern UI of the main dashboard.

### Adding New Features

1. Add route in `dashboard/admin_routes.py`
2. Create template in `templates/admin/`
3. Add navigation link if needed
4. Implement any required database methods

## Troubleshooting

**"You do not have permission to access this page"**
- User needs `is_admin = True` in the database
- Check the user's permissions in MongoDB

**Admin link not showing in sidebar**
- Check that `current_user.is_admin` is True
- Clear browser cache and reload

**500 errors on admin pages**
- Check server logs for detailed errors
- Verify MongoDB connection
- Ensure all required database methods are available

## Future Enhancements

Planned features:
- Real-time analytics dashboard
- User activity logs
- Automated reports
- Group analytics
- Batch operations for user management
- Email notification system
- Advanced search and filtering

## Support

For issues or questions about the admin dashboard, refer to the main README or contact the development team.

