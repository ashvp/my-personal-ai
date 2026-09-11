# Personal AI Assistant - Local Server

A FastAPI-powered backend designed to run on your laptop, connect to a local **Qwen** model (via Ollama), and act as an authenticated server for real-time tasks (such as email processing, background tasks) and mobile client interaction.

---

## 📁 Project Structure

```
localai/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application & CORS
│   ├── config.py                   # Pydantic Settings & environment variables
│   ├── core/
│   │   ├── __init__.py
│   │   └── security.py             # Device token auth (X-Device-Token)
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           └── chat.py         # Protected POST /chat endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── chat.py                 # ChatRequest (message only) & ChatResponse
│   └── services/
│       ├── __init__.py
│       └── llm_service.py          # Asynchronous Ollama / Qwen communication service
├── .env.example                    # Sample environment configuration
├── .env                            # Active environment configuration
├── requirements.txt                # Python dependencies
├── pair.py                         # Device pairing utility (QR code & token generator)
├── run.py                          # Application launcher
└── README.md
```

---

## 🔐 Device Authentication

All requests to `/chat` require a valid **`X-Device-Token`** header. Unauthorized requests are immediately blocked with `401 Unauthorized` before hitting Ollama or consuming laptop resources.

### Pair a Device (Phone or Secondary Laptop)

Run the pairing utility:

```bash
# Pair with local URL
python pair.py

# Or pair with your active ngrok URL
python pair.py --url https://your-tunnel.ngrok-free.app

# Or generate a dedicated new token for a specific device
python pair.py --new --name "Work-MacBook"
```

This will print:
1. **For Laptops:** The exact device token and a ready-to-run `curl` command.
2. **For Mobile Phones:** An **ASCII QR code** directly in your terminal containing `{server_url, token}` for single-tap pairing.

---

## 🚀 Getting Started in WSL

### 1. Set Up Virtual Environment

```bash
cd /mnt/d/localai

# Create and activate virtual environment
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
OLLAMA_MODEL=qwen3.5:2b
LLM_TIMEOUT_SECONDS=120.0

DEFAULT_SYSTEM_PROMPT="You are an intelligent, proactive personal AI assistant. Be concise, helpful, and clear."
DEFAULT_TEMPERATURE=0.7

AUTHORIZED_DEVICE_TOKENS=dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607,dev_laptop_trusted
```

### 3. Run the Server

```bash
python run.py
```

---

## 📖 Testing via Swagger UI & curl

### In Swagger UI:
1. Open [http://localhost:8000/docs](http://localhost:8000/docs).
2. Click the green **Authorize 🔓** button at the top right.
3. Paste your token (e.g. `dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607`).
4. Click **Authorize**, then **Close**.
5. Test `POST /chat` with just:
   ```json
   {
     "message": "Hello! What can you help me with?",
     "stream": true
   }
   ```
   *(Swagger UI will receive the live SSE event stream)*

### Real-Time Streaming via `curl`:
Add `-N` (unbuffered) to see tokens stream live as Qwen produces them:
```bash
curl -N -X POST "http://localhost:8000/chat" \
     -H "X-Device-Token: dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607" \
     -H "Content-Type: application/json" \
     -d '{"message": "Give me a quick 3-bullet briefing."}'
```

### Blocking JSON (for non-streaming or internal callers):
Set `"stream": false`:
```bash
curl -X POST "http://localhost:8000/chat" \
     -H "X-Device-Token: dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607" \
     -H "Content-Type: application/json" \
     -d '{"message": "Give me a quick 3-bullet briefing.", "stream": false}'
```
