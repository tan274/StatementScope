import anthropic
from config import ANTHROPIC_API_KEY, MODEL
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
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        temperature=0,
    )

    return response.content[0].text


AGGREGATE_KEYWORDS = {"how much", "total", "all", "every", "sum", "overall", "breakdown", "list all", "show all", "refund", "return"}

def retrieve_and_answer(retriever: HybridRetriever, question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in AGGREGATE_KEYWORDS):
        transactions = retriever.get_all()
    else:
        transactions = retriever.search(question, top_k=10)
    return answer_query(question, transactions)
