# Complete Campaign Testing Guide

## Prerequisites

### 1. Products Created
- Go to `http://127.0.0.1:5000/products`
- You should have "Health Lock" CPA offer created
- If not, create it now

### 2. Flask Server Running
```bash
cd nicole_web_suite_template
python app.py
```

Should see:
```
✅ UGC Production Worker started
🚀 UGC Scheduler started - monitoring active channels
```

## Step-by-Step Testing

### Test 1: Create Campaign

1. **Go to** `http://127.0.0.1:5000/campaigns`
2. **Click** "Create Campaign"
3. **Fill in**:
   - Campaign Name: "Health Lock Affiliate Test"
   - Objective: "Product Sales" or "E-commerce"
   - Budget: $50 (optional)
4. **Click** "Create Campaign"
5. **Verify**: Redirected to campaign dashboard

### Test 2: Add TikTok Channel

1. **In campaign dashboard**, look for buttons at top
2. **Click** "Add TikTok Channel" (black button with 🎵)
3. **Modal opens** with "Add TikTok Channel" title
4. **Fill in form**:
   - **TikTok Username/URL**: `@testaccount` (any username)
   - **Product to Promote**: Select "Health Lock" from dropdown
   - **Avatar Image**: 
     - Upload a file OR
     - Paste URL: `https://i.pravatar.cc/300`
   - **Videos Per Day**: `2` (slider or number input)
   - **Daily Production Spend**: `$5.00`
   - **Content Style**: "UGC Product Video (Script-based)"
5. **Click** "Add Channel"
6. **Verify**: Channel appears in table

**Expected Result:**
```
Channel: @testaccount
Platform: 🎵 TikTok
Status: Active
Videos/Day: 2/day (every 12.0h)
Daily Spend: $5.00
Today's Cost: $0.00
Total Cost: $0.00
Videos: 0
```

### Test 3: Quick Edit Controls

**Change Product:**
1. Click "🛍️ Product" button on channel row
2. Select different product
3. Click Save
4. Verify product name updates

**Change Frequency:**
1. Click "📅 Frequency" button
2. Change to `3` videos per day
3. Click Save
4. Verify shows `3/day (every 8.0h)`

**Change Daily Spend:**
1. Click "💰 Spend" button
2. Enter `$10.00`
3. Click Save
4. Verify Daily Spend column shows `$10.00`

**Change Avatar:**
1. Click "👤 Avatar" button
2. Enter new avatar URL
3. Click Save

### Test 4: Status Controls

**Pause Channel:**
1. Click "⏸️ Pause"
2. Confirm
3. Status should change to "Paused"
4. Scheduler should skip this channel

**Activate Channel:**
1. Click "▶️ Activate"
2. Confirm  
3. Status should change to "Active"
4. Scheduler should pick it up

**Disable Channel:**
1. Click "🚫 Disable"
2. Confirm
3. Status should change to "Disabled"
4. Scheduler should skip permanently

**Re-Enable:**
1. Click "▶️ Enable" (appears when disabled)
2. Status should change to "Active"

### Test 5: Automatic Video Production

**The scheduler checks every hour.** For faster testing:

**Option A: Wait 1 Hour**
- Leave channel Active with product assigned
- Check console logs after 1 hour
- Should see production start

**Option B: Trigger Manually (faster)**
1. Go to `http://127.0.0.1:5000/products`
2. Find Health Lock product
3. Click purple play button "Test UGC"
4. Wait 3-5 minutes
5. Video should generate and upload to Drive

**Expected Console Output:**
```
📊 Checking 1 active social channels
📋 Content style for @testaccount: ugc_video
🎬 Starting UGC production for @testaccount - Health Lock
✅ Using cached analysis for Health Lock
✅ Using saved persona: [Name]
🎬 Using Sora 2 Pro Storyboard (25 seconds)...
✅ Sora Storyboard task created: [task_id]
⏳ Waiting for Sora Storyboard generation...
✅ Found Sora video at: [URL]
✅ Downloaded: X.XX MB (25 seconds)
✅ Uploaded to Google Drive: [URL]
💰 Cost: $0.32 (Today: $0.32, Total: $0.32)
```

**Check Dashboard:**
- Today's Cost: Should show cost
- Total Cost: Should show cost
- Videos: Should increment
- Latest video URL should be in database

### Test 6: Cost Tracking & Budget Limits

**Test Budget Limit:**
1. Set Daily Spend to `$0.50` (less than 2 videos × $0.32)
2. Wait for first video → Should produce ($0.32)
3. Wait for second video → Should be blocked:
   ```
   💰 Daily spend limit reached for @testaccount: $0.32/$0.50
   ```
4. Today's Cost stays at `$0.32`

**Test Daily Reset:**
- At midnight UTC, Today's Cost resets to `$0.00`
- Production resumes next day

### Test 7: OAuth & Auto-Posting

**Setup TikTok OAuth (Optional):**

1. **Register TikTok Developer App:**
   - Go to https://developers.tiktok.com/
   - Create an app
   - Add redirect URI: `http://127.0.0.1:5000/auth/tiktok/callback`
   - Get Client Key and Client Secret

2. **Add to `.env`:**
   ```bash
   TIKTOK_CLIENT_KEY=your_client_key_here
   TIKTOK_CLIENT_SECRET=your_client_secret_here
   TIKTOK_REDIRECT_URI=http://127.0.0.1:5000/auth/tiktok/callback
   ```

3. **Restart Flask server**

4. **Connect Account:**
   - Click "🔗 Connect" button on channel
   - You'll be redirected to TikTok
   - Authorize the app
   - Redirected back to campaign dashboard
   - Button should show "✅ Connected"

5. **Wait for Next Video:**
   - After video generates
   - Should see: `✅ Posted to TikTok: [URL]`
   - Video appears on your TikTok account

## Quick Troubleshooting

**Can't add TikTok channel:**
- ✅ FIXED: MongoDB ObjectId error (was using Discord ID)
- Check browser console for errors
- Check Flask console for "Error adding channel"
- Verify product exists and is selected

**Videos don't generate:**
- Verify channel status is "Active"
- Verify product_id is assigned
- Check scheduler logs (runs every hour)
- Check `tiktok_content_style` is set to `ugc_video`

**Costs don't track:**
- Restart Flask (loads new schema)
- Verify `production_cost` and `total_production_cost` fields exist
- Check scheduler logs for cost updates

**OAuth fails:**
- Verify TikTok app is created and published
- Check `.env` has correct credentials
- Verify redirect URI matches exactly
- Check callback route logs for errors

## What to Expect

### Without OAuth:
- Videos generate every 12 hours (for 2/day setting)
- Upload to Google Drive
- Costs tracked
- Budget limits enforced
- **Manual posting required**

### With OAuth:
- Everything above
- **Plus:** Videos auto-post to TikTok
- Post URLs tracked
- Fully automated!

## Current System Status

✅ **Working:**
- Campaign creation
- Channel addition (MongoDB ID fix applied)
- Product assignment
- Videos/day setting
- Daily spend limits
- Status controls (Pause/Activate/Disable)
- Cost tracking
- UGC video generation (25 seconds)
- Sora 2 Pro Storyboard
- Persona caching (saves $0.01 per video after first)
- Product analysis caching
- Google Drive upload
- Pattern interrupt hooks with variety

❌ **Requires Setup:**
- TikTok OAuth (need developer account)
- Instagram OAuth (need Facebook app)
- Auto-posting (works after OAuth setup)

✅ **Ready to Test:**
You can test everything except auto-posting right now. Videos will generate and upload to Drive automatically!

## Start Testing

**Right now, you can:**
1. Create campaign
2. Add TikTok channel with username `@test`
3. Verify it appears in dashboard
4. Test quick edit buttons
5. Wait for scheduler or use "Test UGC" button
6. Videos will generate and upload to Drive

**The system is ready!** Start by going to `/campaigns` and creating a new campaign.


