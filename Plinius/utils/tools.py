import os
from langchain_chroma import Chroma
from langchain.tools import tool
from Plinius.utils.rag_config import get_embeddings, CHROMA_DB_DIR

# Initialisation globale du VectorStore
# On le charge une seule fois pour éviter de recharger à chaque appel
_vectorstore = None

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        if not os.path.exists(CHROMA_DB_DIR):
            raise FileNotFoundError(f"La base vectorielle n'existe pas dans {CHROMA_DB_DIR}. Veuillez lancer l'ingestion d'abord.")
        
        embeddings = get_embeddings()
        _vectorstore = Chroma(
            persist_directory=CHROMA_DB_DIR,
            embedding_function=embeddings
        )
    return _vectorstore

@tool
def search_documents(query: str) -> str:
    """
    Recherche des informations pertinentes dans les notes de stage (documents .txt).
    Utilisez cet outil pour trouver des détails sur les missions, l'entreprise, ou les tâches réalisées.
    """
    try:
        vectorstore = get_vectorstore()
        results = vectorstore.similarity_search(query)
        
        if not results:
            return "Aucune information trouvée dans les documents."
            
        # Concaténation des résultats
        context = "\n\n".join([f"[Source: {doc.metadata.get('source', 'Inconnu')}]\n{doc.page_content}" for doc in results])
        return context
    except Exception as e:
        return f"Erreur lors de la recherche : {str(e)}"
