import os
import markdown
import re
import json
import traceback
from xhtml2pdf import pisa
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
try:
    from langchain_core.pydantic_v1 import BaseModel, Field
except ImportError:
    from pydantic import BaseModel, Field
from typing import List

from Plinius.utils.state import AgentState
from Plinius.utils.llm_config import get_llm
from Plinius.utils.tools import search_documents, internet_search, consult_style_guide
from Plinius.utils.security import validate_input, sanitize_output
from Plinius.utils import prompts

# --- Configuration des chemins ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Modèles Pydantic ---
class PartiePlan(BaseModel):
    titre: str = Field(description="Le titre de la partie technique")
    contenu: str = Field(description="Description détaillée du contenu")

class PlanRapport(BaseModel):
    parties: List[PartiePlan] = Field(description="Liste des parties techniques")

# --- Helper de nettoyage ---
def clean_markdown(text: str) -> str:
    if not text: return ""
    text = sanitize_output(text)
    text = re.sub(r"```markdown\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = re.sub(r"[■□▼▲]{3,}", "", text)
    text = re.sub(r"[-=_]{5,}", "", text)
    text = text.replace("■", "-").replace("□", "-").replace("▼", "v").replace("▲", "^")
    text = text.replace("ᵉʳ", "er")
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"<img.*?>", "", text)
    text = re.sub(r"^(Voici|Je vous propose|Ci-dessous).*?:\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Correction : Suppression de "---" qui coupait le texte trop tôt
    stop_patterns = [r"\nNotes? de personnalisation", r"\nNotes? pour", r"\nConseils? :", r"\nExemple d['’]adaptation"]
    for pattern in stop_patterns:
        split_text = re.split(pattern, text, flags=re.IGNORECASE)
        if len(split_text) > 1: text = split_text[0]
        
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            line = line.replace('**', '')
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()

# --- Helper générique ---
def call_llm(system_prompt: str, user_prompt: str, state: AgentState):
    llm = get_llm()
    full_system_prompt = f"{prompts.SECURITY_SYSTEM_PROMPT}\n\n--- TÂCHE SPÉCIFIQUE ---\n{system_prompt}"
    messages = [SystemMessage(content=full_system_prompt)]
    content = user_prompt
    feedback = state.get("user_feedback")
    previous_output = state.get("previous_output")
    if feedback:
        if not validate_input(feedback): feedback = "Feedback ignoré."
        # Correction : Instruction explicite pour régénérer tout le contenu
        if previous_output: 
            content += f"\n\n--- MODE CORRECTION ---\nPrécédent refusé :\n{previous_output}\n\nFeedback :\n{feedback}\n\nCONSIGNE : RÉGÉNÈRE L'INTÉGRALITÉ DU CONTENU EN PRENANT EN COMPTE LE FEEDBACK. NE FAIS PAS JUSTE UNE LISTE DE MODIFICATIONS."
    messages.append(HumanMessage(content=content))
    response = llm.invoke(messages).content
    return clean_markdown(response)

# --- NOEUDS ---

def noeud_orchestrateur(state: AgentState):
    # print("\n[Orchestrateur] Analyse...")
    last = state.get("last_validated")
    current = state.get("current_node")
    sequence = ["contexte", "corps_rapport", "introduction", "conclusion", "mise_en_page", "generation", "conversion_pdf"]
    
    # Gestion des erreurs de boucle (retry automatique)
    if state.get("retry_node"):
        next_node = state.get("retry_node")
        # print(f"[Orchestrateur] Retry automatique -> {next_node}")
        return {"current_node": next_node, "retry_node": None, "human_approved": False}

    if not last: next_node = "contexte"
    else:
        try: idx = sequence.index(last); next_node = sequence[idx + 1] if idx + 1 < len(sequence) else "conversion_pdf"
        except ValueError: next_node = "conversion_pdf"
    
    updates = {"current_node": next_node, "human_approved": False}
    if next_node != current:
        # print(f"[Orchestrateur] -> {next_node}")
        updates.update({"user_feedback": None, "previous_output": None, "revision_count": 0})
    else:
        # print(f"[Orchestrateur] Révision pour {next_node}")
        updates["revision_count"] = state.get("revision_count", 0) + 1
    return updates

def demande_infos_contexte(state: AgentState):
    print("--- Tâche : Contexte & Infos ---")
    llm = get_llm()
    parser = JsonOutputParser()
    rag_notes = search_documents.invoke("Infos administratives stage entreprise tuteur maître de stage université formation sujet étudiant contact dates")
    
    # 1. Récupération des infos existantes (si feedback) ou extraction initiale
    existing_infos = state.get('context_data', {}).get('raw_infos', {})
    feedback = state.get("user_feedback")
    
    if feedback and validate_input(feedback):
        # print(f"   [Correction] Analyse du feedback...")
        infos = existing_infos.copy()
        try:
            fb_response = llm.invoke([
                SystemMessage(content=prompts.SECURITY_SYSTEM_PROMPT + "\n" + prompts.FEEDBACK_CONTEXTE),
                HumanMessage(content=f"Feedback : {feedback}")
            ])
            fb_infos = parser.parse(fb_response.content)
            
            # Mise à jour intelligente avec Reset des dépendances
            for k, v in fb_infos.items():
                if v and v not in ["null", "None", "INCONNU", "NON_MENTIONNE"]:
                    # print(f"   -> Mise à jour {k} : {v}")
                    infos[k] = v
                    
                    # LOGIQUE DE RESET : Si l'école/formation change, on oublie le tuteur inventé pour forcer la recherche
                    if k in ["ECOLE", "FORMATION"]:
                        # On ne reset que si l'utilisateur n'a PAS donné le tuteur dans le même feedback
                        if "TUTEUR_ECOLE" not in fb_infos or fb_infos["TUTEUR_ECOLE"] in ["null", "None", "INCONNU"]:
                            # print("   [Reset] Nouvelle formation/école détectée -> Recherche d'un nouveau tuteur...")
                            infos["TUTEUR_ECOLE"] = "INCONNU"
                    
                    if k == "ENTREPRISE":
                        if "TUTEUR_ENTREPRISE" not in fb_infos or fb_infos["TUTEUR_ENTREPRISE"] in ["null", "None", "INCONNU"]:
                            # print("   [Reset] Nouvelle entreprise détectée -> Recherche d'un nouveau tuteur...")
                            infos["TUTEUR_ENTREPRISE"] = "INCONNU"

        except: pass
    elif not existing_infos:
        # Extraction initiale
        try:
            response = llm.invoke([
                SystemMessage(content=prompts.SECURITY_SYSTEM_PROMPT + "\n" + prompts.EXTRACTION_CONTEXTE),
                HumanMessage(content=f"Texte : {rag_notes[:3000]}")
            ])
            infos = parser.parse(response.content)
        except:
            infos = {k: "INCONNU" for k in ["ETUDIANT_NOM", "ETUDIANT_CONTACT", "ENTREPRISE", "TUTEUR_ENTREPRISE", "ECOLE", "FORMATION", "TUTEUR_ECOLE", "DATES_STAGE", "TITRE_STAGE"]}
    else:
        infos = existing_infos

    # Nettoyage et Détection de Noms Génériques
    generic_terms = ["conseiller", "académique", "tuteur", "responsable", "pédagogique", "maître", "stage", "professeur", "inconnu", "non mentionné"]
    for k, v in infos.items():
        if v in ["None", "null", None]: 
            infos[k] = "INCONNU"
        elif isinstance(v, str):
            # Si le nom contient trop de termes génériques, on le considère comme INCONNU pour forcer la recherche
            if any(term in v.lower() for term in generic_terms) and len(v.split()) < 4: 
                 if k in ["TUTEUR_ECOLE", "TUTEUR_ENTREPRISE"]:
                     # print(f"   [Nettoyage] Nom générique détecté pour {k} ({v}) -> Reset à INCONNU")
                     infos[k] = "INCONNU"

    invented_keys = set()
    missing_alerts = []
    
    # 2. Déduction Automatique (Email, Dates)
    if infos.get("ETUDIANT_NOM") != "INCONNU" and (infos.get("ETUDIANT_CONTACT") == "INCONNU" or "email" in str(infos.get("ETUDIANT_CONTACT"))):
        nom_clean = infos["ETUDIANT_NOM"].lower().replace(" ", ".").replace("é", "e")
        infos["ETUDIANT_CONTACT"] = f"{nom_clean}@gmail.com"
        # print(f"   [Déduction] Email généré : {infos['ETUDIANT_CONTACT']}")

    # 3. Résolution des Structures (Entreprise, Ecole, Formation)
    keys_struct = ["ENTREPRISE", "ECOLE", "FORMATION", "TITRE_STAGE", "ETUDIANT_NOM", "DATES_STAGE"]
    defaults = {
        "ETUDIANT_NOM": "Alexandre Dupont",
        "DATES_STAGE": f"Février - Août {datetime.now().year}",
        "ENTREPRISE": "TechSolutions",
        "ECOLE": "Université de Paris",
        "FORMATION": "Master Informatique",
        "TITRE_STAGE": "Développement d'une solution IA"
    }

    for k in keys_struct:
        val = infos.get(k, "INCONNU")
        if val == "INCONNU" or len(str(val)) < 2:
            # print(f"   [Invention] {k} manquant. Génération plausible...")
            inv_prompt = f"""Tu dois définir : {k}.
            Contexte du stage (Notes) : {rag_notes[:1500]}
            Si l'info est dans les notes, extrais-la.
            Sinon, INVENTE une valeur réaliste (ex: "{defaults.get(k, '...')}") cohérente avec le reste.
            Réponds UNIQUEMENT par la valeur.
            """
            invented = llm.invoke([HumanMessage(content=inv_prompt)]).content.strip()
            if not invented or "INCONNU" in invented or len(invented) < 2:
                invented = defaults.get(k, "INCONNU")
            infos[k] = invented
            invented_keys.add(k)
            missing_alerts.append(f"{k} (Généré : {invented})")
            # print(f"   -> {k} : {invented} (Inventé)")

    # 4. Recherche Web Enrichie (Contexte Entreprise/Formation/Tuteurs)
    web_context = ""
    
    # Recherche Entreprise
    if infos.get("ENTREPRISE") != "INCONNU" and infos.get("ENTREPRISE") != "TechSolutions":
        # print(f"   [Tavily] Recherche Activité {infos['ENTREPRISE']}...")
        try:
            res = internet_search.invoke(f"Activité principale {infos['ENTREPRISE']} présentation")
            web_context += f"\n--- CONTEXTE ENTREPRISE ({infos['ENTREPRISE']}) ---\n{res[:500]}...\n"
        except: pass

    # Recherche Formation/École
    if infos.get("FORMATION") != "INCONNU" and infos.get("ECOLE") != "INCONNU":
        # print(f"   [Tavily] Recherche Programme {infos['FORMATION']} {infos['ECOLE']}...")
        try:
            res = internet_search.invoke(f"Programme objectifs {infos['FORMATION']} {infos['ECOLE']}")
            web_context += f"\n--- CONTEXTE FORMATION ({infos['FORMATION']}) ---\n{res[:500]}...\n"
        except: pass

    # 5. Résolution des Personnes (Tuteurs) avec Recherche Ciblée
    keys_people = [
        {"key": "TUTEUR_ENTREPRISE", "label": "Tuteur Entreprise", "deps": ["ENTREPRISE"], "query": "CTO ou responsable technique {}"},
        {"key": "TUTEUR_ECOLE", "label": "Tuteur Académique", "deps": ["ECOLE", "FORMATION"], "query": "Responsable pédagogique {} {}"}
    ]

    for item in keys_people:
        k = item["key"]
        val = infos.get(k, "INCONNU")
        
        # Si le nom est déjà connu, on cherche des infos sur lui
        if val != "INCONNU" and len(str(val)) > 2:
            # print(f"   [Tavily] Recherche infos sur {item['label']} ({val})...")
            try:
                res = internet_search.invoke(f"{val} {infos[item['deps'][0]]} profil")
                web_context += f"\n--- CONTEXTE {item['label'].upper()} ({val}) ---\n{res[:300]}...\n"
            except: pass
            continue 

        deps = item["deps"]
        # On cherche si les dépendances sont connues (même inventées, on tente la recherche pour voir si ça existe vraiment)
        context_vals = [infos[d] for d in deps]
        
        # --- CORRECTION MAJEURE : On ne lance la recherche que si les dépendances ne sont PAS inventées ---
        # Si l'école ou la formation vient d'être inventée (contient "Inventé" ou est générique), on ne cherche pas le tuteur
        deps_are_invented = any("Inventé" in str(infos[d]) or "INCONNU" in str(infos[d]) for d in deps)
        
        if deps_are_invented:
             # print(f"   [Info] Recherche {item['label']} reportée (Dépendances inventées/inconnues).")
             infos[k] = "INCONNU"
             missing_alerts.append(f"{item['label']} (En attente d'infos)")
             continue

        query = item["query"].format(*context_vals)
        
        # print(f"   [Tavily] Recherche {item['label']} pour {context_vals}...")
        found_via_search = False
        try:
            res = internet_search.invoke(query)
            ext_prompt = prompts.EXTRACTION_INVENTION.format(label=item['label'], res=res)
            found = llm.invoke([HumanMessage(content=ext_prompt)]).content.strip()
            if found and "INCONNU" not in found and len(found) > 2:
                infos[k] = found
                found_via_search = True
                # print(f"   -> Trouvé : {found}")
                # On ajoute le contexte trouvé
                web_context += f"\n--- CONTEXTE {item['label'].upper()} (Trouvé) ---\n{res[:300]}...\n"
        except Exception as e: 
            # print(f"   [Erreur Web] {e}")
            pass
        
        if not found_via_search:
            # Si on n'a pas trouvé, on laisse INCONNU pour l'instant si c'est le tuteur académique
            # pour éviter d'inventer trop vite si l'utilisateur vient de donner l'école
            if k == "TUTEUR_ECOLE" and feedback:
                 # print(f"   [Info] {item['label']} non trouvé, laissé INCONNU pour correction ultérieure.")
                 infos[k] = "INCONNU"
                 missing_alerts.append(f"{item['label']} (Manquant)")
            else:
                # print(f"   [Invention] {item['label']} (Recherche vaine)...")
                inv_prompt = f"""Invente un nom plausible pour {item['label']}.
                Contexte : {context_vals}.
                Réponds juste par un Prénom Nom (ex: Pierre Dupont).
                """
                invented = llm.invoke([HumanMessage(content=inv_prompt)]).content.strip()
                infos[k] = invented
                missing_alerts.append(f"{item['label']} (Inventé : {invented})")
                # print(f"   -> Inventé : {invented}")

    # Synthèse finale
    # On force l'inclusion de TOUS les contextes trouvés
    user_prompt = f"Notes internes :\n{rag_notes}\n\nInfos Validées/Générées :\n{json.dumps(infos, indent=2)}\n\nContexte Web :\n{web_context}\n\nSynthétise tout pour le rapport."
    result = call_llm(prompts.SYNTHESE_CONTEXTE.format(infos=json.dumps(infos, indent=2), web_context=web_context), user_prompt, state)
    
    return {"context_data": {"content": result, "raw_infos": infos}, "missing_infos": missing_alerts}

def coeur_rapport(state: AgentState):
    print("--- Tâche : Corps du Rapport ---")
    rag_notes = search_documents.invoke("Missions, tâches techniques, difficultés, réussites")
    
    # Planification
    print("   [1/2] Planification des parties...")
    llm = get_llm()
    parser = JsonOutputParser(pydantic_object=PlanRapport)
    plan_prompt = prompts.PLANIFICATION_CORPS
    
    try:
        response = llm.invoke([SystemMessage(content=prompts.SECURITY_SYSTEM_PROMPT + "\n" + plan_prompt), HumanMessage(content=f"Notes :\n{rag_notes}")])
        try: plan_data = parser.parse(response.content)
        except: 
            fix_resp = llm.invoke([HumanMessage(content=f"Corrige ce JSON:\n{response.content}")])
            plan_data = parser.parse(fix_resp.content)
        
        # --- CORRECTION JSON : Gestion robuste du format ---
        if plan_data is None:
            raise ValueError("Le JSON parsé est vide (None).")
            
        if isinstance(plan_data, list):
            raw_parties = plan_data
        else:
            raw_parties = plan_data.get("parties", [])
            
        if not raw_parties:
             raise ValueError("Aucune partie trouvée dans le plan.")

        plan = [p for p in raw_parties if not any(x in (p.get("titre") if isinstance(p, dict) else p.titre).lower() for x in ["introduction", "conclusion", "remerciement", "annexe"])]
        
    except Exception as e:
        print(f"   [Attention] Échec de la planification automatique ({e}). Utilisation d'un plan standard.")
        # Plan de secours robuste pour éviter le blocage
        plan = [
            {"titre": "Analyse du Contexte et des Besoins", "contenu": "Analyse approfondie de l'environnement, des enjeux et des objectifs du projet."},
            {"titre": "État de l'Art et Choix Techniques", "contenu": "Étude des solutions existantes, comparatif technologique et justification des choix."},
            {"titre": "Conception et Architecture", "contenu": "Architecture détaillée de la solution, modélisation des données et des flux."},
            {"titre": "Réalisation et Développement", "contenu": "Description technique des développements majeurs, algorithmes et code."},
            {"titre": "Challenges Techniques et Solutions", "contenu": "Focus sur les difficultés rencontrées et les solutions techniques apportées."},
            {"titre": "Tests, Validation et Résultats", "contenu": "Protocole de tests, résultats obtenus et validation par rapport aux objectifs."}
        ]

    # Rédaction
    full_body = ""
    print(f"   [2/2] Rédaction des {len(plan)} parties techniques...")
    for p in plan:
        titre = p.get("titre") if isinstance(p, dict) else p.titre
        desc = p.get("contenu") if isinstance(p, dict) else p.contenu
        print(f"      > Rédaction : {titre}...")
        content = call_llm(prompts.REDACTION_PARTIE.format(titre=titre, desc=desc), f"Notes complètes du stage (RAG):\n{rag_notes}", state)
        full_body += f"# {titre}\n\n{content}\n\n"

    return {"report_body": full_body}

def creation_introduction(state: AgentState):
    print("--- Tâche : Introduction ---")
    context = state.get('context_data', {}).get('content', '')
    raw_infos = state.get('context_data', {}).get('raw_infos', {})
    body_summary = state.get('report_body', '')[:1000]
    style = consult_style_guide.invoke("Exemple d'introduction")
    
    # Injection explicite des infos
    infos_str = json.dumps(raw_infos, indent=2, ensure_ascii=False)
    
    return {"introduction": call_llm(prompts.REDACTION_INTRO.format(context=context), f"Style:\n{style}\nInfos Clés:\n{infos_str}\nCorps:\n{body_summary}", state)}

def creation_conclusion(state: AgentState):
    print("--- Tâche : Conclusion ---")
    body_end = state.get('report_body', '')[-1000:]
    style = consult_style_guide.invoke("Exemple de conclusion")
    return {"conclusion": call_llm(prompts.REDACTION_CONCL, f"Style:\n{style}\nCorps:\n{body_end}", state)}

def creation_mise_en_page(state: AgentState):
    print("--- Tâche : Assemblage & Finitions ---")
    infos = state.get('context_data', {}).get('content')
    raw_infos = state.get('context_data', {}).get('raw_infos', {})
    body = state.get('report_body')
    style_annexes = consult_style_guide.invoke("Exemple de page de garde, remerciements")
    current_date = datetime.now().strftime("%d %B %Y")
    
    # Injection explicite des infos pour les remerciements
    infos_str = json.dumps(raw_infos, indent=2, ensure_ascii=False)
    
    # Tentative de déduction de la ville
    ville = "Calais" # Par défaut pour ULCO
    if "paris" in str(raw_infos.get("ECOLE", "")).lower(): ville = "Paris"
    elif "lyon" in str(raw_infos.get("ECOLE", "")).lower(): ville = "Lyon"

    # print("   [1/3] Avant-propos...")
    ap_prompt = prompts.REDACTION_AVANT_PROPOS.format(date=current_date, ville=ville, infos=infos)
    avant_propos = call_llm(ap_prompt, f"Style:\n{style_annexes}", state)

    # print("   [2/3] Remerciements...")
    remerciements = call_llm(prompts.REDACTION_REMERCIEMENTS.format(infos=infos), f"Style:\n{style_annexes}", state)
    if "# AVANT-PROPOS" in remerciements:
        remerciements = remerciements.replace("# AVANT-PROPOS", "\n\n# AVANT-PROPOS")

    # print("   [3/3] Bibliographie...")
    biblio = call_llm(prompts.REDACTION_BIBLIO, f"Sujet:\n{body[:1000]}", state)

    return {"final_layout": {
        "avant_propos": avant_propos, "remerciements": remerciements,
        "intro": state.get('introduction'), "body": body, "concl": state.get('conclusion'),
        "biblio": biblio, "raw_infos": raw_infos
    }}

def verification_humaine(state: AgentState):
    print(f"--- Vérification : {state.get('current_node')} ---")
    return state

def generation_finale(state: AgentState):
    print("--- ASSEMBLAGE FINAL MARKDOWN ---")
    l = state.get("final_layout", {})
    
    full_md = ""
    full_md += f"{l.get('avant_propos', '')}\n\n"
    full_md += f"{l.get('remerciements', '')}\n\n"
    # Sommaire géré par PDF
    full_md += f"{l.get('intro', '')}\n\n"
    full_md += f"{l.get('body', '')}\n\n"
    full_md += f"{l.get('concl', '')}\n\n"
    full_md += f"{l.get('biblio', '')}\n\n"
    
    lines = full_md.split('\n')
    clean_lines = [line for line in lines if not line.strip().lower().startswith(("note :", "notes :", "notes pour", "hiérarchie visuelle"))]
    full_md = '\n'.join(clean_lines)

    output_path = os.path.join(OUTPUT_DIR, "Rapport_de_Stage_Final.md")
    with open(output_path, "w", encoding="utf-8") as f: f.write(full_md)
    print(f"Fichier Markdown sauvegardé : {output_path}")
    return state

def conversion_pdf(state: AgentState):
    print("--- CONVERSION EN PDF ---")
    md_path = os.path.join(OUTPUT_DIR, "Rapport_de_Stage_Final.md")
    pdf_path = os.path.join(OUTPUT_DIR, "Rapport_de_Stage_Final.pdf")
    
    # On utilise directement le layout structuré pour éviter les erreurs de parsing
    layout = state.get('final_layout', {})
    if not layout:
        print("Erreur : Pas de layout final disponible.")
        return {**state, "current_node": "conversion_pdf"}
        
    raw_infos = layout.get('raw_infos', {})
    def get_info(k, default):
        v = raw_infos.get(k, default)
        # Nettoyage final des variables pour la page de garde
        if v and isinstance(v, str):
            # Enlever tout ce qui est entre parenthèses ou après un tiret explicatif
            v = re.sub(r"\(.*?\)", "", v)
            v = v.split(" - ")[0]
            v = v.strip()
        return v if v and v not in ["INCONNU", "null", "None"] else default

    entreprise = get_info('ENTREPRISE', "Entreprise d'Accueil")
    tuteur = get_info('TUTEUR_ENTREPRISE', "Tuteur Entreprise")
    tuteur_ecole = get_info('TUTEUR_ECOLE', "Tuteur Académique")
    ecole = get_info('ECOLE', "Université / École")
    formation = get_info('FORMATION', "Formation")
    titre_stage = get_info('TITRE_STAGE', "RAPPORT DE STAGE")
    etudiant_nom = get_info('ETUDIANT_NOM', "Prénom Nom")
    etudiant_contact = get_info('ETUDIANT_CONTACT', "email@etudiant.fr")
    dates_stage = get_info('DATES_STAGE', "Dates du stage")
    
    try:
        months = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        now = datetime.now()
        # Sécurisation du calcul de la date
        current_date_fr = f"{months[int(now.month)-1]} {now.year}"
        
        # --- CSS AMÉLIORÉ ---
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
            @page cover_page {
                size: A4;
                margin: 1cm;
                background-color: #ffffff;
            }
            
            body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; text-align: justify; color: #333; }
            
            /* Titres */
            h1 { 
                color: #2c3e50; 
                font-size: 24pt; 
                margin-top: 0; 
                margin-bottom: 30px; 
                padding-bottom: 10px;
                border-bottom: 2px solid #2c3e50;
                page-break-before: always;
                -pdf-keep-with-next: true;
            }
            h2 { 
                color: #34495e; 
                font-size: 18pt; 
                margin-top: 35px; 
                margin-bottom: 15px; 
                page-break-after: avoid;
                -pdf-keep-with-next: true;
            }
            h3 { 
                color: #7f8c8d; 
                font-size: 14pt; 
                margin-top: 20px; 
                margin-bottom: 10px; 
                page-break-after: avoid;
                -pdf-keep-with-next: true;
            }
            
            /* Sommaire */
            pdftoc { color: #2c3e50; }
            pdftoc.pdftoclevel0 { 
                font-weight: bold; 
                margin-top: 12px; 
                color: #2c3e50; 
                font-size: 12pt;
            }
            pdftoc.pdftoclevel1 { 
                margin-left: 25px; 
                font-size: 11pt; 
                color: #555; 
                font-style: italic;
            }
            
            /* Tables et Listes */
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; page-break-inside: avoid; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            
            ul, ol { margin-bottom: 10px; padding-left: 20px; }
            li { margin-bottom: 5px; }
            
            /* Page de garde - Design vertical centré pour éviter les bugs de tableau */
            .cover-container { text-align: center; padding-top: 50px; }
            .cover-title { font-size: 40pt; color: #2c3e50; margin-bottom: 10px; font-weight: bold; }
            .cover-subtitle { font-size: 22pt; color: #7f8c8d; margin-bottom: 50px; }
            .cover-box { border-top: 3px solid #34495e; border-bottom: 3px solid #34495e; padding: 30px; margin: 0 20px; background-color: #f9f9f9; }
            .cover-subject { font-size: 24pt; font-weight: bold; color: #34495e; line-height: 1.3; }
            .cover-student { font-size: 18pt; font-weight: bold; color: #2c3e50; margin-top: 40px; }
            .cover-contact { font-size: 12pt; color: #7f8c8d; }
            .cover-school { margin-top: 20px; font-size: 14pt; }
            .cover-dates { font-style: italic; color: #7f8c8d; margin-top: 5px; }
            
            .cover-mentors { margin-top: 50px; font-size: 13pt; line-height: 1.6; }
            .mentor-block { margin-bottom: 20px; }
            .mentor-label { color: #7f8c8d; font-size: 11pt; text-transform: uppercase; letter-spacing: 1px; }
            
            .cover-footer { position: absolute; bottom: 0; width: 100%; text-align: center; font-size: 12pt; color: #7f8c8d; }
        </style>
        """
        
        # --- PAGE DE GARDE SANS TABLEAU ---
        cover_html = f"""
        <div class="cover-container">
            <div class="cover-title">RAPPORT DE STAGE</div>
            <div class="cover-subtitle">Fin d'Études - Ingénieur Informatique</div>
            
            <div class="cover-box">
                <div class="cover-subject">{titre_stage}</div>
            </div>
            
            <div class="cover-student">{etudiant_nom}</div>
            <div class="cover-contact">{etudiant_contact}</div>
            
            <div class="cover-school">
                <strong>{formation}</strong><br/>
                {ecole}
            </div>
            <div class="cover-dates">{dates_stage}</div>
            
            <div class="cover-mentors">
                <div class="mentor-block">
                    <span class="mentor-label">Entreprise d'accueil</span><br/>
                    <strong>{entreprise}</strong><br/>
                    {tuteur}
                </div>
                
                <div class="mentor-block">
                    <span class="mentor-label">Tuteur Académique</span><br/>
                    <strong>{tuteur_ecole}</strong>
                </div>
            </div>
            
            <div class="cover-footer">
                {current_date_fr}
            </div>
        </div>
        <pdf:next template="body_template" />
        """
        
        # --- ASSEMBLAGE DU CONTENU ---
        # On construit le HTML bloc par bloc pour éviter les problèmes de parsing global
        
        html_parts = []
        html_parts.append(cover_html)
        
        # Avant-Propos & Remerciements
        if layout.get('avant_propos'):
            html_parts.append(markdown.markdown(layout['avant_propos']))
        
        if layout.get('remerciements'):
            # On force un saut de page si besoin, mais H1 le fait déjà
            html_parts.append(markdown.markdown(layout['remerciements']))
            
        # Sommaire (Page dédiée)
        toc_html = """
        <div id="toc">
            <h1 style="border-bottom: none; text-align: center; margin-bottom: 40px;">SOMMAIRE</h1>
            <pdf:toc />
        </div>
        <pdf:next template="body_template" />
        """
        html_parts.append(toc_html)
        
        # Corps du rapport
        if layout.get('intro'):
            html_parts.append(markdown.markdown(layout['intro']))
            
        if layout.get('body'):
            html_parts.append(markdown.markdown(layout['body'], extensions=['tables']))
            
        if layout.get('concl'):
            html_parts.append(markdown.markdown(layout['concl']))
            
        if layout.get('biblio'):
            html_parts.append(markdown.markdown(layout['biblio']))
            
        # Footer
        footer_html = """<div id="footer_content" style="text-align: center; font-size: 10pt; color: #7f8c8d;">Page <pdf:pagenumber /></div>"""
        
        # Concaténation finale
        full_content = "".join(html_parts)
        full_html = f"<html><head>{css}</head><body>{full_content}{footer_html}</body></html>"
        
        with open(pdf_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(full_html, dest=pdf_file)
            
        if pisa_status.err: print("Erreur lors de la conversion PDF.")
        else: print(f"Fichier PDF généré avec succès : {os.path.abspath(pdf_path)}")
            
    except Exception as e: 
        print(f"Exception lors de la conversion PDF : {e}")
        traceback.print_exc()
        
    # On retourne l'état avec current_node mis à jour pour signaler la fin
    return {**state, "current_node": "conversion_pdf"}

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
workflow.add_conditional_edges("orchestrateur", lambda x: x["current_node"], {
    "contexte": "contexte",
    "corps_rapport": "corps_rapport",
    "introduction": "introduction",
    "conclusion": "conclusion",
    "mise_en_page": "mise_en_page",
    "generation": "generation",
    "conversion_pdf": "conversion_pdf"
})
for t in ["contexte", "corps_rapport", "introduction", "conclusion", "mise_en_page"]: workflow.add_edge(t, "verification_humaine")
workflow.add_conditional_edges("verification_humaine", route_after_human, {"valide": "orchestrateur", "refuse": "orchestrateur"})
workflow.add_edge("generation", "conversion_pdf")
workflow.add_edge("conversion_pdf", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory, interrupt_before=["verification_humaine"])
