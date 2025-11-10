#!/usr/bin/env python3
"""
Improved Football Data Agent (fixed and unified)
- Safer slot-filling + context
- Adaptive plotting + validation
- Confidence-aware auto-fill (no random player substitution)
- Disambiguation UI and pending resolution
- Position-specific defaults requested by the user
- Cohort percentile computation
- Better fallback flow and user-friendly messages
- FIXED: Added missing build_context_from_rag and top_rag_player_name functions
- FIXED: Better conversational handling for "who is X" type questions
"""

import os
import sys
import json
import time
import hashlib
import sqlite3
import traceback
import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import difflib

# plotting libs
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import requests
from io import BytesIO

# for nicer date ticks if needed
from datetime import datetime

# load env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------------- Debug helper ----------------
AGENT_DEBUG = os.getenv("AGENT_DEBUG", "1") not in ("0", "false", "False", "")
def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

def dbg(msg: str, *args):
    if not AGENT_DEBUG:
        return
    try:
        s = msg % args if args else msg
    except Exception:
        s = f"{msg} {args}"
    print(f"[{_now()}] DEBUG: {s}", file=sys.stderr)

def _mask(s: Optional[str], keep=6):
    if not s:
        return "<none>"
    if len(s) <= keep * 2:
        return s[:2] + "..." + s[-2:]
    return s[:keep] + "..." + s[-keep:]

def normalize_text(text: str) -> str:
    """
    Normalize text by removing accents/diacritics.
    e.g., "mbappé" -> "mbappe", "müller" -> "muller"
    """
    # Normalize to NFKD form (decompose accented characters)
    nfkd = unicodedata.normalize('NFKD', text)
    # Filter out combining characters (accents)
    return ''.join([c for c in nfkd if not unicodedata.combining(c)])

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

dbg("Agent starting. AGENT_DEBUG=%s", AGENT_DEBUG)

# ---------------- Config / Defaults ----------------
CACHE_DB_PATH = os.getenv("AGENT_CACHE_DB", "./data/agent_cache.sqlite")
CACHE_TTL_SECS = int(os.getenv("AGENT_CACHE_TTL_SECS", str(24 * 3600)))
CACHE_MAX_ENTRIES = int(os.getenv("AGENT_CACHE_MAX_ENTRIES", "2000"))
DEFAULT_SEASONS_BACK = int(os.getenv("DEFAULT_SEASONS_BACK", "5"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", os.getenv("OPENAI_TEMP", "0.0")))
TOP_RAG_MIN_SCORE = float(os.getenv("TOP_RAG_MIN_SCORE", "0.7"))
MIN_COHORT_FOR_PERCENTILES = int(os.getenv("MIN_COHORT_FOR_PERCENTILES", "20"))

dbg("Config: CACHE_DB_PATH=%s DEFAULT_SEASONS_BACK=%d OPENAI_TEMPERATURE=%s TOP_RAG_MIN_SCORE=%s",
    CACHE_DB_PATH, DEFAULT_SEASONS_BACK, OPENAI_TEMPERATURE, TOP_RAG_MIN_SCORE)

# ---------------- Cache (sqlite) ----------------
def _init_cache_db(path: str = CACHE_DB_PATH):
    dbg("ENTER _init_cache_db path=%s", path)
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        value_json TEXT,
        ts INTEGER
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ts ON cache(ts)")
    conn.commit()
    dbg("Cache DB initialized (path=%s)", path)
    return conn

_cache_conn = _init_cache_db(CACHE_DB_PATH)

def _normalize_key(s: Any) -> str:
    dbg("ENTER _normalize_key type=%s", type(s).__name__)
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True, ensure_ascii=False)
    s = " ".join(s.split())
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    dbg("Normalized key -> %s", h)
    return h

def cache_get(raw_key: Any, ttl: Optional[int] = None) -> Optional[Any]:
    dbg("ENTER cache_get ttl=%s raw_key_preview=%s", ttl, str(raw_key)[:120])
    ttl = CACHE_TTL_SECS if ttl is None else ttl
    k = _normalize_key(raw_key)
    cur = _cache_conn.cursor()
    cur.execute("SELECT value_json, ts FROM cache WHERE key = ?", (k,))
    row = cur.fetchone()
    if not row:
        dbg("cache_get miss key=%s", k)
        return None
    value_json, ts = row
    if int(time.time()) - int(ts) > ttl:
        dbg("cache_get stale entry (ts=%s now=%s) deleting", ts, int(time.time()))
        cur.execute("DELETE FROM cache WHERE key = ?", (k,))
        _cache_conn.commit()
        return None
    try:
        val = json.loads(value_json)
        dbg("cache_get hit key=%s", k)
        return val
    except Exception as e:
        dbg("cache_get json decode error: %s", e)
        return None

def cache_set(raw_key: Any, value: Any):
    dbg("ENTER cache_set key_preview=%s", str(raw_key)[:120])
    k = _normalize_key(raw_key)
    v = json.dumps(value, ensure_ascii=False, default=str)
    ts = int(time.time())
    cur = _cache_conn.cursor()
    cur.execute("INSERT OR REPLACE INTO cache(key, value_json, ts) VALUES (?, ?, ?)", (k, v, ts))
    _cache_conn.commit()
    cur.execute("SELECT COUNT(*) FROM cache")
    cnt = cur.fetchone()[0]
    dbg("cache_set stored key=%s cnt=%d", k, cnt)
    if cnt > CACHE_MAX_ENTRIES:
        to_delete = cnt - CACHE_MAX_ENTRIES
        dbg("cache_set pruning %d oldest entries", to_delete)
        cur.execute("DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY ts ASC LIMIT ?)", (to_delete,))
        _cache_conn.commit()

# ---------------- MCP client ----------------
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MCP_URL = os.getenv("MCP_URL", "http://localhost:8080/invoke")
MCP_KEY = os.getenv("MCP_API_KEY", "dev-token")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "10"))
HEADERS = {"Content-Type": "application/json", "X-Api-Key": MCP_KEY}

dbg("MCP client configured: MCP_URL=%s MCP_KEY_mask=%s MCP_TIMEOUT=%s", MCP_URL, _mask(MCP_KEY), MCP_TIMEOUT)

_session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=(500,502,503,504))
_session.mount("http://", HTTPAdapter(max_retries=retries))
_session.mount("https://", HTTPAdapter(max_retries=retries))

def call_mcp(tool_name: str, params: dict, use_cache=True):
    dbg("ENTER call_mcp tool=%s params_keys=%s use_cache=%s", tool_name, list(params.keys()) if isinstance(params, dict) else type(params), use_cache)
    key = {"tool": tool_name, "params": params}
    if use_cache:
        cached = cache_get(key)
        if cached is not None:
            dbg("call_mcp returning cached result for tool=%s", tool_name)
            return cached
    payload = {"tool": tool_name, "params": params}
    try:
        r = _session.post(MCP_URL, json=payload, headers=HEADERS, timeout=MCP_TIMEOUT)
        if r.status_code >= 400:
            dbg("call_mcp http error body_preview=%s", r.text[:400])
            return {"ok": False, "error": "http_error", "status_code": r.status_code, "detail": r.text}
    except requests.exceptions.RequestException as e:
        dbg("call_mcp request exception: %s", e)
        return {"ok": False, "error": "mcp_request_failed", "detail": str(e)}
    try:
        j = r.json()
    except Exception as e:
        dbg("call_mcp json decode error: %s raw=%s", e, r.text[:300])
        return {"ok": False, "error": "invalid_json", "detail": str(e), "raw": r.text}
    if not j.get("ok"):
        dbg("call_mcp mcp_error detail=%s", str(j)[:400])
        return {"ok": False, "error": "mcp_error", "detail": j}
    if use_cache:
        cache_set(key, j.get("result"))
    dbg("call_mcp returning result (tool=%s)", tool_name)
    return j.get("result")

# MCP wrappers
def rag_search_mcp(query: str, k: int = 5):
    try:
        res = call_mcp("search_player", {"query": query, "k": k})
        if isinstance(res, list):
            return res
    except Exception as e:
        dbg("rag_search_mcp error: %s", e)
    return []

def get_all_player_names_fuzzy_match(query: str, top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Fallback fuzzy matching against all player names in database.
    Used when RAG semantic search fails to find typo matches.
    """
    try:
        # Get all unique player names from the database
        result = filter_players_mcp(team=None, position=None, seasons_back=10)
        if not result or not result.get("ok"):
            return []

        all_players = result.get("players", [])
        if not all_players:
            return []

        # Calculate edit distance for each unique player name
        query_normalized = normalize_text(query.lower().strip())
        player_distances = []

        for player in all_players:
            player_normalized = normalize_text(player.lower())
            player_parts = player_normalized.split()

            # Calculate minimum distance across full name and all parts
            distances = [levenshtein_distance(query_normalized, player_normalized)]
            distances.extend([levenshtein_distance(query_normalized, part) for part in player_parts])
            min_dist = min(distances)

            # Only consider close matches (edit distance <= 2 for typos)
            if min_dist <= 2:
                player_distances.append({
                    "player": player,
                    "edit_distance": min_dist,
                    "score": 1.0 / (min_dist + 1)  # Higher score for lower distance
                })

        # Sort by edit distance (closest first)
        player_distances.sort(key=lambda x: x["edit_distance"])

        dbg("Fuzzy fallback for '%s': found %d close matches (edit<=2)", query, len(player_distances))
        return player_distances[:top_n]

    except Exception as e:
        dbg("get_all_player_names_fuzzy_match error: %s", e)
        return []

def resolve_player_name_with_rag(player_name: str, require_confirmation: bool = True) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    """
    Resolve a player name to canonical form using RAG + fuzzy fallback.
    Returns: (canonical_name, ambiguous_hits) where ambiguous_hits is set if user needs to clarify.
    """
    dbg("ENTER resolve_player_name_with_rag player_name=%s require_confirmation=%s", player_name, require_confirmation)

    hits = rag_search_mcp(player_name, k=50)  # Get more results to ensure all matches found
    if not hits:
        dbg("resolve_player_name_with_rag: no RAG hits, trying fuzzy fallback")
        # Fallback: Direct fuzzy matching against all player names
        fuzzy_hits = get_all_player_names_fuzzy_match(player_name, top_n=10)
        if fuzzy_hits:
            dbg("Fuzzy fallback found %d matches", len(fuzzy_hits))
            hits = fuzzy_hits
        else:
            dbg("No matches found even with fuzzy fallback")
            return None, None

    # Boost scores for famous players (heuristic: longer rag_summary = more data = more famous)
    for h in hits:
        summary_len = len(str(h.get("rag_summary") or ""))
        if summary_len > 500:  # Lots of data about this player
            h["score"] = float(h.get("score", 0.0)) * 1.2  # 20% boost
            dbg("Boosting score for %s (long summary)", h.get("player"))

    # Re-sort after boosting
    hits = sorted(hits, key=lambda x: -float(x.get("score", 0.0)))

    # CRITICAL FIX: Deduplicate by player name (same player, different seasons)
    seen_players = {}
    deduped_hits = []
    for h in hits:
        player = h.get("player")
        score = float(h.get("score", 0.0))

        # Keep only the best season for each unique player
        if player not in seen_players:
            seen_players[player] = h
            deduped_hits.append(h)
        elif score > float(seen_players[player].get("score", 0.0)):
            # Replace with higher-scored season
            seen_players[player] = h
            deduped_hits = [d for d in deduped_hits if d.get("player") != player]
            deduped_hits.append(h)

    # Re-sort deduped list
    deduped_hits = sorted(deduped_hits, key=lambda x: -float(x.get("score", 0.0)))
    hits = deduped_hits

    # IMPORTANT: For short queries (last names / typos), use multi-strategy matching
    # Strategy 1: Very close edit distance (likely typos) - "petri" -> "pedri" (distance 1)
    # Strategy 2: Exact substring matches - "mbappe" in "kylian mbappé"
    # Strategy 3: Fuzzy RAG matches - everything else
    query_lower = player_name.lower().strip()
    query_normalized = normalize_text(query_lower)

    if len(query_lower) <= 15:  # Short query, likely a last name, partial name, or typo
        # Calculate edit distance for each player name (check both first and last names)
        for h in hits:
            player_full = normalize_text(h.get("player", "").lower())
            player_parts = player_full.split()

            # Calculate minimum distance across full name and all parts
            distances = [levenshtein_distance(query_normalized, player_full)]
            distances.extend([levenshtein_distance(query_normalized, part) for part in player_parts])
            h["edit_distance"] = min(distances)

        # Categorize matches
        very_close_matches = [h for h in hits if h.get("edit_distance", 999) <= 2]  # Typos: 1-2 char difference
        exact_substring_matches = [h for h in hits if h.get("edit_distance", 999) > 2 and query_normalized in normalize_text(h.get("player", "").lower())]
        fuzzy_matches = [h for h in hits if h.get("edit_distance", 999) > 2 and query_normalized not in normalize_text(h.get("player", "").lower())]

        # Sort very close matches by edit distance (closest first), then by fame, then by score
        # This ensures that for players with the same edit distance (e.g., "mbappé" vs "mbappe"),
        # the more famous one (kylian) is prioritized over the less famous one (ethan)
        very_close_matches = sorted(very_close_matches,
                                   key=lambda x: (x.get("edit_distance", 999),
                                                 -len(str(x.get("rag_summary") or "")),
                                                 -float(x.get("score", 0.0))))

        # CRITICAL: Sort exact substring matches by fame (summary length) to prioritize famous players
        # E.g., "mbappe" should match "kylian mbappé" (famous) not "ethan mbappé" (less famous)
        exact_substring_matches = sorted(exact_substring_matches,
                                        key=lambda x: (-len(str(x.get("rag_summary") or "")), -float(x.get("score", 0.0))))

        # CRITICAL: If we have exact substring matches and the top one is CLEARLY more famous (3x summary length),
        # auto-select it to avoid confusion (e.g., "mbappe" → "kylian mbappé" not "ethan mbappé")
        if len(exact_substring_matches) >= 2:
            top_fame = len(str(exact_substring_matches[0].get("rag_summary") or ""))
            second_fame = len(str(exact_substring_matches[1].get("rag_summary") or ""))
            if top_fame > second_fame * 3:
                canonical = exact_substring_matches[0].get("player")
                dbg("Auto-selecting clearly more famous player '%s' (fame: %d vs %d) for substring match '%s'",
                    canonical, top_fame, second_fame, query_normalized)
                return canonical, None

        # Debug: Log the top very_close matches with their edit distances
        if very_close_matches:
            dbg("Top very_close matches for '%s':", query_normalized)
            for i, h in enumerate(very_close_matches[:5]):
                dbg("  %d. %s (edit_dist=%d, score=%.2f)",
                    i+1, h.get("player"), h.get("edit_distance", 999), float(h.get("score", 0.0)))

        # Prioritize: very close typo matches > exact substrings > fuzzy matches
        hits = very_close_matches + exact_substring_matches + fuzzy_matches
        dbg("Prioritized matches for '%s': %d very_close (edit<=2), %d exact_substring, %d fuzzy",
            query_normalized, len(very_close_matches), len(exact_substring_matches), len(fuzzy_matches))

        # CRITICAL: Check for EXACT matches first (edit distance 0)
        exact_matches = [h for h in very_close_matches if h.get("edit_distance", 999) == 0]
        if len(exact_matches) > 1:
            # Multiple exact matches (e.g., "mbappe" matches both "kylian mbappé" and "ethan mbappé")
            # ALWAYS ask user to disambiguate
            dbg("Found %d exact matches (edit_distance=0) - asking user to choose", len(exact_matches))
            return None, exact_matches[:5]
        elif len(exact_matches) == 1:
            # Single exact match - auto-select
            canonical = exact_matches[0].get("player")
            dbg("Found single exact match (edit_distance=0): '%s'", canonical)
            return canonical, None

        # CRITICAL: For VERY close matches (edit distance 1-2), check if we need disambiguation
        # E.g., "petri" → "pedri" (typo), or "mbappe" → "kylian mbappé" vs "ethan mbappé" (multiple players)
        perfect_typo_matches = [h for h in very_close_matches if h.get("edit_distance", 999) <= 2]
        if len(perfect_typo_matches) > 1:
            # Multiple close matches - ALWAYS ask user to confirm which one they meant
            dbg("Found %d close matches (edit_distance<=2) - asking user to choose", len(perfect_typo_matches))
            return None, perfect_typo_matches[:5]
        elif len(perfect_typo_matches) == 1:
            # Only one close match - auto-select it
            canonical = perfect_typo_matches[0].get("player")
            dbg("Found single close match (edit_distance=%d): '%s'", perfect_typo_matches[0].get("edit_distance"), canonical)
            return canonical, None

        # FALLBACK: No perfect typos found in RAG results, try direct fuzzy matching
        if not perfect_typo_matches:
            # Try fuzzy matching on both the full query and individual words
            # This handles cases like "who is petri" where we need to extract "petri"
            queries_to_try = [player_name]

            # Also try individual words from the query (filter out short words like "is", "who")
            words = [w for w in query_lower.split() if len(w) >= 4 and not w in ('who', 'is', 'the', 'what', 'when', 'where')]
            queries_to_try.extend(words)

            dbg("No perfect typos in RAG results - trying fuzzy fallback for queries: %s", queries_to_try)

            for query in queries_to_try:
                if len(query) > 15:  # Skip very long queries
                    continue

                fuzzy_hits = get_all_player_names_fuzzy_match(query, top_n=10)
                if fuzzy_hits:
                    # Check if fuzzy results have edit distance = 1 matches (typos)
                    fuzzy_perfect = [h for h in fuzzy_hits if h.get("edit_distance") == 1]
                    if fuzzy_perfect:
                        dbg("Fuzzy fallback found %d perfect typo matches (edit_distance=1) for '%s' - asking user to confirm", len(fuzzy_perfect), query)
                        # Always ask user to confirm typo corrections
                        return None, fuzzy_perfect[:10]

    # Filter to high-confidence matches
    high_confidence = [h for h in hits if float(h.get("score", 0.0)) >= TOP_RAG_MIN_SCORE]

    if len(high_confidence) == 1:
        # Single high-confidence match - auto-resolve
        canonical = high_confidence[0].get("player")
        dbg("resolve_player_name_with_rag: single high-confidence match '%s'", canonical)
        return canonical, None

    if len(high_confidence) > 1:
        # Multiple DIFFERENT high-confidence players - need disambiguation
        # BUT: if one is MUCH clearly better (>50% score difference OR 2x fame heuristic), use it
        top_score = float(high_confidence[0].get("score", 0.0))
        second_score = float(high_confidence[1].get("score", 0.0))

        # Also check fame heuristic (summary length)
        top_fame = len(str(high_confidence[0].get("rag_summary") or ""))
        second_fame = len(str(high_confidence[1].get("rag_summary") or ""))

        # Auto-select only if BOTH conditions are true:
        # 1. Score is >50% better OR fame is 2x better
        # 2. Score difference exists
        score_much_better = top_score > second_score * 1.5
        fame_much_better = top_fame > second_fame * 2

        if (score_much_better or fame_much_better) and top_score > second_score:
            canonical = high_confidence[0].get("player")
            dbg("resolve_player_name_with_rag: top player clearly dominant (score: %.3f vs %.3f, fame: %d vs %d), using '%s'",
                top_score, second_score, top_fame, second_fame, canonical)
            return canonical, None

        dbg("resolve_player_name_with_rag: %d unique high-confidence players, need disambiguation", len(high_confidence))
        if require_confirmation:
            return None, high_confidence[:5]  # Max 5 unique players
        else:
            # If not requiring confirmation, take the top one
            return high_confidence[0].get("player"), None

    # Only medium/low confidence matches
    if len(hits) > 0:
        # Check for multiple medium-confidence matches (score >= 0.45)
        medium_confidence = [h for h in hits if float(h.get("score", 0.0)) >= 0.45]

        if len(medium_confidence) > 1:
            # Multiple medium-confidence players - need disambiguation
            dbg("resolve_player_name_with_rag: %d medium-confidence players, need disambiguation", len(medium_confidence))
            if require_confirmation:
                return None, medium_confidence[:5]  # Max 5 unique players
            else:
                return medium_confidence[0].get("player"), None
        elif len(medium_confidence) == 1:
            # Single medium-confidence match
            canonical = medium_confidence[0].get("player")
            top_score = float(medium_confidence[0].get("score", 0.0))
            dbg("resolve_player_name_with_rag: single medium-confidence match '%s' (score=%.3f)", canonical, top_score)
            return canonical, None
        else:
            # All matches are low confidence
            top_score = float(hits[0].get("score", 0.0))
            dbg("resolve_player_name_with_rag: low confidence (top score=%.3f)", top_score)
            if require_confirmation and len(hits) >= 2:
                return None, hits[:3]  # Show top 3 unique players for disambiguation

    return None, None


def aggregate_mcp(player_name: str, stat: str = "goals", seasons_back: int = 3):
    try:
        # First try exact match
        payload = {"player_name": player_name, "player": player_name, "stat": stat, "seasons_back": seasons_back}
        result = call_mcp("aggregate_player_stat", payload)
        
        # If not found, resolve via RAG (don't require confirmation here, we're in tool call)
        if isinstance(result, dict) and not result.get("found"):
            dbg("aggregate_mcp: exact match failed for '%s', trying RAG resolution", player_name)
            canonical, ambiguous = resolve_player_name_with_rag(player_name, require_confirmation=False)
            
            if canonical:
                dbg("aggregate_mcp: retrying with canonical name '%s'", canonical)
                payload = {"player_name": canonical, "player": canonical, "stat": stat, "seasons_back": seasons_back}
                result = call_mcp("aggregate_player_stat", payload, use_cache=False)
                
                if isinstance(result, dict) and result.get("found"):
                    dbg("aggregate_mcp: SUCCESS with canonical name '%s'", canonical)
                    return result
        
        return result
    except Exception as e:
        dbg("aggregate_mcp exception: %s", e)
        return {"ok": False, "error": str(e)}

def plot_mcp(player_name: str, metrics):
    try:
        if isinstance(metrics, str):
            metrics = [m.strip() for m in metrics.split(",") if m.strip()]
        payload = {"player_name": player_name, "player": player_name, "metrics": metrics}
        return call_mcp("plot_player", payload)
    except Exception as e:
        dbg("plot_mcp exception: %s", e)
        return {"ok": False, "error": str(e)}

def filter_players_mcp(team: Optional[str] = None, position: Optional[str] = None, seasons_back: int = 5):
    try:
        return call_mcp("filter_players", {"team": team, "position": position, "seasons_back": seasons_back})
    except Exception as e:
        dbg("filter_players_mcp error: %s", e)
        return {"ok": False, "error": str(e)}

def aggregate_group_mcp(players: List[str], stat: str = "goals", seasons_back: int = 5):
    try:
        return call_mcp("aggregate_group_stats", {"players": players, "stat": stat, "seasons_back": seasons_back})
    except Exception as e:
        dbg("aggregate_group_mcp error: %s", e)
        return {"ok": False, "error": str(e)}

def plot_group_mcp(players: List[str], metrics: Optional[List[str]] = None, seasons_back: int = 5):
    try:
        return call_mcp("plot_group", {"players": players, "metrics": metrics, "seasons_back": seasons_back})
    except Exception as e:
        dbg("plot_group_mcp error: %s", e)
        return {"ok": False, "error": str(e)}

def get_schema_mcp():
    try:
        r = call_mcp("get_schema", {})
        if isinstance(r, list):
            return r
    except Exception as e:
        dbg("get_schema_mcp error: %s", e)
    return None

def rank_players_mcp(stat: str = "goals", top_n: int = 10, team: Optional[str] = None,
                     position: Optional[str] = None, season_year: Optional[int] = None,
                     seasons_back: int = 5):
    """Fast bulk ranking of players by a statistic."""
    try:
        return call_mcp("rank_players", {
            "stat": stat,
            "top_n": top_n,
            "team": team,
            "position": position,
            "season_year": season_year,
            "seasons_back": seasons_back
        })
    except Exception as e:
        dbg("rank_players_mcp error: %s", e)
        return {"ok": False, "error": str(e)}

def aggregate_group_multi_metrics_mcp(players: List[str], metrics: List[str],
                                      seasons_back: int = 5, include_cohort: bool = True,
                                      cohort_size: int = 200):
    """Fast bulk aggregation of multiple metrics for multiple players."""
    try:
        return call_mcp("aggregate_group_multi_metrics", {
            "players": players,
            "metrics": metrics,
            "seasons_back": seasons_back,
            "include_cohort": include_cohort,
            "cohort_size": cohort_size
        })
    except Exception as e:
        dbg("aggregate_group_multi_metrics_mcp error: %s", e)
        return {"ok": False, "error": str(e)}

# ---------------- OpenAI adapter ----------------
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    dbg("Missing OPENAI_API_KEY in environment (.env). Exiting.")
    print("Missing OPENAI_API_KEY in environment (.env).")
    sys.exit(1)
dbg("OpenAI model=%s key_mask=%s", OPENAI_CHAT_MODEL, _mask(OPENAI_API_KEY))

class OpenAIAdapter:
    def __init__(self, api_key: str, model: str):
        try:
            from openai import OpenAI
        except Exception as e:
            raise ImportError("Install openai>=1.0.0. Err: " + str(e))
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def predict(self, prompt: str, max_tokens: int = 512, temperature: float = OPENAI_TEMPERATURE) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role":"user","content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            choice = resp.choices[0]
            if hasattr(choice, "message"):
                content = getattr(choice.message, "content", None)
            else:
                content = choice.get("message", {}).get("content")
        except Exception:
            content = None
        return content if content is not None else str(resp)

    def __call__(self, prompt: str, **kwargs):
        return self.predict(prompt, **kwargs)

llm = OpenAIAdapter(api_key=OPENAI_API_KEY, model=OPENAI_CHAT_MODEL)
dbg("Using OpenAIAdapter (direct OpenAI client).")

# ---------------- Intent stuff & prompts ----------------
COMMON_PLOT_METRICS = ["goals_per_90", "xg_per_90", "npxg_per_90", "assists_per_90", "shots_per_90"]
COMMON_STATS = ["goals", "assists", "playing_time_starts", "minutes", "shots"]

def classify_intent(text: str) -> str:
    t = (text or "").lower()
    # Check for ranking queries first (top N, best, highest, most, etc.)
    if re.search(r"\btop\s+\d+\b|\bbest\s+\d+\b|\bhighest\b|\branking\b|\bleading\b|\bmost\b.*scorer", t):
        return "ranking"
    if re.search(r"\bplot\b|\bshow\b|\bvisualize\b|\bgraph\b", t):
        return "plot"
    if re.search(r"\baggregate\b|\bsum\b|\btotal\b|\bhow many\b|\bcount\b|\bhave\b", t):
        return "aggregate"
    if re.search(r"\bsearch\b|\bfind\b|\brag\b|\btell me about\b|\bwho\b|\bwhos\b|\bwho is\b", t):
        return "search"
    if re.search(r"\bcompare\b|\bvs\b|\bversus\b|\bv s\b", t):
        return "compare"
    return "natural"

# ---------------- Metric aliasing ----------------
METRIC_ALIASES = {
    # wages / pay
    "weekly wage": "gross_p_w_eur",
    "wage per week": "gross_p_w_eur",
    "gross per week": "gross_p_w_eur",
    "gross weekly pay": "gross_p_w_eur",
    "weekly salary": "gross_p_w_eur",
    "weekly pay": "gross_p_w_eur",
    "salary per week": "gross_p_w_eur",

    "annual salary": "gross_p_y_eur",
    "yearly salary": "gross_p_y_eur",
    "salary per year": "gross_p_y_eur",
    "gross per year": "gross_p_y_eur",
    "annual wage": "gross_p_y_eur",

    "adjusted gross euro": "adj_gross_eur",
    "adjusted gross": "adj_gross_eur",

    # identity / demographics
    "nationality": "nation",
    "country": "nation",
    "nation": "nation",
    "national team": "nation",

    "position": "pos",
    "playing position": "pos",
    "role": "pos",

    "team": "squad",
    "club": "squad",
    "squad": "squad",

    "competition": "comp",
    "league": "comp",
    "tournament": "comp",

    "age": "age_stats",
    "player age": "age_stats",

    "date of birth": "born",
    "birthdate": "born",
    "born": "born",

    # playing time
    "appearances": "playing_time_mp",
    "matches played": "playing_time_mp",
    "apps": "playing_time_mp",
    "games played": "playing_time_mp",

    "starts": "playing_time_starts",
    "games started": "playing_time_starts",
    "starting appearances": "playing_time_starts",

    "minutes played": "playing_time_min",
    "minutes": "playing_time_min",
    "mins": "playing_time_min",

    "played nineties": "playing_time_90s",
    "full 90 minutes": "playing_time_90s",
    "played 90s": "playing_time_90s",
    "full match equivalents": "playing_time_90s",
    "90 equivalents": "playing_time_90s",

    # goals & assists
    "goals": "goals",
    "goal": "goals",
    "g": "goals",

    "assists": "assists",
    "assist": "assists",
    "a": "assists",

    "goal contributions": "goals_assists",
    "goals and assists": "goals_assists",
    "g plus a": "goals_assists",
    "goals plus assits": "goals_assists",
    "goals and assits": "goals_assists",

    "non penalty goals": "goals_no_pk",
    "goals excluding penalties": "goals_no_pk",
    "goals no penalty": "goals_no_pk",
    "non pens goals": "goals_no_pk",

    "penalty performance": "performance_pk",
    "penalty pk performance": "performance_pk",
    "penalties scored": "performance_pk",
    "pens scored": "performance_pk",

    "penalties taken": "penalties_taken",
    "pens taken": "penalties_taken",

    # discipline
    "yellow cards": "yellow_cards",
    "yellows": "yellow_cards",
    "red cards": "red_cards",
    "reds": "red_cards",
    "sent off": "red_cards",
    "send off": "red_cards",

    # xg / xa family
    "xg": "xg",
    "expected goals": "xg",
    "expected goal": "xg",

    "npxg": "npxg",
    "non penalty xg": "npxg",
    "non-penalty xg": "npxg",
    "non penalty expected goals": "npxg",
    "non pen expected goals": "npxg",

    "xag": "xag",
    "xa g": "xag",
    "expected assists g": "xag",
    "expected assists": "xag",

    "npxg plus xag": "npxg_xag",
    "npxg and xag": "npxg_xag",
    "npxg xag": "npxg_xag",
    "non penalty expected goals plus assists": "npxg_xag",
    "non penalty expected goals and assists": "npxg_xag",

    # progressive actions
    "progressive carries": "progressive_carries",
    "progressive carry": "progressive_carries",
    "prog carries": "progressive_carries",
    "taking the ball forward":  "progressive_carries",

    "progressive passes": "progressive_passes",
    "progressive pass": "progressive_passes",
    "passes (progressive)": "progressive_passes",
    "passes": "progressive_passes",
    "passes forward": "progressive_passes",

    "progressive received": "progressive_received",
    "progressive receives": "progressive_received",
    "passes received": "progressive_received",
    "progressive passes received": "progressive_received",

    # per-90 rates
    "goals per 90": "goals_per_90",
    "goals/90": "goals_per_90",
    "goals per 90 mins": "goals_per_90",
    "goals/90 mins": "goals_per_90",
    "goals per ninety": "goals_per_90",
    "goals per ninety mins": "goals_per_90",

    "assists per 90": "assists_per_90",
    "assists/90": "assists_per_90",
    "assists per 90 mins": "assists_per_90",
    "assists/90 mins": "assists_per_90",

    "goal contributions per 90": "goals_assists_per_90",
    "g plus a per 90": "goals_assists_per_90",
    "goals and assists per 90": "goals_assists_per_90",
    "goal plus assists per 90": "goals_assists_per_90",

    "non penalty goals per 90": "goals_no_pk_per_90",
    "non pen goals per 90": "goals_no_pk_per_90",
    "goals excluding penalty per 90": "goals_no_pk_per_90",

    "goal contributions no penalty per 90": "goals_assists_no_pk_per_90",
    "g plus a without pens per 90": "goals_assists_no_pk_per_90",

    "xg per 90": "xg_per_90",
    "xg/90": "xg_per_90",
    "expected goals per 90": "xg_per_90",
    "expected goals/90": "xg_per_90",

    "xag per 90": "xag_per_90",
    "xag/90": "xag_per_90",
    "expected assists per 90": "xag_per_90",
    "expected assists/90": "xag_per_90",

    "xg plus xag per 90": "xg_xag_per_90",
    "xg xag per 90": "xg_xag_per_90",

    "npxg per 90": "npxg_per_90",
    "npxg/90": "npxg_per_90",

    "npxg plus xag per 90": "npxg_xag_per_90",

    # season
    "season": "season",
    "year": "season",
    "campaign": "season",

    "mimutes": "mins"
}

KNOWN_METRICS = list(set(list(METRIC_ALIASES.values()) + COMMON_PLOT_METRICS + COMMON_STATS))

def normalize_metric_token(token: str, available_cols: Optional[List[str]] = None) -> Optional[str]:
    """Normalize metric tokens using METRIC_ALIASES, available schema, and fuzzy matches."""
    if not token:
        return None
    k = token.strip().lower()
    # exact alias
    if k in METRIC_ALIASES:
        candidate = METRIC_ALIASES[k]
        if available_cols:
            if candidate in available_cols:
                return candidate
            lowered = {c.lower(): c for c in available_cols}
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]
        return candidate
    # exact match against available_cols
    if available_cols:
        lowered = {c.lower(): c for c in available_cols}
        if k in lowered:
            return lowered[k]
    # fuzzy match to alias keys
    best = difflib.get_close_matches(k, list(METRIC_ALIASES.keys()), n=1, cutoff=0.72)
    if best:
        return METRIC_ALIASES[best[0]]
    # fuzzy match to available cols
    if available_cols:
        best2 = difflib.get_close_matches(k, [c.lower() for c in available_cols], n=1, cutoff=0.6)
        if best2:
            found = next(c for c in available_cols if c.lower() == best2[0])
            return found
    # fuzzy to KNOWN_METRICS
    best3 = difflib.get_close_matches(k, [m.lower() for m in KNOWN_METRICS], n=1, cutoff=0.65)
    if best3:
        candidate = next((m for m in KNOWN_METRICS if m.lower() == best3[0]), None)
        if candidate:
            return candidate
    return token

_schema_cache = None
def get_available_columns():
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    cols = get_schema_mcp()
    if isinstance(cols, list) and cols:
        _schema_cache = cols
        dbg("Obtained schema columns from MCP: %s", cols[:20])
        return cols
    return None

# ---------------- Conversation context / slot management ----------------
CONTEXT = {
    "last_players": [],
    "last_intent": None,
    "last_hits": None,
    "history": [],
    "pending_disambig": None

}
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "12"))

def push_context(player_names: List[str], intent: str, hits: Optional[List[Dict[str,Any]]] = None):
    if player_names:
        for p in reversed(player_names):
            pn = p.strip()
            if pn and pn not in CONTEXT["last_players"]:
                CONTEXT["last_players"].insert(0, pn)
        CONTEXT["last_players"] = CONTEXT["last_players"][:8]

    CONTEXT["last_intent"] = intent
    if hits is not None:
        CONTEXT["last_hits"] = hits
    CONTEXT["history"].append({"time": int(time.time()), "intent": intent, "players": player_names})
    CONTEXT["history"] = CONTEXT["history"][-MAX_HISTORY:]
    dbg("Context updated: last_players=%s last_intent=%s", CONTEXT["last_players"][:3], CONTEXT["last_intent"])

def resolve_pronouns_or_last_player(text: str) -> Optional[str]:
    """If user used 'him/her/they' or 'his/her', resolve to last player in context."""
    t = (text or "").lower()
    if re.search(r"\b(him|his|he|she|her|they|them)\b", t):
        if CONTEXT["last_players"]:
            dbg("Resolved pronoun to last player %s", CONTEXT["last_players"][0])
            return CONTEXT["last_players"][0]
    return None

def resolve_pronouns_in_player_list(players: List[str], query_text: str = "") -> List[str]:
    """
    Resolve pronouns within a list of player names.

    IMPORTANT: Only resolves pronouns if the query looks like a follow-up question.
    Avoids resolving pronouns for completely new questions.
    """
    if not players:
        return players

    resolved = []
    pronouns = {"him", "his", "he", "she", "her", "they", "them", "herself", "himself", "themselves"}

    # Check if this looks like a new question (not a follow-up)
    # If user is asking about a new topic, don't resolve pronouns
    # BUT: Always resolve pronouns for comparison questions
    query_lower = query_text.lower()

    comparison_indicators = ['vs', 'versus', 'or', 'better', 'worse', 'compare']
    is_comparison = any(indicator in query_lower for indicator in comparison_indicators)

    new_question_indicators = [
        r"\b(who is|whos|who's)\b",
        r"^(tell me about|describe|explain)",
        r"^(search|find|lookup)",
    ]

    is_new_question = (not is_comparison) and any(re.search(pattern, query_lower) for pattern in new_question_indicators)

    for player in players:
        player_lower = player.strip().lower()
        if player_lower in pronouns:
            # DON'T resolve if this looks like a new question
            if is_new_question:
                dbg("Not resolving pronoun '%s' - detected new question pattern", player)
                resolved.append(player)
            # Replace pronoun with player(s) from context
            elif CONTEXT["last_players"]:
                # PLURAL pronouns should resolve to multiple players
                if player_lower in {"they", "them", "themselves"}:
                    # For comparisons, we need at least 2 players
                    num_players = min(len(CONTEXT["last_players"]), 3 if is_comparison else 2)
                    for p in CONTEXT["last_players"][:num_players]:
                        resolved.append(p)
                    dbg("Resolved plural pronoun '%s' to %d players: %s", player, num_players, CONTEXT["last_players"][:num_players])
                else:
                    # Singular pronoun, just add first player
                    resolved.append(CONTEXT["last_players"][0])
                    dbg("Resolved singular pronoun '%s' to last player '%s'", player, CONTEXT["last_players"][0])
            else:
                dbg("Found pronoun '%s' but no context player available", player)
                # Keep the pronoun as-is, will be handled later
                resolved.append(player)
        else:
            resolved.append(player)

    return resolved

# ---------------- Name heuristics & disambiguation helpers ----------------
def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = re.sub(r"[^\w\s']", " ", name)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ---------------- Team name normalization ----------------
TEAM_ALIASES = {
    # English Premier League
    "man city": "manchester city",
    "mancity": "manchester city",
    "man utd": "manchester utd",
    "man united": "manchester utd",
    "manutd": "manchester utd",
    "manchester united": "manchester utd",
    "spurs": "tottenham",
    "arsenal": "arsenal",
    "chelsea": "chelsea",
    "liverpool": "liverpool",
    "newcastle": "newcastle utd",
    "west ham": "west ham",
    "brighton": "brighton",
    "crystal palace": "crystal palace",
    "everton": "everton",
    "fulham": "fulham",
    "aston villa": "aston villa",
    "wolves": "wolves",

    # La Liga
    "barca": "barcelona",
    "barça": "barcelona",
    "barcelona": "barcelona",
    "real madrid": "real madrid",
    "madrid": "real madrid",
    "atletico": "atlético madrid",
    "atletico madrid": "atlético madrid",
    "atleti": "atlético madrid",
    "sevilla": "sevilla",
    "valencia": "valencia",
    "villarreal": "villarreal",
    "real sociedad": "real sociedad",
    "athletic club": "athletic club",
    "athletic": "athletic club",
    "betis": "real betis",
    "real betis": "real betis",

    # Bundesliga
    "bayern": "bayern munich",
    "bayern munich": "bayern munich",
    "dortmund": "dortmund",
    "bvb": "dortmund",
    "leipzig": "rb leipzig",
    "rb leipzig": "rb leipzig",
    "leverkusen": "leverkusen",
    "bayer leverkusen": "leverkusen",

    # Serie A
    "inter": "inter",
    "inter milan": "inter",
    "milan": "milan",
    "ac milan": "milan",
    "juve": "juventus",
    "juventus": "juventus",
    "roma": "roma",
    "napoli": "napoli",
    "lazio": "lazio",
    "atalanta": "atalanta",
    "fiorentina": "fiorentina",

    # Ligue 1
    "psg": "paris s-g",
    "paris": "paris s-g",
    "paris saint-germain": "paris s-g",
    "paris sg": "paris s-g",
    "marseille": "marseille",
    "om": "marseille",
    "lyon": "lyon",
    "ol": "lyon",
    "monaco": "monaco",
    "lille": "lille",
}

def normalize_team_name(team: Optional[str]) -> Optional[str]:
    """
    Normalize team name to match database format.
    - Converts to lowercase
    - Handles common aliases (Barca -> barcelona, Man City -> manchester city)
    - Strips extra whitespace
    """
    if not team:
        return None

    team_lower = team.lower().strip()
    team_lower = re.sub(r"\s+", " ", team_lower)  # Collapse multiple spaces

    # Check if it's an alias
    if team_lower in TEAM_ALIASES:
        canonical = TEAM_ALIASES[team_lower]
        dbg("Normalized team '%s' -> '%s'", team, canonical)
        return canonical

    # Return lowercase version
    dbg("Team '%s' -> '%s' (no alias match)", team, team_lower)
    return team_lower

def extract_candidate_names_from_text(text: str, max_candidates: int = 4) -> List[str]:
    """Heuristic: find titlecase sequences (1-3 words) as candidate names."""
    if not text:
        return []
    candidates = []
    for m in re.finditer(r"\b([A-Z][a-z]{1,}\b(?:\s+[A-Z][a-z]{1,}\b){0,2})", text):
        cand = m.group(1).strip()
        if cand and cand.lower() not in ("i","you","who"):
            candidates.append(cand)
    m2 = re.findall(r"(?:player|player name|who is|who's)\s*[:\-]?\s*([A-Z][\w\s'\-]{1,60})", text, flags=re.IGNORECASE)
    for c in m2:
        candidates.insert(0, c.strip())
    seen = set()
    out = []
    for c in candidates:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
        if len(out) >= max_candidates:
            break
    return out

def canonicalize_with_hits(candidates: List[str], max_results=6) -> List[Dict[str,Any]]:
    """For each candidate phrase, call rag_search_mcp and collect hits."""
    out = []
    for cand in candidates:
        hits = rag_search_mcp(cand, k=max_results)
        for h in hits:
            if not isinstance(h, dict):
                continue
            name = h.get("player") or h.get("title") or None
            score = 0.0
            try:
                score = float(h.get("score", 0.0)) if h.get("score") is not None else 0.0
            except Exception:
                try:
                    score = float(str(h.get("score")) or 0.0)
                except Exception:
                    score = 0.0
            snippet = h.get("rag_summary") or h.get("summary") or h.get("snippet") or ""
            if name:
                out.append({"player": name, "score": score, "snippet": snippet, "candidate": cand, "raw_hit": h})
    out_sorted = sorted(out, key=lambda x: -float(x.get("score", 0.0)))
    dedup = {}
    for item in out_sorted:
        key = normalize_name(item.get("player") or "").lower()
        if key not in dedup:
            dedup[key] = item
    return list(dedup.values())

def present_disambiguation_options(options: List[Dict[str, Any]], original_text: str, intent_struct: Dict[str,Any]) -> Optional[str]:
    """
    Stores pending disambiguation in CONTEXT and prints numbered choices.
    Returns auto-selected player name if there's only 1 option, otherwise None.
    """
    if not options:
        return None

    # AUTO-SELECT: If there's only 1 option (non-typo), automatically select it
    if len(options) == 1:
        is_typo_suggestion = all(opt.get("edit_distance") == 1 for opt in options if "edit_distance" in opt)

        if is_typo_suggestion:
            # For typo corrections, still ask for confirmation
            name = options[0].get("player") or options[0].get("title") or str(options[0].get("candidate") or "")
            print(f"Did you mean '{name}'? (yes/no or type the correct name)")
            CONTEXT['pending_disambig'] = {
                "options": options,
                "original_text": original_text,
                "original_intent_struct": intent_struct
            }
            dbg("Set pending_disambig with 1 typo option")
            return None
        else:
            # Auto-select the single option
            name = options[0].get("player") or options[0].get("title") or str(options[0].get("candidate") or "")
            dbg("Auto-selecting single disambiguation option: %s", name)
            print(f"→ Matched: {name}")
            return name

    # Check if this is a typo suggestion (all options have edit_distance = 1)
    is_typo_suggestion = all(opt.get("edit_distance") == 1 for opt in options if "edit_distance" in opt)

    if is_typo_suggestion:
        print("Did you mean one of these? Reply with the option number or type the correct name.")
        for i, opt in enumerate(options, start=1):
            name = opt.get("player") or opt.get("title") or str(opt.get("candidate") or "")
            print(f"{i}. {name}")
    else:
        print("I found multiple possible players that match. Which one do you mean? Reply with the option number or type the full name.")
        for i, opt in enumerate(options, start=1):
            name = opt.get("player") or opt.get("title") or str(opt.get("candidate") or "")
            score = opt.get("score")
            snippet = opt.get("snippet") or ""
            line = f"{i}. {name}"
            if score is not None:
                try:
                    line += f"  (confidence {float(score):.2f})"
                except Exception:
                    pass
            if snippet:
                line += f" — {snippet[:120]}"
            print(line)
    CONTEXT['pending_disambig'] = {
        "options": options,
        "original_text": original_text,
        "original_intent_struct": intent_struct
    }
    dbg("Set pending_disambig with %d options", len(options))
    return None

def resolve_pending_disambiguation(user_reply: str) -> Optional[str]:
    """If CONTEXT has 'pending_disambig', try to match user_reply to one of the options."""
    dbg("Reached disamb - resolve pending")
    pd = CONTEXT.get('pending_disambig')
    dbg("pd:", pd)
    if not pd:
        return None
    opts = pd.get("options", [])
    if not opts:
        return None
    s = user_reply.strip()

    # Handle yes/no responses (for typo suggestions)
    if re.match(r"^(yes|y|yeah|yep|sure|ok|okay)$", s.lower()):
        # User confirmed the first option
        if len(opts) >= 1:
            chosen = opts[0].get("player") or opts[0].get("title") or opts[0].get("candidate")
            dbg("User said yes - accepting first option: %s", chosen)
            return chosen
    elif re.match(r"^(no|n|nope|nah)$", s.lower()):
        dbg("User said no - cancelling")
        CONTEXT.pop('pending_disambig', None)
        return "CANCELLED"

    # Allow user to escape with "cancel", "skip", or starting a new query
    if re.match(r"^(cancel|skip|nevermind|new query)", s.lower()):
        CONTEXT.pop('pending_disambig', None)
        return "CANCELLED"

    # IMPROVED: Detect new questions more broadly
    # Pattern 1: Question keywords
    question_patterns = [
        r"\b(who is|whos|who's|tell me about|tell me|describe|explain)\b",
        r"\b(how many|how much|what|where|when|why|which)\b",
        r"\b(plot|show|graph|visualize|display|compare|versus|vs)\b",
        r"\b(what about|info on|information|stats|statistics)\b",
        r"\b(search|find|look up|lookup|get me)\b",
    ]

    for pattern in question_patterns:
        if re.search(pattern, s.lower()):
            dbg("Detected new question pattern: %s - cancelling disambiguation", pattern)
            CONTEXT.pop('pending_disambig', None)
            return "CANCELLED"

    # Pattern 2: Check if user is asking about a DIFFERENT player using RAG
    # Only do this if the input is longer than a simple number/selection
    if len(s.split()) >= 2 and not re.fullmatch(r"\d+", s):
        try:
            # Quick RAG search to see if this looks like a new player query
            hits = rag_search_mcp(s, k=3)
            if hits:
                top_player = hits[0].get("player")
                top_score = float(hits[0].get("score", 0.0))

                # Check if top hit is for a DIFFERENT player than those in disambiguation
                current_players = set(normalize_name(o.get("player") or "").lower() for o in opts)

                if top_score >= 0.7 and normalize_name(top_player or "").lower() not in current_players:
                    dbg("RAG detected different player '%s' (score=%.2f) - treating as new question", top_player, top_score)
                    CONTEXT.pop('pending_disambig', None)
                    return "CANCELLED"
        except Exception as e:
            dbg("Error in RAG-based new question detection: %s", e)

    # numeric choice
    if re.fullmatch(r"\d+", s):
        idx = int(s) - 1
        if 0 <= idx < len(opts):
            chosen = opts[idx].get("player") or opts[idx].get("title") or opts[idx].get("candidate")
            return chosen
    # exact/ci match
    normalized_reply = normalize_name(s).lower()
    for o in opts:
        candidate = (o.get("player") or o.get("title") or o.get("candidate") or "")
        if normalize_name(candidate).lower() == normalized_reply:
            return candidate
    # fuzzy match
    names = [normalize_name(o.get("player") or o.get("title") or o.get("candidate") or "").strip() for o in opts]
    close = difflib.get_close_matches(s, names, n=1, cutoff=0.6)
    dbg("fetching close matches")
    if close:
        for o in opts:
            nm = normalize_name(o.get("player") or o.get("title") or o.get("candidate") or "").strip()
            if nm == close[0]:
                return o.get("player") or o.get("title") or o.get("candidate")
    return None

# ---------------- NEW: RAG context building functions ----------------
def build_context_from_rag(text: str, k: int = 6) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build RAG context from semantic search results.
    Returns (context_string, hits_list)
    """
    dbg("ENTER build_context_from_rag text_preview=%s k=%d", text[:200], k)
    hits = rag_search_mcp(text, k=k)
    if not hits:
        dbg("build_context_from_rag: no hits returned")
        return "", []
    
    context_parts = []
    for i, h in enumerate(hits):
        if not isinstance(h, dict):
            continue
        player = h.get("player") or h.get("title") or "?"
        snippet = h.get("rag_summary") or h.get("snippet") or ""
        score = h.get("score", 0.0)
        season = h.get("season", "")
        
        context_parts.append(
            f"[{i+1}] Player: {player} | Season: {season} | Score: {score:.3f}\n"
            f"    {snippet[:500]}"
        )
    
    context_str = "\n\n".join(context_parts)
    dbg("build_context_from_rag: built context with %d hits", len(hits))
    return context_str, hits


def top_rag_player_name(text: str) -> Tuple[Optional[str], float]:
    """
    Get the top RAG hit player name and score.
    Returns (player_name, score) or (None, 0.0)
    """
    dbg("ENTER top_rag_player_name text_preview=%s", text[:200])
    hits = rag_search_mcp(text, k=1)
    if not hits or not isinstance(hits, list) or len(hits) == 0:
        dbg("top_rag_player_name: no hits")
        return None, 0.0
    
    hit = hits[0]
    if not isinstance(hit, dict):
        dbg("top_rag_player_name: hit is not dict")
        return None, 0.0
    
    player = hit.get("player") or hit.get("title")
    score = 0.0
    try:
        score = float(hit.get("score", 0.0))
    except Exception:
        pass
    
    dbg("top_rag_player_name: returning player=%s score=%s", player, score)
    return player, score

# ---------------- LLM parse slot extractor ----------------
SLOT_PROMPT = """
Extract the structured intent from the user query. Return only valid JSON (no explanation).
Fields:
- intent: one of ["plot","compare","aggregate","list","search","natural"]
- players: list of ALL player names mentioned (including pronouns like "him", "her", "them"). DO NOT include positional phrases like "front three", "back four" as player names.
- team: team/club name or null
- position: player position or null (e.g. "FW", "MF", "DF", "GK" for specific positions)
- metrics: list of metric tokens or null if user didn't specify
- seasons_back: integer or null (e.g., "current" means 1)
- viz: one of ["time_series","radar","both","auto"]
- limit: number of players to return or null (e.g., "front three" means limit=3, "back four" means limit=4)
- sort_by: how to rank players or null (e.g., "starts", "minutes", "goals")

IMPORTANT:
1. For comparison queries like "compare X with Y" or "X vs Y", extract BOTH players.
2. For pronouns like "him", "her", "them", include them in the players list as-is.
3. For positional group queries like "front three", "back four", "starting forwards", DO NOT extract them as player names. Instead:
   - Set position to the position code based on these mappings:
     * "front" / "forwards" / "strikers" / "attackers" → "FW"
     * "midfield" / "midfielders" → "MF"
     * "back" / "defense" / "defenders" → "DF"
     * "goalkeeper" / "keeper" → "GK"
   - Set limit to the number if specified ("three"=3, "four"=4, etc.)
   - Set sort_by to "starts" for starting lineups (or "goals" for top scorers, etc.)
   - Leave players list empty

Examples:
- "compare Messi with Ronaldo" -> players: ["Messi", "Ronaldo"], intent: "compare"
- "compare him with Salah" -> players: ["him", "Salah"], intent: "compare"
- "Haaland vs Mbappe" -> players: ["Haaland", "Mbappe"], intent: "compare"
- "who are the current front three of Barcelona?" -> players: [], team: "Barcelona", position: "FW", limit: 3, sort_by: "starts", seasons_back: 1, intent: "list"
- "Barcelona's back four" -> players: [], team: "Barcelona", position: "DF", limit: 4, sort_by: "starts", intent: "list"
- "top 5 goal scorers in Premier League" -> players: [], position: null, limit: 5, sort_by: "goals", intent: "list"

User query: {query}

Respond ONLY with JSON.
"""

def parse_intent_with_llm(query: str) -> Dict[str, Any]:
    dbg("ENTER parse_intent_with_llm query_preview=%s", query[:200])
    prompt = SLOT_PROMPT.format(query=query)
    raw = llm.predict(prompt, max_tokens=300, temperature=OPENAI_TEMPERATURE)
    dbg("parse_intent_with_llm raw_response_preview=%s", (raw[:400] if raw else "<none>"))
    try:
        import re as _re
        m = _re.search(r"(\{.*\})", raw or "", _re.S)
        jtxt = m.group(1) if m else (raw or "")
        parsed = json.loads(jtxt)
        parsed.setdefault("intent", classify_intent(query))
        parsed.setdefault("players", parsed.get("players") or [])
        parsed.setdefault("team", parsed.get("team"))
        parsed.setdefault("position", parsed.get("position"))
        parsed.setdefault("metrics", parsed.get("metrics"))
        parsed.setdefault("seasons_back", parsed.get("seasons_back"))
        parsed.setdefault("viz", parsed.get("viz", "auto"))
        parsed.setdefault("limit", parsed.get("limit"))
        parsed.setdefault("sort_by", parsed.get("sort_by"))
        dbg("parse_intent_with_llm parsed=%s", json.dumps(parsed)[:500])
    except Exception as e:
        dbg("parse_intent_with_llm JSON parse failed: %s; raw=%s", e, raw)
        players = []
        if "|" in query:
            parts = [p.strip() for p in query.split("|")]
            players = [parts[0]]
        parsed = {"intent": classify_intent(query), "players": players, "team": None, "position": None, "metrics": None, "seasons_back": None, "viz": "auto", "limit": None, "sort_by": None}
        dbg("parse_intent_with_llm fallback=%s", parsed)

    # If no players found by LLM, try heuristics
    # if not parsed.get("players"):
    #     heur_candidates = extract_candidate_names_from_text(query)
    #     dbg("Heuristic name candidates: %s", heur_candidates)
    #     if heur_candidates:
    #         hits = canonicalize_with_hits(heur_candidates, max_results=6)
    #         dbg("canonicalize_with_hits => %s", hits[:6])
    #         if hits:
    #             high = [h for h in hits if float(h.get("score", 0.0)) >= TOP_RAG_MIN_SCORE]
    #             if len(high) == 1:
    #                 parsed["players"] = [high[0]["player"]]
    #             elif len(hits) == 1 and float(hits[0].get("score", 0.0)) >= 0.45:
    #                 parsed["players"] = [hits[0]["player"]]
    #             else:
    #                 parsed["ambiguous_players"] = hits
    return parsed

# ---------------- Metric defaults by position ----------------
POS_DEFAULT_METRICS = {
    "fw": ["goals", "assists"],
    "mf": ["goals", "assists", "progressive_passes"],
    "df": ["playing_time_starts", "playing_time_min"],
    "gk": ["saves", "clean_sheets"],
}

def infer_position_from_rag(rag_hits: List[Dict[str, Any]]) -> Optional[str]:
    """Infer position from RAG hits. Returns 'fw', 'mf', 'df', 'gk' or None."""
    if not rag_hits:
        return None

    token_to_canonical = {
        "gk": "gk", "goalkeeper": "gk", "keeper": "gk", "goalie": "gk",
        "cb": "df", "center back": "df", "centre back": "df", "centre-back": "df",
        "center-back": "df", "centerback": "df", "centreback": "df",
        "defender": "df", "defence": "df", "defensive": "df",
        "fullback": "df", "full-back": "df", "full back": "df",
        "lb": "df", "left back": "df", "left-back": "df", "leftback": "df",
        "rb": "df", "right back": "df", "right-back": "df", "rightback": "df",
        "mid": "mf", "mf": "mf", "midfielder": "mf", "midfield": "mf", "midfielders": "mf",
        "cm": "mf", "central midfielder": "mf", "centre midfielder": "mf",
        "dm": "mf", "defensive midfielder": "mf", "holding midfielder": "mf", "cdm": "mf",
        "am": "mf", "attacking midfielder": "mf", "cam": "mf", "creative midfielder": "mf",
        "fw": "fw", "forward": "fw", "forwards": "fw", "striker": "fw", "st": "fw",
        "cf": "fw", "center forward": "fw", "centre forward": "fw",
        "winger": "fw", "wing": "fw", "rw": "fw", "right wing": "fw", "right winger": "fw",
        "lw": "fw", "left wing": "fw", "left winger": "fw",
    }

    candidate_fields = ["rag_summary", "summary", "title", "snippet", "content", "text", "source"]
    counts = Counter()

    def norm(s: str) -> str:
        s = s.lower()
        s = s.replace("/", " ").replace("-", " ").replace("_", " ")
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    token_variants = sorted(token_to_canonical.keys(), key=lambda x: -len(x))

    for hit in rag_hits:
        texts = []
        for f in candidate_fields:
            v = hit.get(f)
            if isinstance(v, str) and v.strip():
                texts.append(v)
        if isinstance(hit.get("metadata"), dict):
            for v in hit["metadata"].values():
                if isinstance(v, str) and v.strip():
                    texts.append(v)

        for raw_text in texts:
            t = norm(raw_text)
            m = re.search(r"\bpos(?:ition)?\s*[:=]\s*([a-z0-9\/\-\s]+)", t)
            if m:
                for part in re.split(r"[\/,;]| or | and ", m.group(1)):
                    p = part.strip()
                    if not p:
                        continue
                    if p in token_to_canonical:
                        counts[token_to_canonical[p]] += 5
                    else:
                        compact = p.replace(" ", "")
                        if compact in token_to_canonical:
                            counts[token_to_canonical[compact]] += 5
                        else:
                            maybe = difflib.get_close_matches(p, token_to_canonical.keys(), n=1, cutoff=0.8)
                            if maybe:
                                counts[token_to_canonical[maybe[0]]] += 4

            for token in token_variants:
                pattern = r"\b" + re.escape(token) + r"\b"
                if re.search(pattern, t):
                    counts[token_to_canonical[token]] += 1

    if not counts:
        return None
    best, best_count = counts.most_common(1)[0]
    return best

def choose_default_metrics_for_players(players: List[str], rag_hits: List[Dict[str,Any]], available_cols: Optional[List[str]] = None):
    """Choose defaults according to inferred position."""
    pos = infer_position_from_rag(rag_hits)
    if pos:
        if pos in POS_DEFAULT_METRICS:
            metrics = [normalize_metric_token(m, available_cols) for m in POS_DEFAULT_METRICS[pos] if m]
            return [m for m in metrics if m]
    if available_cols:
        out = []
        if "goals" in available_cols:
            out.append("goals")
        if "assists" in available_cols and "assists" not in out:
            out.append("assists")
        if "progressive_passes" in available_cols and "progressive_passes" not in out:
            out.append("progressive_passes")
        for m in COMMON_PLOT_METRICS:
            nm = normalize_metric_token(m, available_cols)
            if nm and nm not in out:
                out.append(nm)
            if len(out) >= 2:
                break
        return out[:3]
    return ["goals","assists"]

# ---------------- Data extraction helpers ----------------
def extract_timeseries_from_aggregate(resp: dict) -> Tuple[List[int], List[Optional[float]]]:
    """Extract (seasons, values) aligned lists from aggregate response."""
    seasons = []
    vals = []
    if not isinstance(resp, dict) or not resp.get("found"):
        return seasons, vals
    per = resp.get("per_season") or []
    for item in per:
        year = item.get("season_year") or item.get("season_label")
        if isinstance(year, int):
            seasons.append(int(year))
        else:
            try:
                seasons.append(int(str(year)[:4]))
            except Exception:
                seasons.append(None)
        vals.append(item.get("value"))
    filtered = [(s, v) for s,v in zip(seasons, vals) if s is not None]
    if not filtered:
        return [], []
    seasons, vals = zip(*filtered)
    return list(seasons), list(vals)

def compute_percentile_in_cohort(value: float, cohort: List[float]) -> float:
    """Simple percentile computation."""
    if not cohort or value is None:
        return float("nan")
    arr = np.array([v for v in cohort if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if arr.size == 0:
        return float("nan")
    pct = float(np.sum(arr <= value) / arr.size) * 100.0
    return pct

# ---------------- Plot helpers ----------------
def safe_save_plot(fig, fname: str):
    fig.savefig(fname, bbox_inches="tight")
    plt.close(fig)
    return fname

def plot_time_series_single(player: str, seasons: List[int], values: List[Optional[float]], metric_name: str, fname: str):
    fig, ax = plt.subplots(figsize=(8,6))
    yrs = np.array(seasons)
    vals = np.array([np.nan if v is None else float(v) for v in values], dtype=float)
    ax.plot(yrs, vals, marker='o', linestyle='-', label=player)
    ax.set_xticks(yrs)
    ax.set_xlabel("Season")
    ax.set_ylabel(metric_name)
    ax.set_title(f"{player} — {metric_name} by season")
    ax.grid(True)
    if np.all(np.isnan(vals)):
        plt.close(fig)
        return None
    return safe_save_plot(fig, fname)

def plot_group_bar_ranking(players: List[str], all_values: Dict[str, List[Optional[float]]], metric_name: str, fname: str):
    """Create a horizontal bar chart ranking players by total metric value"""
    # Calculate totals for each player
    player_totals = []
    for p in players:
        vals = all_values.get(p, [])
        total = sum(v for v in vals if v is not None)
        if total > 0:  # Only include players with data
            player_totals.append((p, total))

    if not player_totals:
        return None

    # Sort by total (descending)
    player_totals.sort(key=lambda x: x[1], reverse=True)

    # Limit to top 30 for readability
    if len(player_totals) > 30:
        player_totals = player_totals[:30]

    names = [p[0] for p in player_totals]
    totals = [p[1] for p in player_totals]

    # Create horizontal bar chart
    fig, ax = plt.subplots(figsize=(10, max(8, len(names) * 0.4)))
    colors = plt.cm.viridis(np.linspace(0.3, 0.9, len(names)))
    bars = ax.barh(names, totals, color=colors, edgecolor='black', linewidth=0.5)

    # Add value labels on bars
    for i, (bar, total) in enumerate(zip(bars, totals)):
        width = bar.get_width()
        ax.text(width + max(totals) * 0.01, bar.get_y() + bar.get_height()/2,
                f'{int(total)}',
                ha='left', va='center', fontsize=9, weight='bold')

    ax.set_xlabel(f'Total {metric_name.replace("_", " ").title()}', fontsize=12, weight='bold')
    ax.set_title(f'Player Ranking by Total {metric_name.replace("_", " ").title()}',
                 fontsize=14, weight='bold', pad=15)
    ax.grid(axis='x', alpha=0.3)
    ax.set_axisbelow(True)

    # Invert y-axis so #1 is at top
    ax.invert_yaxis()

    plt.tight_layout()
    return safe_save_plot(fig, fname)

def plot_group_timeseries(players: List[str], all_seasons: List[int], all_values: Dict[str, List[Optional[float]]], metric_name: str, fname: str):
    # For large groups (10+ players), use bar chart ranking instead of congested line chart
    if len(players) >= 10:
        dbg("Using bar chart ranking for large group (%d players)", len(players))
        return plot_group_bar_ranking(players, all_values, metric_name, fname)

    fig, ax = plt.subplots(figsize=(10,7))
    yrs = np.array(all_seasons)
    for p in players:
        vals = all_values.get(p, [])
        arr = np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
        ax.plot(yrs, arr, marker='o', linestyle='-', label=p, linewidth=2, markersize=7)
    ax.set_xticks(yrs)
    ax.set_xlabel("Season", fontsize=12, weight='bold')
    ax.set_ylabel(metric_name.replace('_', ' ').title(), fontsize=12, weight='bold')
    ax.set_title(f"Group Comparison: {metric_name.replace('_', ' ').title()} Over Time",
                 fontsize=14, weight='bold')
    ax.legend(loc='best', fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    any_non_nan = False
    for p in players:
        arr = np.array([v for v in all_values.get(p, []) if v is not None])
        if arr.size > 0:
            any_non_nan = True
            break
    if not any_non_nan:
        plt.close(fig)
        return None
    return safe_save_plot(fig, fname)

def plot_group_radar(players: List[str], metric_labels: List[str], players_percentiles: Dict[str, List[float]], fname: str, actual_values: Optional[Dict[str, Dict[str, float]]] = None, players_seasons: Optional[Dict[str, Optional[str]]] = None):
    # Apply dark theme to match comparison charts
    plt.style.use('dark_background')

    N = len(metric_labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    # Create figure with transparent background to blend with page
    fig = plt.figure(figsize=(10,10), facecolor='none')
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor('none')

    colors = ['#FF6B6B', '#4ECDC4', '#FFD93D', '#A78BFA']

    # For single player, use normalized actual values instead of percentiles
    is_single_player = len(players) == 1

    for idx, p in enumerate(players):
        color = colors[idx % len(colors)]

        # Add season label to player name if available
        label_text = p.title()
        if players_seasons and p in players_seasons and players_seasons[p]:
            try:
                year = int(players_seasons[p])
                season_label = f"{str(year)[-2:]}-{str(year+1)[-2:]}"
                label_text = f"{p.title()} ({season_label})"
            except (ValueError, TypeError):
                label_text = f"{p.title()} ({players_seasons[p]})"

        if is_single_player and actual_values and p in actual_values:
            # For single player: normalize actual values to 0-100 scale for visualization
            actual_vals = [actual_values[p].get(m, 0) for m in metric_labels]

            # Normalize each metric independently to 0-100 scale
            # Find max for each metric to normalize
            max_vals = []
            for i, metric in enumerate(metric_labels):
                val = actual_vals[i]
                # Use reasonable max values for common metrics
                if 'goals' in metric.lower() or 'assists' in metric.lower():
                    max_val = max(30, val * 1.5)  # Scale based on player's value
                elif 'xg' in metric.lower() or 'xa' in metric.lower():
                    max_val = max(20, val * 1.5)
                elif 'progressive' in metric.lower():
                    max_val = max(100, val * 1.5)
                else:
                    max_val = max(50, val * 1.5)
                max_vals.append(max_val)

            # Normalize to 0-100
            normalized_vals = [(actual_vals[i] / max_vals[i] * 100) if max_vals[i] > 0 else 0 for i in range(len(actual_vals))]
            data = normalized_vals + normalized_vals[:1]

            ax.plot(angles, data, label=label_text, marker='o', linewidth=3, markersize=10, color=color)
            ax.fill(angles, data, alpha=0.25, color=color)

            # Show actual values as labels
            for i, metric in enumerate(metric_labels):
                actual_val = actual_vals[i]
                if actual_val == 0:
                    continue

                angle_rad = angles[i]
                radial_pos = normalized_vals[i]

                ax.text(angle_rad, radial_pos + 10, f'{actual_val:.0f}',
                       ha='center', va='center', fontsize=11, weight='bold', color='white',
                       bbox=dict(boxstyle='round,pad=0.4', facecolor=color,
                               alpha=0.95, edgecolor='white', linewidth=2))
        else:
            # For multiple players: use percentiles
            vals = players_percentiles.get(p, [])
            if not vals or len(vals) != N:
                continue
            data = vals + vals[:1]

            ax.plot(angles, data, label=label_text, marker='o', linewidth=2.5, markersize=8, color=color)
            ax.fill(angles, data, alpha=0.15, color=color)

            # Add actual value labels if provided - skip zero values to reduce clutter
            if actual_values and p in actual_values:
                for i, metric in enumerate(metric_labels):
                    if metric in actual_values[p]:
                        actual_val = actual_values[p][metric]
                        # Skip labels for zero values to reduce clutter
                        if actual_val == 0:
                            continue

                        percentile = vals[i] if i < len(vals) else 0
                        angle_rad = angles[i]

                        # Offset labels for different players to reduce overlap
                        radial_offset = 8 + (idx * 8)

                        ax.text(angle_rad, percentile + radial_offset, f'{actual_val:.0f}',
                               ha='center', va='center', fontsize=9, weight='bold', color='white',
                               bbox=dict(boxstyle='round,pad=0.35', facecolor=color,
                                       alpha=0.9, edgecolor='white', linewidth=1.5))

    ax.set_thetagrids(np.degrees(angles[:-1]), [m.replace('_', ' ').title() for m in metric_labels],
                     fontsize=11, weight='bold', color='white')

    # Different title for single player vs comparison
    if is_single_player:
        # Get the season for the single player
        player_name = players[0]
        season_text = "Latest Season"
        if players_seasons and player_name in players_seasons and players_seasons[player_name]:
            season_value = players_seasons[player_name]
            # If it's already in "XX-YY" format, use it directly
            if isinstance(season_value, str) and '-' in season_value:
                season_text = f"{season_value}"
            else:
                # Otherwise try to parse as year
                try:
                    year = int(season_value)
                    season_label = f"{str(year)[-2:]}-{str(year+1)[-2:]}"
                    season_text = f"{season_label}"
                except (ValueError, TypeError):
                    season_text = str(season_value)

        ax.set_title(f"Performance Radar - {season_text}\n(Actual Stats)",
                    fontsize=14, weight='bold', pad=20, color='white')
    else:
        ax.set_title("Performance Radar\n(Percentiles vs League - Latest Relevant Season)",
                    fontsize=14, weight='bold', pad=20, color='white')

    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3, color='gray')
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=12, framealpha=0.9)

    # Different y-axis labels for single player vs comparison
    if is_single_player:
        # For single player, hide the percentile ticks since we're showing actual values
        ax.set_yticks([])
    else:
        # For comparisons, show percentile markers
        ax.set_yticks([25, 50, 75, 100])
        ax.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=10, color='white')

    ax.tick_params(colors='white')

    result = safe_save_plot(fig, fname)
    plt.style.use('default')  # Reset to default style
    return result

# ---------------- Football API Integration for Images ----------------
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
FOOTBALL_API_HOST = "api-football-v1.p.rapidapi.com"

def fetch_player_image(player_name: str) -> Optional[Image.Image]:
    """Fetch player image from API-Football"""
    if not FOOTBALL_API_KEY:
        dbg("No FOOTBALL_API_KEY set, skipping player image fetch")
        return None

    try:
        # Search for player
        url = f"https://{FOOTBALL_API_HOST}/v3/players"
        headers = {
            "X-RapidAPI-Key": FOOTBALL_API_KEY,
            "X-RapidAPI-Host": FOOTBALL_API_HOST
        }
        params = {"search": player_name}

        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("response") and len(data["response"]) > 0:
                photo_url = data["response"][0]["player"]["photo"]
                if photo_url:
                    img_response = requests.get(photo_url, timeout=5)
                    if img_response.status_code == 200:
                        return Image.open(BytesIO(img_response.content))
    except Exception as e:
        dbg(f"Error fetching player image for {player_name}: {e}")

    return None

def fetch_team_logo(team_name: str) -> Optional[Image.Image]:
    """Fetch team logo from API-Football"""
    if not FOOTBALL_API_KEY:
        dbg("No FOOTBALL_API_KEY set, skipping team logo fetch")
        return None

    try:
        # Search for team
        url = f"https://{FOOTBALL_API_HOST}/v3/teams"
        headers = {
            "X-RapidAPI-Key": FOOTBALL_API_KEY,
            "X-RapidAPI-Host": FOOTBALL_API_HOST
        }
        params = {"search": team_name}

        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("response") and len(data["response"]) > 0:
                logo_url = data["response"][0]["team"]["logo"]
                if logo_url:
                    img_response = requests.get(logo_url, timeout=5)
                    if img_response.status_code == 200:
                        return Image.open(BytesIO(img_response.content))
    except Exception as e:
        dbg(f"Error fetching team logo for {team_name}: {e}")

    return None

def get_player_team_from_mcp(player_name: str) -> Optional[str]:
    """Get player's current team from MCP"""
    try:
        result = call_mcp("aggregate_player_stat", {
            "player_name": player_name,
            "player": player_name,
            "stat": "squad",
            "seasons_back": 1
        })
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get("squad")
    except Exception as e:
        dbg(f"Error getting team for {player_name}: {e}")
    return None

def plot_vs_comparison(
    players: List[str],
    all_seasons: List[int],
    goals_data: Dict[str, List[Optional[float]]],
    assists_data: Dict[str, List[Optional[float]]],
    fname: str,
    radar_data: Optional[Dict] = None
) -> Optional[str]:
    """
    Create enhanced VS-themed comparison with player/team images
    Combines goals and assists charts side-by-side with logos
    """
    if len(players) != 2:
        dbg("VS comparison requires exactly 2 players")
        return None

    try:
        # Create figure with custom layout - larger for better visibility
        fig = plt.figure(figsize=(20, 14))

        # Define grid for layout - add season info row
        gs = fig.add_gridspec(4, 5, height_ratios=[0.8, 0.5, 4, 4], width_ratios=[1, 4, 1, 4, 1],
                             hspace=0.4, wspace=0.4)

        # Player 1 info (left)
        player1_name = players[0].title()
        player1_team = get_player_team_from_mcp(players[0])

        # Player 2 info (right)
        player2_name = players[1].title()
        player2_team = get_player_team_from_mcp(players[1])

        # Fetch images
        player1_img = fetch_player_image(players[0])
        player2_img = fetch_player_image(players[1])
        team1_logo = fetch_team_logo(player1_team) if player1_team else None
        team2_logo = fetch_team_logo(player2_team) if player2_team else None

        # Title area with VS
        title_ax = fig.add_subplot(gs[0, :])
        title_ax.axis('off')

        # Add player 1 info
        if player1_img:
            img_ax1 = fig.add_subplot(gs[0, 0])
            img_ax1.imshow(player1_img)
            img_ax1.axis('off')

        # VS text in center
        title_ax.text(0.5, 0.5, 'VS', fontsize=48, weight='bold',
                     ha='center', va='center', transform=title_ax.transAxes,
                     bbox=dict(boxstyle='round', facecolor='white', edgecolor='black', linewidth=2))

        # Add player names
        title_ax.text(0.2, 0.3, player1_name, fontsize=22, weight='bold',
                     ha='center', va='top', transform=title_ax.transAxes)
        if player1_team:
            title_ax.text(0.2, 0.05, player1_team, fontsize=16, style='italic',
                         ha='center', va='top', transform=title_ax.transAxes,
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.3))

        title_ax.text(0.8, 0.3, player2_name, fontsize=22, weight='bold',
                     ha='center', va='top', transform=title_ax.transAxes)
        if player2_team:
            title_ax.text(0.8, 0.05, player2_team, fontsize=16, style='italic',
                         ha='center', va='top', transform=title_ax.transAxes,
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='lightcoral', alpha=0.3))

        # Add season range info
        season_ax = fig.add_subplot(gs[1, 1:4])
        season_ax.axis('off')
        if all_seasons:
            season_text = f"Seasons: {min(all_seasons)} - {max(all_seasons)}"
            season_ax.text(0.5, 0.5, season_text, fontsize=14, weight='bold',
                         ha='center', va='center', transform=season_ax.transAxes,
                         bbox=dict(boxstyle='round,pad=0.8', facecolor='yellow', alpha=0.2))

        # Add player 2 info
        if player2_img:
            img_ax2 = fig.add_subplot(gs[0, 4])
            img_ax2.imshow(player2_img)
            img_ax2.axis('off')

        # Team logos
        if team1_logo:
            logo_ax1 = fig.add_subplot(gs[2, 0])
            logo_ax1.imshow(team1_logo)
            logo_ax1.axis('off')

        if team2_logo:
            logo_ax2 = fig.add_subplot(gs[2, 4])
            logo_ax2.imshow(team2_logo)
            logo_ax2.axis('off')

        # Goals chart (top)
        ax_goals = fig.add_subplot(gs[2, 1:4])
        yrs = np.array(all_seasons)

        colors = ['#FF6B6B', '#4ECDC4']  # Nice contrasting colors
        for idx, p in enumerate(players):
            vals = goals_data.get(p, [])
            arr = np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
            ax_goals.plot(yrs, arr, marker='o', linestyle='-', label=p.title(),
                         linewidth=3, markersize=8, color=colors[idx])

            # Add value labels on points
            for x, y in zip(yrs, arr):
                if not np.isnan(y):
                    ax_goals.annotate(f'{int(y)}', (x, y), textcoords="offset points",
                                    xytext=(0,10), ha='center', fontsize=9,
                                    bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[idx], alpha=0.3))

        ax_goals.set_xticks(yrs)
        ax_goals.set_xlabel("Season", fontsize=14, weight='bold')
        ax_goals.set_ylabel("Goals", fontsize=14, weight='bold')
        ax_goals.set_title("⚽ GOALS COMPARISON", fontsize=16, weight='bold', pad=15)
        ax_goals.legend(loc='upper left', fontsize=12, framealpha=0.9)
        ax_goals.grid(True, alpha=0.3, linestyle='--')
        ax_goals.spines['top'].set_visible(False)
        ax_goals.spines['right'].set_visible(False)

        # Assists chart (bottom)
        ax_assists = fig.add_subplot(gs[3, 1:4])

        for idx, p in enumerate(players):
            vals = assists_data.get(p, [])
            arr = np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
            ax_assists.plot(yrs, arr, marker='o', linestyle='-', label=p.title(),
                          linewidth=3, markersize=8, color=colors[idx])

            # Add value labels on points
            for x, y in zip(yrs, arr):
                if not np.isnan(y):
                    ax_assists.annotate(f'{int(y)}', (x, y), textcoords="offset points",
                                      xytext=(0,10), ha='center', fontsize=9,
                                      bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[idx], alpha=0.3))

        ax_assists.set_xticks(yrs)
        ax_assists.set_xlabel("Season", fontsize=14, weight='bold')
        ax_assists.set_ylabel("Assists", fontsize=14, weight='bold')
        ax_assists.set_title("🎯 ASSISTS COMPARISON", fontsize=16, weight='bold', pad=15)
        ax_assists.legend(loc='upper left', fontsize=12, framealpha=0.9)
        ax_assists.grid(True, alpha=0.3, linestyle='--')
        ax_assists.spines['top'].set_visible(False)
        ax_assists.spines['right'].set_visible(False)

        # Team logos at bottom
        if team1_logo:
            logo_ax3 = fig.add_subplot(gs[3, 0])
            logo_ax3.imshow(team1_logo)
            logo_ax3.axis('off')

        if team2_logo:
            logo_ax4 = fig.add_subplot(gs[3, 4])
            logo_ax4.imshow(team2_logo)
            logo_ax4.axis('off')

        return safe_save_plot(fig, fname)

    except Exception as e:
        dbg(f"Error creating VS comparison: {e}")
        traceback.print_exc()
        return None

def plot_comprehensive_comparison(
    players: List[str],
    all_seasons: List[int],
    goals_data: Dict[str, List[Optional[float]]],
    assists_data: Dict[str, List[Optional[float]]],
    metrics_for_radar: List[str],
    radar_percentiles: Dict[str, List[float]],
    radar_actual_values: Dict[str, Dict[str, float]],
    radar_seasons: Dict[str, Optional[str]],
    bar_chart_data: Dict[str, Dict[str, float]],
    fname: str
) -> Optional[str]:
    """
    Creates a comprehensive comparison combining:
    - Goals and Assists time series (top section)
    - Radar chart with actual values (bottom left)
    - Head-to-head bar chart (bottom right)
    All in one large image with dark theme.
    """
    try:
        # Set dark theme
        plt.style.use('dark_background')

        # Create large figure with grid layout - transparent to blend with page
        fig = plt.figure(figsize=(24, 16), facecolor='none')
        gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.2], hspace=0.3, wspace=0.3)

        # Bright colors for dark theme
        chart_colors = ['#FF6B6B', '#4ECDC4', '#FFD93D', '#A78BFA']
        colors_map = {players[0]: chart_colors[0], players[1]: chart_colors[1]} if len(players) == 2 else {}

        # Row 1: Goals comparison
        ax_goals = fig.add_subplot(gs[0, :])
        ax_goals.set_facecolor('none')
        for player in players:
            if player in goals_data:
                color = colors_map.get(player, chart_colors[0])
                ax_goals.plot(all_seasons, goals_data[player], marker='o', linewidth=3,
                            markersize=12, label=player.title(), color=color)
                # Add value labels
                for i, (season, value) in enumerate(zip(all_seasons, goals_data[player])):
                    if value is not None:
                        ax_goals.annotate(f'{int(value)}', (season, value),
                                        textcoords="offset points", xytext=(0,12),
                                        ha='center', fontsize=12, weight='bold', color='white',
                                        bbox=dict(boxstyle='round,pad=0.5', facecolor=color,
                                                alpha=0.9, edgecolor='white', linewidth=1.5))

        ax_goals.set_xlabel('Season', fontweight='bold', fontsize=16, color='white')
        ax_goals.set_ylabel('Goals', fontweight='bold', fontsize=16, color='white')
        ax_goals.set_title('⚽ GOALS COMPARISON', fontweight='bold', fontsize=18, pad=20, color='white')
        ax_goals.legend(fontsize=14, loc='best', framealpha=0.9)
        ax_goals.grid(True, alpha=0.2, color='gray')
        ax_goals.tick_params(colors='white', labelsize=12)

        # Row 2: Assists comparison
        ax_assists = fig.add_subplot(gs[1, :])
        ax_assists.set_facecolor('none')
        for player in players:
            if player in assists_data:
                color = colors_map.get(player, chart_colors[1])
                ax_assists.plot(all_seasons, assists_data[player], marker='o', linewidth=3,
                              markersize=12, label=player.title(), color=color)
                # Add value labels
                for i, (season, value) in enumerate(zip(all_seasons, assists_data[player])):
                    if value is not None:
                        ax_assists.annotate(f'{int(value)}', (season, value),
                                          textcoords="offset points", xytext=(0,12),
                                          ha='center', fontsize=12, weight='bold', color='white',
                                          bbox=dict(boxstyle='round,pad=0.5', facecolor=color,
                                                  alpha=0.9, edgecolor='white', linewidth=1.5))

        ax_assists.set_xlabel('Season', fontweight='bold', fontsize=16, color='white')
        ax_assists.set_ylabel('Assists', fontweight='bold', fontsize=16, color='white')
        ax_assists.set_title('🎯 ASSISTS COMPARISON', fontweight='bold', fontsize=18, pad=20, color='white')
        ax_assists.legend(fontsize=14, loc='best', framealpha=0.9)
        ax_assists.grid(True, alpha=0.2, color='gray')
        ax_assists.tick_params(colors='white', labelsize=12)

        # Row 3 Left: Radar chart with actual values
        ax_radar = fig.add_subplot(gs[2, 0], polar=True)
        ax_radar.set_facecolor('none')
        N = len(metrics_for_radar)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]

        for idx, player in enumerate(players):
            vals = radar_percentiles.get(player, [])
            if not vals or len(vals) != N:
                continue
            data = vals + vals[:1]
            color = chart_colors[idx % len(chart_colors)]

            # Add season label to player name
            player_season = radar_seasons.get(player)
            if player_season:
                # Convert "2024" to "24-25" format for display
                try:
                    year = int(player_season)
                    season_label = f"{str(year)[-2:]}-{str(year+1)[-2:]}"
                    label_text = f"{player.title()} ({season_label})"
                except (ValueError, TypeError):
                    label_text = f"{player.title()} ({player_season})"
            else:
                label_text = player.title()

            ax_radar.plot(angles, data, label=label_text, marker='o',
                         linewidth=3.5, markersize=10, color=color)
            ax_radar.fill(angles, data, alpha=0.25, color=color)

            # Add actual value labels with better visibility
            # Only show labels for non-zero values and use better spacing to reduce overlap
            if player in radar_actual_values:
                for i, metric in enumerate(metrics_for_radar):
                    if metric in radar_actual_values[player]:
                        actual_val = radar_actual_values[player][metric]
                        # Skip labels for zero values to reduce clutter
                        if actual_val == 0:
                            continue

                        percentile = vals[i] if i < len(vals) else 0
                        angle_rad = angles[i]

                        # Increased offset for different players to reduce overlap
                        radial_offset = 15 + (idx * 15)

                        ax_radar.text(angle_rad, percentile + radial_offset, f'{actual_val:.0f}',
                                    ha='center', va='center', fontsize=10, weight='bold', color='white',
                                    bbox=dict(boxstyle='round,pad=0.35', facecolor=color,
                                            alpha=0.9, edgecolor='white', linewidth=1.5))

        ax_radar.set_thetagrids(np.degrees(angles[:-1]),
                               [m.replace('_', ' ').title() for m in metrics_for_radar],
                               fontsize=13, weight='bold', color='white')
        ax_radar.set_title("📊 Performance Radar\n(Percentiles + Actual Values - Latest Relevant Season)",
                          fontsize=15, weight='bold', pad=25, color='white')
        # Increase ylim to accommodate label offsets
        ax_radar.set_ylim(0, 140)
        ax_radar.grid(True, alpha=0.3, color='gray')
        ax_radar.legend(loc='upper right', bbox_to_anchor=(1.35, 1.15), fontsize=12, framealpha=0.9)
        ax_radar.set_yticks([25, 50, 75, 100])
        ax_radar.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=11, color='white')
        ax_radar.tick_params(colors='white')

        # Row 3 Right: Bar chart
        ax_bar = fig.add_subplot(gs[2, 1])
        ax_bar.set_facecolor('none')
        metrics_for_bar = list(bar_chart_data[players[0]].keys()) if players and bar_chart_data.get(players[0]) else []
        x = np.arange(len(metrics_for_bar))
        width = 0.35 if len(players) == 2 else 0.25

        for i, player in enumerate(players[:4]):
            values = [bar_chart_data[player].get(m, 0) for m in metrics_for_bar]
            offset = (i - len(players)/2 + 0.5) * width
            color = chart_colors[i % len(chart_colors)]
            bars = ax_bar.bar(x + offset, values, width, label=player.title(), color=color, alpha=0.9)

            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax_bar.text(bar.get_x() + bar.get_width()/2., height,
                              f'{height:.1f}',
                              ha='center', va='bottom', fontsize=11, weight='bold', color='white')

        ax_bar.set_xlabel('Metrics', fontweight='bold', fontsize=14, color='white')
        ax_bar.set_ylabel('Value', fontweight='bold', fontsize=14, color='white')
        ax_bar.set_title('📊 Head-to-Head Stats\n(Latest Season)', fontweight='bold', fontsize=16, color='white')
        ax_bar.set_xticks(x)
        ax_bar.set_xticklabels([m.replace('_', ' ').title() for m in metrics_for_bar],
                               rotation=20, ha='right', fontsize=12, color='white')
        ax_bar.legend(fontsize=13, framealpha=0.9)
        ax_bar.grid(axis='y', alpha=0.2, color='gray')
        ax_bar.tick_params(colors='white', labelsize=12)

        # Add main title
        season_range = f"{min(all_seasons)} - {max(all_seasons)}" if all_seasons else "Multiple Seasons"
        fig.suptitle(f"{players[0].title()} vs {players[1].title()}\nSeasons: {season_range}",
                    fontsize=22, weight='bold', y=0.98, color='white')

        result = safe_save_plot(fig, fname)
        plt.style.use('default')  # Reset to default style
        return result

    except Exception as e:
        dbg(f"Error creating comprehensive comparison: {e}")
        traceback.print_exc()
        return None

# ---------------- LLM answer helpers ----------------
def llm_fallback_answer(question: str, rag_ctx: str, rag_hits: List[Dict[str,Any]]):
    try:
        schema_cols = get_available_columns() or []
        schema_line = "DATA SCHEMA (some relevant columns): " + ", ".join(sorted(schema_cols[:50])) if schema_cols else ""
        
        # Check if this is a biographical/general question (not numeric stats)
        is_biographical = any(keyword in question.lower() for keyword in ["who is", "who's", "tell me about", "what do you know about", "describe"])
        
        if is_biographical:
            prompt = f"""
You are a knowledgeable football analyst. The user is asking a general question about a player. Use the RAG snippets below to provide a concise, informative answer.

RAG SNIPPETS:
{rag_ctx}

USER QUESTION:
{question}

Provide a brief, conversational answer (2-4 sentences) about the player based on the information available. Focus on their position, team, nationality, and notable characteristics.

IMPORTANT: Use plain text only. Do NOT use markdown formatting like ** for bold or __ for italics. Write in clear, natural language with proper punctuation and structure.
"""
        else:
            prompt = f"""
You are a knowledgeable football analyst. Use the RAG snippets below. If exact numeric values are not present in the snippets, attempt an informed answer labeled clearly as ESTIMATE or BEST_EFFORT. If you use a proxy column (e.g. 'progressive_passes' for 'passes'), say so.

{schema_line}

RAG SNIPPETS:
{rag_ctx}

USER QUESTION:
{question}

Answer briefly and factually. If specific numeric data is not available in the snippets, provide a general knowledge answer based on what you know about football, clearly indicating when you're providing general information vs. specific data from the snippets.

IMPORTANT: Use plain text only. Do NOT use markdown formatting like ** for bold or __ for italics. Write in clear, natural language with proper punctuation and structure.
"""
        ans = llm.predict(prompt, max_tokens=400, temperature=OPENAI_TEMPERATURE)
        return ans
    except Exception as e:
        dbg("llm_fallback_answer exception: %s", e)
        return "Sorry — I couldn't fetch the data from the dataset, and a fallback LLM attempt failed."

def answer_with_context(question, rag_ctx, rag_hits):
    cache_key = {"type":"rag_answer", "query": question, "rag_ids":[h.get("idx") for h in (rag_hits or []) if isinstance(h.get("idx"), (int, str))]}
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    prompt = f"""
You are a helpful football assistant. Use the RAG snippets below when available. If the snippets don't contain the specific data requested, provide a general knowledge answer about football, clearly distinguishing between data-backed facts and general knowledge.

For multi-part questions, answer each part separately and clearly.

RAG SNIPPETS:
{rag_ctx}

USER QUESTION:
{question}

Answer:
"""
    ans = llm.predict(prompt, max_tokens=512, temperature=OPENAI_TEMPERATURE)
    cache_set(cache_key, ans)
    return ans

def synthesize_tool_output(tool_name: str, tool_output: Any, user_query: str, max_tokens: int = 220) -> str:
    try:
        safe_out = json.dumps(tool_output, default=str)
    except Exception:
        safe_out = str(tool_output)
    prompt = (
        f"You are a concise football assistant. The user asked: {user_query}\n\n"
        f"Tool: {tool_name}\n\n"
        f"Result (JSON):\n{safe_out}\n\n"
        "Write a short, plain-English summary (2-5 sentences). If numeric data is missing, say which field is missing."
    )
    try:
        text = llm.predict(prompt, max_tokens=max_tokens, temperature=0.0)
        return text.strip()
    except Exception as e:
        dbg("synthesize_tool_output LLM error: %s", e)
        if isinstance(tool_output, dict) and tool_output.get("found") is False:
            return f"Tool reported: {tool_output.get('message', 'not found')}"
        return "Here's the raw tool output: " + (str(tool_output)[:800])

def humanize_aggregate_for_year(resp: dict, year: int) -> Optional[str]:
    if not isinstance(resp, dict) or not resp.get("found"):
        return None
    player = resp.get("player", "<player>")
    per = resp.get("per_season") or []
    for item in per:
        if "season_year" in item and int(item.get("season_year")) == int(year):
            val = item.get("value")
            if val is None:
                return f"{player} -- no data for {year} (value missing)."
            return f"{player} had {val} ({resp.get('stat','metric') if resp.get('stat') else ''}) in {year}."
    for item in per:
        if "season_label" in item and str(item.get("season_label")).strip().startswith(str(year)):
            val = item.get("value")
            if val is None:
                return f"{player} -- no data for {year} (season label present but value missing)."
            return f"{player} had {val} in {item.get('season_label')}."
    return None

# ---------------- Chart chooser ----------------
def choose_chart_type(players: List[str], metrics: List[str], data_summary: Dict[str, Any]) -> str:
    if not metrics or not players:
        return "fallback_text"
    if len(metrics) == 1:
        return "group_timeseries" if len(players) > 1 else "timeseries"
    if len(metrics) == 2:
        return "group_bar" if len(players) > 1 else "timeseries_multimetric"
    if len(metrics) >= 3:
        return "radar"
    return "fallback_text"

# ---------------- Interactive slot manager ----------------
def interactive_slot_manager(user_text: str, intent_struct: Dict[str,Any]) -> Dict[str,Any]:
    dbg("ENTER interactive_slot_manager user_text=%s", (user_text or "")[:200])

    # If the parse set ambiguous players, present disambiguation options
    if intent_struct.get("ambiguous_players"):
        auto_selected = present_disambiguation_options(intent_struct["ambiguous_players"], user_text, intent_struct)
        if auto_selected:
            # Auto-selected single option - update intent and continue
            intent_struct["players"] = intent_struct.get("players", []) + [auto_selected]
            intent_struct.pop("ambiguous_players", None)
        else:
            # Need user input - return and wait
            return intent_struct
        return intent_struct

    players = intent_struct.get("players") or []

    # CRITICAL: Resolve pronouns in player list FIRST (but only for follow-up questions)
    if players:
        players = resolve_pronouns_in_player_list(players, user_text)
        intent_struct["players"] = players
        dbg("After pronoun resolution: players=%s", players)

    metrics = intent_struct.get("metrics")
    intent = intent_struct.get("intent")

    # Detect if this is a conversational phrase that should NOT trigger player resolution
    # These are general conversational phrases that the LLM should handle directly
    text_lower = user_text.lower().strip()

    conversational_phrases = [
        'anything', 'something', 'tell me more', 'what about', 'how about',
        'more recent', 'something else', 'anything else', 'another',
        'interesting', 'cool', 'nice', 'thanks', 'thank you',
        'ok', 'okay', 'yes', 'no', 'sure', 'great', 'awesome'
    ]
    # Use word boundaries to avoid false matches (e.g., 'no' in 'Cristiano')
    is_conversational = any(re.search(r'\b' + re.escape(phrase) + r'\b', text_lower) for phrase in conversational_phrases)

    # Detect if this is a new question (not a player-specific follow-up)
    question_starters = ['who', 'what', 'when', 'where', 'why', 'how', 'which', 'whose',
                        'tell me', 'show me', 'compare', 'rank', 'list', 'get', 'find']
    starts_with_question = any(text_lower.startswith(starter) for starter in question_starters)

    has_question_mark = '?' in user_text

    new_topic_indicators = ['rank', 'top', 'best', 'worst', 'mvp', 'award', 'champion',
                           'winner', 'world cup', 'paid', 'salary', 'transfer', 'fact']
    has_new_topic = any(indicator in text_lower for indicator in new_topic_indicators)

    is_new_question = starts_with_question or has_question_mark or has_new_topic or is_conversational

    # If this is a conversational phrase, skip all player resolution - let LLM handle it
    if is_conversational and not players:
        dbg("Detected conversational phrase - skipping player resolution, using LLM")
        return intent_struct

    # Resolve pronoun ONLY for follow-up questions (not new questions)
    if not players and not is_new_question:
        pron = resolve_pronouns_or_last_player(user_text)
        if pron:
            players = [pron]
            intent_struct["players"] = players
            dbg("Slot manager resolved pronoun to %s", pron)
            return intent_struct

    # If we have players, try to resolve them to canonical names via RAG
    # BUT skip if this looks like a conversational phrase misinterpreted as player names
    if players and is_conversational:
        # LLM incorrectly extracted "player names" from conversational text - clear them
        dbg("Clearing incorrectly extracted players from conversational text: %s", players)
        intent_struct["players"] = []
        return intent_struct

    if players:
        resolved_players = []
        needs_disambiguation = []
        
        for player_name in players:
            # Skip resolving if it looks like a year or number
            if re.fullmatch(r"\d{4}\??", player_name.strip()):
                dbg("Slot manager skipping year-like token: %s", player_name)
                continue
                
            canonical, ambiguous = resolve_player_name_with_rag(player_name, require_confirmation=True)
            
            if canonical:
                # Successfully resolved to single canonical name
                resolved_players.append(canonical)
                dbg("Slot manager resolved '%s' to canonical '%s'", player_name, canonical)
            elif ambiguous:
                # Multiple matches - need user input
                dbg("Slot manager found ambiguous matches for '%s'", player_name)
                needs_disambiguation.append({"query": player_name, "options": ambiguous})
            else:
                # No good matches - keep original and let later logic handle it
                resolved_players.append(player_name)
                dbg("Slot manager keeping original name '%s' (no RAG match)", player_name)
        
        # If any player needs disambiguation, handle the first one
        if needs_disambiguation:
            first_ambig = needs_disambiguation[0]
            remaining_disambig = needs_disambiguation[1:]  # Store the rest for later

            # Try to auto-select if there's only 1 option
            auto_selected = present_disambiguation_options(first_ambig["options"], user_text, intent_struct)

            if auto_selected:
                # Auto-selected - add to resolved and check if more disambiguations needed
                resolved_players.append(auto_selected)

                if remaining_disambig:
                    # More players need disambiguation - recurse
                    needs_disambiguation = remaining_disambig
                    first_ambig = needs_disambiguation[0]
                    remaining_disambig = needs_disambiguation[1:]

                    auto_selected_next = present_disambiguation_options(first_ambig["options"], user_text, intent_struct)
                    if auto_selected_next:
                        resolved_players.append(auto_selected_next)
                        # Continue until we need user input or finish all
                    else:
                        # Need user input for this one
                        intent_struct["resolved_players"] = resolved_players
                        intent_struct["remaining_disambiguations"] = remaining_disambig
                        intent_struct["ambiguous_query"] = first_ambig["query"]
                        intent_struct["ambiguous_players"] = first_ambig["options"]
                        return intent_struct

                # All resolved - update and continue
                if resolved_players:
                    intent_struct["players"] = resolved_players
                    push_context(resolved_players, intent, hits=None)
                return intent_struct
            else:
                # Need user input
                intent_struct["resolved_players"] = resolved_players
                intent_struct["remaining_disambiguations"] = remaining_disambig
                intent_struct["ambiguous_query"] = first_ambig["query"]
                intent_struct["ambiguous_players"] = first_ambig["options"]
                dbg("Slot manager: %d resolved, 1 asking now, %d remaining to disambiguate",
                    len(resolved_players), len(remaining_disambig))
                return intent_struct
        
        # Update with resolved canonical names
        if resolved_players:
            intent_struct["players"] = resolved_players
            push_context(resolved_players, intent, hits=None)
            return intent_struct

    # If still no players and it's not just a greeting/natural chit-chat, try safe RAG
    # BUT: Only for new questions where we expect a player (not follow-ups)
    if not players and intent not in ("natural",) and is_new_question:
        # Don't search for player names if query is very short or looks like a follow-up
        if len(user_text.strip()) > 4 and not re.fullmatch(r"\d{4}\??", user_text.strip()):
            canonical, ambiguous = resolve_player_name_with_rag(user_text, require_confirmation=True)

            if canonical:
                players = [canonical]
                intent_struct["players"] = players
                dbg("Slot manager auto-filled player from RAG: %s", canonical)
                push_context(players, intent, hits=None)
                return intent_struct
            elif ambiguous:
                dbg("Slot manager found ambiguous players, presenting options")
                auto_selected = present_disambiguation_options(ambiguous, user_text, intent_struct)
                if auto_selected:
                    # Auto-selected - update players and continue
                    players = [auto_selected]
                    intent_struct["players"] = players
                    push_context(players, intent, hits=None)
                    return intent_struct
                else:
                    # Need user input
                    intent_struct["ambiguous_players"] = ambiguous
                    return intent_struct

    # If player present, push context
    if players:
        push_context(players, intent, hits=None)
    
    return intent_struct

# ---------------- Validation & plotting ----------------
def validate_and_plot_players_timeseries(players: List[str], metric: str, seasons_back: int, text: str) -> Optional[str]:
    dbg("validate_and_plot_players_timeseries players=%s metric=%s seasons_back=%d", players, metric, seasons_back)
    all_seasons_set = set()
    per_player_series = {}
    any_data = False
    for p in players:
        resp = aggregate_mcp(p, stat=metric, seasons_back=seasons_back)
        if not isinstance(resp, dict):
            dbg("aggregate_mcp returned non-dict for %s: %s", p, resp)
            per_player_series[p] = ([], [])
            continue
        seasons, vals = extract_timeseries_from_aggregate(resp)
        per_player_series[p] = (seasons, vals)
        all_seasons_set.update(seasons)
        if any(v is not None for v in vals):
            any_data = True

    if not any_data:
        dbg("No data found for any player for metric=%s", metric)
        return None

    all_seasons = sorted(list(all_seasons_set))
    aligned = {}
    for p in players:
        seasons, vals = per_player_series.get(p, ([],[]))
        dict_map = {s:v for s,v in zip(seasons, vals)}
        aligned_vals = [dict_map.get(s, None) for s in all_seasons]
        aligned[p] = aligned_vals

    if len(players) == 1:
        p = players[0]
        path = plot_time_series_single(p, all_seasons, aligned[p], metric, fname=f"{p.replace(' ','_')}_ts.png")
        return path
    else:
        path = plot_group_timeseries(players, all_seasons, aligned, metric, fname=f"group_plot_{int(time.time())}.png")
        return path

def calculate_radar_data(players: List[str], metrics: List[str], seasons_back: int = 1):
    """
    Helper function to calculate radar chart data (percentiles and actual values).
    For each player, finds their last RELEVANT season (with non-zero stats).
    Returns: (players_percentiles, players_actual_values, players_seasons)
    """
    latest_vals = {p: [] for p in players}
    players_percentiles = {p: [] for p in players}
    players_seasons = {p: None for p in players}  # Track which season each player's data is from

    # First, determine the last relevant season for each player
    for p in players:
        # Look back through seasons to find last one with meaningful stats
        for lookback in range(1, 6):  # Check up to 5 seasons back
            resp = aggregate_mcp(p, stat="goals", seasons_back=lookback)
            if isinstance(resp, dict) and resp.get("found"):
                per = resp.get("per_season") or []
                if per:
                    # Find the most recent season with any non-zero stat
                    for season_data in reversed(per):
                        val = season_data.get("value")
                        if val is not None and val > 0:
                            players_seasons[p] = season_data.get("season")
                            dbg("Player %s: using season %s (last active season)", p, players_seasons[p])
                            break
                    if players_seasons[p]:
                        break

        # If still no season found, default to latest
        if not players_seasons[p]:
            resp = aggregate_mcp(p, stat="goals", seasons_back=1)
            if isinstance(resp, dict) and resp.get("found"):
                per = resp.get("per_season") or []
                if per:
                    players_seasons[p] = per[-1].get("season")
                    dbg("Player %s: using latest season %s (default)", p, players_seasons[p])

    for metric in metrics:
        cohort = None
        try:
            flt = filter_players_mcp(team=None, position=None, seasons_back=seasons_back)
            if isinstance(flt, dict) and flt.get("players"):
                cohort = flt.get("players")[:200]
            elif isinstance(flt, list) and flt:
                cohort = flt[:200]
        except Exception as e:
            dbg("cohort fetch failed: %s", e)
            cohort = None

        cohort_vals = []
        if cohort:
            for other in cohort:
                resp = aggregate_mcp(other, stat=metric, seasons_back=1)
                if isinstance(resp, dict) and resp.get("found"):
                    per = resp.get("per_season") or []
                    if per:
                        latest = per[-1].get("value")
                        if latest is not None:
                            try:
                                cohort_vals.append(float(latest))
                            except Exception:
                                pass

        for p in players:
            # Get data from the player's relevant season
            resp = aggregate_mcp(p, stat=metric, seasons_back=5)  # Get multiple seasons
            val = None
            if isinstance(resp, dict) and resp.get("found"):
                per = resp.get("per_season") or []
                # Find the value for the player's relevant season
                target_season = players_seasons.get(p)
                if target_season:
                    for season_data in per:
                        if season_data.get("season") == target_season:
                            val = season_data.get("value")
                            break
                # Fallback to latest if season not found
                if val is None and per:
                    val = per[-1].get("value")

            if val is None:
                latest_vals[p].append(None)
            else:
                try:
                    latest_vals[p].append(float(val))
                except Exception:
                    latest_vals[p].append(None)

        if cohort_vals and len(cohort_vals) >= MIN_COHORT_FOR_PERCENTILES:
            for p in players:
                v = latest_vals[p][-1]
                if v is None:
                    players_percentiles[p].append(0.0)
                else:
                    players_percentiles[p].append(compute_percentile_in_cohort(v, cohort_vals))
        else:
            present = [v for vlist in latest_vals.values() for v in [vlist[-1]] if v is not None]
            if present:
                mn = min(present)
                mx = max(present)
                rng = mx - mn if mx != mn else 1.0
                for p in players:
                    v = latest_vals[p][-1]
                    if v is None:
                        players_percentiles[p].append(0.0)
                    else:
                        players_percentiles[p].append(((v - mn) / rng) * 100.0)
            else:
                for p in players:
                    players_percentiles[p].append(0.0)

    # Convert latest_vals to actual_values format
    players_actual_values = {}
    for p in players:
        actual_dict = {}
        for i, metric in enumerate(metrics):
            if i < len(latest_vals[p]) and latest_vals[p][i] is not None:
                actual_dict[metric] = latest_vals[p][i]
        players_actual_values[p] = actual_dict

    return players_percentiles, players_actual_values, players_seasons

def validate_and_plot_radar(players: List[str], metrics: List[str], seasons_back: int, text: str) -> Optional[str]:
    dbg("validate_and_plot_radar players=%s metrics=%s seasons_back=%d", players, metrics, seasons_back)

    if len(metrics) < 3:
        dbg("Radar needs >=3 metrics; got %d", len(metrics))
        return None

    players_percentiles, players_actual_values, players_seasons = calculate_radar_data(players, metrics, seasons_back)

    # Validate percentiles
    for p in players:
        if len(players_percentiles[p]) != len(metrics):
            players_percentiles[p] = [0.0] * len(metrics)

    fname = f"group_radar_{int(time.time())}.png"
    try:
        return plot_group_radar(players, metrics, players_percentiles, fname, actual_values=players_actual_values, players_seasons=players_seasons)
    except Exception as e:
        dbg("plot_group_radar exception: %s", e)
        return None

# ---------------- Main handler ----------------
HELP = """
Agent usage examples:
- Natural question: "How many progressive passes did Erling Haaland have in the last 3 seasons?"
- Tool-style: "Erling Haaland|goals|3"
- Plot: "plot Salah" -> agent chooses defaults based on position
- Type 'exit' or Ctrl-C to quit.
"""

def safe_print_json(obj):
    try:
        print(json.dumps(obj, indent=2))
    except Exception:
        print(str(obj))

# minimal b64 saver
import base64
def save_b64_image(image_b64, fname="latest_plot.png"):
    if not image_b64:
        raise ValueError("save_b64_image: no image data provided")
    if isinstance(image_b64, dict):
        for k in ("image_b64", "data", "b64", "image"):
            if k in image_b64:
                image_b64 = image_b64[k]
                break
    if image_b64.startswith("data:"):
        try:
            payload = image_b64.split(",",1)[1]
        except Exception:
            payload = image_b64
    else:
        payload = image_b64
    b = base64.b64decode(payload)
    with open(fname, "wb") as f:
        f.write(b)
    return fname

# ---------------- Main input handler ----------------
def handle_input(text: str):
    dbg("ENTER handle_input text_preview=%s", (text[:200].replace('\n','\\n') if text else "<empty>"))
    text = (text or "").strip()
    if not text:
        return
    if text.lower() in ("exit", "quit"):
        print("Goodbye.")
        sys.exit(0)

    # Flag to track if we resolved disambiguation (skip re-parsing if true)
    resolved_disambiguation = False

    # --- handle pending disambiguation from previous turn ---
    pd = CONTEXT.get('pending_disambig')
    if pd:
        dbg("previous context detected, continuing validation")
        chosen = resolve_pending_disambiguation(text)
        if chosen == "CANCELLED":
            # User wants to start a new query - clear disambiguation and proceed normally
            dbg("User cancelled disambiguation, proceeding with new query")
            CONTEXT.pop('pending_disambig', None)
        elif chosen:
            # User made a valid selection - clear disambiguation and update the original intent
            CONTEXT.pop('pending_disambig', None)
            dbg("User selected disambiguation choice: %s", chosen)
            print(f"Selected: {chosen}. Proceeding with your original request...")

            # Update the original intent struct with the chosen player
            orig_intent = pd.get("original_intent_struct", {})
            orig_text = pd.get("original_text", "")

            # Combine resolved players with the chosen disambiguation
            resolved_players = orig_intent.get("resolved_players", [])
            current_resolved = resolved_players + [chosen]

            # Check if there are more players that need disambiguation
            remaining_disambig = orig_intent.get("remaining_disambiguations", [])

            if remaining_disambig:
                # More players need disambiguation - ask for the next one
                next_ambig = remaining_disambig[0]
                still_remaining = remaining_disambig[1:]

                dbg("Disambiguation resolved '%s', but %d more players need disambiguation",
                    chosen, len(remaining_disambig))

                # Update the intent with current progress
                orig_intent["resolved_players"] = current_resolved
                orig_intent["remaining_disambiguations"] = still_remaining
                orig_intent["ambiguous_query"] = next_ambig["query"]

                # Present next disambiguation
                auto_selected_next = present_disambiguation_options(next_ambig["options"], orig_text, orig_intent)

                if auto_selected_next:
                    # Auto-selected - add to current_resolved and check for more
                    current_resolved.append(auto_selected_next)

                    if still_remaining:
                        # More players need disambiguation - continue loop
                        remaining_disambig = still_remaining
                        next_ambig = remaining_disambig[0]
                        still_remaining = remaining_disambig[1:]
                        orig_intent["resolved_players"] = current_resolved
                        orig_intent["remaining_disambiguations"] = still_remaining
                        # Recursively present next (this is not ideal but maintains current structure)
                        # TODO: refactor to avoid recursion
                        auto_selected_next2 = present_disambiguation_options(next_ambig["options"], orig_text, orig_intent)
                        if not auto_selected_next2:
                            # Need user input for this one
                            orig_intent["ambiguous_query"] = next_ambig["query"]
                            orig_intent["ambiguous_players"] = next_ambig["options"]
                            CONTEXT['pending_disambig'] = {
                                "options": next_ambig["options"],
                                "original_text": orig_text,
                                "original_intent_struct": orig_intent
                            }
                            return
                        else:
                            current_resolved.append(auto_selected_next2)

                    # All resolved - proceed with comparison
                    all_players = current_resolved
                    orig_intent["players"] = all_players
                    orig_intent.pop("ambiguous_players", None)
                    orig_intent.pop("ambiguous_query", None)
                    orig_intent.pop("resolved_players", None)
                    orig_intent.pop("remaining_disambiguations", None)

                    text = orig_text
                    intent_struct = orig_intent
                    intent = intent_struct.get("intent", classify_intent(text))
                    players = all_players
                    team = normalize_team_name(intent_struct.get("team"))
                    position = intent_struct.get("position")
                    raw_metrics = intent_struct.get("metrics")
                    seasons_back = intent_struct.get("seasons_back") or None

                    push_context(all_players, intent, hits=None)
                    resolved_disambiguation = True
                    # Continue to processing logic below
                else:
                    # Need user input
                    orig_intent["ambiguous_players"] = next_ambig["options"]

                    # Store updated pending_disambig and return
                    CONTEXT['pending_disambig'] = {
                        "options": next_ambig["options"],
                        "original_text": orig_text,
                        "original_intent_struct": orig_intent
                    }
                    return

            # No more disambiguations needed - proceed with comparison
            all_players = current_resolved
            orig_intent["players"] = all_players

            dbg("All disambiguations resolved: %s", all_players)

            # Remove disambiguation flags
            orig_intent.pop("ambiguous_players", None)
            orig_intent.pop("ambiguous_query", None)
            orig_intent.pop("resolved_players", None)
            orig_intent.pop("remaining_disambiguations", None)

            # Continue processing with the updated intent (DON'T recursively call handle_input)
            text = orig_text  # Use original query text
            intent_struct = orig_intent
            intent = intent_struct.get("intent", classify_intent(text))
            players = all_players  # Use all resolved players
            team = normalize_team_name(intent_struct.get("team"))
            position = intent_struct.get("position")
            raw_metrics = intent_struct.get("metrics")
            seasons_back = intent_struct.get("seasons_back") or None

            # Update context with all resolved players
            push_context(all_players, intent, hits=None)

            # Set flag to skip re-parsing below
            resolved_disambiguation = True

            # Skip to the processing logic below (don't return early)
            # This allows the code to continue with the resolved player
        else:
            print("I didn't understand your selection. Please reply with the option number, exact name, or type 'cancel' to ask something else.")
            for i, opt in enumerate(pd.get("options", []), start=1):
                name = opt.get("player") or opt.get("title") or opt.get("candidate")
                print(f"{i}. {name}")
            return

    # quick raw commands
    if text.lower().startswith("search:"):
        q = text.split(":",1)[1].strip()
        hits = rag_search_mcp(q, k=6)
        safe_print_json(hits)
        return

    if text.lower().startswith("aggregate_player_stat:") or text.lower().startswith("aggregate:"):
        payload = text.split(":",1)[1].strip()
        parts = [p.strip() for p in payload.split("|")]
        player = parts[0]
        stat = parts[1] if len(parts) > 1 else "goals"
        seasons_back = int(parts[2]) if len(parts) > 2 else DEFAULT_SEASONS_BACK
        available_cols = get_available_columns()
        stat = normalize_metric_token(stat, available_cols) or stat
        res = aggregate_mcp(player, stat=stat, seasons_back=seasons_back)
        summary = synthesize_tool_output("aggregate_player_stat", res, text)
        print(summary)
        return

    # pipe shorthand handling
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        player = parts[0]
        second = parts[1] if len(parts) > 1 else ""
        third = parts[2] if len(parts) > 2 else None
        if "," in second:
            metrics_list = [m.strip() for m in second.split(",") if m.strip()]
            available_cols = get_available_columns()
            metrics = [normalize_metric_token(m, available_cols) for m in metrics_list]
            res = plot_mcp(player, metrics)
            if isinstance(res, dict) and res.get("image_b64"):
                fname = save_b64_image(res["image_b64"], fname=f"{player}_plot.png")
                print("Plot saved to", fname)
            else:
                print(synthesize_tool_output("plot_player", res, text))
            return
        else:
            seasons_back = int(third) if third else DEFAULT_SEASONS_BACK
            available_cols = get_available_columns()
            stat = normalize_metric_token(second or "goals", available_cols) or (second or "goals")
            res = aggregate_mcp(player, stat=stat, seasons_back=seasons_back)
            print(synthesize_tool_output("aggregate_player_stat", res, text))
            return

    # Natural language path: parse intent (skip if we already resolved disambiguation)
    if not resolved_disambiguation:
        intent_struct = parse_intent_with_llm(text)
        intent = intent_struct.get("intent", classify_intent(text))

        # Override LLM intent with rule-based classification for high-priority patterns
        rule_based_intent = classify_intent(text)
        if rule_based_intent == "ranking":
            intent = "ranking"
            dbg("Overriding LLM intent with rule-based 'ranking' detection")

        players = intent_struct.get("players") or []
        team = normalize_team_name(intent_struct.get("team"))
        position = intent_struct.get("position")
        raw_metrics = intent_struct.get("metrics")
        seasons_back = intent_struct.get("seasons_back") or None

    # Check if user is responding to a metric clarification request OR asking a follow-up question
    if not players and CONTEXT.get("last_players"):
        text_lower = text.lower()

        # Check for metric clarification
        if CONTEXT.get("last_intent") in ("plot", "compare", "aggregate"):
            if re.search(r"\b(default|defaults|all|all of them|use default)\b", text_lower):
                players = CONTEXT["last_players"]
                available_cols = get_available_columns()
                rag_hits = CONTEXT.get("last_hits") or []
                raw_metrics = choose_default_metrics_for_players(players, rag_hits, available_cols)
                intent = CONTEXT["last_intent"]
                # CRITICAL: Update intent_struct so slot manager doesn't try to re-resolve
                intent_struct["players"] = players
                intent_struct["metrics"] = raw_metrics
                intent_struct["intent"] = intent
                dbg("User chose defaults - using players=%s metrics=%s", players, raw_metrics)

        # Check for follow-up questions that reference previous context
        follow_up_patterns = [
            r"\b(these|those|this|that)\s+(player|comparison|info|data|stat)",
            r"\b(based on|given|considering)\s+(this|that|these|those)",
            r"\b(who is|which is|who's|which one is)\s+(better|best|stronger|faster|more)",
            r"\b(between (them|these|those))\b",
            r"\b(their|they're|them)\b.*\b(career|future|potential|performance)",
        ]

        is_follow_up = any(re.search(pattern, text_lower) for pattern in follow_up_patterns)

        if is_follow_up:
            dbg("Detected follow-up question referencing previous context")
            players = CONTEXT["last_players"]
            intent_struct["players"] = players
            # Keep the parsed intent (likely "natural" or "search")
            dbg("Using context players for follow-up: %s", players)

    # If it's a plain greeting or chit-chat -> respond with LLM small-talk
    no_slots = not (players or raw_metrics or team or position or seasons_back)
    if intent == "natural" and no_slots:
        small = llm.predict(f"You are a friendly football assistant. Reply briefly to this user message: {text}", max_tokens=120, temperature=0.7)
        print(small)
        return

    # attempt intelligent slot-filling (skip if we already resolved disambiguation)
    if not resolved_disambiguation:
        intent_struct = interactive_slot_manager(text, intent_struct)
        players = intent_struct.get("players") or []
        raw_metrics = intent_struct.get("metrics")

        # CRITICAL: If disambiguation is pending, STOP and wait for user response
        if intent_struct.get("ambiguous_players"):
            dbg("Disambiguation pending - waiting for user response")
            return

    # prefer explicit year detection with clarification
    explicit_year = None
    explicit_season_label = None
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        year_mentioned = int(m.group(1))
        dbg("Detected year %d in text", year_mentioned)

        # User says "2020" - could mean season 2019-20 or 2020-21
        # Convention: "2020" usually refers to the season that ENDS in 2020 (2019-20)
        # But we should check which interpretation makes more sense

        # Check if user specified "season" keyword with slash/dash format
        season_match = re.search(r"\b(20\d{2})[-/](20)?\d{2}\b", text)
        if season_match:
            # User explicitly said "2020-21" or "2020/21"
            explicit_season_label = season_match.group(0)
            # Get the ending year
            parts = re.findall(r"20\d{2}", explicit_season_label)
            if len(parts) == 2:
                explicit_year = int(parts[1])  # Use ending year
            else:
                # Format like "2020-21", extract both parts
                start_year = int(parts[0])
                end_part = explicit_season_label.split(re.search(r'[-/]', explicit_season_label).group())[1]
                if len(end_part) == 2:
                    explicit_year = 2000 + int(end_part)
                else:
                    explicit_year = int(end_part)
            dbg("Parsed explicit season label '%s' -> year=%d", explicit_season_label, explicit_year)
        else:
            # Ambiguous: just "2020" mentioned
            # Ask for clarification if not obvious from context
            if re.search(r"\b(in|for|during|from)\s+(20\d{2})\b", text):
                # Phrasing suggests they mean the season ending in that year
                explicit_year = year_mentioned
                dbg("Interpreted year %d as season ending year (based on phrasing)", explicit_year)
            else:
                # Default interpretation: year mentioned = season ending year
                # E.g., "2020" -> 2019-20 season
                explicit_year = year_mentioned
                dbg("Using year %d as season ending year (default interpretation)", explicit_year)

        seasons_for_query = max(DEFAULT_SEASONS_BACK, 10)
    else:
        seasons_for_query = seasons_back or DEFAULT_SEASONS_BACK

    available_cols = get_available_columns()

    # normalize metrics tokens
    metrics = None
    if raw_metrics:
        if isinstance(raw_metrics, str):
            raw_list = [m.strip() for m in raw_metrics.split(",") if m.strip()]
        else:
            raw_list = [m for m in raw_metrics if isinstance(m, str)]
        metrics = [normalize_metric_token(m, available_cols) for m in raw_list]

    dbg("Resolved intent=%s players=%s metrics=%s", intent, players, metrics)

    # IMPROVED: If user mentioned player(s) but no metric -> check intent first
    if players and not metrics:
        # If it's a COMPARISON request with 2+ players, generate COMPREHENSIVE comparison with visualizations
        if intent == "compare" and len(players) >= 2:
            dbg("User requesting comprehensive comparison of %d players: %s", len(players), players)

            # Key metrics to compare
            key_metrics = ["goals", "assists", "xg", "npxg", "progressive_carries", "progressive_passes"]
            available_cols = get_available_columns()
            metrics_to_compare = [normalize_metric_token(m, available_cols) for m in key_metrics if normalize_metric_token(m, available_cols)]

            charts_created = []

            # 1. For 2-player comparisons, create comprehensive combined chart
            if len(players) == 2:
                try:
                    # OPTIMIZED: Use bulk aggregation instead of 1,200+ individual MCP calls
                    # Get ALL metrics for ALL players in ONE call
                    bulk_result = aggregate_group_multi_metrics_mcp(
                        players=players,
                        metrics=metrics_to_compare[:6],
                        seasons_back=seasons_for_query,
                        include_cohort=True,
                        cohort_size=200
                    )

                    if not bulk_result or not bulk_result.get("ok"):
                        dbg("Bulk aggregation failed, falling back to individual calls")
                        # Fallback to old method if bulk fails
                        radar_percentiles, radar_actual_values, radar_seasons = calculate_radar_data(players, metrics_to_compare[:6], seasons_back=1)
                        goals_data = {}
                        assists_data = {}
                        all_seasons = []
                        bar_chart_data = {}

                        for player in players:
                            goals_resp = aggregate_mcp(player, stat="goals", seasons_back=seasons_for_query)
                            if goals_resp and goals_resp.get("found"):
                                per_season = goals_resp.get("per_season", [])
                                seasons = [x.get("season_year") or x.get("season_label") for x in per_season]
                                values = [x.get("value") for x in per_season]
                                goals_data[player] = values
                                if seasons and len(seasons) > len(all_seasons):
                                    all_seasons = seasons

                            assists_resp = aggregate_mcp(player, stat="assists", seasons_back=seasons_for_query)
                            if assists_resp and assists_resp.get("found"):
                                per_season = assists_resp.get("per_season", [])
                                values = [x.get("value") for x in per_season]
                                assists_data[player] = values

                            stats_dict = {}
                            for metric in metrics_to_compare[:4]:
                                resp = aggregate_mcp(player, stat=metric, seasons_back=1)
                                if isinstance(resp, dict) and resp.get("found"):
                                    per = resp.get("per_season") or []
                                    if per:
                                        val = per[-1].get("value")
                                        if val is not None:
                                            stats_dict[metric] = float(val)
                            bar_chart_data[player] = stats_dict
                    else:
                        # Extract data from bulk result
                        dbg("Successfully got bulk data for %d players", len(players))
                        player_data = bulk_result.get("players", {})
                        all_seasons = bulk_result.get("seasons", [])
                        cohort = bulk_result.get("cohort", {})

                        # Build time series data for goals and assists
                        goals_data = {}
                        assists_data = {}
                        for player_name, data in player_data.items():
                            if data.get("found"):
                                per_season = data.get("per_season", {})

                                # Extract goals per season
                                goals_values = []
                                assists_values = []
                                for season in all_seasons:
                                    # JSON converts int keys to strings, so look up as string
                                    season_stats = per_season.get(str(season), {})
                                    goals_values.append(season_stats.get("goals", 0))
                                    assists_values.append(season_stats.get("assists", 0))

                                dbg("Player %s: goals_values=%s", player_name, goals_values)
                                goals_data[player_name] = goals_values
                                assists_data[player_name] = assists_values

                        dbg("Final goals_data keys: %s", list(goals_data.keys()))

                        # FILTER OUT SEASONS WHERE BOTH PLAYERS HAVE NO DATA
                        seasons_with_data = []
                        for idx, season in enumerate(all_seasons):
                            has_data = False
                            for player_name in goals_data.keys():
                                goals_val = goals_data.get(player_name, [])[idx] if idx < len(goals_data.get(player_name, [])) else 0
                                assists_val = assists_data.get(player_name, [])[idx] if idx < len(assists_data.get(player_name, [])) else 0
                                if (goals_val is not None and goals_val > 0) or (assists_val is not None and assists_val > 0):
                                    has_data = True
                                    break
                            if has_data:
                                seasons_with_data.append(idx)

                        # Filter seasons and data
                        if seasons_with_data:
                            filtered_seasons = [all_seasons[i] for i in seasons_with_data]
                            filtered_goals_data = {
                                player: [goals_data[player][i] if i < len(goals_data[player]) else None for i in seasons_with_data]
                                for player in goals_data.keys()
                            }
                            filtered_assists_data = {
                                player: [assists_data[player][i] if i < len(assists_data[player]) else None for i in seasons_with_data]
                                for player in assists_data.keys()
                            }
                            all_seasons = filtered_seasons
                            goals_data = filtered_goals_data
                            assists_data = filtered_assists_data
                            dbg("Filtered to %d seasons with data", len(all_seasons))

                        # Build radar chart data using cohort percentiles
                        # IMPORTANT: Use each player's latest season WITH DATA, not global latest
                        radar_percentiles = {}
                        radar_actual_values = {}
                        radar_seasons = {}

                        for player_name, data in player_data.items():
                            if data.get("found"):
                                per_season = data.get("per_season", {})

                                # Find player's latest season with actual data (non-zero values)
                                latest_stats = {}
                                player_season = None
                                for season in reversed(all_seasons):  # Start from most recent
                                    season_stats = per_season.get(str(season), {})
                                    # Check if this season has any non-zero stats
                                    has_data = any(v > 0 for v in season_stats.values() if isinstance(v, (int, float)))
                                    if has_data:
                                        latest_stats = season_stats
                                        player_season = str(season)
                                        dbg("Player %s: using season %s for radar/bar (latest with data)", player_name, season)
                                        break

                                # Fallback to global latest if no season found
                                if not latest_stats:
                                    latest_stats = data.get("latest", {})
                                    if all_seasons:
                                        player_season = str(all_seasons[-1])
                                    dbg("Player %s: falling back to global latest", player_name)

                                radar_actual_values[player_name] = latest_stats
                                radar_seasons[player_name] = player_season

                                # Calculate percentiles using cohort data
                                percentiles = []
                                for metric in metrics_to_compare[:6]:
                                    player_value = latest_stats.get(metric, 0)

                                    if metric in cohort:
                                        cohort_values = cohort[metric].get("values", [])
                                        if cohort_values:
                                            # Calculate percentile
                                            below = sum(1 for v in cohort_values if v < player_value)
                                            percentile = (below / len(cohort_values)) * 100.0
                                            percentiles.append(percentile)
                                        else:
                                            percentiles.append(50.0)
                                    else:
                                        percentiles.append(50.0)

                                radar_percentiles[player_name] = percentiles

                        # Build bar chart data from each player's latest season WITH DATA
                        bar_chart_data = {}
                        for player_name, data in player_data.items():
                            if data.get("found"):
                                per_season = data.get("per_season", {})

                                # Find player's latest season with actual data
                                latest_stats = {}
                                for season in reversed(all_seasons):  # Start from most recent
                                    season_stats = per_season.get(str(season), {})
                                    has_data = any(v > 0 for v in season_stats.values() if isinstance(v, (int, float)))
                                    if has_data:
                                        latest_stats = season_stats
                                        break

                                if not latest_stats:
                                    latest_stats = data.get("latest", {})

                                # Only include first 4 metrics for bar chart
                                bar_chart_data[player_name] = {
                                    m: latest_stats.get(m, 0)
                                    for m in metrics_to_compare[:4]
                                    if m in latest_stats
                                }

                    # Create comprehensive comparison chart
                    if all_seasons and goals_data and assists_data:
                        comp_fname = f"comprehensive_comparison_{int(time.time())}.png"
                        # Use canonical player names for plotting
                        canonical_players = players
                        comp_path = plot_comprehensive_comparison(
                            canonical_players, all_seasons, goals_data, assists_data,
                            metrics_to_compare[:6], radar_percentiles, radar_actual_values,
                            radar_seasons, bar_chart_data, comp_fname
                        )
                        if comp_path:
                            charts_created.append(("comprehensive", comp_path))
                            # Chart generated successfully - sent via WebSocket
                        else:
                            raise Exception("Comprehensive comparison returned None")
                except Exception as e:
                    dbg(f"Error creating comprehensive comparison, falling back to standard charts: {e}")
                    traceback.print_exc()
                    # Fallback to standard charts
                    for metric in ["goals", "assists"]:
                        norm_metric = normalize_metric_token(metric, available_cols)
                        if norm_metric:
                            path = validate_and_plot_players_timeseries(players, norm_metric, seasons_for_query, text)
                            if path:
                                charts_created.append((metric, path))
                                # Chart generated successfully - sent via WebSocket
            else:
                # For 3+ players, use standard time series charts
                for metric in ["goals", "assists"][:2]:
                    norm_metric = normalize_metric_token(metric, available_cols)
                    if norm_metric:
                        path = validate_and_plot_players_timeseries(players, norm_metric, seasons_for_query, text)
                        if path:
                            charts_created.append((metric, path))
                            # Chart generated successfully - sent via WebSocket

                # Generate radar chart (percentiles)
                if len(metrics_to_compare) >= 3:
                    radar_path = validate_and_plot_radar(players, metrics_to_compare[:6], seasons_for_query, text)
                    if radar_path:
                        charts_created.append(("radar", radar_path))
                        # Chart generated successfully - sent via WebSocket

                # Generate head-to-head bar chart for latest season
                try:
                    fig, ax = plt.subplots(figsize=(12, 6))
                    player_stats = {}

                    for player in players:
                        stats_dict = {}
                        for metric in metrics_to_compare[:4]:
                            resp = aggregate_mcp(player, stat=metric, seasons_back=1)
                            if isinstance(resp, dict) and resp.get("found"):
                                per = resp.get("per_season") or []
                                if per:
                                    val = per[-1].get("value")
                                    if val is not None:
                                        stats_dict[metric] = float(val)
                        player_stats[player] = stats_dict

                    # Create grouped bar chart
                    x = np.arange(len(metrics_to_compare[:4]))
                    width = 0.35 if len(players) == 2 else 0.25
                    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

                    for i, player in enumerate(players[:4]):
                        values = [player_stats[player].get(m, 0) for m in metrics_to_compare[:4]]
                        offset = (i - len(players)/2 + 0.5) * width
                        ax.bar(x + offset, values, width, label=player, color=colors[i % len(colors)])

                    ax.set_xlabel('Metrics', fontweight='bold', fontsize=12)
                    ax.set_ylabel('Value', fontweight='bold', fontsize=12)
                    ax.set_title('📊 Head-to-Head Stats Comparison (Latest Season)', fontweight='bold', fontsize=14)
                    ax.set_xticks(x)
                    ax.set_xticklabels([m.replace('_', ' ').title() for m in metrics_to_compare[:4]], rotation=15, ha='right')
                    ax.legend()
                    ax.grid(axis='y', alpha=0.3)

                    bar_path = f"comparison_bars_{int(time.time())}.png"
                    safe_save_plot(fig, bar_path)
                    charts_created.append(("head_to_head", bar_path))
                    # Chart generated successfully - sent via WebSocket
                except Exception as e:
                    dbg("Error creating head-to-head chart: %s", e)

            # 4. Generate text comparison with RAG
            comparison_data = []
            for player in players:
                rag_ctx, hits = build_context_from_rag(player, k=3)
                comparison_data.append({
                    "player": player,
                    "context": rag_ctx,
                    "hits": hits
                })

            comparison_prompt = f"""You are a football analyst. Compare ALL {len(players)} players in detail:

"""
            for i, data in enumerate(comparison_data, 1):
                comparison_prompt += f"\nPlayer {i}: {data['player']}\n{data['context']}\n"

            comparison_prompt += f"""

Write a comprehensive comparison covering ALL {len(players)} players with these sections:

OVERVIEW
Write 3-4 sentences comparing their positions and overall playing styles. Mention ALL {len(players)} players by name and their key characteristics.

GOAL SCORING VS PLAYMAKING
Write a detailed paragraph (4-5 sentences) comparing their goal-scoring records and creative contributions. Include specific numbers for ALL {len(players)} players. For example: "In the 2022-23 season, [Player 1] scored X goals and provided Y assists, while [Player 2] netted Z goals with W assists..." Continue for all players.

KEY STATISTICAL DIFFERENCES
Write a paragraph (4-5 sentences) highlighting important statistical comparisons across ALL {len(players)} players. Use metrics like goals per 90, xG, progressive passes, etc. Make direct comparisons with numbers.

PLAYING STYLES & STRENGTHS
Write a detailed paragraph (5-6 sentences) describing each player's distinct playing style and strengths. Cover ALL {len(players)} players, explaining what makes each unique.

CAREER PROGRESSION
Write 2-3 sentences summarizing notable achievements and career highlights for ALL {len(players)} players.

IMPORTANT RULES:
- You MUST discuss ALL {len(players)} players throughout the analysis
- Write in flowing paragraphs, not bullet points
- Use section headers in ALL CAPS
- Include specific statistics and numbers
- Keep it readable and well-structured
- No markdown formatting, asterisks, or special characters
- Make it comprehensive but scannable"""

            # Increase token limit for multi-player comparisons
            max_tokens = 1500 if len(players) == 2 else 2000

            try:
                ans = llm.predict(comparison_prompt, max_tokens=max_tokens, temperature=0.0)
                print("\n" + ans)
            except Exception as e:
                dbg("Comparison LLM error: %s", e)
                print("Based on the data, here's what stands out about each player:")
                for data in comparison_data:
                    ans = llm_fallback_answer(f"Summarize {data['player']}'s key stats", data['context'], data['hits'])
                    print(f"\n{data['player']}: {ans}")

            print()
            push_context(players, intent, hits=None)
            return

        # If it's a search/natural question about the player, answer with RAG
        if intent in ("search", "natural"):
            dbg("User asking about player without metrics - using RAG to answer")
            # CRITICAL: Use the resolved player name, not the original query text
            # This prevents re-searching typos like "petri" after we've resolved it to "pedri"

            # For multi-player follow-up questions, gather context for all players
            if players and len(players) > 1:
                # Build combined RAG context for all players
                all_rag_ctx = []
                all_hits = []
                for player in players:
                    rag_ctx_single, hits_single = build_context_from_rag(player, k=3)
                    all_rag_ctx.append(f"### {player}\n{rag_ctx_single}")
                    all_hits.extend(hits_single)

                combined_rag_ctx = "\n\n".join(all_rag_ctx)

                # Create enhanced prompt with comparison context
                enhanced_prompt = f"""You are a knowledgeable football analyst. The user previously compared these players: {', '.join(players)}.

Now they're asking a follow-up question:
{text}

Use the context below to provide a thoughtful answer:

{combined_rag_ctx}

Answer their question directly and comprehensively (3-5 sentences), considering the comparison between these players.

IMPORTANT: Use plain text only. Do NOT use markdown formatting like ** for bold or __ for italics. Write in clear, natural language with proper punctuation and structure."""

                ans = llm.predict(enhanced_prompt, max_tokens=500, temperature=0.0)
                push_context(players, intent, hits=all_hits)
                print("\n", ans)
                print()
                return
            else:
                # Single player or general question
                search_query = players[0] if players and len(players) == 1 else text
                rag_ctx, hits = build_context_from_rag(search_query, k=6)

                # Store hits in context for later use
                push_context(players, intent, hits=hits)

                # Use LLM fallback which is smarter about answering general questions
                ans = llm_fallback_answer(text, rag_ctx, hits)

                # Print the answer directly - no DATA_MISSING checking for biographical queries
                print("\n", ans)
                print()

                # Generate radar chart for single player queries
                if players and len(players) == 1:
                    try:
                        # Get key metrics for the player
                        key_metrics = ["goals", "assists", "xg", "npxg", "progressive_carries", "progressive_passes"]
                        available_cols = get_available_columns()
                        metrics_to_chart = [normalize_metric_token(m, available_cols) for m in key_metrics if normalize_metric_token(m, available_cols)]

                        if len(metrics_to_chart) >= 3:
                            dbg("Generating radar chart for single player: %s", players[0])
                            radar_path = validate_and_plot_radar(players, metrics_to_chart[:6], seasons_for_query, text)
                            # Chart is generated silently - no need to print the path
                    except Exception as e:
                        dbg("Error generating radar chart for single player: %s", e)

                return

        # If it's explicitly a plot/aggregate request, ask for metrics with context-aware defaults
        if intent in ("plot", "compare", "aggregate"):
            available_cols = get_available_columns()
            rag_hits = CONTEXT.get("last_hits") or []
            metrics_default = choose_default_metrics_for_players(players, rag_hits, available_cols)
            pretty = [m for m in metrics_default]
            
            print(f"\n📊 I can work with these metrics for {players[0]}: {', '.join(pretty)}")
            print(f"Which metric would you like? (or say 'use defaults' / 'all of them')")
            print()
            push_context(players, intent, hits=None)
            return

    # Handle "compare" intent with team/position but no specific players
    # This is for queries like "compare all forwards from Barcelona"
    if intent == "compare" and not players and (team or position):
        dbg("Handling group comparison: team=%s position=%s", team, position)

        # Normalize position to canonical form
        position_canonical = None
        if position:
            position_map = {
                "striker": "FW", "strikers": "FW", "forward": "FW", "forwards": "FW",
                "st": "FW", "cf": "FW", "fw": "FW",
                "midfielder": "MF", "midfielders": "MF", "mid": "MF", "mf": "MF",
                "defender": "DF", "defenders": "DF", "defence": "DF", "defense": "DF", "df": "DF",
                "goalkeeper": "GK", "goalkeepers": "GK", "keeper": "GK", "keepers": "GK", "gk": "GK"
            }
            position_canonical = position_map.get(position.lower(), position.upper())

        # Get the list of players from filter_players
        result = filter_players_mcp(team=team, position=position_canonical, seasons_back=seasons_for_query)

        if isinstance(result, dict) and result.get("players"):
            players = result["players"]
            dbg("Got %d players from filter_players for group comparison", len(players))

            if len(players) == 0:
                print(f"No {position or 'players'} found for {team or 'all teams'} in the past {seasons_for_query} seasons.")
                return
            elif len(players) > 30:
                print(f"Found {len(players)} {position or 'players'} from {team or 'all teams'}. That's too many to compare at once.")
                print(f"Please specify 2-30 players or use a more specific filter.")
                return

            # Continue with comparison flow
            dbg("Proceeding with comparison of %d players", len(players))
        else:
            print(f"Sorry, I couldn't retrieve {position or 'players'} from {team or 'all teams'}.")
            return

    # Handle "ranking" intent - top N players by metric
    if intent == "ranking":
        dbg("Handling ranking intent: metrics=%s team=%s position=%s", raw_metrics, team, position)

        # Extract top N from query
        top_n_match = re.search(r"\b(top|best)\s+(\d+)\b", text.lower())
        top_n = int(top_n_match.group(2)) if top_n_match else 10

        # Check if a specific year/season is requested
        specific_year = None
        year_match = re.search(r"\b(in|for|during)\s+(20\d{2})\b", text.lower())
        if year_match:
            specific_year = int(year_match.group(2))
            dbg("Detected specific year request: %d", specific_year)

        # Get metric - default to goals if not specified
        # Extract metric keyword from phrases like "goal scorers", "assist leaders", etc.
        metric_keywords = {
            "goal": "goals",
            "goals": "goals",
            "assist": "assists",
            "assists": "assists",
            "shot": "shots",
            "shots": "shots",
            "xg": "xg",
            "npxg": "npxg"
        }

        metric = "goals"  # default
        if raw_metrics:
            for rm in raw_metrics:
                # Split and check each word
                words = rm.lower().split()
                for word in words:
                    if word in metric_keywords:
                        metric = metric_keywords[word]
                        break
                if metric != "goals":  # found a match
                    break

        available_cols = get_available_columns()
        metric = normalize_metric_token(metric, available_cols) or metric
        dbg("Ranking query using metric='%s' (normalized from raw_metrics=%s)", metric, raw_metrics)

        # Normalize position if specified
        position_canonical = None
        if position:
            position_map = {
                "striker": "FW", "strikers": "FW", "forward": "FW", "forwards": "FW",
                "st": "FW", "cf": "FW", "fw": "FW",
                "midfielder": "MF", "midfielders": "MF", "mid": "MF", "mf": "MF",
                "defender": "DF", "defenders": "DF", "defence": "DF", "defense": "DF", "df": "DF",
                "goalkeeper": "GK", "goalkeepers": "GK", "keeper": "GK", "keepers": "GK", "gk": "GK"
            }
            position_canonical = position_map.get(position.lower(), position.upper())

        # Adjust seasons_back if specific year requested
        filter_seasons_back = seasons_for_query
        if specific_year:
            # Calculate how many seasons back the specific year is
            # Current year is 2025 (from env), specific_year might be 2023 (2 years back)
            # We want to capture players who played in that year
            import datetime
            current_year = datetime.datetime.now().year
            years_back = current_year - specific_year
            filter_seasons_back = max(1, years_back + 1)  # +1 to ensure we capture the year
            dbg("Specific year %d detected, adjusting filter seasons_back from %d to %d",
                specific_year, seasons_for_query, filter_seasons_back)

        # Use fast bulk ranking function instead of slow filter+aggregate loop
        result = rank_players_mcp(
            stat=metric,
            top_n=top_n,
            team=team,
            position=position_canonical,
            season_year=specific_year,
            seasons_back=filter_seasons_back
        )

        if isinstance(result, dict) and result.get("ok") and result.get("rankings"):
            rankings = result["rankings"]
            dbg("Got %d rankings from bulk ranking function", len(rankings))

            # Convert to (player, score) tuples for compatibility with existing code
            top_players = [(r["player"], r["value"]) for r in rankings if r.get("value")]

            if not top_players:
                print(f"No players found with {metric} data.")
                return

            # Format output
            print(f"\n🏆 Top {min(top_n, len(top_players))} {position or 'Players'} by {metric.replace('_', ' ').title()}")
            if team:
                print(f"   Team: {team}")
            if position:
                print(f"   Position: {position}")
            if specific_year:
                print(f"   Season: {specific_year}\n")
            else:
                print(f"   Seasons: Last {filter_seasons_back}\n")

            for rank, (player, score) in enumerate(top_players, 1):
                print(f"{rank}. {player.title()}: {int(score)} {metric.replace('_', ' ')}")

            print()
            push_context([], intent, hits=None)
            return
        else:
            print(f"Sorry, couldn't retrieve players for ranking.")
            return

    # Handle "list" intent - filter players by team/position
    if intent == "list" and (team or position):
        dbg("Handling list intent: team=%s position=%s limit=%s sort_by=%s seasons_back=%s", team, position, intent_struct.get("limit"), intent_struct.get("sort_by"), seasons_for_query)

        # Check if user is EXPLICITLY asking for current year or very recent information
        from datetime import datetime
        current_year = datetime.now().year
        current_month = datetime.now().month

        # Only trigger LLM fallback if user explicitly mentions current year or very specific time indicators
        # More strict detection - only for phrases that clearly mean "right now"
        text_lower = text.lower()
        explicit_current_indicators = [
            f"{current_year}",  # Explicit year mention
            "right now",
            "at the moment",
            "as of today",
            "most recent",
            "up to date"
        ]
        is_explicitly_asking_current = any(indicator in text_lower for indicator in explicit_current_indicators)

        # Also check for "current" or "now" or "today" combined with year context
        has_current_keyword = any(word in text_lower for word in ["current", "now", "today"])
        mentions_recent_year = str(current_year) in text or str(current_year - 1) in text

        is_asking_very_recent = is_explicitly_asking_current or (has_current_keyword and mentions_recent_year)

        # Our database has seasons: 20-21, 21-22, 22-23, 23-24, 24-25
        # Latest season is 24-25 which covers mid-2024 to mid-2025
        latest_season_end_year = 2025  # 24-25 season ends around mid-2025

        if is_asking_very_recent and current_year >= latest_season_end_year and current_month > 6:
            # User is explicitly asking for current info but we only have data up to 24-25 season
            print(f"\n📊 Note: My database contains seasons 2020-21 through 2024-25.")
            print(f"For up-to-date {current_year} information, I'll check current sources...\n")

            # Use LLM fallback to get current info from internet
            ans = llm_fallback_answer(text, "", [])
            print(ans)
            print()
            return

        # Normalize position to canonical form (fw/mf/df/gk)
        position_canonical = None
        if position:
            position_map = {
                "striker": "FW", "strikers": "FW", "forward": "FW", "forwards": "FW",
                "st": "FW", "cf": "FW", "fw": "FW",
                "midfielder": "MF", "midfielders": "MF", "mid": "MF", "mf": "MF",
                "defender": "DF", "defenders": "DF", "defence": "DF", "defense": "DF", "df": "DF",
                "goalkeeper": "GK", "goalkeepers": "GK", "keeper": "GK", "keepers": "GK", "gk": "GK"
            }
            position_canonical = position_map.get(position.lower(), position.upper())

        # Call filter_players MCP tool
        result = filter_players_mcp(team=team, position=position_canonical, seasons_back=seasons_for_query)

        if isinstance(result, dict) and result.get("players"):
            player_list = result["players"]
            dbg("filter_players returned %d players", len(player_list))

            # If limit and sort_by are specified, rank players by stats
            limit = intent_struct.get("limit")
            sort_by = intent_struct.get("sort_by")

            if limit and sort_by and len(player_list) > 0:
                dbg("Ranking players by %s and taking top %d", sort_by, limit)

                # Get aggregate stats for each player
                player_stats = []
                for player_name in player_list[:100]:  # Limit to 100 to avoid too many API calls
                    stat = aggregate_mcp(player_name, stat=sort_by, seasons_back=seasons_for_query)
                    if isinstance(stat, dict) and stat.get("found"):
                        total_value = 0
                        for year_data in stat.get("data", []):
                            val = year_data.get("value")
                            if val is not None:
                                # For latest season, use that value. Otherwise sum across seasons.
                                if seasons_for_query == 1:
                                    total_value = val
                                    break
                                else:
                                    total_value += val

                        player_stats.append({
                            "name": player_name,
                            "value": total_value,
                            "stat": stat
                        })

                # Sort by value (descending)
                player_stats.sort(key=lambda x: x["value"], reverse=True)

                # Take top N
                top_players = player_stats[:limit]

                if len(top_players) == 0:
                    print(f"No data available for {position or 'players'} from {team or 'all teams'}.")
                else:
                    # Format the response
                    position_name = "forwards" if position_canonical == "FW" else "defenders" if position_canonical == "DF" else "midfielders" if position_canonical == "MF" else "goalkeepers" if position_canonical == "GK" else "players"
                    header = f"{team}'s " if team else ""
                    if limit == 3 and position_canonical == "FW":
                        header += "front three"
                    elif limit == 4 and position_canonical == "DF":
                        header += "back four"
                    else:
                        header += f"top {limit} {position_name}"

                    # Determine season label for output
                    if seasons_for_query == 1:
                        season_label = "2024-25 season"
                    else:
                        season_label = f"past {seasons_for_query} seasons (2020-25)"

                    print(f"\n{header} ({season_label}, by {sort_by}):\n")
                    for i, player in enumerate(top_players, 1):
                        print(f"{i}. {player['name'].title()} - {player['value']:.1f} {sort_by.replace('_', ' ')}")

                push_context([p["name"] for p in top_players], intent, hits=None)
                print()
                return

            # Original behavior when no limit/sort_by
            # Format the response
            if len(player_list) == 0:
                print(f"No {position or 'players'} found for {team or 'all teams'} in the database (seasons 2020-25).")
            else:
                # Determine season label
                if seasons_for_query == 1:
                    season_label = "2024-25 season"
                else:
                    season_label = f"past {seasons_for_query} seasons (2020-25)"

                header = f"{'Strikers' if position and 'striker' in position.lower() else position or 'Players'} from {team or 'all teams'} ({season_label}):"
                print(f"\n{header}")
                print(f"Found {len(player_list)} player(s):\n")
                for i, player in enumerate(player_list[:50], 1):  # Limit to first 50
                    print(f"{i}. {player}")
                if len(player_list) > 50:
                    print(f"\n... and {len(player_list) - 50} more")

            push_context([], intent, hits=None)
            return
        else:
            dbg("filter_players_mcp failed or returned no data: %s", result)
            print(f"Sorry, I couldn't retrieve {position or 'players'} from {team or 'all teams'}. The data might not be available.")
            return

    # If metrics specified and players present -> try direct MCP aggregate/time-series flow
    if metrics and players:
        # handle single-player numeric aggregate/time-series
        if intent in ("search", "aggregate") and len(players) == 1:
            preferred_metric = metrics[0]
            res = aggregate_mcp(players[0], stat=preferred_metric, seasons_back=seasons_for_query)
            if isinstance(res, dict) and res.get("found"):
                if explicit_year:
                    hy = humanize_aggregate_for_year(res, explicit_year)
                    if hy:
                        print(hy)
                        push_context(players, intent, hits=None)
                        return
                print(synthesize_tool_output("aggregate_player_stat", res, text))
                push_context(players, intent, hits=None)
                return
            else:
                dbg("aggregate_mcp did not return found for %s: %s", players[0], res)

        # If plotting requested
        if intent in ("plot", "compare") or (intent == "search" and len(metrics) >= 1):
            chart_type = choose_chart_type(players, metrics, {})
            dbg("Adaptive chart choice=%s", chart_type)

            if chart_type in ("timeseries", "group_timeseries"):
                metric_to_plot = metrics[0]
                path = validate_and_plot_players_timeseries(players, metric_to_plot, seasons_for_query, text)
                if path:
                    print("Plot saved to", path)
                    push_context(players, intent, hits=None)
                    return
                else:
                    rag_ctx, hits = build_context_from_rag(text, k=6)
                    ans = answer_with_context(text, rag_ctx, hits)
                    print("\nLLM answer:\n", ans)
                    return

            if chart_type == "group_bar":
                metric1, metric2 = metrics[0], metrics[1]
                latest_map = {}
                for p in players:
                    v1 = None
                    v2 = None
                    r1 = aggregate_mcp(p, stat=metric1, seasons_back=1)
                    r2 = aggregate_mcp(p, stat=metric2, seasons_back=1)
                    if isinstance(r1, dict) and r1.get("found"):
                        per = r1.get("per_season") or []
                        if per:
                            v1 = per[-1].get("value")
                    if isinstance(r2, dict) and r2.get("found"):
                        per = r2.get("per_season") or []
                        if per:
                            v2 = per[-1].get("value")
                    latest_map[p] = (v1, v2)
                fig, ax = plt.subplots(figsize=(8,6))
                inds = np.arange(len(players))
                w = 0.35
                vals1 = [latest_map[p][0] if latest_map[p][0] is not None else 0.0 for p in players]
                vals2 = [latest_map[p][1] if latest_map[p][1] is not None else 0.0 for p in players]
                ax.bar(inds - w/2, vals1, width=w, label=metric1)
                ax.bar(inds + w/2, vals2, width=w, label=metric2)
                ax.set_xticks(inds)
                ax.set_xticklabels(players, rotation=45, ha='right')
                ax.set_title(f"Latest-season comparison: {metric1} vs {metric2}")
                ax.legend()
                pname = f"group_bar_{int(time.time())}.png"
                safe_save_plot(fig, pname)
                print("Plot saved to", pname)
                push_context(players, intent, hits=None)
                return

            if chart_type == "radar":
                path = validate_and_plot_radar(players, metrics, seasons_for_query, text)
                if path:
                    print("Plot saved to", path)
                    push_context(players, intent, hits=None)
                    return
                else:
                    rag_ctx, hits = build_context_from_rag(text, k=6)
                    fb = llm_fallback_answer(text, rag_ctx, hits)
                    print("\nLLM fallback:\n", fb)
                    return

    # If no players but metrics present -> attempt to use last player from context
    if metrics and not players:
        if CONTEXT["last_players"]:
            players = [CONTEXT["last_players"][0]]
            dbg("Using last context player %s for metrics=%s", players, metrics)
            chart_type = choose_chart_type(players, metrics, {})
            if chart_type in ("timeseries", "group_timeseries"):
                path = validate_and_plot_players_timeseries(players, metrics[0], seasons_for_query, text)
                if path:
                    print("Plot saved to", path)
                    push_context(players, intent, hits=None)
                    return
            if chart_type == "radar":
                path = validate_and_plot_radar(players, metrics, seasons_for_query, text)
                if path:
                    print("Plot saved to", path)
                    push_context(players, intent, hits=None)
                    return
        else:
            print("I don't know which player you mean. Which player should I use?")
            return

    # If still nothing, use RAG + LLM to provide a helpful answer
    # The LLM will use RAG data when available, and general knowledge otherwise
    rag_ctx, hits = build_context_from_rag(text, k=6)
    ans = answer_with_context(text, rag_ctx, hits)
    print("\n", ans)
    print()
    return

    print("\nLLM answer:\n")
    print(ans)
    print()

# ---------------- REPL ----------------
if __name__ == "__main__":
    print("Improved Lightweight Football Data Agent.")
    print(HELP)
    try:
        while True:
            try:
                q = input("Question> ").strip()
            except EOFError:
                break
            if not q:
                continue
            try:
                handle_input(q)
            except Exception as e:
                print("Error handling input:", str(e))
                traceback.print_exc()
                dbg("Exception in handle_input: %s", e)
    except KeyboardInterrupt:
        print("\nGoodbye.")
