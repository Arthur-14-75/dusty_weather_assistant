import json
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from dusty.state import FlightState
from typing import Literal, Dict
from pydantic import BaseModel, Field
from pathlib import Path
from time import time

from langchain_openai import ChatOpenAI
from openai import RateLimitError
from langchain_ollama import ChatOllama
from models import resilient_extractor, FlightIntent

from skills.notam_fetcher import navigate_and_download_notams_pdf

DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "NOTAMS"

def parse_user_flight_bis(state):
    extractor = resilient_extractor

    system_prompt = (
        "Tu es un préparateur de vol aéronautique. "
        "Analyse le message du pilote pour déterminer les aérodromes et le type de vol.\n"
        "Règles d'aiguillage :\n"
        "- Si le pilote mentionne un départ et une arrivée distincts (ex: 'Saint-Cyr vers Le Touquet') -> mode='trajet'.\n"
        "- Si le pilote ne mentionne qu'un seul terrain, parle de tours de piste, de local ou de mania -> mode='local' et destination_icao=None.\n"
        "- Convertis toujours les noms de villes ou terrains en codes OACI français valides (ex: Toussus -> LFPN, Lille -> LFQQ, Pontoise -> LFPT)."
    )

    print("⏳ [1/2] Appel du LLM pour extraire le trajet...")
    last_user_message = state["messages"][-1].content
    intent: FlightIntent = extractor.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=last_user_message)
    ])

    print("⏳ [2/2] Lancement de Playwright pour Sofia Briefing...")
    # Mise à jour du State
    return {
        "mode": intent.mode,
        "departure": intent.departure_airfield,
        "destination": intent.arrival_airfield,
        "flight_rules": intent.flight_rules
    }

async def fetch_bulletin_node_bis(state:FlightState)->dict:
    mode = state["mode"]
    departure = state["departure"]
    destination = state.get("destination") or departure  # destination = départ si vol local


    pdf_file_path = await navigate_and_download_notams_pdf(
        mode=mode,
        departure_airfield=departure,
        arrival_airfield=destination,
        directory=str(DOWNLOADS_DIR)
    )

    translated_dir = Path(__file__).resolve().parent.parent / "bulletins_traduits"
    translated_dir.mkdir(parents=True, exist_ok=True)

    json_path = translated_dir / f"bulletin_{departure}_{destination}_traduit.json"
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump({}, json_file)

    return {"pdf_path": pdf_file_path, "translated_json_path": str(json_path)}
