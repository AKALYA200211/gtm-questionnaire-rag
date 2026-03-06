from rank_bm25 import BM25Okapi
import re

def tokenize(s: str):
    return re.findall(r"[A-Za-z0-9]+", s.lower())

def chunk_text(text: str, chunk_size_words=220):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size_words):
        chunk = " ".join(words[i:i+chunk_size_words]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks

class BM25Retriever:
    def __init__(self, chunks_meta):
        self.chunks_meta = chunks_meta
        corpus = [tokenize(c["text"]) for c in chunks_meta]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k=3):
        q = tokenize(query)
        scores = self.bm25.get_scores(q)
        ranked = sorted(list(enumerate(scores)), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            item = self.chunks_meta[idx].copy()
            item["score"] = float(score)
            results.append(item)
        return results