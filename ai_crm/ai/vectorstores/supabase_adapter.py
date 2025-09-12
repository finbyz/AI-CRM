from .base import BaseVectorStore
from .registry import register_vector_store
from langchain_postgres import PGVector
from sqlalchemy import create_engine

@register_vector_store("supabase")
class SupabaseAdapter(BaseVectorStore):
    def __init__(self, kb_name: str, embeddings, api_key: str = None, connection_string: str = None, **kwargs):
        super().__init__(kb_name, embeddings, api_key, **kwargs)
        if not connection_string:
            raise ValueError("connection_string is required for SupabaseAdapter")
        self.vs = PGVector(collection_name=kb_name, embedding_function=embeddings, connection_string=connection_string)

    def upsert(self, texts, metadatas, ids):
        self.vs.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        return len(texts)

    def search(self, query, k=5):
        docs_and_scores = self.vs.similarity_search_with_score(query, k=k)
        return [
            {"id": d.metadata.get("id"), "score": score, "metadata": d.metadata}
            for d, score in docs_and_scores
        ]
