import os
import glob
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from Plinius.utils.rag_config import get_embeddings, DOCS_DIR, CHROMA_DB_DIR

def ingest_documents():
    """
    Charge les documents .txt, les découpe et crée/met à jour la base vectorielle Chroma.
    """
    print(f"--- Démarrage de l'ingestion depuis {DOCS_DIR} ---")
    
    # 1. Chargement des documents
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        print(f"Dossier {DOCS_DIR} créé. Veuillez y ajouter vos fichiers .txt.")
        return

    txt_files = glob.glob(os.path.join(DOCS_DIR, "*.txt"))
    if not txt_files:
        print(f"Aucun fichier .txt trouvé dans {DOCS_DIR}.")
        return

    documents = []
    for file_path in txt_files:
        try:
            loader = TextLoader(file_path, encoding='utf-8')
            documents.extend(loader.load())
            print(f"Chargé: {file_path}")
        except Exception as e:
            print(f"Erreur lors du chargement de {file_path}: {e}")

    if not documents:
        return

    # 2. Découpage (Chunking)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Documents découpés en {len(chunks)} morceaux.")

    # 3. Création/Mise à jour du Vector Store
    print("Initialisation du modèle d'embeddings...")
    embeddings = get_embeddings()
    
    print(f"Création de la base vectorielle dans {CHROMA_DB_DIR}...")
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_DIR
    )
    
    print("--- Ingestion terminée avec succès ! ---")

if __name__ == "__main__":
    ingest_documents()
