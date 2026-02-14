import sys
import os

# Ajout du répertoire parent au PYTHONPATH pour permettre les imports relatifs
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Plinius.start_plinius import run_interactive_session

if __name__ == "__main__":
    print("Lancement de Plinius via le point d'entrée principal...")
    run_interactive_session()
