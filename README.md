# StatementScope

![CI](https://github.com/tan274/StatementScope/actions/workflows/ci.yml/badge.svg)

An MCP server that connects Claude to your local bank statements. Load a CSV or PDF, ask natural-language questions, and get answers backed by a hybrid retrieval pipeline.

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/tan274/StatementScope.git
cd StatementScope
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Add your API key

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

### 3. Connect to Claude

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "statementscope": {
      "command": "python",
      "args": ["/absolute/path/to/StatementScope/server.py"]
    }
  }
}
```

**Claude Code:**
```bash
claude mcp add statementscope python /absolute/path/to/StatementScope/server.py
```

---

## Demo

```
Load my statement from /home/user/Downloads/chase_april.pdf
Load my statement from /home/user/Downloads/usbank_august.pdf
Categorize my transactions
Show me grocery spending
How much did I spend on food in April 2025?
Show me all transactions at CVS
What subscriptions am I paying for?
```

---

## Supported Banks

| Bank | CSV | PDF |
|------|-----|-----|
| Chase | ✅ | ✅ |
| Bank of America | ✅ | ✅ |
| Wells Fargo | — | ✅ |
| Citi | — | ✅ |
| Capital One | — | ✅ |
| US Bank | — | ✅ |
| Other | ⚠️ best-effort | ✅ |

Chase and Bank of America have explicit CSV parsers. Other CSV formats fall back to a generic parser that infers columns by header name — it works for simple formats but may fail on non-standard exports.

---

## How It Works

**Ingestion**
Transactions are parsed from CSV or PDF into a consistent format with fields for date, description, amount, direction, category, and source file. For PDFs, Claude reads the document and returns a structured list of transactions.

**Indexing**
Each transaction is turned into a searchable text string and embedded with `all-MiniLM-L6-v2` (SentenceTransformers) for semantic search in FAISS. The same text is also indexed in BM25 for keyword search.

**Retrieval**
When a question comes in, Claude Haiku first decides whether it needs all transactions or just the most relevant ones. For targeted questions, both the semantic index and keyword index are searched independently, and their results are combined using Reciprocal Rank Fusion (RRF). This covers cases where keyword search misses meaning ("gasoline" vs Shell/Chevron) and where semantic search misses exact names.

**Answering**
Common questions like totals, category breakdowns, top merchants, and date-filtered sums are answered locally when they match supported handlers — no API call needed. Questions that need language understanding are sent to Claude with the relevant transactions as context.

**Categorization**
Uncategorized transactions are sent to Claude in batches of 100, which assigns a category to each one. Categories are saved back to the transaction list and both indexes are rebuilt so category-based searches work right away.

**Persistence**
Loaded transactions are saved to a local SQLite database and restored automatically on server startup.

---

## Retrieval Benchmark

Evaluated BM25-only, FAISS-only, and hybrid RRF on 10 labeled queries across 160 transactions from 6 sample bank statements. A hit means at least one correct transaction appeared in the top-k results.

| Query | BM25@1 | BM25@3 | BM25@5 | FAISS@1 | FAISS@3 | FAISS@5 | Hybrid@1 | Hybrid@3 | Hybrid@5 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| grocery store | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| electric utility bill | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| coffee shop | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| gasoline | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| streaming subscription | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CVSS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CVS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| PSEG | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| PG&E | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| payroll direct deposit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Hit rate** | **90%** | **90%** | **90%** | **100%** | **100%** | **100%** | **100%** | **100%** | **100%** |

BM25 missed "gasoline" entirely — the word doesn't appear in Shell/Chevron/ARCO descriptions — while FAISS and hybrid found them by meaning. Hybrid matched the strongest method on every query.

Run the benchmark: `python eval_retrieval.py`

---

## Tools / Resources / Prompts

| Tool | Description |
|------|-------------|
| `load_statement(file_path)` | Parse and index a CSV or PDF statement |
| `query_transactions(question)` | Semantic + keyword search over transactions |
| `get_spending_summary(period)` | Local computation of totals and category breakdown |
| `categorize_transactions()` | Batch AI categorization of uncategorized transactions |
| `clear_statements()` | Remove all loaded statements and reset to a clean state |

**Resources:** `statements://loaded` · `statements://summary`

**Prompts:** `monthly_report`

---

## Privacy

StatementScope does not send data to any third-party financial services. There is no Plaid integration, no cloud storage, and no external database.

It does use the Anthropic API for PDF text extraction, query answering, and transaction categorization. Transaction descriptions and amounts are included in those API calls.

---

## Current Limitations

- **Scale** — not designed for very large transaction histories.

---

## License

MIT
