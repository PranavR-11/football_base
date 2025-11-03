"""
Security utilities for Football Analytics AI
"""
import re
import time
from typing import Dict, List
from collections import defaultdict, deque
import hashlib

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests: Dict[str, deque] = defaultdict(deque)
        self.limits = {
            "default": (100, 3600),  # 100 requests per hour
            "search": (200, 3600),   # 200 searches per hour
            "plot": (50, 3600),      # 50 plots per hour
        }
    
    def is_allowed(self, client_id: str, endpoint: str = "default") -> bool:
        """Check if request is allowed under rate limits"""
        now = time.time()
        limit, window = self.limits.get(endpoint, self.limits["default"])
        
        # Clean old requests
        client_requests = self.requests[client_id]
        while client_requests and client_requests[0] < now - window:
            client_requests.popleft()
        
        # Check limit
        if len(client_requests) >= limit:
            return False
        
        # Add current request
        client_requests.append(now)
        return True

class InputValidator:
    """Input validation and sanitization"""
    
    @staticmethod
    def sanitize_player_name(name: str) -> str:
        """Sanitize player name input"""
        if not isinstance(name, str):
            raise ValueError("Player name must be a string")
        
        # Remove potentially dangerous characters
        name = re.sub(r'[<>"\';\\]', '', name)
        name = name.strip()
        
        if len(name) > 100:
            raise ValueError("Player name too long")
        
        if len(name) < 1:
            raise ValueError("Player name cannot be empty")
        
        return name
    
    @staticmethod
    def sanitize_metric(metric: str) -> str:
        """Sanitize metric name"""
        if not isinstance(metric, str):
            raise ValueError("Metric must be a string")
        
        # Only allow alphanumeric, underscore, and common metric characters
        metric = re.sub(r'[^a-zA-Z0-9_\-/]', '', metric)
        
        if len(metric) > 50:
            raise ValueError("Metric name too long")
        
        return metric
    
    @staticmethod
    def validate_seasons_back(seasons: int) -> int:
        """Validate seasons_back parameter"""
        if not isinstance(seasons, int):
            try:
                seasons = int(seasons)
            except (ValueError, TypeError):
                raise ValueError("Seasons must be an integer")
        
        if seasons < 1:
            raise ValueError("Seasons must be at least 1")
        
        if seasons > 20:
            raise ValueError("Seasons cannot exceed 20")
        
        return seasons

def get_client_id(request) -> str:
    """Generate client ID for rate limiting"""
    # Use IP address as client ID (in production, consider user authentication)
    client_ip = getattr(request, 'client', {}).get('host', 'unknown')
    return hashlib.md5(client_ip.encode()).hexdigest()

# Global instances
rate_limiter = RateLimiter()
validator = InputValidator()