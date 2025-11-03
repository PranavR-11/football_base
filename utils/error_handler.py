"""
Centralized error handling for Football Analytics AI
"""
import logging
import traceback
from typing import Dict, Any, Optional, Callable
from functools import wraps
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class FootballAnalyticsError(Exception):
    """Base exception for Football Analytics AI"""
    pass

class PlayerNotFoundError(FootballAnalyticsError):
    """Raised when a player cannot be found in the dataset"""
    pass

class DataValidationError(FootballAnalyticsError):
    """Raised when data validation fails"""
    pass

class APIConnectionError(FootballAnalyticsError):
    """Raised when external API connections fail"""
    pass

class SeasonFormatError(FootballAnalyticsError):
    """Raised when season format is invalid"""
    pass

class ConfigurationError(FootballAnalyticsError):
    """Raised when configuration is invalid"""
    pass

def handle_errors(func):
    """Decorator for consistent error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PlayerNotFoundError as e:
            logger.warning(f"Player not found: {e}")
            return {
                "ok": False,
                "error": "player_not_found",
                "message": str(e)
            }
        except DataValidationError as e:
            logger.error(f"Data validation error: {e}")
            return {
                "ok": False,
                "error": "data_validation",
                "message": str(e)
            }
        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            return {
                "ok": False,
                "error": "api_connection",
                "message": "External service unavailable"
            }
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            logger.error(traceback.format_exc())
            return {
                "ok": False,
                "error": "internal_error",
                "message": "An unexpected error occurred"
            }
    return wrapper

def validate_player_name(name: str) -> str:
    """Validate and normalize player name"""
    if not name or not isinstance(name, str):
        raise DataValidationError("Player name must be a non-empty string")
    
    name = name.strip()
    if len(name) < 2:
        raise DataValidationError("Player name must be at least 2 characters")
    
    if len(name) > 100:
        raise DataValidationError("Player name too long")
    
    return name

def validate_metric(metric: str, available_metrics: list) -> str:
    """Validate metric name against available options"""
    if not metric or not isinstance(metric, str):
        raise DataValidationError("Metric must be a non-empty string")
    
    metric = metric.strip().lower()
    
    # Check if metric exists in available options
    available_lower = [m.lower() for m in available_metrics]
    if metric not in available_lower:
        raise DataValidationError(f"Metric '{metric}' not available. Available: {', '.join(available_metrics[:10])}")
    
    # Return original case version
    return available_metrics[available_lower.index(metric)]