# # mcp/tools.py
# import os
# import pickle
# import math
# import re
# import base64
# import io
# from dotenv import load_dotenv
# import pandas as pd
# from typing import List, Dict, Any, Optional

# load_dotenv()

# DATA_CSV = os.getenv("DATA_PATH", "./data/FINAL_with_rag.csv")
# VECTOR_DIR = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
# EMB_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
# OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# K_DEFAULT = int(os.getenv("K_DEFAULT", "5"))
# DEFAULT_SEASONS_BACK = int(os.getenv("DEFAULT_SEASONS_BACK", "5"))

# def _ensure_openai():
#     try:
#         from openai import OpenAI
#         return OpenAI(api_key=OPENAI_KEY)
#     except Exception as e:
#         raise ImportError("Install openai>=1.0.0 and set OPENAI_API_KEY in .env. Err: " + str(e))

# def _ensure_faiss():
#     try:
#         import faiss
#         return faiss
#     except Exception as e:
#         raise ImportError("Install faiss-cpu (pip install faiss-cpu). Err: " + str(e))

# def _load_meta_df():
#     if not os.path.exists(DATA_CSV):
#         raise RuntimeError(f"CSV not found at {DATA_CSV}")
#     df = pd.read_csv(DATA_CSV)
#     # normalize rag_summary column if present
#     if "rag_summary" in df.columns:
#         df["rag_summary"] = df["rag_summary"].astype(str).fillna("")
#     return df

# def _load_index_and_meta():
#     faiss = _ensure_faiss()
#     idx_path = os.path.join(VECTOR_DIR, "index.faiss")
#     meta_path = os.path.join(VECTOR_DIR, "metadata.pkl")
#     if not os.path.exists(idx_path) or not os.path.exists(meta_path):
#         raise RuntimeError("FAISS index or metadata not found. Run scripts/batch_embed.py first.")
#     index = faiss.read_index(idx_path)
#     with open(meta_path, "rb") as f:
#         df = pickle.load(f)
#     return faiss, index, df

# def get_schema() -> List[str]:
#     """
#     Return the available columns in the canonical CSV (if present).
#     This is used by agents to map user metric tokens to real dataset columns.
#     """
#     if not os.path.exists(DATA_CSV):
#         return []
#     try:
#         df = pd.read_csv(DATA_CSV, nrows=1)
#         return list(df.columns)
#     except Exception:
#         return []

# def search_player(query: str, k: int = K_DEFAULT) -> List[Dict[str, Any]]:
#     """Semantic search using embeddings + FAISS index; returns top-k hits with rag_summary snippet."""
#     if not query:
#         return []
#     try:
#         client = _ensure_openai()
#         faiss = _ensure_faiss()
#         _, index, df = _load_index_and_meta()
#     except Exception as e:
#         # if embeddings/index not available, fallback to simple textual substring match in CSV
#         try:
#             df = _load_meta_df()
#             matches = []
#             q = str(query).lower()
#             for i, row in df.iterrows():
#                 score = 0.0
#                 txt = " ".join([str(row.get(c, "") or "") for c in ("player", "rag_summary", "season")])
#                 if q in txt.lower():
#                     score = 1.0
#                 if score > 0:
#                     matches.append({"score": float(score), "idx": int(i), "player": row.get("player"), "season": row.get("season"), "rag_summary": str(row.get("rag_summary"))[:1000]})
#             return sorted(matches, key=lambda r: r["score"], reverse=True)[:k]
#         except Exception as e2:
#             raise RuntimeError("Search unavailable: " + str(e2))

#     resp = client.embeddings.create(model=EMB_MODEL, input=[query])
#     emb = resp.data[0]["embedding"] if isinstance(resp.data[0], dict) else getattr(resp.data[0], "embedding")
#     import numpy as np
#     vec = np.array(emb, dtype="float32").reshape(1, -1)
#     faiss.normalize_L2(vec)
#     D, I = index.search(vec, k)
#     results = []
#     for score, idx in zip(D[0].tolist(), I[0].tolist()):
#         if idx < 0:
#             continue
#         row = df.iloc[idx]
#         results.append(
#             {
#                 "score": float(score),
#                 "idx": int(idx),
#                 "player": row.get("player"),
#                 "season": row.get("season"),
#                 "rag_summary": str(row.get("rag_summary"))[:1000],
#             }
#         )
#     return results

# # ------- helper: robust season -> year parser -------
# def season_to_year(s):
#     """
#     Try to convert season like "2021/22", "2021-22", "22/23", "2022" -> int year (use the later year).
#     Return None if not parsable.
#     """
#     try:
#         if s is None:
#             return None
#         s = str(s)
#         parts = re.findall(r"\d{2,4}", s)
#         if not parts:
#             try:
#                 v = int(float(s))
#                 return v
#             except Exception:
#                 return None
#         y = parts[-1]
#         if len(y) == 2:
#             return 2000 + int(y)
#         return int(y)
#     except Exception:
#         return None

# # ------- aggregate_player_stat (robust; default 5 seasons) -------
# def aggregate_player_stat(
#     player_name: str,
#     stat: str = "playing_time_starts",
#     seasons_back: int = DEFAULT_SEASONS_BACK,
#     player_col: str = "player",
#     season_col: str = "season",
# ) -> Dict[str, Any]:
#     df = _load_meta_df().copy()
#     if season_col not in df.columns:
#         raise RuntimeError(f"Season column '{season_col}' not found in CSV")

#     df["_season_year"] = df[season_col].apply(season_to_year)
#     df["_player_lc"] = df[player_col].astype(str).str.strip().str.lower()
#     mask = df["_player_lc"] == player_name.strip().lower()

#     player_rows_years = df[mask & df["_season_year"].notna()].copy()
#     if not player_rows_years.empty:
#         latest = int(player_rows_years["_season_year"].max())
#         requested_years = [latest - i for i in range(seasons_back)][::-1]
#         if stat not in player_rows_years.columns:
#             per_season = [{"season_year": y, "value": None} for y in requested_years]
#             return {
#                 "found": True,
#                 "player": player_rows_years[player_col].iloc[0],
#                 "latest_season": latest,
#                 "requested_seasons": requested_years,
#                 "per_season": per_season,
#                 "total": None,
#                 "has_consecutive_n": False,
#                 "note": f"stat '{stat}' not found",
#             }
#         agg = player_rows_years.groupby("_season_year")[stat].sum(min_count=1).to_dict()
#         per_season = []
#         total = 0.0
#         has_all = True
#         for y in requested_years:
#             v = agg.get(y)
#             if v is None or (isinstance(v, float) and math.isnan(v)):
#                 per_season.append({"season_year": int(y), "value": None})
#                 has_all = False
#             else:
#                 per_season.append({"season_year": int(y), "value": float(v)})
#                 total += float(v)
#         return {
#             "found": True,
#             "player": player_rows_years[player_col].iloc[0],
#             "latest_season": latest,
#             "requested_seasons": requested_years,
#             "per_season": per_season,
#             "total": total if has_all else None,
#             "has_consecutive_n": has_all,
#         }

#     # FALLBACK: no parseable numeric years -> use labels by dataset order (preserve order)
#     player_rows = df[mask].copy()
#     if player_rows.empty:
#         return {"found": False, "message": "player not found or no season data"}

#     labels = list(pd.Series(player_rows[season_col].astype(str)).dropna().unique())
#     if not labels:
#         return {
#             "found": True,
#             "player": player_rows[player_col].iloc[0],
#             "requested_seasons": [],
#             "per_season": [],
#             "total": None,
#             "has_consecutive_n": False,
#             "note": "no season labels available",
#         }
#     chosen = labels[-seasons_back:]
#     if stat not in player_rows.columns:
#         per_season = [{"season_label": s, "value": None} for s in chosen]
#         return {
#             "found": True,
#             "player": player_rows[player_col].iloc[0],
#             "requested_seasons": chosen,
#             "per_season": per_season,
#             "total": None,
#             "has_consecutive_n": False,
#             "note": f"stat '{stat}' not found (fallback to labels)",
#         }
#     agg_label = player_rows.groupby(season_col)[stat].sum(min_count=1).to_dict()
#     per_season = []
#     total = 0.0
#     has_all = True
#     for s in chosen:
#         v = agg_label.get(s)
#         if v is None or (isinstance(v, float) and math.isnan(v)):
#             per_season.append({"season_label": s, "value": None})
#             has_all = False
#         else:
#             per_season.append({"season_label": s, "value": float(v)})
#             total += float(v)
#     return {
#         "found": True,
#         "player": player_rows[player_col].iloc[0],
#         "requested_seasons": chosen,
#         "per_season": per_season,
#         "total": total if has_all else None,
#         "has_consecutive_n": has_all,
#     }

# # ------- plot_player (robust, returns safe dates and image) -------
# def plot_player(
#     player_name: str, metrics: List[str] = None, player_col: str = "player", season_col: str = "season"
# ) -> Dict[str, Any]:
#     if metrics is None:
#         metrics = ["playing_time_starts"]
#     df = _load_meta_df().copy()

#     if season_col not in df.columns:
#         df["_season_year"] = None
#     else:
#         df["_season_year"] = df[season_col].apply(season_to_year)

#     sel = df[df[player_col].astype(str).str.lower() == player_name.strip().lower()].copy()
#     if sel.empty:
#         candidates = df[df[player_col].astype(str).str.contains(player_name, case=False, na=False)][player_col].unique().tolist()[:8]
#         return {"found": False, "message": "player not found", "player": player_name, "candidates": candidates}

#     use_years = sel["_season_year"].notna().any()
#     if use_years:
#         sel = sel.sort_values("_season_year")
#         dates = [int(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None for x in sel["_season_year"].tolist()]
#         labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(d) for d in dates]
#     else:
#         sel = sel.sort_index()
#         labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(i) for i in range(len(sel))]
#         dates = labels

#     series = {}
#     for m in metrics:
#         if m not in sel.columns:
#             series[m] = [None for _ in dates]
#         else:
#             vals = pd.to_numeric(sel[m], errors="coerce").tolist()
#             series[m] = [None if (isinstance(v, float) and math.isnan(v)) else float(v) for v in vals]

#     n_rows = len(dates)
#     keep_mask = []
#     for i in range(n_rows):
#         row_has_value = any((series[m][i] is not None) for m in metrics)
#         keep_mask.append(row_has_value)

#     if not any(keep_mask):
#         return {"found": True, "player": player_name, "points": {"dates": dates, "series": series}, "image_b64": None, "error": "no_numeric_points_for_metrics"}

#     filtered_dates = [d for d, k in zip(dates, keep_mask) if k]
#     filtered_series = {m: [v for v, k in zip(series[m], keep_mask) if k] for m in metrics}

#     try:
#         import matplotlib
#         matplotlib.use("Agg")
#         import matplotlib.pyplot as plt

#         fig, ax = plt.subplots(figsize=(9, 4))
#         if use_years and any((isinstance(d, int) or (isinstance(d, float) and not math.isnan(d)) for d in filtered_dates)):
#             x = [int(d) if (d is not None) else None for d in filtered_dates]
#             if any(v is None for v in x):
#                 x = list(range(len(filtered_dates)))
#                 for m in metrics:
#                     ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
#                 ax.set_xticks(x)
#                 ax.set_xticklabels([str(d) for d in filtered_dates], rotation=30)
#             else:
#                 for m in metrics:
#                     ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
#                 ax.set_xticks(x)
#         else:
#             x = list(range(len(filtered_dates)))
#             for m in metrics:
#                 ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
#             ax.set_xticks(x)
#             ax.set_xticklabels([str(d) for d in filtered_dates], rotation=30)

#         ax.set_title(f"{player_name} - {' & '.join(metrics)}")
#         ax.set_xlabel("Season")
#         ax.set_ylabel("Value")
#         ax.grid(True)
#         if any(len(filtered_series.get(m, [])) > 0 for m in metrics):
#             ax.legend()
#         fig.tight_layout()
#         buf = io.BytesIO()
#         fig.savefig(buf, format="png", dpi=150)
#         buf.seek(0)
#         img_b64 = base64.b64encode(buf.read()).decode("ascii")
#         plt.close(fig)
#     except Exception as e:
#         return {"found": True, "player": player_name, "points": {"dates": filtered_dates, "series": filtered_series}, "image_b64": None, "error": str(e)}

#     return {"found": True, "player": player_name, "image_b64": img_b64, "points": {"dates": filtered_dates, "series": filtered_series}}

# # ---------------- NEW group helpers ----------------

# def candidate_metrics_from_df(df: pd.DataFrame) -> List[str]:
#     prefer = [
#         "goals_per_90", "xg_per_90", "npxg_per_90", "assists_per_90", "shots_per_90",
#         "xg", "npxg", "goals", "assists", "minutes"
#     ]
#     available = [c for c in prefer if c in df.columns]
#     if not available:
#         nums = df.select_dtypes(include=["number"]).columns.tolist()
#         available = nums[:5]
#     return available

# def filter_players(team: Optional[str] = None, position: Optional[str] = None,
#                    seasons_back: int = DEFAULT_SEASONS_BACK, player_col: str = "player",
#                    team_cols_candidates: List[str] = None, pos_col_candidates: List[str] = None) -> Dict[str, Any]:
#     df = _load_meta_df().copy()
#     if team_cols_candidates is None:
#         team_cols_candidates = [c for c in df.columns if "team" in c.lower() or "club" in c.lower()]
#     if pos_col_candidates is None:
#         pos_col_candidates = [c for c in df.columns if "pos" in c.lower() or "position" in c.lower()]

#     mask = pd.Series(True, index=df.index)
#     if team:
#         found_team_col = False
#         for tc in team_cols_candidates:
#             if tc in df.columns:
#                 found_team_col = True
#                 mask = mask & df[tc].astype(str).str.contains(team, case=False, na=False)
#         if not found_team_col:
#             mask = mask & (df["rag_summary"].astype(str).str.contains(team, case=False, na=False) | df[player_col].astype(str).str.contains(team, case=False, na=False))

#     if position:
#         pos_mask = pd.Series(False, index=df.index)
#         for pc in pos_col_candidates:
#             if pc in df.columns:
#                 pos_mask = pos_mask | df[pc].astype(str).str.contains(position, case=False, na=False)
#         if not pos_mask.any() and "rag_summary" in df.columns:
#             pos_mask = df["rag_summary"].astype(str).str.contains(position, case=False, na=False)
#         mask = mask & pos_mask

#     if "season" in df.columns:
#         df["_season_year"] = df["season"].apply(season_to_year)
#         if df["_season_year"].notna().any():
#             latest = int(df["_season_year"].max())
#             valid_years = [latest - i for i in range(seasons_back)]
#             mask = mask & df["_season_year"].isin(valid_years)

#     candidates = df[mask][player_col].dropna().astype(str).unique().tolist()
#     return {"ok": True, "players": candidates[:500], "count": len(candidates)}

# def aggregate_group_stats(players: List[str], stat: str = "goals", seasons_back: int = DEFAULT_SEASONS_BACK,
#                           player_col: str = "player", season_col: str = "season") -> Dict[str, Any]:
#     df = _load_meta_df().copy()
#     if season_col in df.columns:
#         df["_season_year"] = df[season_col].apply(season_to_year)
#         latest_years = sorted(df["_season_year"].dropna().unique())[::-1]
#     else:
#         df["_season_year"] = None
#         latest_years = []

#     if latest_years:
#         years = [latest_years[0] - i for i in range(seasons_back)][::-1]
#     else:
#         labels = list(pd.Series(df[season_col].astype(str)).dropna().unique()) if season_col in df.columns else []
#         years = labels[-seasons_back:] if labels else []

#     totals = {y: 0.0 for y in years}
#     per_player = {}
#     for p in players:
#         sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
#         if sel.empty:
#             per_player[p] = {"found": False}
#             continue
#         if season_col in sel.columns:
#             sel["_season_year"] = sel[season_col].apply(season_to_year)
#         by_year = {}
#         for y in years:
#             if stat not in sel.columns:
#                 v = None
#             else:
#                 if isinstance(y, int):
#                     v = pd.to_numeric(sel.loc[sel["_season_year"] == y, stat], errors="coerce").sum(min_count=1)
#                 else:
#                     v = pd.to_numeric(sel.loc[sel[season_col] == y, stat], errors="coerce").sum(min_count=1)
#                 v = None if pd.isna(v) else float(v)
#             by_year[y] = v
#             if v is not None:
#                 totals[y] += float(v)
#         per_player[p] = {"found": True, "per_season": by_year}
#     return {"ok": True, "players": players, "requested_seasons": years, "per_player": per_player, "totals": totals}

# def plot_group(players: List[str], metrics: List[str] = None, seasons_back: int = DEFAULT_SEASONS_BACK,
#                player_col: str = "player", season_col: str = "season") -> Dict[str, Any]:
#     df = _load_meta_df().copy()
#     if season_col in df.columns:
#         df["_season_year"] = df[season_col].apply(season_to_year)
#     else:
#         df["_season_year"] = None

#     if metrics is None or not metrics:
#         metrics = candidate_metrics_from_df(df)[:3] or ["goals_per_90", "xg_per_90"]

#     if df["_season_year"].notna().any():
#         all_years = sorted(df["_season_year"].dropna().unique())[::-1]
#         chosen_years = all_years[:seasons_back][::-1] if all_years else []
#     else:
#         labels = list(pd.Series(df[season_col].astype(str)).dropna().unique()) if season_col in df.columns else []
#         chosen_years = labels[-seasons_back:] if labels else []

#     series_table = {}
#     for p in players:
#         sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
#         if sel.empty:
#             series_table[p] = {"found": False}
#             continue
#         if season_col in sel.columns:
#             sel["_season_year"] = sel[season_col].apply(season_to_year)
#         sel = sel.sort_values("_season_year") if "_season_year" in sel.columns else sel.sort_index()
#         primary = metrics[0]
#         series_vals = []
#         for y in chosen_years:
#             if primary in sel.columns:
#                 if isinstance(y, int):
#                     v = pd.to_numeric(sel.loc[sel["_season_year"] == y, primary], errors="coerce").sum(min_count=1)
#                 else:
#                     v = pd.to_numeric(sel.loc[sel[season_col] == y, primary], errors="coerce").sum(min_count=1)
#                 v = None if pd.isna(v) else float(v)
#             else:
#                 v = None
#             series_vals.append(v)
#         series_table[p] = {"found": True, "series": series_vals}

#     latest = chosen_years[-1] if chosen_years else None
#     percentiles = {}
#     import numpy as np
#     for m in metrics:
#         if m in df.columns:
#             col_vals = pd.to_numeric(df[m], errors="coerce").dropna().values
#         else:
#             col_vals = np.array([])
#         for p in players:
#             if not series_table.get(p, {}).get("found"):
#                 percentiles.setdefault(p, {})[m] = None
#                 continue
#             sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
#             if latest is not None and "_season_year" in sel.columns and isinstance(latest, int):
#                 if m in sel.columns:
#                     row_val = pd.to_numeric(sel.loc[sel["_season_year"] == latest, m], errors="coerce").sum(min_count=1)
#                 else:
#                     row_val = None
#             else:
#                 if m in sel.columns and not sel[m].dropna().empty:
#                     row_val = pd.to_numeric(sel[m].dropna().iloc[-1], errors="coerce")
#                 else:
#                     row_val = None
#             if row_val is None or (isinstance(row_val, float) and np.isnan(row_val)) or len(col_vals) == 0:
#                 percentiles.setdefault(p, {})[m] = None
#             else:
#                 percentiles.setdefault(p, {})[m] = float((col_vals <= float(row_val)).sum()) / float(len(col_vals)) * 100.0

#     try:
#         import matplotlib
#         matplotlib.use("Agg")
#         import matplotlib.pyplot as plt

#         fig = plt.figure(figsize=(12, 6))
#         ax1 = fig.add_subplot(1, 2, 1)
#         if chosen_years:
#             x = list(range(len(chosen_years)))
#             for p in players:
#                 if not series_table.get(p, {}).get("found"):
#                     continue
#                 ax1.plot(x, series_table[p]["series"], marker="o", label=p)
#             ax1.set_xticks(x)
#             ax1.set_xticklabels([str(y) for y in chosen_years], rotation=30)
#         else:
#             for p in players:
#                 if not series_table.get(p, {}).get("found"):
#                     continue
#                 vals = series_table[p]["series"]
#                 ax1.plot(list(range(len(vals))), vals, marker="o", label=p)
#         ax1.set_title(f"Group time-series ({metrics[0]})")
#         ax1.grid(True)
#         ax1.legend(fontsize="small")

#         ax2 = fig.add_subplot(1, 2, 2, polar=True)
#         theta = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
#         for p in players:
#             if not percentiles.get(p):
#                 continue
#             vals = [percentiles[p].get(m, 0.0) or 0.0 for m in metrics]
#             vals_closed = vals + [vals[0]]
#             theta_closed = np.concatenate((theta, [theta[0]]))
#             ax2.plot(theta_closed, vals_closed, marker="o", label=p)
#             ax2.fill(theta_closed, vals_closed, alpha=0.12)
#         ax2.set_xticks(theta)
#         ax2.set_xticklabels(metrics, fontsize=9)
#         ax2.set_yticks([20, 40, 60, 80, 100])
#         ax2.set_ylim(0, 100)
#         ax2.set_title("Latest-season percentiles (0-100)")
#         ax2.legend(loc="upper right", bbox_to_anchor=(1.4, 1.05), fontsize="small")

#         fig.tight_layout()
#         buf = io.BytesIO()
#         fig.savefig(buf, format="png", dpi=150)
#         buf.seek(0)
#         img_b64 = base64.b64encode(buf.read()).decode("ascii")
#         plt.close(fig)
#     except Exception as e:
#         return {"ok": False, "error": "plot_error", "detail": str(e), "players": players, "chosen_seasons": chosen_years, "series_table": series_table, "percentiles": percentiles}

#     return {"ok": True, "players": players, "chosen_seasons": chosen_years, "image_b64": img_b64, "series_table": series_table, "percentiles": percentiles}

# mcp/tools.py - COMPLETE VERSION WITH FLEXIBLE MATCHING
import os
import pickle
import math
import re
import base64
import io
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

load_dotenv()

# Configuration
DATA_CSV = os.getenv("DATA_PATH", "./data/FINAL_with_rag.csv")
VECTOR_DIR = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
EMB_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
K_DEFAULT = int(os.getenv("K_DEFAULT", "5"))
DEFAULT_SEASONS_BACK = int(os.getenv("DEFAULT_SEASONS_BACK", "5"))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _ensure_openai():
    """Lazy load OpenAI client."""
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_KEY)
    except Exception as e:
        raise ImportError("Install openai>=1.0.0 and set OPENAI_API_KEY in .env. Err: " + str(e))

def _ensure_faiss():
    """Lazy load FAISS library."""
    try:
        import faiss
        return faiss
    except Exception as e:
        raise ImportError("Install faiss-cpu (pip install faiss-cpu). Err: " + str(e))

def _load_meta_df():
    """Load the main CSV data file."""
    if not os.path.exists(DATA_CSV):
        raise RuntimeError(f"CSV not found at {DATA_CSV}")
    df = pd.read_csv(DATA_CSV)
    if "rag_summary" in df.columns:
        df["rag_summary"] = df["rag_summary"].astype(str).fillna("")
    return df

def _load_index_and_meta():
    """Load FAISS index and metadata for semantic search."""
    faiss = _ensure_faiss()
    idx_path = os.path.join(VECTOR_DIR, "index.faiss")
    meta_path = os.path.join(VECTOR_DIR, "metadata.pkl")
    if not os.path.exists(idx_path) or not os.path.exists(meta_path):
        raise RuntimeError("FAISS index or metadata not found. Run scripts/batch_embed.py first.")
    index = faiss.read_index(idx_path)
    with open(meta_path, "rb") as f:
        df = pickle.load(f)
    return faiss, index, df

def season_to_year(s):
    """
    Convert season string to year integer.
    Examples: "2021/22" -> 2022, "2021-22" -> 2022, "22/23" -> 2023, "2022" -> 2022
    Returns the LATER year from ranges (for matching "2022" to "2021-22" season).
    """
    try:
        if s is None:
            return None
        s = str(s)
        parts = re.findall(r"\d{2,4}", s)
        if not parts:
            try:
                v = int(float(s))
                return v
            except Exception:
                return None
        # Take the last number found (the ending year)
        y = parts[-1]
        if len(y) == 2:
            return 2000 + int(y)
        return int(y)
    except Exception:
        return None

def _flexible_player_match(df: pd.DataFrame, player_name: str, player_col: str = "player") -> pd.Series:
    """
    CRITICAL FIX: Flexible player name matching.
    
    Tries in order:
    1. Exact match (case-insensitive): "lionel messi" == "lionel messi"
    2. Partial match (contains): "lionel messi" contains "messi"
    3. Token match: all tokens in query present in player name
    
    Returns: Boolean Series (mask)
    """
    if "_player_lc" not in df.columns:
        df["_player_lc"] = df[player_col].astype(str).str.strip().str.lower()
    
    player_name_lc = player_name.strip().lower()
    
    # 1. Exact match
    mask = df["_player_lc"] == player_name_lc
    
    # 2. Partial match (contains)
    if not mask.any():
        mask = df["_player_lc"].str.contains(player_name_lc, na=False, regex=False)
    
    # 3. Token match (all query tokens present in name)
    if not mask.any():
        tokens = player_name_lc.split()
        if tokens:
            mask = df["_player_lc"].apply(
                lambda x: all(token in str(x) for token in tokens)
            )
    
    return mask

def _get_canonical_player_name(df: pd.DataFrame, player_name: str, player_col: str = "player") -> Optional[str]:
    """Get the canonical (full) player name from the dataset."""
    mask = _flexible_player_match(df, player_name, player_col)
    matches = df[mask]
    if matches.empty:
        return None
    return matches[player_col].iloc[0]

def candidate_metrics_from_df(df: pd.DataFrame) -> List[str]:
    """Get sensible default metrics from the dataframe."""
    prefer = [
        "goals_per_90", "xg_per_90", "npxg_per_90", "assists_per_90", "shots_per_90",
        "xg", "npxg", "goals", "assists", "minutes", "playing_time_starts"
    ]
    available = [c for c in prefer if c in df.columns]
    if not available:
        nums = df.select_dtypes(include=["number"]).columns.tolist()
        available = nums[:5]
    return available

# ============================================================================
# CORE TOOLS
# ============================================================================

def get_schema() -> List[str]:
    """
    Get the available columns in the dataset.
    Used by agents to understand what metrics are available.
    """
    if not os.path.exists(DATA_CSV):
        return []
    try:
        df = pd.read_csv(DATA_CSV, nrows=1)
        return list(df.columns)
    except Exception:
        return []

def search_player(query: str, k: int = K_DEFAULT) -> List[Dict[str, Any]]:
    """
    Semantic search for players using FAISS embeddings.
    Falls back to simple text search if embeddings unavailable.
    
    Returns: List of dicts with keys: score, idx, player, season, rag_summary
    """
    if not query:
        return []
    
    try:
        client = _ensure_openai()
        faiss = _ensure_faiss()
        _, index, df = _load_index_and_meta()
        
        # Generate embedding for query
        resp = client.embeddings.create(model=EMB_MODEL, input=[query])
        emb = resp.data[0]["embedding"] if isinstance(resp.data[0], dict) else getattr(resp.data[0], "embedding")
        
        # Search FAISS index
        vec = np.array(emb, dtype="float32").reshape(1, -1)
        faiss.normalize_L2(vec)
        D, I = index.search(vec, k)
        
        results = []
        query_lower = query.strip().lower()

        for score, idx in zip(D[0].tolist(), I[0].tolist()):
            if idx < 0:
                continue
            row = df.iloc[idx]
            player_name = str(row.get("player") or "")
            player_name_lower = player_name.strip().lower()

            # CRITICAL FIX: Boost score for exact/partial player name matches
            # FAISS returns cosine similarity (0-1 range, higher is better)
            boosted_score = float(score)

            # Exact match: set to maximum score
            if player_name_lower == query_lower:
                boosted_score = 1.0
            # Contains match: boost significantly
            elif query_lower in player_name_lower:
                boosted_score = max(boosted_score, 0.9)
            # Token match: all query tokens in player name
            elif all(token in player_name_lower for token in query_lower.split()):
                boosted_score = max(boosted_score, 0.85)
            # Partial token overlap
            else:
                query_tokens = set(query_lower.split())
                player_tokens = set(player_name_lower.split())
                overlap = len(query_tokens & player_tokens)
                if overlap > 0:
                    # Boost based on token overlap ratio
                    overlap_ratio = overlap / len(query_tokens)
                    if overlap_ratio > 0.5:  # More than half tokens match
                        boosted_score = max(boosted_score, 0.7 + (overlap_ratio * 0.2))

            results.append({
                "score": boosted_score,
                "idx": int(idx),
                "player": player_name,
                "season": row.get("season"),
                "rag_summary": str(row.get("rag_summary"))[:1000],
            })

        # Re-sort by boosted scores
        results.sort(key=lambda x: -x["score"])
        return results
        
    except Exception as e:
        # Fallback: simple text search with smart scoring
        try:
            df = _load_meta_df()
            matches = []
            query_lower = str(query).strip().lower()
            query_tokens = set(query_lower.split())

            for i, row in df.iterrows():
                player_name = str(row.get("player", ""))
                player_name_lower = player_name.strip().lower()
                rag_summary = str(row.get("rag_summary", ""))

                # Smart scoring - same logic as FAISS
                score = 0.0

                # Exact player name match
                if player_name_lower == query_lower:
                    score = 1.0
                # Contains match in player name
                elif query_lower in player_name_lower:
                    score = 0.9
                # All query tokens in player name
                elif all(token in player_name_lower for token in query_lower.split()):
                    score = 0.85
                # Partial token overlap in player name
                else:
                    player_tokens = set(player_name_lower.split())
                    overlap = len(query_tokens & player_tokens)
                    if overlap > 0:
                        overlap_ratio = overlap / len(query_tokens)
                        if overlap_ratio > 0.5:
                            score = 0.7 + (overlap_ratio * 0.2)

                # If not found in player name, check rag_summary (lower priority)
                if score == 0.0 and query_lower in rag_summary.lower():
                    score = 0.3

                if score > 0:
                    matches.append({
                        "score": float(score),
                        "idx": int(i),
                        "player": player_name,
                        "season": row.get("season"),
                        "rag_summary": rag_summary[:1000]
                    })

            return sorted(matches, key=lambda r: r["score"], reverse=True)[:k]
        except Exception as e2:
            raise RuntimeError("Search unavailable: " + str(e2))

def aggregate_player_stat(
    player_name: str,
    stat: str = "playing_time_starts",
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season",
) -> Dict[str, Any]:
    """
    Aggregate a statistic for a player over multiple seasons.
    NOW WITH FLEXIBLE NAME MATCHING!
    
    Returns dict with:
    - found: bool
    - player: canonical player name
    - stat: the statistic name
    - latest_season: most recent season year
    - requested_seasons: list of years/labels
    - per_season: list of {season_year/season_label: int, value: float}
    - total: sum if all seasons have data
    - has_consecutive_n: bool, whether all requested seasons have data
    """
    df = _load_meta_df().copy()
    
    if season_col not in df.columns:
        raise RuntimeError(f"Season column '{season_col}' not found in CSV")

    df["_season_year"] = df[season_col].apply(season_to_year)
    
    # CRITICAL FIX: Use flexible matching
    mask = _flexible_player_match(df, player_name, player_col)
    player_rows_years = df[mask & df["_season_year"].notna()].copy()
    
    if not player_rows_years.empty:
        latest = int(player_rows_years["_season_year"].max())
        requested_years = [latest - i for i in range(seasons_back)][::-1]
        
        # Get canonical player name
        canonical_player_name = player_rows_years[player_col].iloc[0]
        
        if stat not in player_rows_years.columns:
            per_season = [{"season_year": y, "value": None} for y in requested_years]
            return {
                "found": True,
                "player": canonical_player_name,
                "stat": stat,
                "latest_season": latest,
                "requested_seasons": requested_years,
                "per_season": per_season,
                "total": None,
                "has_consecutive_n": False,
                "note": f"stat '{stat}' not found in columns",
            }
        
        # Aggregate by season year
        agg = player_rows_years.groupby("_season_year")[stat].sum(min_count=1).to_dict()
        per_season = []
        total = 0.0
        has_all = True
        
        for y in requested_years:
            v = agg.get(y)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                per_season.append({"season_year": int(y), "value": None})
                has_all = False
            else:
                per_season.append({"season_year": int(y), "value": float(v)})
                total += float(v)
        
        return {
            "found": True,
            "player": canonical_player_name,
            "stat": stat,
            "latest_season": latest,
            "requested_seasons": requested_years,
            "per_season": per_season,
            "total": total if has_all else None,
            "has_consecutive_n": has_all,
        }

    # FALLBACK: No parseable numeric years, use season labels
    player_rows = df[mask].copy()
    if player_rows.empty:
        return {
            "found": False,
            "message": f"player '{player_name}' not found",
            "query": player_name
        }

    labels = list(pd.Series(player_rows[season_col].astype(str)).dropna().unique())
    if not labels:
        return {
            "found": True,
            "player": player_rows[player_col].iloc[0],
            "stat": stat,
            "requested_seasons": [],
            "per_season": [],
            "total": None,
            "has_consecutive_n": False,
            "note": "no season labels available",
        }
    
    canonical_player_name = player_rows[player_col].iloc[0]
    chosen = labels[-seasons_back:]
    
    if stat not in player_rows.columns:
        per_season = [{"season_label": s, "value": None} for s in chosen]
        return {
            "found": True,
            "player": canonical_player_name,
            "stat": stat,
            "requested_seasons": chosen,
            "per_season": per_season,
            "total": None,
            "has_consecutive_n": False,
            "note": f"stat '{stat}' not found (fallback to labels)",
        }
    
    agg_label = player_rows.groupby(season_col)[stat].sum(min_count=1).to_dict()
    per_season = []
    total = 0.0
    has_all = True
    
    for s in chosen:
        v = agg_label.get(s)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            per_season.append({"season_label": s, "value": None})
            has_all = False
        else:
            per_season.append({"season_label": s, "value": float(v)})
            total += float(v)
    
    return {
        "found": True,
        "player": canonical_player_name,
        "stat": stat,
        "requested_seasons": chosen,
        "per_season": per_season,
        "total": total if has_all else None,
        "has_consecutive_n": has_all,
    }

def plot_player(
    player_name: str,
    metrics: List[str] = None,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Plot metrics for a player over time.
    NOW WITH FLEXIBLE NAME MATCHING!
    
    Returns dict with:
    - found: bool
    - player: canonical name
    - image_b64: base64 encoded PNG
    - points: dict with dates and series data
    """
    if metrics is None:
        metrics = ["playing_time_starts"]
    
    df = _load_meta_df().copy()

    if season_col not in df.columns:
        df["_season_year"] = None
    else:
        df["_season_year"] = df[season_col].apply(season_to_year)

    # CRITICAL FIX: Use flexible matching
    mask = _flexible_player_match(df, player_name, player_col)
    sel = df[mask].copy()
    
    if sel.empty:
        # Try to find similar names for suggestions
        candidates = df[df[player_col].astype(str).str.contains(player_name, case=False, na=False)][player_col].unique().tolist()[:8]
        return {
            "found": False,
            "message": "player not found",
            "player": player_name,
            "candidates": candidates
        }

    # Get canonical name
    canonical_name = sel[player_col].iloc[0]
    
    use_years = sel["_season_year"].notna().any()
    if use_years:
        sel = sel.sort_values("_season_year")
        dates = [int(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None for x in sel["_season_year"].tolist()]
        labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(d) for d in dates]
    else:
        sel = sel.sort_index()
        labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(i) for i in range(len(sel))]
        dates = labels

    # Extract series data
    series = {}
    for m in metrics:
        if m not in sel.columns:
            series[m] = [None for _ in dates]
        else:
            vals = pd.to_numeric(sel[m], errors="coerce").tolist()
            series[m] = [None if (isinstance(v, float) and math.isnan(v)) else float(v) for v in vals]

    # Filter out rows with no data
    n_rows = len(dates)
    keep_mask = []
    for i in range(n_rows):
        row_has_value = any((series[m][i] is not None) for m in metrics)
        keep_mask.append(row_has_value)

    if not any(keep_mask):
        return {
            "found": True,
            "player": canonical_name,
            "points": {"dates": dates, "series": series},
            "image_b64": None,
            "error": "no_numeric_points_for_metrics"
        }

    filtered_dates = [d for d, k in zip(dates, keep_mask) if k]
    filtered_series = {m: [v for v, k in zip(series[m], keep_mask) if k] for m in metrics}

    # Create plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 4))
        
        if use_years and any((isinstance(d, int) or (isinstance(d, float) and not math.isnan(d)) for d in filtered_dates)):
            x = [int(d) if (d is not None) else None for d in filtered_dates]
            if any(v is None for v in x):
                x = list(range(len(filtered_dates)))
                for m in metrics:
                    ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
                ax.set_xticks(x)
                ax.set_xticklabels([str(d) for d in filtered_dates], rotation=30)
            else:
                for m in metrics:
                    ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
                ax.set_xticks(x)
        else:
            x = list(range(len(filtered_dates)))
            for m in metrics:
                ax.plot(x, filtered_series.get(m, []), marker="o", label=str(m))
            ax.set_xticks(x)
            ax.set_xticklabels([str(d) for d in filtered_dates], rotation=30)

        ax.set_title(f"{canonical_name} - {' & '.join(metrics)}")
        ax.set_xlabel("Season")
        ax.set_ylabel("Value")
        ax.grid(True)
        
        if any(len(filtered_series.get(m, [])) > 0 for m in metrics):
            ax.legend()
        
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode("ascii")
        plt.close(fig)
        
    except Exception as e:
        return {
            "found": True,
            "player": canonical_name,
            "points": {"dates": filtered_dates, "series": filtered_series},
            "image_b64": None,
            "error": str(e)
        }

    return {
        "found": True,
        "player": canonical_name,
        "image_b64": img_b64,
        "points": {"dates": filtered_dates, "series": filtered_series}
    }

def compare_players(
    players: List[str],
    stat: str = "goals",
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Compare multiple players on a single statistic.
    NOW WITH FLEXIBLE NAME MATCHING!
    
    Returns dict with per-player aggregated stats.
    """
    df = _load_meta_df().copy()
    df["_season_year"] = df[season_col].apply(season_to_year) if season_col in df.columns else None
    
    results = {}
    for player_name in players:
        # Use aggregate_player_stat which already has flexible matching
        result = aggregate_player_stat(player_name, stat, seasons_back, player_col, season_col)
        results[player_name] = result
    
    return {
        "ok": True,
        "stat": stat,
        "seasons_back": seasons_back,
        "players": results
    }

def filter_players(
    team: Optional[str] = None,
    position: Optional[str] = None,
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    team_cols_candidates: List[str] = None,
    pos_col_candidates: List[str] = None
) -> Dict[str, Any]:
    """
    Filter players by team and/or position.
    
    Returns dict with:
    - ok: bool
    - players: list of player names
    - count: number of players found
    """
    df = _load_meta_df().copy()
    
    if team_cols_candidates is None:
        team_cols_candidates = [c for c in df.columns if "team" in c.lower() or "club" in c.lower() or "squad" in c.lower()]
    if pos_col_candidates is None:
        pos_col_candidates = [c for c in df.columns if "pos" in c.lower() or "position" in c.lower()]

    mask = pd.Series(True, index=df.index)
    
    # Filter by team
    if team:
        found_team_col = False
        for tc in team_cols_candidates:
            if tc in df.columns:
                found_team_col = True
                mask = mask & df[tc].astype(str).str.contains(team, case=False, na=False)
        if not found_team_col and "rag_summary" in df.columns:
            mask = mask & (
                df["rag_summary"].astype(str).str.contains(team, case=False, na=False) |
                df[player_col].astype(str).str.contains(team, case=False, na=False)
            )

    # Filter by position
    if position:
        pos_mask = pd.Series(False, index=df.index)
        for pc in pos_col_candidates:
            if pc in df.columns:
                pos_mask = pos_mask | df[pc].astype(str).str.contains(position, case=False, na=False)
        if not pos_mask.any() and "rag_summary" in df.columns:
            pos_mask = df["rag_summary"].astype(str).str.contains(position, case=False, na=False)
        mask = mask & pos_mask

    # Filter by season recency
    if "season" in df.columns:
        df["_season_year"] = df["season"].apply(season_to_year)
        if df["_season_year"].notna().any():
            latest = int(df["_season_year"].max())
            valid_years = [latest - i for i in range(seasons_back)]
            mask = mask & df["_season_year"].isin(valid_years)

    candidates = df[mask][player_col].dropna().astype(str).unique().tolist()

    # Return all players - no arbitrary limit
    # Performance is acceptable even with full player list
    return {
        "ok": True,
        "players": candidates,
        "count": len(candidates),
        "limited": False
    }

def aggregate_group_stats(
    players: List[str],
    stat: str = "goals",
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Aggregate statistics for a group of players.
    NOW WITH FLEXIBLE NAME MATCHING!
    
    Returns dict with per-player and total stats.
    """
    df = _load_meta_df().copy()
    
    if season_col in df.columns:
        df["_season_year"] = df[season_col].apply(season_to_year)
        latest_years = sorted(df["_season_year"].dropna().unique())[::-1]
    else:
        df["_season_year"] = None
        latest_years = []

    if latest_years:
        years = [latest_years[0] - i for i in range(seasons_back)][::-1]
    else:
        labels = list(pd.Series(df[season_col].astype(str)).dropna().unique()) if season_col in df.columns else []
        years = labels[-seasons_back:] if labels else []

    totals = {y: 0.0 for y in years}
    per_player = {}
    
    for player_name in players:
        # CRITICAL FIX: Use flexible matching
        mask = _flexible_player_match(df, player_name, player_col)
        sel = df[mask].copy()
        
        if sel.empty:
            per_player[player_name] = {"found": False}
            continue
        
        # Get canonical name
        canonical_name = sel[player_col].iloc[0]
        
        if season_col in sel.columns:
            sel["_season_year"] = sel[season_col].apply(season_to_year)
        
        by_year = {}
        for y in years:
            if stat not in sel.columns:
                v = None
            else:
                if isinstance(y, int):
                    v = pd.to_numeric(sel.loc[sel["_season_year"] == y, stat], errors="coerce").sum(min_count=1)
                else:
                    v = pd.to_numeric(sel.loc[sel[season_col] == y, stat], errors="coerce").sum(min_count=1)
                v = None if pd.isna(v) else float(v)
            by_year[y] = v
            if v is not None:
                totals[y] += float(v)
        
        per_player[canonical_name] = {"found": True, "per_season": by_year}
    
    return {
        "ok": True,
        "players": players,
        "requested_seasons": years,
        "per_player": per_player,
        "totals": totals
    }

def plot_group(
    players: List[str],
    metrics: List[str] = None,
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Plot group comparison with time-series and radar chart.
    NOW WITH FLEXIBLE NAME MATCHING!
    
    Returns dict with image_b64 and data tables.
    """
    df = _load_meta_df().copy()
    
    if season_col in df.columns:
        df["_season_year"] = df[season_col].apply(season_to_year)
    else:
        df["_season_year"] = None

    if metrics is None or not metrics:
        metrics = candidate_metrics_from_df(df)[:3] or ["goals_per_90", "xg_per_90"]

    if df["_season_year"].notna().any():
        all_years = sorted(df["_season_year"].dropna().unique())[::-1]
        chosen_years = all_years[:seasons_back][::-1] if all_years else []
    else:
        labels = list(pd.Series(df[season_col].astype(str)).dropna().unique()) if season_col in df.columns else []
        chosen_years = labels[-seasons_back:] if labels else []

    series_table = {}
    canonical_names = {}
    
    for player_name in players:
        # CRITICAL FIX: Use flexible matching
        mask = _flexible_player_match(df, player_name, player_col)
        sel = df[mask].copy()
        
        if sel.empty:
            series_table[player_name] = {"found": False}
            canonical_names[player_name] = player_name
            continue
        
        # Get canonical name
        canonical_name = sel[player_col].iloc[0]
        canonical_names[player_name] = canonical_name
        
        if season_col in sel.columns:
            sel["_season_year"] = sel[season_col].apply(season_to_year)
        sel = sel.sort_values("_season_year") if "_season_year" in sel.columns else sel.sort_index()
        
        primary = metrics[0]
        series_vals = []
        for y in chosen_years:
            if primary in sel.columns:
                if isinstance(y, int):
                    v = pd.to_numeric(sel.loc[sel["_season_year"] == y, primary], errors="coerce").sum(min_count=1)
                else:
                    v = pd.to_numeric(sel.loc[sel[season_col] == y, primary], errors="coerce").sum(min_count=1)
                v = None if pd.isna(v) else float(v)
            else:
                v = None
            series_vals.append(v)
        series_table[canonical_name] = {"found": True, "series": series_vals}

    latest = chosen_years[-1] if chosen_years else None
    percentiles = {}
    
    for m in metrics:
        if m in df.columns:
            col_vals = pd.to_numeric(df[m], errors="coerce").dropna().values
        else:
            col_vals = np.array([])
        
        for player_name in players:
            canonical_name = canonical_names.get(player_name, player_name)
            
            if not series_table.get(canonical_name, {}).get("found"):
                percentiles.setdefault(canonical_name, {})[m] = None
                continue
            
            mask = _flexible_player_match(df, player_name, player_col)
            sel = df[mask].copy()
            
            if latest is not None and "_season_year" in sel.columns and isinstance(latest, int):
                if m in sel.columns:
                    row_val = pd.to_numeric(sel.loc[sel["_season_year"] == latest, m], errors="coerce").sum(min_count=1)
                else:
                    row_val = None
            else:
                if m in sel.columns and not sel[m].dropna().empty:
                    row_val = pd.to_numeric(sel[m].dropna().iloc[-1], errors="coerce")
                else:
                    row_val = None
            
            if row_val is None or (isinstance(row_val, float) and np.isnan(row_val)) or len(col_vals) == 0:
                percentiles.setdefault(canonical_name, {})[m] = None
            else:
                percentiles.setdefault(canonical_name, {})[m] = float((col_vals <= float(row_val)).sum()) / float(len(col_vals)) * 100.0

    # Create visualization
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(12, 6))
        
        # Time series plot
        ax1 = fig.add_subplot(1, 2, 1)
        if chosen_years:
            x = list(range(len(chosen_years)))
            for player_name in players:
                canonical_name = canonical_names.get(player_name, player_name)
                if not series_table.get(canonical_name, {}).get("found"):
                    continue
                ax1.plot(x, series_table[canonical_name]["series"], marker="o", label=canonical_name)
            ax1.set_xticks(x)
            ax1.set_xticklabels([str(y) for y in chosen_years], rotation=30)
        else:
            for player_name in players:
                canonical_name = canonical_names.get(player_name, player_name)
                if not series_table.get(canonical_name, {}).get("found"):
                    continue
                vals = series_table[canonical_name]["series"]
                ax1.plot(list(range(len(vals))), vals, marker="o", label=canonical_name)
        
        ax1.set_title(f"Group time-series ({metrics[0]})")
        ax1.grid(True)
        ax1.legend(fontsize="small")

        # Radar plot
        ax2 = fig.add_subplot(1, 2, 2, polar=True)
        theta = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
        
        for player_name in players:
            canonical_name = canonical_names.get(player_name, player_name)
            if not percentiles.get(canonical_name):
                continue
            vals = [percentiles[canonical_name].get(m, 0.0) or 0.0 for m in metrics]
            vals_closed = vals + [vals[0]]
            theta_closed = np.concatenate((theta, [theta[0]]))
            ax2.plot(theta_closed, vals_closed, marker="o", label=canonical_name)
            ax2.fill(theta_closed, vals_closed, alpha=0.12)
        
        ax2.set_xticks(theta)
        ax2.set_xticklabels(metrics, fontsize=9)
        ax2.set_yticks([20, 40, 60, 80, 100])
        ax2.set_ylim(0, 100)
        ax2.set_title("Latest-season percentiles (0-100)")
        ax2.legend(loc="upper right", bbox_to_anchor=(1.4, 1.05), fontsize="small")

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode("ascii")
        plt.close(fig)
        
    except Exception as e:
        return {
            "ok": False,
            "error": "plot_error",
            "detail": str(e),
            "players": players,
            "chosen_seasons": chosen_years,
            "series_table": series_table,
            "percentiles": percentiles
        }

    return {
        "ok": True,
        "players": [canonical_names.get(p, p) for p in players],
        "chosen_seasons": chosen_years,
        "image_b64": img_b64,
        "series_table": series_table,
        "percentiles": percentiles
    }


# ============================================================================
# ADDITIONAL UTILITY FUNCTIONS
# ============================================================================

def get_player_info(
    player_name: str,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Get basic information about a player.
    Returns biographical info and recent stats.
    """
    df = _load_meta_df().copy()
    
    mask = _flexible_player_match(df, player_name, player_col)
    sel = df[mask].copy()
    
    if sel.empty:
        return {
            "found": False,
            "message": f"Player '{player_name}' not found"
        }
    
    canonical_name = sel[player_col].iloc[0]
    
    # Get most recent row
    if season_col in sel.columns:
        sel["_season_year"] = sel[season_col].apply(season_to_year)
        if sel["_season_year"].notna().any():
            latest_row = sel.loc[sel["_season_year"] == sel["_season_year"].max()].iloc[0]
        else:
            latest_row = sel.iloc[-1]
    else:
        latest_row = sel.iloc[-1]
    
    info = {
        "found": True,
        "player": canonical_name,
        "latest_season": latest_row.get(season_col) if season_col in latest_row else None,
    }
    
    # Add available biographical fields
    bio_fields = ["nation", "pos", "squad", "comp", "age_stats", "born"]
    for field in bio_fields:
        if field in latest_row and pd.notna(latest_row[field]):
            info[field] = latest_row[field]
    
    # Add rag_summary if available
    if "rag_summary" in latest_row and pd.notna(latest_row["rag_summary"]):
        info["summary"] = str(latest_row["rag_summary"])[:500]
    
    return info


def get_top_players(
    stat: str = "goals",
    n: int = 10,
    season: Optional[str] = None,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Get top N players by a statistic.
    Optionally filter by season.
    """
    df = _load_meta_df().copy()
    
    if stat not in df.columns:
        return {
            "ok": False,
            "error": f"Stat '{stat}' not found in dataset"
        }
    
    # Filter by season if specified
    if season and season_col in df.columns:
        df = df[df[season_col].astype(str).str.contains(str(season), na=False)]
    
    # Aggregate by player
    player_totals = df.groupby(player_col)[stat].sum().sort_values(ascending=False)
    
    top_players = []
    for player, value in player_totals.head(n).items():
        top_players.append({
            "player": player,
            stat: float(value) if not pd.isna(value) else None
        })
    
    return {
        "ok": True,
        "stat": stat,
        "season": season,
        "top_players": top_players
    }


def get_player_percentile(
    player_name: str,
    stat: str = "goals_per_90",
    season: Optional[str] = None,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Calculate a player's percentile rank for a statistic.
    """
    df = _load_meta_df().copy()
    
    if stat not in df.columns:
        return {
            "ok": False,
            "error": f"Stat '{stat}' not found in dataset"
        }
    
    # Filter by season if specified
    if season and season_col in df.columns:
        df = df[df[season_col].astype(str).str.contains(str(season), na=False)]
    
    # Get player's value
    mask = _flexible_player_match(df, player_name, player_col)
    player_rows = df[mask]
    
    if player_rows.empty:
        return {
            "ok": False,
            "error": f"Player '{player_name}' not found"
        }
    
    canonical_name = player_rows[player_col].iloc[0]
    player_value = pd.to_numeric(player_rows[stat], errors="coerce").mean()
    
    if pd.isna(player_value):
        return {
            "ok": False,
            "error": f"No data for {stat} for player {canonical_name}"
        }
    
    # Calculate percentile
    all_values = pd.to_numeric(df[stat], errors="coerce").dropna()
    percentile = float((all_values <= player_value).sum()) / float(len(all_values)) * 100.0
    
    return {
        "ok": True,
        "player": canonical_name,
        "stat": stat,
        "value": float(player_value),
        "percentile": float(percentile),
        "season": season,
        "sample_size": len(all_values)
    }


def get_similar_players(
    player_name: str,
    n: int = 5,
    metrics: List[str] = None,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    Find players with similar statistical profiles.
    Uses Euclidean distance in normalized metric space.
    """
    df = _load_meta_df().copy()
    
    if metrics is None:
        metrics = ["goals_per_90", "assists_per_90", "xg_per_90", "xag_per_90"]
    
    # Filter to metrics that exist
    metrics = [m for m in metrics if m in df.columns]
    if not metrics:
        return {
            "ok": False,
            "error": "None of the specified metrics exist in dataset"
        }
    
    # Get player's profile
    mask = _flexible_player_match(df, player_name, player_col)
    player_rows = df[mask]
    
    if player_rows.empty:
        return {
            "ok": False,
            "error": f"Player '{player_name}' not found"
        }
    
    canonical_name = player_rows[player_col].iloc[0]
    
    # Get most recent season data
    if season_col in player_rows.columns:
        player_rows["_season_year"] = player_rows[season_col].apply(season_to_year)
        if player_rows["_season_year"].notna().any():
            player_row = player_rows.loc[player_rows["_season_year"] == player_rows["_season_year"].max()].iloc[0]
        else:
            player_row = player_rows.iloc[-1]
    else:
        player_row = player_rows.iloc[-1]
    
    player_values = []
    for m in metrics:
        val = pd.to_numeric(player_row.get(m), errors="coerce")
        if pd.isna(val):
            player_values.append(0.0)
        else:
            player_values.append(float(val))
    
    player_vector = np.array(player_values)
    
    # Calculate distances to all other players
    similarities = []
    for idx, row in df.iterrows():
        other_name = row[player_col]
        if other_name == canonical_name:
            continue
        
        other_values = []
        for m in metrics:
            val = pd.to_numeric(row.get(m), errors="coerce")
            if pd.isna(val):
                other_values.append(0.0)
            else:
                other_values.append(float(val))
        
        other_vector = np.array(other_values)
        
        # Euclidean distance
        distance = np.linalg.norm(player_vector - other_vector)
        similarities.append({
            "player": other_name,
            "distance": float(distance),
            "season": row.get(season_col)
        })
    
    # Sort by distance and take top N
    similarities.sort(key=lambda x: x["distance"])
    
    return {
        "ok": True,
        "player": canonical_name,
        "metrics": metrics,
        "similar_players": similarities[:n]
    }


def rank_players(
    stat: str = "goals",
    top_n: int = 10,
    team: Optional[str] = None,
    position: Optional[str] = None,
    season_year: Optional[int] = None,
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    FAST bulk ranking of players by a statistic.

    This function does aggregation in pandas instead of making individual MCP calls,
    making it 100x faster for ranking queries.

    Args:
        stat: The statistic to rank by (e.g., "goals", "assists", "gross_p_w_eur")
        top_n: Number of top players to return
        team: Optional team filter
        position: Optional position filter
        season_year: Optional specific season year (e.g., 2023)
        seasons_back: Number of seasons to look back if season_year not specified
        player_col: Column name for player names
        season_col: Column name for season data

    Returns:
        Dict with:
        - ok: bool
        - stat: the statistic name
        - rankings: list of {player, value, rank}
        - filters: dict of applied filters
    """
    df = _load_meta_df().copy()

    if stat not in df.columns:
        return {
            "ok": False,
            "error": f"Stat '{stat}' not found in dataset",
            "available_stats": list(df.select_dtypes(include=["number"]).columns[:20])
        }

    # Add season_year column
    df["_season_year"] = df[season_col].apply(season_to_year) if season_col in df.columns else None

    # Apply filters
    mask = pd.Series(True, index=df.index)

    # Team filter
    if team:
        team_cols = [c for c in df.columns if "team" in c.lower() or "club" in c.lower() or "squad" in c.lower()]
        team_mask = pd.Series(False, index=df.index)
        for tc in team_cols:
            if tc in df.columns:
                team_mask = team_mask | df[tc].astype(str).str.contains(team, case=False, na=False)
        mask = mask & team_mask

    # Position filter
    if position:
        pos_cols = [c for c in df.columns if "pos" in c.lower() or "position" in c.lower()]
        pos_mask = pd.Series(False, index=df.index)
        for pc in pos_cols:
            if pc in df.columns:
                pos_mask = pos_mask | df[pc].astype(str).str.contains(position, case=False, na=False)
        mask = mask & pos_mask

    # Season filter
    if season_year:
        # Filter to specific year
        if df["_season_year"].notna().any():
            mask = mask & (df["_season_year"] == season_year)
    else:
        # Filter to last N seasons
        if df["_season_year"].notna().any():
            latest = int(df["_season_year"].max())
            valid_years = [latest - i for i in range(seasons_back)]
            mask = mask & df["_season_year"].isin(valid_years)

    # Filter data
    filtered_df = df[mask].copy()

    if filtered_df.empty:
        return {
            "ok": False,
            "error": "No players found matching filters",
            "filters": {"team": team, "position": position, "season_year": season_year}
        }

    # Aggregate by player (sum stat values across filtered seasons/rows)
    player_totals = filtered_df.groupby(player_col)[stat].sum().sort_values(ascending=False)

    # Get top N
    top_players = player_totals.head(top_n)

    rankings = []
    for rank, (player, value) in enumerate(top_players.items(), 1):
        rankings.append({
            "rank": rank,
            "player": player,
            "value": float(value) if not pd.isna(value) else None
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


def aggregate_group_multi_metrics(
    players: List[str],
    metrics: List[str],
    seasons_back: int = DEFAULT_SEASONS_BACK,
    include_cohort: bool = True,
    cohort_size: int = 200,
    player_col: str = "player",
    season_col: str = "season"
) -> Dict[str, Any]:
    """
    FAST bulk aggregation of multiple metrics for multiple players.

    Instead of making N_players × N_metrics individual calls, this does
    ONE pandas operation to get all data at once.

    Args:
        players: List of player names to aggregate
        metrics: List of metrics to aggregate (e.g., ["goals", "assists", "shots"])
        seasons_back: Number of seasons to look back
        include_cohort: If True, also return cohort statistics for percentile calculations
        cohort_size: Number of players to include in cohort
        player_col: Column name for player names
        season_col: Column name for season data

    Returns:
        Dict with:
        - ok: bool
        - players: {player_name: {per_season: {...}, totals: {...}, latest: {...}}}
        - cohort: {metric: {values: [...], percentiles: {...}}} (if include_cohort=True)
    """
    df = _load_meta_df().copy()

    # Validate metrics exist
    available_metrics = [m for m in metrics if m in df.columns]
    if not available_metrics:
        return {
            "ok": False,
            "error": f"None of the requested metrics found in dataset",
            "requested": metrics,
            "available": list(df.select_dtypes(include=["number"]).columns[:20])
        }

    # Add season_year column
    if season_col in df.columns:
        df["_season_year"] = df[season_col].apply(season_to_year)
        latest_years = sorted(df["_season_year"].dropna().unique())[::-1][:seasons_back]
    else:
        df["_season_year"] = None
        latest_years = []

    # Filter to relevant seasons
    if latest_years:
        season_mask = df["_season_year"].isin(latest_years)
        filtered_df = df[season_mask].copy()
    else:
        filtered_df = df.copy()

    # Build results for each player
    results = {}

    for player_name in players:
        # Use flexible matching
        mask = _flexible_player_match(filtered_df, player_name, player_col)
        player_df = filtered_df[mask]

        if player_df.empty:
            results[player_name] = {
                "found": False,
                "per_season": {},
                "totals": {},
                "latest": {}
            }
            continue

        # Get canonical name
        canonical_name = player_df[player_col].iloc[0]

        # Aggregate by season
        per_season = {}
        for year in latest_years:
            year_df = player_df[player_df["_season_year"] == year]
            season_stats = {}

            for metric in available_metrics:
                value = pd.to_numeric(year_df[metric], errors='coerce').sum()
                season_stats[metric] = float(value) if not pd.isna(value) else 0.0

            # Convert numpy int64 to Python int for JSON serialization
            per_season[int(year)] = season_stats

        # Calculate totals across all seasons
        totals = {}
        for metric in available_metrics:
            total = pd.to_numeric(player_df[metric], errors='coerce').sum()
            totals[metric] = float(total) if not pd.isna(total) else 0.0

        # Get latest season stats
        latest = {}
        if latest_years:
            latest_year_df = player_df[player_df["_season_year"] == latest_years[0]]
            for metric in available_metrics:
                value = pd.to_numeric(latest_year_df[metric], errors='coerce').sum()
                latest[metric] = float(value) if not pd.isna(value) else 0.0

        results[canonical_name] = {
            "found": True,
            "per_season": per_season,
            "totals": totals,
            "latest": latest
        }

    response = {
        "ok": True,
        "players": results,
        "seasons": [int(y) for y in latest_years],  # Convert numpy int64 to Python int
        "metrics": available_metrics
    }

    # Add cohort statistics if requested
    if include_cohort and latest_years:
        cohort_stats = {}
        latest_year = latest_years[0]
        latest_season_df = filtered_df[filtered_df["_season_year"] == latest_year]

        for metric in available_metrics:
            # Get all player values for this metric in latest season
            player_stats = latest_season_df.groupby(player_col)[metric].sum()
            cohort_values = pd.to_numeric(player_stats, errors='coerce').dropna()

            if len(cohort_values) > 0:
                # Take top cohort_size by this metric
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


# ============================================================================
# EXPORT ALL FUNCTIONS
# ============================================================================

__all__ = [
    "get_schema",
    "search_player",
    "aggregate_player_stat",
    "plot_player",
    "compare_players",
    "filter_players",
    "aggregate_group_stats",
    "plot_group",
    "get_player_info",
    "get_top_players",
    "get_player_percentile",
    "get_similar_players",
    "rank_players",
    "aggregate_group_multi_metrics",  # NEW! Bulk multi-metric aggregation
]