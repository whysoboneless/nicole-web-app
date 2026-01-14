# 🎬 UGC Automated Production System - READY TO USE

## What's Been Implemented

### ✅ Core Services
1. **`services/ugc_sora_service.py`** - Full UGC production pipeline
   - Persona generation (OpenAI Casting Director prompt)
   - Script generation with **ANTI-AD FRAMEWORK** 
   - Sora 2 video generation
   - Google Drive upload
   - Supports both physical products AND CPA offers

2. **`services/ugc_scheduler_service.py`** - Automated scheduler
   - Monitors all active TikTok/Instagram channels
   - Produces videos automatically based on upload frequency
   - NO manual triggers needed

3. **`workers/ugc_production_worker.py`** - Background worker
   - Runs continuously
   - Checks channels every hour
   - Auto-starts with Flask app

### ✅ Database Support
- **Products** now support:
  - `product_type`: 'physical_product' or 'cpa_offer'
  - `offer_url`: Landing page for CPA offers
  - `cpa_payout`: Expected payout
  - `conversion_action`: 'purchase', 'signup', 'install', 'trial'

### ✅ Anti-Ad Framework (Baked Into Every Script)

**SECONDS 0-3: Open Like a Story**
- ✅ "Okay so I literally just woke up and..."
- ❌ "Hey guys, let me tell you about..."

**SECONDS 3-7: Bridge Naturally**
- ✅ "...grabbed this thing my friend mentioned"
- ❌ "Let me show you this product"

**SECONDS 7-10: Feelings Over Features**
- ✅ "It's just... I don't know, it feels different?"
- ❌ "It has 3 settings and comes in 5 colors"

**SECONDS 10-12: Soft CTA**
- ✅ "Link below if you're curious"
- ❌ "Click now to buy!"

## How To Use RIGHT NOW

### 1. Add a Product or CPA Offer

**Physical Product:**
```
Name: "AG1 Greens Powder"
URL: https://drinkag1.com
Product Type: physical_product
Image URL: https://...product-image.jpg
```

**CPA Offer:**
```
Name: "Stake.us Free Bonus"
URL: https://stake.us/promotions
Product Type: cpa_offer
Offer URL: https://stake.us/sign-up
CPA Payout: $25
Conversion Action: signup
```

### 2. Add TikTok/Instagram Channel to Campaign

```
Platform: TikTok
Username: @yourbrand
Product: [Select from dropdown]
Upload Frequency: daily
Avatar URL: https://...avatar.jpg (optional)
Status: ACTIVE ← This starts auto-production!
```

### 3. System Automatically:
1. Analyzes product/offer
2. Generates ideal UGC creator persona
3. Writes 3 scripts following anti-ad framework
4. Generates first frame (720x1280)
5. Creates video with Sora 2 (12 seconds)
6. Uploads to Google Drive
7. Updates channel stats
8. **Repeats daily** (or per schedule)

## API Keys Required

Add to your `.env` or environment:

```bash
OPENAI_API_KEY=sk-...  # For Sora 2 and GPT-4 Vision
GEMINI_API_KEY=...     # For Gemini 2.5 Pro script generation
```

## Cost Per Video

- Persona Generation: ~$0.01 (GPT-4)
- Script Generation: ~$0.02 (Gemini 2.5 Pro)
- First Frame: ~$0.01 (Gemini)
- Video Generation: ~$0.50-1.00 (Sora 2)

**Total: ~$0.55-1.05 per 12-second UGC video**

## Manual Production Testing

You can manually trigger production via campaign dashboard:

```python
# Add route for manual testing
POST /campaigns/{campaign_id}/channels/{channel_id}/produce-ugc
{
    "video_count": 2  # Produce 2 videos right now
}
```

## What Happens When You Set Channel to "Active"

1. ✅ Channel is marked as active in database
2. ✅ Background worker picks it up within 1 hour
3. ✅ Checks if video is due (based on frequency)
4. ✅ If due: produces video automatically
5. ✅ Uploads to Google Drive
6. ✅ Updates last_upload_time
7. ✅ Repeats daily (or per schedule)

## Next Steps

### Immediate (Can Use Now):
- Add products/offers via UI
- Add channels to campaigns
- Set to active
- Monitor Google Drive for generated videos

### Coming Soon:
- Auto-posting to TikTok/Instagram APIs
- Performance tracking (views, engagement)
- A/B testing (generate variants)
- Winner scaling (produce more of what works)

## Example Use Case

**Scenario:** Promoting Stake.us sweepstakes casino

1. Create offer:
   - Name: "Stake Bonus"
   - Type: CPA Offer
   - URL: https://stake.us
   - Payout: $25 per signup

2. Add TikTok channel:
   - @stakepromo
   - Frequency: Daily
   - Status: Active

3. System produces:
   - Day 1: UGC video with "I was so skeptical but..." angle
   - Day 2: UGC video with "Okay this is actually legit..." angle
   - Day 3: UGC video with "Free $25 and I didn't even..." angle
   - Continues daily forever

**Result:** 365 unique UGC videos per year, all sounding authentic, zero manual work.

## System Is Live!

The UGC worker is running in the background. Just add channels and set them to active. Production starts automatically. 🚀

