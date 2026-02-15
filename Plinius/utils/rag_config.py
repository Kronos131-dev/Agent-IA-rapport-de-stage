import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# Chemins relatifs à la racine du projet
# On suppose que le script est lancé depuis la racine
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

DOCS_DIR = os.path.join(DATA_DIR, "documents")
CHROMA_DB_DIR = os.path.join(DATA_DIR, "chroma_db")
STYLE_DB_DIR = os.path.join(DATA_DIR, "chroma_style_db") # Ajouté ici pour centraliser

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

def get_embeddings():
    """Initialise et retourne le modèle d'embeddings."""
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"trust_remote_code": True}
    )

def get_reranker():
    """Initialise et retourne le modèle de reranking (CrossEncoder)."""
    return HuggingFaceCrossEncoder(
        model_name=RERANKER_MODEL_NAME,
        model_kwargs={"trust_remote_code": True}
    )
