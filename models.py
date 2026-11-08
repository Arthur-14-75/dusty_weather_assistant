import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from typing import Literal, Optional
from pydantic import BaseModel, Field
#from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from openrouter.errors.unauthorizedresponse_error import UnauthorizedResponseError
from openai import RateLimitError, OpenAIError


load_dotenv(find_dotenv(), override=True)

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise ValueError("OPENROUTER_API_KEY est introuvable. Vérifie le nom de la variable dans ton fichier .env.")

print("Clé OpenRouter chargée :", "OUI" if os.getenv("OPENROUTER_API_KEY") else "NON")


primary_openrouter = ChatOpenAI(
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

fallback_qwen = ChatOllama(model="qwen2.5:7b", timeout=120)
fallback_llama = ChatOllama(model="llama3.2:3b", timeout=120)

# 3. Chaîne de fallback ciblée sur le 429
# exceptions_to_handle n'intercepte que l'erreur de quota/débit
resilient_model = primary_openrouter.with_fallbacks(
    [fallback_qwen, fallback_llama],
    exceptions_to_handle=(RateLimitError,)
)

class FlightIntent(BaseModel):
    mode: Literal["trajet", "local"] = Field(description="Choisis 'local' si le vol se limite à un seul aérodrome "
    "(tour de piste, mania, secteur local). Choisis 'trajet' s'il s'agit d'une navigation entre deux terrains distincts.")

    departure_airfield: str = Field(description="Code OACI de l'aérodrome de départ (ex: LFPO pour Paris Orly)")

    arrival_airfield: Optional[str] = Field(default=None, 
    description="Code OACI de l'aérodrome d'arrivée (ex: LFPO pour Paris Orly). Nécessaire uniquement si le mode est 'trajet'.")

    flight_rules: str = Field(description="Règles de vol VFR.")


resilient_extractor = (
    primary_openrouter.with_structured_output(FlightIntent)
    .with_fallbacks(
        [
            fallback_qwen.with_structured_output(FlightIntent),
            fallback_llama.with_structured_output(FlightIntent)
        ],
        exceptions_to_handle=(RateLimitError, UnauthorizedResponseError, Exception)
    )
)
