# Personal AI Assistant - Local Server & PWA

A FastAPI-powered backend with a standalone Progressive Web App (PWA) designed to run on your laptop, connect to a local **Qwen** model (via Ollama), and serve as your authenticated personal assistant accessible from your mobile phone and secondary laptops.

---

## 📁 Project Structure

```
localai/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application, CORS & PWA static mounts
│   ├── config.py                   # Pydantic Settings & model routing configuration
│   ├── core/
│   │   ├── __init__.py
│   │   └── security.py             # Device token auth (X-Device-Token)
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── chat.py         # Protected POST /chat (SSE streaming by default)
│   │           ├── gmail.py        # Gmail sync & status endpoints
│   │           ├── whatsapp.py     # WhatsApp (Beeper) sync & status endpoints
│   │           ├── sms.py          # Google Messages SMS sync endpoints
│   │           ├── contacts.py     # Contacts & autonomous dialing endpoints
│   │           ├── sync.py         # Multi-modal background sync controller
│   │           ├── graph.py        # Bitemporal Knowledge Graph (V2) REST endpoints
│   │           └── outlook.py      # Outlook/College mail endpoints (on hold)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── chat.py                 # ChatRequest & ChatResponse schemas
│   └── services/
│       ├── __init__.py
│       ├── llm_service.py          # LLM-native action engine, model routing & Ollama stream service
│       ├── graph_service.py        # Bitemporal Knowledge Graph Engine (V2 - assertions, time-travel, BFS)
│       ├── contacts_service.py     # Local contacts resolver & autonomous MacroDroid calling/messaging
│       ├── triage_service.py       # Multi-modal daily briefing cognitive triage (Schedule -> People -> Promos)
│       ├── memory_service.py       # 3-Tier Cognitive Memory Engine (Working, Episodic, Archive)
│       ├── background_sync.py      # Non-blocking periodic background sync worker
│       ├── gmail_service.py        # Gmail API OAuth client & message ingester
│       ├── whatsapp_service.py     # Beeper SQLite snapshot ingester & contact resolver
│       ├── sms_service.py          # Beeper SQLite Google Messages SMS snapshot ingester
│       └── outlook_service.py      # Microsoft Graph API client (College mail integration)
├── data/
│   └── assistant.duckdb            # Local DuckDB database (emails, messages, entities, temporal_edges)
├── frontend/
│   ├── index.html                  # Modern responsive chat interface
│   ├── manifest.json               # PWA configuration for mobile home screen installation
│   ├── sw.js                       # Service Worker for offline caching & standalone mode
│   ├── css/
│   │   └── custom.css              # Custom styling (thinking pulse, markdown, safe areas)
│   └── js/
│       ├── app.js                  # Real-time SSE streaming client & token handling
│       └── pwa.js                  # PWA service worker installer
├── .env                            # Active environment configuration
├── requirements.txt                # Python dependencies
├── authenticate_gmail.py           # One-time Google OAuth authorization helper
├── authenticate_outlook.py         # One-time Microsoft OAuth authorization helper
├── pair.py                         # Device pairing utility (QR code & link generator)
├── run.py                          # Application launcher
├── run_tests.py                    # 105-Case benchmark & evaluation runner
├── run_v1_vs_v2_llm_eval.py        # Live Ollama LLM Benchmark (V1 Vector RAG vs V2 Temporal KG)
├── tests/
│   ├── dataset_100_cases.py        # Curated 105-case benchmark evaluation dataset
│   ├── dataset_v1_vs_v2_benchmarks.py # 25 Ground-truth temporal scenarios
│   ├── test_v1_comprehensive.py    # Automated test suite computing formal metrics
│   ├── test_graph_service.py       # V2 DuckDB Temporal Knowledge Graph unit test suite
│   └── v1_vs_v2_engine.py          # Comparative reference benchmark engines
├── LICENSE                         # MIT License
├── v2.md                           # Version 2.0 architecture & roadmap specification
└── README.md
```

---

## 📦 Version 1.0 (v1) Deliverables

The v1 release transforms the assistant from a basic single-model chat prototype into a fully autonomous, production-ready local personal executive system. All core deliverables have been implemented, benchmarked, and verified end-to-end:

| Deliverable | Key Highlights | Status |
| :--- | :--- | :---: |
| **100% LLM-Native Action Engine** | Zero-regex architecture; resolves intent, recipient, and message in a single ~4s warm inference call (`qwen3:1.7b`). Auto-rewrites colloquial & imperative requests into direct first-person polite messages. Conversational context continuity extracts recipients and messages from previous turns (`"send that to him in whatsapp"`). | ✅ **Delivered** |
| **Autonomous Cellular Calling** | Hands-free physical SIM dialing on Android via MacroDroid webhooks (`/call`). Intelligent 10-digit Indian SIM dialing (auto-strips `91` / `0` prefixes). Interactive call cards with episodic history of the last conversation and quick-action links. | ✅ **Delivered** |
| **Autonomous WhatsApp Messaging** | Direct hands-free WhatsApp messaging via MacroDroid webhook (`/whatsapp`). Auto-formats phone numbers (`91XXXXXXXXXX`), enforces first-person perspective, and provides 1-tap WhatsApp deep link fallbacks. | ✅ **Delivered** |
| **3-Tier Cognitive Memory Engine** | Fully migrated from raw SQL to **SQLAlchemy ORM + DuckDB** (`assistant.duckdb`). Categorizes multi-modal data into Working Memory (<48h), Episodic Memory (2–30d), and Historical Archive (>30d). | ✅ **Delivered** |
| **Local Contacts Synchronization** | Ingests verified human contacts from Beeper's local SQLite store into DuckDB (`contacts` table). Provides sub-millisecond fuzzy search and alias matching (`appa` $\to$ `Prasad Appa`). | ✅ **Delivered** |
| **Multi-Modal Data Ingestion** | Full ingestion pipelines for **Gmail** (OAuth read-only with auto-refresh), **WhatsApp** (local Beeper SQLite snapshot), and **Google Messages / Android SMS** (Beeper SQLite snapshot). | ✅ **Delivered** |
| **Automated 1-Minute Background Sync** | Fully non-blocking background daemon using `asyncio.to_thread` for SQLite snapshots and DuckDB writes. Keeps working memory near real-time every 60s (<50ms execution on idle). | ✅ **Delivered** |
| **Executive Daily Cognitive Triage** | Intelligent multi-modal daily briefing triaging data into: 1. Schedule & Deadlines $\to$ 2. People Waiting on You $\to$ 3. Important Correspondence $\to$ 4. Collapsed Promotional Noise. | ✅ **Delivered** |
| **Dynamic Model Routing** | 3-tier local LLM routing (`qwen3:0.6b` classifier $\to$ `qwen3:1.7b` fast worker $\to$ `qwen3.5:2b` reasoning engine). Eliminates reasoning lag, slashing simple chat response times from **>60s down to ~2s**. | ✅ **Delivered** |
| **Zero-Build PWA & Device Auth** | Lightweight standalone mobile web app installable on iOS & Android home screens. Secure `X-Device-Token` authentication and one-line pairing CLI with ASCII QR codes (`pair.py`). | ✅ **Delivered** |

---

## ⚡ Performance Breakthrough: From 60s Down to ~2s
 
* **The Problem with a Single Reasoning Model:**
  Originally, the assistant ran exclusively on a single model (`qwen3.5:2b`). Because it was a reasoning/thinking model running on consumer hardware (e.g., RTX 2050 4GB), even a simple *"hi"* or *"what was my last mail?"* forced the model into massive chain-of-thought loops, generating hundreds of internal hidden reasoning tokens before outputting an answer. A simple greeting or inbox check took **over 60 seconds**!
* **The Solution: Intent-Based Model Routing:**
  Instead of forcing one model to do everything, we implemented a 3-tier routing architecture with few-shot intent classification:
  1. **Micro-Classifier (`qwen3:0.6b` / ~400MB VRAM):** Takes ~100ms to classify user intent into `EMAIL_LOOKUP`, `FAST_CHAT`, or `DEEP_REASON`.
  2. **Fast Chat / Lookup Worker (`qwen3:1.7b`):** Answers casual greetings, drafts, and email summaries in **~2 seconds** without heavy reasoning overhead.
  3. **Deep Reasoning Model (`qwen3.5:2b`):** Reserved strictly for complex multi-step reasoning, coding, and analytical tasks where thinking chains are genuinely needed.

---

## 🤖 100% LLM-Native Action Engine: Zero-Regex Architecture

* **The Fallacy of Regex Rules:**
  Initially, communication commands relied on regex patterns and prefix stripping (`"tell "`, `"ask "`, `"text "`, `"call "`). Natural language has infinite permutations, and regex continuously broke on colloquial phrasing or crossed wires (e.g., misrouting *"call appa"* into a WhatsApp prompt asking *"Who would you like to message?"*).
* **Pure LLM Intent Understanding:**
  We replaced all regex parsers, heuristic fallbacks, and string matchers with a **100% LLM-native action resolver** powered by a single warm call to `qwen3:1.7b` with structured JSON output:
  ```json
  {
    "action": "whatsapp" | "call" | "daily_briefing" | "message_lookup" | "email_lookup" | "chat",
    "recipient": "person name or phone number",
    "message": "polite first-person message addressed to recipient",
    "query": "search query if lookup"
  }
  ```
* **~4-Second Average Inference:**
  On a consumer laptop GPU (RTX 2050 4GB), end-to-end intent understanding, contact lookup, message sanitization, and webhook dispatch execute in an average of **4 seconds**.
* **Broken English & Imperative-to-Polite Conversion:**
  The model understands that the user is an executive and **never** wants mock chat roleplays or drafts. Any imperative, casual, or broken English instruction is automatically converted into a direct, polite first-person message:
  - *"Ask Prasad to buy pizza and come home today"* $\to$ WhatsApp message: `"Please buy pizza and come home today."`
  - *"Text appa telling him to come early"* $\to$ WhatsApp message: `"Please come early."`
  - *"tell mom not to wait for dinner"* $\to$ WhatsApp message: `"Please do not wait for me for dinner."`
* **Conversational Context & Pronoun Continuity:**
  Follow-up instructions seamlessly pull from recent conversation turns:
  - User: *"Draft a message for Prasad about the project delay."*
  - Assistant: *"Hi Prasad, the server migration will cause a 2-day delay."*
  - User: *"Send that to him in whatsapp"* $\to$ Automatically extracts `recipient='Prasad'` and `message='Hi Prasad, the server migration will cause a 2-day delay.'` and sends it immediately!

---

## 📞 Autonomous Calling & Messaging (MacroDroid Integration)

* **Autonomous Cellular Calling (Android SIM):**
  - Natural commands like *"call appa"*, *"dial mom"*, or *"ring Prasad"* autonomously trigger a direct cellular phone call on the phone's physical SIM via MacroDroid Webhooks.
  - **Indian 10-Digit SIM Dialing:** Automatically strips `91` or leading `0` (`+919940020084` $\to$ `9940020084`) so Indian telecom carriers don't reject the call as an invalid STD/area code.
  - Displays a rich interactive call card with episodic memory context of the last conversation, quick-dial links, and SMS shortcuts.
* **Autonomous WhatsApp Delivery:**
  - MacroDroid webhook opens WhatsApp, enters the sanitized message, sends it, and returns back—completely hands-free.

---

## 🌟 Key Features

* **Sub-2s Chat & ~4s Autonomous Actions:** 100% LLM-native action engine with dynamic routing across specialized local models.
* **Hands-Free Cellular Calling:** Dials contacts directly on your Android SIM via MacroDroid without manual intervention.
* **Autonomous WhatsApp Messaging:** Automatically converts broken English and informal commands into polite, direct messages and sends them via WhatsApp.
* **Executive Never-Draft Policy:** Real-world execution over simulation—no fake mock chat transcripts.
* **Local Memory & Contact Resolution (DuckDB):** Ingests and indexes Google Contacts, WhatsApp chats, and SMS from local Beeper SQLite stores for instant name resolution.
* **Real-time SSE Streaming:** Live token streaming with dynamic thinking accordion (`🧠 Thought process ▾`).
* **Passwordless Device Authentication:** Authorized `X-Device-Token` verification with 1ms rejection of unauthorized requests.
* **Zero-Build PWA:** Runs directly from FastAPI. Installable on mobile home screens without browser frames.

---

## 🚀 Getting Started in WSL

### 1. Set Up Environment

```bash
cd /mnt/d/localai

# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)

```env
HOST=0.0.0.0
PORT=8000
DEBUG=True

OLLAMA_BASE_URL=http://172.25.240.1:11434
LLM_TIMEOUT_SECONDS=120.0

# 3-Model Dynamic Routing
MODEL_ROUTER=qwen3:0.6b        # Fast ~100ms intent classifier
MODEL_FAST=qwen3:1.7b          # Instant 1-2s replies (chat, drafting, email lookups)
MODEL_REASONING=qwen3.5:2b     # Deep reasoning model (logic, math, code analysis)

DEFAULT_SYSTEM_PROMPT="You are an intelligent, proactive personal AI assistant. Be concise, helpful, and clear."
DEFAULT_TEMPERATURE=0.7

AUTHORIZED_DEVICE_TOKENS=your_secret_device_token
```

### 3. Start the Server

```bash
python run.py
```

---

## 📱 Pairing Your Devices

Run the pairing helper inside WSL:

```bash
# For local network / other laptop
python pair.py

# Or if exposing via ngrok tunnel
python pair.py --url https://your-tunnel.ngrok-free.app
```

### 1. On Your Other Laptop Browser:
Just open the printed link:
```
http://<server-ip>:8000/?token=your_secret_device_token
```
It will automatically save your token into `localStorage` and clear the token from the URL bar. You're ready to chat!

### 2. On Your Mobile Phone:
1. Scan the ASCII QR code printed in the terminal with your phone camera.
2. Tap the link to open the app.
3. In Safari (iOS) tap **Share $\rightarrow$ Add to Home Screen**, or in Chrome (Android) tap **Menu $\rightarrow$ Install App / Add to Home screen**.
4. Launch it from your home screen as a native full-screen app!

---

## 📖 API & Developer Testing

* **Web App:** [http://localhost:8000/](http://localhost:8000/)
* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs) (Use Authorize 🔓 with your token)
* **Automated 105-Case Evaluation Benchmark & Test Suite:**
  ```bash
  python run_tests.py
  ```
  Computes 7 formal evaluation metrics across 105 curated test scenarios: Meta-Prefix Strip Rate (MPSR), First-Person Perspective Fidelity (FPPF), Phone Dialer 10-Digit Sanitization Precision (PDSP), Contact Alias Resolution Rate (CARR), Follow-Up Context Extraction Accuracy (FCEA), DuckDB Memory ORM Integrity (MOI), and Temporal Knowledge Graph Benchmark Accuracy (TGBA).

* **Head-to-Head V1 (Vector RAG) vs. V2 (Temporal Knowledge Graph) Benchmark:**
  ```bash
  python run_v1_vs_v2_benchmarks.py
  ```
  Pits unstructured vector search against the bitemporal knowledge graph across 25 real-world scenarios. Evaluates Temporal Fact Invalidation Precision (TFIP), Point-In-Time Historical Accuracy (PITHA), Multi-Hop Relational Traversal Rate (MHTR), State Contradiction Resolution Rate (SCRR), and Hallucinatory Blending Rate (HBR).

---

## 🔌 Integrations & Data Ingestion Status

| Source | Status | Storage / Memory Tier | Notes |
| :--- | :--- | :--- | :--- |
| **Cellular Calls (MacroDroid)** | 🟢 **Active** | Android SIM via Webhook (`/call`) | Autonomous physical SIM dialing. Auto-strips `91` for Indian 10-digit dialing; URL-encodes `+` for international. |
| **WhatsApp Outbound (MacroDroid)** | 🟢 **Active** | MacroDroid Webhook (`/whatsapp`) | Hands-free background message dispatch. Converts broken English commands to polite direct text. |
| **Contacts Sync (Beeper)** | 🟢 **Active** | DuckDB `contacts` table | Synchronizes verified phonebook names & numbers from local Beeper SQLite store for sub-millisecond lookup. |
| **Gmail** | 🟢 **Active** | DuckDB `emails` table + Working Memory (<48h) | Google OAuth device flow. Full inbox search & summaries. |
| **WhatsApp (Beeper Inbound)** | 🟢 **Active** | DuckDB `messages` table (3-Tier Engine) | Reads local SQLite store (`index.db`), auto-resolves 1-on-1 participant names, segments into Working (<48h), Episodic (2–30d), and Long-Term (>30d). |
| **Google SMS (Beeper Inbound)** | 🟢 **Active** | DuckDB `messages` table (`source='sms'`) | Ingests Android RCS / SMS from Beeper store, resolves contact names, feeds cognitive triage (separates promos from personal SMS). |
| **Outlook / College Mail** | 🟡 **On Hold (Tenant Restricted)** | Standby (`app/services/outlook_service.py`) | **University Policy Restriction:** Many university/organizational Microsoft 365 tenants require Tenant Admin consent for Microsoft Graph `Mail.Read`. Student self-registered Azure apps are often blocked with `AADSTS65002` / `Need admin approval`. |


### Outlook / College Mail Fallback Solutions:
1. **Auto-Forwarding Rule (Recommended):** Set an inbox forwarding rule in college webmail (`outlook.office.com`) to redirect incoming emails to your connected Gmail account. The assistant automatically tags emails from your college domain as `source: college`.
2. **Windows Desktop Outlook (COM):** Local Python script querying the desktop Outlook client directly on Windows (bypassing cloud API & tenant restrictions).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE). See the [LICENSE](LICENSE) file for the full text.


