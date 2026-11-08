import json
from pathlib import Path
from typing import List
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from dusty.state import FlightState
from models import primary_openrouter, fallback_qwen, fallback_llama
from openrouter.errors.unauthorizedresponse_error import UnauthorizedResponseError
from openai import RateLimitError


class FlightFeasibility(BaseModel):
    is_feasible:bool = Field(description="True si le vol est réalisable et False s'il ne l'est pas")
    time_window:str = Field(description = "Créneaux où il est recommandé de voler")
    blocking_factors: List[str] = Field(default = [],description="Liste des facteurs compromettant le vol (nuages trop bas, vent trop fort, pluie, orage)")
    weather_report : str = Field(description="Rapport détaillé de l'analyse météo")

async def evaluate_flight_feasibility_node(state:FlightState) -> dict:

    decoded_weather = state.get("decoded_weather") or {}

    # Sécurité : lecture du JSON si non présent dans le State
    if not decoded_weather and state.get("translated_json_path"):
        json_file = Path(state["translated_json_path"])
        if json_file.exists():
            decoded_weather = json.loads(json_file.read_text(encoding="utf-8"))

    decoded_weather = decoded_weather or {}
    departure = state["departure"]
    destination = state["destination"] or departure
    mode = state["mode"]

    print("⏳ [LLM] Évaluation de la faisabilité VFR...")

    system_prompt = (
        "Tu es un instructeur avion et préparateur de vol expert en réglementation VFR.\n"
        "Ton rôle est d'analyser les bulletins METAR et TAF décodés fournis pour statuer sur la faisabilité du vol.\n\n"
        "Critères d'évaluation VFR standard :\n"
        "1. Visibilité minimale : 5 km (alerte si < 5000m, no-go si < 1500m).\n"
        "2. Plafond nuageux : La base des nuages fragmentés (BKN), couverts (OVC) ou obscurcissement (VV) doit être >= 1500 ft AGL.\n"
        "3. Phénomènes météo rédhibitoires : Orages (TS, CB), Givrage/Pluie verglaçante (FZRA), Brouillard dense (FG).\n"
        "4. Vent : Alerte forte si vent soutenu > 20 kt ou rafales (G) > 25 kt.\n"
        "5. Créneaux TAF : Analyse les changements (BECMG, TEMPO, PROB) pour indiquer à quel moment de la journée le vol est possible ou impossible.\n\n"
        "Réponds impérativement au format JSON structuré selon le schéma demandé."
        "6. Vols VFR interdits de nuit : ne propose pas des créneraux nocturnes mêmes si les conditions météo sont favorables.\n"

    )
    
    user_content = (
        f"Mode de vol : {mode.upper()}\n"
        f"Départ : {departure}\n"
        f"Destination : {destination}\n\n"
        f"Données météo décodées :\n"
        f"{json.dumps(decoded_weather, indent=2, ensure_ascii=False)}"
    )

    Other_resilient_extractor = (
        primary_openrouter.with_structured_output(FlightFeasibility)
            .with_fallbacks(
                [
                    fallback_qwen.with_structured_output(FlightFeasibility),
                    fallback_llama.with_structured_output(FlightFeasibility)
                ],
                exceptions_to_handle=(RateLimitError, UnauthorizedResponseError, Exception)
            )
    )

    llm = Other_resilient_extractor

    assessment: FlightFeasibility = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content)
    ])

    verdict_badge = "🟢 VOL FAISABLE" if assessment.is_feasible else "🔴 VOL NON CONSEILLÉ / IMPOSSIBLE"
    report_lines = [
        f"# Dossier Prévol — {departure} ➔ {destination} ({mode.upper()})",
        "",
        f"## Décision Opérationnelle : {verdict_badge}",
        f"**Créneau conseillé :** {assessment.time_window}",
        ""
    ]

    if assessment.blocking_factors:
        report_lines.append("**Points d'attention / Facteurs bloquants :**")
        for factor in assessment.blocking_factors:
            report_lines.append(f"- ⚠️ {factor}")
        report_lines.append("")

    report_lines.extend([
        "### Analyse Météorologique",
        assessment.weather_report,
        "",
        "---",
        "## Bulletins Météo Traduits (Détails par terrain)",
        ""
    ])

    for icao, messages in decoded_weather.items():
        report_lines.append(f"### Terrain : {icao}")
        metar_text = messages.get("METAR", "Aucun bulletin METAR")
        taf_text = messages.get("TAF", "Aucun bulletin TAF")

        report_lines.append(f"**METAR (Observation) :**\n> {metar_text}\n")
        report_lines.append(f"**TAF (Prévision) :**\n> {taf_text}\n")

    full_report = "\n".join(report_lines)

    # Enregistrement du rapport en format markdown
    report_filename = Path("./downloads") / f"rapport_vol_{departure}_{destination}.md"
    report_filename.parent.mkdir(parents=True, exist_ok=True)
    report_filename.write_text(full_report, encoding="utf-8")


    return {
        "is_feasible":assessment.is_feasible,
        "feasibility_report":full_report,
        "messages": [AIMessage(content=full_report)]
    }