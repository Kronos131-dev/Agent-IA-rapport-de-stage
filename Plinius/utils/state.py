from typing import TypedDict, Optional, Any, List

class AgentState(TypedDict):
    last_validated: Optional[str]
    current_node: str
    human_approved: bool
    
    user_feedback: Optional[str]
    previous_output: Optional[Any]
    revision_count: int
    
    missing_infos: Optional[List[str]]
    retry_node: Optional[str]
    retry_count: int # Compteur pour éviter les boucles infinies de retry
    
    # Données du rapport
    context_data: dict
    style_rules: str
    report_body: str
    sommaire: str
    introduction: str
    conclusion: str
    final_layout: dict