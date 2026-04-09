#!/usr/bin/env python3
"""
Retrieval benchmark: BM25-only vs FAISS-only vs Hybrid RRF

Loads all 6 sample PDFs and runs a fixed query set against each retrieval
method independently. Reports hit@3 and hit@5 for each.

Run: python eval_retrieval.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.pdf_parser import parse_pdf
from store.embeddings import EmbeddingModel
from rag.retriever import HybridRetriever
from config import EMBEDDING_MODEL

SAMPLE_PDFS = [
    "sample_data/Chase_style.pdf",
    "sample_data/USBank_style.pdf",
    "sample_data/BofA_style.pdf",
    "sample_data/CapOne_style.pdf",
    "sample_data/Citi_style.pdf",
    "sample_data/WellsFargo_style.pdf",
]

# (query, expected substrings in description)
# Gold labels derived from actual extracted transactions across all 6 PDFs.
# Semantic queries: concept does not appear literally in descriptions.
# Lexical queries: exact or near-exact token match expected.
TEST_CASES = [
    # Semantic — concept not in description text
    ("grocery store",           ["TRADER JOE", "WHOLE FOODS", "SAFEWAY", "KROGER",
                                 "CUB FOODS", "RALPHS", "SPROUTS", "PUBLIX",
                                 "FRED MEYER", "ALDI", "LIDL"]),
    ("electric utility bill",   ["PG&E", "XCEL ENERGY", "GEORGIA POWER",
                                 "SAN DIEGO GAS", "PSEG ELECTRIC", "PORTLAND GENERAL"]),
    ("coffee shop",             ["STARBUCKS", "CARIBOU"]),
    ("gasoline",                ["SHELL", "CHEVRON", "ARCO"]),
    ("streaming subscription",  ["NETFLIX", "SPOTIFY", "HULU", "HBO MAX",
                                 "APPLE.COM", "APPLE ONE", "GOOGLE ONE"]),

    # Lexical — strong exact token match
    ("CVSS",                    ["CVSS"]),
    ("CVS",                     ["CVS"]),
    ("PSEG",                    ["PSEG"]),
    ("PG&E",                    ["PG&E"]),
    ("payroll direct deposit",  ["PAYROLL", "DIR-DEP"]),
]


def score_at_k(results: list[dict], expected: list[str], k: int) -> bool:
    for txn in results[:k]:
        desc = txn["description"].upper()
        if any(e.upper() in desc for e in expected):
            return True
    return False


def main():
    print("Loading statements...")
    all_txns = []
    for path in SAMPLE_PDFS:
        txns = parse_pdf(path)
        all_txns.extend(txns)
        print(f"  {os.path.basename(path)}: {len(txns)} transactions")
    print(f"  Total: {len(all_txns)} transactions\n")

    print("Building retriever (this may take a moment on CPU)...")
    embedding_model = EmbeddingModel(EMBEDDING_MODEL)
    retriever = HybridRetriever(embedding_model)
    retriever.add_transactions(all_txns)
    print("  Done\n")

    col = 28
    header = (
        f"{'Query':<{col}}"
        f"{'BM25@1':>8}{'BM25@3':>8}{'BM25@5':>8}"
        f"{'FAISS@1':>9}{'FAISS@3':>9}{'FAISS@5':>9}"
        f"{'Hybrid@1':>10}{'Hybrid@3':>10}{'Hybrid@5':>10}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)

    totals = [0] * 9

    for query, expected in TEST_CASES:
        q_emb = embedding_model.embed_query(query)
        bm25_res  = [r["metadata"] for r in retriever.bm25_store.search(query, top_k=5)]
        faiss_res = [r["metadata"] for r in retriever.vector_store.search(q_emb, top_k=5)]
        hybrid_res = retriever.search(query, top_k=5)

        scores = [
            score_at_k(bm25_res,   expected, 1),
            score_at_k(bm25_res,   expected, 3),
            score_at_k(bm25_res,   expected, 5),
            score_at_k(faiss_res,  expected, 1),
            score_at_k(faiss_res,  expected, 3),
            score_at_k(faiss_res,  expected, 5),
            score_at_k(hybrid_res, expected, 1),
            score_at_k(hybrid_res, expected, 3),
            score_at_k(hybrid_res, expected, 5),
        ]
        for i, s in enumerate(scores):
            totals[i] += s

        marks = ["✓" if s else "✗" for s in scores]
        print(
            f"{query:<{col}}"
            f"{marks[0]:>8}{marks[1]:>8}{marks[2]:>8}"
            f"{marks[3]:>9}{marks[4]:>9}{marks[5]:>9}"
            f"{marks[6]:>10}{marks[7]:>10}{marks[8]:>10}"
        )

    n = len(TEST_CASES)
    print(sep)
    print(
        f"{'Hit rate':<{col}}"
        f"{totals[0]/n:>8.0%}{totals[1]/n:>8.0%}{totals[2]/n:>8.0%}"
        f"{totals[3]/n:>9.0%}{totals[4]/n:>9.0%}{totals[5]/n:>9.0%}"
        f"{totals[6]/n:>10.0%}{totals[7]/n:>10.0%}{totals[8]/n:>10.0%}"
    )


if __name__ == "__main__":
    main()
