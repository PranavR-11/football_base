# # mcp/mcp_server.py
# from fastapi import FastAPI, HTTPException, Header, Request
# from pydantic import BaseModel
# from typing import Optional, Dict, Any, List
# # Try package-relative import first; fallback to flat import for side-by-side
# try:
#     from . import tools
# except Exception:
#     import tools
#
# from dotenv import load_dotenv
# import os
# import logging
# import inspect
# import traceback
# import datetime
#
# load_dotenv()
#
# # --- Config (env) ---
# MCP_API_KEY = os.getenv("MCP_API_KEY", "dev-token")
# MCP_API_KEY_ALIASES = os.getenv("MCP_API_KEY_ALIASES", "")
# MCP_ALLOW_ANY = os.getenv("MCP_ALLOW_ANY", "0") in ("1", "true", "True")
#
# app = FastAPI(title="Football MCP Tools (Local)")
#
# logger = logging.getLogger("mcp_server")
# logger.setLevel(logging.INFO)
# if not logger.handlers:
#     ch = logging.StreamHandler()
#     ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
#     logger.addHandler(ch)
#
#
# class ToolCall(BaseModel):
#     tool: str
#     params: Dict[str, Any] = {}
#
#
# def _mask_key_for_log(k: Optional[str]) -> str:
#     if not k:
#         return "<none>"
#     if len(k) <= 8:
#         return k[:2] + "..." + k[-2:]
#     return k[:4] + "..." + k[-4:]
#
#
# def _extract_api_key(request: Request, x_api_key: Optional[str]) -> Optional[str]:
#     """
#     Extract API key from:
#       - FastAPI header param (x_api_key)
#       - common header spellings (case-insensitive)
#       - Authorization: Bearer <token>
#       - query param "api_key"
#     """
#     # FastAPI-injected header param
#     if x_api_key:
#         return x_api_key
#
#     headers = {k.lower(): v for k, v in request.headers.items()}
#
#     for candidate in ("x-api-key", "authorization"):
#         c = candidate.lower()
#         if c in headers:
#             val = headers[c]
#             if c == "authorization":
#                 parts = val.split()
#                 if len(parts) == 2 and parts[0].lower() == "bearer":
#                     return parts[1]
#                 return val
#             return val
#
#     q = request.query_params.get("api_key")
#     if q:
#         return q
#     return None
#
#
# def _allowed_keys_list() -> List[str]:
#     out = []
#     if MCP_API_KEY:
#         out.append(MCP_API_KEY)
#     if MCP_API_KEY_ALIASES:
#         out += [a.strip() for a in MCP_API_KEY_ALIASES.split(",") if a.strip()]
#     return list(dict.fromkeys(out))
#
#
# # heuristic param-name mapping for compatibility (common pairs)
# _PARAM_NAME_MAP = {
#     "player": "player_name",
#     "player_name": "player",
#     "players": "player_list",
#     "player_list": "players",
#     "k": "limit",
#     "limit": "k",
# }
#
#
# def _call_tool_function(func, params: Dict[str, Any]):
#     """
#     Robustly attempt to call a tool function with flexible parameter handling.
#
#     Strategy:
#       1) try func(**params)
#       2) try filtered params (only names present in function signature)
#       3) try mapped param names (e.g. player -> player_name)
#       4) if function has one positional parameter, try passing single sensible value
#       5) try passing the entire dict as single positional argument
#       6) try func() (no args)
#
#     Raises a TypeError if nothing workable is found (so the caller can return a controlled 500).
#     """
#     # 1) direct attempt
#     try:
#         return func(**params)
#     except TypeError as e_direct:
#         logger.debug("Direct call to %s failed: %s", getattr(func, "__name__", str(func)), e_direct)
#         # continue
#
#     # inspect signature
#     try:
#         sig = inspect.signature(func)
#         param_names = [
#             n
#             for n, p in sig.parameters.items()
#             if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
#         ]
#     except Exception:
#         param_names = []
#
#     # 2) filtered kwargs
#     filtered = {k: v for k, v in params.items() if k in param_names}
#     if filtered:
#         try:
#             logger.info("Trying filtered kwargs for %s: %s", getattr(func, "__name__", "?"), list(filtered.keys()))
#             return func(**filtered)
#         except Exception:
#             logger.debug("Filtered kwargs attempt failed", exc_info=True)
#
#     # 3) try mapped param names (player <-> player_name etc)
#     mapped_candidates = {}
#     for k, v in params.items():
#         mapped_candidates[k] = v
#         if k in _PARAM_NAME_MAP:
#             mapped_key = _PARAM_NAME_MAP[k]
#             mapped_candidates[mapped_key] = v
#     mapped = {k: v for k, v in mapped_candidates.items() if k in param_names}
#     if mapped and mapped != filtered:
#         try:
#             logger.info("Trying mapped kwargs for %s: %s", getattr(func, "__name__", "?"), list(mapped.keys()))
#             return func(**mapped)
#         except Exception:
#             logger.debug("Mapped kwargs attempt failed", exc_info=True)
#
#     # 4) if function has exactly one normal parameter, try picking a sensible candidate value
#     normal_params = [n for n, p in sig.parameters.items() if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD]
#     if len(normal_params) == 1:
#         candidate_order = ("player", "player_name", "query", "id", "player_id", "name")
#         for cand in candidate_order:
#             if cand in params:
#                 try:
#                     logger.info("Trying single-positional arg '%s' for %s", cand, getattr(func, "__name__", "?"))
#                     return func(params[cand])
#                 except Exception:
#                     logger.debug("Single-positional attempt with key %s failed", cand, exc_info=True)
#         # try dict as single arg
#         try:
#             logger.info("Trying entire params dict as single arg for %s", getattr(func, "__name__", "?"))
#             return func(params)
#         except Exception:
#             logger.debug("Single-dict positional attempt failed", exc_info=True)
#
#     # 5) try call with no args (some tools accept none)
#     try:
#         logger.info("Trying call without args for %s", getattr(func, "__name__", "?"))
#         return func()
#     except Exception:
#         logger.debug("Call without args failed", exc_info=True)
#
#     raise TypeError(f"Could not call function {getattr(func,'__name__',str(func))} with provided params: {list(params.keys())}")
#
#
# def _sanitize_for_json(obj):
#     """
#     Recursively convert numpy/pandas/scalar types to native Python types for FastAPI JSON encoding.
#     Avoid raising — swallow to str fallback.
#     """
#     # local imports only if available
#     np = None
#     pd = None
#     try:
#         import numpy as _np
#
#         np = _np
#     except Exception:
#         np = None
#     try:
#         import pandas as _pd
#
#         pd = _pd
#     except Exception:
#         pd = None
#
#     # primitives
#     if obj is None:
#         return None
#     if isinstance(obj, (str, bool)):
#         return obj
#     if isinstance(obj, (int, float)):
#         # python primitives are already safe
#         return obj
#     # numpy scalars
#     if np is not None:
#         if isinstance(obj, (np.integer,)):
#             return int(obj)
#         if isinstance(obj, (np.floating,)):
#             return float(obj)
#         if isinstance(obj, (np.ndarray,)):
#             try:
#                 return obj.tolist()
#             except Exception:
#                 return [ _sanitize_for_json(v) for v in list(obj) ]
#     # pandas scalars/series/dataframes
#     if pd is not None:
#         if isinstance(obj, pd.Timestamp):
#             return obj.isoformat()
#         if isinstance(obj, (pd.Series,)):
#             return [ _sanitize_for_json(v) for v in obj.tolist() ]
#         if isinstance(obj, pd.DataFrame):
#             try:
#                 return obj.to_dict(orient="records")
#             except Exception:
#                 return str(obj)
#         if isinstance(obj, (pd.Timedelta,)):
#             return str(obj)
#     # mappings / sequences
#     if isinstance(obj, dict):
#         return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
#     if isinstance(obj, (list, tuple, set)):
#         return [ _sanitize_for_json(v) for v in obj ]
#     # datetime
#     if isinstance(obj, datetime.datetime):
#         return obj.isoformat()
#     if isinstance(obj, datetime.date):
#         return obj.isoformat()
#     if isinstance(obj, bytes):
#         try:
#             return obj.decode("utf-8")
#         except Exception:
#             return str(obj)
#     # fallback: try to cast to builtin types
#     try:
#         return int(obj)
#     except Exception:
#         pass
#     try:
#         return float(obj)
#     except Exception:
#         pass
#     try:
#         return str(obj)
#     except Exception:
#         return None
#
#
# @app.get("/tools")
# def list_tools() -> Dict[str, Any]:
#     """Return a simple list of tools detected in mcp.tools"""
#     available = []
#     for name in ("search_player", "aggregate_player_stat", "plot_player", "compare_players",
#                  "filter_players", "aggregate_group_stats", "plot_group"):
#         if hasattr(tools, name):
#             available.append(name)
#     return {"ok": True, "tools": available}
#
#
# @app.post("/invoke")
# async def invoke(call: ToolCall, request: Request, x_api_key: Optional[str] = Header(None)):
#     provided_key = _extract_api_key(request, x_api_key)
#
#     if provided_key is None:
#         raise HTTPException(
#             status_code=401,
#             detail="Missing API key. Provide header 'X-Api-Key' (or 'X-API-KEY') or 'Authorization: Bearer <key>'."
#         )
#
#     allowed = _allowed_keys_list()
#     if MCP_ALLOW_ANY:
#         logger.info("Auth: allowing any key (MCP_ALLOW_ANY=1). Provided=%s len=%d",
#                     _mask_key_for_log(provided_key), len(provided_key) if provided_key else 0)
#     else:
#         if provided_key not in allowed:
#             allowed_lengths = [len(k) for k in allowed]
#             logger.warning("Invalid API key attempt provided=%s len=%d allowed_lens=%s",
#                            _mask_key_for_log(provided_key), len(provided_key) if provided_key else 0, allowed_lengths)
#             raise HTTPException(status_code=401, detail="Invalid API key")
#
#     t = call.tool
#     p = call.params or {}
#
#     # prefer explicit tool lookup
#     if not hasattr(tools, t):
#         raise HTTPException(status_code=404, detail=f"Tool '{t}' not found")
#
#     func = getattr(tools, t)
#     try:
#         result = _call_tool_function(func, p)
#         sanitized = _sanitize_for_json(result)
#         return {"ok": True, "result": sanitized}
#     except HTTPException:
#         raise
#     except Exception as e:
#         # don't include raw params in error; log them masked
#         try:
#             param_keys = list(p.keys())
#         except Exception:
#             param_keys = "<unavailable>"
#         logger.exception("Tool execution error calling '%s' with params=%s: %s", t, param_keys, e)
#         raise HTTPException(status_code=500, detail=f"Tool execution error: {type(e).__name__}: {str(e)}")
#
#
# @app.get("/.well-known/mcp/health")
# def health():
#     return {"status": "ok"}
#
#
# @app.get("/.well-known/mcp/whoami")
# def whoami():
#     allowed = _allowed_keys_list()
#     primary_len = len(MCP_API_KEY) if MCP_API_KEY else 0
#     alias_lengths = [len(k) for k in allowed if k != MCP_API_KEY]
#     return {
#         "detail": "key_loaded" if MCP_API_KEY else "no_primary_key",
#         "primary_key_length": primary_len,
#         "alias_count": len(alias_lengths),
#         "alias_lengths": alias_lengths,
#         "allow_any": MCP_ALLOW_ANY,
#     }


# mcp/mcp_server.py
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
# Try package-relative import first; fallback to flat import for side-by-side
try:
    from . import tools
except Exception:
    import tools

from dotenv import load_dotenv
import os
import logging
import inspect
import traceback
import datetime

load_dotenv()

# --- Config (env) ---
MCP_API_KEY = os.getenv("MCP_API_KEY", "dev-token")
MCP_API_KEY_ALIASES = os.getenv("MCP_API_KEY_ALIASES", "")
MCP_ALLOW_ANY = os.getenv("MCP_ALLOW_ANY", "0") in ("1", "true", "True")

app = FastAPI(title="Football MCP Tools (Local)")

logger = logging.getLogger("mcp_server")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(ch)


class ToolCall(BaseModel):
    tool: str
    params: Dict[str, Any] = {}


def _mask_key_for_log(k: Optional[str]) -> str:
    if not k:
        return "<none>"
    if len(k) <= 8:
        return k[:2] + "..." + k[-2:]
    return k[:4] + "..." + k[-4:]


def _extract_api_key(request: Request, x_api_key: Optional[str]) -> Optional[str]:
    """
    Extract API key from:
      - FastAPI header param (x_api_key)
      - common header spellings (case-insensitive)
      - Authorization: Bearer <token>
      - query param "api_key"
    """
    # FastAPI-injected header param
    if x_api_key:
        return x_api_key

    headers = {k.lower(): v for k, v in request.headers.items()}

    for candidate in ("x-api-key", "authorization"):
        c = candidate.lower()
        if c in headers:
            val = headers[c]
            if c == "authorization":
                parts = val.split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]
                return val
            return val

    q = request.query_params.get("api_key")
    if q:
        return q
    return None


def _allowed_keys_list() -> List[str]:
    out = []
    if MCP_API_KEY:
        out.append(MCP_API_KEY)
    if MCP_API_KEY_ALIASES:
        out += [a.strip() for a in MCP_API_KEY_ALIASES.split(",") if a.strip()]
    return list(dict.fromkeys(out))


# heuristic param-name mapping for compatibility (common pairs)
_PARAM_NAME_MAP = {
    "player": "player_name",
    "player_name": "player",
    "players": "player_list",
    "player_list": "players",
    "k": "limit",
    "limit": "k",
}


def _call_tool_function(func, params: Dict[str, Any]):
    """
    Robustly attempt to call a tool function with flexible parameter handling.

    Strategy:
      1) try func(**params)
      2) try filtered params (only names present in function signature)
      3) try mapped param names (e.g. player -> player_name)
      4) if function has one positional parameter, try passing single sensible value
      5) try passing the entire dict as single positional argument
      6) try func() (no args)

    Raises a TypeError if nothing workable is found (so the caller can return a controlled 500).
    """
    # 1) direct attempt
    try:
        return func(**params)
    except TypeError as e_direct:
        logger.debug("Direct call to %s failed: %s", getattr(func, "__name__", str(func)), e_direct)

    # inspect signature
    try:
        sig = inspect.signature(func)
        param_names = [
            n
            for n, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]
    except Exception:
        param_names = []

    # 2) filtered kwargs
    filtered = {k: v for k, v in params.items() if k in param_names}
    if filtered:
        try:
            logger.info("Trying filtered kwargs for %s: %s", getattr(func, "__name__", "?"), list(filtered.keys()))
            return func(**filtered)
        except Exception:
            logger.debug("Filtered kwargs attempt failed", exc_info=True)

    # 3) try mapped param names (player <-> player_name etc)
    mapped_candidates = {}
    for k, v in params.items():
        mapped_candidates[k] = v
        if k in _PARAM_NAME_MAP:
            mapped_key = _PARAM_NAME_MAP[k]
            mapped_candidates[mapped_key] = v
    mapped = {k: v for k, v in mapped_candidates.items() if k in param_names}
    if mapped and mapped != filtered:
        try:
            logger.info("Trying mapped kwargs for %s: %s", getattr(func, "__name__", "?"), list(mapped.keys()))
            return func(**mapped)
        except Exception:
            logger.debug("Mapped kwargs attempt failed", exc_info=True)

    # 4) if function has exactly one normal parameter, try picking a sensible candidate value
    normal_params = [n for n, p in sig.parameters.items() if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD]
    if len(normal_params) == 1:
        candidate_order = ("player", "player_name", "query", "id", "player_id", "name")
        for cand in candidate_order:
            if cand in params:
                try:
                    logger.info("Trying single-positional arg '%s' for %s", cand, getattr(func, "__name__", "?"))
                    return func(params[cand])
                except Exception:
                    logger.debug("Single-positional attempt with key %s failed", cand, exc_info=True)
        try:
            logger.info("Trying entire params dict as single arg for %s", getattr(func, "__name__", "?"))
            return func(params)
        except Exception:
            logger.debug("Single-dict positional attempt failed", exc_info=True)

    # 5) try call with no args (some tools accept none)
    try:
        logger.info("Trying call without args for %s", getattr(func, "__name__", "?"))
        return func()
    except Exception:
        logger.debug("Call without args failed", exc_info=True)

    raise TypeError(f"Could not call function {getattr(func,'__name__',str(func))} with provided params: {list(params.keys())}")


def _sanitize_for_json(obj):
    """
    Recursively convert numpy/pandas/scalar types to native Python types for FastAPI JSON encoding.
    Avoid raising — swallow to str fallback.
    """
    # local imports only if available
    np = None
    pd = None
    try:
        import numpy as _np

        np = _np
    except Exception:
        np = None
    try:
        import pandas as _pd

        pd = _pd
    except Exception:
        pd = None

    # primitives
    if obj is None:
        return None
    if isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (int, float)):
        # python primitives are already safe
        return obj
    # numpy scalars
    if np is not None:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            try:
                return obj.tolist()
            except Exception:
                return [ _sanitize_for_json(v) for v in list(obj) ]
    # pandas scalars/series/dataframes
    if pd is not None:
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, (pd.Series,)):
            return [ _sanitize_for_json(v) for v in obj.tolist() ]
        if isinstance(obj, pd.DataFrame):
            try:
                return obj.to_dict(orient="records")
            except Exception:
                return str(obj)
        if isinstance(obj, (pd.Timedelta,)):
            return str(obj)
    # mappings / sequences
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [ _sanitize_for_json(v) for v in obj ]
    # datetime
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except Exception:
            return str(obj)
    # fallback: try to cast to builtin types
    try:
        return int(obj)
    except Exception:
        pass
    try:
        return float(obj)
    except Exception:
        pass
    try:
        return str(obj)
    except Exception:
        return None


@app.get("/tools")
def list_tools() -> Dict[str, Any]:
    """Return a simple list of tools detected in mcp.tools"""
    available = []
    # include get_schema so agents can introspect available columns
    for name in ("search_player", "aggregate_player_stat", "plot_player", "compare_players",
                 "filter_players", "aggregate_group_stats", "plot_group", "get_schema"):
        if hasattr(tools, name):
            available.append(name)
    return {"ok": True, "tools": available}


@app.post("/invoke")
async def invoke(call: ToolCall, request: Request, x_api_key: Optional[str] = Header(None)):
    provided_key = _extract_api_key(request, x_api_key)

    if provided_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide header 'X-Api-Key' (or 'X-API-KEY') or 'Authorization: Bearer <key>'."
        )

    allowed = _allowed_keys_list()
    if MCP_ALLOW_ANY:
        logger.info("Auth: allowing any key (MCP_ALLOW_ANY=1). Provided=%s len=%d",
                    _mask_key_for_log(provided_key), len(provided_key) if provided_key else 0)
    else:
        if provided_key not in allowed:
            allowed_lengths = [len(k) for k in allowed]
            logger.warning("Invalid API key attempt provided=%s len=%d allowed_lens=%s",
                           _mask_key_for_log(provided_key), len(provided_key) if provided_key else 0, allowed_lengths)
            raise HTTPException(status_code=401, detail="Invalid API key")

    t = call.tool
    p = call.params or {}

    # small debug about tool invocation
    logger.info("Invoke request for tool '%s' with params keys=%s", t, list(p.keys()))

    if not hasattr(tools, t):
        raise HTTPException(status_code=404, detail=f"Tool '{t}' not found")

    func = getattr(tools, t)
    try:
        result = _call_tool_function(func, p)
        sanitized = _sanitize_for_json(result)
        return {"ok": True, "result": sanitized}
    except HTTPException:
        raise
    except Exception as e:
        try:
            param_keys = list(p.keys())
        except Exception:
            param_keys = "<unavailable>"
        logger.exception("Tool execution error calling '%s' with params=%s: %s", t, param_keys, e)
        raise HTTPException(status_code=500, detail=f"Tool execution error: {type(e).__name__}: {str(e)}")


@app.get("/.well-known/mcp/health")
def health():
    return {"status": "ok"}


@app.get("/.well-known/mcp/whoami")
def whoami():
    allowed = _allowed_keys_list()
    primary_len = len(MCP_API_KEY) if MCP_API_KEY else 0
    alias_lengths = [len(k) for k in allowed if k != MCP_API_KEY]
    return {
        "detail": "key_loaded" if MCP_API_KEY else "no_primary_key",
        "primary_key_length": primary_len,
        "alias_count": len(alias_lengths),
        "alias_lengths": alias_lengths,
        "allow_any": MCP_ALLOW_ANY,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)