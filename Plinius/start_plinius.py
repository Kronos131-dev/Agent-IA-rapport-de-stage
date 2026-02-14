import uuid
import sys
from Plinius.utils.nodes import app

def run_interactive_session():
    """
    Lance une session interactive pour la génération du rapport de stage.
    Gère le flux de conversation et les validations utilisateur.
    """
    # ID de thread unique pour la mémoire persistante
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"Démarrage de la session Plinius (Thread ID: {thread_id})")
    print("Initialisation du workflow...")
    
    # Premier lancement
    initial_input = {"current_node": None, "revision_count": 0}
    
    # On lance le graphe jusqu'au premier point d'interruption (verification_humaine)
    for event in app.stream(initial_input, config=config):
        pass

    while True:
        snapshot = app.get_state(config)
        if not snapshot.values:
            print("Fin du processus.")
            break
            
        current_node = snapshot.values.get("current_node")
        
        # Si on arrive à la fin du processus de génération
        if current_node == "generation":
            print("\n--- Rapport généré avec succès ! ---")
            break

        print(f"\n[INTERACTION] L'agent a terminé la tâche : {current_node}")
        
        # Récupération du contenu généré selon le noeud pour affichage
        current_content = None
        missing_infos = snapshot.values.get("missing_infos", [])
        
        if current_node == "contexte":
            current_content = snapshot.values.get('context_data', {}).get('content')
        elif current_node == "corps_rapport":
            current_content = snapshot.values.get('report_body')
        elif current_node == "introduction":
            current_content = snapshot.values.get('introduction')
        elif current_node == "conclusion":
            current_content = snapshot.values.get('conclusion')
        elif current_node == "mise_en_page":
            current_content = snapshot.values.get('final_layout', {}).get('full_markdown')
            
        if current_content:
            print(f"   Résultat actuel (Aperçu) :\n{str(current_content)[:500]}...\n")

        # --- AFFICHAGE DES ALERTES ---
        if missing_infos:
            print("\n⚠️  INFORMATIONS IMPORTANTES MANQUANTES / DÉDUITES ⚠️")
            print("L'agent n'a pas trouvé les informations suivantes dans vos notes et a dû improviser ou laisser des placeholders :")
            for info in missing_infos:
                print(f"  - {info}")
            print("\nSi vous connaissez ces informations, veuillez les fournir dans votre correction ci-dessous (ex: 'L'entreprise est Google').")
            print("Sinon, l'agent gardera ses inventions/placeholders.")
            print("-" * 60)

        # Boucle de validation utilisateur
        while True:
            user_input = input("\nValidez-vous ce résultat ? (o/n) : ").strip().lower()
            if user_input in ['o', 'n']:
                break
            print("Veuillez répondre par 'o' (oui) ou 'n' (non).")

        if user_input == 'o':
            print("Validation enregistrée.")
            app.update_state(config, {
                "human_approved": True, 
                "last_validated": current_node,
                "user_feedback": None,
                "previous_output": None,
                "missing_infos": [] # On nettoie les alertes
            })
        else:
            feedback = input("Veuillez donner vos instructions de correction (ou les infos manquantes) : ")
            print("Feedback enregistré. L'agent va réviser en tenant compte de la version précédente.")
            
            app.update_state(config, {
                "human_approved": False,
                "user_feedback": feedback,
                "previous_output": current_content,
                "missing_infos": [] # On reset pour que l'agent recalcul les manques
            })

        # On relance l'exécution jusqu'au prochain point d'arrêt
        for event in app.stream(None, config=config):
            pass

if __name__ == "__main__":
    try:
        run_interactive_session()
    except KeyboardInterrupt:
        print("\nSession interrompue par l'utilisateur.")
        sys.exit(0)
    except Exception as e:
        print(f"\nUne erreur inattendue est survenue : {e}")
        sys.exit(1)
