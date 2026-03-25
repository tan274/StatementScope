import re
from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


class BM25Store:
    def __init__(self):
        self.corpus: list[list[str]] = []
        self.documents: list[dict] = []
        self._index: BM25Okapi | None = None
        self._dirty: bool = False

    def add(self, text: str, metadata: dict):
        self.corpus.append(_tokenize(text))
        self.documents.append(metadata)
        self._dirty = True

    def _build(self):
        self._index = BM25Okapi(self.corpus)
        self._dirty = False

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self.corpus:
            return []
        if self._dirty:
            self._build()
        tokens = _tokenize(query)
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
