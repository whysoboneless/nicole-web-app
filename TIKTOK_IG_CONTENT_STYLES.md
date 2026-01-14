# TikTok & Instagram Content Styles

These content styles need to be added to the database via the Content Styles UI or direct database insertion.

## TikTok Content Styles

1. **UGC Product Video**
   - Platform: `tiktok`
   - Type: `ugc_video`
   - Name: "UGC Product Video"
   - Description: "Script-based short-form product videos with UGC aesthetic"
   - Format: Video (15-60s)

2. **Product Showcase**
   - Platform: `tiktok`
   - Type: `product_showcase`
   - Name: "Product Showcase"
   - Description: "Static product images with trending music"
   - Format: Slideshow/Carousel

## Instagram Content Styles

1. **Carousel Post**
   - Platform: `instagram`
   - Type: `carousel`
   - Name: "Carousel Post"
   - Description: "Multi-image carousel with product information and swipe-worthy content"
   - Format: Images (up to 10 slides)

2. **Reel**
   - Platform: `instagram`
   - Type: `reel`
   - Name: "Reel"
   - Description: "Short-form vertical video (15-90s) optimized for Instagram Reels"
   - Format: Video

## How to Add

Via Content Styles UI at `/content-styles` or insert directly:

```javascript
// MongoDB insert example
db.content_styles.insertMany([
  {
    name: "UGC Product Video",
    platform: "tiktok",
    type: "ugc_video",
    description: "Script-based short-form product videos",
    created_at: new Date()
  },
  {
    name: "Product Showcase",
    platform: "tiktok",
    type: "product_showcase",
    description: "Static product images with music",
    created_at: new Date()
  },
  {
    name: "Carousel Post",
    platform: "instagram",
    type: "carousel",
    description: "Multi-image carousel posts",
    created_at: new Date()
  },
  {
    name: "Reel",
    platform: "instagram",
    type: "reel",
    description: "Short-form vertical video",
    created_at: new Date()
  }
]);
```

