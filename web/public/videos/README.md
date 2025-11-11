# Background Video

Add a single football highlight video to create a **professional, cinematic background** for your welcome screen!

## Current Setup:

**Video File:** `1111.mov` (or `1111.mp4`)
- Full-screen background video
- Plays on loop with random start time
- Professional blend with green theme

## How It Works:

### 🎬 Visual Effects Applied:
1. **Random Start Time** - Video begins at random point each page load (0-30 seconds)
2. **Dimmed** - 40% brightness for subtle effect
3. **Desaturated** - 80% saturation to match green theme
4. **Slight Blur** - 1px blur for depth and text clarity
5. **Green Tint Overlay** - Emerald/teal gradient for brand consistency
6. **Vignette Effect** - Dark edges to focus attention on center
7. **Top/Bottom Gradient** - Extra text protection

### 🎨 Professional Blending:
```
Video (dimmed, blurred)
  ↓
Green tint overlay (brand colors)
  ↓
Radial vignette (focus on center)
  ↓
Gradient protection (top/bottom)
  ↓
Your content (perfectly readable)
```

## To Update Video:

1. **Replace** `1111.mov` with your video
2. **Keep the same filename** OR update in `page.tsx`
3. **Recommended specs:**
   - Length: 30-60 seconds (will loop)
   - Format: MP4 (H.264) or MOV
   - Resolution: 1920x1080 or higher
   - File size: Under 10MB (compress if needed)
   - Content: Dynamic football action, not too busy

## Tips:
- **Smooth action clips** work best (passing, dribbling)
- **Avoid static shots** - keep movement consistent
- **Test different clips** - some look better dimmed than others
- **Compress videos** - Use Handbrake or online tools

## To Adjust Effects:

In `page.tsx`, modify:
- `brightness(0.4)` - Higher = brighter (0-1)
- `saturate(0.8)` - Higher = more color (0-1)
- `blur(1px)` - Higher = more blur
- Random start range: `Math.random() * 30` (0-30 seconds)

## Result:
✨ Professional, cinematic background that enhances your brand without distracting from content!
