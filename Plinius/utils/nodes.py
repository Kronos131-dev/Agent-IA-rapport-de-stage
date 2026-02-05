import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage
from Plinius.utils.state import AgentState
from Plinius.utils.llm_config import get_llm
from Plinius.utils.tools import search_documents

# --- Helper pour l'appel LLM ---

def call_llm_with_rag(query: str, system_prompt: str, state: AgentState, extra_context: str = ""):
    """
    Fonction générique pour interroger le LLM avec RAG, historique du state et gestion du feedback.
    """
    llm = get_llm()
    
    # 1. Recherche RAG
    rag_content = search_documents.invoke(query)
    
    # 2. Construction du prompt
    messages = [SystemMessage(content=system_prompt)]
    
    # Construction du contexte utilisateur
    user_content = f"--- DOCUMENTS SOURCES (RAG) ---\n{rag_content}\n\n"
    
    if extra_context:
        user_content += f"--- CONTEXTE DÉJÀ GÉNÉRÉ ---\n{extra_context}\n\n"
        
    user_content += f"--- DEMANDE ---\n{query}"
    
    # Gestion du feedback (Correction)
    feedback = state.get("user_feedback")
    previous_output = state.get("previous_output")
    
    if feedback and previous_output:
        user_content += f"\n\n--- MODE CORRECTION ---\nVoici ta précédente proposition qui a été refusée :\n{previous_output}\n\nVoici le feedback de l'utilisateur pour corriger :\n{feedback}\n\nTu dois réécrire le contenu en prenant en compte ces critiques."
        
    messages.append(HumanMessage(content=user_content))
    
    # 3. Appel LLM
    response = llm.invoke(messages)
    return response.content

# --- Implémentation des Noeuds ---

def noeud_orchestrateur(state: AgentState):
    print("\n[Orchestrateur] Analyse de la prochaine tâche...")
    last = state.get("last_validated")
    current = state.get("current_node")
    
    if not last:
        next_to_run = "contexte"
    elif last == "contexte":
        next_to_run = "corps_rapport"
    elif last == "corps_rapport":
        next_to_run = "introduction"
    elif last == "introduction":
        next_to_run = "conclusion"
    elif last == "conclusion":
        next_to_run = "mise_en_page"
    elif last == "mise_en_page":
        next_to_run = "generation"
    else:
        next_to_run = "generation"

    updates = {"current_node": next_to_run, "human_approved": False}
    
    if next_to_run != current:
        print(f"[Orchestrateur] Nouvelle étape : {next_to_run}. Reset du feedback.")
        updates["user_feedback"] = None
        updates["previous_output"] = None
        updates["revision_count"] = 0
    else:
        count = state.get("revision_count", 0) + 1
        updates["revision_count"] = count
        print(f"[Orchestrateur] Révision #{count} pour {next_to_run}.")

    return updates

def demande_infos_contexte(state: AgentState):
    print("--- Tâche : Extraction Contexte & Page de Garde ---")
    
    system_prompt = """Tu es un assistant expert. Extrais les infos pour la PAGE DE GARDE :
    - Nom étudiant, Entreprise, Dates, Tuteur, Sujet.
    Si une info manque, note-le."""
    
    query = "Quelles sont les informations administratives du stage ?"
    
    result = call_llm_with_rag(query, system_prompt, state)
    return {"context_data": {"content": result}}

def coeur_rapport(state: AgentState):
    print("--- Tâche : Rédaction du Corps du Rapport ---")
    
    # On passe le contexte déjà généré
    prev_context = f"Infos administratives : {state.get('context_data', {}).get('content', '')}"
    
    system_prompt = """Rédige le DÉVELOPPEMENT du rapport (Missions, Apports).
    Structure avec des titres Markdown (##, ###).
    Sois précis et technique."""
    
    query = "Rédige le corps du rapport en détaillant les missions et l'environnement technique."
    
    result = call_llm_with_rag(query, system_prompt, state, extra_context=prev_context)
    return {"report_body": result}

def creation_introduction(state: AgentState):
    print("--- Tâche : Rédaction de l'Introduction ---")
    
    # L'intro doit être cohérente avec le corps
    prev_context = f"Sujet du stage : {state.get('context_data', {}).get('content', '')}\n\nRésumé du corps du rapport : {state.get('report_body', '')[:500]}..."
    
    system_prompt = """Rédige l'INTRODUCTION.
    Présente le contexte, la problématique et annonce le plan."""
    
    query = "Rédige l'introduction du rapport."
    
    result = call_llm_with_rag(query, system_prompt, state, extra_context=prev_context)
    return {"introduction": result}

def creation_conclusion(state: AgentState):
    print("--- Tâche : Rédaction de la Conclusion ---")
    
    prev_context = f"Corps du rapport : {state.get('report_body', '')[-1000:]}"
    
    system_prompt = """Rédige la CONCLUSION et le BILAN.
    Réponds à la problématique, cite les compétences acquises."""
    
    query = "Rédige la conclusion et le bilan personnel."
    
    result = call_llm_with_rag(query, system_prompt, state, extra_context=prev_context)
    return {"conclusion": result}

def creation_mise_en_page(state: AgentState):
    print("--- Tâche : Assemblage & Génération des sections manquantes ---")
    
    # Ici, on utilise le LLM pour générer les parties "liantes" (Remerciements, Avant-propos)
    # en se basant sur tout ce qu'on sait déjà.
    
    all_context = f"""
    Infos: {state.get('context_data', {}).get('content')}
    Intro: {state.get('introduction')}
    Conclusion: {state.get('conclusion')}
    """
    
    system_prompt = """Tu es un expert en édition. Rédige les sections :
    1. REMERCIEMENTS (formels, pour le tuteur et l'équipe).
    2. AVANT-PROPOS (motivations, facultatif).
    
    Renvoie le résultat formaté en Markdown."""
    
    query = "Rédige les remerciements et l'avant-propos adaptés à ce rapport."
    
    extras = call_llm_with_rag(query, system_prompt, state, extra_context=all_context)
    
    # Assemblage final dans un dictionnaire structuré
    layout = {
        "page_de_garde": state.get('context_data', {}).get('content'),
        "avant_propos_remerciements": extras,
        "sommaire": "[SOMMAIRE GÉNÉRÉ AUTOMATIQUEMENT À L'EXPORT PDF]",
        "introduction": state.get('introduction'),
        "corps": state.get('report_body'),
        "conclusion": state.get('conclusion'),
        "bibliographie": "## Bibliographie\n\n[Liste des sources et documents consultés]"
    }
    
    return {"final_layout": layout}

def verification_humaine(state: AgentState):
    print(f"--- Vérification humaine pour : {state.get('current_node')} ---")
    return state

def generation_finale(state: AgentState):
    print("--- GÉNÉRATION DU FICHIER MARKDOWN FINAL ---")
    
    layout = state.get("final_layout", {})
    
    # Construction du contenu Markdown complet
    md_content = ""
    
    # 1. Page de Garde (Simplifiée en MD)
    md_content += "# RAPPORT DE STAGE\n\n"
    md_content += f"{layout.get('page_de_garde')}\n\n"
    md_content += "---\n\n"
    
    # 2. Avant-propos & Remerciements
    md_content += f"{layout.get('avant_propos_remerciements')}\n\n"
    md_content += "---\n\n"
    
    # 3. Sommaire (Placeholder)
    md_content += "## Sommaire\n\n*(Table des matières à générer lors de la conversion PDF)*\n\n"
    md_content += "---\n\n"
    
    # 4. Introduction
    md_content += "## Introduction\n\n"
    md_content += f"{layout.get('introduction')}\n\n"
    
    # 5. Corps
    md_content += f"{layout.get('corps')}\n\n"
    
    # 6. Conclusion & Biblio
    md_content += "## Conclusion\n\n"
    md_content += f"{layout.get('conclusion')}\n\n"
    md_content += "---\n\n"
    md_content += f"{layout.get('bibliographie')}\n\n"
    
    # Écriture du fichier
    output_path = "Rapport_de_Stage_Final.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"Fichier généré : {os.path.abspath(output_path)}")

    return state

def route_after_human(state: AgentState):
    if state.get("human_approved"):
        return "valide"
    return "refuse"

# --- Construction du Graphique LangGraph ---

workflow = StateGraph(AgentState)

workflow.add_node("orchestrateur", noeud_orchestrateur)
workflow.add_node("contexte", demande_infos_contexte)
workflow.add_node("corps_rapport", coeur_rapport)
workflow.add_node("introduction", creation_introduction)
workflow.add_node("conclusion", creation_conclusion)
workflow.add_node("mise_en_page", creation_mise_en_page)
workflow.add_node("verification_humaine", verification_humaine)
workflow.add_node("generation", generation_finale)

workflow.set_entry_point("orchestrateur")

workflow.add_conditional_edges(
    "orchestrateur",
    lambda x: x["current_node"],
    {
        "contexte": "contexte",
        "corps_rapport": "corps_rapport",
        "introduction": "introduction",
        "conclusion": "conclusion",
        "mise_en_page": "mise_en_page",
        "generation": "generation"
    }
)

tasks = ["contexte", "corps_rapport", "introduction", "conclusion", "mise_en_page"]
for task in tasks:
    workflow.add_edge(task, "verification_humaine")

workflow.add_conditional_edges(
    "verification_humaine",
    route_after_human,
    {
        "valide": "orchestrateur", 
        "refuse": "orchestrateur"
    }
)

workflow.add_edge("generation", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory, interrupt_before=["verification_humaine"])