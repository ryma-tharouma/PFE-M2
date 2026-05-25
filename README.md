# 📚 PFE-M2 - Système RAG Intelligent pour Gestion de Documentation

> **Projet de Fin d'Études M2** - Système de Chatbot RAG (Retrieval-Augmented Generation) pour la gestion et recherche intelligente de manuels administratifs.

---

## 📋 Table des Matières

- [Vue d'ensemble](#-vue-densemble)
- [Architecture Générale](#-architecture-générale)
- [Composants Principaux](#-composants-principaux)
  - [Frontend (Laravel)](#frontend-laravel)
  - [Backend RAG (FastAPI)](#backend-rag-fastapi)
  - [Pipeline d'Extraction](#pipeline-dextraction)
  - [Infrastructure & DevOps](#infrastructure--devops)
- [Rôles Utilisateurs](#-rôles-utilisateurs)
- [Flux de Données](#-flux-de-données)
- [Configuration & Déploiement](#-configuration--déploiement)
- [Guide d'Utilisation](#-guide-dutilisation)
- [Dépannage](#-dépannage)

---

## 🎯 Vue d'ensemble

Le **PFE-M2** est un système complet de gestion et consultation de documentation utilisant les technologies modernes d'IA :

- **RAG (Retrieval-Augmented Generation)** : Combine la recherche sémantique et la génération de texte pour des réponses contextualisées
- **Vector Store (Qdrant)** : Stockage et recherche de représentations sémantiques des documents
- **LLM (Large Language Models)** : Génération des réponses basée sur Qwen 3.5 4B (CPU) ou 7B (GPU)
- **Authentification LDAP** : Intégration avec l'annuaire d'entreprise
- **WebSocket** : Communication en temps réel pour les réponses en streaming

### Cas d'usage principaux :
1. **Utilisateurs** 📖 : Consultation intelligente de manuels administratifs via chat
2. **Administrateurs** 👨‍💼 : Upload de nouveaux manuels, gestion des collections, suivi des tickets
3. **Support IT** 💻 : Création automatique de tickets GLPI depuis le chatbot

---

## 🏗️ Architecture Générale

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT WEB (Navigateur)                      │
│                                                                     │
│  ┌─────────────┐         ┌──────────────────┐                     │
│  │   Chat UI   │◄────────►│  Admin Panel     │                     │
│  │ (Messages)  │         │  (Upload PDF)    │                     │
│  └──────┬──────┘         └────────┬─────────┘                     │
└─────────┼──────────────────────────┼──────────────────────────────┘
          │                          │
          │ HTTP / WebSocket         │ HTTP
          │                          │
┌─────────▼──────────────────────────▼──────────────────────────────┐
│               FRONTEND (Laravel + PHP + JavaScript)                 │
│                                                                     │
│  ┌────────────────────┐  ┌────────────────────┐                   │
│  │  ChatController    │  │  AdminController   │                   │
│  │ - Chat messages    │  │ - Manual upload    │                   │
│  │ - Conversations    │  │ - Collection mgmt  │                   │
│  └────────┬───────────┘  └────────┬───────────┘                   │
│           │ LDAP Auth              │ API calls                     │
│  ┌────────▼────────────────────────▼──────────┐                   │
│  │  LdapAuthController                        │                   │
│  │  - Login via LDAP / OpenLDAP               │                   │
│  │  - Session management                      │                   │
│  └────────┬─────────────────────────────────┘                     │
│           │                                                        │
│  ┌────────▼──────────────────────────────────┐                   │
│  │  Models (Eloquent ORM)                     │                   │
│  │  - User (LDAP profile)                     │                   │
│  │  - Conversation, Message, Manual          │                   │
│  │  - Ticket (GLPI)                          │                   │
│  └────────┬────────────────────────────────┘                     │
│           │ Database queries/writes                               │
└───────────┼─────────────────────────────────────────────────────┘
            │
│ HTTP/HTTPS│
│ REST API  │
│ /ws/chat  │ WebSocket streaming
│           │
┌───────────▼────────────────────────────────────────────────────────┐
│               BACKEND RAG (FastAPI + Python)                        │
│              (Serveur Python sur port 8000)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                 │
│  │ RAGManager (main.py)                         │                 │
│  │ - Initialise la pipeline RAG                 │                 │
│  │ - Charge les collections Qdrant              │                 │
│  │ - Routage des requêtes                       │                 │
│  └──────┬───────────────────────────┬───────────┘                 │
│         │                           │                              │
│  ┌──────▼────────┐          ┌──────▼──────────┐                   │
│  │  Embedder     │          │  Vector Store   │                   │
│  │ (BGE-M3)      │          │  (Qdrant)       │                   │
│  │ - Encode text │          │ - Store vectors │                   │
│  │ - 1024 dims   │          │ - Search SIM    │                   │
│  └──────┬────────┘          └──────┬──────────┘                   │
│         │                           │                              │
│         │     ┌──────────────────────┤                             │
│         │     │                      │                             │
│  ┌──────▼─────▼────────┐   ┌────────▼──────────┐                 │
│  │ RAG Pipeline        │   │ Collections       │                 │
│  │ ┌─────────────────┐ │   │ Qdrant Data:      │                 │
│  │ │ 1. Retriever    │ │   │ - app_2levels...  │                 │
│  │ │  (Search top-k) │ │   │ - manual_2levels..│                 │
│  │ │ 2. Reranker     │ │   │ - etc             │                 │
│  │ │  (BGE-reranker) │ │   │                   │                 │
│  │ │ 3. Generator    │ │   │ (Persistent)      │                 │
│  │ │  (Qwen LLM)     │ │   │                   │                 │
│  │ │ 4. Session Mgmt │ │   └───────────────────┘                 │
│  │ └─────────────────┘ │                                         │
│  └─────────────────────┘                                         │
│                                                                     │
│  WebSocket /ws/chat          REST Endpoints                      │
│  - Streaming answers      GET  /health                           │
│  - Real-time tokens      GET  /api/collections                   │
│                          POST /api/chat                          │
│                          POST /api/index                         │
│                          DELETE /api/collections/{name}          │
└─────────────────────────────────────────────────────────────────┘
            │
│ Index call│ GET collections
└───────────┼──────▲─────────────────────────────────────────────────┐
            │      │                                                 │
            │      └──────────────────────────────────────────────┐  │
            │                                                     │  │
┌───────────▼──────────────────────────────────────────────────┐ │  │
│          PIPELINE D'EXTRACTION (Python)                      │ │  │
│                                                               │ │  │
│  ┌──────────────────────────────────────────────────────┐   │ │  │
│  │  Manual Upload (Laravel → Python)                    │   │ │  │
│  │                                                       │   │ │  │
│  │  1. Upload PDF → /extract/app/manuels/              │   │ │  │
│  │  2. Run extractor (docling/ollama)                   │   │ │  │
│  │  3. Extract to JSON (_2level.json)                   │   │ │  │
│  │  4. Clean data (fix bullets, bold, etc)              │   │ │  │
│  │  5. Save _2levels_cleaned.json                       │   │ │  │
│  │  6. Trigger Backend: POST /api/index                 │   │ │  │
│  └┬─────────────────────────────────────────────────────┘   │ │  │
│  │                                                         │ │  │
│  │                   Extractor Output:                  │ │  │
│  │ /extract/app/json/ Directory                        │ │  │
│  │ ├─ app_2level.json (raw)                            │ │  │
│  │ ├─ app_2levels_cleaned.json (cleaned) ──────────────┼─┼──┘  │
│  │ ├─ manual_2level.json (raw)                         │ │     │
│  │ ├─ manual_2levels_cleaned.json (cleaned) ──────────┼─┘     │
│  │ └─ ... (other documents)                            │        │
│  │                                                     │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

(Database)
┌─────────────────────────────────────┐
│  PostgreSQL 15 (Docker)              │
│  - Users (LDAP synced)               │
│  - Conversations & Messages          │
│  - Manuals metadata                  │
│  - Tickets (GLPI integration)        │
└─────────────────────────────────────┘

(Authentication)
┌─────────────────────────────────────┐
│  OpenLDAP (Docker)                   │
│  - User authentication               │
│  - Organization structure            │
│  - Role mapping                      │
└─────────────────────────────────────┘
```

---

## 🚀 Composants Principaux

### Frontend: Laravel

**Localisation**: `/dev/frontend/`

#### Description
Interface web complète construite avec **Laravel 11 + PHP** pour :
- Chat interactif avec le chatbot RAG
- Gestion des conversations et historique
- Upload de manuels (Admin)
- Authentification LDAP
- Intégration WebSocket pour les réponses en temps réel

#### Fichiers/Dossiers clés
```
/dev/frontend/
├── routes/
│   └── web.php                 # Routage principal
├── app/
│   ├── Http/
│   │   ├── Controllers/
│   │   │   ├── Chat/ChatController.php      # Chat logic
│   │   │   ├── Admin/AdminController.php    # Admin actions
│   │   │   ├── Auth/LdapAuthController.php  # LDAP login
│   │   │   └── TicketController.php         # GLPI tickets
│   │   └── Middleware/
│   │       ├── EnsureAuthenticated.php      # Auth guard
│   │       └── EnsureIsAdmin.php            # Admin guard
│   ├── Models/
│   │   ├── User.php            # Eloquent User model (LDAP synced)
│   │   ├── Conversation.php    # Chat sessions
│   │   ├── Message.php         # Chat messages
│   │   ├── Manual.php          # Document metadata
│   │   └── Ticket.php          # GLPI tickets
│   └── Services/
│       └── ChatbotService.php   # WebSocket & API communication
├── resources/
│   ├── js/
│   │   └── chat.js             # Chat UI interactions
│   └── views/
│       ├── chat.blade.php       # Chat interface
│       └── admin/               # Admin templates
├── config/
│   ├── services.php            # External service configuration
│   └── auth.php                # Authentication config
└── database/
    └── migrations/             # Database schemas
```

#### Composants Laravel détaillés

**1. ChatController (`app/Http/Controllers/Chat/ChatController.php`)**
- **Vue d'ensemble** : Gère toutes les opérations de chat
- **Responsabilités** :
  - `/chat/` → Affiche l'interface de chat
  - `getConversations()` → Récupère l'historique des conversations
  - `newConversation()` → Crée une nouvelle conversation
  - `initMessage()` → Prépare un message pour envoi
  - `finalizeMessage()` → Sauvegarde le message en base de données
  - `deleteConversation()` → Supprime une conversation complète
- **Communication** : Utilise `ChatbotService` pour parler à FastAPI
- **Données stockées en DB** : `conversations`, `messages` tables PostgreSQL
- **Flux** :
  ```
  User input (UI) → ChatController.initMessage()
     ↓
  ChatbotService.sendMessage() (WebSocket)
     ↓
  FastAPI /ws/chat (streaming)
     ↓
  ChatController.finalizeMessage() (save to DB)
  ```

**2. AdminController (`app/Http/Controllers/Admin/AdminController.php`)**
- **Vue d'ensemble** : Interface d'administration pour gérer les manuels
- **Responsabilités** :
  - `index()` → Tableau de bord admin
  - `storeManual()` → Upload du PDF et déclenchement extraction
  - `showManual()` → Détails d'un manuel
  - `updateManual()` → Modification des métadonnées
  - `destroyManual()` → Suppression et nettoyage
- **Workflow d'upload** :
  ```
  1. Admin upload PDF
  2. Laravel save temp file
  3. Call /extract/app/extractor_level_2.py
  4. Extract → JSON (_2level.json)
  5. Call clean_data.py
  6. Save → _2levels_cleaned.json
  7. POST /api/index to Backend
  8. Backend indexes in Qdrant
  9. Save metadata in DB
  ```

**3. LdapAuthController (`app/Http/Controllers/Auth/LdapAuthController.php`)**
- **Authentification LDAP** :
  - Vérifie les credentials contre OpenLDAP
  - Crée/met à jour les utilisateurs dans PostgreSQL
  - Assigne les rôles (User/Admin)
  - Crée les sessions
- **Configuration** : voir `config/auth.php`

**4. TicketController (`app/Http/Controllers/TicketController.php`)**
- **Gestion de tickets GLPI** :
  - Crée des tickets depuis le chat (escalade)
  - Utilise GLPI API via `config/services.php`
  - Lie le contexte du chat au ticket

**5. Models Eloquent**
- **User.php** : Représente un utilisateur LDAP synced
- **Conversation.php** : Session de chat (belongsTo User)
- **Message.php** : Messages individuels (belongsTo Conversation)
- **Manual.php** : Métadonnées des manuels uploadés
- **Ticket.php** : Tickets GLPI tracés

**6. ChatbotService (`app/Services/ChatbotService.php`)**
- **Point de contact principal avec le Backend**
- **Méthodes** :
  - `sendMessage($query, $collection)` → WebSocket stream
  - `getCollections()` → List des collections disponibles
  - `uploadManual($filePath)` → Trigger extraction & indexing
- **Configuration depuis** : `config/services.php`
  ```php
  'chatbot' => [
      'url'     => 'http://127.0.0.1:8000',
      'ws_url'  => 'ws://127.0.0.1:8000/ws/chat',
      'timeout' => 30,
  ]
  ```

---

### Backend RAG: FastAPI

**Localisation**: `/dev/backend/main.py` + `/prod/`

#### Description
Serveur FastAPI qui implémente la pipeline RAG complète :
- Réception des requêtes chat
- Embeddings et recherche sémantique
- Génération des réponses avec LLM
- Indexation automatique de documents
- WebSocket pour streaming temps réel

#### Fichiers clés

```
/dev/backend/
└── main.py                     # FastAPI server

/prod/
├── config.yaml                 # Configuration centralisée RAG
├── app.py                      # Interface Streamlit (test)
├── assistant.py                # Gestionnaire de sessions & pipeline
├── chunker.py                  # Découpe documents en chunks
├── embedder.py                 # Encodage texte (BGE-M3)
├── retriever.py                # Recherche + reranking
├── generator.py                # LLM (Qwen)
├── rag.py                      # Orchestration RAG
├── vector_store.py             # Interface Qdrant
├── rewriter.py                 # Rewriting des questions
├── pipeline.py                 # Utilitaires
├── prompt_1.txt                # Template système
├── requirements.txt            # Dépendances Python
└── logs/                       # Logs applicatifs
```

#### Flux détaillé du Backend RAG

**1. FastAPI Server (`/dev/backend/main.py`)**
- **Rôle** : Point d'entrée HTTP/WebSocket
- **Endpoints** :

| Endpoint | Méthode | Params | Description |
|----------|---------|--------|-------------|
| `/ws/chat` | WebSocket | user_id, message, collection, max_turns | Stream responses in real-time |
| `/api/chat` | POST | message, user_id, collection, max_turns | Blocking request (full response at once) |
| `/health` | GET | - | Health check, list collections |
| `/api/collections` | GET | - | Available Qdrant collections |
| `/api/index` | POST | json_path, collection | Index cleaned JSON into Qdrant |
| `/api/collections/{name}` | DELETE | - | Drop collection + folder |

**2. RAGManager (classe dans `main.py`)**
- **Initialisation** :
  ```python
  1. Load config.yaml
  2. Create Embedder (BGE-M3)
  3. Initialize Qdrant VectorDB
  4. Build Assistant
  5. Load all *_2levels_cleaned.json from /extract/app/json/
  6. Auto-index new collections
  ```
- **Méthodes clés** :
  - `initialize()` → Démarre la pipeline RAG
  - `resolve_collection()` → trouve la collection demand ée (fuzzy matching)
  - `_load_json_collections()` → Index auto collections
  - `_index_collection()` → Chunk + encode + upsert

**3. Configuration RAG (`/prod/config.yaml`)**

```yaml
# Vector Database Configuration
vector_db:
  path: "qdrant_data/"         # Local Qdrant data
  host: null                    # For remote server
  port: 6333

# Chunking Strategy
chunker:
  max_tokens: 1024             # Max tokens per chunk
  overlap: 10                  # Overlapping tokens
  tokenizer_model: "BAAI/bge-m3"

# Embeddings (Dense)
embedder:
  model_name: "BAAI/bge-m3"    # HuggingFace model
  device: "cpu"                # CPU or CUDA
  batch_size: 32

# Search Parameters
retriever:
  search_top_k: 10             # Initial search
  sections_top_k: 3            # Final results

# Reranking (Optional)
reranker:
  enabled: false               # BGE-reranker-v2-m3
  top_k_rerank: 10

# LLM Generation
generator:
  device: "cpu"                # CPU (GGUF) or CUDA (HF)
  prompt_file: "prompt_1.txt"
  # CPU Mode
  gguf_path: "../models/Qwen3.5-4B-Q4_K_S.gguf"
  n_ctx: 4000                  # Context window
  n_threads: 4
  n_batch: 1024
  # GPU Mode
  hf_model_name: "Qwen/Qwen2-7B-Instruct"
  # Generation
  max_tokens: 1024
  temperature: 0.1
  top_p: 0.8
  top_k: 20

# RAG Logic
rag:
  routing_threshold: 3.0       # FAQ vs Document routing

# Session Management
assistant:
  max_turns: 2                 # Conversation history
  verbose: true
  log_dir: "logs"
```

**4. Assistant (`/prod/assistant.py`)**
- **Gère les sessions de conversation** :
  ```python
  class Session:
      - session_id: str
      - max_turns: int
      - history: List[Dict]  # Previous Q&A pairs
      - get_history_text()   # Format for context
      - add_turn()           # Add Q&A pair
```
- **Orchestration RAG** :
  ```python
  def chat(session_id, query, app_id):
      1. Get session history (context)
      2. Call RAG pipeline:
         - Embed query (Embedder)
         - Search Qdrant (Retriever)
         - Rerank if enabled (Reranker)
         - Generate answer (Generator)
      3. Stream answer token by token
      4. Save sources in session
      5. Add Q&A to history
      6. Yield final result with sources
  ```

**5. Chunker (`/prod/chunker.py`)**
- **Découpe les sections en chunks indexables** :
  ```python
  Input:  {"title": "...", "content": "...", "breadcrumb": [...]}
  ↓
  Process:
  - Split content into paragraphs
  - Join by max_tokens (1024)
  - Add overlap (10 tokens)
  - Generate unique IDs
  
  Output: [
    {
      "id": "chunk_001",
      "embed_text": "...",  # For embeddings
      "source_text": "...",  # Original text
      "breadcrumb": [...],   # Hierarchy
      "section_title": "..."
    },
    ...
  ]
  ```

**6. Embedder (`/prod/embedder.py`)**
- **Conversion texte → vecteur dense** :
  - Modèle : **BGE-M3** (1024 dimensions)
  - Multilingual, optimisé pour recherche sémantique
  - Batch processing (32 texts at a time)
  - Normalisation : cosine distance

**7. Retriever (`/prod/retriever.py`)**
- **Recherche sémantique + Reranking** :
  ```python
  Input: query (string)
  
  Step 1: Embed query with BGE-M3
  Step 2: Search Qdrant (cosine similarity)
    └─ Retrieve top-10 chunks
  Step 3: Optionally Rerank (BGE-reranker)
    └─ Score (query, document) pairs
    └─ Keep top-10 after rerank
  Step 4: Aggregate chunks → sections
    └─ Group by section_title
    └─ Return top-3 sections
  
  Output: [
    {"text": "...", "breadcrumb": [...], "score": X},
    ...
  ]
  ```

**8. Reranker (`/prod/retriever.py`)**
- **BGE Cross-Encoder Reranker** (optionnel) :
  - Modèle : `BAAI/bge-reranker-v2-m3`
  - Score la pertinence de chaque chunk
  - Réordonne les résultats
  - GPU-accelerated si disponible

**9. Generator (`/prod/generator.py`)**
- **Génération de réponses avec LLM** :

| Mode | Modèle | Device | Vitesse | Qualité |
|------|--------|--------|---------|---------|
| CPU | Qwen 3.5 4B (GGUF) | CPU | Rapide | Moyenne |
| GPU | Qwen 2 7B (HF) | CUDA | Très rapide | Bonne |

- **Prompt Format** :
  ```
  System: You are a helpful assistant...
  
  Context: [Retrieved sections]
  
  Question: [User question]
  
  Answer: [Generated response]
  ```
- **Paramètres** :
  - Temperature: 0.1 (déterministe)
  - Top-p: 0.8 (nucleus sampling)
  - Max tokens: 1024
  - Streaming token-by-token

**10. Vector Store (`/prod/vector_store.py`)**
- **Interface Qdrant** :
  ```python
  - create_collection(name, dim=1024)
  - upsert(name, records)  # Add/update chunks
  - search(name, query_vec, top_k=10)
  - delete_collection(name)
  - list_collections()
  ```
- **Storage** : `/prod/qdrant_data/`
  - Chaque collection = dossier séparé
  - Persistant entre redémarrages

---

### Pipeline d'Extraction

**Localisation**: `/extract/app/`

#### Description
Système automatisé pour transformer PDFs en documents structurés indexables :

#### Fichiers clés
```
/extract/app/
├── extractor_level_2.py       # Extraction PDF → JSON
├── clean_data.py              # Nettoyage du JSON
├── manual_pipeline.py          # Orchestration complète
├── /manuels/                  # PDF uploads
├── /json/                     # Extracted JSON files
│   ├── app_2level.json           (raw extraction)
│   ├── app_2levels_cleaned.json  (cleaned - indexed)
│   ├── manual_2level.json
│   └── manual_2levels_cleaned.json
└── /logs/                     # Process logs
```

#### Flux d'Extraction

**Étape 1 : Upload et Extraction (`extractor_level_2.py`)**
```
INPUT: app.pdf
   ↓
Tool: Docling (OCR + extraction)
or: Ollama (if needed)
   ↓
OUTPUT: app_2level.json
   {
     "sections": [
       {
         "title": "Chapter 1",
         "content": "Full text content...",
         "breadcrumb": ["Manual", "Part A", "Chapter 1"],
         "level": 2
       },
       ...
     ]
   }
```

**Étape 2 : Nettoyage (`clean_data.py`)**

Retire les artéfacts de l'extraction :

```python
# Bug 1: Bullets cassés
"• \n**Titre**"  →  "• Titre"

# Bug 2: Gras coupé en milieu de phrase
"**fin de ligne** suite"  →  "fin de ligne suite"

# Bug 3: Espaces superflus
"  multiple   spaces  "  →  "multiple spaces"

# Bug 4: Mauvaise pagination
"page\nbreak"  →  "page break" (adjust context)
```

```
INPUT: app_2level.json (raw)
   ↓
Apply cleaning rules:
1. Fix broken bullets (•, o)
2. Fix split bold formatting
3. Remove extra whitespace
4. Fix double spaces in content
5. Normalize line breaks
6. Clean special characters
   ↓
OUTPUT: app_2levels_cleaned.json
```

**Étape 3 : Indexation (`main.py` Backend)**
```
INPUT: app_2levels_cleaned.json
   ↓
1. Parse sections
2. Chunk each section (1024 tokens max)
3. Embed chunks with BGE-M3
4. Create Qdrant collection: "app_2levels_cleaned"
5. Upsert chunks with metadata
   ↓
OUTPUT: Collection indexed in Qdrant
   └─ Points searchable by semantic similarity
```

#### Nommage des Collections

**Convention stricte** :
```
PDF Upload:      app.pdf
   ↓
Raw Extraction:  app_2level.json
   ↓
After Cleaning:  app_2levels_cleaned.json
   ↓
Collection:      app_2levels_cleaned
   ↓
Query:           collection="app_2levels_cleaned"
```

Les tirets `-` et espaces ` ` sont convertis en `_` dans les noms.

---

### Infrastructure & DevOps

**Localisation**: `/dev/docker/`

#### Configuration Docker Compose

**Fichier** : `/dev/docker/docker-compose.yml`

```yaml
version: "3.8"

services:

  # OpenLDAP - User Directory
  openldap:
    image: osixia/openldap:1.5.0
    container_name: openldap
    environment:
      LDAP_ORGANISATION: "Sonatrach"
      LDAP_DOMAIN: "sonatrach.test"
      LDAP_ADMIN_PASSWORD: "pfe@2026"
    ports:
      - "1389:389"      # LDAP
      - "1636:636"      # LDAPS

  # PostgreSQL - Data Storage
  postgres:
    image: postgres:15
    container_name: postgres
    environment:
      POSTGRES_DB: pfe_2026
      POSTGRES_USER: pfe_user
      POSTGRES_PASSWORD: secret
    ports:
      - "5432:5432"
```

#### Services Détaillés

**1. OpenLDAP (Port 1389/1636)**
- **Rôle** : Annuaire centralisé pour authentification
- **Configuration** :
  - Domain: `sonatrach.test`
  - Admin Password: `pfe@2026`
  - DN: `dc=sonatrach,dc=test`
- **Utilisations** :
  - Login utilisateurs (Laravel LDAP Auth)
  - Synchronisation des rôles
  - Gestion des groupes
- **Connexion depuis Laravel** :
  ```php
  LDAP Server: ldap://openldap:389
  Base DN: dc=sonatrach,dc=test
  Admin DN: cn=admin,dc=sonatrach,dc=test
  Password: pfe@2026
  ```

**2. PostgreSQL (Port 5432)**
- **Rôle** : Base de données persistante
- **Base de données** : `pfe_2026`
- **Utilisateur** : `pfe_user` / `secret`
- **Tables** :
  - `users` - Utilisateurs synced depuis LDAP
  - `conversations` - Sessions de chat
  - `messages` - Messages individuels
  - `manuals` - Métadonnées des documents
  - `tickets` - Tickets GLPI tracés
- **Backup** : À configurer avec cron/pg_dump
- **Port d'écoute** :
  - Interne (container): 5432
  - Externe (host): 5432

#### Déploiement Local

```bash
# 1. Start all services
cd /dev/docker
docker-compose up -d

# 2. Verify services
docker-compose ps

# 3. Test LDAP
ldapsearch -x -h localhost:1389 -b "dc=sonatrach,dc=test" "(cn=admin)"

# 4. Test PostgreSQL
docker exec -it postgres psql -U pfe_user -d pfe_2026 -c "SELECT version();"

# 5. Stop services
docker-compose down
```

---

## 👥 Rôles Utilisateurs

### 1. Utilisateur Standard 👤

**Permissions** :
- ✅ Accès au chatbot RAG
- ✅ Consulter manuels via chat
- ✅ Créer/consulter conversations
- ✅ Créer tickets GLPI (support)
- ❌ Upload de manuels
- ❌ Admin panel

**Actions** :
```
1. Login with LDAP credentials
2. Chat with RAG chatbot
3. Select document collection (if multiple)
4. Ask questions about manuals
5. View sources and references
6. Escalate to support ticket
7. View conversation history
```

**Flow Technique** :
```
User Browser
    │
    ├─ POST /login (LDAP verify)
    ├─ Store session cookie
    ├─ GET /chat (view chat UI)
    │
    └─ WebSocket /ws/chat
        ├─ User message
        ├─ Backend processes:
        │  1. Embed query
        │  2. Search collection
        │  3. Generate answer
        │  4. Stream response
        └─ Save to Message table
```

**Base de données** :
- Lectures : `conversations`, `messages`, `manuals`
- Écritures : `messages`, `conversations` (own only)

### 2. Administrateur 👨‍💼

**Permissions** : Toutes les permissions utilisateur +
- ✅ Upload manuels (PDF)
- ✅ Gérer collections Qdrant
- ✅ Voir tableau de bord admin
- ✅ Supprimer documents
- ✅ Gérer utilisateurs LDAP
- ✅ Voir logs extraction

**Actions** :
```
1. Admin Login
2. Access /admin dashboard
3. Upload PDF manual
4. Monitor extraction process
5. View indexed collections
6. Delete collection (trigger cleanup)
7. View all conversations (admin view)
8. Manage users (LDAP)
```

**Flow d'Upload Technique** :
```
Admin
  │
  └─ POST /admin/manuals (file upload)
     │
     ├─ Laravel saves PDF to /extract/app/manuels/
     │
     ├─ Call Python extractor:
     │  /extract/app/extractor_level_2.py
     │
     ├─ Generate {name}_2level.json
     │
     ├─ Call cleaner:
     │  /extract/app/clean_data.py
     │
     ├─ Generate {name}_2levels_cleaned.json
     │
     └─ POST http://backend:8000/api/index
        ├─ Backend chunks & embeds
        ├─ Upsert to Qdrant
        └─ Response: collection name
```

**Contrôle d'accès** :
- Middleware `EnsureIsAdmin::class` sur `/admin/*`
- Vérification du rôle dans `users` table

---

## 🔄 Flux de Données

### Flux 1: Chat RAG (WebSocket Streaming)

```
┌─────────────┐
│   USER      │
└──────┬──────┘
       │ Types message in chat UI
       │
┌──────▼──────────────────────────────────┐
│  Browser JavaScript (WebSocket)         │
│  new WebSocket(ws://localhost:8000      │
│         /ws/chat)                       │
└──────┬──────────────────────────────────┘
       │ Sends JSON:
       │ {
       │   "user_id": "user@sonatrach.test",
       │   "message": "How to...",
       │   "collection": "app_2levels...",
       │   "max_turns": 2
       │ }
       │
┌──────▼──────────────────────────────────┐
│  FastAPI WebSocket Handler              │
│  /ws/chat (main.py)                     │
└──────┬──────────────────────────────────┘
       │ 1. Parse credentials
       │ 2. Validate collection
       │ 3. Create async queue
       │
┌──────▼──────────────────────────────────┐
│  Thread: run_assistant()                │
│  ┌────────────────────────────────────┐ │
│  │ Assistant.chat(session, query,     │ │
│  │              collection)           │ │
│  └────────────────────────────────────┘ │
└──────┬──────────────────────────────────┘
       │ Yields streaming items:
       │
       ├─► Embed query (Embedder)
       │   └─ Query vector (1024 dims)
       │
       ├─► Search Qdrant (Retriever)
       │   └─ Top-10 chunks by similarity
       │
       ├─► Optional: Rerank (Reranker)
       │   └─ Score & reorder chunks
       │
       ├─► Generate answer (Generator)
       │   ├─ Format prompt with context
       │   ├─ Stream each token
       │   └─ Collect sources
       │
       └─► Done signal
           └─ Include sources list
       │
┌──────▼──────────────────────────────────┐
│  Queue → WebSocket send                 │
│  Message types:                         │
│  - {"type": "typing", "status": true}   │
│  - {"type": "token", "text": "..."}     │
│  - {"type": "done", "sources": [...]}   │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│  Browser receives streams               │
│  Updates UI in real-time                │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│  ChatController.finalizeMessage()       │
│  Save to Message table                  │
└─────────────────────────────────────────┘
```

### Flux 2: Manual Upload & Indexing

```
┌─────────────┐
│ ADMIN USER  │
└──────┬──────┘
       │ Select PDF file, click "Upload"
       │
┌──────▼───────────────────────────────────┐
│  Browser                                  │
│  POST /admin/manuals (form-data)         │
└──────┬───────────────────────────────────┘
       │
┌──────▼───────────────────────────────────┐
│  Laravel AdminController                  │
│  storeManual($request)                   │
└──────┬───────────────────────────────────┘
       │ 1. Validate file (PDF)
       │ 2. Store to /extract/app/manuels/
       │ 3. Create DB record in manuals table
       │
┌──────▼───────────────────────────────────┐
│  Shell exec (PHP):                       │
│  python /extract/app/                    │
│  extractor_level_2.py \                  │
│  --pdf /path/to/file.pdf                │
└──────┬───────────────────────────────────┘
       │
       │ Process in Python:
       │ 1. Docling/OCR extraction
       │ 2. Parse structure (sections, paragraphs)
       │ 3. Save to {id}_2level.json
       │
┌──────▼───────────────────────────────────┐
│  Python: clean_data.py                   │
│  Load {id}_2level.json                   │
│  Apply cleaning rules (see Extraction)   │
│  Save {id}_2levels_cleaned.json          │
└──────┬───────────────────────────────────┘
       │
┌──────▼───────────────────────────────────┐
│  Laravel calls Backend:                  │
│  POST http://backend:8000/api/index      │
│  Body:                                   │
│  {                                       │
│    "json_path": "/path/.../file...      │
│                _2levels_cleaned.json",  │
│    "collection": "file_2levels_cleaned" │
│  }                                       │
└──────┬───────────────────────────────────┘
       │
┌──────▼───────────────────────────────────┐
│  FastAPI POST /api/index (main.py)       │
│  ┌────────────────────────────────────┐ │
│  │ 1. Validate file existence          │ │
│  │ 2. Check naming convention          │ │
│  │ 3. Load JSON sections               │ │
│  └────────────────────────────────────┘ │
└──────┬───────────────────────────────────┘
       │
┌──────▼───────────────────────────────────┐
│  Async executor: _index_collection()     │
│  ┌────────────────────────────────────┐ │
│  │ 1. Chunker.process_sections()       │ │
│  │    └─ Split by max_tokens (1024)   │ │
│  │ 2. Embedder.encode(chunks)          │ │
│  │    └─ BGE-M3: 1024-dim vectors     │ │
│  │ 3. VectorDB.create_collection()     │ │
│  │    └─ Create in Qdrant              │ │
│  │ 4. VectorDB.upsert(chunks)          │ │
│  │    └─ Add to Qdrant with metadata   │ │
│  └────────────────────────────────────┘ │
└──────┬───────────────────────────────────┘
       │ Response:
       │ {
       │   "success": true,
       │   "collection": "file_2levels...",
       │   "status": "indexed"
       │ }
       │
┌──────▼───────────────────────────────────┐
│  Laravel response to Admin:               │
│  "Manual indexed successfully"            │
└?──────────────────────────────────────────┘
```

### Flux 3: LDAP Authentication

```
┌─────────────┐
│   USER      │
└──────┬──────┘
       │ Enters credentials on login page
       │
┌──────▼────────────────────────────────────┐
│  Browser POST /login                      │
│  {                                        │
│    "username": "john.doe",               │
│    "password": "secret123"                │
│  }                                        │
└──────┬────────────────────────────────────┘
       │
┌──────▼────────────────────────────────────┐
│  Laravel LdapAuthController::login()      │
└──────┬────────────────────────────────────┘
       │ 1. Validate input
       │ 2. Connect to LDAP server:
       │    (openldap:389 in Docker)
       │
┌──────▼────────────────────────────────────┐
│  LDAP Query:                              │
│  Server: ldap://openldap:389              │
│  Base DN: dc=sonatrach,dc=test           │
│  Bind: cn=john.doe,ou=people,...         │
│  Password: [user input]                  │
└──────┬────────────────────────────────────┘
       │
       ├─ If authentication succeeds:
       │  ├─ Fetch user attributes (name, email, group)
       │  │
       │  └─ Check if user exists in PostgreSQL
       │     ├─ No → Create new User record
       │     └─ Yes → Update existing record
       │
       └─ If fails:
          └─ Return auth error
       │
┌──────▼────────────────────────────────────┐
│  Laravel: Auth::login($user)              │
│  Create session cookie                    │
│  Store in PHP $_SESSION                   │
└──────┬────────────────────────────────────┘
       │
┌──────▼────────────────────────────────────┐
│  Redirect to /chat (for users)            │
│  or /admin (if user is admin)            │
└────────────────────────────────────────────┘
```

---

## ⚙️ Configuration & Déploiement

### Configuration des Services

**Fichier** : `/dev/frontend/config/services.php`

```php
return [
    // LDAP Configuration
    'ldap' => [
        'host' => env('LDAP_HOST', 'ldap://openldap:389'),
        'base_dn' => env('LDAP_BASE_DN', 'dc=sonatrach,dc=test'),
        'admin_dn' => env('LDAP_ADMIN_DN', 'cn=admin,dc=sonatrach,dc=test'),
        'password' => env('LDAP_PASSWORD', 'pfe@2026'),
    ],

    // Chatbot RAG API
    'chatbot' => [
        'url' => env('PYTHON_API_URL', 'http://127.0.0.1:8000'),
        'ws_url' => env('PYTHON_WS_URL', 'ws://127.0.0.1:8000/ws/chat'),
        'timeout' => env('PYTHON_API_TIMEOUT', 30),
    ],

    // Extract Pipeline
    'extract' => [
        'python_bin' => env('EXTRACT_PYTHON_BIN',
            '/var/www/PFE_M2/PFE-M2/extract/venv_docling/bin/python3'),
        'extract_dir' => env('EXTRACT_DIR', base_path('../../extract/app')),
        'manuals_dir' => env('EXTRACT_MANUALS_DIR', base_path('../../extract/app/manuels')),
        'json_dir' => env('EXTRACT_JSON_DIR', base_path('../../extract/app/json')),
        'max_upload_kb' => env('EXTRACT_MAX_UPLOAD_KB', 512000), // 500 MB
        'timeout' => env('EXTRACT_TIMEOUT', 1800), // 30 mins
    ],

    // Qdrant Vector Store
    'qdrant' => [
        'url' => env('QDRANT_URL', 'http://127.0.0.1:6333'),
    ],

    // GLPI Ticket System
    'glpi' => [
        'url' => env('GLPI_URL', 'https://glpi.sonatrach.dz'),
        'api_token' => env('GLPI_API_TOKEN', '...'),
        'app_token' => env('GLPI_APP_TOKEN', '...'),
    ],
];
```

### Variables d'Environnement

**Fichier** : `.env` (à la racine du projet)

```bash
# Laravel
APP_NAME="PFE RAG Chatbot"
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:...
LOG_CHANNEL=stack

# Database
DB_CONNECTION=pgsql
DB_HOST=postgres
DB_PORT=5432
DB_DATABASE=pfe_2026
DB_USERNAME=pfe_user
DB_PASSWORD=secret

# LDAP
LDAP_HOST=ldap://openldap:389
LDAP_BASE_DN=dc=sonatrach,dc=test
LDAP_ADMIN_DN=cn=admin,dc=sonatrach,dc=test
LDAP_PASSWORD=pfe@2026

# Python Backend
PYTHON_API_URL=http://backend:8000
PYTHON_WS_URL=ws://backend:8000/ws/chat
PYTHON_API_TIMEOUT=30

# Extract Pipeline
EXTRACT_PYTHON_BIN=/var/www/PFE_M2/PFE-M2/extract/venv_docling/bin/python3
EXTRACT_DIR=/var/www/PFE_M2/PFE-M2/extract/app
EXTRACT_MAX_UPLOAD_KB=512000
EXTRACT_TIMEOUT=1800

# Vector Store
QDRANT_URL=http://qdrant:6333

# GLPI
GLPI_URL=https://glpi.sonatrach.dz
GLPI_API_TOKEN=...
GLPI_APP_TOKEN=...
```

---

## 📖 Guide d'Utilisation

### Pour les Utilisateurs Finaux

#### 1. Se Connecter

```
1. Aller sur https://votre-domaine.com/login
2. Entrer votre login LDAP (ex: john.doe)
3. Entrer votre mot de passe
4. Cliquer "Se Connecter"
```

#### 2. Poser une Question

```
1. Interface Chat s'affiche
2. Sélectionner collection (si plusieurs disponibles)
3. Taper votre question
4. Cliquer Envoyer
5. Réponse arrive en streaming (temps réel)
6. Sources affichées en bas
```

#### 3. Consulter l'Historique

```
1. Cliquer "Conversations" dans le menu
2. Sélectionner une conversation passée
3. Voir tous les messages
4. Continuer la conversation ou en ouvrir une nouvelle
```

### Pour les Administrateurs

#### 1. Se Connecter et Accéder Admin

```
1. Login normal (LDAP)
2. Interface redirige vers /chat (utilisateur) ou /admin (admin)
3. Menu "Administration" visible en haut
```

#### 2. Upload d'un Manuel

```
1. Aller à /admin/manuals
2. Cliquer "Nouveau Manuel"
3. Sélectionner le PDF
4. Remplir les métadonnées:
   - Titre
   - Description
   - Langue (option)
5. Cliquer "Upload"
6. Patienter extraction + indexing (1-30 mins selon taille)
7. Confirmation: "Manuel indexé avec succès"
```

#### 3. Supprimer une Collection

```
1. /admin/collections
2. Voir liste des collections
3. Cliquer "Supprimer" à côté d'une collection
4. Les fichiers JSON et Qdrant sont supprimés
```

#### 4. Voir les Logs

```
1. /admin/logs
2. Voir logs d'extraction et d'indexation
3. Rechercher par manuel, date, statut
```

---

## 🔧 Dépannage

### Problème 1: Le backend FastAPI ne démarre pas

```bash
# 1. Vérifier que les dépendances sont installées
cd /prod
pip install -r requirements.txt

# 2. Vérifier le fichier config.yaml
cat config.yaml | grep -A 5 "generator"

# 3. Vérifier les chemins des modèles GGUF
ls -la ../models/

# 4. Tester le démarrage manuel
python main.py
# ou via uvicorn:
cd /dev/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Problème 2: WebSocket ne se connecte pas

```bash
# 1. Vérifier que le backend est accessible
curl http://localhost:8000/health

# 2. Vérifier les CORS dans main.py
# Doit avoir: allow_origins=["*"]

# 3. Vérifier la URL WebSocket en config
# ws://localhost:8000/ws/chat ou ws://backend:8000/ws/chat?

# 4. Check du navigateur:
# F12 → Console → Network → WS
# Voir si connexion établie ou reject
```

### Problème 3: LDAP login échoue

```bash
# 1. Vérifier le container OpenLDAP
docker ps | grep openldap

# 2. Tester la connexion LDAP
ldapsearch -x -h localhost:1389 \
  -b "dc=sonatrach,dc=test" \
  -D "cn=admin,dc=sonatrach,dc=test" \
  -w "pfe@2026" \
  "(cn=*)"

# 3. Vérifier la config dans services.php
grep -A 5 "LDAP" /dev/frontend/config/services.php

# 4. Logs Laravel:
tail -f /dev/frontend/storage/logs/laravel.log
```

### Problème 4: Collection introuvable

```bash
# 1. Lister les collections disponibles
curl http://localhost:8000/api/collections

# 2. Vérifier les fichiers JSON
ls -la /extract/app/json/ | grep "_2levels_cleaned"

# 3. Vérifier le nom de la collection
# Règle: {nom_fichier}_2levels_cleaned sans tirets/espaces

# 4. Éventuellement réindexer:
python /dev/backend/main.py
# Cela va auto-charger toutes les collections
```

### Problème 5: Extraction de PDF freeze/timeout

```bash
# 1. Vérifier la taille du PDF
du -h /extract/app/manuels/

# 2. Vérifier les ressources:
df -h  # Disque
free -h  # RAM

# 3. Timeout config:
# Edit .env: EXTRACT_TIMEOUT=1800 (seconds)

# 4. Forcer cleanup:
# Supprimer les fichiers de temp extraction
rm -rf /extract/app/json/tmp_*

# 5. Vérifier les logs:
tail -f /extract/app/logs/
```

---

## 📊 Statistiques et Monitoring

### Fichiers de Logs

```
/prod/logs/
├── assistant.log          # RAG assistant operations
└── [daily logs]           # One file per day

/extract/app/logs/
├── extraction.log         # PDF extraction
├── cleaning.log          # Data cleaning
└── [process logs]        # Process outputs

/dev/frontend/storage/logs/
├── laravel.log           # Laravel errors/info
└── [by date]
```

### Métriques à Suivre

| Métrique | Info | Where |
|----------|------|-------|
| Queries/jour | Volume chatbot | Laravel DB |
| Latence moyenne | Temps premier token | Logs RAG |
| Collections | Documents indexés | /api/collections |
| Users actifs | Logins réussis | Laravel audit |
| Erreurs extract | PDFs échoués | /extract/logs |
| Qdrant size | Storage utilisé | Qdrant API |

---

## 🔐 Sécurité

### Points Importants

1. **LDAP** : Credentials stockés en .env, jamais en code
2. **GLPI API** : Tokens en .env seulement
3. **Database** : PostgreSQL protégé par mot de passe, pas d'accès externe
4. **WebSocket** : CORS ouvert (* à adapter en prod)
5. **Files** : Uploads sauvegardés le EXTRACT_DIR avec permissions restreintes

### Recommandations Production

```bash
# 1. CORS restrictive
allow_origins=["https://votre-domaine.com"]

# 2. HTTPS obligatoire
Utiliser reverse proxy (Nginx) avec certificat SSL

# 3. Rate limiting
Implémenter sur les endpoints API

# 4. Authentification Stronger
2FA ou OAuth si possible

# 5. Logs sécurisés
Rotation automatique, backup distant

# 6. Backups DB
Automatiser avec cron + S3

# 7. Encryption DB
Activer encryption au repos
```

---

## 📞 Support & Contacte

Pour des questions sur :
- **RAG Pipeline** : Voir `/prod/README.md` (si existe)
- **Laravel Frontend** : Check `/dev/frontend/`
- **Extraction** : Check `/extract/app/`
- **Docker** : Check `/dev/docker/docker-compose.yml`

---

## 📝 Licence & Crédits

**Projet académique PFE-M2**
- Université : [À remplir]
- Promoteur industriel : Sonatrach
- Technologies : Laravel, FastAPI, Qdrant, LangChain, BGE, Qwen

---

## 📚 Ressources & Documentation Externe

### Composants Utilisés

- **Laravel** : https://laravel.com/docs/11.x
- **FastAPI** : https://fastapi.tiangolo.com/
- **Qdrant** : https://qdrant.tech/documentation/
- **BGE-M3** : https://huggingface.co/BAAI/bge-m3
- **Qwen** : https://github.com/QwenLM/Qwen
- **OpenLDAP** : https://www.openldap.org/

### Articles & Papers

- RAG : https://arxiv.org/abs/2005.11401
- Dense Passage Retrieval : https://arxiv.org/abs/2004.04906
- BGE Embeddings : https://arxiv.org/abs/2309.07597

---

**Last Updated**: Mai 2026
**Version**: 1.0.0

