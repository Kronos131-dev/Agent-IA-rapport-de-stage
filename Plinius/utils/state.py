from typing import TypedDict, Optional, Any, List, Dict

class AgentState(TypedDict):
    """
    État global de l'agent Plinius.
    Stocke toutes les données nécessaires au passage entre les nœuds du graphe.
    """
    # --- Contrôle du flux ---
    last_validated: Optional[str]   # La dernière étape validée par l'humain (ex: "contexte")
    current_node: str               # L'étape en cours d'exécution ou à exécuter
    human_approved: bool            # Indicateur si l'étape actuelle a été validée par l'utilisateur
    
    # --- Gestion des itérations et corrections ---
    user_feedback: Optional[str]    # Feedback textuel de l'utilisateur en cas de refus
    previous_output: Optional[Any]  # Le contenu généré précédemment (pour comparaison lors de la correction)
    revision_count: int             # Compteur d'itérations pour éviter les boucles infinies (optionnel)
    
    # --- Alertes et Qualité ---
    missing_infos: Optional[List[str]] # Liste des informations détectées comme manquantes ou inventées
    
    # --- Données du Rapport (Contenu) ---
    context_data: Dict[str, Any]    # Données contextuelles (Entreprise, Tuteurs, etc.)
    report_body: str                # Le corps principal du rapport (Markdown)
    sommaire: str                   # Le sommaire généré automatiquement
    introduction: str               # Le texte de l'introduction
    conclusion: str                 # Le texte de la conclusion
    
    # --- Mise en page finale ---
    final_layout: Dict[str, Any]    # Dictionnaire contenant tous les blocs assemblés pour la génération finale