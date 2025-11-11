# Player Video Clips

Add your football player video clips here to display them **simultaneously** across the welcome screen!

## Instructions:

1. **Download 3-5 short video clips** of football players (5-10 seconds each)
   - Recommend: action clips, goals, dribbles, celebrations
   - Keep file sizes small (<5MB each) for fast loading

2. **Name your videos:**
   - `player1.mp4` - appears in **top-left** corner
   - `player2.mp4` - appears in **top-right** corner
   - `player3.mp4` - appears in **bottom-left** corner
   - `player4.mp4` - appears in **bottom-right** corner
   - `player5.mp4` - appears in **center-left** side

   (Add as many or as few as you want!)

3. **Place them in this folder** (`public/videos/`)

4. **The videos will automatically:**
   - Play **simultaneously** in different positions across the page
   - Appear with smooth fade-in scale animation (staggered timing)
   - Show in rounded cards with subtle borders
   - Disappear once the chat starts

## Layout Visual:
```
┌─────────────────────────────────────┐
│  [Video 1]          [Video 2]       │
│                                      │
│  [Video 5]    WELCOME TEXT           │
│                                      │
│  [Video 3]          [Video 4]       │
└─────────────────────────────────────┘
```

## Tips:
- Use MP4 format (H.264 codec) for best browser compatibility
- Keep videos short and looping for seamless playback
- Mix different player actions for variety
- Each video is 320x240px in a rounded card

## To customize positions:
Edit the `videoClips` array in `page.tsx` to change positions:
- `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center`

## To disable videos:
If you don't want video backgrounds, simply don't add any video files to this folder.
