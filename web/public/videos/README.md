# Player Video Clips

Add your football player video clips here to display them on the welcome screen!

## Instructions:

1. **Download 3-5 short video clips** of football players (5-10 seconds each)
   - Recommend: action clips, goals, dribbles, celebrations
   - Keep file sizes small (<5MB each) for fast loading

2. **Name your videos:**
   - `player1.mp4`
   - `player2.mp4`
   - `player3.mp4`
   - (You can add more by updating the `videoClips` array in `page.tsx`)

3. **Place them in this folder** (`public/videos/`)

4. **The videos will automatically:**
   - Play in the background of the welcome screen
   - Fade smoothly between each clip every 5 seconds
   - Be dimmed and slightly blurred for text readability
   - Disappear once the chat starts

## Tips:
- Use MP4 format (H.264 codec) for best browser compatibility
- Keep videos short and looping for seamless transitions
- Test different clips to find the best aesthetic

## To disable videos:
If you don't want video backgrounds, simply don't add any video files to this folder, or comment out the video section in `page.tsx`.
