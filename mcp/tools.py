# mcp/tools.py - Complete rewrite addressing all 40+ issues
import os
import pickle
import re
import base64
import io
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from functools import lru_cache
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

from mcp.config import (
    get_openai_api_key, get_data_csv_path, get_vector_dir, 
    get_embedding_model, get_k_default, get_default_seasons_back
)

# Configure logging
logger = logging.getLogger(__name__)

# Thread-safe singleton OpenAI client
_openai_client = None
_client_lock = threading.Lock()

def _get_openai_client():
    """Thread-safe singleton OpenAI client with proper error handling."""
    global _openai_client
    
    with _client_lock:
        if _openai_client is None:
            try:
                from openai import OpenAI
                api_key = get_openai_api_key()  # Dynamic key retrieval
                _openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized successfully")
            except ImportError as e:
                raise ImportError("Install openai>=1.0.0: pip install openai") from e
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise
    
    return _openai_client

# Cached data loading with proper cache invalidation
_cached_df = None
_df_cache_time = None
_cache_lock = threading.Lock()

@lru_cache(maxsize=1)
def _get_dataframe_cached(file_path: str, mtime: float) -> pd.DataFrame:
    """LRU cached dataframe loading."""
    logger.info(f"Loading CSV: {file_path}")
    df = pd.read_csv(file_path)
    
    # Normalize columns consistently
    if "rag_summary" in df.columns:
        df["rag_summary"] = df["rag_summary"].astype(str).fillna("")
    
    return df

def _load_dataframe(force_reload: bool = False) -> pd.DataFrame:
    """Load CSV with thread-safe caching and proper error handling."""
    file_path = get_data_csv_path()
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV not found: {file_path}")
    
    current_mtime = os.path.getmtime(file_path)
    
    if force_reload:
        _get_dataframe_cached.cache_clear()
    
    try:
        df = _get_dataframe_cached(file_path, current_mtime)
        return df.copy()  # Always return copy to prevent mutations
    except Exception as e:
        logger.error(f"Failed to load dataframe: {e}")
        raise

def _get_faiss_components():
    """Load FAISS index and metadata with proper error handling."""
    try:
        import faiss
    except ImportError as e:
        raise ImportError("Install faiss-cpu: pip install faiss-cpu") from e
    
    vector_dir = get_vector_dir()
    idx_path = os.path.join(vector_dir, "index.faiss")
    meta_path = os.path.join(vector_dir, "metadata.pkl")
    
    if not os.path.exists(idx_path):
        raise FileNotFoundError(f"FAISS index not found: {idx_path}")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"FAISS metadata not found: {meta_path}")
    
    try:
        index = faiss.read_index(idx_path)
        with open(meta_path, "rb") as f:
            metadata_df = pickle.load(f)
        
        logger.info(f"Loaded FAISS index with {index.ntotal} vectors")
        return faiss, index, metadata_df
    except Exception as e:
        logger.error(f"Failed to load FAISS components: {e}")
        raise

def season_to_year(season_str) -> Optional[int]:
    """Convert season string to ending year with robust parsing."""
    if pd.isna(season_str) or season_str is None:
        return None
    
    try:
        s = str(season_str).strip()
        if not s:
            return None
            
        # Find all 2-4 digit numbers
        numbers = re.findall(r'\b\d{2,4}\b', s)
        if not numbers:
            # Try direct conversion for simple numeric strings
            return int(float(s))
        
        # Take the last (ending) year
        year_str = numbers[-1]
        year = int(year_str)
        
        # Handle 2-digit years (assume 20xx for years 00-99)
        if year < 100:
            if year <= 50:  # 00-50 -> 2000-2050
                year += 2000
            else:  # 51-99 -> 1951-1999 (historical data)
                year += 1900
        
        # Sanity check for reasonable football seasons
        if 1900 <= year <= 2100:
            return year
        
        return None
    except (ValueError, TypeError, OverflowError):
        return None

# Comprehensive position mapping with synonyms
POSITION_MAPPING = {
    # Forwards/Strikers
    'striker': ['FW', 'ST', 'CF', 'F'],
    'forward': ['FW', 'ST', 'CF', 'F'],
    'center-forward': ['CF', 'ST', 'FW'],
    'centre-forward': ['CF', 'ST', 'FW'],
    'cf': ['CF', 'ST', 'FW'],
    'st': ['ST', 'CF', 'FW'],
    'fw': ['FW', 'ST', 'CF'],
    
    # Midfielders
    'midfielder': ['MF', 'CM', 'DM', 'AM', 'CAM', 'CDM', 'M'],
    'midfield': ['MF', 'CM', 'DM', 'AM', 'CAM', 'CDM', 'M'],
    'central-midfielder': ['CM', 'MF'],
    'attacking-midfielder': ['AM', 'CAM', 'MF'],
    'defensive-midfielder': ['DM', 'CDM', 'MF'],
    'cm': ['CM', 'MF'],
    'am': ['AM', 'CAM', 'MF'],
    'dm': ['DM', 'CDM', 'MF'],
    'cam': ['CAM', 'AM', 'MF'],
    'cdm': ['CDM', 'DM', 'MF'],
    'mf': ['MF', 'CM', 'AM', 'DM'],
    
    # Defenders
    'defender': ['DF', 'CB', 'LB', 'RB', 'LWB', 'RWB', 'D'],
    'defence': ['DF', 'CB', 'LB', 'RB', 'LWB', 'RWB', 'D'],
    'defense': ['DF', 'CB', 'LB', 'RB', 'LWB', 'RWB', 'D'],
    'center-back': ['CB', 'DF'],
    'centre-back': ['CB', 'DF'],
    'fullback': ['LB', 'RB', 'DF'],
    'full-back': ['LB', 'RB', 'DF'],
    'wingback': ['LWB', 'RWB', 'DF'],
    'wing-back': ['LWB', 'RWB', 'DF'],
    'cb': ['CB', 'DF'],
    'lb': ['LB', 'DF'],
    'rb': ['RB', 'DF'],
    'lwb': ['LWB', 'DF'],
    'rwb': ['RWB', 'DF'],
    'df': ['DF', 'CB', 'LB', 'RB'],
    
    # Goalkeepers
    'goalkeeper': ['GK', 'G'],
    'keeper': ['GK', 'G'],
    'goalie': ['GK', 'G'],
    'gk': ['GK'],
    
    # Wingers (can be forwards or midfielders)
    'winger': ['LW', 'RW', 'LM', 'RM', 'W'],
    'wing': ['LW', 'RW', 'LM', 'RM', 'W'],
    'left-winger': ['LW', 'LM'],
    'right-winger': ['RW', 'RM'],
    'lw': ['LW', 'LM'],
    'rw': ['RW', 'RM'],
    'lm': ['LM', 'LW'],
    'rm': ['RM', 'RW']
}

def _normalize_position(position: str) -> List[str]:
    """Convert position query to canonical position codes with comprehensive mapping."""
    if not position:
        return []
    
    pos_lower = position.lower().strip()
    
    # Direct mapping from synonyms
    if pos_lower in POSITION_MAPPING:
        return POSITION_MAPPING[pos_lower]
    
    # Check if it's already a canonical code
    canonical_codes = set()
    for codes in POSITION_MAPPING.values():
        canonical_codes.update(codes)
    
    if position.upper() in canonical_codes:
        return [position.upper()]
    
    # Partial matching for compound terms
    matches = []
    for synonym, codes in POSITION_MAPPING.items():
        if synonym in pos_lower or pos_lower in synonym:
            matches.extend(codes)
    
    if matches:
        return list(set(matches))  # Remove duplicates
    
    # Return original if no mapping found
    return [position]

def _flexible_player_match(df: pd.DataFrame, player_name: str, player_col: str = "player") -> pd.Series:
    """Robust player name matching with multiple strategies and proper error handling."""
    if not player_name or pd.isna(player_name):
        return pd.Series([False] * len(df), index=df.index, dtype=bool)
    
    try:
        player_lower = str(player_name).strip().lower()
        if not player_lower:
            return pd.Series([False] * len(df), index=df.index, dtype=bool)
        
        df_players = df[player_col].astype(str).str.strip().str.lower()
        
        # Strategy 1: Exact match
        mask = df_players == player_lower
        if mask.any():
            return mask
        
        # Strategy 2: Contains match (player name contains query)
        mask = df_players.str.contains(player_lower, na=False, regex=False)
        if mask.any():
            return mask
        
        # Strategy 3: Token-based match (all query tokens in player name)
        query_tokens = player_lower.split()
        if len(query_tokens) > 1:
            mask = df_players.apply(
                lambda x: all(token in str(x) for token in query_tokens) if pd.notna(x) else False
            )
            if mask.any():
                return mask
        
        # Strategy 4: Reverse contains (query contains player name - for nicknames)
        mask = pd.Series([False] * len(df), index=df.index, dtype=bool)
        for idx, player in df_players.items():
            if pd.notna(player) and player and player in player_lower:
                mask.iloc[idx] = True
        
        return mask
        
    except Exception as e:
        logger.error(f"Error in player matching for '{player_name}': {e}")
        return pd.Series([False] * len(df), index=df.index, dtype=bool)

@dataclass
class SearchResult:
    """Structured search result with proper typing."""
    score: float
    idx: int
    player: str
    season: Optional[str]
    rag_summary: str

def get_schema() -> List[str]:
    """Get available dataset columns with error handling."""
    try:
        df = _load_dataframe()
        return list(df.columns)
    except Exception as e:
        logger.error(f"Failed to get schema: {e}")
        return []

def search_player(query: str, k: int = None) -> List[Dict[str, Any]]:
    """Semantic player search with robust fallback and proper error handling."""
    if not query or not query.strip():
        return []
    
    if k is None:
        k = get_k_default()
    
    query = query.strip()
    
    try:
        # Try FAISS search first
        client = _get_openai_client()
        faiss_lib, index, metadata_df = _get_faiss_components()
        
        # Generate embedding with proper error handling
        try:
            response = client.embeddings.create(
                model=get_embedding_model(), 
                input=[query]
            )
            embedding = response.data[0].embedding
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            raise  # Re-raise to trigger fallback
        
        # Search index with validation
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        
        if vec.shape[1] != index.d:
            raise ValueError(f"Embedding dimension mismatch: {vec.shape[1]} != {index.d}")
        
        faiss_lib.normalize_L2(vec)
        distances, indices = index.search(vec, k)
        
        results = []
        query_lower = query.lower()
        
        for score, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(metadata_df):
                continue
                
            try:
                row = metadata_df.iloc[idx]
                player_name = str(row.get("player", ""))
                
                # Boost scores for name matches (FAISS returns cosine similarity)
                boosted_score = float(score)
                
                # Exact name match
                if query_lower == player_name.lower():
                    boosted_score = 1.0
                # Contains match
                elif query_lower in player_name.lower():
                    boosted_score = max(boosted_score, 0.95)
                # Token overlap
                elif any(token in player_name.lower() for token in query_lower.split()):
                    boosted_score = max(boosted_score, 0.85)
                
                results.append({
                    "score": boosted_score,
                    "idx": int(idx),
                    "player": player_name,
                    "season": row.get("season"),
                    "rag_summary": str(row.get("rag_summary", ""))[:1000]
                })
            except Exception as e:
                logger.warning(f"Error processing search result {idx}: {e}")
                continue
        
        return sorted(results, key=lambda x: -x["score"])
        
    except Exception as e:
        logger.warning(f"FAISS search failed, using fallback: {e}")
        
        # Fallback to simple text search
        try:
            df = _load_dataframe()
            results = []
            query_lower = query.lower()
            query_tokens = set(query_lower.split())
            
            for idx, row in df.iterrows():
                try:
                    player_name = str(row.get("player", ""))
                    player_lower = player_name.lower()
                    player_tokens = set(player_lower.split())
                    
                    score = 0.0
                    
                    # Exact match
                    if query_lower == player_lower:
                        score = 1.0
                    # Contains match
                    elif query_lower in player_lower:
                        score = 0.9
                    # All query tokens in player name
                    elif query_tokens.issubset(player_tokens):
                        score = 0.8
                    # Partial token overlap
                    else:
                        overlap = len(query_tokens & player_tokens)
                        if overlap > 0:
                            overlap_ratio = overlap / len(query_tokens)
                            if overlap_ratio >= 0.5:
                                score = 0.5 + (overlap_ratio * 0.3)
                    
                    # Check rag_summary as last resort (lower priority)
                    if score == 0.0:
                        rag_summary = str(row.get("rag_summary", "")).lower()
                        if query_lower in rag_summary:
                            score = 0.2
                    
                    if score > 0:
                        results.append({
                            "score": score,
                            "idx": int(idx),
                            "player": player_name,
                            "season": row.get("season"),
                            "rag_summary": str(row.get("rag_summary", ""))[:500]
                        })
                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    continue
            
            return sorted(results, key=lambda x: -x["score"])[:k]
            
        except Exception as e2:
            logger.error(f"Fallback search failed: {e2}")
            return []

def rank_players(
    stat: str = "goals",
    top_n: int = 10,
    team: Optional[str] = None,
    position: Optional[str] = None,
    season_year: Optional[int] = None,
    seasons_back: Optional[int] = None
) -> Dict[str, Any]:
    """Fast bulk ranking with comprehensive error handling and filtering."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    try:
        df = _load_dataframe()
        
        # Validate stat column
        if stat not in df.columns:
            numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
            return {
                "ok": False,
                "error": f"Stat '{stat}' not found in dataset",
                "available_stats": numeric_cols[:20]
            }
        
        # Add season year column with proper error handling
        df["_season_year"] = df["season"].apply(season_to_year)
        
        # Initialize filter mask
        mask = pd.Series([True] * len(df), index=df.index, dtype=bool)
        
        # Team filter with comprehensive column search
        if team:
            team_cols = [c for c in df.columns 
                        if any(keyword in c.lower() 
                              for keyword in ['team', 'club', 'squad', 'side'])]
            
            if team_cols:
                team_mask = pd.Series([False] * len(df), index=df.index, dtype=bool)
                for col in team_cols:
                    try:
                        team_mask |= df[col].astype(str).str.contains(
                            team, case=False, na=False, regex=False
                        )
                    except Exception as e:
                        logger.warning(f"Error filtering by team column {col}: {e}")
                mask &= team_mask
            else:
                logger.warning(f"No team columns found for filtering by '{team}'")
        
        # Position filter with comprehensive mapping
        if position:
            position_codes = _normalize_position(position)
            pos_cols = [c for c in df.columns 
                       if any(keyword in c.lower() 
                             for keyword in ['pos', 'position', 'role'])]
            
            if pos_cols and position_codes:
                pos_mask = pd.Series([False] * len(df), index=df.index, dtype=bool)
                for col in pos_cols:
                    try:
                        for code in position_codes:
                            pos_mask |= df[col].astype(str).str.contains(
                                code, case=False, na=False, regex=False
                            )
                    except Exception as e:
                        logger.warning(f"Error filtering by position column {col}: {e}")
                mask &= pos_mask
            else:
                if not pos_cols:
                    logger.warning(f"No position columns found for filtering by '{position}'")
                if not position_codes:
                    logger.warning(f"Position '{position}' not recognized")
        
        # Season filter
        if season_year:
            mask &= (df["_season_year"] == season_year)
        else:
            # Filter to recent seasons
            valid_years = df["_season_year"].dropna()
            if not valid_years.empty:
                latest_year = int(valid_years.max())
                season_range = [latest_year - i for i in range(seasons_back)]
                mask &= df["_season_year"].isin(season_range)
        
        # Apply filters
        filtered_df = df[mask].copy()
        
        if filtered_df.empty:
            return {
                "ok": False,
                "error": "No players found matching the specified filters",
                "filters_applied": {
                    "team": team,
                    "position": position,
                    "season_year": season_year,
                    "seasons_back": seasons_back
                }
            }
        
        # Ensure numeric data and handle missing values properly
        stat_series = pd.to_numeric(filtered_df[stat], errors='coerce')
        
        # Group by player and sum (handling NaN properly)
        player_totals = stat_series.groupby(filtered_df["player"]).sum()
        
        # Remove players with no valid data
        player_totals = player_totals[player_totals.notna() & (player_totals > 0)]
        
        if player_totals.empty:
            return {
                "ok": False,
                "error": f"No players found with valid '{stat}' data",
                "filters_applied": {
                    "team": team,
                    "position": position,
                    "season_year": season_year,
                    "seasons_back": seasons_back
                }
            }
        
        # Sort and get top N
        top_players = player_totals.sort_values(ascending=False).head(top_n)
        
        # Build rankings
        rankings = []
        for rank, (player, value) in enumerate(top_players.items(), 1):
            rankings.append({
                "rank": rank,
                "player": player,
                "value": float(value)
            })
        
        return {
            "ok": True,
            "stat": stat,
            "rankings": rankings,
            "filters": {
                "team": team,
                "position": position,
                "season_year": season_year,
                "seasons_back": seasons_back if not season_year else None
            },
            "total_players_evaluated": len(player_totals)
        }
        
    except Exception as e:
        logger.error(f"Ranking failed: {e}")
        return {
            "ok": False,
            "error": f"Ranking operation failed: {str(e)}"
        }

def aggregate_player_stat(
    player_name: str,
    stat: str = "goals",
    seasons_back: Optional[int] = None,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """Get player statistics with flexible name matching and proper error handling."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    try:
        df = _load_dataframe()
        
        # Validate required columns
        if season_col not in df.columns:
            return {
                "found": False,
                "error": f"Season column '{season_col}' not found in dataset"
            }
        
        if player_col not in df.columns:
            return {
                "found": False,
                "error": f"Player column '{player_col}' not found in dataset"
            }
        
        # Add season year column
        df["_season_year"] = df[season_col].apply(season_to_year)
        
        # Use flexible player matching
        mask = _flexible_player_match(df, player_name, player_col)
        player_data = df[mask & df["_season_year"].notna()].copy()
        
        if player_data.empty:
            # Try to find similar players for suggestions
            similar_mask = df[player_col].astype(str).str.contains(
                player_name, case=False, na=False, regex=False
            )
            suggestions = df[similar_mask][player_col].unique()[:5].tolist()
            
            return {
                "found": False,
                "message": f"Player '{player_name}' not found",
                "suggestions": suggestions
            }
        
        # Get canonical player name
        canonical_name = player_data[player_col].iloc[0]
        
        # Validate stat column
        if stat not in player_data.columns:
            available_stats = list(player_data.select_dtypes(include=[np.number]).columns)
            return {
                "found": True,
                "player": canonical_name,
                "error": f"Stat '{stat}' not available for this player",
                "available_stats": available_stats[:10]
            }
        
        # Calculate statistics
        latest_year = int(player_data["_season_year"].max())
        requested_years = [latest_year - i for i in range(seasons_back)][::-1]
        
        # Group by season and sum values
        season_data = player_data.groupby("_season_year")[stat].sum()
        
        per_season = []
        total = 0.0
        seasons_with_data = 0
        
        for year in requested_years:
            value = season_data.get(year)
            if pd.notna(value) and value != 0:
                per_season.append({"season_year": year, "value": float(value)})
                total += float(value)
                seasons_with_data += 1
            else:
                per_season.append({"season_year": year, "value": None})
        
        return {
            "found": True,
            "player": canonical_name,
            "stat": stat,
            "per_season": per_season,
            "total": total,
            "latest_season": latest_year,
            "seasons_with_data": seasons_with_data,
            "has_consecutive_n": seasons_with_data == seasons_back
        }
        
    except Exception as e:
        logger.error(f"Aggregate failed for player '{player_name}': {e}")
        return {
            "found": False,
            "error": f"Failed to aggregate stats: {str(e)}"
        }

# MCP wrapper functions (maintaining compatibility)
def rank_players_mcp(**kwargs) -> Dict[str, Any]:
    """MCP wrapper for rank_players with parameter validation."""
    try:
        return rank_players(**kwargs)
    except Exception as e:
        logger.error(f"MCP rank_players failed: {e}")
        return {
            "ok": False,
            "error": f"MCP ranking failed: {str(e)}"
        }

def aggregate_mcp(player_name: str, **kwargs) -> Dict[str, Any]:
    """MCP wrapper for aggregate_player_stat."""
    try:
        return aggregate_player_stat(player_name, **kwargs)
    except Exception as e:
        logger.error(f"MCP aggregate failed for '{player_name}': {e}")
        return {
            "found": False,
            "error": f"MCP aggregation failed: {str(e)}"
        }

def rag_search_mcp(query: str, k: int = None) -> List[Dict[str, Any]]:
    """MCP wrapper for search_player."""
    try:
        return search_player(query, k)
    except Exception as e:
        logger.error(f"MCP search failed for '{query}': {e}")
        return []

# Export functions for langchain_agent compatibility
__all__ = [
    "get_schema",
    "search_player",
    "rank_players",
    "rank_players_mcp", 
    "aggregate_player_stat",
    "aggregate_mcp",
    "rag_search_mcp"
]

# Additional MCP functions required by langchain_agent.py

def filter_players_mcp(
    team: Optional[str] = None, 
    position: Optional[str] = None, 
    seasons_back: Optional[int] = None
) -> Dict[str, Any]:
    """Filter players by team and/or position."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    try:
        df = _load_dataframe()
        
        # Initialize mask
        mask = pd.Series([True] * len(df), index=df.index, dtype=bool)
        
        # Team filter
        if team:
            team_cols = [c for c in df.columns 
                        if any(keyword in c.lower() 
                              for keyword in ['team', 'club', 'squad', 'side'])]
            if team_cols:
                team_mask = pd.Series([False] * len(df), index=df.index, dtype=bool)
                for col in team_cols:
                    try:
                        team_mask |= df[col].astype(str).str.contains(
                            team, case=False, na=False, regex=False
                        )
                    except Exception as e:
                        logger.warning(f"Error filtering by team column {col}: {e}")
                mask &= team_mask
        
        # Position filter
        if position:
            position_codes = _normalize_position(position)
            pos_cols = [c for c in df.columns 
                       if any(keyword in c.lower() 
                             for keyword in ['pos', 'position', 'role'])]
            if pos_cols and position_codes:
                pos_mask = pd.Series([False] * len(df), index=df.index, dtype=bool)
                for col in pos_cols:
                    try:
                        for code in position_codes:
                            pos_mask |= df[col].astype(str).str.contains(
                                code, case=False, na=False, regex=False
                            )
                    except Exception as e:
                        logger.warning(f"Error filtering by position column {col}: {e}")
                mask &= pos_mask
        
        # Season filter
        df["_season_year"] = df["season"].apply(season_to_year)
        valid_years = df["_season_year"].dropna()
        if not valid_years.empty:
            latest_year = int(valid_years.max())
            season_range = [latest_year - i for i in range(seasons_back)]
            mask &= df["_season_year"].isin(season_range)
        
        # Get unique players
        filtered_players = df[mask]["player"].dropna().unique().tolist()
        
        return {
            "ok": True,
            "players": filtered_players,
            "count": len(filtered_players)
        }
        
    except Exception as e:
        logger.error(f"Filter players failed: {e}")
        return {
            "ok": False,
            "error": f"Filter operation failed: {str(e)}"
        }

def plot_mcp(player_name: str, metrics: List[str]) -> Dict[str, Any]:
    """Generate plot for player metrics (placeholder - plotting not implemented)."""
    try:
        # Get player data to validate
        result = aggregate_player_stat(player_name, metrics[0] if metrics else "goals")
        
        if not result.get("found"):
            return result
        
        # Plotting functionality would go here
        # For now, return success without actual plot
        return {
            "ok": True,
            "player": result["player"],
            "metrics": metrics,
            "message": "Plot generation not implemented in this version"
        }
        
    except Exception as e:
        logger.error(f"Plot MCP failed for '{player_name}': {e}")
        return {
            "ok": False,
            "error": f"Plot generation failed: {str(e)}"
        }

def aggregate_group_mcp(
    players: List[str], 
    stat: str = "goals", 
    seasons_back: Optional[int] = None
) -> Dict[str, Any]:
    """Aggregate statistics for a group of players."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    try:
        results = {}
        for player in players:
            result = aggregate_player_stat(player, stat, seasons_back)
            results[player] = result
        
        return {
            "ok": True,
            "stat": stat,
            "seasons_back": seasons_back,
            "players": results
        }
        
    except Exception as e:
        logger.error(f"Group aggregate failed: {e}")
        return {
            "ok": False,
            "error": f"Group aggregation failed: {str(e)}"
        }

def plot_group_mcp(
    players: List[str], 
    metrics: Optional[List[str]] = None, 
    seasons_back: Optional[int] = None
) -> Dict[str, Any]:
    """Generate group plot (placeholder - plotting not implemented)."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    if metrics is None:
        metrics = ["goals"]
    
    try:
        # Validate players exist
        valid_players = []
        for player in players:
            result = aggregate_player_stat(player, metrics[0], seasons_back)
            if result.get("found"):
                valid_players.append(result["player"])
        
        return {
            "ok": True,
            "players": valid_players,
            "metrics": metrics,
            "seasons_back": seasons_back,
            "message": "Group plot generation not implemented in this version"
        }
        
    except Exception as e:
        logger.error(f"Group plot failed: {e}")
        return {
            "ok": False,
            "error": f"Group plot failed: {str(e)}"
        }

def get_schema_mcp() -> Optional[List[str]]:
    """Get dataset schema (MCP wrapper)."""
    try:
        return get_schema()
    except Exception as e:
        logger.error(f"Schema MCP failed: {e}")
        return None

def aggregate_group_multi_metrics_mcp(
    players: List[str],
    metrics: List[str],
    seasons_back: Optional[int] = None,
    include_cohort: bool = True,
    cohort_size: int = 200
) -> Dict[str, Any]:
    """Bulk aggregation of multiple metrics for multiple players."""
    if seasons_back is None:
        seasons_back = get_default_seasons_back()
    
    try:
        df = _load_dataframe()
        
        # Validate metrics
        available_metrics = [m for m in metrics if m in df.columns]
        if not available_metrics:
            return {
                "ok": False,
                "error": "None of the requested metrics found in dataset",
                "requested": metrics,
                "available": list(df.select_dtypes(include=[np.number]).columns[:20])
            }
        
        # Add season year column
        df["_season_year"] = df["season"].apply(season_to_year)
        
        # Get recent seasons
        valid_years = df["_season_year"].dropna()
        if valid_years.empty:
            return {
                "ok": False,
                "error": "No valid season data found"
            }
        
        latest_years = sorted(valid_years.unique())[-seasons_back:]
        season_mask = df["_season_year"].isin(latest_years)
        filtered_df = df[season_mask].copy()
        
        # Build results for each player
        results = {}
        for player_name in players:
            mask = _flexible_player_match(filtered_df, player_name)
            player_df = filtered_df[mask]
            
            if player_df.empty:
                results[player_name] = {
                    "found": False,
                    "per_season": {},
                    "totals": {},
                    "latest": {}
                }
                continue
            
            canonical_name = player_df["player"].iloc[0]
            
            # Aggregate by season
            per_season = {}
            for year in latest_years:
                year_df = player_df[player_df["_season_year"] == year]
                season_stats = {}
                for metric in available_metrics:
                    value = pd.to_numeric(year_df[metric], errors='coerce').sum()
                    season_stats[metric] = float(value) if pd.notna(value) else 0.0
                per_season[int(year)] = season_stats
            
            # Calculate totals
            totals = {}
            for metric in available_metrics:
                total = pd.to_numeric(player_df[metric], errors='coerce').sum()
                totals[metric] = float(total) if pd.notna(total) else 0.0
            
            # Get latest season stats
            latest = {}
            if latest_years:
                latest_year_df = player_df[player_df["_season_year"] == latest_years[-1]]
                for metric in available_metrics:
                    value = pd.to_numeric(latest_year_df[metric], errors='coerce').sum()
                    latest[metric] = float(value) if pd.notna(value) else 0.0
            
            results[canonical_name] = {
                "found": True,
                "per_season": per_season,
                "totals": totals,
                "latest": latest
            }
        
        response = {
            "ok": True,
            "players": results,
            "seasons": [int(y) for y in latest_years],
            "metrics": available_metrics
        }
        
        # Add cohort statistics if requested
        if include_cohort and latest_years:
            cohort_stats = {}
            latest_year = latest_years[-1]
            latest_season_df = filtered_df[filtered_df["_season_year"] == latest_year]
            
            for metric in available_metrics:
                player_stats = latest_season_df.groupby("player")[metric].sum()
                cohort_values = pd.to_numeric(player_stats, errors='coerce').dropna()
                
                if len(cohort_values) > 0:
                    top_cohort = cohort_values.nlargest(cohort_size)
                    cohort_stats[metric] = {
                        "values": top_cohort.tolist(),
                        "count": len(top_cohort),
                        "percentiles": {
                            "25": float(top_cohort.quantile(0.25)),
                            "50": float(top_cohort.quantile(0.50)),
                            "75": float(top_cohort.quantile(0.75)),
                            "90": float(top_cohort.quantile(0.90)),
                            "max": float(top_cohort.max()),
                            "min": float(top_cohort.min())
                        }
                    }
            
            response["cohort"] = cohort_stats
        
        return response
        
    except Exception as e:
        logger.error(f"Multi-metrics aggregation failed: {e}")
        return {
            "ok": False,
            "error": f"Multi-metrics aggregation failed: {str(e)}"
        }

# Update exports
__all__.extend([
    "filter_players_mcp",
    "plot_mcp", 
    "aggregate_group_mcp",
    "plot_group_mcp",
    "get_schema_mcp",
    "aggregate_group_multi_metrics_mcp"
])