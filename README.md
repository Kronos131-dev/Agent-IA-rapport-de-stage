# 🦉 Plinius : Agent IA Rédacteur de Rapport de Stage

**Plinius** est un agent intelligent autonome conçu pour rédiger des rapports de stage de fin d'études (Bac+5 / Ingénieur) de haute qualité, complets et prêts à l'emploi.

Il combine la puissance des **LLM (Mistral Large)**, du **RAG (Retrieval Augmented Generation)** sur vos notes personnelles, et de la **Recherche Web (Tavily)** pour produire un document dense (~50-70 pages), structuré et professionnel.

---

## ✨ Fonctionnalités Clés

*   **🧠 Analyse Intelligente** : Lit et comprend vos notes de stage (fichiers `.txt`) pour en extraire le fond technique et les missions.
*   **🌐 Recherche Web Autonome** : Trouve automatiquement les informations manquantes (chiffres clés de l'entreprise, bio du tuteur, détails sur la formation) via Tavily.
*   **💡 Invention Plausible** : Si une information est introuvable (ex: nom du tuteur académique), Plinius propose une invention crédible ("Professeur Martin") pour ne jamais laisser de trous dans le rapport.
*   **✍️ Rédaction "Ingénieur Senior"** : Génère un contenu dense, technique et fluide, sans "remplissage" inutile.
*   **🔄 Workflow Interactif** : Vous gardez le contrôle à chaque étape. Validez ou corrigez le travail de l'agent en temps réel.
*   **📄 Rendu PDF Pro** : Génère un PDF final avec une mise en page soignée (page de garde design, sommaire, sauts de page, typographie).
*   **🛡️ Sécurité & Monitoring** : Protégé contre les injections de prompt et tracé via **MLflow** pour le débogage.

---

## 🚀 Installation

### 1. Prérequis
- Python 3.10+
- Une clé API **Mistral AI** (pour l'intelligence).
- Une clé API **Tavily** (pour la recherche web).

### 2. Installation des dépendances
```bash
pip install -r requirements.txt
```

### 3. Configuration
Créez un fichier `.env` à la racine du projet et ajoutez vos clés :
```env
MISTRAL_API_KEY=votre_cle_mistral
TAVILY_API_KEY=votre_cle_tavily
```

### 4. Préparation des Données
1.  Placez vos notes de stage (fichiers `.txt`) dans le dossier `data/documents/` (créez-le s'il n'existe pas).
2.  (Optionnel) Placez un PDF exemple de style nommé `Exemple de rapport de stage.pdf` dans `data/`.
3.  Lancez l'ingestion des documents :
    ```bash
    python -m scripts.ingest
    # Si vous avez un guide de style :
    python -m scripts.ingest_style
    ```

---

## 🎮 Guide d'Utilisation

Pour lancer l'agent, exécutez simplement :
```bash
python -m Plinius.start_plinius
```

### Le Workflow Interactif (Terminal)

L'agent fonctionne étape par étape (Contexte -> Plan -> Rédaction -> Mise en page). À la fin de chaque étape, il vous présente son travail et attend votre validation.

**Vous avez deux choix :**

1.  **Valider (`o`)** :
    *   Tapez `o` (oui) et Entrée.
    *   L'agent passe à l'étape suivante.

2.  **Corriger / Compléter (`n`)** :
    *   Tapez `n` (non) ou n'importe quelle autre touche.
    *   L'agent vous demandera : *"Veuillez donner vos instructions de correction"*.
    *   **C'est le moment d'agir !** Vous pouvez :
        *   Donner une info manquante : *"Mon tuteur s'appelle Jean Dupont"*.
        *   Corriger une erreur : *"L'entreprise ne fait pas de BTP, c'est de la Tech"*.
        *   Demander une réécriture : *"Rends cette partie plus technique"*.
    *   L'agent prendra en compte votre feedback et recommencera l'étape.

### 💡 L'Invention Intelligente (Smart Filling)

Plinius déteste les trous (`[...]`).
*   **S'il ne trouve pas une info** (ex: le nom de votre responsable pédagogique) dans vos notes ni sur le web, **il inventera un nom plausible** pour que la mise en page reste impeccable.
*   **Pas de panique !** Lors de l'étape de validation, il vous signalera ce qu'il a inventé. Si cela ne vous convient pas, utilisez l'option de correction (`n`) pour donner le vrai nom. Sinon, validez (`o`) et modifiez le PDF final plus tard si nécessaire.

---

## 📊 Monitoring & Tests (MLflow)

Plinius intègre **MLflow** pour tracer chaque exécution et sauvegarder les artefacts générés.

Pour visualiser l'historique de vos générations :
```bash
# Depuis la racine du projet
mlflow ui --backend-store-uri sqlite:///data/mlflow.db
```
Ouvrez ensuite `http://127.0.0.1:5000` dans votre navigateur.

---

## 📂 Structure du Projet

```
Agent-IA-rapport-de-stage/
├── data/                   # Données (créé automatiquement)
│   ├── documents/          # Vos notes de stage (.txt)
│   ├── chroma_db/          # Base vectorielle (générée)
│   └── mlflow.db           # Base de données de tracking MLflow
├── output/                 # Rapports générés (.md, .pdf)
├── Plinius/                # Code source de l'agent
│   ├── utils/              # Modules utilitaires (LLM, RAG, Prompts, Sécurité...)
│   └── start_plinius.py    # Point d'entrée principal
├── scripts/                # Scripts d'ingestion
│   ├── ingest.py
│   └── ingest_style.py
├── .env                    # Clés API (à créer)
├── README.md               # Documentation
└── requirements.txt        # Dépendances Python
```

---

*Fait par Kronos le 15/02/2025.*
