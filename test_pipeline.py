from parsers.csv_parser import parse_csv
from store.embeddings import EmbeddingModel
from store.vector_store import VectorStore
from store.bm25_store import BM25Store
from rag.retriever import HybridRetriever
from rag.query_engine import retrieve_and_answer

def main():
    chase_txns = parse_csv("sample_data/chase_sample.csv")
    bofa_txns = parse_csv("sample_data/bofa_sample.csv")
    transactions = chase_txns + bofa_txns
    print(f"Loaded {len(chase_txns)} transactions from Chase, {len(bofa_txns)} from BofA ({len(transactions)} total)")

    embedding_model = EmbeddingModel()
    vector_store = VectorStore()
    bm25_store = BM25Store()
    retriever = HybridRetriever(embedding_model, vector_store, bm25_store)

    retriever.add_transactions(transactions)

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
