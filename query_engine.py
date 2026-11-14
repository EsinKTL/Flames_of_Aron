"""
Flames of Aron - Advanced Microgravity Combustion Retrieval & Query Engine
NASA Space Apps Challenge 2026 - Microgravity Combustion & Spacecraft Fire Safety

Features:
- Hybrid Search (BM25Okapi + Dense Embeddings from all-MiniLM-L6-v2)
- Reciprocal Rank Fusion (RRF) with experiment and document filtering
- Structured Golden Table retrieval (physical limits, O2, pressure, flow rate, lunar flags)
- Guardrail Fact verification from facts.yaml
- Strict citation synthesis: [SourceID, Page X]
"""

import os
import re
import json
import pickle
import numpy as np
import pandas as pd
import yaml
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE_DIR, "indexes")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")

BM25_PATH = os.path.join(INDEX_DIR, "bm25_index.pkl")
DENSE_PATH = os.path.join(INDEX_DIR, "dense_embeddings.npy")
CHUNK_LOOKUP_PATH = os.path.join(INDEX_DIR, "chunk_lookup.json")
ALL_CHUNKS_PATH = os.path.join(INDEX_DIR, "all_chunks_lookup.json")
GOLDEN_TABLE_PATH = os.path.join(PROCESSED_DIR, "golden_table.csv")
FACTS_PATH = os.path.join(REFERENCE_DIR, "facts.yaml")
MANIFEST_PATH = os.path.join(REFERENCE_DIR, "manifest.csv")

MODEL_NAME = "all-MiniLM-L6-v2"

def tokenize(text: str):
    """Tokenization matching the indexing pipeline."""
    return re.findall(r"\b[A-Za-z0-9_/%.-]+\b", text.lower())

class CombustionQueryEngine:
    def __init__(self):
        print("Initializing CombustionQueryEngine...")
        
        # 1. Load BM25 Index
        with open(BM25_PATH, "rb") as f:
            data = pickle.load(f)
            self.bm25 = data["bm25"]
            self.tokenized_corpus = data["tokenized_corpus"]
            
        # 2. Load Dense Embeddings
        self.embeddings = np.load(DENSE_PATH)
        self.encoder = SentenceTransformer(MODEL_NAME)
        
        # 3. Load Chunks
        with open(CHUNK_LOOKUP_PATH, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
            
        with open(ALL_CHUNKS_PATH, "r", encoding="utf-8") as f:
            self.all_chunks = json.load(f)
            
        # 4. Load Golden Table
        if os.path.exists(GOLDEN_TABLE_PATH):
            self.golden_df = pd.read_csv(GOLDEN_TABLE_PATH, encoding="utf-8")
        else:
            self.golden_df = pd.DataFrame()
            
        # 5. Load Facts YAML
        if os.path.exists(FACTS_PATH):
            with open(FACTS_PATH, "r", encoding="utf-8") as f:
                self.facts_data = yaml.safe_load(f)
        else:
            self.facts_data = {}
            
        # 6. Load Manifest
        if os.path.exists(MANIFEST_PATH):
            self.manifest_df = pd.read_csv(MANIFEST_PATH, encoding="utf-8-sig")
        else:
            self.manifest_df = pd.DataFrame()
            
        print(f"Ready! Corpus: {len(self.chunks)} active chunks, {len(self.golden_df)} Golden Table experiments, {len(self.facts_data.get('facts', []))} verified facts.")

    def search_hybrid(self, query: str, top_k: int = 5, experiment_filter: str = None, category_filter: str = None):
        """
        Executes hybrid search combining BM25 and dense vector cosine similarity via RRF.
        Supports filtering by experiment (e.g. 'BASS', 'Saffire', 'FLEX') or category.
        """
        # BM25 scores
        q_toks = tokenize(query)
        bm25_scores = self.bm25.get_scores(q_toks)
        
        # Dense similarity
        q_emb = self.encoder.encode([query], normalize_embeddings=True)[0]
        dense_scores = np.dot(self.embeddings, q_emb)
        
        # Reciprocal Rank Fusion (k=60)
        rrf_scores = {}
        top_bm25_candidates = np.argsort(bm25_scores)[::-1][:50]
        top_dense_candidates = np.argsort(dense_scores)[::-1][:50]
        
        for rank, idx in enumerate(top_bm25_candidates, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))
        for rank, idx in enumerate(top_dense_candidates, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))
            
        # Filter & Sort
        sorted_indices = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in sorted_indices:
            chunk = self.chunks[idx]
            
            # Apply filters if provided
            if experiment_filter:
                exp_matched = False
                ef_lower = experiment_filter.lower().strip()
                for exp in chunk.get("investigation_ids", []):
                    e_lower = exp.lower().strip()
                    if ef_lower == "bass":
                        if e_lower in ("bass", "bass-i", "bass 1"):
                            exp_matched = True
                            break
                    elif ef_lower == e_lower or (ef_lower in e_lower and not (ef_lower == "bass" and "bass-ii" in e_lower)):
                        exp_matched = True
                        break
                if not exp_matched:
                    continue
                    
            if category_filter:
                cat = chunk.get("doc_type", "")
                if category_filter.lower() not in cat.lower():
                    continue
                    
            results.append({
                "chunk_id": chunk["chunk_id"],
                "source_id": chunk["source_id"],
                "page": chunk.get("page", 1),
                "section_title": chunk.get("section_title", ""),
                "section_type": chunk.get("section_type", ""),
                "investigation_ids": chunk.get("investigation_ids", []),
                "doc_type": chunk.get("doc_type", ""),
                "has_table": chunk.get("has_table", False),
                "rrf_score": float(score),
                "bm25_score": float(bm25_scores[idx]),
                "dense_score": float(dense_scores[idx]),
                "text": chunk["text"]
            })
            if len(results) >= top_k:
                break
                
        return results

    def get_golden_facts(self, query: str):
        """
        Retrieves matching experiment rows from Golden Table based on experiment names in query.
        """
        if self.golden_df.empty:
            return []
            
        matches = []
        q_lower = query.lower()
        
        for _, row in self.golden_df.iterrows():
            exp_id = str(row.get("id", "")).lower()
            exp_name = str(row.get("name", "")).lower()
            
            # Check for keyword overlap
            if exp_id in q_lower or (len(exp_id) > 2 and exp_id in q_lower.replace("-", "")):
                matches.append(row.to_dict())
            elif any(token in q_lower for token in exp_name.split() if len(token) > 4):
                matches.append(row.to_dict())
                
        return matches

    def get_guardrail_facts(self, query: str):
        """
        Retrieves relevant ground truth facts and physical calculation rules from facts.yaml.
        """
        facts = self.facts_data.get("facts", [])
        rules = self.facts_data.get("rules", [])
        calcs = self.facts_data.get("calculations", [])
        
        q_tokens = set(tokenize(query))
        matching_facts = []
        
        for f in facts:
            topic = str(f.get("topic", "")).lower()
            claim = str(f.get("claim", "")).lower()
            claim_tokens = set(tokenize(topic + " " + claim))
            overlap = q_tokens.intersection(claim_tokens)
            if len(overlap) >= 2 or any(k in topic for k in q_tokens if len(k) > 3):
                matching_facts.append(f)
                
        return matching_facts[:4]

    def build_rag_context(self, query: str, top_k: int = 5):
        """
        Assembles all retrieved evidence into an organized, citation-ready context block.
        """
        search_results = self.search_hybrid(query, top_k=top_k)
        golden_matches = self.get_golden_facts(query)
        guardrails = self.get_guardrail_facts(query)
        
        context_parts = []
        
        # 1. Guardrail Facts
        if guardrails:
            context_parts.append("### AUTHORITATIVE NASA BASELINE FACTS & PHYSICAL CONSTANTS:")
            for g in guardrails:
                context_parts.append(f"- [{g.get('id', 'F')}] ({g.get('topic')}) {g.get('claim')} [Source: {g.get('source')}]")
            context_parts.append("")
            
        # 2. Golden Table Parameters
        if golden_matches:
            context_parts.append("### GOLDEN TABLE EXPERIMENT SPECIFICATIONS:")
            for m in golden_matches:
                context_parts.append(f"**Experiment: {m.get('name')} (ID: {m.get('id')})**")
                context_parts.append(f"- Category: {m.get('category')} | Fuel: {m.get('fuel_type')} ({m.get('fuel_material', m.get('fuel_shape_size'))})")
                context_parts.append(f"- Oxygen Range: {m.get('o2_min')} - {m.get('o2_max')} ({m.get('o2_raw', '')})")
                context_parts.append(f"- Pressure Range: {m.get('pressure_psi_min')} - {m.get('pressure_psi_max')} psi ({m.get('pressure_raw', '')})")
                context_parts.append(f"- Flow Speed: {m.get('flow_cm_s_min')} - {m.get('flow_cm_s_max')} cm/s ({m.get('flow_raw', '')})")
                context_parts.append(f"- Key Finding: {m.get('main_finding')}")
                context_parts.append(f"- Citations: {m.get('pages')}")
                context_parts.append("")
                
        # 3. Microgravity Literature Chunks
        context_parts.append("### RETRIEVED RESEARCH PASSAGES & EXPERIMENT TABLES:")
        for idx, res in enumerate(search_results, start=1):
            source_tag = f"[{res['source_id']}, Page {res['page']}]"
            context_parts.append(f"--- [Passage {idx} | Source: {source_tag} | Score: {res['rrf_score']:.4f}] ---")
            context_parts.append(res["text"])
            context_parts.append("")
            
        return {
            "query": query,
            "assembled_context": "\n".join(context_parts),
            "search_results": search_results,
            "golden_matches": golden_matches,
            "guardrails": guardrails
        }

if __name__ == "__main__":
    engine = CombustionQueryEngine()
    test_q = "How does forced air flow affect PMMA flammability in BASS-II compared to normal gravity?"
    res = engine.build_rag_context(test_q, top_k=3)
    print("\n" + "="*70)
    print("QUERY:", res["query"])
    print("="*70)
    print(res["assembled_context"][:2000])
    print("...")
