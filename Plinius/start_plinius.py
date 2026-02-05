import uuid
from Plinius.utils.nodes import app

def run_interactive_session():
    # ID de thread unique pour la mémoire
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"Démarrage de la session Plinius (Thread ID: {thread_id})")
    
    # Premier lancement
    initial_input = {"current_node": None, "revision_count": 0}
    
    for event in app.stream(initial_input, config=config):
        pass

    while True:
        snapshot = app.get_state(config)
        if not snapshot.values:
            print("Fin du processus.")
            break
            
        current_node = snapshot.values.get("current_node")
        
        if current_node == "generation":
            print("\n--- Rapport généré avec succès ! ---")
            break

        print(f"\n[INTERACTION] L'agent a terminé la tâche : {current_node}")
        
        # Récupération du contenu généré selon le noeud
        current_content = None
        if current_node == "contexte":
            current_content = snapshot.values.get('context_data')
        elif current_node == "corps_rapport":
            current_content = snapshot.values.get('report_body')
        elif current_node == "introduction":
            current_content = snapshot.values.get('introduction')
        elif current_node == "conclusion":
            current_content = snapshot.values.get('conclusion')
        elif current_node == "mise_en_page":
            current_content = snapshot.values.get('final_layout')
            
        print(f"   Résultat actuel : {current_content}")

        user_input = input("Validez-vous ce résultat ? (o/n) : ").strip().lower()

        if user_input == 'o':
            print("Validation enregistrée.")
            app.update_state(config, {
                "human_approved": True, 
                "last_validated": current_node,
                "user_feedback": None,
                "previous_output": None # On nettoie l'historique car validé
            })
        else:
            feedback = input("Veuillez donner vos instructions de correction : ")
            print("Feedback enregistré. L'agent va réviser en tenant compte de la version précédente.")
            
            # On sauvegarde le contenu actuel comme "previous_output" pour que l'agent puisse comparer
            app.update_state(config, {
                "human_approved": False,
                "user_feedback": feedback,
                "previous_output": current_content
            })

        # On relance l'exécution
        for event in app.stream(None, config=config):
            pass

if __name__ == "__main__":
    run_interactive_session()