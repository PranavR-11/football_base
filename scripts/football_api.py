"""
Football API Integration for fetching player images and club logos
Uses API-Football (free tier: 100 requests/day)
"""

import os
import requests
from typing import Optional, Dict
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Cache directory for downloaded images
CACHE_DIR = Path(__file__).parent.parent / "data" / "images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("FOOTBALL_API_KEY", "")
API_BASE_URL = "https://v3.football.api-sports.io"

# In-memory cache to avoid repeated API calls
_player_cache: Dict[str, Optional[str]] = {}
_team_cache: Dict[str, Optional[str]] = {}

def get_player_image(player_name: str) -> Optional[str]:
    """
    Fetch player image URL from API-Football.
    Returns local cached path if available, otherwise downloads and caches.
    Returns None if not found or API not configured.
    """
    if not API_KEY:
        return None

    # Check memory cache
    if player_name in _player_cache:
        return _player_cache[player_name]

    # Check file cache
    safe_name = player_name.lower().replace(" ", "_").replace("'", "")
    cached_path = CACHE_DIR / f"player_{safe_name}.png"

    if cached_path.exists():
        _player_cache[player_name] = str(cached_path)
        return str(cached_path)

    try:
        # Search for player across major leagues
        # Free tier requires league parameter with search
        headers = {
            "x-apisports-key": API_KEY
        }

        # Major league IDs: Premier League, La Liga, Bundesliga, Serie A, Ligue 1
        leagues_to_try = [39, 140, 78, 135, 61]

        for league_id in leagues_to_try:
            response = requests.get(
                f"{API_BASE_URL}/players",
                headers=headers,
                params={
                    "search": player_name,
                    "league": league_id,
                    "season": 2023  # Recent season
                },
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                players = data.get("response", [])

                if players:
                    # Get first result's photo
                    photo_url = players[0].get("player", {}).get("photo")

                    if photo_url:
                        # Download and cache image
                        img_response = requests.get(photo_url, timeout=5)
                        if img_response.status_code == 200:
                            cached_path.write_bytes(img_response.content)
                            _player_cache[player_name] = str(cached_path)
                            return str(cached_path)

                    # Found player but no photo URL
                    break

        # Cache negative result
        _player_cache[player_name] = None
        return None

    except Exception as e:
        print(f"Error fetching player image for {player_name}: {e}")
        _player_cache[player_name] = None
        return None


def get_team_logo(team_name: str) -> Optional[str]:
    """
    Fetch team logo URL from API-Football.
    Returns local cached path if available, otherwise downloads and caches.
    Returns None if not found or API not configured.
    """
    if not API_KEY:
        return None

    # Check memory cache
    if team_name in _team_cache:
        return _team_cache[team_name]

    # Check file cache
    safe_name = team_name.lower().replace(" ", "_").replace("'", "")
    cached_path = CACHE_DIR / f"team_{safe_name}.png"

    if cached_path.exists():
        _team_cache[team_name] = str(cached_path)
        return str(cached_path)

    try:
        # Search for team
        headers = {
            "x-apisports-key": API_KEY
        }

        response = requests.get(
            f"{API_BASE_URL}/teams",
            headers=headers,
            params={"search": team_name},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            teams = data.get("response", [])

            if teams:
                # Get first result's logo
                logo_url = teams[0].get("team", {}).get("logo")

                if logo_url:
                    # Download and cache image
                    img_response = requests.get(logo_url, timeout=5)
                    if img_response.status_code == 200:
                        cached_path.write_bytes(img_response.content)
                        _team_cache[team_name] = str(cached_path)
                        return str(cached_path)

        # Cache negative result
        _team_cache[team_name] = None
        return None

    except Exception as e:
        print(f"Error fetching team logo for {team_name}: {e}")
        _team_cache[team_name] = None
        return None


def add_player_image_to_plot(ax, player_name: str, position: tuple, zoom: float = 0.15):
    """
    Add player headshot to matplotlib plot at specified position.

    Args:
        ax: Matplotlib axes object
        player_name: Name of player
        position: (x, y) tuple for image position in data coordinates
        zoom: Size of image (default 0.15)
    """
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    from PIL import Image
    import numpy as np

    image_path = get_player_image(player_name)

    if not image_path:
        return  # Skip if image not available

    try:
        # Load and process image
        img = Image.open(image_path)
        img = img.convert("RGBA")

        # Make circular
        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Create circular mask
        y, x = np.ogrid[:h, :w]
        center_y, center_x = h // 2, w // 2
        radius = min(center_x, center_y)
        mask = (x - center_x)**2 + (y - center_y)**2 <= radius**2

        # Apply mask
        img_array[~mask] = [0, 0, 0, 0]
        img_circular = Image.fromarray(img_array)

        # Add to plot
        imagebox = OffsetImage(img_circular, zoom=zoom)
        ab = AnnotationBbox(imagebox, position, frameon=False, pad=0)
        ax.add_artist(ab)

    except Exception as e:
        print(f"Error adding player image to plot: {e}")


def add_team_logo_to_plot(ax, team_name: str, position: tuple, zoom: float = 0.1):
    """
    Add team logo to matplotlib plot at specified position.

    Args:
        ax: Matplotlib axes object
        team_name: Name of team
        position: (x, y) tuple for image position in data coordinates
        zoom: Size of logo (default 0.1)
    """
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    from PIL import Image

    logo_path = get_team_logo(team_name)

    if not logo_path:
        return  # Skip if logo not available

    try:
        # Load image
        img = Image.open(logo_path)
        img = img.convert("RGBA")

        # Add to plot
        imagebox = OffsetImage(img, zoom=zoom)
        ab = AnnotationBbox(imagebox, position, frameon=False, pad=0)
        ax.add_artist(ab)

    except Exception as e:
        print(f"Error adding team logo to plot: {e}")
