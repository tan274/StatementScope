from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-20250514"
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
