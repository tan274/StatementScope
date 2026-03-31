# StatementScope

A free, privacy-first MCP server that lets Claude analyze your bank statements locally. Download a CSV or PDF from your bank, point StatementScope at it, and ask natural language questions about your spending — no Plaid, no third-party data sharing, no per-page fees.

---

## Why?

**Dropping a file into Claude chat** works for one small statement. It breaks down with 6–12 months of data across multiple banks — the transactions won't fit in context. StatementScope indexes transactions with a hybrid RAG pipeline and retrieves only what's relevant.

**Plaid-based tools** (BankSync, Monarch) require sharing your bank login with a third party. Many people won't do this.

**Bankstatemently** charges per page and processes your data in their cloud.

**Generic CSV MCP servers** don't understand financial data — they can't answer "what did I spend on food?" because they have no concept of categories or transaction direction.

StatementScope is free, runs locally, and is built specifically for financial data.

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/tan274/StatementScope.git
cd statementscope
```

### 2. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Set up your API key

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

### 4. Connect to Claude

**Claude Code:**
```bash
claude mcp add statementscope python /absolute/path/to/statementscope/server.py
```

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "statementscope": {
      "command": "python",
      "args": ["/absolute/path/to/statementscope/server.py"]
    }
  }
}
```

### 5. Load a statement and ask questions

```
Load my statement from /home/user/Downloads/chase_january.csv
Categorize my transactions
How much did I spend on food last month?
What subscriptions am I paying for?
```

---

## Supported Banks

| Bank | CSV export | PDF statement |
|------|-----------|---------------|
| Chase | ✅ | ✅ |
| Bank of America | ✅ | ✅ |
| Wells Fargo | — | ✅ |
| Citi | — | ✅ |
| Capital One | — | ✅ |
| US Bank | — | ✅ |
| Other banks | ✅ (generic) | ✅ |

CSV exports are detected automatically by column headers. PDFs from any bank work via Claude's native document understanding — no templates or regex required.

---

## Example Conversation

```
You: Load my statement from /home/raymond/Downloads/BofA_june.pdf

Claude: Loaded 29 transactions from unknown (2025-06-01 to 2025-06-30)

You: Categorize my transactions

Claude: Categorized 29 transactions. Top categories: Food (8), Bills (4),
        Shopping (3), Transport (2), Income (2)

You: How much did I spend on groceries?

Claude: You spent $538.10 on groceries in June across 5 visits:
        - Publix #1024: $112.34, $123.56
        - Kroger #0447: $98.43
        - Whole Foods #51: $104.77
        - Costco #0237: $207.33 (note: Costco sells non-grocery items too)

You: What are my recurring bills?

Claude: Your recurring bills in June:
        - Chase Mortgage: $1,642.00
        - Georgia Power: $134.22
        - Comcast Cable: $84.99
        - Verizon Wireless: $85.00
        - Netflix: $15.49
        Total: $1,961.70

You: Load my Chase statement too

Claude: Loaded 30 transactions from chase (2025-01-01 to 2025-01-31)

You: How much did I spend across both accounts combined?

Claude: Across both statements:
        - Total spent: $8,127.43
        - Total received: $14,420.00
        - Net: +$6,292.57
```

---

## Architecture

```
Your computer (everything below runs locally)
─────────────────────────────────────────────────

  ~/Downloads/
  ├── chase_jan.csv          ← Downloaded from bank website
  └── bofa_feb.pdf           ← Downloaded from bank website
         │
         │  "Load my Chase statement"
         ▼
  ┌─────────────────────────────────────────────────┐
  │  Claude Desktop / Claude Code (MCP Client)       │
  └───────────────────┬─────────────────────────────┘
                      │ MCP Protocol (stdio)
                      ▼
  ┌─────────────────────────────────────────────────┐
  │  StatementScope MCP Server (server.py)           │
  │                                                  │
  │  Tools:                                          │
  │   • load_statement(file_path)                    │
  │   • query_transactions(question)                 │
  │   • get_spending_summary(period)                 │
  │   • categorize_transactions()                    │
  │                                                  │
  │  Resources:                                      │
  │   • statements://loaded                          │
  │   • statements://summary                         │
  │                                                  │
  │  Prompts:                                        │
  │   • monthly_report                               │
  │                                                  │
  │  Internal pipeline:                              │
  │   parsers/ → store/ → rag/                       │
  │                                                  │
  │  In-memory:                                      │
  │   • List[dict] of parsed transactions            │
  │   • FAISS index (vector embeddings)              │
  │   • BM25 index (keyword search)                  │
  └───────────────────┬─────────────────────────────┘
                      │ Only external call
                      ▼
              Anthropic API (api.anthropic.com)
```

---

## Privacy

Transaction data stays on your machine. The only external calls are to the Anthropic API:

- **PDF parsing:** the PDF is sent to Claude to extract transactions
- **Query answering:** retrieved transaction summaries (not raw statements) are sent to Claude to answer your question
- **Categorization:** transaction descriptions are sent to Claude in batches for category assignment

This is the same data exposure as asking Claude any question manually. No third-party services, no Plaid, no additional data sharing beyond the Anthropic API itself.

---

## How It Works

### Parsing

CSV exports are parsed with pandas. The bank format is detected automatically by column headers — Chase and BofA have distinct formats; anything else falls back to generic column detection. Every transaction is normalized to the same schema regardless of source.

PDF statements are parsed using Claude's native document support with forced structured output via `tool_choice`. This handles the messy table layouts in bank PDFs without regex or templates.

### Hybrid Search

When you ask a question, StatementScope uses reciprocal rank fusion across two indexes:

- **FAISS** (vector search) — finds semantically similar transactions. "Food expenses" matches "Chipotle" and "Whole Foods" even without exact keywords.
- **BM25** (keyword search) — finds exact term matches. "Amazon" or "Chase" return precise results.

Combining both handles the full range of financial queries.

### Query Routing

A lightweight Haiku classifier decides whether your question needs all transactions (totals, summaries, subscription lists) or just the relevant ones (specific merchant lookups). This keeps context lean for targeted queries while ensuring complete data for aggregate questions.

### Answering

Retrieved transactions are formatted and passed to Claude with a financial assistant system prompt. Temperature is set to 0 for precise, factual answers.

---

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `load_statement(file_path)` | Load a CSV or PDF bank statement |
| `query_transactions(question)` | Ask a natural language question about transactions |
| `get_spending_summary(period)` | Get totals and category breakdown for a period |
| `categorize_transactions()` | Auto-categorize all uncategorized transactions |

**Resources:** `statements://loaded` · `statements://summary`

**Prompts:** `monthly_report`

---

## License

MIT
