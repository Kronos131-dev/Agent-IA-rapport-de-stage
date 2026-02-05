# Roadmap : Agent IA Rédacteur de Rapport de Stage

## Phase 1 : Initialisation & Infrastructure
- [ ] **Setup du projet** : Création de l'arborescence et de l'environnement virtuel.
- [ ] **Installation des dépendances** : LangGraph, LangChain, etc.

## Phase 2 : Gestion des Données (Ingestion RAG)
- [ ] **Ingestion des documents** : Support initial des fichiers `.txt` (notes de stage).
- [ ] **Traitement des données** : Découpage (chunking) et nettoyage du texte.

## Phase 3 : Architecture de l'Agent (LangGraph)
- [ ] **Implémentation des Nœuds**
- [ ] **Construction du Graph**

## Phase 4 : Outils & Contexte
- [ ] **Définition du System Prompt** : Persona de l'agent (ton académique, structure formelle).
- [ ] **Intégration des Tools** : Définition des outils à mettre à la disposition de l'agent et à quels moments

## Phase 5 : Génération & Rendu
- [ ] **Sortie Markdown** : Assemblage du rapport final au format `.md`.
- [ ] **Conversion PDF** : Pipeline de conversion Markdown vers PDF

## Phase 6 : Interaction & Itération
- [ ] **Interaction Utilisateur** : Gestion des validations et retours de l'utilisateur
- [ ] **Boucle de Feedback** : Ajustement du contenu généré selon les retours utilisateurs.

## Phase 7 : Optimisation & Finalisation
- [ ] **Optimisation du RAG** : Amélioration de la pertinence des documents retrouvés.
- [ ] **Prompt Engineering** : Affinage des prompts pour la qualité rédactionnelle.
- [ ] **Tests** : Test de l'agent avec MLFlow.
- [ ] **Validation Sécurité** : Tests de robustesse contre les injections malveillantes.