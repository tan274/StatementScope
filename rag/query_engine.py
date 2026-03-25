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
    return "all" if "all" in result else "relevant"


def retrieve_and_answer(retriever: HybridRetriever, question: str) -> str:
    if _classify_query(question) == "all":
        transactions = retriever.get_all()
    else:
        transactions = retriever.search(question, top_k=10)
    return answer_query(question, transactions)
