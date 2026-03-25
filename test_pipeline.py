from config import EMBEDDING_MODEL
from parsers.csv_parser import parse_csv
from store.embeddings import EmbeddingModel
from store.bm25_store import _tokenize
from rag.retriever import HybridRetriever
from rag.query_engine import retrieve_and_answer


def run_assertions(chase_txns: list[dict], bofa_txns: list[dict], retriever: HybridRetriever):
    failures = []

    def check(name: str, condition: bool, detail: str = ""):
        if not condition:
            failures.append(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))

    # --- Fix 1: BM25 lazy build — index should not exist yet before first search ---
    check("bm25 not built before search", retriever.bm25_store._index is None)
    check("bm25 dirty before search",     retriever.bm25_store._dirty is True)

    # --- Fix 2: VectorStore dimension matches embedding model ---
    check(
        "vector store dimension matches model",
        retriever.vector_store.index.d == retriever.embedding_model.dimension,
        f"index.d={retriever.vector_store.index.d}, model.dimension={retriever.embedding_model.dimension}",
    )

    # --- Fix 3: BM25 tokenization strips punctuation ---
    check("tokenize strips dot",      "com" in _tokenize("NETFLIX.COM"),             f"got {_tokenize('NETFLIX.COM')}")
    check("tokenize strips asterisk", "mk1ab6te1" in _tokenize("AMAZON.COM*MK1AB6TE1"), f"got {_tokenize('AMAZON.COM*MK1AB6TE1')}")

    # --- Fix 4: Embedding model dimension matches expected model ---
    check("embedding model dimension is 384", retriever.embedding_model.dimension == 384,
          f"got {retriever.embedding_model.dimension}")

    # --- Parser: counts ---
    check("chase count", len(chase_txns) == 30, f"got {len(chase_txns)}")
    check("bofa count", len(bofa_txns) == 20, f"got {len(bofa_txns)}")

    # --- Parser: Chase first transaction fields ---
    t = chase_txns[0]
    check("chase[0] date",        t["date"] == "2025-01-02",         f"got {t['date']!r}")
    check("chase[0] description", t["description"] == "CHIPOTLE MEXICAN GRILL", f"got {t['description']!r}")
    check("chase[0] amount",      t["amount"] == 12.47,              f"got {t['amount']}")
    check("chase[0] direction",   t["direction"] == "debit",         f"got {t['direction']!r}")
    check("chase[0] provider",    t["provider"] == "chase",          f"got {t['provider']!r}")

    # --- Parser: Chase credit detection ---
    payroll = chase_txns[13]   # row 14 (0-indexed): DIRECT DEPOSIT - ACME CORP
    check("chase payroll direction", payroll["direction"] == "credit", f"got {payroll['direction']!r}")
    check("chase payroll amount",    payroll["amount"] == 2847.50,     f"got {payroll['amount']}")

    amazon_return = chase_txns[16]  # row 17: AMAZON.COM*RETURN
    check("amazon return direction", amazon_return["direction"] == "credit", f"got {amazon_return['direction']!r}")
    check("amazon return amount",    amazon_return["amount"] == 34.99,       f"got {amazon_return['amount']}")

    # --- Parser: BofA balance field and provider ---
    b = bofa_txns[0]
    check("bofa[0] balance",  b["balance"] == 1436.53, f"got {b['balance']}")
    check("bofa[0] provider", b["provider"] == "bofa", f"got {b['provider']!r}")

    # --- Retrieval: starbucks query returns starbucks transactions ---
    results = retriever.search("starbucks", top_k=5)
    # Fix 1 (cont): after first search the BM25 index should now be built
    check("bm25 built after search",    retriever.bm25_store._index is not None)
    check("bm25 not dirty after search", retriever.bm25_store._dirty is False)
    check("starbucks results non-empty", len(results) > 0)
    check(
        "starbucks results on-topic",
        any("STARBUCKS" in r["description"].upper() for r in results),
        f"top result was {results[0]['description']!r}" if results else "no results",
    )

    # --- Retrieval: netflix query ---
    results = retriever.search("netflix", top_k=5)
    check("netflix results non-empty", len(results) > 0)
    check(
        "netflix results on-topic",
        any("NETFLIX" in r["description"].upper() for r in results),
        f"top result was {results[0]['description']!r}" if results else "no results",
    )

    # --- Retrieval: get_all() covers all loaded transactions ---
    check("get_all count", len(retriever.get_all()) == 50, f"got {len(retriever.get_all())}")

    if failures:
        print("ASSERTION FAILURES:")
        for f in failures:
            print(f)
        raise SystemExit(1)

    print("All assertions passed.")


def main():
    chase_txns = parse_csv("sample_data/chase_sample.csv")
    bofa_txns = parse_csv("sample_data/bofa_sample.csv")
    transactions = chase_txns + bofa_txns
    print(f"Loaded {len(chase_txns)} transactions from Chase, {len(bofa_txns)} from BofA ({len(transactions)} total)")

    embedding_model = EmbeddingModel(EMBEDDING_MODEL)
    retriever = HybridRetriever(embedding_model)

    retriever.add_transactions(transactions)

    run_assertions(chase_txns, bofa_txns, retriever)
    print()

    while True:
        question = input("\nAsk a question (or 'quit'): ").strip()
        if question.lower() == "quit":
            break
        if not question:
            continue

        print("\n--- Claude's answer ---")
        answer = retrieve_and_answer(retriever, question)
        print(answer)

if __name__ == "__main__":
    main()
