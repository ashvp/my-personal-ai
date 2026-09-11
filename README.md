# Personal AI Assistant - Local Server

A FastAPI-powered backend designed to run on your laptop, connect to a local **Qwen** model (via Ollama), and act as a server for real-time tasks (such as email processing, background tasks) and mobile client interaction.

---

## 📁 Project Structure

```
localai/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application setup & middleware
│   ├── config.py                   # Pydantic Settings & environment variables
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           └── chat.py         # POST /chat endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── chat.py                 # ChatRequest, ChatResponse Pydantic models
│   └── services/
│       ├── __init__.py
│       └── llm_service.py          # Asynchronous Ollama / Qwen communication service
├── .env.example                    # Sample environment configuration
├── .env                            # Active environment configuration
├── requirements.txt                # Python dependencies
├── run.py                          # Application entry point
└── README.md
```

---

## 🚀 Getting Started in WSL

### 1. Set Up Virtual Environment

Open your WSL terminal and navigate to the project directory:

```bash
cd /mnt/d/localai

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)

Check your `.env` file:

```env
HOST=0.0.0.0
PORT=8000
DEBUG=True

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:2b
LLM_TIMEOUT_SECONDS=120.0
```

> **💡 WSL to Windows Ollama Note:**
> - If Ollama is running **inside WSL**: `http://127.0.0.1:11434` works directly.
> - If Ollama is running **on Windows host**:
>   - In Windows, make sure Ollama listens on all interfaces (set Windows user environment variable `OLLAMA_HOST=0.0.0.0`).
>   - In WSL, point `OLLAMA_BASE_URL` to `http://$(ip route | awk '/default/ {print $3}'):11434` or `http://host.docker.internal:11434` (if mirrored networking or Docker Desktop is configured).

### 3. Run the Server

```bash
# Using the helper script:
python run.py

# Or directly using uvicorn:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📖 API Documentation & Testing

Once the server is running, open your browser:

- **Swagger UI (Interactive Docs):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

### Testing `/chat` in Swagger UI

1. Open `http://localhost:8000/docs`.
2. Expand `POST /chat` and click **"Try it out"**.
3. Send a test payload:
   ```json
   {
     "message": "Hello! What can you help me with?",
     "system_prompt": "You are a helpful personal AI assistant.",
     "temperature": 0.7
   }
   ```
4. Click **Execute** to receive the reply from your local Qwen model.

### Testing via `curl`

```bash
curl -X POST "http://localhost:8000/chat" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Give me 3 quick productivity tips for today."
     }'
```
