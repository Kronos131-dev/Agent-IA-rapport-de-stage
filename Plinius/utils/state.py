from typing import TypedDict, Optional, Any

class AgentState(TypedDict):
    last_validated: Optional[str]
    current_node: str
    human_approved: bool
    
    # Gestion des itérations
    user_feedback: Optional[str]
    previous_output: Optional[Any]
    revision_count: int
    
    # Données du rapport
    context_data: dict
    report_body: str
    introduction: str
    conclusion: str
    final_layout: dict