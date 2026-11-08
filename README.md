# Agent Dusty (version test) - Aero Weather Agent 🛩️🌦️

## Bonjour et bienvenue sur mon projet Dusty

Dusty (référence au héros du dessin animé PIXAR Planes)est un agent IA destiné à assister les élèves pilotes et jeunes pilotes dans leur préparation aux vols de navigation.

Agent autonome d'aide à la décision pour la préparation de vol VFR, orchestré avec **LangGraph**. L'agent analyse les intentions du pilote en langage naturel, télécharge automatiquement les dossiers officiels Météo-France via **Playwright**, extrait et décode les bulletins cryptiques (**METAR / TAF**) via un pipeline OCR (**Tesseract** / **Poppler**), évalue la faisabilité opérationnelle selon les règles VFR, génère un rapport PDF et propose l'envoi par e-mail via un mécanisme sécurisé **Human-in-the-loop (HITL)**.

---

## Fonctionnalités clés

- 🧠 **Compréhension du langage naturel :** Extraction automatique du type de vol (local, navigation/trajet), des aérodromes (codes OACI ou noms de villes) et des règles de vol avec validation Pydantic.
- 🌐 **Automatisation web résiliente (Playwright) :** Authentification et navigation automatique sur le portail officiel Aeroweb (Météo-France) pour extraire le dossier de vol PDF.
- 👁️ **Pipeline Vision & OCR :** Conversion vectorielle PDF vers images haute résolution (`pdf2image`), reconnaissance optique de caractères (`pytesseract`), extraction ciblée par regex et décodage complet en clair des messages aéronautiques.
- ⚖️ **Aide à la décision VFR :** Synthèse contextuelle croisant les observations réelles et prévisions (visibilité, base des nuages BKN/OVC, vent, rafales, phénomènes dangereux) pour déterminer si le vol est praticable et définir les créneaux favorables.
- 📄 **Export PDF & HITL (Human-in-the-loop) :** Compilation du rapport prévol au format PDF et suspension d'exécution (`interrupt()`) pour exiger l'accord explicite et l'adresse e-mail du pilote avant tout envoi SMTP.

---

## Architecture du graphe & Workflows

L'agent repose sur une topologie de graphe d'états déterministe avec interruption humaine contrôlée :

```text
                  START
                    │
                    ▼
          [parse_user_flight]
                    │
         (Aérodromes complets ?)
          ├── NON ──► [ask_clarification] ──► END
          └── OUI ──► [fetch_bulletin] (Playwright)
                            │
                            ▼
                     [process_ocr] (Tesseract + Regex + Traduction)
                            │
                            ▼
                  [analyse_feasibility] (Évaluation VFR & LLM)
                            │
                            ▼
                      [export_pdf] (Génération Weasyprint/HTML)
                            │
                            ▼
              [human_review_and_send_email] ──(interrupt)──► Validation Pilote
                            │                                     │
                            └───────────◄── (Command: resume) ────┘
                                  │
                                 END
```

### Détail des nœuds du graphe

1. **`parse_user_flight` :** Analyse la requête initiale du pilote. Identifie l'intention, déduit le mode (`trajet` ou `local`), mappe les villes en codes OACI français normalisés (ex: *Saint-Cyr* $\rightarrow$ `LFPZ`, *Melun* $\rightarrow$ `LFPM`) et extrait les règles de vol associées.
2. **`ask_clarification` :** Nœud de repli déclenché si les paramètres obligatoires (aérodrome de départ ou d'arrivée) sont manquants ou ambigus.
3. **`fetch_bulletin` :** Pilote une instance de navigateur Chromium asynchrone via Playwright. Le script se connecte à Aeroweb, navigue dans l'interface de dossier de vol, soumet les terrains et télécharge le PDF officiel. Il initialise également le fichier JSON de suivi.
4. **`process_ocr` :** Convertit les pages du PDF en images (`pdf2image`), extrait le texte brut via Tesseract, isole les blocs METAR et TAF de chaque aérodrome par expressions régulières, puis traduit chaque segment météo en langage clair. Sauvegarde la structure complète dans un fichier JSON.
5. **`analyse_feasibility` :** Évalue la conformité des données météo vis-à-vis des critères VFR (plafond minimal, visibilité en vol, vent traversier, rafales, orages/brouillards). Rédige une synthèse décisionnelle structurée (Go / No-Go, facteurs bloquants, créneau favorable).
6. **`export_pdf` :** Compile l'analyse de faisabilité et la transcription intégrale des bulletins en un document PDF mis en page et prêt à l'impression.
7. **`human_review_and_send_email` :** Gèle l'exécution du graphe (`interrupt`) pour afficher l'aperçu du dossier au pilote et lui demander son autorisation d'envoi ainsi que l'adresse e-mail de destination. Après confirmation (`Command(resume=...)`), invoque le tool d'envoi SMTP avec le PDF en pièce jointe.

---

## Prérequis système

> [!WARNING]
> Ce projet nécessite des utilitaires système natifs qui doivent être installés sur votre machine hôte avant de lancer l'environnement Python.

### Sur macOS (via Homebrew) :
```bash
brew install tesseract
brew install poppler
```

### Sur Linux (Debian / Ubuntu) :
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
```

---

## Installation et configuration

### 1. Cloner le projet et préparer l'environnement

```bash
git clone https://github.com/votre-compte/weather-assistant.git
cd weather-assistant

# Création de l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installation des dépendances Python
pip install -r requirements.txt

# Installation des binaires de navigation Playwright
playwright install chromium
```

### 2. Configuration des variables d'environnement (`.env`)

Créez un fichier `.env` à la racine du projet en vous basant sur le modèle suivant :

```env
# Clé API LLM (OpenRouter ou OpenAI)
OPENROUTER_API_KEY=votre_cle_api

# Identifiants du portail officiel Météo-France / Aeroweb
AEROWEB_USERNAME=votre_identifiant_aeroweb
AEROWEB_PASSWORD=votre_mot_de_passe_aeroweb

# Configuration SMTP pour l'envoi du dossier
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=votre_adresse@gmail.com
# IMPORTANT: Utilisez un mot de passe d'application de 16 caractères (sans espaces)
SMTP_PASSWORD=abcdefghijklmnop
```

---

## Utilisation

Pour lancer une session interactive complète avec arrêt Human-in-the-loop :

```bash
python test_hitl.py
```

### Exemple de déroulement :
```text
🚀 [Étape 1] Lancement du pipeline...
⏳ [LLM] Extraction du trajet... Trajet détecté : LFPZ -> LFPM (VFR)
⏳ [Playwright] Téléchargement du dossier officiel Aeroweb...
⏳ [OCR] Rendu image et extraction des bulletins METAR/TAF...
⏳ [LLM] Évaluation de la conformité VFR...
📄 [PDF] Génération du rapport de prévol...

==================================================
🛑 DEMANDE DE VALIDATION PILOTE :
Le rapport PDF est prêt (rapport_prevol_LFPZ_LFPM.pdf).
Souhaitez-vous le recevoir par e-mail ?
==================================================

Confirmer l'envoi ? (o/n) : o
Adresse e-mail : pilote@aero-club.fr

🚀 [Étape 2] Reprise du graphe...
📧 [EMAIL] Email envoyé à pilote@aero-club.fr avec succès.
```

---

## Structure du projet

```text
weather-assistant/
├── bulletins/                 # Dossiers PDF bruts téléchargés depuis Aeroweb
├── bulletins_analyses/        # Rapports PDF finaux générés
├── bulletins_traduits/        # JSON intermédiaires des bulletins décodés
├── skills/
│   ├── aeroweb_fetcher.py     # Automatisation Playwright du site Aeroweb
│   ├── pipeline_ocr.py        # Conversion pdf2image, Tesseract, parseur regex
│   ├── report_generator.py    # Moteur de génération HTML/PDF (Weasyprint)
│   ├── email_sender.py        # Outil d'envoi SMTP avec pièce jointe
│   └── vfr_rules.py           # Logique d'analyse de conformité météo VFR
├── models.py                  # Schémas Pydantic et configuration des LLMs
├── state.py                   # Définition du FlightState LangGraph
├── graph.py                   # Définition et compilation du graphe LangGraph
├── test_hitl.py               # Script de test de bout en bout (Human-in-the-loop)
├── requirements.txt           # Dépendances Python
└── README.md
```