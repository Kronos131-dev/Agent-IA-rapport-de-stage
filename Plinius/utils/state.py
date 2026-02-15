from typing import TypedDict, Optional, Any, List

class AgentState(TypedDict):
    last_validated: Optional[str]
    current_node: str
    human_approved: bool
    
    user_feedback: Optional[str]
    previous_output: Optional[Any]
    revision_count: int
    
    missing_infos: Optional[List[str]]
    
    # Données du rapport
    context_data: dict
    style_rules: str    # Nouvelles règles de style extraites de l'exemple
    report_body: str
    sommaire: str
    introduction: str
    conclusion: str
    final_layout: dict