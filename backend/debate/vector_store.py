import os
import uuid
import logging
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger("argus.vector_store")

_vector_store_instance = None


class ChromaVectorStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.CHROMA_DB_PATH
        self.client = None
        self.evidence_coll = None
        self.history_coll = None
        self._init_db()

    def _init_db(self):
        try:
            import chromadb
            os.makedirs(self.db_path, exist_ok=True)
            self.client = chromadb.PersistentClient(path=self.db_path)
            self.evidence_coll = self.client.get_or_create_collection(
                name=config.CHROMA_EVIDENCE_COLLECTION
            )
            self.history_coll = self.client.get_or_create_collection(
                name=config.CHROMA_HISTORY_COLLECTION
            )
            logger.info(f"ChromaDB initialized at: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB at {self.db_path}: {e}")
            self.client = None
            self.evidence_coll = None
            self.history_coll = None

    @property
    def is_available(self) -> bool:
        return self.client is not None and self.evidence_coll is not None

    def add_evidence(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: Optional[List[str]] = None) -> bool:
        if not self.is_available:
            return False
        try:
            if ids is None:
                ids = [f"ev-{uuid.uuid4().hex[:10]}" for _ in documents]
            self.evidence_coll.add(documents=documents, metadatas=metadatas, ids=ids)
            return True
        except Exception as e:
            logger.error(f"Error adding evidence to ChromaDB: {e}")
            return False

    def query_evidence(self, query: str, top_k: int = None, stance: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        top_k = top_k or config.RAG_TOP_K
        try:
            where_clause = {"stance": stance} if stance else None
            results = self.evidence_coll.query(
                query_texts=[query],
                n_results=top_k,
                where=where_clause
            )
            retrieved = []
            if results and results.get("documents") and results["documents"][0]:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
                distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                for doc, meta, doc_id, dist in zip(docs, metas, ids, distances):
                    retrieved.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta,
                        "distance": dist
                    })
            return retrieved
        except Exception as e:
            logger.error(f"Error querying ChromaDB evidence: {e}")
            return []

    def add_debate_turn(self, debate_id: str, topic: str, round_num: int, sub_round: int, side: str, text: str) -> bool:
        if not self.is_available or not text.strip():
            return False
        try:
            doc_id = f"turn-{debate_id}-r{round_num}-s{sub_round}-{side}"
            metadata = {
                "debate_id": debate_id,
                "topic": topic,
                "round": round_num,
                "sub_round": sub_round,
                "side": side
            }
            self.history_coll.add(documents=[text], metadatas=[metadata], ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"Error indexing debate turn in ChromaDB: {e}")
            return False

    def query_similar_rebuttals(self, claim: str, top_k: int = 2) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        try:
            results = self.history_coll.query(
                query_texts=[claim],
                n_results=top_k
            )
            retrieved = []
            if results and results.get("documents") and results["documents"][0]:
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                for doc, meta in zip(docs, metas):
                    retrieved.append({"text": doc, "metadata": meta})
            return retrieved
        except Exception as e:
            logger.error(f"Error querying debate history: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "unavailable", "evidence_count": 0, "history_count": 0}
        try:
            return {
                "status": "online",
                "evidence_count": self.evidence_coll.count(),
                "history_count": self.history_coll.count(),
                "db_path": self.db_path
            }
        except Exception as e:
            return {"status": f"error: {e}", "evidence_count": 0, "history_count": 0}

    def seed_default_knowledge(self) -> int:
        """Seed starter facts and evidence if collection is empty."""
        if not self.is_available:
            return 0
        if self.evidence_coll.count() > 0:
            return 0
        
        from debate.seed_evidence import DEFAULT_EVIDENCE_CORPUS
        docs = [item["text"] for item in DEFAULT_EVIDENCE_CORPUS]
        metas = [item["metadata"] for item in DEFAULT_EVIDENCE_CORPUS]
        ids = [f"seed-{i+1:03d}" for i in range(len(DEFAULT_EVIDENCE_CORPUS))]
        
        self.add_evidence(documents=docs, metadatas=metas, ids=ids)
        logger.info(f"Seeded {len(docs)} default evidence items into ChromaDB.")
        return len(docs)


def get_vector_store() -> ChromaVectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = ChromaVectorStore()
    return _vector_store_instance
