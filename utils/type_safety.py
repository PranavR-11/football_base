"""
Type safety utilities for Football Analytics AI
"""
from typing import Any, Optional, Union, Dict, List
import pandas as pd

class SafeTypes:
    """Safe type conversion utilities"""
    
    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to int"""
        if value is None:
            return default
        try:
            return int(float(value))  # Handle "5.0" -> 5
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def safe_str(value: Any, default: str = "") -> str:
        """Safely convert value to string"""
        if value is None:
            return default
        try:
            return str(value).strip()
        except Exception:
            return default
    
    @staticmethod
    def safe_get_dict(d: Dict, key: str, converter=None, default=None):
        """Safely get and convert dictionary value"""
        value = d.get(key)
        if value is None:
            return default
        if converter:
            try:
                return converter(value)
            except Exception:
                return default
        return value

class SeasonHandler:
    """Unified season format handling"""
    
    @staticmethod
    def normalize_season_to_dataset_format(season_input: Union[str, int]) -> Optional[str]:
        """
        Convert any season format to dataset format (XX-YY)
        
        Examples:
        - 2020 -> "20-21" (season starting in 2020)
        - "2020-21" -> "20-21"
        - "20/21" -> "20-21"
        - 2021 -> "21-22"
        """
        if season_input is None:
            return None
            
        season_str = str(season_input).strip()
        
        # Already in correct format
        if len(season_str) == 5 and season_str[2] == '-':
            return season_str
        
        # Handle "2020-21" or "2020/21" format
        if len(season_str) in [7, 8] and ('/' in season_str or '-' in season_str):
            parts = season_str.replace('/', '-').split('-')
            if len(parts) == 2:
                try:
                    start_year = int(parts[0])
                    end_part = parts[1]
                    
                    # Handle 2-digit end year
                    if len(end_part) == 2:
                        end_year = 2000 + int(end_part)
                    else:
                        end_year = int(end_part)
                    
                    # Convert to XX-YY format
                    return f"{start_year % 100:02d}-{end_year % 100:02d}"
                except ValueError:
                    pass
        
        # Handle 4-digit year (assume it's the starting year)
        try:
            year = int(season_str)
            if 2000 <= year <= 2030:
                start_short = year % 100
                end_short = (year + 1) % 100
                return f"{start_short:02d}-{end_short:02d}"
        except ValueError:
            pass
        
        return None
    
    @staticmethod
    def season_to_end_year(season: str) -> Optional[int]:
        """Convert season format to ending year integer"""
        if not season or len(season) != 5 or season[2] != '-':
            return None
        try:
            end_part = season[3:5]
            end_year = 2000 + int(end_part)
            return end_year
        except ValueError:
            return None

class DataValidator:
    """Data validation utilities"""
    
    @staticmethod
    def validate_player_data(data: Dict) -> Dict[str, Any]:
        """Validate and clean player data"""
        safe = SafeTypes()
        return {
            'player': safe.safe_str(data.get('player')),
            'season': safe.safe_str(data.get('season')),
            'goals': safe.safe_float(data.get('goals')),
            'assists': safe.safe_float(data.get('assists')),
            'score': safe.safe_float(data.get('score')),
            'rag_summary': safe.safe_str(data.get('rag_summary'))
        }
    
    @staticmethod
    def is_valid_season_format(season: str) -> bool:
        """Check if season is in valid XX-YY format"""
        if not season or len(season) != 5:
            return False
        return season[2] == '-' and season[:2].isdigit() and season[3:].isdigit()