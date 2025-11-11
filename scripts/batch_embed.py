#!/usr/bin/env python3
"""
Batch-embed rag_summary using OpenAI v1+ client (no LangChain).
Creates:
  - <VECTOR_DIR>/index.faiss
  - <VECTOR_DIR>/metadata.pkl
"""
import os, time, pickle
from dotenv import load_dotenv
import pandas as pd
import numpy as np

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATA_CSV = os.getenv("DATA_PATH", "./data/FINAL_with_rag.csv")
VECTOR_DIR = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
EMB_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
BATCH_SIZE = int(os.getenv("EMB_BATCH_SIZE", "256"))
SLEEP_BETWEEN = float(os.getenv("EMB_SLEEP", "0.5"))

if OPENAI_API_KEY is None:
    raise RuntimeError("Set OPENAI_API_KEY in .env (OPENAI_API_KEY)")

try:
    from openai import OpenAI
except Exception as e:
    raise ImportError("Please install openai>=1.0.0 (pip install openai). Err: " + str(e))

try:
    import faiss
except Exception as e:
    raise ImportError("Please install faiss-cpu (pip install faiss-cpu). Err: " + str(e))

client = OpenAI(api_key=OPENAI_API_KEY)

def chunked(it, size):
    for i in range(0, len(it), size):
        yield it[i:i+size]

def embed_batch(texts):
    for attempt in range(6):
        try:
            resp = client.embeddings.create(model=EMB_MODEL, input=texts)
            embeds = []
            for d in resp.data:
                if isinstance(d, dict):
                    embeds.append(d["embedding"])
                else:
                    embeds.append(getattr(d, "embedding"))
            return embeds
        except Exception as e:
            wait = (2 ** attempt) + 0.5
            print(f"Embedding request failed (attempt {attempt+1}), waiting {wait}s:", e)
            time.sleep(wait)
    raise RuntimeError("Embedding failed after retries")

def main():
    os.makedirs(VECTOR_DIR, exist_ok=True)
    print("Loading CSV:", DATA_CSV)
    df = pd.read_csv(DATA_CSV)
    if "rag_summary" not in df.columns:
        raise RuntimeError("rag_summary column not found in CSV at " + DATA_CSV)
    texts = df["rag_summary"].fillna("").astype(str).tolist()
    n = len(texts)
    print("Rows to embed:", n)

    all_embs = []
    for i, chunk in enumerate(chunked(texts, BATCH_SIZE)):
        print(f"Embedding batch {i+1}/{(n + BATCH_SIZE - 1)//BATCH_SIZE} (size {len(chunk)})...")
        embeds = embed_batch(chunk)
        all_embs.extend(embeds)
        time.sleep(SLEEP_BETWEEN)

    arr = np.array(all_embs, dtype="float32")
    if arr.shape[0] != n:
        raise RuntimeError(f"Embeddings count {arr.shape[0]} != rows {n}")

    dim = arr.shape[1]
    print("Embedding dimension:", dim)

    import faiss
    faiss.normalize_L2(arr)

    index = faiss.IndexFlatIP(dim)
    index.add(arr)
    index_path = os.path.join(VECTOR_DIR, "index.faiss")
    faiss.write_index(index, index_path)
    print("Wrote FAISS index to:", index_path)

    meta_path = os.path.join(VECTOR_DIR, "metadata.pkl")
    with open(meta_path, "wb") as f:
        pickle.dump(df, f)
    print("Wrote metadata to:", meta_path)
    print("Done.")

if __name__ == "__main__":
    main()