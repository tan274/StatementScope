# StatementScope

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

Chase and Bank of America have explicit CSV parsers. Other CSV formats fall back to a generic parser that infers columns by header name — it works for simple formats but may fail on non-standard exports. PDFs from any bank are parsed by Claude with no templates required.

---

## How It Works

**Ingestion**
Transactions are parsed from CSV or PDF into a normalized schema (`date`, `description`, `amount`, `direction`, `category`, `source_file`). PDFs are sent to Claude with `tool_choice` forced structured extraction — Claude must return a typed transaction array, no free-text parsing.

**Indexing**
Each transaction description is embedded with `all-MiniLM-L6-v2` (SentenceTransformers) and stored in a FAISS flat index. The same transactions are also indexed in BM25. Both indexes are held in memory.

**Retrieval**
Incoming queries are classified by Claude Haiku — a cheap binary call that decides whether the question needs all transactions or just the most relevant ones. For targeted queries, FAISS and BM25 are searched independently and their ranked results are fused with Reciprocal Rank Fusion (RRF). This covers cases where pure semantic search misses exact merchant names and pure keyword search misses semantic intent.

**Answering**
Retrieved transactions are formatted as a context block and passed to Claude with a strict system prompt. Common aggregate questions (totals, category breakdowns, top merchants, date-filtered sums) are intercepted before reaching Claude and computed locally when they match supported local handlers — no API call needed. Questions that require language understanding are sent to the model. Simple summaries are also available locally via `get_spending_summary(period)`.

**Categorization**
Uncategorized transactions are batched in groups of 100 and sent to Claude with `tool_choice` forced output. Categories are written back in-place to the in-memory transaction list.

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

On this dataset, dense retrieval was already strong. BM25 missed "gasoline" entirely — zero token overlap with Shell/Chevron/ARCO descriptions — while FAISS and hybrid found them semantically. Hybrid matches the strongest method on every query without regressions. BM25 remains useful for exact-token lookups, especially when merchant strings are abbreviated or irregular.

Run the benchmark: `python eval_retrieval.py`

---

## Tools / Resources / Prompts

| Tool | Description |
|------|-------------|
| `load_statement(file_path)` | Parse and index a CSV or PDF statement |
| `query_transactions(question)` | Semantic + keyword search over transactions |
| `get_spending_summary(period)` | Local computation of totals and category breakdown |
| `categorize_transactions()` | Batch AI categorization of uncategorized transactions |

**Resources:** `statements://loaded` · `statements://summary`

**Prompts:** `monthly_report`

---

## Privacy

StatementScope does not send data to any third-party financial services. There is no Plaid integration, no cloud storage, and no external database.

It does use the Anthropic API for PDF text extraction, query answering, and transaction categorization. Transaction descriptions and amounts are included in those API calls.

---

## Current Limitations

- **No persistence** — all loaded statements are in-memory and lost on server restart.
- **Scale** — aggregate queries are computed locally, but semantic queries that need Claude still send retrieved transactions to the API. Not designed for very large histories.

---

## License

MIT
