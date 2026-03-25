from store.embeddings import EmbeddingModel
from store.vector_store import VectorStore
from store.bm25_store import BM25Store


class HybridRetriever:
    def __init__(self, embedding_model: EmbeddingModel, vector_store: VectorStore | None = None, bm25_store: BM25Store | None = None):
        self.embedding_model = embedding_model
        self.vector_store = vector_store or VectorStore(dimension=embedding_model.dimension)
        self.bm25_store = bm25_store or BM25Store()
        self._all_transactions: list[dict] = []

    def get_all(self) -> list[dict]:
        return list(self._all_transactions)

    @staticmethod
    def _build_text(txn: dict) -> str:
        return "{} {} {} {} {}".format(
            txn["date"],
            txn["description"],
            txn["amount"],
            txn["direction"],
            txn.get("category") or "",
        ).strip()

    def add_transaction(self, transaction: dict):
        self.add_transactions([transaction])

    def add_transactions(self, transactions: list[dict]):
        texts = [self._build_text(txn) for txn in transactions]
        embeddings = self.embedding_model.embed(texts)
        for i, txn in enumerate(transactions):
            self._all_transactions.append(txn)
            self.vector_store.add(embeddings[i], txn)
            self.bm25_store.add(texts[i], txn)

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
