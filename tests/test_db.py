"""
Tests for SQLite persistence layer.
No API calls — uses a temporary database file.

Run: pytest tests/test_db.py -v
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store.db as db_module
from store.db import init_db, save_transactions, load_transactions, update_categories, clear_transactions
from store.embeddings import EmbeddingModel
from rag.retriever import HybridRetriever
from config import EMBEDDING_MODEL

SAMPLE_TRANSACTIONS = [
    {
        "id": "abc123_001",
        "date": "2025-01-15",
        "description": "STARBUCKS",
        "amount": 5.75,
        "direction": "debit",
        "category": None,
        "balance": None,
        "source_file": "/tmp/test.csv",
        "provider": "chase",
    },
    {
        "id": "abc123_002",
        "date": "2025-01-16",
        "description": "NETFLIX",
        "amount": 15.99,
        "direction": "debit",
        "category": None,
        "balance": 1200.50,
        "source_file": "/tmp/test.csv",
        "provider": "chase",
    },
]


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._original_path = db_module.DB_PATH
        db_module.DB_PATH = self.tmp.name
        init_db()

    def tearDown(self):
        db_module.DB_PATH = self._original_path
        os.unlink(self.tmp.name)

    def test_save_and_load(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        loaded = load_transactions()
        self.assertEqual(len(loaded), 2)
        ids = {t["id"] for t in loaded}
        self.assertIn("abc123_001", ids)
        self.assertIn("abc123_002", ids)

    def test_fields_preserved(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        loaded = {t["id"]: t for t in load_transactions()}
        t = loaded["abc123_001"]
        self.assertEqual(t["date"], "2025-01-15")
        self.assertEqual(t["description"], "STARBUCKS")
        self.assertAlmostEqual(t["amount"], 5.75)
        self.assertEqual(t["direction"], "debit")
        self.assertIsNone(t["category"])
        self.assertIsNone(t["balance"])
        self.assertEqual(t["provider"], "chase")

    def test_balance_preserved(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        loaded = {t["id"]: t for t in load_transactions()}
        self.assertAlmostEqual(loaded["abc123_002"]["balance"], 1200.50)

    def test_duplicate_ignored(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        save_transactions(SAMPLE_TRANSACTIONS)
        loaded = load_transactions()
        self.assertEqual(len(loaded), 2)

    def test_update_categories(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        categorized = [
            {**SAMPLE_TRANSACTIONS[0], "category": "Food"},
            {**SAMPLE_TRANSACTIONS[1], "category": "Entertainment"},
        ]
        update_categories(categorized)
        loaded = {t["id"]: t for t in load_transactions()}
        self.assertEqual(loaded["abc123_001"]["category"], "Food")
        self.assertEqual(loaded["abc123_002"]["category"], "Entertainment")

    def test_clear(self):
        save_transactions(SAMPLE_TRANSACTIONS)
        clear_transactions()
        self.assertEqual(load_transactions(), [])

    def test_empty_load(self):
        self.assertEqual(load_transactions(), [])


class TestPersistenceIntegration(unittest.TestCase):
    """
    Simulates the full startup-reload flow:
    save transactions to DB, rebuild retriever from DB,
    assert retriever works, then clear and assert both
    memory and DB are empty.
    """

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._original_path = db_module.DB_PATH
        db_module.DB_PATH = self.tmp.name
        init_db()
        self.embedding_model = EmbeddingModel(EMBEDDING_MODEL)

    def tearDown(self):
        db_module.DB_PATH = self._original_path
        os.unlink(self.tmp.name)

    def test_startup_reload(self):
        # Save transactions to DB (simulates load_statement)
        save_transactions(SAMPLE_TRANSACTIONS)

        # Simulate server startup: load from DB and rebuild retriever
        persisted = load_transactions()
        all_transactions = list(persisted)
        retriever = HybridRetriever(self.embedding_model)
        retriever.add_transactions(persisted)

        # Memory is populated
        self.assertEqual(len(all_transactions), 2)

        # Retriever can search
        results = retriever.search("starbucks", top_k=5)
        self.assertTrue(any("STARBUCKS" in r["description"].upper() for r in results))

    def test_clear_resets_db_and_memory(self):
        save_transactions(SAMPLE_TRANSACTIONS)

        # Simulate startup
        persisted = load_transactions()
        all_transactions = list(persisted)
        retriever = HybridRetriever(self.embedding_model)
        retriever.add_transactions(persisted)

        # Clear (simulates clear_statements tool)
        all_transactions.clear()
        retriever = None
        clear_transactions()

        # Both memory and DB are empty
        self.assertEqual(all_transactions, [])
        self.assertIsNone(retriever)
        self.assertEqual(load_transactions(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
