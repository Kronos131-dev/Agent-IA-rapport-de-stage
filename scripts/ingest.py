import os
import glob
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from Plinius.utils.rag_config import get_embeddings, DOCS_DIR, CHROMA_DB_DIR

def ingest_documents():
    """
    Charge les documents .txt depuis le dossier 'documents', les découpe en morceaux (chunks)
    et crée ou met à jour la base vectorielle Chroma pour le RAG.
    """
    print(f"--- Démarrage de l'ingestion depuis {DOCS_DIR} ---")
    
    # Vérification de l'existence du dossier documents
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        print(f"Dossier '{DOCS_DIR}' créé. Veuillez y ajouter vos fichiers de notes (.txt).")
        return

    # Récupération des fichiers .txt
    txt_files = glob.glob(os.path.join(DOCS_DIR, "*.txt"))
    if not txt_files:
        print(f"Aucun fichier .txt trouvé dans '{DOCS_DIR}'. Ajoutez vos notes et relancez.")
        return

    documents = []
    for file_path in txt_files:
        try:
            loader = TextLoader(file_path, encoding='utf-8')
            loaded_docs = loader.load()
            documents.extend(loaded_docs)
            print(f"   [OK] Chargé : {os.path.basename(file_path)}")
        except Exception as e:
            print(f"   [ERREUR] Impossible de charger {os.path.basename(file_path)} : {e}")

    if not documents:
        print("Aucun document valide n'a été chargé.")
        return

    # Découpage (Chunking) intelligent
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Documents découpés en {len(chunks)} morceaux.")

    # Création/Mise à jour du Vector Store
    print("Initialisation du modèle d'embeddings (BAAI/bge-m3)...")
    embeddings = get_embeddings()
    
    print(f"Indexation dans la base vectorielle : {CHROMA_DB_DIR}...")
    # On utilise from_documents qui gère la persistance automatiquement avec Chroma v0.4+
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_DIR
    )
    
    print("--- Ingestion terminée avec succès ! ---")

if __name__ == "__main__":
    ingest_documents()
