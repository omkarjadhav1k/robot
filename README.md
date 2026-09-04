# 🤖 Business AI Robot

A voice-first physical AI business assistant and operational manager built for retail stores, inventory tracking, voice-operated billing, physical IoT appliance control, and real-time business telemetry.

---

## 🏛️ System Architecture: "One Brain"

```text
                  +-----------------------------------+
                  |        FastAPI Cloud Backend      |
                  |     (Business Brain & Authority)  |
                  +-----------------+-----------------+
                                    |
                    +---------------+---------------+
                    |                               |
              HTTPS |                         HTTPS |
                    v                               v
        +-----------------------+       +-----------------------+
        |     📱 Flutter App    |       |    🤖 ESP32 Robot     |
        |  (Visual Dashboard)   |       |  (Physical Interface) |
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

- **PostgreSQL** is the sole source of truth for inventory, pricing, customer records, bills, payments, reminders, and audit logs.
- **FastAPI** is the central authority for authentication, validation, business transactions, and hardware command lifecycles.
- **Gemini AI** serves as the conversational reasoning and intent layer, executing pre-approved structured tool actions only.
- **ESP32 DevKit V1** provides physical presence, I2S voice capture/playback, OLED visual status, buttons, and relay appliance control.
- **Flutter App** provides real-time visual control and operations management for the business owner.

---

## 📁 Repository Structure

```text
c:\project\Robot\
├── README.md               # Project documentation & run guide
├── .env.example            # Environment variables configuration template
├── .gitignore              # Git ignore rules for Python, Flutter, ESP32
├── docs/                   # Master specifications and hardware guides
│   ├── PRODUCT_SPEC.md     # Full architectural specification
│   ├── HARDWARE_SPEC.md    # Hardware components, pinouts & wiring rules
│   ├── DEVELOPMENT_PLAN.md # 36-Phase development roadmap
│   └── ANTIGRAVITY_MASTER_PROMPT.md
├── backend/                # Python / FastAPI central backend
│   ├── requirements.txt    # Python dependencies
│   ├── pyproject.toml      # Project metadata & test configuration
│   ├── app/
│   │   ├── main.py         # Application entry point & middleware
│   │   ├── config.py       # Pydantic settings management
│   │   ├── api/            # REST API route handlers (/health, /robots)
│   │   ├── models/         # SQLAlchemy database models
│   │   ├── schemas/        # Pydantic request/response validation schemas
│   │   ├── services/       # Core business logic (inventory, billing, payments)
│   │   ├── ai/             # Gemini API integration & tool dispatch
│   │   ├── robot/          # Robot command lifecycle & state machine
│   │   ├── automation/     # Trigger-based automation engine
│   │   ├── security/       # JWT auth, RBAC (Owner/Staff/Robot)
│   │   └── database/       # DB session, engine & migrations
├── robot/
│   └── firmware/           # ESP32 C++ / Arduino firmware
├── app/                    # Flutter cross-platform mobile application
├── deployment/             # Dockerfile & Cloud Run configurations
└── tests/                  # Integration & unit test suites
```

---

## 🚀 Getting Started (Backend)

### Prerequisites
- Python 3.11+
- Virtual environment (`uv` or `venv`)

### Setup Instructions
1. Navigate to the backend:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment:
   ```bash
   cp ../.env.example .env
   ```
5. Run the FastAPI server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
6. Run tests:
   ```bash
   pytest
   ```
