import base64
import os

import anthropic
from config import ANTHROPIC_API_KEY, MODEL
from parsers.csv_parser import _parse_date

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EXTRACTION_TOOL = {
    "name": "extract_transactions",
    "description": "Extract all transactions from a bank statement PDF.",
    "input_schema": {
        "type": "object",
        "properties": {
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date":        {"type": "string", "description": "Transaction date in YYYY-MM-DD format"},
                        "description": {"type": "string", "description": "Merchant name or transaction description"},
                        "amount":      {"type": "number", "description": "Transaction amount, always positive"},
                        "direction":   {"type": "string", "enum": ["debit", "credit"], "description": "debit = money out, credit = money in"},
                    },
                    "required": ["date", "description", "amount", "direction"],
                },
            }
        },
        "required": ["transactions"],
    },
}


def parse_pdf(file_path: str) -> list[dict]:
    """Parse a bank statement PDF using Claude's document support
    with structured output via tool_choice."""
    with open(file_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=MODEL,
        max_tokens=16384,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_transactions"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Extract ALL transactions from this bank statement. "
                        "Include every transaction — debits and credits. "
                        "For each transaction provide: date in YYYY-MM-DD format, "
                        "description, amount as a positive number, and direction "
                        "(debit for money out, credit for money in)."
                    ),
                },
            ],
        }],
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            "PDF has too many transactions to extract in one pass. "
            "Try splitting the statement into individual months."
        )

    raw_transactions = []
    for block in response.content:
        if block.type == "tool_use":
            raw_transactions = block.input["transactions"]
            break

    basename = os.path.splitext(os.path.basename(file_path))[0]
    transactions = []
    for i, raw in enumerate(raw_transactions, start=1):
        transactions.append({
            "id": f"{basename}_{i:03d}",
            "date": _parse_date(raw["date"]),
            "description": str(raw["description"]).strip(),
            "amount": float(raw["amount"]),
            "direction": raw["direction"],
            "category": None,
            "balance": None,
            "source_file": file_path,
            "provider": "unknown",
        })

    return transactions
