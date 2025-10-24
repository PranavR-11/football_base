#!/usr/bin/env python3
"""
Patched agent: canonicalization, position-aware defaults, LLM-fallback, safer MCP handling.
Drop this over your existing langchain_agent.py (keep a backup).
"""
import os
import sys
import json
import base64
import time
import traceback
import hashlib
import sqlite3
import re
from typing import List, Dict, Any, Optional
from collections import Counter
import difflib
from dotenv import load_dotenv
load_dotenv()

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
dbg("Config: CACHE_DB_PATH=%s DEFAULT_SEASONS_BACK=%d OPENAI_TEMPERATURE=%s",
    CACHE_DB_PATH, DEFAULT_SEASONS_BACK, OPENAI_TEMPERATURE)

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
    v = json.dumps(value, ensure_ascii=False)
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

# wrappers
def rag_search_mcp(query: str, k: int = 5):
    res = call_mcp("search_player", {"query": query, "k": k})
    if not isinstance(res, list):
        return []
    return res

def aggregate_mcp(player_name: str, stat: str = "goals", seasons_back: int = 3):
    payload = {"player_name": player_name, "player": player_name, "stat": stat, "seasons_back": seasons_back}
    return call_mcp("aggregate_player_stat", payload)

def plot_mcp(player_name: str, metrics):
    if isinstance(metrics, str):
        metrics = [m.strip() for m in metrics.split(",") if m.strip()]
    payload = {"player_name": player_name, "player": player_name, "metrics": metrics}
    return call_mcp("plot_player", payload)

def filter_players_mcp(team: Optional[str] = None, position: Optional[str] = None, seasons_back: int = 5):
    return call_mcp("filter_players", {"team": team, "position": position, "seasons_back": seasons_back})

def aggregate_group_mcp(players: List[str], stat: str = "goals", seasons_back: int = 5):
    return call_mcp("aggregate_group_stats", {"players": players, "stat": stat, "seasons_back": seasons_back})

def plot_group_mcp(players: List[str], metrics: Optional[List[str]] = None, seasons_back: int = 5):
    return call_mcp("plot_group", {"players": players, "metrics": metrics, "seasons_back": seasons_back})

def get_schema_mcp():
    """Ask MCP for dataset schema/columns (new tools.get_schema). Returns list or None."""
    r = call_mcp("get_schema", {})
    if isinstance(r, list):
        return r
    return None

# ---------------- OpenAI adapter (unchanged semantics) ----------------
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

# ---------------- Intent stuff (unchanged) ----------------
COMMON_PLOT_METRICS = ["goals_per_90", "xg_per_90", "npxg_per_90", "assists_per_90", "shots_per_90"]
COMMON_STATS = ["goals", "assists", "playing_time_starts", "minutes", "shots"]

def classify_intent(text: str) -> str:
    t = text.lower()
    if re.search(r"\bplot\b|\bshow\b|\bvisualize\b", t):
        return "plot"
    if re.search(r"\baggregate\b|\bsum\b|\btotal\b|\bhow many\b|\bcount\b", t):
        return "aggregate"
    if re.search(r"\bsearch\b|\bfind\b|\brag\b", t):
        return "search"
    if re.search(r"\bcompare\b|\bvs\b|\bversus\b|\bv s\b", t):
        return "compare"
    return "natural"

# ---------------- Metric aliasing & normalization ----------------
# full alias mapping (the one you provided + added small corrections)
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
    "passes": "progressive_passes",  # you defined passes = progressive_passes
    "passes forward": "progressive_passes",

    "progressive received": "progressive_received",
    "progressive receives": "progressive_received",
    "passes received": "progressive_received",
    "progressive passes received": "progressive_received",

    # per-90 rates (natural phrasings)
    "goals per 90": "goals_per_90",
    "goals/90": "goals_per_90",
    "goals per 90 mins": "goals_per_90",
    "goals/90 mins": "goals_per_90",
    "goals per ninety": "goals_per_90",
    "goals per ninety mins": "goals_per_90",
    "goals per 90 mins": "goals_per_90",


    "assists per 90": "assists_per_90",
    "assists/90": "assists_per_90",
    "assists per 90": "assists_per_90",
    "assists per 90 mins": "assists_per_90",
    "assists/90 mins": "assists_per_90",
    "assists per 90 mins": "assists_per_90",

    "goal contributions per 90": "goals_assists_per_90",
    "g plus a per 90": "goals_assists_per_90",
    "goals and assists per 90": "goals_assists_per_90",
    "goal plus assists per 90": "goals_assists_per_90",
    "goal contributions per 90 mins": "goals_assists_per_90",
    "g plus a per 90 mins": "goals_assists_per_90",
    "goals and assists per 90 mins": "goals_assists_per_90",
    "goal plus assists per 90 mins": "goals_assists_per_90",

    "non penalty goals per 90": "goals_no_pk_per_90",
    "non pen goals per 90": "goals_no_pk_per_90",
    "goals excluding penalty per 90": "goals_no_pk_per_90",
    "non penalty goals per 90 mins": "goals_no_pk_per_90",
    "goals excluding penalty per 90 mins": "goals_no_pk_per_90",

    "goal contributions no penalty per 90": "goals_assists_no_pk_per_90",
    "g plus a without pens per 90": "goals_assists_no_pk_per_90",
    "goals and assists without pens per 90": "goals_assists_no_pk_per_90",
    "goal plus assists without pens per 90": "goals_assists_no_pk_per_90",
    "goal contributions without pens per 90 mins": "goals_assists_no_pk_per_90",
    "g plus a without pens per 90 mins": "goals_assists_no_pk_per_90",
    "goals and assists without pens per 90 mins": "goals_assists_no_pk_per_90",
    "goal plus assists without pens per 90 mins": "goals_assists_no_pk_per_90",

    "xg per 90": "xg_per_90",
    "xg/90": "xg_per_90",
    "expected goals per 90": "xg_per_90",
    "expected goals/90": "xg_per_90",
    "expected goals per 90 mins": "xg_per_90",
    "expected goals/90 mins": "xg_per_90",
    "expected goals per ninety": "xg_per_90",
    "expected goals per ninety mins": "xg_per_90",
    "expected goals per 90 mins": "xg_per_90",

    "xag per 90": "xag_per_90",
    "xag/90": "xag_per_90",
    "expected assists per 90": "xag_per_90",
    "expected assists/90": "xag_per_90",
    "expected assists per 90": "xag_per_90",
    "expected assists per 90 mins": "xag_per_90",
    "expected assists/90 mins": "xag_per_90",
    "expected assists per 90 mins": "xag_per_90",

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
    if not token:
        return None
    k = token.strip().lower()
    # exact alias
    if k in METRIC_ALIASES:
        candidate = METRIC_ALIASES[k]
        # if schema present, ensure candidate exists; otherwise return candidate anyway
        if available_cols:
            if candidate in available_cols:
                return candidate
            # if candidate not present but a close match exists, pick that
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

# helper: ask server for schema columns (if available)
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
    # fallback: call search_player for a single hit and inspect keys
    sample = rag_search_mcp("salah", k=1)
    if isinstance(sample, list) and sample:
        # if rag_summary present, we cannot infer columns; ask for get_schema in tools instead in a later patch.
        return None
    return None

# ---------------- Prompt & RAG answer + LLM fallback ----------------
SLOT_PROMPT = """
Extract the structured intent from the user query. Return only valid JSON (no explanation).
Fields:
- intent: one of ["plot","compare","aggregate","list","search","natural"]
- players: list of player names (may be empty)
- team: team/club name or null
- position: player position or null (e.g. "striker", "forward", "midfielder", "defender")
- metrics: list of metric tokens or null if user didn't specify
- seasons_back: integer or null
- viz: one of ["time_series","radar","both","auto"]

User query: {query}

Respond ONLY with JSON.
"""

def parse_intent_with_llm(query: str) -> Dict[str, Any]:
    dbg("ENTER parse_intent_with_llm query_preview=%s", query[:200])
    prompt = SLOT_PROMPT.format(query=query)
    raw = llm.predict(prompt, max_tokens=300, temperature=OPENAI_TEMPERATURE)
    dbg("parse_intent_with_llm raw_response_preview=%s", (raw[:400] if raw else "<none>"))
    import re
    m = re.search(r"(\{.*\})", raw or "", re.S)
    jtxt = m.group(1) if m else (raw or "")
    try:
        parsed = json.loads(jtxt)
        parsed.setdefault("intent", classify_intent(query))
        parsed.setdefault("players", parsed.get("players") or [])
        parsed.setdefault("team", parsed.get("team"))
        parsed.setdefault("position", parsed.get("position"))
        parsed.setdefault("metrics", parsed.get("metrics"))
        parsed.setdefault("seasons_back", parsed.get("seasons_back"))
        parsed.setdefault("viz", parsed.get("viz", "auto"))
        dbg("parse_intent_with_llm parsed=%s", json.dumps(parsed)[:500])
        return parsed
    except Exception as e:
        dbg("parse_intent_with_llm JSON parse failed: %s; raw=%s", e, raw)
        players = []
        if "|" in query:
            parts = [p.strip() for p in query.split("|")]
            players = [parts[0]]
        fallback = {"intent": classify_intent(query), "players": players, "team": None, "position": None, "metrics": None, "seasons_back": None, "viz": "auto"}
        dbg("parse_intent_with_llm fallback=%s", fallback)
        return fallback

# ---------------- position defaults ----------------
POS_DEFAULT_METRICS = {
    "fw": ["goals_per_90", "xg_per_90"],
    "mf": ["assists_per_90", "xg_per_90"],
    "df": ["progressive_passes", "progressive_carries"],
    "gk": ["saves", "clean_sheets"],
}

# ---------------- top_rag_player_name ----------------
def top_rag_player_name(query: str):
    dbg("ENTER top_rag_player_name query=%s", query)
    hits = rag_search_mcp(query, k=3)
    if not hits:
        dbg("top_rag_player_name no hits")
        return None
    for h in hits:
        p = h.get("player")
        if p:
            dbg("top_rag_player_name -> %s", p)
            return p
    dbg("top_rag_player_name found no player field")
    return None

def build_context_from_rag(query, k=5):
    hits = rag_search_mcp(query, k=k)
    ctx_lines = []
    for i, h in enumerate(hits):
        player = h.get("player") or ""
        season = h.get("season") or ""
        snippet = h.get("rag_summary") or ""
        score = h.get("score")
        ctx_lines.append(f"[{i+1}] player={player} season={season} score={score}\n{snippet}")
    return "\n\n".join(ctx_lines), hits

def llm_fallback_answer(question: str, rag_ctx: str, rag_hits: List[Dict[str,Any]]):
    try:
        schema_cols = get_available_columns() or []
        schema_line = "DATA SCHEMA (some relevant columns): " + ", ".join(sorted(schema_cols[:50])) if schema_cols else ""
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

# ---------------- helpers for choosing defaults ----------------
def infer_position_from_rag(rag_hits: List[Dict[str, Any]]) -> Optional[str]:
    if not rag_hits:
        return None

    token_to_canonical = {
        "gk": "gk", "goalkeeper": "gk", "keeper": "gk", "goalie": "gk",
        "cb": "df", "center back": "df", "centre back": "df", "centre-back": "df",
        "center-back": "df", "centerback": "df", "centreback": "df",
        "center halves": "df", "centre half": "df",
        "defender": "df", "defence": "df", "defensive": "df",
        "fullback": "df", "full-back": "df", "full back": "df",
        "lb": "df", "left back": "df", "left-back": "df", "leftback": "df",
        "rb": "df", "right back": "df", "right-back": "df", "rightback": "df",
        "wingback": "df", "lwb": "df", "rwb": "df",
        "sweeper": "df",
        "mid": "mf", "mf": "mf", "midfielder": "mf", "midfield": "mf", "midfielders": "mf",
        "cm": "mf", "central midfielder": "mf", "centre midfielder": "mf",
        "dm": "mf", "defensive midfielder": "mf", "holding midfielder": "mf", "cdm": "mf",
        "am": "mf", "attacking midfielder": "mf", "cam": "mf", "creative midfielder": "mf",
        "box to box": "mf",
        "fw": "fw", "forward": "fw", "forwards": "fw", "striker": "fw", "st": "fw",
        "cf": "fw", "center forward": "fw", "centre forward": "fw",
        "winger": "fw", "wing": "fw", "rw": "fw", "right wing": "fw", "right winger": "fw",
        "lw": "fw", "left wing": "fw", "left winger": "fw",
        "inside forward": "fw", "ss": "fw", "second striker": "fw",
        "false nine": "fw", "attacker": "fw",
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
    pos = infer_position_from_rag(rag_hits)
    if pos:
        if pos in POS_DEFAULT_METRICS:
            metrics = [normalize_metric_token(m, available_cols) for m in POS_DEFAULT_METRICS[pos] if m]
            return [m for m in metrics if m]
    if available_cols:
        out = []
        for m in COMMON_PLOT_METRICS:
            nm = normalize_metric_token(m, available_cols)
            if nm:
                out.append(nm)
            if len(out) >= 2:
                break
        return out or COMMON_PLOT_METRICS[:2]
    return COMMON_PLOT_METRICS[:2]

# ---------------- Safe printing/saving of images ----------------
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
# ---------------- Synthesis + small helpers ----------------
def extract_target_year_from_text(text: str) -> Optional[int]:
    """Return a 4-digit year if present in user text (e.g. 2025) else None."""
    m = re.search(r"\b(20\d{2})\b", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def synthesize_tool_output(tool_name: str, tool_output: Any, user_query: str, max_tokens: int = 220) -> str:
    """
    Turn structured result (dict/list) into a short natural English reply via the LLM.
    Keeps instructions short and deterministic (temperature = 0 unless overridden).
    """
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
        # fallback to mechanical summarization
        if isinstance(tool_output, dict) and tool_output.get("found") is False:
            return f"Tool reported: {tool_output.get('message', 'not found')}"
        return "Here's the raw tool output: " + (str(tool_output)[:800])

def humanize_aggregate_for_year(resp: dict, year: int) -> Optional[str]:
    """
    If an aggregate result contains per_season entries with 'season_year' or 'season_label',
    extract value for `year` and produce one-line English summary.
    """
    if not isinstance(resp, dict) or not resp.get("found"):
        return None
    player = resp.get("player", "<player>")
    per = resp.get("per_season") or []
    # look for season_year entries
    for item in per:
        if "season_year" in item and int(item.get("season_year")) == int(year):
            val = item.get("value")
            if val is None:
                return f"{player} -- no data for {year} (value missing)."
            return f"{player} had {val} ({resp.get('stat','metric') if resp.get('stat') else ''}) in {year}."
    # fallback: seasons labeled
    for item in per:
        if "season_label" in item and str(item.get("season_label")).strip().startswith(str(year)):
            val = item.get("value")
            if val is None:
                return f"{player} -- no data for {year} (season label present but value missing)."
            return f"{player} had {val} in {item.get('season_label')}."
    return None


# ---------------- Interactive handling (main REPL) ----------------
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

# def handle_input(text: str):
    dbg("ENTER handle_input text_preview=%s", (text[:200].replace("\n","\\n") if text else "<empty>"))
    text = (text or "").strip()
    if not text:
        return
    if text.lower() in ("exit", "quit"):
        print("Goodbye.")
        sys.exit(0)

    # explicit quick commands
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
        if isinstance(res, dict) and res.get("found") is False:
            rag_ctx, hits = build_context_from_rag(text, k=6)
            ans = llm_fallback_answer(text, rag_ctx, hits)
            print("\nLLM fallback:\n", ans)
            return
        safe_print_json(res)
        return

    # shorthand pipes
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
                safe_print_json(res)
            return
        else:
            seasons_back = int(third) if third else DEFAULT_SEASONS_BACK
            available_cols = get_available_columns()
            stat = normalize_metric_token(second or "goals", available_cols) or (second or "goals")
            res = aggregate_mcp(player, stat=stat, seasons_back=seasons_back)
            if isinstance(res, dict) and res.get("found") is False:
                rag_ctx, hits = build_context_from_rag(text, k=6)
                ans = llm_fallback_answer(text, rag_ctx, hits)
                print("\nLLM fallback:\n", ans)
                return
            safe_print_json(res)
            return

    # Natural language path
    rag_ctx, hits = build_context_from_rag(text, k=6)
    if not rag_ctx:
        # no local data -> directly ask LLM (cacheable)
        cache_key = {"type":"llm_direct","query":text}
        cached = cache_get(cache_key)
        if cached:
            print("LLM answer (cached):\n", cached)
            return
        ans = llm.predict(text)
        print("LLM answer:\n", ans)
        cache_set(cache_key, ans)
        return

    intent_struct = parse_intent_with_llm(text)
    intent = intent_struct.get("intent", classify_intent(text))
    players = intent_struct.get("players") or []
    team = intent_struct.get("team")
    position = intent_struct.get("position")
    raw_metrics = intent_struct.get("metrics")
    seasons_back = intent_struct.get("seasons_back") or None

    available_cols = get_available_columns()

    # normalize any metrics the LLM returned
    metrics = None
    if raw_metrics:
        if isinstance(raw_metrics, str):
            raw_list = [m.strip() for m in raw_metrics.split(",") if m.strip()]
        else:
            raw_list = [m for m in raw_metrics if isinstance(m, str)]
        metrics = [normalize_metric_token(m, available_cols) for m in raw_list]
    dbg("Intent=%s players=%s metrics=%s", intent, players, metrics)

    # slot filling using team/position
    if not players and (team or position):
        flt = filter_players_mcp(team=team, position=position, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
        if isinstance(flt, dict) and flt.get("ok") is False:
            print("Error filtering players:", flt)
            return
        players = flt.get("players", []) if flt else []

    # compare/plot flow
    if intent in ("compare", "plot"):
        if not players:
            top = top_rag_player_name(text)
            if top:
                players = [top]
        if not players:
            ans = answer_with_context(text, rag_ctx, hits)
            print("\nLLM answer:\n", ans)
            return

        if not metrics:
            metrics = choose_default_metrics_for_players(players, hits, available_cols)
            print(f"No metrics specified — using defaults {metrics} for player(s).")

        # limit players to a reasonable number
        max_players_for_plot = int(os.getenv("MAX_PLAYERS_FOR_PLOT", "12"))
        players_to_plot = players[:max_players_for_plot]

        res = plot_group_mcp(players_to_plot, metrics=metrics, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
        if isinstance(res, dict) and res.get("ok") is False:
            print("Plot error (dataset):", res)
            # fallback LLM summary
            ans = llm_fallback_answer(text, rag_ctx, hits)
            print("\nLLM fallback:\n", ans)
            return
        if isinstance(res, dict) and res.get("image_b64"):
            fname = save_b64_image(res["image_b64"], fname=f"group_plot_{int(time.time())}.png")
            print("Group plot saved to", fname)
            # ask LLM to summarize the plot (use a slightly higher temperature for conversational summary)
            summ_prompt = f"Briefly summarize (2 bullets) what the plot for players {players_to_plot} across metrics {metrics} shows. Be factual and concise."
            summary = llm.predict(summ_prompt, max_tokens=200, temperature=min(0.6, OPENAI_TEMPERATURE + 0.2))
            print("\nSummary:\n", summary)
        else:
            safe_print_json(res)
        return

    # aggregate group stats
    if intent == "aggregate":
        if not players:
            top = top_rag_player_name(text)
            if top:
                players = [top]
            else:
                print("No players specified or found for aggregation.")
                return
        stat = (metrics[0] if metrics else "goals") if metrics else "goals"
        stat = normalize_metric_token(stat, available_cols) or stat
        res = aggregate_group_mcp(players, stat=stat, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
        safe_print_json(res)
        return

    # default: ask LLM with RAG context
    ans = answer_with_context(text, rag_ctx, hits)
    if isinstance(ans, str) and "DATA_MISSING" in ans:
        top_player = top_rag_player_name(text)
        if top_player:
            # Prefer the metric the parser returned; otherwise fall back to 'goals'.
            preferred = None
            try:
                if metrics and isinstance(metrics, list) and len(metrics) > 0 and metrics[0]:
                    preferred = metrics[0]
                elif isinstance(raw_metrics, str) and raw_metrics.strip():
                    preferred = raw_metrics.strip().split(",")[0]
            except Exception:
                preferred = None

            # Normalize preferred metric against available schema (if available).
            try:
                available_cols = get_available_columns()
            except Exception:
                available_cols = None

            if preferred:
                try:
                    preferred = normalize_metric_token(preferred, available_cols) or preferred
                except Exception:
                    pass

            default_stat = preferred or "goals"

            print(f"DATA_MISSING. Attempting automatic slot-fill using top RAG player: {top_player}, stat={default_stat}")
            res = aggregate_mcp(top_player, stat=default_stat, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
            if isinstance(res, dict) and res.get("found"):
                safe_print_json(res)
                return

        # If automatic aggregate fails, call the LLM fallback with schema/context.
        fb = llm_fallback_answer(text, rag_ctx, hits)
        print("\nLLM fallback:\n", fb)
        return

    print("\nLLM answer:\n")
    print(ans)
    print()
def handle_input(text: str):
    dbg("ENTER handle_input text_preview=%s", (text[:200].replace("\n","\\n") if text else "<empty>"))
    text = (text or "").strip()
    if not text:
        return
    if text.lower() in ("exit", "quit"):
        print("Goodbye.")
        sys.exit(0)

    # quick commands unchanged
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
        # synthesize
        summary = synthesize_tool_output("aggregate_player_stat", res, text)
        print(summary)
        return

    # check for pipe-style shorthand first (leave behavior similar to before)
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

    # Natural-language path: parse intent first (small-talk short-circuit)
    intent_struct = parse_intent_with_llm(text)
    intent = intent_struct.get("intent", classify_intent(text))
    players = intent_struct.get("players") or []
    team = intent_struct.get("team")
    position = intent_struct.get("position")
    raw_metrics = intent_struct.get("metrics")
    seasons_back = intent_struct.get("seasons_back") or None

    # If user just said 'hi' or non-domain chit-chat, respond with LLM small-talk and skip RAG
    no_slots = not (players or raw_metrics or team or position or seasons_back)
    if intent == "natural" and no_slots:
        small = llm.predict(f"You are a friendly football assistant. Reply briefly to this user message: {text}", max_tokens=120, temperature=0.7)
        print("LLM answer:\n", small)
        return

    # Now we need RAG context for domain queries only
    rag_ctx, hits = build_context_from_rag(text, k=6)
    available_cols = get_available_columns()

    # normalize metrics returned by LLM
    metrics = None
    if raw_metrics:
        if isinstance(raw_metrics, str):
            raw_list = [m.strip() for m in raw_metrics.split(",") if m.strip()]
        else:
            raw_list = [m for m in raw_metrics if isinstance(m, str)]
        metrics = [normalize_metric_token(m, available_cols) for m in raw_list]

    dbg("Intent=%s players=%s metrics=%s", intent, players, metrics)

    # Try to fill players from team/position if none found
    if not players and (team or position):
        flt = filter_players_mcp(team=team, position=position, seasons_back=(seasons_back or DEFAULT_SEASONS_BACK))
        if isinstance(flt, dict) and flt.get("ok") is False:
            print("Error filtering players:", flt)
            return
        players = flt.get("players", []) if flt else []

    # If still no players, use RAG top hit
    if not players:
        top = top_rag_player_name(text)
        if top:
            players = [top]

    # detect explicit year in user query, prefer year if present
    explicit_year = extract_target_year_from_text(text)
    if explicit_year:
        # if a year is present, we will request a broader seasons_back then filter by year
        seasons_for_query = max(DEFAULT_SEASONS_BACK, 10)
    else:
        seasons_for_query = seasons_back or DEFAULT_SEASONS_BACK

    # handle plot/compare
    if intent in ("compare", "plot"):
        if not players:
            ans = answer_with_context(text, rag_ctx, hits)
            print("\nLLM answer:\n", ans)
            return

        if not metrics:
            metrics = choose_default_metrics_for_players(players, hits, available_cols)
            print(f"No metrics specified — using defaults {metrics} for player(s).")

        max_players_for_plot = int(os.getenv("MAX_PLAYERS_FOR_PLOT", "12"))
        players_to_plot = players[:max_players_for_plot]

        res = plot_group_mcp(players_to_plot, metrics=metrics, seasons_back=seasons_for_query)
        if isinstance(res, dict) and res.get("ok") is False:
            print("Plot error (dataset):", res)
            ans = llm_fallback_answer(text, rag_ctx, hits)
            print("\nLLM fallback:\n", ans)
            return
        if isinstance(res, dict) and res.get("image_b64"):
            fname = save_b64_image(res["image_b64"], fname=f"group_plot_{int(time.time())}.png")
            print("Group plot saved to", fname)
            summ_prompt = f"Briefly summarize (2 bullets) what the plot for players {players_to_plot} across metrics {metrics} shows."
            summary = llm.predict(summ_prompt, max_tokens=200, temperature=min(0.6, OPENAI_TEMPERATURE + 0.2))
            print("\nSummary:\n", summary)
        else:
            print(synthesize_tool_output("plot_group", res, text))
        return

    # aggregate single player or group
    if intent == "aggregate":
        if not players:
            print("No players specified or found for aggregation.")
            return
        stat = (metrics[0] if metrics else "goals")
        stat = normalize_metric_token(stat, available_cols) or stat
        res = aggregate_group_mcp(players, stat=stat, seasons_back=seasons_for_query) if len(players) > 1 else aggregate_mcp(players[0], stat=stat, seasons_back=seasons_for_query)

        # If explicit year requested, attempt to extract just that year from the result
        if explicit_year:
            # for single-player aggregate_mcp returns dict with per_season; try to humanize quickly
            if isinstance(res, dict) and res.get("found"):
                hy = humanize_aggregate_for_year(res, explicit_year)
                if hy:
                    print(hy)
                    return
            # for group aggregates, look in per_player maps
            if isinstance(res, dict) and res.get("ok") and "per_player" in res:
                lines = []
                for p, d in res.get("per_player", {}).items():
                    if d.get("found") and isinstance(d.get("per_season"), dict):
                        v = d["per_season"].get(explicit_year)
                        if v is None:
                            lines.append(f"{p}: no data for {explicit_year}")
                        else:
                            lines.append(f"{p}: {v} ({stat}) in {explicit_year}")
                    else:
                        lines.append(f"{p}: not found")
                print("\n".join(lines))
                return

        # default: synthesize entire result
        print(synthesize_tool_output("aggregate_player_stat" if len(players) == 1 else "aggregate_group_stats", res, text))
        return

    # fallback: answer with RAG + LLM
    ans = answer_with_context(text, rag_ctx, hits)
    if isinstance(ans, str) and "DATA_MISSING" in ans:
        top_player = top_rag_player_name(text)
        if top_player:
            default_stat = "goals"
            print(f"DATA_MISSING. Attempting automatic slot-fill using top RAG player: {top_player}")
            res = aggregate_mcp(top_player, stat=default_stat, seasons_back=DEFAULT_SEASONS_BACK)
            if isinstance(res, dict) and res.get("found"):
                print(synthesize_tool_output("aggregate_player_stat", res, text))
                return
        fb = llm_fallback_answer(text, rag_ctx, hits)
        print("\nLLM fallback:\n", fb)
        return

    print("\nLLM answer:\n")
    print(ans)
    print()


# REPL
print("Lightweight Football Data Agent (patched).")
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