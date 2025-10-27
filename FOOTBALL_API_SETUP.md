# Football API Setup Guide

To enable player photos and team logos in the VS comparisons, you need to set up the API-Football service.

## Steps to Get API Key

1. **Sign up for RapidAPI:**
   - Go to https://rapidapi.com/
   - Create a free account

2. **Subscribe to API-Football:**
   - Visit https://rapidapi.com/api-football/api/api-football
   - Click "Subscribe to Test"
   - Choose the **FREE** plan (100 requests/day)

3. **Get Your API Key:**
   - After subscribing, you'll see your API key in the "X-RapidAPI-Key" field
   - Copy this key

4. **Add to Environment:**
   Add this line to your `.env` file:
   ```bash
   FOOTBALL_API_KEY=your_api_key_here
   ```

## Features Enabled

With the API key configured, the VS comparisons will include:

✅ **Player Photos** - Real headshots of both players
✅ **Team Logos** - Official club badges
✅ **Enhanced Layout** - Professional VS-themed design
✅ **Better Labels** - Values displayed on each data point

## Without API Key

The script will still work without the API key, but:
- No player photos will be displayed
- No team logos will be shown
- VS comparison will still show the graphs, just without images

## Free Tier Limits

- **100 requests per day**
- Each comparison uses ~4 requests (2 players + 2 teams)
- About 25 comparisons per day on free tier

## Example Output

When properly configured, your VS comparisons will look like:

```
[Player 1 Photo]     VS     [Player 2 Photo]
   Name                      Name
   Team                      Team

[Team Logo]  📊 GOALS CHART  [Team Logo]
[Team Logo]  🎯 ASSISTS CHART [Team Logo]
```

With color-coded lines, value labels on each point, and professional styling!
