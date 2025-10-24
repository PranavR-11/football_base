#!/usr/bin/env python3
"""
Generate canonical CSV and rag_summary from your Excel (FINAL.xlsx).
Saves:
 - data/FINAL_canonical.csv
 - data/FINAL_with_rag.csv
 - data/FINAL_rename_map.json
 - data/FINAL_data_dictionary.json
 - data/FINAL_rag_mapping_allstats.json
"""
import os, json, re
import pandas as pd
from pathlib import Path

ROOT = Path(".")
IN_XLSX = Path("data/FINAL.xlsx")  # update if needed
OUT_CANON = Path("data/FINAL_canonical.csv")
OUT_RAG = Path("data/FINAL_with_rag.csv")
OUT_MAP = Path("data/FINAL_rename_map.json")
OUT_DICT = Path("data/FINAL_data_dictionary.json")
OUT_RAG_MAP = Path("data/FINAL_rag_mapping_allstats.json")

MAX_RAG_CHARS = 1200

def canonicalize(col):
    s = str(col).strip().lower()
    s = re.sub(r'&', ' and ', s)
    s = re.sub(r'[^0-9a-z]+', '_', s)
    s = re.sub(r'__+', '_', s)
    s = s.strip('_')
    if s == '':
        s = 'col'
    return s

# heuristics for canonical names
synonyms = {
    "player": ["player", "player_name", "name"],
    "season": ["season", "season_year", "year"],
    "squad": ["squad", "team", "club"],
    "pos": ["pos", "position"],
    "nation": ["nation", "country", "nationality"],
    "playing_time_90s": ["playing_time_90s", "playing_time_90", "90s"],
    "playing_time_min": ["playing_time_min", "minutes_played", "mins"],
    "playing_time_starts": ["playing_time_starts", "starts", "games_started", "lineups"],
    "goals": ["performance_gls", "goals", "goals_total", "gls"],
    "assists": ["performance_ast", "assists", "ast"],
    "goals_assists": ["performance_g+a", "g+a", "goals_assists"],
    "goals_no_pk": ["performance_g-pk", "g-pk", "goals_no_pk"],
    "penalties_taken": ["performance_pkatt", "pkatt"],
    "yellow_cards": ["performance_crdy", "crdy", "yellow_cards"],
    "red_cards": ["performance_crdr", "crdr", "red_cards"],
    "xg": ["expected_xg", "xg"],
    "npxg": ["expected_npxg", "npxg"],
    "xag": ["expected_xag", "xag"],
    "npxg_xag": ["expected_npxg+xag", "npxg_xag"],
    "progressive_carries": ["progression_prgc", "prgc"],
    "progressive_passes": ["progression_prgp", "prgp"],
    "progressive_received": ["progression_prgr", "prgr"],
    "goals_per_90": ["per_90_minutes_gls", "goals_per_90"],
    "assists_per_90": ["per_90_minutes_ast", "assists_per_90"],
    "goals_assists_per_90": ["per_90_minutes_g+a", "g+a_per_90"],
    "goals_no_pk_per_90": ["per_90_minutes_g-pk", "g-pk_per_90"],
    "goals_assists_no_pk_per_90": ["per_90_minutes_g+a-pk", "g+a-pk_per_90"],
    "xg_per_90": ["per_90_minutes_xg", "xg_per_90"],
    "xag_per_90": ["per_90_minutes_xag", "xag_per_90"],
    "xg_xag_per_90": ["per_90_minutes_xg+xag", "xg_xag_per_90"],
    "npxg_per_90": ["per_90_minutes_npxg", "npxg_per_90"],
    "npxg_xag_per_90": ["per_90_minutes_npxg+xag", "npxg_xag_per_90"],
    "market_value_24_25": ["market_value", "market_value_24_25"]
}

def load_excel(path):
    print("Loading Excel:", path)
    return pd.read_excel(path)

def build_rename_map(cols):
    lower_map = {c.lower(): c for c in cols}
    rename = {}
    used_canon = set()
    # map synonyms
    for canon, forms in synonyms.items():
        for f in forms:
            if f in lower_map:
                orig = lower_map[f]
                rename[orig] = canon
                used_canon.add(canon)
                break
    # remaining columns -> canonicalize
    for c in cols:
        if c in rename: continue
        cand = canonicalize(c)
        base = cand
        i = 1
        while cand in used_canon:
            cand = f"{base}_{i}"
            i += 1
        rename[c] = cand
        used_canon.add(cand)
    return rename

def build_data_dictionary(df, rename_map):
    dd = {}
    auto_descriptions = {
        "player": "Player full name.",
        "season": "Season label (e.g., 2022/23).",
        "squad": "Club / squad name.",
        "pos": "Player position (e.g., ST, CM, LB).",
        "nation": "Player nationality.",
        "playing_time_90s": "Minutes played converted to 90-minute equivalents.",
        "playing_time_min": "Total minutes played.",
        "playing_time_starts": "Number of matches the player started.",
        "goals": "Number of goals.",
        "assists": "Number of assists.",
        "goals_assists": "Goals + assists combined.",
        "market_value_24_25": "Market value for 2024/25 season (EUR)."
    }
    for orig, canon in rename_map.items():
        vals = df[orig].dropna().astype(str).unique()[:5].tolist() if orig in df.columns else []
        dd[canon] = {
            "original_column": orig,
            "description": auto_descriptions.get(canon, ""),
            "example_values": vals
        }
    return dd

def fmt_num(v):
    try:
        if pd.isna(v): return None
        f = float(v)
        if abs(f - round(f)) < 1e-6:
            return str(int(round(f)))
        return str(round(f,2))
    except:
        return str(v)

def build_rag_summary_row(row, text_cols, numeric_cols, max_chars=MAX_RAG_CHARS):
    parts = []
    for c in text_cols:
        if c in row and pd.notna(row[c]):
            parts.append(f"{c}: {str(row[c]).strip()}")
    for c in numeric_cols:
        if c in row and pd.notna(row[c]):
            v = fmt_num(row[c])
            parts.append(f"{c}: {v}")
    summary = " | ".join(parts)
    if len(summary) > max_chars:
        toks = summary.split(" | ")
        keep = []
        # prefer text cols, then numeric in provided order
        for t in toks:
            key = t.split(":")[0]
            if key in text_cols:
                keep.append(t)
        for t in toks:
            key = t.split(":")[0]
            if key in numeric_cols and t not in keep:
                keep.append(t)
        acc = ""
        final = []
        for t in keep:
            if len(acc) + len(t) + 3 > max_chars:
                break
            final.append(t)
            acc = " | ".join(final)
        if final:
            summary = acc
        else:
            summary = summary[:max_chars-3] + "..."
    return summary

def main():
    os.makedirs("data", exist_ok=True)
    if not IN_XLSX.exists():
        print(f"Input Excel not found at {IN_XLSX}. Please place FINAL.xlsx in data/ or update IN_XLSX.")
        return
    df = load_excel(IN_XLSX)
    cols = df.columns.tolist()
    rename_map = build_rename_map(cols)
    df_canon = df.rename(columns=rename_map)
    # write canonical CSV
    df_canon.to_csv(OUT_CANON, index=False)
    # data dictionary
    data_dict = build_data_dictionary(df, rename_map)
    with open(OUT_MAP, "w") as f:
        json.dump(rename_map, f, indent=2)
    with open(OUT_DICT, "w") as f:
        json.dump(data_dict, f, indent=2)
    # prepare rag_summary: pick text cols & numeric stats (all user-important stats if present)
    text_cols = [c for c in ["player","squad","pos","season","nation","status","notes"] if c in df_canon.columns]
    # prioritized numeric stats (include if present)
    numeric_candidates = [
        "goals","assists","goals_assists","goals_no_pk","penalties_taken",
        "yellow_cards","red_cards",
        "xg","npxg","xag","npxg_xag",
        "progressive_carries","progressive_passes","progressive_received",
        "goals_per_90","assists_per_90","goals_assists_per_90",
        "goals_no_pk_per_90","goals_assists_no_pk_per_90",
        "xg_per_90","xag_per_90","xg_xag_per_90","npxg_per_90","npxg_xag_per_90",
        "market_value_24_25"
    ]
    present_numeric = [c for c in numeric_candidates if c in df_canon.columns]
    # include up to 8 other numeric columns
    extra_numeric = [c for c in df_canon.columns if (df_canon[c].dtype.kind in "fi") and (c not in present_numeric)]
    extra_numeric = extra_numeric[:8]
    numeric_cols = present_numeric + extra_numeric
    # build rag_summary
    df_canon["rag_summary"] = df_canon.apply(lambda r: build_rag_summary_row(r, text_cols, numeric_cols), axis=1)
    df_canon.to_csv(OUT_RAG, index=False)
    # save rag mapping metadata
    mapping = {
        "text_cols_used": text_cols,
        "numeric_cols_included": numeric_cols,
        "extra_numeric_sample": extra_numeric,
        "num_rows": len(df_canon),
        "rag_max_chars": MAX_RAG_CHARS
    }
    with open(OUT_RAG_MAP, "w") as f:
        json.dump(mapping, f, indent=2)
    print("Wrote:", OUT_CANON)
    print("Wrote:", OUT_RAG)
    print("Wrote rename map and data dictionary and rag mapping.")
    print("Rows:", len(df_canon))

if __name__ == "__main__":
    main()