"""
Flames of Aron - Hybrid RAG Indexing Pipeline (BM25 + Dense Embeddings + RRF)
NASA Space Apps Challenge 2026 - Microgravity Combustion & Spacecraft Fire Safety
"""

import os
import re
import json
import pickle
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNKS_PATH = os.path.join(BASE_DIR, "processed", "chunks.jsonl")
INDEX_DIR = os.path.join(BASE_DIR, "indexes")
os.makedirs(INDEX_DIR, exist_ok=True)

MODEL_NAME = "all-MiniLM-L6-v2"

def tokenize(text: str):
    """Clean, lowercase alphanumeric tokenization preserving hyphenated terms and chemical formulas."""
    return re.findall(r"\b[A-Za-z0-9_/%.-]+\b", text.lower())

def main():
    print("=" * 65)
    print(" FLAMES OF ARON: HYBRID SEARCH INDEXING PIPELINE")
    print("=" * 65)
    print(f" Loading chunks from: {CHUNKS_PATH}")

    chunks = []
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    print(f" Loaded {len(chunks)} total chunks.")

    # Split into active search chunks and reference/caption chunks
    active_chunks = [c for c in chunks if not c.get("exclude_from_default_search", False)]
    print(f" Active search corpus size: {len(active_chunks)} chunks (prose + tables).")

    # 1. BM25 (Sparse) Indexing
    print("\n[1/3] Building BM25 sparse index...")
    tokenized_corpus = [tokenize(c["text"]) for c in active_chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    bm25_save_path = os.path.join(INDEX_DIR, "bm25_index.pkl")
    with open(bm25_save_path, "wb") as f:
        pickle.dump({"bm25": bm25, "tokenized_corpus": tokenized_corpus}, f)
    print(f" -> BM25 index saved to {bm25_save_path}")

    # 2. Dense Embeddings Indexing
    print(f"\n[2/3] Computing dense vector embeddings with '{MODEL_NAME}'...")
    encoder = SentenceTransformer(MODEL_NAME)
    
    # We embed the chunk text (including its rich context header)
    texts_to_embed = [c["text"] for c in active_chunks]
    embeddings = encoder.encode(
        texts_to_embed,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True
    )
    embeddings = np.array(embeddings, dtype=np.float32)

    embeddings_save_path = os.path.join(INDEX_DIR, "dense_embeddings.npy")
    np.save(embeddings_save_path, embeddings)
    print(f" -> Dense embeddings ({embeddings.shape[0]}x{embeddings.shape[1]}) saved to {embeddings_save_path}")

    # 3. Save Chunk Metadata Lookup
    print("\n[3/3] Saving chunk lookup dictionary...")
    chunk_lookup_path = os.path.join(INDEX_DIR, "chunk_lookup.json")
    with open(chunk_lookup_path, "w", encoding="utf-8") as f:
        json.dump(active_chunks, f, ensure_ascii=False, indent=2)
    print(f" -> Chunk lookup table saved to {chunk_lookup_path}")

    # Also save an all-chunks lookup for deep reference / caption retrieval
    all_chunks_lookup_path = os.path.join(INDEX_DIR, "all_chunks_lookup.json")
    with open(all_chunks_lookup_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f" -> All-chunks reference table saved to {all_chunks_lookup_path}")

    print("\n" + "=" * 65)
    print(" INDEXING COMPLETE! RUNNING VERIFICATION QUERIES...")
    print("=" * 65)

    test_queries = [
        "What is the blowoff flammability limit for PMMA rods in concurrent flow in BASS-II?",
        "Methanol droplet extinction diameter in carbon dioxide enriched ambient environments in FLEX",
        "Saffire SIBAL fabric flame spread rate in concurrent flow in microgravity"
    ]

    for q in test_queries:
        print(f"\n--- QUERY: '{q}' ---")
        
        # BM25 Top 3
        q_toks = tokenize(q)
        bm25_scores = bm25.get_scores(q_toks)
        top_bm25_idx = np.argsort(bm25_scores)[::-1][:3]
        
        # Dense Top 3
        q_emb = encoder.encode([q], normalize_embeddings=True)[0]
        dense_scores = np.dot(embeddings, q_emb)
        top_dense_idx = np.argsort(dense_scores)[::-1][:3]

        # Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        for rank, idx in enumerate(np.argsort(bm25_scores)[::-1][:20], start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))
        for rank, idx in enumerate(np.argsort(dense_scores)[::-1][:20], start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))

        top_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:3]

        for rank, (idx, score) in enumerate(top_rrf, start=1):
            c = active_chunks[idx]
            first_line = c["text"].split("\n")[0]
            preview = c["text"].split("\n")[1][:120] if len(c["text"].split("\n")) > 1 else ""
            print(f" [Rank {rank} | RRF Score: {score:.5f}] {c['chunk_id']} (has_table={c['has_table']})")
            print(f"    Header: {first_line}")
            print(f"    Snippet: {preview}...")

if __name__ == "__main__":
    main()
