import asyncio
from langchain_core.messages import HumanMessage
from dusty.graph import graph

async def main():
    #Test 1: l'agent télécharge le bulletin de vol
    user_prompt = "Je veux faire un vol entre LFPZ et LFON en VFR ."

    print(f"--- Envoi de la requête : '{user_prompt}' ---")
    inputs = {"messages": [HumanMessage(content=user_prompt)]}

    print(f"\n🚀 Démarrage du graphe avec l'entrée : '{user_prompt}'\n")

    # stream_mode="updates" n'émet QUE les modifications apportées par le nœud qui vient de s'exécuter
    async for output in graph.astream(inputs, stream_mode="updates"):
        for node_name, node_update in output.items():
            print(f"┌── 🟢 Nœud exécuté : [{node_name}]")
            for key, val in node_update.items():
                # Formatage propre pour les messages ou les dictionnaires
                if key == "messages":
                    print(f"│   └── messages : {[m.content for m in val]}")
                else:
                    print(f"│   └── {key} : {val}")
            print("└──" + "─" * 40)

if __name__ == "__main__":
    asyncio.run(main())