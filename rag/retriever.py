from store.embeddings import EmbeddingModel
from store.vector_store import VectorStore
from store.bm25_store import BM25Store


class HybridRetriever:
    def __init__(self, embedding_model: EmbeddingModel, vector_store: VectorStore, bm25_store: BM25Store):
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self._all_transactions: list[dict] = []

    def get_all(self) -> list[dict]:
        return list(self._all_transactions)

    def add_transaction(self, transaction: dict):
        self._all_transactions.append(transaction)
        text = "{} {} {} {} {}".format(
            transaction["date"],
            transaction["description"],
            transaction["amount"],
            transaction["direction"],
            transaction.get("category") or "",
        ).strip()
        emb = self.embedding_model.embed([text])[0]
        self.vector_store.add(emb, transaction)
        self.bm25_store.add(text, transaction)

    def add_transactions(self, transactions: list[dict]):
        for txn in transactions:
            self.add_transaction(txn)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_emb = self.embedding_model.embed_query(query)
        vector_results = self.vector_store.search(query_emb, top_k=top_k)
        bm25_results = self.bm25_store.search(query, top_k=top_k)

        rrf_scores: dict[str, float] = {}
        rrf_txns: dict[str, dict] = {}

        for rank, result in enumerate(vector_results):
            txn = result["metadata"]
            tid = txn["id"]
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + 1.0 / (rank + 60)
            rrf_txns[tid] = txn

        for rank, result in enumerate(bm25_results):
            txn = result["metadata"]
            tid = txn["id"]
            rrf_scores[tid] = rrf_scores.get(tid, 0.0) + 1.0 / (rank + 60)
            rrf_txns[tid] = txn

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [rrf_txns[tid] for tid, _ in ranked[:top_k]]
