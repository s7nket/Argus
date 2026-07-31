import unittest
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from debate.vector_store import ChromaVectorStore


class TestChromaVectorStore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.vs = ChromaVectorStore(db_path=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initialization(self):
        self.assertTrue(self.vs.is_available)
        stats = self.vs.get_stats()
        self.assertEqual(stats["status"], "online")
        self.assertEqual(stats["evidence_count"], 0)

    def test_add_and_query_evidence(self):
        docs = [
            "The EU AI Act mandates risk assessments for high-risk systems.",
            "Athens pioneered democratic assemblies in 508 BCE."
        ]
        metas = [
            {"topic": "AI", "source": "EU Law"},
            {"topic": "History", "source": "Thucydides"}
        ]
        self.vs.add_evidence(docs, metas)
        stats = self.vs.get_stats()
        self.assertEqual(stats["evidence_count"], 2)

        results = self.vs.query_evidence("artificial intelligence regulation", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("EU AI Act", results[0]["text"])

    def test_add_and_query_debate_turn(self):
        self.vs.add_debate_turn(
            debate_id="test-1",
            topic="AI Regulation",
            round_num=1,
            sub_round=1,
            side="pro",
            text="AI risks require immediate legislative frameworks to prevent bias."
        )
        stats = self.vs.get_stats()
        self.assertEqual(stats["history_count"], 1)

        rebuttals = self.vs.query_similar_rebuttals("legislative AI regulation", top_k=1)
        self.assertEqual(len(rebuttals), 1)
        self.assertIn("legislative frameworks", rebuttals[0]["text"])

if __name__ == "__main__":
    unittest.main()
