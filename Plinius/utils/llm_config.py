import os
from dotenv import load_dotenv
from langchain_mistralai import ChatMistralAI

# Chargement des variables d'environnement
load_dotenv()

def get_llm():
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY non trouvée dans le fichier .env")
        
    return ChatMistralAI(
        model="mistral-large-latest",
        temperature=0.7,
        mistral_api_key=api_key
    )
