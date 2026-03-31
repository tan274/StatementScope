"""
Day 9 test suite for StatementScope parsers.

CSV tests: fast, no API calls.
PDF tests: call Claude API — each PDF costs a small amount.

Run all:  python tests/test_parsers.py
Run fast: python tests/test_parsers.py --no-pdf
"""

import sys
import os
import unittest

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.csv_parser import parse_csv
from parsers.pdf_parser import parse_pdf

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "sample_data")

REQUIRED_FIELDS = {"id", "date", "description", "amount", "direction", "category", "balance", "source_file", "provider"}
VALID_DIRECTIONS = {"debit", "credit"}


def assert_valid_transactions(test: unittest.TestCase, txns: list[dict], label: str):
    test.assertIsInstance(txns, list, f"{label}: result should be a list")
    test.assertGreater(len(txns), 0, f"{label}: should have at least one transaction")

    for i, t in enumerate(txns):
        loc = f"{label}[{i}]"

        # Required fields present
        for field in REQUIRED_FIELDS:
            test.assertIn(field, t, f"{loc}: missing field '{field}'")

        # Date is YYYY-MM-DD
        test.assertRegex(t["date"], r"^\d{4}-\d{2}-\d{2}$", f"{loc}: date not in YYYY-MM-DD format")

        # Amount is a non-negative float
        test.assertIsInstance(t["amount"], float, f"{loc}: amount should be float")
        test.assertGreaterEqual(t["amount"], 0, f"{loc}: amount should be non-negative")

        # Direction is valid
        test.assertIn(t["direction"], VALID_DIRECTIONS, f"{loc}: invalid direction '{t['direction']}'")

        # ID is a non-empty string
        test.assertIsInstance(t["id"], str, f"{loc}: id should be string")
        test.assertTrue(t["id"].strip(), f"{loc}: id should not be empty")



# ─── CSV Tests ────────────────────────────────────────────────────────────────

class TestChaseCSV(unittest.TestCase):
    def setUp(self):
        self.txns = parse_csv(os.path.join(SAMPLE, "chase_sample.csv"))

    def test_returns_transactions(self):
        assert_valid_transactions(self, self.txns, "Chase CSV")

    def test_provider_is_chase(self):
        for t in self.txns:
            self.assertEqual(t["provider"], "chase", f"Expected provider=chase, got {t['provider']}")

    def test_category_passthrough(self):
        # Chase CSVs include a Category column — parser should use it
        categorized = [t for t in self.txns if t["category"] is not None]
        self.assertGreater(len(categorized), 0, "Chase CSV: expected some transactions to have categories from CSV")

    def test_no_negative_amounts(self):
        for t in self.txns:
            self.assertGreaterEqual(t["amount"], 0, f"Negative amount found: {t}")

    def test_unique_ids(self):
        ids = [t["id"] for t in self.txns]
        self.assertEqual(len(ids), len(set(ids)), "Chase CSV: duplicate IDs found")


class TestBofACSV(unittest.TestCase):
    def setUp(self):
        self.txns = parse_csv(os.path.join(SAMPLE, "bofa_sample.csv"))

    def test_returns_transactions(self):
        assert_valid_transactions(self, self.txns, "BofA CSV")

    def test_provider_is_bofa(self):
        for t in self.txns:
            self.assertEqual(t["provider"], "bofa", f"Expected provider=bofa, got {t['provider']}")

    def test_no_negative_amounts(self):
        for t in self.txns:
            self.assertGreaterEqual(t["amount"], 0, f"Negative amount found: {t}")

    def test_unique_ids(self):
        ids = [t["id"] for t in self.txns]
        self.assertEqual(len(ids), len(set(ids)), "BofA CSV: duplicate IDs found")


class TestCSVEdgeCases(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(Exception):
            parse_csv("/nonexistent/path/file.csv")

    def test_ids_are_unique_across_files(self):
        chase = parse_csv(os.path.join(SAMPLE, "chase_sample.csv"))
        bofa = parse_csv(os.path.join(SAMPLE, "bofa_sample.csv"))
        all_ids = [t["id"] for t in chase + bofa]
        self.assertEqual(len(all_ids), len(set(all_ids)), "IDs should be unique across different files")


# ─── PDF Tests (API calls) ────────────────────────────────────────────────────

PDF_FILES = [
    ("BofA_style.pdf",       "BofA PDF"),
    ("Chase_style.pdf",      "Chase PDF"),
    ("WellsFargo_style.pdf", "Wells Fargo PDF"),
    ("Citi_style.pdf",       "Citi PDF"),
    ("CapOne_style.pdf",     "Capital One PDF"),
    ("USBank_style.pdf",     "US Bank PDF"),
]


def make_pdf_test(filename: str, label: str):
    class PDFTest(unittest.TestCase):
        def setUp(self):
            self.path = os.path.join(SAMPLE, filename)
            self.txns = parse_pdf(self.path)
            self.label = label

        def test_returns_transactions(self):
            assert_valid_transactions(self, self.txns, self.label)

        def test_no_negative_amounts(self):
            for t in self.txns:
                self.assertGreaterEqual(t["amount"], 0, f"{self.label}: negative amount in {t}")

        def test_unique_ids(self):
            ids = [t["id"] for t in self.txns]
            self.assertEqual(len(ids), len(set(ids)), f"{self.label}: duplicate IDs found")

        def test_source_file_recorded(self):
            for t in self.txns:
                self.assertEqual(t["source_file"], self.path, f"{self.label}: source_file mismatch")

        def test_has_both_debits_and_credits(self):
            directions = {t["direction"] for t in self.txns}
            self.assertIn("debit", directions, f"{self.label}: no debits found")
            self.assertIn("credit", directions, f"{self.label}: no credits found")

    PDFTest.__name__ = f"Test{label.replace(' ', '')}"
    PDFTest.__qualname__ = PDFTest.__name__
    return PDFTest


class TestPDFEdgeCases(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(Exception):
            parse_pdf("/nonexistent/path/statement.pdf")


# Dynamically register PDF test classes
for _filename, _label in PDF_FILES:
    _cls = make_pdf_test(_filename, _label)
    globals()[_cls.__name__] = _cls


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    skip_pdf = "--no-pdf" in sys.argv
    if skip_pdf:
        sys.argv.remove("--no-pdf")

    if skip_pdf:
        # Load only non-PDF test classes
        suite = unittest.TestSuite()
        for name, obj in list(globals().items()):
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                if "PDF" not in name or name == "TestPDFEdgeCases":
                    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(obj))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
    else:
        print("Running all tests including PDF (API calls). Use --no-pdf to skip.\n")
        unittest.main(verbosity=2)
