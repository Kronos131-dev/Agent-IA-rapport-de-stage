import uuid
import mlflow
import os
from Plinius.utils.nodes import app
from Plinius.utils.mlflow_config import setup_mlflow, start_run, end_run

# Chemin vers le dossier output
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

def run_interactive_session():
    # Initialisation MLflow
    setup_mlflow()
    
    # ID de thread unique pour la mémoire
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print(f"Démarrage de la session Plinius (Thread ID: {thread_id})")
    
    # Démarrage du tracking MLflow
    with start_run(run_name=f"Session_{thread_id[:8]}"):
        # Log des paramètres initiaux
        mlflow.log_param("thread_id", thread_id)
        mlflow.log_param("model", "mistral-large-latest")
        
        # Premier lancement
        initial_input = {"current_node": None, "revision_count": 0}
        
        try:
            # On lance le graphe une première fois
            for event in app.stream(initial_input, config=config):
                pass

            while True:
                # On récupère l'état actuel (après interruption)
                snapshot = app.get_state(config)
                if not snapshot.values:
                    print("Fin du processus (plus d'état).")
                    break
                
                current_node = snapshot.values.get("current_node")
                
                # Si on est arrivé à la fin (conversion_pdf -> END)
                if current_node == "conversion_pdf":
                    print("\n--- Rapport généré avec succès ! ---")
                    
                    md_path = os.path.join(OUTPUT_DIR, "Rapport_de_Stage_Final.md")
                    pdf_path = os.path.join(OUTPUT_DIR, "Rapport_de_Stage_Final.pdf")
                    
                    if os.path.exists(md_path):
                        mlflow.log_artifact(md_path)
                        print(f"   [MLflow] Artefact loggué : {md_path}")
                    
                    if os.path.exists(pdf_path):
                        mlflow.log_artifact(pdf_path)
                        print(f"   [MLflow] Artefact loggué : {pdf_path}")
                        
                    break

                print(f"\n[INTERACTION] L'agent a terminé la tâche : {current_node}")
                
                # Récupération du contenu généré pour affichage
                current_content = "Contenu non disponible"
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
                    # Ici on peut montrer l'avant-propos ou un résumé
                    layout = snapshot.values.get('final_layout', {})
                    current_content = f"--- AVANT-PROPOS ---\n{layout.get('avant_propos','')}\n\n--- REMERCIEMENTS ---\n{layout.get('remerciements','')}\n\n--- BIBLIOGRAPHIE ---\n{layout.get('biblio','')}"

                # --- AFFICHAGE COMPLET ---
                print(f"\n{'='*20} RÉSULTAT GÉNÉRÉ {'='*20}\n")
                print(str(current_content))
                print(f"\n{'='*58}\n")

                # --- AFFICHAGE DES ALERTES ---
                if missing_infos:
                    print("\n⚠️  INFORMATIONS IMPORTANTES MANQUANTES / DÉDUITES ⚠️")
                    for info in missing_infos:
                        print(f"  - {info}")
                    print("-" * 60)

                # Interaction utilisateur
                user_input = input("\nValidez-vous ce résultat ? (o/n) : ").strip().lower()

                if user_input == 'o':
                    print("Validation enregistrée.")
                    mlflow.log_metric(f"validation_{current_node}", 1)
                    
                    # Mise à jour de l'état pour passer à la suite
                    app.update_state(config, {
                        "human_approved": True, 
                        "last_validated": current_node,
                        "user_feedback": None,
                        "previous_output": None,
                        "missing_infos": []  # On vide les alertes
                    })
                else:
                    feedback = input("Veuillez donner vos instructions de correction : ")
                    print("Feedback enregistré.")
                    
                    mlflow.log_metric(f"validation_{current_node}", 0)
                    mlflow.log_text(feedback, f"feedback_{current_node}.txt")
                    
                    # Mise à jour pour rejouer le noeud actuel
                    app.update_state(config, {
                        "human_approved": False,
                        "user_feedback": feedback,
                        "previous_output": current_content,
                        "missing_infos": []
                    })

                # On relance l'exécution jusqu'à la prochaine interruption
                for event in app.stream(None, config=config):
                    pass
                    
        except Exception as e:
            print(f"Erreur critique : {e}")
            mlflow.log_param("status", "failed")
            mlflow.log_text(str(e), "error_log.txt")
            raise e

if __name__ == "__main__":
    run_interactive_session()