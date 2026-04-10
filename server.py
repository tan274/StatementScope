import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

import anthropic
from mcp.server.fastmcp import FastMCP

from config import ANTHROPIC_API_KEY, EMBEDDING_MODEL, MODEL
from parsers.csv_parser import parse_csv
from parsers.pdf_parser import parse_pdf
from store.embeddings import EmbeddingModel
from rag.retriever import HybridRetriever
from rag.query_engine import retrieve_and_answer

mcp = FastMCP("statementscope")

all_transactions: list[dict] = []
retriever: HybridRetriever | None = None


@mcp.tool()
def load_statement(file_path: str) -> str:
    """Load a bank statement file (CSV or PDF) for analysis.
    Parses the file, extracts transactions, and indexes them for
    querying. Supports Chase and Bank of America CSV exports; other
    CSVs use a generic parser. PDF extraction and query answering
    send data to the Anthropic API. Provide the full absolute file path."""
    global all_transactions, retriever

    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".csv", ".pdf"):
        return f"Error: Unsupported file type '{ext}'. Only .csv and .pdf are supported."

    if any(t["source_file"] == file_path for t in all_transactions):
        return f"Already loaded: {os.path.basename(file_path)}, skipping."

    try:
        new_transactions = parse_pdf(file_path) if ext == ".pdf" else parse_csv(file_path)
    except Exception as e:
        return f"Error parsing file: {e}"
    if not new_transactions:
        return "No transactions found in file."

    all_transactions.extend(new_transactions)

    if retriever is None:
        embedding_model = EmbeddingModel(EMBEDDING_MODEL)
        retriever = HybridRetriever(embedding_model)

    retriever.add_transactions(new_transactions)

    provider = new_transactions[0].get("provider", "unknown")
    dates = [t["date"] for t in new_transactions if t.get("date")]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "unknown date range"

    return f"Loaded {len(new_transactions)} transactions from {provider} ({date_range})"


@mcp.tool()
def query_transactions(question: str) -> str:
    """Answer a natural language question about specific transactions,
    merchants, or categories. Use this for questions like 'Show me Amazon
    purchases', 'What subscriptions am I paying for?', 'Did I go to Starbucks?',
    'Show me refunds'. Do NOT use this for simple totals or summaries —
    use get_spending_summary instead."""
    if not all_transactions:
        return "No statements loaded. Use load_statement to load a bank statement first."

    return retrieve_and_answer(retriever, question)


@mcp.tool()
def categorize_transactions() -> str:
    """Automatically categorize all uncategorized transactions using AI.
    Assigns categories: Food, Shopping, Transport, Bills, Entertainment,
    Health, Travel, Income, Transfer, Other. Safe to call multiple times —
    skips transactions that are already categorized."""
    if not all_transactions:
        return "No statements loaded. Use load_statement to load a bank statement first."

    uncategorized = [t for t in all_transactions if t.get("category") is None]
    if not uncategorized:
        return "All transactions are already categorized."

    CATEGORIZE_TOOL = {
        "name": "categorize",
        "description": "Assign a category to each transaction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categorizations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id":       {"type": "string"},
                            "category": {"type": "string", "enum": [
                                "Food", "Shopping", "Transport", "Bills",
                                "Entertainment", "Health", "Travel",
                                "Income", "Transfer", "Other"
                            ]},
                        },
                        "required": ["id", "category"],
                    },
                }
            },
            "required": ["categorizations"],
        },
    }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    BATCH_SIZE = 100
    total_categorized = 0

    for i in range(0, len(uncategorized), BATCH_SIZE):
        batch = uncategorized[i:i + BATCH_SIZE]
        batch_text = "\n".join(
            f"{t['id']} | {t['description']} | ${t['amount']:.2f} {t['direction']}"
            for t in batch
        )

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=[CATEGORIZE_TOOL],
                tool_choice={"type": "tool", "name": "categorize"},
                messages=[{
                    "role": "user",
                    "content": (
                        "Categorize each transaction using ONLY these categories: "
                        "Food, Shopping, Transport, Bills, Entertainment, Health, "
                        "Travel, Income, Transfer, Other.\n\n"
                        "Rules:\n"
                        "- Food: restaurants, groceries, coffee, food delivery\n"
                        "- Shopping: retail, Amazon, clothing, electronics\n"
                        "- Transport: gas, Uber, Lyft, parking, transit\n"
                        "- Bills: utilities, phone, internet, insurance, rent, mortgage\n"
                        "- Entertainment: streaming, movies, music, games\n"
                        "- Health: pharmacy, gym, medical\n"
                        "- Travel: flights, hotels, Airbnb\n"
                        "- Income: payroll, deposits, tax refunds, Zelle received\n"
                        "- Transfer: transfers between own accounts\n"
                        "- Other: anything that doesn't fit\n\n"
                        f"Transactions:\n{batch_text}"
                    ),
                }],
            )

            for block in response.content:
                if block.type == "tool_use":
                    id_to_txn = {t["id"]: t for t in batch}
                    for item in block.input["categorizations"]:
                        if item["id"] in id_to_txn:
                            id_to_txn[item["id"]]["category"] = item["category"]
                            total_categorized += 1
                    break

        except Exception as e:
            return f"Error during categorization (batch {i // BATCH_SIZE + 1}): {e}"

    category_totals: dict[str, int] = defaultdict(int)
    for t in all_transactions:
        if t.get("category"):
            category_totals[t["category"]] += 1

    if retriever is not None:
        retriever.rebuild()

    top_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_str = ", ".join(f"{cat} ({n})" for cat, n in top_cats)
    return f"Categorized {total_categorized} transactions. Top categories: {top_str}"


@mcp.tool()
def get_spending_summary(period: str = "all") -> str:
    """Get total spending figures, category breakdowns, and top merchants.
    Use this for questions like 'What's my total spending?', 'How much did
    I spend overall?', 'Give me a breakdown by category'. Period can be
    'all', a month like 'January 2025', or 'last 30 days'."""
    if not all_transactions:
        return "No statements loaded. Use load_statement to load a bank statement first."

    txns = _filter_by_period(all_transactions, period)
    if not txns:
        return f"No transactions found for period: {period}"

    total_debits = sum(t["amount"] for t in txns if t["direction"] == "debit")
    total_credits = sum(t["amount"] for t in txns if t["direction"] == "credit")
    net = total_credits - total_debits

    merchant_totals: dict[str, float] = defaultdict(float)
    for t in txns:
        if t["direction"] == "debit":
            merchant_totals[t["description"]] += t["amount"]
    top_merchants = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    category_totals: dict[str, float] = defaultdict(float)
    for t in txns:
        if t["direction"] == "debit" and t.get("category"):
            category_totals[t["category"]] += t["amount"]

    lines = [
        f"Period: {period}",
        f"Transactions: {len(txns)}",
        f"Total spent (debits):    ${total_debits:.2f}",
        f"Total received (credits): ${total_credits:.2f}",
        f"Net: ${net:+.2f}",
        "",
        "Top merchants by spend:",
    ]
    for name, amount in top_merchants:
        lines.append(f"  {name}: ${amount:.2f}")

    if category_totals:
        lines.append("")
        lines.append("By category:")
        for cat, amount in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {cat}: ${amount:.2f}")

    return "\n".join(lines)


@mcp.resource("statements://loaded")
def list_loaded_statements() -> str:
    """List all currently loaded bank statements with transaction counts."""
    if not all_transactions:
        return "No statements loaded yet. Use load_statement to load a bank statement."

    by_file: dict[str, list[dict]] = defaultdict(list)
    for t in all_transactions:
        by_file[t["source_file"]].append(t)

    result = []
    for file_path, txns in by_file.items():
        dates = [t["date"] for t in txns if t.get("date")]
        result.append({
            "file": os.path.basename(file_path),
            "provider": txns[0].get("provider", "unknown"),
            "transactions": len(txns),
            "date_range": f"{min(dates)} to {max(dates)}" if dates else "unknown",
        })

    return json.dumps(result, indent=2)


@mcp.resource("statements://summary")
def portfolio_summary() -> str:
    """Quick financial overview across all loaded statements."""
    if not all_transactions:
        return "No statements loaded yet. Use load_statement to load a bank statement."

    total_debits = sum(t["amount"] for t in all_transactions if t["direction"] == "debit")
    total_credits = sum(t["amount"] for t in all_transactions if t["direction"] == "credit")
    dates = [t["date"] for t in all_transactions if t.get("date")]

    merchant_totals: dict[str, float] = defaultdict(float)
    for t in all_transactions:
        if t["direction"] == "debit":
            merchant_totals[t["description"]] += t["amount"]
    top_5 = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    return json.dumps({
        "total_transactions": len(all_transactions),
        "total_debits": round(total_debits, 2),
        "total_credits": round(total_credits, 2),
        "net": round(total_credits - total_debits, 2),
        "date_range": {"earliest": min(dates), "latest": max(dates)} if dates else {},
        "top_5_merchants": [{"name": name, "total_amount": round(amt, 2)} for name, amt in top_5],
    }, indent=2)


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


def _filter_by_period(transactions: list[dict], period: str) -> list[dict]:
    if period == "all":
        return transactions

    period_lower = period.lower().strip()

    if period_lower == "last 30 days":
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        return [t for t in transactions if t.get("date", "") >= cutoff]

    for fmt in ("%B %Y", "%b %Y"):
        try:
            dt = datetime.strptime(period.strip(), fmt)
            prefix = dt.strftime("%Y-%m")
            return [t for t in transactions if t.get("date", "").startswith(prefix)]
        except ValueError:
            continue

    return []


if __name__ == "__main__":
    mcp.run()
