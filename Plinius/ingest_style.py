import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from Plinius.utils.rag_config import get_embeddings

# Configuration spécifique pour le style
STYLE_PDF_PATH = "./Exemple de rapport de stage.pdf"
STYLE_DB_DIR = "./chroma_style_db"

def ingest_style_guide():
    """
    Ingère le PDF d'exemple (guide de style) pour servir de référence (ton, structure).
    Crée une base vectorielle séparée pour ne pas mélanger le fond (notes) et la forme (style).
    """
    print(f"--- Ingestion du Guide de Style : {STYLE_PDF_PATH} ---")
    
    if not os.path.exists(STYLE_PDF_PATH):
        print(f"ERREUR : Le fichier '{STYLE_PDF_PATH}' est introuvable.")
        print("Veuillez placer votre 'Exemple de rapport de stage.pdf' à la racine du projet.")
        return

    # 1. Chargement du PDF
    try:
        loader = PyPDFLoader(STYLE_PDF_PATH)
        documents = loader.load()
        print(f"   [OK] PDF chargé : {len(documents)} pages.")
    except Exception as e:
        print(f"   [ERREUR] Impossible de lire le PDF : {e}")
        return

    # 2. Découpage
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100
    )
    chunks = text_splitter.split_documents(documents)
    print(f"   Découpé en {len(chunks)} segments.")
    
    # 3. Vector Store
    print("Initialisation des embeddings...")
    embeddings = get_embeddings()
    
    print(f"Création de la base de style dans '{STYLE_DB_DIR}'...")
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=STYLE_DB_DIR
    )
    print("--- Ingestion du Style terminée ! ---")

if __name__ == "__main__":
    ingest_style_guide()
