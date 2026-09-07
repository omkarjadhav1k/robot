# 🤖 Business AI Robot: Complete System Architecture, Tech Stack & Setup Guide

This document is the authoritative technical reference for the **Business AI Robot** project. It details the complete end-to-end request lifecycle, technology stack, Python libraries, API catalog, cloud infrastructure, and step-by-step setup guides for both **Cloud Mode** and **Ultra-Fast Local Wi-Fi Mode**.

---

## 📑 Table of Contents

1. [High-Level Architecture & Core Philosophy](#1-high-level-architecture--core-philosophy)
2. [Hosting Platforms & Repository Mapping](#2-hosting-platforms--repository-mapping)
3. [End-to-End Request Flow (API Call Kaha Se Kaha Jaata Hai)](#3-end-to-end-request-flow)
4. [Complete Technology Stack & Python Libraries](#4-complete-technology-stack--python-libraries)
5. [Complete API Catalog (Sabhi API Endpoints)](#5-complete-api-catalog)
6. [Database Schema (Single Source of Truth)](#6-database-schema)
7. [Step-by-Step Setup Guide (Proper Setup)](#7-step-by-step-setup-guide)
   - [Mode A: Ultra-Fast Local Wi-Fi Setup (~1.0s Response)](#mode-a-ultra-fast-local-wi-fi-setup-recommended)
   - [Mode B: Production Cloud Deployment (Render + WhatsApp)](#mode-b-production-cloud-deployment)
   - [ESP32 Firmware Flashing Guide](#esp32-firmware-flashing-guide)
8. [Troubleshooting & Performance Optimization Guide](#8-troubleshooting--performance-optimization-guide)

---

## 1. High-Level Architecture & Core Philosophy

The Business AI Robot is built on a **"One Brain"** architecture. Rather than having fragmented logic across microcontroller firmware or client apps, a single central backend maintains strict authority over:
- **Authoritative Database**: PostgreSQL is the sole truth for inventory, prices, customer credits, bills, and learned rules.
- **Natural Multilingual NLU**: Understands everyday conversational speech in Hindi, Marathi, Hinglish, and English without rigid commands.
- **Short-Term Memory**: Tracks multi-turn conversational state and resolves pronouns (*"Tata Salt kitna hai?"* -> *"Usme se 5 bech diye"*).
- **Physical Hardware Coordination**: Translates natural appliance commands (*"light on kar"*, *"fan band kar"*) into verified relay channel commands.
- **Automated Communication**: Directly drafts, generates PDF invoices, and sends messages via the official Meta WhatsApp Business Cloud API.
- **Neural Speech Synthesis**: Speaks responses back in natural Indian voice accents using Microsoft Edge Neural TTS.

```
                      +------------------------------------------+
                      |        FastAPI Central Brain             |
                      |   (Render Cloud or Local Laptop/PC)      |
                      +--------------------+---------------------+
                                           |
           +-------------------------------+-------------------------------+
           |                               |                               |
           v                               v                               v
+---------------------+         +---------------------+         +---------------------+
|   🤖 ESP32 Robot    |         |  🌐 Web Admin Panel |         |  📱 WhatsApp Cloud  |
| - Mic Audio / Serial|         | - Live Chat & Audio |         | - Official Meta API |
| - 4-Ch Relay Board  |         | - Knowledge Trainer |         | - PDF Bill Delivery |
| - OLED Display      |         | - Product & Ledger  |         +---------------------+
| - MAX98357A Speaker |         +---------------------+
+---------------------+                    |
           |                               v
           |                    +---------------------+
           +------------------->| PostgreSQL Database |
                                | (Master Truth Store)|
                                +---------------------+
```

---

## 2. Hosting Platforms & Repository Mapping

| Component | Platform / Host | URL / Identifier | Responsibility |
|---|---|---|---|
| **Git Repository** | GitHub | `https://github.com/omkarjadhav1k/robot.git` (branch: `main`) | Source code version control, CI/CD automated deployments. |
| **Central Backend** | Render Cloud Web Service | `https://business-ai-robot-backend.onrender.com` | FastAPI server hosting core business logic, voice orchestration, AI tools. |
| **Primary Database** | Cloud PostgreSQL (Render / Neon) | `postgresql://...` (via `DATABASE_URL`) | Permanent storage of 18 tables: inventory, bills, ledger, instructions. |
| **Test Database** | In-Memory SQLite | `sqlite:///:memory:` | 100% isolated test database used by pytest (55 passing tests). |
| **Conversational AI** | Google Gemini API | `gemini-3.1-flash-lite`, `gemini-flash-latest` | Multilingual NLP, tool selection, reasoning, context memory. |
| **Speech-to-Text (STT)**| Groq Whisper API / Gemini | `whisper-large-v3`, Gemini Multimodal | Voice audio transcribing (`/api/v1/voice/audio/transcribe`). |
| **Text-to-Speech (TTS)**| Microsoft Edge Neural / Google | `hi-IN-MadhurNeural`, `mr-IN-AarohiNeural` | Neural voice synthesis (`/api/v1/voice/audio/tts`). |
| **WhatsApp Messaging** | Meta Developer Graph API v21.0 | `https://graph.facebook.com/v21.0/{PHONE_ID}/messages` | Sends approved utility templates with PDF invoice attachment. |
| **Physical Hardware** | ESP32-WROOM-32 Microcontroller | `ROBOT-001` (C++ Firmware) | I2C OLED, 4 Relays, Status LED, Audio Trigger, Serial Console. |

---

## 3. End-to-End Request Flow

### Complete Sequence Diagram

```
User Spoken Voice / Text
         |
         v
+------------------+
|  ESP32 / Web UI  | ---> POST /api/v1/voice/interact {"text": "...", "robot_id": "ROBOT-001"}
+------------------+
         |
         v
+-------------------------------------------------------------+
| FastAPI Central Brain (voice.py)                           |
|  1. Check Fast-Path Rules (Relays, Rules, Phone Numbers)    |
|  2. Retrieve Session Conversation History (Memory)          |
|  3. Fetch Dynamic Active Learned Instructions from DB       |
|  4. Query Google Gemini AI with Tools & System Persona       |
+-------------------------------------------------------------+
         |
         +----------------------------+
         | Tool Invocation Triggered  | (check_stock / reduce_stock / create_bill / control_relay)
         v                            v
+--------------------+      +--------------------+
| InventoryService   |      | Hardware Dispatch  |
| - Query Stock      |      | - Map "light" -> 1 |
| - Reduce Stock     |      | - Map "fan" -> 2   |
| - Log Audit Trail  |      | - Queue Command    |
+--------------------+      +--------------------+
         |                            |
         +----------------------------+
         |
         v
+-------------------------------------------------------------+
| Response Construction                                       |
|  - Generate Natural Hinglish/Hindi text reply               |
|  - Create TTS Audio Stream URL: /api/v1/voice/audio/tts      |
|  - Sanitize text for ESP32 115200 baud Serial output        |
+-------------------------------------------------------------+
         |
         v
+------------------+
|  ESP32 / Web UI  | <--- JSON Response: {"response_text": "...", "audio_url": "...", "command_dispatched": {...}}
+------------------+
         |
         +---> 1. Switch Physical Relays & Update OLED Screen
         +---> 2. Play Neural Speech MP3 via Speaker or Browser
         +---> 3. Send Execution ACK back to Backend (/commands/{id}/ack)
```

### Turn-by-Turn Real Examples

#### Scenario A: Stock Inquiry with Pronoun Resolution
1. **Turn 1 (User)**: *"Tata Salt ka stock kitna hai?"*
   - Backend calls Gemini tool `check_stock(product_name="Tata Salt")`.
   - `InventoryService.get_stock()` checks PostgreSQL -> returns 37 packets @ ₹28.00.
   - Reply: *"Tata Salt ke 37 packets available hain."*
2. **Turn 2 (User)**: *"Usme se 5 bech diye"*
   - Gemini inspects the previous turn from session history, resolves *"usme se"* -> `Tata Salt`.
   - Gemini invokes `reduce_stock(product_name="Tata Salt", quantity=5.0)`.
   - `InventoryService.reduce_or_sell_stock()` deducts stock to 32.0 and logs `InventoryTransaction(TransactionType.SALE)`.
   - Reply: *"Tata Salt ka stock 5 packet kam kar diya hai. Ab 32 packet bache hain."*

#### Scenario B: Appliance Control
- **User**: *"Robo light on kar"*
  - Backend maps `"light"` -> Relay 1, state `"on"`.
  - Dispatches hardware command `set_relay` (channel 1, on) to ESP32.
  - ESP32 triggers GPIO 26 relay pin to LOW (active-low optocoupler), switches light ON, and replies: *"Relay 1 has been switched on."*

#### Scenario C: Multi-Turn Bill Creation & WhatsApp Dispatch
1. **Turn 1 (User)**: *"Rahul ka 2 chai aur 1 sandwich ka bill bana ke WhatsApp kar do"*
   - Backend checks `Rahul` in database -> finds phone `9876543210`.
   - Calculates items with authoritative database pricing.
   - Generates PDF invoice using `ReportLab`.
   - Calls Meta WhatsApp Cloud API with template `invoice_bill_sent`.
   - Reply: *"Bill INV-20260907-001 of ₹120.00 has been generated and sent to Rahul on WhatsApp."*

---

## 4. Complete Technology Stack & Python Libraries

### Backend Python Stack (`backend/pyproject.toml`)

| Library | Version | Purpose in Project |
|---|---|---|
| **`python`** | `3.11+` / `3.14` | Modern async runtime with high performance and strong typing. |
| **`fastapi`** | `>=0.115.0` | High-performance asynchronous REST API framework with auto OpenAPI documentation. |
| **`uvicorn[standard]`**| `>=0.30.0` | Lightning-fast ASGI web server hosting the FastAPI application. |
| **`sqlalchemy`** | `>=2.0.30` | Modern database ORM for declarative models, joined eager loading, and connection pooling. |
| **`pydantic`** | `>=2.8.0` | Request and response validation, settings parsing, and schema generation. |
| **`pydantic-settings`**| `>=2.4.0` | Environment variables loading from `.env` file and system environment. |
| **`psycopg2-binary`**| `>=2.9.9` | High-performance PostgreSQL database adapter for production. |
| **`httpx`** | `>=0.27.0` | Non-blocking async HTTP client for Google Gemini, Groq, and Meta WhatsApp APIs. |
| **`edge-tts`** | `>=7.0.0` | Neural Indian speech synthesis (Microsoft Edge Neural Hindi/Marathi voices). |
| **`reportlab`** | `>=4.2.0` | Generates official PDF invoices with store branding, itemized tables, and totals. |
| **`jinja2`** | `>=3.1.4` | Server-rendered HTML templating for the Web Admin Console (`admin.html`). |
| **`pytest`** | `>=8.0.0` | Comprehensive test suite runner (55 unit and integration tests). |
| **`pytest-asyncio`**| `>=0.23.0` | Async testing fixture runner for FastAPI and database integration tests. |

### Microcontroller Hardware Stack (`robot/firmware/robot_firmware/`)

| Hardware / Component | Model / Specs | Purpose |
|---|---|---|
| **Microcontroller** | ESP32 DevKit V1 (30-pin, 2.4 GHz Wi-Fi) | Hardware brain, network client, peripheral coordinator. |
| **Relay Module** | 4-Channel 5V Optocoupler Relay Board | Switches high-voltage physical shop appliances (Light, Fan, Socket, Aux). |
| **Display** | 0.96" SSD1306 I2C OLED (128x64) | Real-time status, Wi-Fi IP, AI reply preview, relay states. |
| **Audio Amplifier**| MAX98357A I2S Class D Amp + 4Ω 3W Speaker | Plays neural audio responses spoken by the robot. |
| **Status LED** | Onboard LED / RGB LED (GPIO 2) | Blinks on booting, connects on Wi-Fi, pulses during AI execution. |
| **Serial Console** | 115200 baud USB UART | Development and physical interaction console. |

---

## 5. Complete API Catalog

Base URL:
- **Cloud Mode**: `https://business-ai-robot-backend.onrender.com`
- **Local Wi-Fi Mode**: `http://<YOUR-LAPTOP-IP>:8000`

### 1. Voice & AI Interaction
- **`POST /api/v1/voice/interact`**
  - **Body**: `{"text": "Tata Salt kitna hai?", "robot_id": "ROBOT-001", "conversation_id": "conv_xxx"}`
  - **Returns**: `response_text`, `action_type`, `conversation_id`, `audio_url`, `command_dispatched`, `latencies`.
  - **Function**: Central AI brain endpoint that processes spoken queries, updates database, queues hardware commands, and returns TTS audio link.
- **`GET /api/v1/voice/audio/tts`**
  - **Query Params**: `text=...&lang=hi`
  - **Returns**: `audio/mpeg` MP3 stream.
  - **Function**: Synthesizes natural Indian speech using Microsoft Edge Neural TTS with Google TTS fallback.
- **`POST /api/v1/voice/audio/transcribe`**
  - **Body**: `multipart/form-data` with audio file bytes.
  - **Returns**: `{"text": "transcribed speech"}`.
  - **Function**: Converts spoken mic audio to text using Groq Whisper or Gemini Multimodal.

### 2. Physical Robot Hardware Management
- **`POST /api/v1/robots/{robot_id}/heartbeat`**
  - **Body**: `{"firmware_version": "0.1.0", "wifi_rssi": -65, "relays_state": [1,0,0,0], "uptime_seconds": 120}`
  - **Returns**: `{"acknowledged": true, "pending_commands_count": 0}`.
  - **Function**: Registers robot, reports online status, and notifies if pending hardware commands exist.
- **`GET /api/v1/robots/{robot_id}/commands`**
  - **Query Params**: `status=pending`
  - **Returns**: Array of pending hardware commands to execute.
- **`POST /api/v1/robots/{robot_id}/commands/{command_id}/ack`**
  - **Body**: `{"status": "success", "message": "Relay 1 switched ON", "relays_state": [1,0,0,0]}`
  - **Returns**: `{"acknowledged": true}`.
  - **Function**: Confirms physical hardware execution on the ESP32.
- **`GET /api/v1/robots/{robot_id}/status`**
  - **Returns**: Live telemetry, online status, relay states, and last heartbeat timestamp.

### 3. Web Admin Console & Knowledge Base
- **`GET /admin`**
  - **Returns**: Interactive HTML5 Web Admin Console with live chat, Auto-Speak audio player, instruction trainer, and store ledger.
- **`POST /api/v1/admin/chat`**
  - **Body**: `{"message": "Remember that Ramesh gets 5% discount", "teach_mode": true}`
  - **Returns**: AI reply, rule learning status, tool executed, and `audio_url`.
- **`GET /api/v1/admin/instructions`**
  - **Returns**: List of all learned custom rules and store guidelines stored in PostgreSQL.
- **`POST /api/v1/admin/instructions`**
  - **Body**: `{"instruction": "...", "category": "DISCOUNT|HOURS|POLICY|BEHAVIOR"}`
  - **Returns**: Created instruction object.
- **`PATCH /api/v1/admin/instructions/{id}`**
  - **Body**: `{"is_active": false}` (toggles active rule status).
- **`GET /api/v1/admin/store/products`**
  - **Returns**: Live retail catalog, current stock, selling price, and low-stock warning badges.
- **`GET /api/v1/admin/store/bills`**
  - **Returns**: Generated bills, customer names, payment methods, and timestamps.
- **`POST /api/v1/admin/store/bills/{bill_id}/whatsapp`**
  - **Body**: `{"phone_number": "9876543210"}`
  - **Returns**: Direct WhatsApp dispatch status.

### 4. Health & Documentation
- **`GET /health`**: Health check reporting database connection status and server version.
- **`GET /docs`**: Interactive Swagger UI for testing all API endpoints.
- **`GET /redoc`**: ReDoc API documentation.

---

## 6. Database Schema

All models inherit from SQLAlchemy `Base` with UUID primary keys and multi-tenant `business_id` scoping:

```
+-----------------------------------------------------------------------------------+
| businesses                                                                        |
|  id (UUID PK), name, owner_name, business_type, currency, created_at              |
+-----------------------------------------------------------------------------------+
       | 1
       +-----> N (products)
       |          id, barcode, name, unit, purchase_price, selling_price, current_stock,
       |          minimum_stock, is_active
       |
       +-----> N (inventory_transactions)  [Immutable Audit Trail]
       |          id, product_id, transaction_type (STOCK_IN, SALE, RETURN), quantity,
       |          balance_after, reference_id, notes
       |
       +-----> N (customers)
       |          id, name, phone, email, outstanding_balance, credit_limit
       |
       +-----> N (bills)
       |          id, bill_number, customer_id, subtotal, tax_amount, discount_amount,
       |          total_amount, payment_status, payment_method, source
       |          |
       |          +-----> N (bill_items)
       |                     id, bill_id, product_id, item_name, quantity, unit_price,
       |                     total_price
       |
       +-----> N (brain_instructions)  [Learned Knowledge Base]
       |          id, instruction, category, is_active, source, priority
       |
       +-----> N (ai_activities)  [AI Analytics & Latency Audit]
       |          id, robot_id, user_query, ai_response_text, structured_tool_name,
       |          execution_status, latency_ms
       |
       +-----> N (robots)
                  id, robot_name, is_online, last_heartbeat_at, relays_state
                  |
                  +-----> N (robot_commands)
                             command_id, action, payload, status (pending, executing, executed)
```

---

## 7. Step-by-Step Setup Guide

### Mode A: Ultra-Fast Local Wi-Fi Setup (RECOMMENDED)
*Zero cloud cold starts, zero internet delay, response time **under 1.2 seconds**.*

#### 1. Setup Backend on Laptop/PC
1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd c:\project\Robot\backend
   ```
2. Activate or use the virtual environment:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. Find your Laptop's Local Wi-Fi IP address:
   ```powershell
   ipconfig
   ```
   Look for `IPv4 Address` under your Wi-Fi adapter (e.g. `192.168.1.15`).

#### 2. Configure ESP32 to Local Server
Open `robot/firmware/robot_firmware/config.h` and update:
```cpp
#define WIFI_SSID           "Your_Home_Or_Shop_WiFi"
#define WIFI_PASSWORD       "Your_WiFi_Password"

// Set to your laptop's local IP address and port 8000:
#define BACKEND_BASE_URL    "http://192.168.1.15:8000"
```
Flash the ESP32 via Arduino IDE. Your robot will now communicate directly with your laptop on local Wi-Fi with lightning speed!

---

### Mode B: Production Cloud Deployment

#### 1. Cloud Host (Render)
- The backend repository is linked to GitHub: `https://github.com/omkarjadhav1k/robot.git`.
- Every `git push origin main` triggers an automatic build and deployment on Render.
- Build Command: `pip install -r backend/requirements.txt`
- Start Command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`

#### 2. Required Environment Variables on Render
Configure these in Render Dashboard -> **Environment**:
```env
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
GEMINI_API_KEY=AIzaSy...your-gemini-key
GEMINI_MODEL=gemini-3.1-flash-lite
GROQ_API_KEY=gsk_...your-groq-key
WHATSAPP_TOKEN=EAAG...your-meta-token
WHATSAPP_PHONE_NUMBER_ID=1250939338105560
WHATSAPP_BUSINESS_ACCOUNT_ID=4484629245150675
WHATSAPP_TEMPLATE_NAME=invoice_bill_sent
```

#### 3. Keep-Alive Ping (Preventing Free Tier Cold Starts)
Render free services sleep after 15 minutes of inactivity. To prevent cold starts:
1. Create a free account on [UptimeRobot.com](https://uptimerobot.com).
2. Add an HTTP(s) monitor pointing to:
   `https://business-ai-robot-backend.onrender.com/health`
3. Set the interval to **Every 5 minutes**.
   *Result: The server stays warm 24/7 with zero startup delay.*

---

### ESP32 Firmware Flashing Guide

#### 1. Hardware Pinout Reference
| Component | ESP32 Pin | Details |
|---|---|---|
| **OLED SDA** | GPIO 21 | I2C Data line with pullup |
| **OLED SCL** | GPIO 22 | I2C Clock line with pullup |
| **Relay 1 (Light)** | GPIO 26 | Active-LOW trigger |
| **Relay 2 (Fan)** | GPIO 25 | Active-LOW trigger |
| **Relay 3 (Socket)**| GPIO 33 | Active-LOW trigger |
| **Relay 4 (Aux)** | GPIO 32 | Active-LOW trigger |
| **Status LED** | GPIO 2 | Onboard Blue LED |
| **I2S BCLK (Audio)**| GPIO 14 | MAX98357A Bit Clock |
| **I2S LRC (Audio)** | GPIO 15 | MAX98357A Word Select |
| **I2S DIN (Audio)** | GPIO 13 | MAX98357A Data In |

#### 2. Arduino IDE Setup
1. Install **Arduino IDE** (v2.0+).
2. Add ESP32 Board URL in Preferences:
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Install **esp32 by Espressif Systems** from Boards Manager.
4. Install Library: **U8g2 by olikraus** (for SSD1306 OLED display).
5. Open `robot/firmware/robot_firmware/robot_firmware.ino`.
6. Select Board: **ESP32 Dev Module**, choose the COM port, and click **Upload**.
7. Open Serial Monitor at **115200 baud** to interact.

---

## 8. Troubleshooting & Performance Optimization Guide

| Issue / Symptom | Root Cause | Solution Applied |
|---|---|---|
| `❌ Backend chat error (HTTP -11)` | ESP32 HTTP read timeout occurred while Render was waking up from sleep. | 1. Increased ESP32 timeout from 30s to **45s**.<br>2. Setup UptimeRobot keep-alive or use Local Wi-Fi mode. |
| Response takes 20+ seconds | Google's `gemini-flash-lite-latest` had HTTP 503 high demand; backend was retrying multiple heavy models. | Prioritized `gemini-3.1-flash-lite` and reduced per-model timeout to **4.0s** for instant failover. |
| Garbage characters (``) in Serial | ESP32 Serial terminal running 115200 baud does not support UTF-8 4-byte astral emojis. | Replaced unicode emojis with clean ASCII tags: `[ROBOT AI]`, `[YOU]`, `[AI THINKING]`. |
| WhatsApp bill delivery failure | Meta access token expired or phone number missing international prefix. | Paste a permanent System User Token in Render environment variables or `.env`. Ensure phone numbers are 10 digits starting with 6-9. |

---

## 9. Verification & Test Suite

The entire backend test suite verifies database truth, voice intent parsing, inventory safety, relay mappings, and neural speech synthesis:

```powershell
cd c:\project\Robot\backend
.\.venv\Scripts\python.exe -m pytest
```

**Test Results:**
```
55 passed, 2 warnings in 109.49s (100% SUCCESS)
```
- Stock deduction and audit trails: Verified
- Multi-turn conversational memory: Verified
- Hardware appliance relay mapping: Verified
- PDF bill creation & WhatsApp service: Verified
- Microsoft Edge Neural TTS audio streaming: Verified
