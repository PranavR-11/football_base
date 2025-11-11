#!/usr/bin/env python3
"""
Load FAISS index + metadata and run a semantic search for a query.
"""
import os, pickle, numpy as np
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_DIR = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
EMB_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
K = 5

if OPENAI_API_KEY is None:
    raise RuntimeError("Set OPENAI_API_KEY in .env")

from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

try:
    import faiss
except Exception as e:
    raise ImportError("Install faiss-cpu: pip install faiss-cpu") from e

def get_embedding(text):
    resp = client.embeddings.create(model=EMB_MODEL, input=[text])
    d = resp.data[0]
    return np.array(d["embedding"] if isinstance(d, dict) else getattr(d, "embedding"), dtype="float32")

def main():
    idx_path = os.path.join(VECTOR_DIR, "index.faiss")
    meta_path = os.path.join(VECTOR_DIR, "metadata.pkl")
    if not os.path.exists(idx_path) or not os.path.exists(meta_path):
        raise RuntimeError("Index or metadata not found. Run scripts/batch_embed.py first.")

    index = faiss.read_index(idx_path)
    with open(meta_path, "rb") as f:
        df = pickle.load(f)

    q = input("Query> ").strip()
    if q == "":
        print("Empty query")
        return

    vec = get_embedding(q)
    faiss.normalize_L2(vec.reshape(1, -1))
    D, I = index.search(vec.reshape(1, -1), K)
    ids = I[0].tolist()
    scores = D[0].tolist()
    print("Top results:")
    for idx, score in zip(ids, scores):
        if idx < 0:
            continue
        row = df.iloc[idx]
        print(f"score={score:.4f}  idx={idx}  player={row.get('player')}  season={row.get('season')}")
        print("  snippet:", (row.get("rag_summary") or "")[:300].replace("\n"," "))
        print("-"*80)

if __name__ == "__main__":
    main()