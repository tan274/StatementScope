# StatementScope — Build Plan

> A free, privacy-first MCP server that lets Claude analyze your bank
> statements locally. Drop a PDF or CSV, ask questions about your spending.
> No Plaid, no cloud uploads, no per-page fees.

---

## Table of Contents

1. [Project Summary](#project-summary)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Architecture](#architecture)
5. [Transaction Schema](#transaction-schema)
6. [Phase 1: CSV Parsing + RAG Pipeline (Days 1–3)](#phase-1-csv-parsing--rag-pipeline-days-13)
7. [Phase 2: MCP Server (Days 4–6)](#phase-2-mcp-server-days-46)
8. [Phase 3: PDF Support + Categorization (Days 7–9)](#phase-3-pdf-support--categorization-days-79)
9. [Phase 4: Polish + Ship (Days 10–12)](#phase-4-polish--ship-days-1012)
10. [Scope Boundaries](#scope-boundaries)
11. [Interview Talking Points](#interview-talking-points)
12. [Technical Concepts Demonstrated](#technical-concepts-demonstrated)

---

## Project Summary

### What it does
Users download a bank statement (CSV or PDF) from their bank's website —
something everyone already does. They point StatementScope at the file.
Then they ask Claude natural language questions like:

- "How much did I spend on restaurants in February?"
- "What subscriptions am I paying for?"
- "Show me all Amazon purchases over $50"

### Why it's useful (and not just a wrapper)
- **Dropping a file into Claude chat** works for 1 small statement. It fails
  with 6–12 months of data across multiple banks (won't fit in context).
  StatementScope indexes transactions with RAG and retrieves only what's
  relevant.
- **Plaid-based MCP servers** (BankSync, Monarch) require sharing your bank
  login with a third party. Many people won't do this.
- **Bankstatemently** charges per page and processes data in their cloud.
- **Generic CSV MCP servers** don't understand financial data — they can't
  answer "what did I spend on food?" because they don't know what
  categories or transactions are.
- StatementScope is **free, local, finance-aware, and private**.

### Privacy note (be honest about this)
Transaction data stays on your machine. The only external call is to the
Claude API for natural language understanding — this sends retrieved
transaction summaries (not raw statements) to Anthropic's servers. This is
the same data exposure as asking Claude any question. No third-party
services, no Plaid, no additional data sharing beyond the Claude API itself.

---

## Prerequisites

Before starting, make sure you have these set up in your WSL environment:

```bash
# Check Python version (need 3.10+)
python3 --version

# Check that pip works
pip --version

# Check that git is configured
git config --global user.name   # should show your name
git config --global user.email  # should show your email

# You should already have Claude Code installed
claude --version

# Get an Anthropic API key from console.anthropic.com
# You'll store this in .env later
```

### Python packages you'll need (installed during Day 1)
- `anthropic` — Claude API client
- `mcp` — Official MCP Python SDK (includes FastMCP)
- `sentence-transformers` — Local embedding model for FAISS
- `faiss-cpu` — Vector similarity search
- `rank-bm25` — BM25 lexical search
- `pandas` — CSV parsing
- `python-dotenv` — Environment variable loading
- `numpy` — Array operations (dependency of FAISS)

---

## Project Structure

```
statementscope/
├── BUILD_PLAN.md              # This file (reference for you and Claude Code)
├── README.md                  # User-facing docs (written in Phase 4)
├── requirements.txt           # Python dependencies
├── .env.example               # Template: ANTHROPIC_API_KEY=your_key_here
├── .env                       # Your actual API key (git-ignored)
├── .gitignore
│
├── server.py                  # MCP server entry point (Phase 2)
├── config.py                  # API key loading, model name, constants
├── test_pipeline.py           # CLI script to test RAG pipeline (Phase 1)
│
├── parsers/
│   ├── __init__.py
│   ├── csv_parser.py          # Parse bank CSV exports into transactions
│   └── pdf_parser.py          # Parse bank PDF statements via Claude (Phase 3)
│
├── store/
│   ├── __init__.py
│   ├── embeddings.py          # SentenceTransformer wrapper
│   ├── vector_store.py        # FAISS index: add vectors, search by similarity
│   └── bm25_store.py          # BM25 index: add documents, search by keywords
│
├── rag/
│   ├── __init__.py
│   ├── retriever.py           # Hybrid search: vector + BM25 + rank fusion
│   └── query_engine.py        # Build prompt from retrieved txns, call Claude
│
├── sample_data/
│   ├── chase_sample.csv       # 30 rows of fake but realistic Chase data
│   └── bofa_sample.csv        # 20 rows of fake but realistic BofA data
│
└── tests/
    └── test_parsers.py        # Basic sanity checks for CSV parser
```

### Why this structure
- `parsers/` — Handles turning raw files into structured transactions
- `store/` — Handles indexing transactions for fast retrieval
- `rag/` — Handles finding relevant transactions and answering questions
- `server.py` — Thin MCP wrapper that calls into parsers/, store/, and rag/
- `test_pipeline.py` — Lets you test the full pipeline WITHOUT MCP (Phase 1)

---

## Architecture

```
User's computer (everything below runs locally)
─────────────────────────────────────────────────

  ~/Downloads/
  ├── chase_jan.csv          ← Downloaded from bank website
  └── bofa_feb.pdf           ← Downloaded from bank website
         │
         │  User tells Claude: "Load my Chase statement"
         ▼
  ┌─────────────────────────────────────────────────┐
  │  Claude Desktop / Claude Code                    │
  │  (MCP Client — discovers and calls tools)        │
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
  │   • categorize_transactions()     [Phase 3]      │
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
  │  In-memory data:                                 │
  │   • List[dict] of parsed transactions            │
  │   • FAISS index (vector embeddings)              │
  │   • BM25 index (keyword index)                   │
  └───────────────────┬─────────────────────────────┘
                      │
                      │ Only external call: Claude API
                      │ (sends transaction summaries for
                      │  natural language answering)
                      ▼
              Anthropic API (api.anthropic.com)
```

---

## Transaction Schema

Every transaction, regardless of source (CSV or PDF), gets normalized
into this dictionary structure:

```python
{
    "id": str,              # Unique ID: "chase_001", "bofa_015"
    "date": str,            # ISO format: "2025-01-15"
    "description": str,     # Raw description: "AMAZON.COM*MK1AB6TE1"
    "amount": float,        # Always positive
    "direction": str,       # "debit" or "credit"
    "category": str | None, # "food", "shopping", etc. (None until categorized)
    "balance": float | None,# Running balance if available
    "source_file": str,     # Which file this came from
    "provider": str,        # "chase", "bofa", "amex", "wells_fargo", "unknown"
}
```

This is the single source of truth. Parsers produce these dicts.
The store indexes them. The retriever searches them. Keep it simple.

---

## Phase 1: CSV Parsing + RAG Pipeline (Days 1–3)

**Goal:** Load a bank CSV, parse it, index it, and answer questions via
a simple test script. No MCP yet — just the core engine.

### Day 1: Project skeleton + CSV parser + sample data

#### Step 1: Create the project and initialize git

```bash
mkdir -p ~/projects/statementscope
cd ~/projects/statementscope
git init
```

#### Step 2: Launch Claude Code and scaffold files

```bash
claude
```

Prompt for Claude Code:
```
Read BUILD_PLAN.md. I'm on Day 1.

Create these files:
1. requirements.txt — with these packages: anthropic, mcp, 
   sentence-transformers, faiss-cpu, rank-bm25, pandas, python-dotenv, numpy
2. .env.example — containing ANTHROPIC_API_KEY=your_key_here
3. .gitignore — ignore .env, __pycache__/, *.pyc, .venv/
4. config.py — load ANTHROPIC_API_KEY from .env using python-dotenv,
   set MODEL = "claude-sonnet-4-20250514", set EMBEDDING_MODEL = "all-MiniLM-L6-v2"
5. Empty __init__.py files in parsers/, store/, rag/

Just create the files. Don't build logic yet. Let me review.
```

#### Step 3: Create sample data

Prompt for Claude Code:
```
Create sample_data/chase_sample.csv with 30 rows of realistic fake
Chase bank transactions. Use Chase's real CSV column headers:
"Transaction Date","Post Date","Description","Category","Type","Amount","Memo"

Include a variety of:
- Restaurant charges (Chipotle, Starbucks, DoorDash)
- Shopping (Amazon, Target, Walmart)
- Subscriptions (Netflix, Spotify, gym)
- Gas stations
- A few credits/refunds
- Dates spanning January 2025

Also create sample_data/bofa_sample.csv with 20 rows using BofA's format:
"Date","Description","Amount","Running Bal."

Use different merchants from the Chase file.
Make amounts realistic (not round numbers — use $12.47, $67.83, etc.)
```

#### Step 4: Build the CSV parser

Prompt for Claude Code:
```
Now build parsers/csv_parser.py based on the schema in BUILD_PLAN.md.

It should have one main function:
    def parse_csv(file_path: str) -> list[dict]

This function should:
1. Read the CSV with pandas
2. Detect the bank format by checking column headers:
   - If columns contain "Transaction Date" → Chase format
   - If columns contain "Running Bal." → BofA format  
   - Otherwise → try generic parsing (date, description, amount columns)
3. For each row, create a transaction dict matching the schema in BUILD_PLAN.md
4. Handle amount signs: Chase uses negative for debits. BofA uses negative
   for debits. Normalize so amount is always positive and direction is
   "debit" or "credit".
5. Parse dates into ISO format (YYYY-MM-DD)
6. Set provider based on detected format
7. Generate unique IDs like "chase_001", "chase_002", etc.
8. Return the list of transaction dicts

Test it by adding this at the bottom:
    if __name__ == "__main__":
        txns = parse_csv("sample_data/chase_sample.csv")
        for t in txns[:3]:
            print(t)
        print(f"Total: {len(txns)} transactions")
```

#### Step 5: Test and commit

```bash
# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy .env.example to .env and add your API key
cp .env.example .env
# Edit .env with your actual ANTHROPIC_API_KEY

# Test the CSV parser
python -m parsers.csv_parser

# Commit
git add .
git commit -m "day 1: project skeleton, sample data, csv parser"
```

#### Done when
- [ ] `python -m parsers.csv_parser` prints 3 transactions from Chase CSV
- [ ] Each transaction has: id, date, description, amount, direction, provider
- [ ] Amounts are positive numbers with direction "debit" or "credit"
- [ ] Dates are in YYYY-MM-DD format

---

### Day 2: Embedding + FAISS + BM25 hybrid search

#### Step 1: Build the embedding wrapper

Prompt for Claude Code:
```
I'm on Day 2 of BUILD_PLAN.md.

Build store/embeddings.py with a class:

class EmbeddingModel:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        # Load SentenceTransformer model
    
    def embed(self, texts: list[str]) -> numpy array of float32:
        # Encode list of strings, return numpy array
    
    def embed_query(self, query: str) -> numpy array of float32:
        # Encode single query string, return numpy array

Keep it simple. This is a thin wrapper around SentenceTransformer.
```

#### Step 2: Build the FAISS vector store

Prompt for Claude Code:
```
Build store/vector_store.py with a class:

class VectorStore:
    def __init__(self, dimension: int = 384):
        # Initialize empty FAISS IndexFlatL2
        # Initialize empty list to store metadata alongside vectors
    
    def add(self, embedding: numpy array, metadata: dict):
        # Add one vector + its metadata to the index
    
    def search(self, query_embedding: numpy array, top_k: int = 5) -> list[dict]:
        # Search FAISS for top_k nearest neighbors
        # Return list of {"metadata": dict, "score": float}
        # Score = L2 distance (lower = more similar)
    
    def __len__(self) -> int:
        # Return number of stored vectors

Test at bottom:
    if __name__ == "__main__":
        from store.embeddings import EmbeddingModel
        model = EmbeddingModel()
        store = VectorStore()
        
        texts = ["coffee at starbucks", "amazon purchase", "netflix subscription"]
        for i, text in enumerate(texts):
            emb = model.embed([text])
            store.add(emb[0], {"text": text, "index": i})
        
        query_emb = model.embed_query("where did I buy coffee")
        results = store.search(query_emb, top_k=2)
        for r in results:
            print(r["metadata"]["text"], "score:", r["score"])
```

#### Step 3: Build the BM25 store

Prompt for Claude Code:
```
Build store/bm25_store.py with a class:

class BM25Store:
    def __init__(self):
        # Initialize empty document list and corpus
        # BM25 index will be rebuilt on each add (fine for <10k docs)
    
    def add(self, text: str, metadata: dict):
        # Tokenize text (lowercase, split on spaces)
        # Append to corpus and document list
        # Rebuild BM25Okapi index
    
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        # Tokenize query
        # Get BM25 scores for all documents
        # Return top_k results as list of {"metadata": dict, "score": float}
        # Only include results with score > 0
    
    def __len__(self) -> int:
        # Return number of stored documents

Use rank_bm25.BM25Okapi for the BM25 implementation.

Test at bottom with the same coffee/amazon/netflix example.
Query "amazon" should rank "amazon purchase" highest.
Query "subscription" should rank "netflix subscription" highest.
```

#### Step 4: Build the hybrid retriever

Prompt for Claude Code:
```
Build rag/retriever.py with a class:

class HybridRetriever:
    def __init__(self, embedding_model, vector_store, bm25_store):
        # Store references to all three components
    
    def add_transaction(self, transaction: dict):
        # Convert transaction dict to a search-friendly text string:
        #   "{date} {description} {amount} {direction} {category or ''}"
        # Embed the text and add to vector_store with transaction as metadata
        # Add the text to bm25_store with transaction as metadata
    
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        # 1. Get top_k results from vector_store
        # 2. Get top_k results from bm25_store
        # 3. Merge using Reciprocal Rank Fusion (RRF):
        #    For each unique transaction across both result sets:
        #      rrf_score = sum of 1/(rank + 60) for each list it appears in
        #    (Use transaction["id"] to identify unique transactions)
        #    (The constant 60 is standard for RRF — it dampens rank differences)
        # 4. Sort by rrf_score descending
        # 5. Return top_k transaction dicts
    
    def add_transactions(self, transactions: list[dict]):
        # Convenience: loop through and call add_transaction for each

Note: RRF constant is 60, not 1. The formula is: 1/(rank + 60).
This is the standard RRF formula used in search engines.
```

#### Step 5: Test hybrid search end-to-end

```bash
# Test each component
python -m store.vector_store
python -m store.bm25_store

# Commit
git add .
git commit -m "day 2: embeddings, faiss, bm25, hybrid retriever"
```

#### Done when
- [ ] VectorStore: "where did I buy coffee" returns "coffee at starbucks" as top result
- [ ] BM25Store: "amazon" returns "amazon purchase" as top result
- [ ] Both stores work independently

---

### Day 3: Query engine + end-to-end test

#### Step 1: Build the query engine

Prompt for Claude Code:
```
Build rag/query_engine.py:

import anthropic
from config import ANTHROPIC_API_KEY, MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a financial assistant analyzing the user's bank 
transactions. Use ONLY the provided transaction data to answer questions. 
Be precise with amounts (use exact numbers from the data). If the data 
doesn't contain enough information to answer, say so. Do not make up 
transactions or amounts."""

def answer_query(question: str, retrieved_transactions: list[dict]) -> str:
    # 1. Format retrieved transactions into a readable context string.
    #    For each transaction, create a line like:
    #    "2025-01-15 | STARBUCKS #1234 | $5.67 debit | Food"
    #
    # 2. Build the user message:
    #    <transactions>
    #    {formatted context}
    #    </transactions>
    #
    #    Question: {question}
    #
    # 3. Call Claude API:
    #    client.messages.create(
    #        model=MODEL,
    #        max_tokens=1024,
    #        system=SYSTEM_PROMPT,
    #        messages=[{"role": "user", "content": user_message}],
    #        temperature=0
    #    )
    #
    # 4. Return the text content of the response
```

#### Step 2: Build the test pipeline script

Prompt for Claude Code:
```
Build test_pipeline.py — a simple CLI script that tests the full pipeline
WITHOUT MCP. This is for verifying everything works before wrapping in MCP.

The script should:
1. Parse sample_data/chase_sample.csv using csv_parser
2. Create EmbeddingModel, VectorStore, BM25Store, HybridRetriever
3. Add all parsed transactions to the retriever
4. Print: "Loaded {N} transactions from Chase"
5. Enter an interactive loop:
   - Prompt: "Ask a question (or 'quit'): "
   - Retrieve top 5 transactions using hybrid search
   - Print the retrieved transactions (so I can see what was found)
   - Call answer_query with the question and retrieved transactions
   - Print Claude's answer
   - Repeat until user types 'quit'

Run with: python test_pipeline.py
```

#### Step 3: Test and iterate

```bash
# Run the test pipeline
python test_pipeline.py

# Try these queries:
# - "How much did I spend on food?"
# - "Show me my Amazon purchases"
# - "What's my biggest transaction?"
# - "Did I get any refunds?"
```

If results are bad, tell Claude Code what went wrong and ask it to adjust
the transaction-to-text conversion in the retriever, or the system prompt
in the query engine.

```bash
git add .
git commit -m "day 3: query engine, end-to-end pipeline working"
```

#### Done when
- [ ] `python test_pipeline.py` loads transactions and enters interactive mode
- [ ] "Amazon purchases" retrieves Amazon transactions (not random ones)
- [ ] "food spending" retrieves restaurant/food transactions
- [ ] Claude gives a coherent answer with specific amounts from the data
- [ ] A query about something NOT in the data returns "not enough info"

---

## Phase 2: MCP Server (Days 4–6)

**Goal:** Wrap the working pipeline as an MCP server that Claude Desktop
or Claude Code can connect to.

### Day 4: Basic MCP server with load + query tools

#### Step 1: Build the MCP server

Prompt for Claude Code:
```
I'm on Day 4 of BUILD_PLAN.md. Time to wrap the pipeline as an MCP server.

Build server.py using the official MCP Python SDK's FastMCP class.

Important: Use this import and pattern:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("statementscope")

The server needs these global variables for in-memory state:
- all_transactions: list[dict] = []     # all loaded transactions
- retriever: HybridRetriever | None = None  # initialized on first load

Define these tools using @mcp.tool decorator:

TOOL 1: load_statement
    @mcp.tool()
    def load_statement(file_path: str) -> str:
        """Load a bank statement file (CSV or PDF) for analysis.
        Parses the file, extracts transactions, and indexes them for
        querying. Supports Chase, Bank of America, Amex, and Wells Fargo
        CSV exports. Provide the full absolute file path."""
        
        # 1. Check file exists, check extension (.csv or .pdf)
        # 2. If CSV: call csv_parser.parse_csv(file_path)
        #    If PDF: return "PDF support coming soon" (Phase 3)
        # 3. Add parsed transactions to all_transactions list
        # 4. Initialize or update the retriever:
        #    - Create EmbeddingModel, VectorStore, BM25Store if not exists
        #    - Call retriever.add_transactions(new_transactions)
        # 5. Return: "Loaded {N} transactions from {provider} ({date_range})"

TOOL 2: query_transactions
    @mcp.tool()
    def query_transactions(question: str) -> str:
        """Search loaded bank transactions and answer a question about
        spending, purchases, or financial activity. The question should be
        in natural language. Examples: 'How much did I spend on food?',
        'Show me Amazon purchases', 'What subscriptions am I paying for?'"""
        
        # 1. Check that transactions are loaded (return helpful error if not)
        # 2. Use retriever.search(question, top_k=10)
        # 3. Call query_engine.answer_query(question, results)
        # 4. Return Claude's answer

TOOL 3: get_spending_summary
    @mcp.tool()
    def get_spending_summary(period: str = "all") -> str:
        """Get a spending summary with totals and category breakdowns.
        Period can be 'all', a month like 'January 2025', or 'last 30 days'.
        Returns total debits, credits, top merchants, and category breakdown."""
        
        # 1. Filter all_transactions by date if period specified
        # 2. Calculate: total debits, total credits, net
        # 3. Group by description to find top merchants
        # 4. Group by category (if categorized)
        # 5. Return formatted summary string

At the bottom:
    if __name__ == "__main__":
        mcp.run()

Note: The @mcp.tool() decorator auto-generates the JSON schema from the
function signature and docstring. The docstring becomes the tool description
that Claude sees. Type hints become parameter types. Keep docstrings
descriptive — they directly affect how well Claude uses the tools.
```

#### Step 2: Test with MCP Inspector

```bash
# Start the MCP server in one terminal
python server.py

# In another terminal, test with MCP Inspector
mcp dev server.py

# In the inspector:
# 1. Click "Connect"
# 2. Go to "Tools" tab — verify all 3 tools appear
# 3. Click load_statement, enter file_path: the absolute path to
#    sample_data/chase_sample.csv
# 4. Click "Run Tool" — should return "Loaded 30 transactions..."
# 5. Click query_transactions, enter question: "food spending"
# 6. Click "Run Tool" — should return an answer about food transactions
```

```bash
git add .
git commit -m "day 4: basic MCP server with load + query + summary tools"
```

#### Done when
- [ ] `mcp dev server.py` opens inspector and shows 3 tools
- [ ] load_statement successfully parses Chase CSV
- [ ] query_transactions returns relevant answers
- [ ] get_spending_summary returns totals and top merchants

---

### Day 5: MCP resources + prompts

#### Step 1: Add resources

Prompt for Claude Code:
```
I'm on Day 5. Add MCP resources to server.py.

Resources let Claude passively see what data is available without calling
a tool. Add these using the @mcp.resource() decorator:

RESOURCE 1:
    @mcp.resource("statements://loaded")
    def list_loaded_statements() -> str:
        """List all currently loaded bank statements with transaction counts."""
        # Return JSON string showing:
        # - Which files have been loaded
        # - Number of transactions per file
        # - Date range per file
        # If nothing loaded, return helpful message

RESOURCE 2:
    @mcp.resource("statements://summary")
    def portfolio_summary() -> str:
        """Quick financial overview across all loaded statements."""
        # Return JSON string with:
        # - total_transactions: int
        # - total_debits: float
        # - total_credits: float
        # - net: float
        # - date_range: {earliest, latest}
        # - top_5_merchants: list of {name, total_amount}
        # If nothing loaded, return helpful message
```

#### Step 2: Add a prompt template

Prompt for Claude Code:
```
Add one MCP prompt to server.py using @mcp.prompt() decorator:

    @mcp.prompt()
    def monthly_report(month: str) -> str:
        """Generate a detailed monthly spending report. 
        Month should be like 'January 2025'."""
        return (
            f"Using the loaded bank statement data, generate a detailed "
            f"spending report for {month}. Include:\n"
            f"1. Total amount spent (debits only)\n"
            f"2. Total amount received (credits only)\n"
            f"3. Net cash flow\n"
            f"4. Top 10 merchants by total spend\n"
            f"5. Breakdown by category (if categorized)\n"
            f"6. Any unusually large transactions (over $100)\n"
            f"7. Recurring charges that look like subscriptions\n"
            f"Be precise — use exact dollar amounts from the data."
        )
```

#### Step 3: Test with Claude Code (or Claude Desktop)

If using Claude Code (since you already have it set up):
```bash
# Add StatementScope as an MCP server to Claude Code
claude mcp add statementscope python /absolute/path/to/statementscope/server.py

# Restart Claude Code
claude

# Test:
# "Load my bank statement from /absolute/path/to/statementscope/sample_data/chase_sample.csv"
# "How much did I spend on food?"
# "Give me a spending summary"
```

If using Claude Desktop, add to `claude_desktop_config.json`:
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

```bash
git add .
git commit -m "day 5: MCP resources and prompt template"
```

#### Done when
- [ ] Resources show up in MCP Inspector under "Resources" tab
- [ ] statements://loaded returns list of loaded files
- [ ] statements://summary returns financial overview
- [ ] monthly_report prompt appears in "Prompts" tab

---

### Day 6: Multi-file support + bug fixes

#### Step 1: Support loading multiple files

Prompt for Claude Code:
```
Update server.py so that load_statement can be called multiple times.
Each call should ADD transactions to the existing set, not replace them.
The retriever should be updated incrementally.

Also add the BofA sample data to testing:
1. Load chase_sample.csv
2. Load bofa_sample.csv
3. Query across both: "Show me all my transactions over $50"
   — should return results from BOTH banks

Make sure get_spending_summary and the resources reflect data from
ALL loaded files, not just the most recent one.
```

#### Step 2: Test real conversation flow

In Claude Code or Desktop, test this conversation:
```
1. "Load ~/projects/statementscope/sample_data/chase_sample.csv"
2. "Load ~/projects/statementscope/sample_data/bofa_sample.csv"  
3. "How many transactions do I have total?"
4. "How much did I spend on Amazon?"
5. "What's my total spending this month?"
6. "What subscriptions am I paying for?"
7. "Show me refunds or credits"
```

Fix any bugs that come up. This is the most important testing day.

```bash
git add .
git commit -m "day 6: multi-file support, tested full conversation flow"
```

#### Done when
- [ ] Can load multiple CSV files in one session
- [ ] Queries return results from all loaded files
- [ ] Spending summary reflects all loaded data
- [ ] A 7-question conversation flow works without errors

**MILESTONE: Phase 2 complete. You now have a working MCP server. This is
already a shippable portfolio project. If you need to stop here and apply
for jobs, you can — just write a README and push to GitHub.**

---

## Phase 3: PDF Support + Categorization (Days 7–9)

**Goal:** Parse actual bank statement PDFs using Claude's document support.
This is the "wow" feature that makes the project stand out.

### Day 7: PDF parser

Prompt for Claude Code:
```
I'm on Day 7 of BUILD_PLAN.md. Build parsers/pdf_parser.py.

This uses Claude's PDF/document support to extract transactions from bank
statement PDFs. The key idea: bank PDFs have messy table layouts that are
hard to parse with regex, but Claude can read them natively.

def parse_pdf(file_path: str) -> list[dict]:
    """Parse a bank statement PDF using Claude's document support
    with structured output via tool_choice."""
    
    # 1. Read the PDF file as bytes, base64 encode it
    #    with open(file_path, "rb") as f:
    #        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")
    
    # 2. Define a tool schema for transaction extraction:
    #    Tool name: "extract_transactions"
    #    Input schema: {
    #      "transactions": array of {
    #        "date": string (YYYY-MM-DD format),
    #        "description": string,
    #        "amount": number (positive),
    #        "direction": string (enum: "debit", "credit"),
    #      }
    #    }
    
    # 3. Call Claude API with:
    #    - The PDF as a document block (type: "document", source: base64)
    #    - A text block asking to extract ALL transactions
    #    - tools=[extraction_schema]
    #    - tool_choice={"type": "tool", "name": "extract_transactions"}
    #    - model: claude-sonnet-4-20250514
    #    - max_tokens: 8192 (PDFs can have many transactions)
    
    # 4. Find the tool_use block in the response
    #    for block in response.content:
    #        if block.type == "tool_use":
    #            raw_transactions = block.input["transactions"]
    
    # 5. Normalize each raw transaction into the project's standard schema
    #    (add id, source_file, provider="unknown", category=None, balance=None)
    
    # 6. Return list of transaction dicts

Then update load_statement in server.py:
- If file_path ends with .pdf → call parse_pdf()
- If file_path ends with .csv → call parse_csv() (existing)
- Otherwise → return error message
```

### Day 8: Auto-categorization tool

Prompt for Claude Code:
```
Add a categorize_transactions tool to server.py:

    @mcp.tool()
    def categorize_transactions() -> str:
        """Automatically categorize all uncategorized transactions using AI.
        Assigns categories like Food, Shopping, Transport, Bills, 
        Entertainment, Health, Travel, Income, Transfer, Other."""
        
        # 1. Find all transactions where category is None
        # 2. If none found, return "All transactions already categorized"
        # 3. Format uncategorized transactions as a list of
        #    {id, description, amount, direction}
        # 4. Send to Claude with tool_choice forcing a categorization schema:
        #    Tool: "categorize"
        #    Schema: {"categorizations": [{id: str, category: str}]}
        # 5. Update each transaction's category in all_transactions
        # 6. Rebuild the retriever index (since text representations changed)
        # 7. Return: "Categorized {N} transactions. Top categories: ..."
        
        # Important: Process in batches of 50 if there are many transactions.
        # Claude can handle ~50 descriptions per call comfortably.
```

### Day 9: Test PDF + edge cases

- Create a simple test PDF (or find a sample bank statement PDF online)
- Test the full flow: load PDF → categorize → query
- Handle edge cases: empty file, wrong file type, very large CSV
- Add error handling with helpful messages

```bash
git add .
git commit -m "day 9: pdf support, auto-categorization, edge case handling"
```

#### Done when
- [ ] Can load a PDF bank statement
- [ ] Transactions are extracted with correct dates and amounts
- [ ] categorize_transactions assigns reasonable categories
- [ ] Queries like "food spending" work better after categorization
- [ ] Bad inputs (wrong file type, missing file) return helpful errors

---

## Phase 4: Polish + Ship (Days 10–12)

### Day 10: README

Prompt for Claude Code:
```
Write a README.md for this project. It should include:

1. Project name and one-line description
2. "Why?" section (3-4 sentences explaining the problem and why existing
   solutions fall short — Plaid requires bank login, Bankstatemently costs
   money, generic CSV tools aren't finance-aware)
3. Quick Start section with numbered steps:
   - Clone repo
   - Install dependencies  
   - Set up .env with API key
   - Configure Claude Desktop / Claude Code
   - Load a statement and ask questions
4. Supported banks list
5. Example conversation (copy-paste from a real test session)
6. Architecture section with the diagram from BUILD_PLAN.md
7. Privacy section explaining what data goes where
8. "How it works" section briefly explaining: CSV/PDF parsing, hybrid 
   search (FAISS + BM25), RAG query answering
9. License (MIT)
```

### Day 11: Demo + sample data polish

- Record a demo: screen recording of Claude Desktop session, 60-90 seconds
- Or use `asciinema` for a terminal recording if using Claude Code
- Make sure sample_data CSVs are clean and realistic
- Run through the full flow one more time to catch any issues

### Day 12: Final push

```bash
# Final cleanup
git add .
git commit -m "day 12: readme, demo, final polish"
git remote add origin https://github.com/tan274/statementscope.git
git push -u origin main
```

- Update your resume with the project link
- Update your LinkedIn
- Optional: Post to r/ClaudeAI, r/MCP, or Hacker News

---

## Scope Boundaries

### DO build
- CSV parsing for Chase, BofA, Amex, Wells Fargo, and generic format
- PDF parsing via Claude
- FAISS + BM25 hybrid search with RRF
- Auto-categorization via Claude
- MCP tools, resources, and one prompt
- Good README with examples

### DO NOT build (scope creep traps)
- ❌ Web frontend (Claude Desktop IS the frontend)
- ❌ Database persistence (in-memory FAISS is fine — data is re-loaded each session)
- ❌ Plaid or any bank API integration (the whole point is NO Plaid)
- ❌ Multi-user support (personal tool)
- ❌ Cross-month trend analysis (V2 feature)
- ❌ Non-US bank formats (start US-only)
- ❌ Export to spreadsheet (Claude can do that natively)
- ❌ Metadata filtering in FAISS (this killed your previous project version)

---

## Interview Talking Points

### Project pitch (30 seconds)
"I built a local MCP server that lets Claude analyze your bank statements
privately. You download your CSV or PDF from your bank's website, point the
tool at it, and ask natural language questions about your spending. No Plaid
credentials, no cloud processing, no per-page fees."

### On parsing (technical depth)
"The parsing layer handles two formats. CSVs are parsed with pandas using a
column-mapping approach — I detect the bank by its header format and
normalize to a common schema. PDFs are parsed using Claude's native document
support with forced structured output via tool_choice, which is much more
robust than regex for messy bank statement table layouts."

### On retrieval (technical depth)
"Retrieval uses reciprocal rank fusion across FAISS vector search and BM25
lexical search. The hybrid approach matters because financial queries mix
semantic intent — like 'food expenses' — with exact terms like 'Chase' or
'Amazon.' Pure embedding search misses exact keyword matches, and pure
keyword search misses semantic similarity."

### On MCP (architecture decision)
"I built this as an MCP server rather than a standalone app because it lets
users query their data through Claude Desktop or Claude Code. They get
Claude's full reasoning capabilities without me building a chat interface.
The MCP protocol handles tool discovery automatically, so Claude knows what
capabilities are available."

### On privacy (design decision)
"The privacy-first design was intentional. Existing solutions like
Bankstatemently charge per page and process data in their cloud. Plaid-based
tools require sharing bank credentials with a third party. StatementScope
runs entirely locally — the only external call is to the Claude API for
natural language understanding."

---

## Technical Concepts Demonstrated

| Concept | Where |
|---------|-------|
| MCP Server — tools | server.py: load_statement, query_transactions, get_spending_summary, categorize_transactions |
| MCP Server — resources | server.py: statements://loaded, statements://summary |
| MCP Server — prompts | server.py: monthly_report prompt template |
| Tool use / tool_choice | pdf_parser.py: force structured JSON extraction from PDFs |
| Structured output | pdf_parser.py + categorization: typed JSON via tool schemas |
| PDF document support | pdf_parser.py: send PDF as base64 document block to Claude |
| RAG pipeline | Full flow: parse → embed → index → retrieve → answer |
| Embeddings (FAISS) | store/vector_store.py: SentenceTransformer + FAISS L2 search |
| BM25 lexical search | store/bm25_store.py: keyword-based retrieval |
| Reciprocal rank fusion | rag/retriever.py: merge vector + BM25 results |
| System prompts | rag/query_engine.py: financial assistant persona |
| Temperature control | query_engine.py: temp=0 for factual answers |
