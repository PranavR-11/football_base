# mcp/tools.py
import os
import pickle
import math
import re
import base64
import io
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict, Any, Optional

load_dotenv()

DATA_CSV = os.getenv("DATA_PATH", "./data/FINAL_with_rag.csv")
VECTOR_DIR = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
EMB_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
K_DEFAULT = int(os.getenv("K_DEFAULT", "5"))
DEFAULT_SEASONS_BACK = int(os.getenv("DEFAULT_SEASONS_BACK", "5"))

def _ensure_openai():
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_KEY)
    except Exception as e:
        raise ImportError("Install openai>=1.0.0 and set OPENAI_API_KEY in .env. Err: " + str(e))

def _ensure_faiss():
    try:
        import faiss
        return faiss
    except Exception as e:
        raise ImportError("Install faiss-cpu (pip install faiss-cpu). Err: " + str(e))

def _load_meta_df():
    if not os.path.exists(DATA_CSV):
        raise RuntimeError(f"CSV not found at {DATA_CSV}")
    df = pd.read_csv(DATA_CSV)
    # normalize rag_summary column if present
    if "rag_summary" in df.columns:
        df["rag_summary"] = df["rag_summary"].astype(str).fillna("")
    return df

def _load_index_and_meta():
    faiss = _ensure_faiss()
    idx_path = os.path.join(VECTOR_DIR, "index.faiss")
    meta_path = os.path.join(VECTOR_DIR, "metadata.pkl")
    if not os.path.exists(idx_path) or not os.path.exists(meta_path):
        raise RuntimeError("FAISS index or metadata not found. Run scripts/batch_embed.py first.")
    index = faiss.read_index(idx_path)
    with open(meta_path, "rb") as f:
        df = pickle.load(f)
    return faiss, index, df

def get_schema() -> List[str]:
    """
    Return the available columns in the canonical CSV (if present).
    This is used by agents to map user metric tokens to real dataset columns.
    """
    if not os.path.exists(DATA_CSV):
        return []
    try:
        df = pd.read_csv(DATA_CSV, nrows=1)
        return list(df.columns)
    except Exception:
        return []

def search_player(query: str, k: int = K_DEFAULT) -> List[Dict[str, Any]]:
    """Semantic search using embeddings + FAISS index; returns top-k hits with rag_summary snippet."""
    if not query:
        return []
    try:
        client = _ensure_openai()
        faiss = _ensure_faiss()
        _, index, df = _load_index_and_meta()
    except Exception as e:
        # if embeddings/index not available, fallback to simple textual substring match in CSV
        try:
            df = _load_meta_df()
            matches = []
            q = str(query).lower()
            for i, row in df.iterrows():
                score = 0.0
                txt = " ".join([str(row.get(c, "") or "") for c in ("player", "rag_summary", "season")])
                if q in txt.lower():
                    score = 1.0
                if score > 0:
                    matches.append({"score": float(score), "idx": int(i), "player": row.get("player"), "season": row.get("season"), "rag_summary": str(row.get("rag_summary"))[:1000]})
            return sorted(matches, key=lambda r: r["score"], reverse=True)[:k]
        except Exception as e2:
            raise RuntimeError("Search unavailable: " + str(e2))

    resp = client.embeddings.create(model=EMB_MODEL, input=[query])
    emb = resp.data[0]["embedding"] if isinstance(resp.data[0], dict) else getattr(resp.data[0], "embedding")
    import numpy as np
    vec = np.array(emb, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(vec)
    D, I = index.search(vec, k)
    results = []
    for score, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0:
            continue
        row = df.iloc[idx]
        results.append(
            {
                "score": float(score),
                "idx": int(idx),
                "player": row.get("player"),
                "season": row.get("season"),
                "rag_summary": str(row.get("rag_summary"))[:1000],
            }
        )
    return results

# ------- helper: robust season -> year parser -------
def season_to_year(s):
    """
    Try to convert season like "2021/22", "2021-22", "22/23", "2022" -> int year (use the later year).
    Return None if not parsable.
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
        y = parts[-1]
        if len(y) == 2:
            return 2000 + int(y)
        return int(y)
    except Exception:
        return None

# ------- aggregate_player_stat (robust; default 5 seasons) -------
def aggregate_player_stat(
    player_name: str,
    stat: str = "playing_time_starts",
    seasons_back: int = DEFAULT_SEASONS_BACK,
    player_col: str = "player",
    season_col: str = "season",
) -> Dict[str, Any]:
    df = _load_meta_df().copy()
    if season_col not in df.columns:
        raise RuntimeError(f"Season column '{season_col}' not found in CSV")

    df["_season_year"] = df[season_col].apply(season_to_year)
    df["_player_lc"] = df[player_col].astype(str).str.strip().str.lower()
    mask = df["_player_lc"] == player_name.strip().lower()

    player_rows_years = df[mask & df["_season_year"].notna()].copy()
    if not player_rows_years.empty:
        latest = int(player_rows_years["_season_year"].max())
        requested_years = [latest - i for i in range(seasons_back)][::-1]
        if stat not in player_rows_years.columns:
            per_season = [{"season_year": y, "value": None} for y in requested_years]
            return {
                "found": True,
                "player": player_rows_years[player_col].iloc[0],
                "latest_season": latest,
                "requested_seasons": requested_years,
                "per_season": per_season,
                "total": None,
                "has_consecutive_n": False,
                "note": f"stat '{stat}' not found",
            }
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
            "player": player_rows_years[player_col].iloc[0],
            "latest_season": latest,
            "requested_seasons": requested_years,
            "per_season": per_season,
            "total": total if has_all else None,
            "has_consecutive_n": has_all,
        }

    # FALLBACK: no parseable numeric years -> use labels by dataset order (preserve order)
    player_rows = df[mask].copy()
    if player_rows.empty:
        return {"found": False, "message": "player not found or no season data"}

    labels = list(pd.Series(player_rows[season_col].astype(str)).dropna().unique())
    if not labels:
        return {
            "found": True,
            "player": player_rows[player_col].iloc[0],
            "requested_seasons": [],
            "per_season": [],
            "total": None,
            "has_consecutive_n": False,
            "note": "no season labels available",
        }
    chosen = labels[-seasons_back:]
    if stat not in player_rows.columns:
        per_season = [{"season_label": s, "value": None} for s in chosen]
        return {
            "found": True,
            "player": player_rows[player_col].iloc[0],
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
        "player": player_rows[player_col].iloc[0],
        "requested_seasons": chosen,
        "per_season": per_season,
        "total": total if has_all else None,
        "has_consecutive_n": has_all,
    }

# ------- plot_player (robust, returns safe dates and image) -------
def plot_player(
    player_name: str, metrics: List[str] = None, player_col: str = "player", season_col: str = "season"
) -> Dict[str, Any]:
    if metrics is None:
        metrics = ["playing_time_starts"]
    df = _load_meta_df().copy()

    if season_col not in df.columns:
        df["_season_year"] = None
    else:
        df["_season_year"] = df[season_col].apply(season_to_year)

    sel = df[df[player_col].astype(str).str.lower() == player_name.strip().lower()].copy()
    if sel.empty:
        candidates = df[df[player_col].astype(str).str.contains(player_name, case=False, na=False)][player_col].unique().tolist()[:8]
        return {"found": False, "message": "player not found", "player": player_name, "candidates": candidates}

    use_years = sel["_season_year"].notna().any()
    if use_years:
        sel = sel.sort_values("_season_year")
        dates = [int(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None for x in sel["_season_year"].tolist()]
        labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(d) for d in dates]
    else:
        sel = sel.sort_index()
        labels = sel[season_col].astype(str).fillna("").tolist() if season_col in sel.columns else [str(i) for i in range(len(sel))]
        dates = labels

    series = {}
    for m in metrics:
        if m not in sel.columns:
            series[m] = [None for _ in dates]
        else:
            vals = pd.to_numeric(sel[m], errors="coerce").tolist()
            series[m] = [None if (isinstance(v, float) and math.isnan(v)) else float(v) for v in vals]

    n_rows = len(dates)
    keep_mask = []
    for i in range(n_rows):
        row_has_value = any((series[m][i] is not None) for m in metrics)
        keep_mask.append(row_has_value)

    if not any(keep_mask):
        return {"found": True, "player": player_name, "points": {"dates": dates, "series": series}, "image_b64": None, "error": "no_numeric_points_for_metrics"}

    filtered_dates = [d for d, k in zip(dates, keep_mask) if k]
    filtered_series = {m: [v for v, k in zip(series[m], keep_mask) if k] for m in metrics}

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

        ax.set_title(f"{player_name} - {' & '.join(metrics)}")
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
        return {"found": True, "player": player_name, "points": {"dates": filtered_dates, "series": filtered_series}, "image_b64": None, "error": str(e)}

    return {"found": True, "player": player_name, "image_b64": img_b64, "points": {"dates": filtered_dates, "series": filtered_series}}

# ---------------- NEW group helpers ----------------

def candidate_metrics_from_df(df: pd.DataFrame) -> List[str]:
    prefer = [
        "goals_per_90", "xg_per_90", "npxg_per_90", "assists_per_90", "shots_per_90",
        "xg", "npxg", "goals", "assists", "minutes"
    ]
    available = [c for c in prefer if c in df.columns]
    if not available:
        nums = df.select_dtypes(include=["number"]).columns.tolist()
        available = nums[:5]
    return available

def filter_players(team: Optional[str] = None, position: Optional[str] = None,
                   seasons_back: int = DEFAULT_SEASONS_BACK, player_col: str = "player",
                   team_cols_candidates: List[str] = None, pos_col_candidates: List[str] = None) -> Dict[str, Any]:
    df = _load_meta_df().copy()
    if team_cols_candidates is None:
        team_cols_candidates = [c for c in df.columns if "team" in c.lower() or "club" in c.lower()]
    if pos_col_candidates is None:
        pos_col_candidates = [c for c in df.columns if "pos" in c.lower() or "position" in c.lower()]

    mask = pd.Series(True, index=df.index)
    if team:
        found_team_col = False
        for tc in team_cols_candidates:
            if tc in df.columns:
                found_team_col = True
                mask = mask & df[tc].astype(str).str.contains(team, case=False, na=False)
        if not found_team_col:
            mask = mask & (df["rag_summary"].astype(str).str.contains(team, case=False, na=False) | df[player_col].astype(str).str.contains(team, case=False, na=False))

    if position:
        pos_mask = pd.Series(False, index=df.index)
        for pc in pos_col_candidates:
            if pc in df.columns:
                pos_mask = pos_mask | df[pc].astype(str).str.contains(position, case=False, na=False)
        if not pos_mask.any() and "rag_summary" in df.columns:
            pos_mask = df["rag_summary"].astype(str).str.contains(position, case=False, na=False)
        mask = mask & pos_mask

    if "season" in df.columns:
        df["_season_year"] = df["season"].apply(season_to_year)
        if df["_season_year"].notna().any():
            latest = int(df["_season_year"].max())
            valid_years = [latest - i for i in range(seasons_back)]
            mask = mask & df["_season_year"].isin(valid_years)

    candidates = df[mask][player_col].dropna().astype(str).unique().tolist()
    return {"ok": True, "players": candidates[:500], "count": len(candidates)}

def aggregate_group_stats(players: List[str], stat: str = "goals", seasons_back: int = DEFAULT_SEASONS_BACK,
                          player_col: str = "player", season_col: str = "season") -> Dict[str, Any]:
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
    for p in players:
        sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
        if sel.empty:
            per_player[p] = {"found": False}
            continue
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
        per_player[p] = {"found": True, "per_season": by_year}
    return {"ok": True, "players": players, "requested_seasons": years, "per_player": per_player, "totals": totals}

def plot_group(players: List[str], metrics: List[str] = None, seasons_back: int = DEFAULT_SEASONS_BACK,
               player_col: str = "player", season_col: str = "season") -> Dict[str, Any]:
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
    for p in players:
        sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
        if sel.empty:
            series_table[p] = {"found": False}
            continue
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
        series_table[p] = {"found": True, "series": series_vals}

    latest = chosen_years[-1] if chosen_years else None
    percentiles = {}
    import numpy as np
    for m in metrics:
        if m in df.columns:
            col_vals = pd.to_numeric(df[m], errors="coerce").dropna().values
        else:
            col_vals = np.array([])
        for p in players:
            if not series_table.get(p, {}).get("found"):
                percentiles.setdefault(p, {})[m] = None
                continue
            sel = df[df[player_col].astype(str).str.strip().str.lower() == p.strip().lower()].copy()
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
                percentiles.setdefault(p, {})[m] = None
            else:
                percentiles.setdefault(p, {})[m] = float((col_vals <= float(row_val)).sum()) / float(len(col_vals)) * 100.0

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(12, 6))
        ax1 = fig.add_subplot(1, 2, 1)
        if chosen_years:
            x = list(range(len(chosen_years)))
            for p in players:
                if not series_table.get(p, {}).get("found"):
                    continue
                ax1.plot(x, series_table[p]["series"], marker="o", label=p)
            ax1.set_xticks(x)
            ax1.set_xticklabels([str(y) for y in chosen_years], rotation=30)
        else:
            for p in players:
                if not series_table.get(p, {}).get("found"):
                    continue
                vals = series_table[p]["series"]
                ax1.plot(list(range(len(vals))), vals, marker="o", label=p)
        ax1.set_title(f"Group time-series ({metrics[0]})")
        ax1.grid(True)
        ax1.legend(fontsize="small")

        ax2 = fig.add_subplot(1, 2, 2, polar=True)
        theta = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
        for p in players:
            if not percentiles.get(p):
                continue
            vals = [percentiles[p].get(m, 0.0) or 0.0 for m in metrics]
            vals_closed = vals + [vals[0]]
            theta_closed = np.concatenate((theta, [theta[0]]))
            ax2.plot(theta_closed, vals_closed, marker="o", label=p)
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
        return {"ok": False, "error": "plot_error", "detail": str(e), "players": players, "chosen_seasons": chosen_years, "series_table": series_table, "percentiles": percentiles}

    return {"ok": True, "players": players, "chosen_seasons": chosen_years, "image_b64": img_b64, "series_table": series_table, "percentiles": percentiles}