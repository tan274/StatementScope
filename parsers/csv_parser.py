import hashlib
import os
import pandas as pd
from datetime import datetime


def _make_id(file_path: str, row_index: int) -> str:
    path_hash = hashlib.md5(os.path.abspath(file_path).encode()).hexdigest()[:8]
    return f"{path_hash}_{row_index:03d}"


def _parse_date(date_str: str) -> str:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(date_str).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return str(date_str).strip()


def _parse_chase(df: pd.DataFrame, source_file: str) -> list[dict]:
    transactions = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        raw_amount = float(row["Amount"])
        amount = abs(raw_amount)
        direction = "credit" if raw_amount > 0 else "debit"
        category = str(row["Category"]).strip() if pd.notna(row["Category"]) else None
        transactions.append({
            "id": _make_id(source_file, i),
            "date": _parse_date(row["Transaction Date"]),
            "description": str(row["Description"]).strip(),
            "amount": amount,
            "direction": direction,
            "category": category,
            "balance": None,
            "source_file": source_file,
            "provider": "chase",
        })
    return transactions


def _parse_bofa(df: pd.DataFrame, source_file: str) -> list[dict]:
    transactions = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        raw_amount = float(row["Amount"])
        amount = abs(raw_amount)
        direction = "credit" if raw_amount > 0 else "debit"
        try:
            balance = float(row["Running Bal."])
        except (ValueError, TypeError):
            balance = None
        transactions.append({
            "id": _make_id(source_file, i),
            "date": _parse_date(row["Date"]),
            "description": str(row["Description"]).strip(),
            "amount": amount,
            "direction": direction,
            "category": None,
            "balance": balance,
            "source_file": source_file,
            "provider": "bofa",
        })
    return transactions


def _parse_generic(df: pd.DataFrame, source_file: str) -> list[dict]:
    """Best-effort parsing for unknown CSV formats."""
    cols_lower = {c.lower().strip(): c for c in df.columns}

    date_col = next((cols_lower[c] for c in cols_lower if "date" in c), None)
    desc_col = next((cols_lower[c] for c in cols_lower if any(k in c for k in ("desc", "merchant", "name", "payee"))), None)
    amount_col = next((cols_lower[c] for c in cols_lower if "amount" in c), None)
    balance_col = next((cols_lower[c] for c in cols_lower if "bal" in c), None)

    if date_col is None or amount_col is None:
        raise ValueError(f"Cannot parse CSV: could not identify date/amount columns. Headers: {list(df.columns)}")

    transactions = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        raw_amount = float(row[amount_col])
        amount = abs(raw_amount)
        direction = "credit" if raw_amount > 0 else "debit"
        description = str(row[desc_col]).strip() if desc_col else "UNKNOWN"
        balance = float(row[balance_col]) if balance_col and pd.notna(row[balance_col]) else None
        transactions.append({
            "id": _make_id(source_file, i),
            "date": _parse_date(row[date_col]),
            "description": description,
            "amount": amount,
            "direction": direction,
            "category": None,
            "balance": balance,
            "source_file": source_file,
            "provider": "unknown",
        })
    return transactions


def parse_csv(file_path: str) -> list[dict]:
    df = pd.read_csv(file_path)
    cols = list(df.columns)

    if "Transaction Date" in cols:
        return _parse_chase(df, file_path)
    elif "Running Bal." in cols:
        return _parse_bofa(df, file_path)
    else:
        return _parse_generic(df, file_path)


if __name__ == "__main__":
    txns = parse_csv("sample_data/chase_sample.csv")
    txnx = parse_csv("sample_data/bofa_sample.csv")
    for t in txns[:3]:
        print(t)
    for t in txnx[-3:]:
        print(t)
    print(f"Total: {len(txns)} transactions")
    print(f"Total: {len(txnx)} transactions")
