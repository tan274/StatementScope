from rank_bm25 import BM25Okapi


class BM25Store:
    def __init__(self):
        self.corpus: list[list[str]] = []
        self.documents: list[dict] = []
        self._index: BM25Okapi | None = None

    def add(self, text: str, metadata: dict):
        tokens = text.lower().split()
        self.corpus.append(tokens)
        self.documents.append(metadata)
        self._index = BM25Okapi(self.corpus)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._index:
            return []
        tokens = query.lower().split()
        scores = self._index.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score > 0:
                results.append({"metadata": self.documents[idx], "score": float(score)})
        return results

    def __len__(self) -> int:
        return len(self.documents)


if __name__ == "__main__":
    store = BM25Store()
    texts = ["coffee at starbucks", "amazon purchase", "netflix subscription"]
    for text in texts:
        store.add(text, {"text": text})

    print("Query: amazon")
    for r in store.search("amazon"):
        print(" ", r["metadata"]["text"], "score:", r["score"])

    print("Query: subscription")
    for r in store.search("subscription"):
        print(" ", r["metadata"]["text"], "score:", r["score"])
