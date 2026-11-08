from typing import Annotated, Optional, Literal, Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages, BaseMessage



class FlightState(TypedDict):
    
    messages: Annotated[list[BaseMessage], add_messages]

    mode: Literal["trajet", "local"]
    departure: str
    destination: Optional[str]
    flight_rules: str
    pdf_path: Optional[str]
    # données de traitement
    pdf_path: Optional[str]
    translated_json_path: Optional[str]
    #message météo décodé
    decoded_weather: Optional[Dict[str, Dict[str, str]]]

    # Décisions de l'agent

    is_feasible: Optional[bool]
    feasibility_report : Optional[str]
    report_pdf_path: Optional[str]

    # envoie de l'email
    recipient_email: Optional[str]
    email_sent:Optional[bool]


