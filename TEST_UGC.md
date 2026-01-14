# 🧪 How to Test UGC Production

## Quick Test (Using Browser Console)

1. **Go to Products page** (`/products`)
2. **Note a product ID** from the list
3. **Open browser console** (F12)
4. **Run this code:**

```javascript
fetch('/campaigns/test-ugc-production', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        product_id: 'YOUR_PRODUCT_ID_HERE',
        avatar_url: 'https://i.pravatar.cc/300'  // Random avatar
    })
})
.then(r => r.json())
.then(data => {
    console.log('✅ UGC Production Result:', data);
    if (data.success) {
        alert('Video generated! Drive URL: ' + data.video_url);
        window.open(data.video_url, '_blank');
    } else {
        alert('Error: ' + data.error);
    }
});
```

## What Happens:

1. **Analyzes product** (physical or CPA offer)
2. **Generates persona** (ideal UGC creator)
3. **Writes script** (following anti-ad framework)
4. **Creates first frame** (720x1280 adapted image)
5. **Generates video** (Sora 2 - takes 2-3 minutes)
6. **Uploads to Drive** (returns link)

## Expected Timeline:
- Persona + Script: ~30 seconds
- Sora 2 generation: ~2-3 minutes  
- Drive upload: ~10 seconds

**Total: ~3-4 minutes per video**

## Test with Different Products:

**Physical Product:**
- Create product with image URL
- Click test
- See UGC video generated

**CPA Offer:**
- Create offer with `product_type: 'cpa_offer'`
- Add `offer_url` and `conversion_action: 'signup'`
- Click test
- See sign-up focused UGC

## Response Format:

```json
{
    "success": true,
    "video_url": "https://drive.google.com/file/d/.../view",
    "drive_file_id": "abc123...",
    "script": "Full UGC script with timestamps...",
    "persona": {
        "full_profile": "Detailed creator profile..."
    },
    "message": "UGC video generated successfully!"
}
```

## Once Working:

1. Add TikTok/IG channel to campaign
2. Set status to 'active'
3. Background worker will auto-produce daily
4. Check Google Drive for new videos

