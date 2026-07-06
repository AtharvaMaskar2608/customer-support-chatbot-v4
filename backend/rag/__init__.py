"""Hybrid RAG retrieval package.

Public entrypoint: ``from backend.rag import rag_search``.
"""

from backend.rag.search import rag_search

__all__ = ["rag_search"]
