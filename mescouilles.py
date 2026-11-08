import os
import sys
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(find_dotenv(), override=True)

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    sys.exit("Erreur : OPENROUTER_API_KEY absente du .env")

print("1. Initialisation de l'instance ChatOpenAI...")
llm = ChatOpenAI(
    model="recursive/flint-v1.0:free",
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1",
    request_timeout=15,  # Timeout court pour ne pas bloquer indéfiniment
    max_retries=0,
    streaming=True,
    default_headers={
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Aero Weather Agent",
    }
)

print("2. Envoi de la requête en streaming (Ctrl+C pour annuler)...")
try:
    for chunk in llm.stream("Dis bonjour en un mot en français, en anglais et en allemand."):
        print(chunk.content, end="", flush=True)
    print("\n--- Test réussi ---")
except Exception as e:
    print(f"\nÉchec de l'appel : {type(e).__name__} -> {e}")