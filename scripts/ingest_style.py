import os
import sys

# Ajout du dossier parent au path pour importer Plinius
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from Plinius.utils.rag_config import get_embeddings, STYLE_DB_DIR, DATA_DIR

# Le PDF de style est maintenant dans data/
STYLE_PDF_PATH = os.path.join(DATA_DIR, "Exemple de rapport de stage.pdf")

def ingest_style_guide():
    """
    Ingère le PDF d'exemple (guide de style) pour servir de référence (ton, structure).
    Crée une base vectorielle séparée pour ne pas mélanger le fond (notes) et la forme (style).
    """
    print(f"--- Ingestion du Guide de Style : {STYLE_PDF_PATH} ---")
    
    if not os.path.exists(STYLE_PDF_PATH):
        print(f"ERREUR : Le fichier '{STYLE_PDF_PATH}' est introuvable.")
        print(f"Veuillez placer votre 'Exemple de rapport de stage.pdf' dans le dossier '{DATA_DIR}'.")
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
