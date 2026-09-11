# Personal AI Assistant - Local Server & PWA

A FastAPI-powered backend with a standalone Progressive Web App (PWA) designed to run on your laptop, connect to a local **Qwen** model (via Ollama), and serve as your authenticated personal assistant accessible from your mobile phone and secondary laptops.

---

## 📁 Project Structure

```
localai/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application, CORS & PWA static mounts
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
│   │           └── chat.py         # Protected POST /chat (SSE streaming by default)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── chat.py                 # ChatRequest & ChatResponse schemas
│   └── services/
│       ├── __init__.py
│       └── llm_service.py          # Asynchronous Ollama / Qwen communication service
├── frontend/
│   ├── index.html                  # Modern responsive chat interface
│   ├── manifest.json               # PWA configuration for mobile home screen installation
│   ├── sw.js                       # Service Worker for offline caching & standalone mode
│   ├── css/
│   │   └── custom.css              # Custom styling (thinking pulse, markdown, safe areas)
│   └── js/
│       ├── app.js                  # Real-time SSE streaming client & token handling
│       └── pwa.js                  # PWA service worker installer
├── .env.example                    # Sample environment configuration
├── .env                            # Active environment configuration
├── requirements.txt                # Python dependencies
├── pair.py                         # Device pairing utility (QR code & link generator)
├── run.py                          # Application launcher
└── README.md
```

---

## 🌟 Key Features

* **Real-time SSE Streaming:** Tokens stream instantly to the UI as Qwen generates them.
* **Collapsible "Thinking" Accordion:** Displays live reasoning step-by-step (`Thinking... (14s)`), and collapses automatically into `🧠 Thought process ▾` when the final answer begins.
* **Passwordless Device Authentication:** Every request requires an authorized `X-Device-Token`. Unauthorized callers or random ngrok visitors get rejected in 1ms with `401 Unauthorized`.
* **Zero-Build PWA:** Runs directly from FastAPI. No Node.js or npm needed.
* **Mobile Ready:** Tap "Add to Home Screen" on iOS/Android to install it as a standalone app with no browser address bar.

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
OLLAMA_MODEL=qwen3.5:2b
LLM_TIMEOUT_SECONDS=120.0

DEFAULT_SYSTEM_PROMPT="You are an intelligent, proactive personal AI assistant. Be concise, helpful, and clear."
DEFAULT_TEMPERATURE=0.7

AUTHORIZED_DEVICE_TOKENS=dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607
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
http://<server-ip>:8000/?token=dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607
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
* **Terminal Stream (curl -N):**
  ```bash
  curl -N -X POST "http://localhost:8000/chat" \
       -H "X-Device-Token: dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607" \
       -H "Content-Type: application/json" \
       -d '{"message": "Give me 3 productivity tips"}'
  ```
