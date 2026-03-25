import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

from mcp.server.fastmcp import FastMCP

from config import EMBEDDING_MODEL
from parsers.csv_parser import parse_csv
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
    querying. Supports Chase, Bank of America, Amex, and Wells Fargo
    CSV exports. Provide the full absolute file path."""
    global all_transactions, retriever

    if not os.path.exists(file_path):
        return f"Error: File not found: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return "PDF support coming soon (Phase 3)."
    elif ext != ".csv":
        return f"Error: Unsupported file type '{ext}'. Only .csv and .pdf are supported."

    if any(t["source_file"] == file_path for t in all_transactions):
        return f"Already loaded: {os.path.basename(file_path)}, skipping."

    new_transactions = parse_csv(file_path)
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

    return transactions


if __name__ == "__main__":
    mcp.run()
