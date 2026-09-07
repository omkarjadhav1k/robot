# 🤖 MAX — Manager AI eXecutive

**MAX (Manager AI eXecutive)** is an enterprise-grade, voice-first physical AI retail store manager. Built with a FastAPI central brain, PostgreSQL authoritative truth, Google Gemini 2.5 Flash conversational intelligence, and ESP32 physical IoT hardware, MAX automates retail sales, stock tracking, partial payment collection, appliance controls, and operational tasks.

---

## 🏛️ System Architecture: "One Brain, Absolute Truth"

```text
                  +-----------------------------------+
                  |        FastAPI Cloud Backend      |
                  |     (MAX Central Brain & Logic)   |
                  +-----------------+-----------------+
                                    |
                    +---------------+---------------+
                    |                               |
              HTTPS |                         HTTPS |
                    v                               v
        +-----------------------+       +-----------------------+
        |     🖥️ Admin Console   |       |    🤖 MAX Robot (ESP32)
        |  (/admin Web Portal)  |       |  (Physical Interface) |
        +-----------------------+       +-----------------------+
                    |                               |
                    +---------------+---------------+
                                    |
                                    v
                  +-----------------------------------+
                  |         PostgreSQL Database       |
                  |       (Single Source of Truth)    |
                  +-----------------------------------+
```

- **PostgreSQL Database**: Single authoritative source of truth for products, stock quantities, bills, partial payments, running customer balances, and immutable audit/security logs.
- **FastAPI Backend**: Central authority managing business workflows, sub-second fast-path pattern evaluation, owner PIN verification, and robot command queues.
- **Sub-Second Fast-Path Engine**: Zero-LLM instant responses for greetings (<50ms), relay appliance controls (<100ms), stock inquiries (<200ms), and customer balance queries (<200ms).
- **Gemini AI with Function Calling**: Handles complex conversational intent, multi-item billing calculations, and tool dispatch when business queries exceed the fast-path.
- **ESP32 DevKit V1 Hardware**: Physical robot with INMP441 I2S microphone, MAX98357A I2S amplifier, SSD1306 OLED display, status LEDs, and 4-channel relay appliance controllers.
- **Non-Blocking TTS & Audio Cache**: Immediate response text returned without waiting for TTS; asynchronous background TTS generation with in-memory deterministic LRU audio caching.

---

## 🌟 Key Capabilities & Upgrades

### 1. Sub-Second Fast-Path Engine
- Greets owners and customers in Hindi, Hinglish, Marathi, and English (*"Hello MAX"*, *"Kaise ho"*) in <50ms.
- Executes appliance switching instantly (*"light on kar do"*, *"fan band kar do"*, *"turn on relay 1"*) in <100ms.
- Answers frequent stock queries (*"Tata Salt ka stock kitna hai"*) and customer balance checks (*"Ramesh ka kitna baaki hai"*) in <200ms.

### 2. Partial Payment Lifecycle & Customer Ledger
- Dedicated `payments` table with `PAID`, `PARTIAL`, and `PENDING` statuses.
- Supports split and installment payments (e.g. ₹123 bill paid as ₹60 + ₹63).
- Real-time customer balance deduction and automatic FIFO application to pending bills.
- Overpayment protection strictly prevents payments exceeding outstanding due amounts.
- Comprehensive customer ledger with chronological transaction timelines and natural manager summaries.

### 3. Dynamic AI Memory & Operational Tasks
- **Strict Isolation**: Facts memorized in `ai_memory` never override PostgreSQL database truth.
- **Natural Task Extraction**: Automatically creates structured, persistent operational tasks from spoken commands (*"kal Ramesh ko remind karna ₹500 ke liye"*).
- Owner task management via `/api/v1/admin/tasks` and web console.

### 4. 6-Digit Owner PIN Security
- **PBKDF2-HMAC-SHA256**: 600,000 hashing rounds with per-business cryptographic salt.
- **Brute-Force Protection**: 3 failed PIN attempts triggers a strict 5-minute lockout.
- **High-Risk Action Protection**: Price updates, system resets, and sensitive financial actions require a verified 5-minute owner authorization token.
- **Privacy Assurance**: Owner PIN is never sent to Gemini AI, never recorded in activity logs, and sanitized from security event metadata.

### 5. Detailed Latency Observability
Every voice interaction measures and reports granular execution timestamps:
- `fast_path_ms`: Pattern matching and local database execution duration.
- `memory_ms`: Contextual AI memory retrieval time.
- `instructions_ms`: Dynamic business rule injection time.
- `gemini_ms`: Cloud LLM round-trip duration.
- `tool_ms`: Tool execution and database update time.
- `total_ms`: End-to-end processing latency.

### 6. Resilient ESP32 Transport & Error Translation
- Translates network transport errors (HTTP -11, timeout, 503) into natural, spoken manager explanations (*"Server se connect hone mein thodi dikkat ho rahi hai..."*) rather than technical codes.
- Immediate OLED status updates (*"MAX THINKING..."*, *"MAX REPLIED"*).

---

## 📁 Repository Structure

```text
c:\project\Robot\
├── README.md               # Project documentation & run guide
├── backend/                # Python / FastAPI central backend
│   ├── app/
│   │   ├── main.py         # Application entry point & lifespan
│   │   ├── config.py       # MAX Pydantic settings
│   │   ├── api/            # REST API endpoints (voice, health, security, admin, robots)
│   │   ├── models/         # SQLAlchemy models (products, bills, payments, tasks, security)
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # FastPath, Billing, Customer, Task, Memory, Security
│   │   ├── ai/             # Gemini service, speech service & LRU audio cache
│   │   ├── core/           # Shared HTTP client singleton & connection pooling
│   │   └── templates/      # MAX Admin & Operations Console (admin.html)
│   ├── tests/              # 67 Automated tests covering all MAX features
│   └── requirements.txt
├── robot/
│   └── firmware/           # ESP32 C++ / Arduino firmware (display, audio, network)
├── app/                    # Flutter cross-platform mobile application
└── docs/                   # Master architecture specifications
```

---

## 🚀 Getting Started

### 1. Environment Setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows PowerShell / CMD
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Edit `backend/.env`:
```ini
PROJECT_NAME="MAX — Manager AI eXecutive"
GEMINI_API_KEY="your-gemini-api-key"
GROQ_API_KEY="your-groq-api-key"
WHATSAPP_ACCESS_TOKEN="your-whatsapp-token"
WHATSAPP_PHONE_NUMBER_ID="your-phone-id"
```

### 3. Launch Central Brain
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Open Admin Operations Console: `http://localhost:8000/admin`
- Interactive API Documentation: `http://localhost:8000/docs`

### 4. Run Automated Tests
```bash
pytest
```
All **67 tests** (baseline + MAX upgrade suite) execute cleanly with zero failures.
