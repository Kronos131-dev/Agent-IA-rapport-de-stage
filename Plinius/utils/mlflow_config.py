import mlflow
import os
from datetime import datetime

def setup_mlflow():
    """
    Configure MLflow pour le projet Plinius.
    Active l'autologging pour LangChain.
    """
    # Chemin absolu vers la base de données SQLite dans data/
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_path = os.path.join(project_root, "data", "mlflow.db")
    
    # Création du dossier data s'il n'existe pas
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Configuration de l'URI de tracking avec SQLite
    tracking_uri = f"sqlite:///{db_path}"
    mlflow.set_tracking_uri(tracking_uri)
    
    experiment_name = "Plinius_Rapport_Stage"
    
    try:
        if not mlflow.get_experiment_by_name(experiment_name):
            mlflow.create_experiment(experiment_name)
        mlflow.set_experiment(experiment_name)
    except Exception as e:
        print(f"Erreur init MLflow : {e}")
    
    mlflow.langchain.autolog()
    
    print(f"MLflow configuré.")
    print(f"  - Tracking URI : {tracking_uri}")
    print(f"  - Expérience : {experiment_name}")
    print(f"  - Commande UI : mlflow ui --backend-store-uri {tracking_uri}")

def start_run(run_name=None):
    """Démarre une run MLflow."""
    if not run_name:
        run_name = f"Run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return mlflow.start_run(run_name=run_name)

def end_run():
    """Termine la run active."""
    mlflow.end_run()
