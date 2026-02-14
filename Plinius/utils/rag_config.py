import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# Configuration des chemins et modèles
DOCS_DIR = "./documents"
CHROMA_DB_DIR = "./chroma_db"

# Modèles de haute qualité pour le français et l'anglais
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"

def get_embeddings():
    """
    Initialise et retourne le modèle d'embeddings (BAAI/bge-m3).
    Ce modèle est multilingue et performant pour la recherche sémantique dense.
    """
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"trust_remote_code": True}
    )

def get_reranker():
    """
    Initialise et retourne le modèle de reranking (CrossEncoder).
    Utilisé pour réordonner les résultats du RAG et améliorer la précision.
    """
    return HuggingFaceCrossEncoder(
        model_name=RERANKER_MODEL_NAME,
        model_kwargs={"trust_remote_code": True}
    )
