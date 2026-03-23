"""
humphi_search/search.py

Natural language file search using ChromaDB vectors.
Call search() with plain English and get back matching file paths.
"""

import sys
from pathlib import Path
from typing import Optional
import logging

log = logging.getLogger("humphi.search")

CHROMA_DIR = Path.home() / ".humphi" / "vectordb"


class HumphiSearch:
    """
    Natural language file search.
    Converts query to vector, finds closest matches in ChromaDB.
    """

    def __init__(self):
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.get_or_create_collection(
                name="humphi_files",
                embedding_function=self.ef,
            )
        except ImportError:
            log.error("Run: pip install chromadb sentence-transformers")
            sys.exit(1)

    def search(
        self,
        query: str,
        n_results: int = 10,
        file_type: Optional[str] = None,  # "document" or "image"
        extension: Optional[str] = None,  # ".pdf", ".docx" etc
    ) -> list[dict]:
        """
        Search for files using natural language.

        Args:
            query: plain English description e.g. "invoice for Sharma last month"
            n_results: max results to return
            file_type: filter by "document" or "image"
            extension: filter by extension e.g. ".pdf"

        Returns:
            List of dicts with path, filename, score, metadata
        """
        if self.collection.count() == 0:
            return []

        # Build where filter
        where = {}
        if file_type:
            where["type"] = file_type
        if extension:
            where["extension"] = extension.lower()

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count()),
                where=where if where else None,
                include=["metadatas", "distances", "documents"],
            )

            matches = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                distance = results["distances"][0][i]
                # Convert distance to similarity score (0-100)
                score = round((1 - distance) * 100, 1)

                matches.append({
                    "path": meta.get("path", ""),
                    "filename": meta.get("filename", ""),
                    "extension": meta.get("extension", ""),
                    "folder": meta.get("folder", ""),
                    "type": meta.get("type", ""),
                    "modified": meta.get("modified", ""),
                    "size_bytes": meta.get("size_bytes", 0),
                    "score": score,
                    "preview": results["documents"][0][i][:200],
                })

            # Sort by score descending
            matches.sort(key=lambda x: x["score"], reverse=True)
            return matches

        except Exception as e:
            log.error(f"Search error: {e}")
            return []

    def count(self) -> int:
        return self.collection.count()

    def delete_file(self, path: str):
        """Remove a file from search index."""
        try:
            self.collection.delete(ids=[path])
        except Exception:
            pass
