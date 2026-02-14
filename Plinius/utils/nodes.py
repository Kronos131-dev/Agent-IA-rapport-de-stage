import os
import markdown
import re
import json
from xhtml2pdf import pisa
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from Plinius.utils.state import AgentState
from Plinius.utils.llm_config import get_llm
from Plinius.utils.tools import search_documents, internet_search, consult_style_guide

# --- Helper de nettoyage ---

def clean_markdown(text: str) -> str:
    """Nettoie le markdown généré par le LLM."""
    if not text: return ""
    text = re.sub(r"```markdown\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = re.sub(r"[■□▼▲]{3,}", "", text)
    text = re.sub(r"[-=_]{5,}", "", text)
    text = text.replace("■", "-").replace("□", "-").replace("▼", "v").replace("▲", "^")
    text = text.replace("ᵉʳ", "er")
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            line = line.replace('**', '')
            if " : " in line:
                line = line.split(" : ")[0]
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

# --- Helper générique ---

def call_llm(system_prompt: str, user_prompt: str, state: AgentState):
    """Appel simple au LLM avec gestion du feedback."""
    llm = get_llm()
    messages = [SystemMessage(content=system_prompt)]
    
    content = user_prompt
    feedback = state.get("user_feedback")
    previous_output = state.get("previous_output")
    
    if feedback and previous_output:
        content += f"\n\n--- MODE CORRECTION ---\nPrécédent refusé :\n{previous_output}\n\nFeedback :\n{feedback}\n\nCorrige en conséquence."
        
    messages.append(HumanMessage(content=content))
    response = llm.invoke(messages).content
    return clean_markdown(response)

# --- Implémentation des Noeuds ---

def noeud_orchestrateur(state: AgentState):
    print("\n[Orchestrateur] Analyse...")
    last = state.get("last_validated")
    current = state.get("current_node")
    
    sequence = ["contexte", "corps_rapport", "introduction", "conclusion", "mise_en_page", "generation", "conversion_pdf"]
    
    if not last:
        next_node = "contexte"
    else:
        try:
            idx = sequence.index(last)
            next_node = sequence[idx + 1] if idx + 1 < len(sequence) else "conversion_pdf"
        except ValueError:
            next_node = "conversion_pdf"

    updates = {"current_node": next_node, "human_approved": False}
    
    if next_node != current:
        print(f"[Orchestrateur] -> {next_node}")
        updates["user_feedback"] = None
        updates["previous_output"] = None
        updates["revision_count"] = 0
    else:
        print(f"[Orchestrateur] Révision pour {next_node}")
        updates["revision_count"] = state.get("revision_count", 0) + 1

    return updates

def demande_infos_contexte(state: AgentState):
    print("--- Tâche : Contexte & Infos Complètes ---")
    llm = get_llm()
    parser = JsonOutputParser()
    
    rag_notes = search_documents.invoke("Infos administratives stage entreprise tuteur maître de stage université formation")
    
    # 1. Extraction initiale
    extraction_prompt = """Analyse le texte ci-dessous (Notes).
    Identifie les entités nommées.
    
    Format JSON attendu :
    {
        "ENTREPRISE": "Nom ou INCONNU",
        "TUTEUR_ENTREPRISE": "Nom ou INCONNU",
        "ECOLE": "Nom ou INCONNU",
        "FORMATION": "Nom ou INCONNU",
        "TUTEUR_ECOLE": "Nom ou INCONNU"
    }
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=f"Texte : {rag_notes[:3000]}")
        ])
        infos = parser.parse(response.content)
    except Exception as e:
        print(f"   [Erreur Extraction] {e}. Utilisation valeurs par défaut.")
        infos = {k: "INCONNU" for k in ["ENTREPRISE", "TUTEUR_ENTREPRISE", "ECOLE", "FORMATION", "TUTEUR_ECOLE"]}

    # 2. Analyse du feedback (Correction JSON plus souple)
    feedback = state.get("user_feedback")
    if feedback:
        print(f"   [Correction] Analyse du feedback : '{feedback}'")
        feedback_prompt = """L'utilisateur donne une correction. Extrais les nouveaux noms si présents.
        Si une info est mentionnée (même implicitement), mets-la à jour.
        
        Format JSON attendu :
        {
            "ENTREPRISE": "Nouveau Nom ou null",
            "TUTEUR_ENTREPRISE": "Nouveau Nom ou null",
            "ECOLE": "Nouveau Nom ou null",
            "FORMATION": "Nouveau Nom ou null",
            "TUTEUR_ECOLE": "Nouveau Nom ou null"
        }
        """
        try:
            fb_response = llm.invoke([
                SystemMessage(content=feedback_prompt),
                HumanMessage(content=f"Feedback : {feedback}")
            ])
            fb_infos = parser.parse(fb_response.content)
            
            for key, val in fb_infos.items():
                if val and val not in ["null", "None", "INCONNU", "NON_MENTIONNE"]:
                    print(f"   -> Mise à jour {key} : {val}")
                    infos[key] = val
        except Exception as e:
            print(f"   [Erreur Feedback] {e}")

    # 3. Recherches Web
    web_infos = ""
    missing_alerts = []
    
    def search_and_log(key, query_template, label):
        val = infos.get(key, "INCONNU")
        val_clean = str(val).replace('"', '').replace("'", "").replace(".", "").strip()
        
        # On considère que si le nom est court (< 2 chars) ou générique, c'est inconnu
        if val_clean and val_clean not in ["INCONNU", "None", "null"] and len(val_clean) > 2:
            print(f"   [Tavily] Recherche {label} : '{val_clean}'")
            query = query_template.format(val_clean)
            res = internet_search.invoke(query)
            return f"\n--- INFOS WEB {key} ({val_clean}) ---\n{res}\n"
        else:
            print(f"   [Info] {label} inconnu ({val}). Pas de recherche web.")
            missing_alerts.append(label)
            return ""

    web_infos += search_and_log("ENTREPRISE", "Entreprise {} présentation secteur chiffres clés", "Entreprise")
    
    tutor_query = "Profil professionnel {}"
    if infos.get("ENTREPRISE") and infos["ENTREPRISE"] not in ["INCONNU", "null"]:
        tutor_query += f" {infos['ENTREPRISE']}"
    web_infos += search_and_log("TUTEUR_ENTREPRISE", tutor_query, "Tuteur Entreprise")
    
    web_infos += search_and_log("ECOLE", "École {} présentation formation informatique", "École/Université")
    web_infos += search_and_log("FORMATION", "Formation {} programme débouchés", "Formation")
    web_infos += search_and_log("TUTEUR_ECOLE", "Profil académique chercheur {}", "Tuteur Académique")

    # 4. Génération finale
    system_prompt = """Tu es un assistant administratif expert.
    Extrais et compile les informations du stage pour la page de garde et l'intro.
    """
    user_prompt = f"Notes internes :\n{rag_notes}\n\nInfos Web (Tavily) :\n{web_infos}\n\nSynthétise tout."
    result = call_llm(system_prompt, user_prompt, state)
    
    placeholders = re.findall(r"\[(.*?)\]", result)
    if placeholders:
        for p in placeholders:
            if "http" not in p and len(p) < 50: 
                missing_alerts.append(f"Information manquante : {p}")
    
    missing_alerts = list(set(missing_alerts))
    
    # On stocke les infos brutes dans le state pour la page de garde HTML plus tard
    return {"context_data": {"content": result, "raw_infos": infos}, "missing_infos": missing_alerts}

def coeur_rapport(state: AgentState):
    print("--- Tâche : Corps du Rapport & Sommaire Détaillé ---")
    
    context_str = state.get('context_data', {}).get('content', '')
    rag_notes = search_documents.invoke("Missions, tâches techniques, difficultés, réussites")
    style_guide = consult_style_guide.invoke("Structure du développement, style rédactionnel technique")
    
    # 1. GÉNÉRATION DU PLAN
    print("   [1/2] Génération du Plan de Développement (5-7 parties)...")
    parser = JsonOutputParser()
    plan_prompt = """Tu es un architecte de contenu.
    Analyse les notes de stage et propose un PLAN DE DÉVELOPPEMENT détaillé en 5 à 7 grandes parties techniques.
    Format JSON : [{"titre": "...", "contenu": "..."}]
    """
    llm = get_llm()
    try:
        response = llm.invoke([SystemMessage(content=plan_prompt), HumanMessage(content=f"Notes :\n{rag_notes}\n\nGénère le plan JSON.")])
        plan = parser.parse(response.content)
        if not isinstance(plan, list): raise ValueError("Le plan n'est pas une liste.")
    except Exception as e:
        print(f"   [Erreur JSON] {e}. Fallback.")
        return {"report_body": call_llm("Rédige le corps du rapport.", f"Notes:\n{rag_notes}", state), "sommaire": "Sommaire non généré"}

    # 2. RÉDACTION ITÉRATIVE
    full_body = ""
    print(f"   [2/2] Rédaction des {len(plan)} parties...")
    
    for i, partie in enumerate(plan):
        titre = partie.get("titre", f"Partie {i+1}")
        desc = partie.get("contenu", "")
        print(f"      -> Rédaction de : {titre}")
        
        part_prompt = f"""Tu es un rédacteur technique expert.
        Rédige la partie : "{titre}".
        Contexte : {desc}
        
        CONSIGNES :
        - NE METS PAS LE TITRE DE LA PARTIE (je l'ajoute moi-même). Commence directement par le contenu.
        - Volume : 3-5 pages.
        - Structure : Utilise des sous-titres (##).
        - Style : Fluide, technique, précis.
        """
        
        part_content = call_llm(part_prompt, f"Notes globales :\n{rag_notes}\n\nRédige la partie '{titre}'.", state)
        
        # Ajout du saut de page avant chaque grande partie
        full_body += f"<div style='page-break-before: always;'></div>\n\n# {titre}\n\n{part_content}\n\n"

    # 3. SOMMAIRE
    print("   [Info] Extraction du Sommaire Détaillé...")
    sommaire_md = ""
    for line in full_body.split('\n'):
        if line.startswith("# "):
            sommaire_md += f"- {line.replace('# ', '').strip()}\n"
        elif line.startswith("## "):
            sommaire_md += f"  - {line.replace('## ', '').strip()}\n"
    
    return {"report_body": full_body, "sommaire": sommaire_md}

def creation_introduction(state: AgentState):
    print("--- Tâche : Introduction ---")
    context = state.get('context_data', {}).get('content', '')
    body_summary = state.get('report_body', '')[:1000]
    style = consult_style_guide.invoke("Exemple d'introduction")
    
    system_prompt = """Tu es un rédacteur académique.
    Rédige l'INTRODUCTION (Bac+5).
    - TITRE : "# INTRODUCTION".
    - Contenu : 3-5 pages.
    """
    user_prompt = f"Style :\n{style}\n\nContexte :\n{context}\n\nDébut du corps :\n{body_summary}\n\nRédige l'intro."
    result = call_llm(system_prompt, user_prompt, state)
    return {"introduction": result}

def creation_conclusion(state: AgentState):
    print("--- Tâche : Conclusion ---")
    body_end = state.get('report_body', '')[-1000:]
    style = consult_style_guide.invoke("Exemple de conclusion et bilan")
    
    system_prompt = """Tu es un rédacteur académique.
    Rédige la CONCLUSION (Bac+5).
    - TITRE : "# CONCLUSION".
    - Contenu : 3-4 pages.
    """
    user_prompt = f"Style :\n{style}\n\nFin du corps :\n{body_end}\n\nRédige la conclusion."
    result = call_llm(system_prompt, user_prompt, state)
    return {"conclusion": result}

def creation_mise_en_page(state: AgentState):
    print("--- Tâche : Assemblage & Finitions ---")
    
    infos = state.get('context_data', {}).get('content')
    intro = state.get('introduction')
    body = state.get('report_body')
    concl = state.get('conclusion')
    sommaire_genere = state.get('sommaire', '')
    style_annexes = consult_style_guide.invoke("Exemple de page de garde, remerciements, avant-propos")

    # Remerciements & Avant-propos
    print("   [1/2] Génération Remerciements...")
    system_prompt_remerciements = """Rédige les REMERCIEMENTS et l'AVANT-PROPOS.
    TITRES : "# REMERCIEMENTS" et "# AVANT-PROPOS".
    Sépare les deux par un saut de ligne clair.
    """
    user_prompt_remerciements = f"Infos :\n{infos}\n\nStyle :\n{style_annexes}\n\nRédige ces deux sections."
    remerciements = call_llm(system_prompt_remerciements, user_prompt_remerciements, state)
    
    # Ajout manuel du saut de page entre Remerciements et Avant-propos si le LLM ne l'a pas fait
    if "# AVANT-PROPOS" in remerciements:
        remerciements = remerciements.replace("# AVANT-PROPOS", "<div style='page-break-before: always;'></div>\n\n# AVANT-PROPOS")

    # Bibliographie
    print("   [2/2] Génération Bibliographie...")
    system_prompt_biblio = """Génère une BIBLIOGRAPHIE plausible.
    TITRE : "# BIBLIOGRAPHIE".
    """
    user_prompt_biblio = f"Sujet :\n{body[:1000]}\n\nGénère la bibliographie."
    biblio = call_llm(system_prompt_biblio, user_prompt_biblio, state)

    layout = {
        "avant_propos_remerciements": remerciements,
        "sommaire": sommaire_genere,
        "intro": intro,
        "body": body,
        "concl": concl,
        "biblio": biblio
    }
    
    return {"final_layout": layout}

def verification_humaine(state: AgentState):
    print(f"--- Vérification : {state.get('current_node')} ---")
    return state

def generation_finale(state: AgentState):
    print("--- ASSEMBLAGE FINAL MARKDOWN ---")
    l = state.get("final_layout", {})
    
    full_md = ""
    # On commence par Remerciements (la page de garde est gérée par le PDF)
    full_md += f"{l.get('avant_propos_remerciements', '')}\n\n<div style='page-break-after: always;'></div>\n\n"
    full_md += "# SOMMAIRE\n\n" + f"{l.get('sommaire', '')}\n\n<div style='page-break-after: always;'></div>\n\n"
    full_md += f"{l.get('intro', '')}\n\n<div style='page-break-after: always;'></div>\n\n"
    full_md += f"{l.get('body', '')}\n\n<div style='page-break-after: always;'></div>\n\n"
    full_md += f"{l.get('concl', '')}\n\n<div style='page-break-after: always;'></div>\n\n"
    full_md += f"{l.get('biblio', '')}\n\n"
    
    lines = full_md.split('\n')
    clean_lines = [line for line in lines if not line.strip().lower().startswith(("note :", "notes :", "notes pour", "hiérarchie visuelle"))]
    full_md = '\n'.join(clean_lines)

    output_path = "Rapport_de_Stage_Final.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_md)
    
    print(f"Fichier Markdown sauvegardé : {os.path.abspath(output_path)}")
    return state

def conversion_pdf(state: AgentState):
    print("--- CONVERSION EN PDF (AVEC PAGE DE GARDE HTML DYNAMIQUE) ---")
    
    md_path = "Rapport_de_Stage_Final.md"
    pdf_path = "Rapport_de_Stage_Final.pdf"
    
    if not os.path.exists(md_path):
        return state
        
    # Récupération des infos brutes pour la page de garde
    raw_infos = state.get('context_data', {}).get('raw_infos', {})
    
    # Valeurs par défaut si manquant
    entreprise = raw_infos.get('ENTREPRISE', '[Nom Entreprise]')
    if entreprise == "INCONNU": entreprise = "[Nom Entreprise]"
    
    tuteur = raw_infos.get('TUTEUR_ENTREPRISE', '[Nom Tuteur]')
    if tuteur == "INCONNU": tuteur = "[Nom Tuteur]"
    
    tuteur_ecole = raw_infos.get('TUTEUR_ECOLE', '[Nom Tuteur École]')
    if tuteur_ecole == "INCONNU": tuteur_ecole = "[Nom Tuteur École]"
    
    ecole = raw_infos.get('ECOLE', 'Université / École')
    if ecole == "INCONNU": ecole = "Université / École"
    
    formation = raw_infos.get('FORMATION', 'Formation')
    if formation == "INCONNU": formation = "Formation"
    
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
            
        current_date = datetime.now().strftime("%B %Y")
        
        cover_html = f"""
        <div id="cover">
            <div style="text-align: center; margin-top: 50px;">
                <h1 style="font-size: 36pt; color: #2c3e50; margin-bottom: 20px;">RAPPORT DE STAGE</h1>
                <h2 style="font-size: 20pt; color: #34495e; margin-bottom: 10px;">Fin d'Études - Ingénieur Informatique</h2>
                <h3 style="font-size: 16pt; color: #7f8c8d; margin-bottom: 50px;">{formation} - {ecole}</h3>
                
                <div style="border: 2px solid #2c3e50; padding: 20px; margin: 50px 20px;">
                    <p style="font-size: 18pt; font-weight: bold;">TITRE DU SUJET</p>
                </div>
                
                <div style="margin-top: 80px; font-size: 14pt; text-align: left; margin-left: 20%;">
                    <p><strong>Entreprise :</strong> {entreprise}</p>
                    <p><strong>Tuteur Entreprise :</strong> {tuteur}</p>
                    <p><strong>Tuteur École :</strong> {tuteur_ecole}</p>
                </div>
                
                <div style="position: absolute; bottom: 20px; width: 100%; text-align: center;">
                    <p style="font-size: 12pt;">{current_date}</p>
                </div>
            </div>
        </div>
        <pdf:next template="body_template" />
        """
        
        css = """
        <style>
            @page {
                size: A4;
                margin: 2.5cm;
                @frame footer_frame {
                    -pdf-frame-content: footer_content;
                    bottom: 1cm;
                    margin-left: 2.5cm;
                    margin-right: 2.5cm;
                    height: 1cm;
                }
            }
            @page body_template {
                margin: 2.5cm;
            }
            
            body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; text-align: justify; }
            h1 { color: #2c3e50; font-size: 22pt; margin-top: 30px; margin-bottom: 15px; page-break-after: avoid; }
            h2 { color: #34495e; font-size: 16pt; margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #eee; page-break-after: avoid; }
            h3 { color: #7f8c8d; font-size: 14pt; margin-top: 15px; margin-bottom: 8px; page-break-after: avoid; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; page-break-inside: avoid; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            ul, ol { margin-bottom: 10px; padding-left: 20px; }
            li { margin-bottom: 5px; }
            #cover { height: 100%; width: 100%; }
        </style>
        """
        
        html_content = markdown.markdown(text, extensions=['tables'])
        
        footer_html = """
        <div id="footer_content" style="text-align: center; font-size: 10pt;">
            Page <pdf:pagenumber />
        </div>
        """
        
        full_html = f"<html><head>{css}</head><body>{cover_html}{html_content}{footer_html}</body></html>"
        
        with open(pdf_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(full_html, dest=pdf_file)
            
        if pisa_status.err:
            print("Erreur lors de la conversion PDF.")
        else:
            print(f"Fichier PDF généré avec succès : {os.path.abspath(pdf_path)}")
            
    except Exception as e:
        print(f"Exception lors de la conversion PDF : {e}")
        
    return state

def route_after_human(state: AgentState):
    return "valide" if state.get("human_approved") else "refuse"

# --- Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("orchestrateur", noeud_orchestrateur)
workflow.add_node("contexte", demande_infos_contexte)
workflow.add_node("corps_rapport", coeur_rapport)
workflow.add_node("introduction", creation_introduction)
workflow.add_node("conclusion", creation_conclusion)
workflow.add_node("mise_en_page", creation_mise_en_page)
workflow.add_node("verification_humaine", verification_humaine)
workflow.add_node("generation", generation_finale)
workflow.add_node("conversion_pdf", conversion_pdf)

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
        "generation": "generation",
        "conversion_pdf": "conversion_pdf"
    }
)

for t in ["contexte", "corps_rapport", "introduction", "conclusion", "mise_en_page"]:
    workflow.add_edge(t, "verification_humaine")

workflow.add_conditional_edges(
    "verification_humaine",
    route_after_human,
    {
        "valide": "orchestrateur",
        "refuse": "orchestrateur"
    }
)

workflow.add_edge("generation", "conversion_pdf")
workflow.add_edge("conversion_pdf", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory, interrupt_before=["verification_humaine"])
