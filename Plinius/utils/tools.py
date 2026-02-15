import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain.tools import tool
from tavily import TavilyClient
from Plinius.utils.rag_config import get_embeddings, CHROMA_DB_DIR, STYLE_DB_DIR

# Chargement des variables d'environnement
load_dotenv()

# --- RAG Notes (Contenu) ---
_vectorstore = None

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        if not os.path.exists(CHROMA_DB_DIR):
            # On ne lève plus d'erreur bloquante, on retourne None pour gérer le cas "pas encore ingéré"
            print(f"Attention : Base vectorielle introuvable dans {CHROMA_DB_DIR}.")
            return None
        embeddings = get_embeddings()
        _vectorstore = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    return _vectorstore

@tool
def search_documents(query: str) -> str:
    """Recherche dans les notes de stage de l'utilisateur."""
    try:
        vs = get_vectorstore()
        if not vs: return "Aucune note disponible (base vectorielle vide)."
        results = vs.similarity_search(query, k=5)
        if not results: return "Aucune info trouvée."
        return "\n\n".join([f"[Note]: {doc.page_content}" for doc in results])
    except Exception as e:
        return f"Erreur RAG : {e}"

# --- RAG Style (Forme) ---
_style_vectorstore = None

def get_style_vectorstore():
    global _style_vectorstore
    if _style_vectorstore is None:
        if not os.path.exists(STYLE_DB_DIR):
            return None 
        embeddings = get_embeddings()
        _style_vectorstore = Chroma(persist_directory=STYLE_DB_DIR, embedding_function=embeddings)
    return _style_vectorstore

@tool
def consult_style_guide(query: str) -> str:
    """
    Consulte l'exemple de rapport de stage (PDF) pour s'inspirer de la mise en page.
    """
    try:
        vs = get_style_vectorstore()
        if not vs: return "Aucun guide de style disponible."
        results = vs.similarity_search(query, k=3)
        return "\n\n".join([f"[Exemple]: {doc.page_content}" for doc in results])
    except Exception as e:
        return f"Erreur Style : {e}"

# --- Web Search (Tavily Client Direct) ---

tavily_api_key = os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key=tavily_api_key) if tavily_api_key else None

@tool
def internet_search(query: str):
    """Does an internet research using Tavily Advanced Search."""
    if not tavily_client:
        return "Erreur: Clé API Tavily non configurée."
    
    try:
        result = tavily_client.search(query, search_depth="advanced")
        if 'results' in result:
            formatted_results = "\n".join([f"- {res['content']} ({res['url']})" for res in result['results'][:3]])
            return formatted_results
        return str(result)
    except Exception as e:
        return f"Erreur Tavily : {e}"
