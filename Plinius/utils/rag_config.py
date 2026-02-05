from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

# Configuration des chemins et modèles
DOCS_DIR = "./documents"
CHROMA_DB_DIR = "./chroma_db"

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
