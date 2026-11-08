# test_hitl.py
import asyncio
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from dusty.graph import graph

async def main():
    config = {"configurable": {"thread_id": "vol-test-001"}}
    
    # recipient_email est absent (None) au départ
    initial_input = {
        "messages": [HumanMessage(content="Vol VFR entre LFPZ et LFAB")]
    }

    print("🚀 [Étape 1] Exécution du graphe jusqu'au point de contrôle...")
    async for event in graph.astream(initial_input, config=config, stream_mode="updates"):
        for node, update in event.items():
            print(f"  ✓ Nœud terminé : {node}")

    # Vérification de l'interruption
    state = graph.get_state(config)
    if state.next and "human_review_and_send_email" in state.next:
        interruption = state.tasks[0].interrupts[0].value
        print("\n" + "=" * 50)
        print(f"🛑 Demande d'approbation reçue :")
        print(f"Question : {interruption.get('question')}")
        print("=" * 50)

        # Saisie de l'accord et de l'e-mail
        user_choice = input("\nConfirmer l'envoi par e-mail ? (o/n) : ").strip().lower()
        
        if user_choice == "o":
            email = input("Saisissez l'adresse e-mail destinataire : ").strip()
            user_decision = {"approved": True, "email": email}
        else:
            user_decision = {"approved": False}

        print("\n🚀 [Passe 2] Reprise du graphe avec Command(resume=...)...")
        # Cette seconde passe exécute le reste du code après interrupt()
        async for event in graph.astream(Command(resume=user_decision), config=config, stream_mode="updates"):
            for node, update in event.items():
                print(f"  ✓ Nœud terminé : {node}")
                if update and "messages" in update:
                    print(f"  📢 {update['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(main())