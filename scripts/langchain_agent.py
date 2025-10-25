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
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import difflib

# plotting libs
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

def resolve_player_name_with_rag(player_name: str, require_confirmation: bool = True) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
    """
    Resolve a player name to canonical form using RAG.
    Returns: (canonical_name, ambiguous_hits) where ambiguous_hits is set if user needs to clarify.
    """
    dbg("ENTER resolve_player_name_with_rag player_name=%s require_confirmation=%s", player_name, require_confirmation)
    
    hits = rag_search_mcp(player_name, k=5)
    if not hits:
        dbg("resolve_player_name_with_rag: no RAG hits")
        return None, None
    
    # Boost scores for famous players (heuristic: longer rag_summary = more data = more famous)
    for h in hits:
        summary_len = len(str(h.get("rag_summary") or ""))
        if summary_len > 500:  # Lots of data about this player
            h["score"] = float(h.get("score", 0.0)) * 1.2  # 20% boost
            dbg("Boosting score for %s (long summary)", h.get("player"))
    
    # Re-sort after boosting
    hits = sorted(hits, key=lambda x: -float(x.get("score", 0.0)))
    
    # Filter to high-confidence matches
    high_confidence = [h for h in hits if float(h.get("score", 0.0)) >= TOP_RAG_MIN_SCORE]
    
    if len(high_confidence) == 1:
        # Single high-confidence match - auto-resolve
        canonical = high_confidence[0].get("player")
        dbg("resolve_player_name_with_rag: single high-confidence match '%s'", canonical)
        return canonical, None
    
    if len(high_confidence) > 1:
        # Multiple high-confidence matches - need disambiguation
        # BUT: if one is clearly better (>15% score difference), use it
        top_score = float(high_confidence[0].get("score", 0.0))
        second_score = float(high_confidence[1].get("score", 0.0))
        if top_score > second_score * 1.15:
            canonical = high_confidence[0].get("player")
            dbg("resolve_player_name_with_rag: top score significantly better (%.3f vs %.3f), using '%s'", top_score, second_score, canonical)
            return canonical, None
        
        dbg("resolve_player_name_with_rag: %d high-confidence matches, need disambiguation", len(high_confidence))
        if require_confirmation:
            return None, high_confidence
        else:
            # If not requiring confirmation, take the top one
            return high_confidence[0].get("player"), None
    
    # Only medium/low confidence matches
    if len(hits) > 0:
        top_score = float(hits[0].get("score", 0.0))
        if top_score >= 0.45:  # Lower threshold for single match
            canonical = hits[0].get("player")
            dbg("resolve_player_name_with_rag: single medium-confidence match '%s' (score=%.3f)", canonical, top_score)
            return canonical, None
        else:
            dbg("resolve_player_name_with_rag: low confidence (top score=%.3f)", top_score)
            if require_confirmation and len(hits) >= 2:
                return None, hits[:3]  # Show top 3 for disambiguation
    
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
    new_question_indicators = [
        r"\b(who is|whos|who's)\b",
        r"^(tell me about|describe|explain)",
        r"^(search|find|lookup)",
    ]

    is_new_question = any(re.search(pattern, query_text.lower()) for pattern in new_question_indicators)

    for player in players:
        player_lower = player.strip().lower()
        if player_lower in pronouns:
            # DON'T resolve if this looks like a new question
            if is_new_question:
                dbg("Not resolving pronoun '%s' - detected new question pattern", player)
                resolved.append(player)
            # Replace pronoun with last player from context
            elif CONTEXT["last_players"]:
                resolved.append(CONTEXT["last_players"][0])
                dbg("Resolved pronoun '%s' to last player '%s'", player, CONTEXT["last_players"][0])
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

def present_disambiguation_options(options: List[Dict[str, Any]], original_text: str, intent_struct: Dict[str,Any]):
    """Stores pending disambiguation in CONTEXT and prints numbered choices."""
    if not options:
        return
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

def resolve_pending_disambiguation(user_reply: str) -> Optional[str]:
    """If CONTEXT has 'pending_disambig', try to match user_reply to one of the options."""
    pd = CONTEXT.get('pending_disambig')
    if not pd:
        return None
    opts = pd.get("options", [])
    if not opts:
        return None
    s = user_reply.strip()

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
- players: list of ALL player names mentioned (including pronouns like "him", "her", "them")
- team: team/club name or null
- position: player position or null (e.g. "striker", "forward", "midfielder", "defender")
- metrics: list of metric tokens or null if user didn't specify
- seasons_back: integer or null
- viz: one of ["time_series","radar","both","auto"]

IMPORTANT: For comparison queries like "compare X with Y" or "X vs Y", extract BOTH players.
For pronouns like "him", "her", "them", include them in the players list as-is.

Examples:
- "compare Messi with Ronaldo" -> players: ["Messi", "Ronaldo"]
- "compare him with Salah" -> players: ["him", "Salah"]
- "Haaland vs Mbappe" -> players: ["Haaland", "Mbappe"]

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
        dbg("parse_intent_with_llm parsed=%s", json.dumps(parsed)[:500])
    except Exception as e:
        dbg("parse_intent_with_llm JSON parse failed: %s; raw=%s", e, raw)
        players = []
        if "|" in query:
            parts = [p.strip() for p in query.split("|")]
            players = [parts[0]]
        parsed = {"intent": classify_intent(query), "players": players, "team": None, "position": None, "metrics": None, "seasons_back": None, "viz": "auto"}
        dbg("parse_intent_with_llm fallback=%s", parsed)

    # If no players found by LLM, try heuristics
    if not parsed.get("players"):
        heur_candidates = extract_candidate_names_from_text(query)
        dbg("Heuristic name candidates: %s", heur_candidates)
        if heur_candidates:
            hits = canonicalize_with_hits(heur_candidates, max_results=6)
            dbg("canonicalize_with_hits => %s", hits[:6])
            if hits:
                high = [h for h in hits if float(h.get("score", 0.0)) >= TOP_RAG_MIN_SCORE]
                if len(high) == 1:
                    parsed["players"] = [high[0]["player"]]
                elif len(hits) == 1 and float(hits[0].get("score", 0.0)) >= 0.45:
                    parsed["players"] = [hits[0]["player"]]
                else:
                    parsed["ambiguous_players"] = hits
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

def plot_group_timeseries(players: List[str], all_seasons: List[int], all_values: Dict[str, List[Optional[float]]], metric_name: str, fname: str):
    fig, ax = plt.subplots(figsize=(8,6))
    yrs = np.array(all_seasons)
    for p in players:
        vals = all_values.get(p, [])
        arr = np.array([np.nan if v is None else float(v) for v in vals], dtype=float)
        ax.plot(yrs, arr, marker='o', linestyle='-', label=p)
    ax.set_xticks(yrs)
    ax.set_xlabel("Season")
    ax.set_ylabel(metric_name)
    ax.set_title(f"Group time-series ({metric_name})")
    ax.legend(loc='upper left', fontsize='small')
    ax.grid(True)
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

def plot_group_radar(players: List[str], metric_labels: List[str], players_percentiles: Dict[str, List[float]], fname: str):
    N = len(metric_labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]
    fig = plt.figure(figsize=(8,8))
    ax = fig.add_subplot(111, polar=True)
    for p in players:
        vals = players_percentiles.get(p, [])
        if not vals or len(vals) != N:
            continue
        data = vals + vals[:1]
        ax.plot(angles, data, label=p, marker='o')
        ax.fill(angles, data, alpha=0.15)
    ax.set_thetagrids(np.degrees(angles[:-1]), metric_labels)
    ax.set_title("Latest-season percentiles (0-100)")
    ax.set_ylim(0, 100)
    ax.grid(True)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
    return safe_save_plot(fig, fname)

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
"""
        else:
            prompt = f"""
You are a knowledgeable football analyst. Use the RAG snippets below. If exact numeric values are not present in the snippets, attempt an informed answer labeled clearly as ESTIMATE or BEST_EFFORT. If you use a proxy column (e.g. 'progressive_passes' for 'passes'), say so.

{schema_line}

RAG SNIPPETS:
{rag_ctx}

USER QUESTION:
{question}

Answer briefly and factually. If answering requires numeric data not present, say DATA_MISSING and then offer a best-effort summary labeled ESTIMATE (with the reason).
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
You are a concise football data assistant. Use the RAG snippets below. If the snippets do not contain exact numeric data needed, reply exactly with the token DATA_MISSING followed by a short note about what is missing (player/stat/seasons).
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
        present_disambiguation_options(intent_struct["ambiguous_players"], user_text, intent_struct)
        return intent_struct

    players = intent_struct.get("players") or []

    # CRITICAL: Resolve pronouns in player list FIRST (but only for follow-up questions)
    if players:
        players = resolve_pronouns_in_player_list(players, user_text)
        intent_struct["players"] = players
        dbg("After pronoun resolution: players=%s", players)

    metrics = intent_struct.get("metrics")
    intent = intent_struct.get("intent")

    # Detect if this is a new question (not a follow-up)
    new_question_patterns = [
        r"\b(who is|whos|who's)\b",
        r"\b(tell me about|describe|explain)\b",
        r"\b(search|find|lookup)\b",
        r"\b(compare|versus|vs)\b",
    ]
    is_new_question = any(re.search(pattern, user_text.lower()) for pattern in new_question_patterns)

    # Resolve pronoun ONLY for follow-up questions (not new questions)
    if not players and not is_new_question:
        pron = resolve_pronouns_or_last_player(user_text)
        if pron:
            players = [pron]
            intent_struct["players"] = players
            dbg("Slot manager resolved pronoun to %s", pron)
            return intent_struct

    # If we have players, try to resolve them to canonical names via RAG
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
            present_disambiguation_options(first_ambig["options"], user_text, intent_struct)
            intent_struct["ambiguous_players"] = first_ambig["options"]
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
                present_disambiguation_options(ambiguous, user_text, intent_struct)
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

def validate_and_plot_radar(players: List[str], metrics: List[str], seasons_back: int, text: str) -> Optional[str]:
    dbg("validate_and_plot_radar players=%s metrics=%s seasons_back=%d", players, metrics, seasons_back)
    latest_vals = {p: [] for p in players}
    players_percentiles = {p: [] for p in players}
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
            resp = aggregate_mcp(p, stat=metric, seasons_back=1)
            val = None
            if isinstance(resp, dict) and resp.get("found"):
                per = resp.get("per_season") or []
                if per:
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
                dbg("Radar: no present values for metrics=%s players=%s", metrics, players)
                return None

    if len(metrics) < 3:
        dbg("Radar needs >=3 metrics; got %d", len(metrics))
        return None

    for p in players:
        if len(players_percentiles[p]) != len(metrics):
            players_percentiles[p] = [0.0] * len(metrics)

    fname = f"group_radar_{int(time.time())}.png"
    try:
        return plot_group_radar(players, metrics, players_percentiles, fname)
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

            # Replace the ambiguous player with the chosen canonical name
            if orig_intent.get("players"):
                orig_intent["players"] = [chosen]
            else:
                orig_intent["players"] = [chosen]

            # Remove ambiguous_players flag
            orig_intent.pop("ambiguous_players", None)

            # Continue processing with the updated intent (DON'T recursively call handle_input)
            text = orig_text  # Use original query text
            intent_struct = orig_intent
            intent = intent_struct.get("intent", classify_intent(text))
            players = [chosen]  # Use the chosen player directly
            team = intent_struct.get("team")
            position = intent_struct.get("position")
            raw_metrics = intent_struct.get("metrics")
            seasons_back = intent_struct.get("seasons_back") or None

            # Update context with the resolved player
            push_context([chosen], intent, hits=None)

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
        players = intent_struct.get("players") or []
        team = intent_struct.get("team")
        position = intent_struct.get("position")
        raw_metrics = intent_struct.get("metrics")
        seasons_back = intent_struct.get("seasons_back") or None

    # Check if user is responding to a metric clarification request
    if not players and CONTEXT.get("last_players") and CONTEXT.get("last_intent") in ("plot", "compare", "aggregate"):
        # User might be responding with metric choice
        if re.search(r"\b(default|defaults|all|all of them|use default)\b", text.lower()):
            players = CONTEXT["last_players"]
            available_cols = get_available_columns()
            rag_hits = CONTEXT.get("last_hits") or []
            raw_metrics = choose_default_metrics_for_players(players, rag_hits, available_cols)
            intent = CONTEXT["last_intent"]
            dbg("User chose defaults - using players=%s metrics=%s", players, raw_metrics)

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
        # If it's a COMPARISON request with 2+ players, generate comparison
        if intent == "compare" and len(players) >= 2:
            dbg("User requesting comparison of %d players: %s", len(players), players)

            # Gather data for all players
            comparison_data = []
            for player in players:
                # Get player info via RAG
                rag_ctx, hits = build_context_from_rag(player, k=3)
                comparison_data.append({
                    "player": player,
                    "context": rag_ctx,
                    "hits": hits
                })

            # Build comparison prompt
            comparison_prompt = f"""You are a football analyst. Compare these players based on the information provided:

"""
            for i, data in enumerate(comparison_data, 1):
                comparison_prompt += f"\nPlayer {i}: {data['player']}\n{data['context']}\n"

            comparison_prompt += f"""

User question: {text}

Provide a concise comparison (3-5 sentences) covering their positions, playing styles, key statistics, and notable differences. Be factual and based only on the data provided."""

            try:
                ans = llm.predict(comparison_prompt, max_tokens=500, temperature=0.0)
                print("\n", ans)
                print()
                push_context(players, intent, hits=None)
                return
            except Exception as e:
                dbg("Comparison LLM error: %s", e)
                print("Sorry, I couldn't generate a comparison. Here's what I found about each player:")
                for data in comparison_data:
                    print(f"\n{data['player']}:")
                    ans = llm_fallback_answer(f"Tell me about {data['player']}", data['context'], data['hits'])
                    print(ans)
                return

        # If it's a search/natural question about the player, answer with RAG
        if intent in ("search", "natural"):
            dbg("User asking about player without metrics - using RAG to answer")
            rag_ctx, hits = build_context_from_rag(text, k=6)

            # Store hits in context for later use
            push_context(players, intent, hits=hits)

            # Use LLM fallback which is smarter about answering general questions
            ans = llm_fallback_answer(text, rag_ctx, hits)

            # Print the answer directly - no DATA_MISSING checking for biographical queries
            print("\n", ans)
            print()
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

    # If still nothing, use RAG + LLM fallback answer
    rag_ctx, hits = build_context_from_rag(text, k=6)
    ans = answer_with_context(text, rag_ctx, hits)
    if isinstance(ans, str) and "DATA_MISSING" in ans:
        top_player, score = top_rag_player_name(text)
        if top_player and score >= TOP_RAG_MIN_SCORE:
            default_stat = None
            try:
                if metrics and len(metrics) > 0:
                    default_stat = metrics[0]
            except Exception:
                default_stat = None
            default_stat = default_stat or "goals"
            print(f"DATA_MISSING. Attempting automatic slot-fill using top RAG player: {top_player}, stat={default_stat}")
            res = aggregate_mcp(top_player, stat=default_stat, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
            if isinstance(res, dict) and res.get("found"):
                safe_print_json(res)
                push_context([top_player], intent, hits=None)
                return
        fb = llm_fallback_answer(text, rag_ctx, hits)
        print("\nLLM fallback:\n", fb)
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