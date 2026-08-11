from .contracts import RetrievedChunk


class NullRetriever:
    def retrieve(self, item_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        return []
