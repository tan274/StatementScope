import numpy as np
import faiss


class VectorStore:
    def __init__(self, dimension: int = 384):
        self.index = faiss.IndexFlatL2(dimension)
        self.metadata: list[dict] = []

    def add(self, embedding: np.ndarray, metadata: dict):
        self.index.add(embedding.reshape(1, -1))
        self.metadata.append(metadata)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> list[dict]:
        top_k = min(top_k, len(self.metadata))
        distances, indices = self.index.search(query_embedding.reshape(1, -1), top_k)
        return [
            {"metadata": self.metadata[idx], "score": float(distances[0][i])}
            for i, idx in enumerate(indices[0])
        ]

    def __len__(self) -> int:
        return self.index.ntotal


if __name__ == "__main__":
    from store.embeddings import EmbeddingModel

    model = EmbeddingModel()
    store = VectorStore()

    texts = ["coffee at starbucks", "amazon purchase", "netflix subscription"]
    for i, text in enumerate(texts):
        emb = model.embed([text])
        store.add(emb[0], {"text": text, "index": i})

    query_emb = model.embed_query("where did I buy coffee")
    results = store.search(query_emb, top_k=2)
    for r in results:
        print(r["metadata"]["text"], "score:", r["score"])
