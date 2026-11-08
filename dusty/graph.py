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

from skills.aeroweb_fetcher import navigate_and_download_aeroweb_pdf
from skills.pipeline_ocr import ocr_page_to_text, extract_metar_taf, decode_weather_message_to_human
from skills.vfr_rules import evaluate_flight_feasibility_node
from skills.report_writter import generate_analysis_report
from skills.email_sender import send_report_email


#tools = [navigate_and_download_aeroweb_pdf, ocr_page_to_text, extract_metar_taf, decode_weather_message_to_human, evaluate_flight_feasibility_node]

#model_with_tools = llm.bind_tools(tools)

DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "bulletins"

def parse_user_flight(state):
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

    print("⏳ [2/2] Lancement de Playwright pour Aeroweb...")
    # Mise à jour du State
    return {
        "mode": intent.mode,
        "departure": intent.departure_airfield,
        "destination": intent.arrival_airfield,
        "flight_rules": intent.flight_rules
    }

async def fetch_bulletin_node(state:FlightState)->dict:
    mode = state["mode"]
    departure = state["departure"]
    destination = state.get("destination") or departure  # destination = départ si vol local


    pdf_file_path = await navigate_and_download_aeroweb_pdf(
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

def decode_bulletin(bulletin_data)->Dict[str, Dict[str, str]]:
    decoded_bulletin: Dict[str, Dict[str, str]] = {}

    for icao, messages in bulletin_data.items():
        decoded_bulletin[icao] = {}

        for message_type in ["METAR", "TAF"]:
            raw_message = messages.get(message_type)

            if isinstance(raw_message, str) and raw_message.strip():
                decoded_bulletin[icao][message_type] = decode_weather_message_to_human(
                    raw_message
                )
            else:
                decoded_bulletin[icao][message_type] = "Aucun bulletin disponible"

    return decoded_bulletin

async def process_ocr_node(state:FlightState)->dict:
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        raise ValueError("Aucun chemin vers le pdf trouvé")

    pdf_file = Path(pdf_path)
    print(pdf_file)
    if not pdf_file.is_file() or pdf_file.stat().st_size == 0:
        raise FileNotFoundError(f"Le fichier {pdf_path} est introuvable ou vide.")

    file_age = time() - pdf_file.stat().st_mtime
    if file_age > 120:
        print(f"⚠️ Attention : Le fichier {pdf_path} a plus de 2 minutes ({int(file_age)}s).")

    json_path = state.get("translated_json_path")
    if not json_path:
        raise ValueError("Aucun chemin vers le fichier JSON trouvé")
    
    print(f"⏳ [OCR] Traitement du bulletin PDF : {pdf_path}")
    
    raw_message = ocr_page_to_text(str(pdf_file))

    structured_message = extract_metar_taf(raw_message)

    bulletin_translated = decode_bulletin(structured_message)

    with Path(json_path).open("w", encoding="utf-8") as json_file:
        json.dump(bulletin_translated, json_file, ensure_ascii=False, indent=2)

    return {"decoded_weather": bulletin_translated} 


#Noeud de rempli si l'aérodrome est incomplet
def ask_clarification(state:FlightState)->Dict:
    message = AIMessage(content="Je n'ai pas compris votre demande. Pouvez-vous préciser le type de vol et les aérodromes concernés ?")
    return {"messages":[message]}

#condition d'aiguillage : si l'aérodrome de départ est manquant, on demande une clarification
def route_after_parsing(state:FlightState)->Literal["fetch_bulletin", "ask_clarification"]:
    # Si l'aérodrome de départ est manquant, on demande une clarification avant de lancer le MCP
    if not state.get("departure"):
        return "ask_clarification"
    if state.get("mode") == "trajet" and not state.get("destination"):
        return "ask_clarification"
    return "fetch_bulletin"

# Neoud d'export du pdf de rapport d'analyse
def export_pdf_node(state:FlightState)->dict:
    departure = state["departure"]
    destination = state["destination"] or departure
    report_markdown = state["feasibility_report"]

    print(f"📄 [PDF] Génération du PDF du rapport de vol...")
    pdf_path = generate_analysis_report(report_markdown, departure, destination)

    return {"report_pdf_path": pdf_path}

# Neoud Human-in-the-loop pour l'envoi du rapport par email

def human_review_and_send_email_node(state:FlightState)->dict:
    report_pdf_path = state["report_pdf_path"]
    if not report_pdf_path:
        raise ValueError("Aucun rapport PDF disponible pour l'envoi.")
    known_email = state.get("recipient_email")
    departure = state["departure"]
    destination = state["destination"] or departure

    if known_email:
        prompt_question = f"Voulez-vous envoyer le rapport PDF ({Path(report_pdf_path).name}) à l'adresse {known_email} ?"
    else:
        prompt_question = f"Le rapport PDF est prêt ({Path(report_pdf_path).name}). Souhaitez-vous le recevoir par e-mail ? Si oui, précisez votre adresse e-mail."
    #Interruption Human-in-the-loop pour la validation de l'envoi du rapport par email
    # Le graphe gèle son état ici et attend que l'utilisateur reprenne avec sa réponse

    user_decision = interrupt({
        "question": prompt_question,
        "current_recipient": known_email,
        "attachment_path": report_pdf_path
    })

    is_approved = user_decision.get("approved")
    target_email = user_decision.get("email") or known_email

    if is_approved and target_email:
        print(f"📧 [Email Tool] Accord validé. Invocation de l'outil d'envoi pour : {target_email}...")

        # Invocation directe du Tool LangChain
        tool_result = send_report_email.invoke({
            "recipient_email": target_email,
            "subject": f"Dossier de vol météo VFR : {departure} -> {destination}",
            "body": (
                f"Bonjour,\n\n"
                f"Veuillez trouver ci-joint votre dossier de préparation de vol VFR "
                f"pour le trajet {departure} -> {destination}.\n\n"
                f"Bon vol !"
            ),
            "attachment_path": report_pdf_path
        })

        return {
            "recipient_email": target_email,
            "email_sent": True,
            "messages": [AIMessage(content=str(tool_result))]
        }
        
    else:
        print("🛑 [Email] Envoi annulé par l'utilisateur.")
        return {
            "email_sent": False,
            "messages": [AIMessage(content="Aucun e-mail n'a été envoyé (accord refusé ou adresse manquante).")]
        }


# Construction du graphe
builder = StateGraph(FlightState)

#Ajout des noeuds
builder.add_node("parse_user_flight", parse_user_flight)
builder.add_node("ask_clarification", ask_clarification)
builder.add_node("fetch_bulletin", fetch_bulletin_node)
builder.add_node("process_ocr", process_ocr_node)
builder.add_node("analyse_feasibility", evaluate_flight_feasibility_node)
builder.add_node("export_pdf", export_pdf_node)
builder.add_node("human_review_and_send_email", human_review_and_send_email_node)

# Câblage des arrêtes
builder.add_edge(START, "parse_user_flight")

builder.add_conditional_edges("parse_user_flight",
                              
    route_after_parsing,
    {
        "fetch_bulletin": "fetch_bulletin",
        "ask_clarification": "ask_clarification"
    })
builder.add_edge("ask_clarification", END)

# Chaînage direct : téléchargement -> OCR & décodage
builder.add_edge("fetch_bulletin", "process_ocr")
builder.add_edge("process_ocr", "analyse_feasibility")
builder.add_edge("analyse_feasibility", "export_pdf")
builder.add_edge("export_pdf", "human_review_and_send_email")
builder.add_edge("human_review_and_send_email", END)


checkpoint_saver = MemorySaver()
graph = builder.compile(checkpointer=checkpoint_saver)
#graph = builder.compile()