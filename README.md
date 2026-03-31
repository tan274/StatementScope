# StatementScope

An MCP server that lets Claude analyze your local bank statements. Load a CSV or PDF, then ask natural language questions about your spending.

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

**Claude Code:**
```bash
claude mcp add statementscope python /absolute/path/to/StatementScope/server.py
```

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

### 4. Use it

```
Load my statement from /home/user/Downloads/chase_january.csv
Categorize my transactions
How much did I spend on food last month?
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
| Other | ✅ (generic) | ✅ |

CSV format is detected automatically by column headers. PDFs are parsed by Claude — no templates required.

---

## Tools

| Tool | Description |
|------|-------------|
| `load_statement(file_path)` | Load a CSV or PDF bank statement |
| `query_transactions(question)` | Ask a question about specific transactions |
| `get_spending_summary(period)` | Get totals and category breakdown |
| `categorize_transactions()` | Auto-categorize all transactions |

**Resources:** `statements://loaded` · `statements://summary`

**Prompts:** `monthly_report`

---

## Privacy

Everything runs locally. The only external calls are to the Anthropic API — for PDF parsing, query answering, and categorization. No third-party services or data sharing beyond that.

---

## License

MIT
