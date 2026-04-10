import re
from collections import defaultdict
from datetime import datetime, timedelta

import anthropic
from config import ANTHROPIC_API_KEY, MODEL, CLASSIFIER_MODEL
from rag.retriever import HybridRetriever

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a financial assistant analyzing the user's bank
transactions. Use ONLY the provided transaction data to answer questions.
Be precise with amounts (use exact numbers from the data). If the data
doesn't contain enough information to answer, say so. Do not make up
transactions or amounts."""


def answer_query(question: str, retrieved_transactions: list[dict]) -> str:
    lines = []
    for txn in retrieved_transactions:
        direction = txn.get("direction", "")
        amount = txn.get("amount", 0)
        category = txn.get("category") or ""
        line = "{} | {} | ${:.2f} {} | {}".format(
            txn.get("date", ""),
            txn.get("description", ""),
            amount,
            direction,
            category,
        ).rstrip(" |")
        lines.append(line)

    context = "\n".join(lines)
    user_message = "<transactions>\n{}\n</transactions>\n\nQuestion: {}".format(context, question)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        temperature=0,
    )

    return response.content[0].text


def _classify_query(question: str) -> str:
    """Use Haiku to classify whether question needs all transactions or just relevant ones."""
    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": (
                "Classify this financial question. Answer with exactly one word: 'all' or 'relevant'.\n\n"
                "Answer 'all' if the question asks for: totals, sums, spending amounts, "
                "lists of all occurrences (subscriptions, refunds, recurring charges), "
                "or anything requiring a complete picture.\n"
                "Answer 'relevant' if the question asks about a specific merchant, "
                "transaction, or event (e.g. 'did I go to X', 'show me X purchases').\n\n"
                f"Question: {question}"
            ),
        }],
        temperature=0,
    )
    result = response.content[0].text.strip().lower()
    return "all" if result == "all" else "relevant"


_AGGREGATE_KEYWORDS = re.compile(
    r"\b(total|how much|spent|spending|income|breakdown|by category|top merchants?|summary)\b",
    re.IGNORECASE,
)

_MONTH_NAMES = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)

_KNOWN_CATEGORIES = (
    "food", "shopping", "transport", "bills", "entertainment",
    "health", "travel", "transfer", "other",
)

_FILLER_WORDS = {
    "show", "what", "how", "did", "my", "get", "give", "tell",
    "much", "many", "the", "for", "on", "in", "at", "is", "are",
    "spent", "spend", "spending", "total", "summary", "breakdown",
}


def _mentions_specific_merchant(question: str) -> bool:
    """Return True if the question appears to reference a specific merchant."""
    q_lower = question.lower()

    # merchant after "at" or "from" is a strong signal
    if re.search(r"\b(at|from)\s+\S+", q_lower):
        return True

    # all-caps tokens are likely merchant abbreviations (CVS, PG&E, PSEG)
    if re.search(r"\b[A-Z]{2,}\b", question):
        return True

    # capitalized words that aren't months or filler
    months = {m.lower() for m in _MONTH_NAMES.findall(question)}
    caps_words = re.findall(r"\b[A-Z][a-zA-Z]+\b", question)
    specific = [w for w in caps_words if w.lower() not in months and w.lower() not in _FILLER_WORDS]
    return len(specific) > 0


def _extract_category(question: str) -> str | None:
    """Return a known category name if mentioned in the question."""
    q_lower = question.lower()
    for cat in _KNOWN_CATEGORIES:
        if cat in q_lower:
            return cat.capitalize()
    return None


def _filter_by_period(transactions: list[dict], question: str) -> list[dict]:
    q = question.lower()
    if "last 30 days" in q:
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        return [t for t in transactions if t.get("date", "") >= cutoff]
    match = _MONTH_NAMES.search(question)
    if match:
        month_num = datetime.strptime(match.group(1), "%B").month
        year_match = re.search(r"\b(20\d{2})\b", question)
        if year_match:
            prefix = f"{year_match.group(1)}-{month_num:02d}"
            return [t for t in transactions if t.get("date", "").startswith(prefix)]
        else:
            month_str = f"-{month_num:02d}-"
            return [t for t in transactions if month_str in t.get("date", "")]
    return transactions


def _try_local_aggregate(question: str, transactions: list[dict]) -> str | None:
    """
    Handle aggregate questions locally without calling Claude.
    Returns None if the question should be sent to Claude instead.
    """
    if not _AGGREGATE_KEYWORDS.search(question):
        return None
    if _mentions_specific_merchant(question):
        return None

    txns = _filter_by_period(transactions, question)
    if not txns:
        return "No transactions found for that period."

    q = question.lower()
    debits = [t for t in txns if t["direction"] == "debit"]
    credits = [t for t in txns if t["direction"] == "credit"]

    # Category-specific spend: "how much on food", "food spending", etc.
    category = _extract_category(question)
    if category:
        cat_debits = [t for t in debits if (t.get("category") or "").lower() == category.lower()]
        if not cat_debits:
            return f"No {category} transactions found. Run categorize_transactions first."
        total = sum(t["amount"] for t in cat_debits)
        return f"{category} spending: ${total:.2f} ({len(cat_debits)} transactions)"

    if "income" in q or "received" in q:
        total = sum(t["amount"] for t in credits)
        return f"Total received: ${total:.2f} ({len(credits)} transactions)"

    if "breakdown" in q or "by category" in q:
        cat_totals: dict[str, float] = defaultdict(float)
        for t in debits:
            if t.get("category"):
                cat_totals[t["category"]] += t["amount"]
        if not cat_totals:
            return "No categorized transactions found. Run categorize_transactions first."
        lines = ["Spending by category:"]
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {cat}: ${amt:.2f}")
        return "\n".join(lines)

    if re.search(r"\btop merchants?\b", q):
        merchant_totals: dict[str, float] = defaultdict(float)
        for t in debits:
            merchant_totals[t["description"]] += t["amount"]
        top = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        lines = ["Top merchants by spend:"]
        for name, amt in top:
            lines.append(f"  {name}: ${amt:.2f}")
        return "\n".join(lines)

    # Default: total spending
    total = sum(t["amount"] for t in debits)
    return f"Total spending: ${total:.2f} ({len(debits)} transactions)"


def retrieve_and_answer(retriever: HybridRetriever, question: str) -> str:
    if _classify_query(question) == "all":
        transactions = retriever.get_all()
        local_answer = _try_local_aggregate(question, transactions)
        if local_answer is not None:
            return local_answer
        return answer_query(question, transactions)
    else:
        transactions = retriever.search(question, top_k=10)
        return answer_query(question, transactions)
