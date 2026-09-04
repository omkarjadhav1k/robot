# Business AI Robot — FINAL Development Plan

## 0. Verified Project State

The latest Antigravity audit confirms that the workspace is currently **Phase 0 / specification stage**. The repository contains the architecture specification, V1 component instructions, and roadmap, but no executable backend, database migrations, ESP32 firmware, or Flutter application yet. fileciteturn1file0L31-L43

The final exhibition target is:

**🤖 Robot + 📱 Phone + ☁️ Cloud Backend + Internet — NO PC**

The PC is only a temporary development tool for the virtual microphone/speaker bridge.

---

## 1. Product Goal

Build a physical AI business assistant/manager for small and medium businesses.

The system should automate repetitive operational work such as:

- voice interaction,
- inventory,
- billing,
- customers,
- payments,
- reminders,
- reports,
- proactive alerts,
- business recommendations,
- physical relay control,
- WhatsApp/customer communication,
- automation.

The product claim should be:

> A digital business manager/assistant that automates routine operational management while the owner remains in control of important and sensitive decisions.

Do not claim that a human manager can always be completely eliminated.

---

## 2. Core Product Differentiator

The project is not merely an AI chatbot.

The differentiation is:

```text
VOICE
 +
BUSINESS DATA
 +
AI
 +
PHYSICAL ROBOT
 +
AUTOMATION
 +
MOBILE APP
 +
ONE SHARED BACKEND
```

Core workflow:

```text
OWNER
  |
  v
VOICE INPUT
  |
  v
SPEECH-TO-TEXT
  |
  v
AI / INTENT ENGINE
  |
  v
STRUCTURED COMMAND
  |
  v
BACKEND VALIDATION + PERMISSIONS
  |
  +------------------------+
  |                        |
  v                        v
BUSINESS SERVICES       ROBOT SERVICES
  |                        |
  v                        v
DATABASE                 ESP32
                            |
                  +---------+---------+
                  |         |         |
                OLED      Speaker    Relay
```

---

## 3. Final Technology Stack

| Layer | Technology |
|---|---|
| Physical controller | ESP32 DevKit V1 |
| Microphone | INMP441 I2S |
| Amplifier | MAX98357A I2S |
| Speaker | 4Ω 3W |
| Display | 0.96" SSD1306 128×64 I2C |
| Controls | 4–5 tactile buttons |
| Actuation | 4-channel 5V relay |
| Backend | Python 3.11+ + FastAPI |
| Validation | Pydantic |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| AI | Google Gemini API |
| Speech | STT + multilingual TTS |
| App | Flutter / Dart |
| Production backend | Google Cloud Run |
| Production DB | Cloud SQL PostgreSQL |
| Messaging | WhatsApp Business Cloud API |
| Development bridge | PC microphone/speaker temporarily |
| Robot transport | HTTPS/REST initially |

The audited architecture independently confirms this stack. fileciteturn1file0L53-L71

---

## 4. One-Brain Architecture

The app and robot must not maintain separate business truth.

```text
              CLOUD BACKEND
                    |
        +-----------+-----------+
        |           |           |
     Gemini     PostgreSQL    Robot API
        |           |           |
        +-----------+-----------+
                    |
          +---------+---------+
          |                   |
        📱 APP              🤖 ROBOT
```

Example:

```text
Robot: "Add 20 kg sugar."
        |
        v
Backend
        |
        v
PostgreSQL: sugar +20 kg
        |
        v
Flutter App: updated stock
```

The audit confirms this shared-state / one-brain principle. fileciteturn1file0L46-L47

---

# 5. Runtime Modes

## 5.1 Development Mode

Current physical audio hardware is pending.

```text
PC Mic
  ↓
Virtual Voice Bridge
  ↓
Backend / Gemini
  ↓
ESP32
  ↓
Relay
  ↓
PC TTS / Speaker
```

The PC must remain replaceable.

## 5.2 Hardware V1

```text
INMP441 → ESP32
ESP32 → MAX98357A → Speaker
ESP32 → OLED
ESP32 → Buttons
ESP32 → Relay
```

## 5.3 Exhibition Mode

```text
🤖 ROBOT
   ↓ Wi-Fi
🌐 INTERNET
   ↓
☁️ CLOUD BACKEND
   ├── Gemini
   ├── PostgreSQL
   ├── Business services
   └── Robot API
        ^
        |
      📱 PHONE APP
```

No PC.

---

# 6. Hardware Baseline

Already available:

```text
ESP32 DevKit V1 ×1
4-channel relay module ×1
ESP32 USB cable ×1
```

V1 components:

```text
INMP441 I2S microphone ×1
MAX98357A I2S amplifier ×1
4Ω 3W speaker ×1
0.96" SSD1306 128×64 I2C OLED ×1
5V 2A regulated adapter ×1
Breadboard ×1–2
M-M jumper set ×1
M-F jumper set ×1
F-F jumper set ×1
Push buttons ×5
```

These procurement items are verified in the Antigravity audit. fileciteturn1file0L233-L247

---

# 7. Provisional ESP32 Pin Map

The audit also records this as **provisional**, not final. fileciteturn1file0L249-L266

```text
OLED SDA         GPIO 21
OLED SCL         GPIO 22

INMP441 BCLK     GPIO 27
INMP441 WS       GPIO 14
INMP441 DATA     GPIO 34

MAX98357A BCLK   GPIO 27
MAX98357A LRC    GPIO 14
MAX98357A DIN    GPIO 13

Relay 1          GPIO 16
Relay 2          GPIO 17
Relay 3          GPIO 18
Relay 4          GPIO 19

Listen Button    GPIO 32
Stop Button      GPIO 33
Confirm Button   GPIO 25
Menu Button      GPIO 26
```

Do not lock this pinout until the physical modules are inspected.

---

# 8. Hardware Safety Rules

The audit identifies four major hardware/architecture risks. fileciteturn1file0L291-L318

## 8.1 Power

Do not power the amplifier/relay loads from an inappropriate ESP32 regulator path.

Target a properly designed 5V external rail.

Use adequate decoupling.

## 8.2 MAX98357A

`SPK+` and `SPK-` are bridged outputs.

Never connect `SPK-` to ground.

## 8.3 Relay Logic

Relay active level must be configurable.

Do not assume active-LOW without testing the actual board.

## 8.4 Shared I2S Clock

The provisional microphone/amplifier design shares BCLK and WS.

For V1, prefer half-duplex:

```text
RECORD
 ↓
STOP
 ↓
PROCESS
 ↓
PLAY
```

Avoid unnecessary full-duplex complexity.

---

# 9. Phase 0 — Workspace Preparation

## Goal

Convert specification-only workspace into a clean development project.

## Tasks

Create:

```text
business-ai-robot/
├── README.md
├── docs/
├── backend/
├── robot/
├── app/
├── deployment/
└── tests/
```

Recommended docs:

```text
docs/
├── PRODUCT_SPEC.md
├── HARDWARE_SPEC.md
├── DEVELOPMENT_PLAN.md
└── ANTIGRAVITY_MASTER_PROMPT.md
```

Create:

```text
.env.example
.gitignore
README.md
```

Do not commit secrets.

## Exit Criteria

- Git works.
- Python environment works.
- Flutter environment works.
- ESP32 toolchain works.
- Documentation is accessible from the repository.

---

# 10. Phase 1 — FastAPI Backend Foundation

## Goal

Create the first executable backend.

Structure:

```text
backend/app/
├── main.py
├── config.py
├── api/
├── models/
├── schemas/
├── services/
├── ai/
├── robot/
├── automation/
├── security/
└── database/
```

First API:

```text
GET /health
```

Then:

```text
GET /robots/{robot_id}/status
POST /robots/{robot_id}/heartbeat
```

Use:

- FastAPI
- Pydantic
- environment configuration
- structured logging
- controlled error responses

## Exit Criteria

```text
GET /health → 200 OK
```

with an automated test.

---

# 11. Phase 2 — PostgreSQL

## Goal

Implement real business persistence.

Core tables:

```text
users
businesses
robots

products
inventory_transactions
suppliers

customers
bills
bill_items
payments

reminders
notifications

business_instructions

ai_activity
robot_commands
audit_logs
```

Every business-owned record should identify its business/tenant.

Use database transactions for important mutations.

---

# 12. Phase 3 — Authentication and Permissions

Implement:

```text
OWNER
STAFF
ROBOT
```

Need:

- authentication,
- RBAC,
- robot identity,
- permission checking,
- audit logging,
- sensitive-action protection,
- secure secret management.

The audited plan explicitly requires secure authentication/authorization and sensitive action protection. fileciteturn1file0L313-L318

Never trust client-side permissions alone.

---

# 13. Phase 4 — Robot Command + Heartbeat API

Implement:

```text
POST /robots/register
POST /robots/{id}/heartbeat
GET  /robots/{id}/status

POST /robots/{id}/commands
POST /robots/{id}/commands/{command_id}/result
```

Command:

```json
{
  "command_id": "cmd_123",
  "robot_id": "ROBOT-001",
  "action": "relay",
  "relay": 1,
  "state": "on"
}
```

Lifecycle:

```text
PENDING
→ VALIDATED
→ SENT
→ RECEIVED
→ EXECUTING
→ SUCCESS / FAILED
```

Use command IDs to make retries/idempotency safe.

---

# 14. Phase 5 — ESP32 Base Firmware

Responsibilities:

- Wi-Fi
- authentication
- heartbeat
- command reception
- relay control
- safe startup
- reconnect logic
- hardware state

Firmware should use a clear non-blocking state machine.

Initial state flow:

```text
BOOT
→ WIFI_CONNECTING
→ BACKEND_CONNECTING
→ READY
```

---

# 15. Milestone 1 — Voice Relay Control

This is the first real vertical slice.

```text
PC Mic
 ↓
STT
 ↓
Gemini
 ↓
Structured command
 ↓
FastAPI validation
 ↓
ESP32
 ↓
Relay
 ↓
PC TTS
```

Example:

> "Robot, turn on relay one."

Expected:

```text
Speech captured
→ understood
→ validated
→ relay 1 ON
→ confirmation
```

Do not proceed to advanced business functionality until this works.

---

# 16. Phase 6 — Virtual Voice Bridge

Build:

```text
backend/virtual_voice/
├── microphone.py
├── speech_to_text.py
├── text_to_speech.py
└── main.py
```

This allows development now while the physical audio components are in transit.

The audit confirms this bridge is specifically missing and should be built as a temporary development component. fileciteturn1file0L337-L340

---

# 17. Phase 7 — Gemini Intent Engine

Gemini should convert natural language into approved structured actions.

Example:

```json
{
  "type": "action",
  "action": "relay",
  "relay": 1,
  "state": "on"
}
```

Approved tool/action families:

```text
get_business_summary
get_product_stock
add_inventory
reduce_inventory
create_bill
get_bill
get_customer
get_customer_balance
record_payment
create_reminder
get_reminders
get_reports
control_relay
get_robot_status
```

AI output must pass:

```text
Schema validation
→ Permission check
→ Business validation
→ Execution
```

Never:

```text
Gemini
→ SQL
→ database
```

or:

```text
Gemini
→ GPIO
```

---

# 18. Phase 8 — Real Audio Hardware

When delivery arrives:

```text
INMP441
→ ESP32 I2S input

ESP32
→ MAX98357A
→ 4Ω 3W speaker
```

First implement half-duplex operation.

Test:
- microphone capture,
- audio quality,
- speaker output,
- gain,
- clipping,
- long-duration stability.

---

# 19. Phase 9 — OLED + Buttons + Robot State UI

OLED states:

```text
BOOT
WIFI CONNECTING
BACKEND CONNECTING
READY
LISTENING
THINKING
EXECUTING
SPEAKING
OFFLINE
ERROR
```

Buttons:

```text
Listen
Stop / Cancel
Confirm
Menu
Spare
```

Buttons must have software debouncing.

---

# 20. Phase 10 — Robot Name Activation

The robot must not respond to normal conversations.

```text
Normal speech
→ IGNORE

"ROBOT_NAME, ..."
→ WAKE
→ LISTEN
→ PROCESS
```

Push-to-talk remains a reliable fallback.

The robot name must be configurable.

---

# 21. Phase 11 — Business Instruction TXT

Owner can upload:

```text
business_instructions.txt
```

Example:

```text
Business Name: Example Store
Business Type: Grocery
Working Hours: 8 AM - 9 PM
Minimum Sugar Stock: 20 kg
Credit allowed only for regular customers.
Owner language: Marathi
```

Flow:

```text
Upload
→ validate
→ store
→ business context
→ AI request
```

The uploaded file is context only.

It cannot override security, permissions or data-integrity rules.

---

# 22. Phase 12 — Inventory

Core:

```text
Product list
Add product using barcode
Edit product
Add stock
Reduce stock
Current stock
Minimum stock
Low-stock alerts
Stock history
Supplier information
Purchase history
Reorder suggestion
```

Every stock mutation creates an inventory transaction.

The audited feature specification confirms this inventory scope. fileciteturn1file0L215-L217

---

# 23. Phase 13 — Billing

Core:

```text
Create bill
Add products
Quantity
Database prices
Calculate totals
Generate invoice
Billing history
Robot voice billing
```

Useful later:

```text
GST
Discount
PDF
Print
Digital sending
Cancel/refund
```

Critical rule:

**Prices and totals come from deterministic backend/database logic, not Gemini.**

This is explicitly identified as a project risk and mitigation. fileciteturn1file0L313-L318

---

# 24. Phase 14 — Customers

Build:

```text
Customer
├── name
├── phone
├── bills
├── purchase history
├── payments
├── outstanding balance
└── optional notes/preferences
```

---

# 25. Phase 15 — Payments

Core:

```text
Record payment
Pending payments
Payment history
Outstanding balance
```

Payment mutations must be:

```text
Authenticated
Authorized
Transactional
Idempotent
Audited
```

---

# 26. Phase 16 — Reminders

Core:

```text
Create
View
Complete/delete
Voice-created reminders
Due notifications
```

Useful:

```text
Recurring reminders
AI suggestions
```

Future:

```text
Routine learning
```

---

# 27. Phase 17 — Reports

Core:

```text
Daily sales
Weekly sales
Inventory
Pending payments
AI business summary
```

Useful:

```text
Monthly sales
Profit
Product sales
Customer report
Charts
AI recommendations
```

The database provides the numbers. AI explains them.

---

# 28. Phase 18 — Automation Engine

Core deterministic workflows:

```text
SALE CREATED
→ INVENTORY REDUCTION

BILL CREATED
→ CUSTOMER HISTORY UPDATE

PAYMENT CREATED
→ BALANCE UPDATE

LOW STOCK
→ OWNER ALERT
```

Later:

```text
Daily closing
Purchase list
AI-created workflows
Custom IF/THEN
```

Do not let AI directly execute arbitrary workflow code.

---

# 29. Phase 19 — Proactive Manager

The system should surface meaningful actionable issues:

```text
Low stock
Pending/overdue payment
Important reminder
Daily summary
```

Example:

> "Oil stock is below your configured minimum. Add it to the purchase list?"

Avoid notification spam.

---

# 30. Phase 20 — Multi-Action Commands

Support controlled multi-step commands.

Example:

> "Add 20 kg sugar and tell me what is below minimum stock."

Backend:

```text
Find sugar
→ validate
→ add stock
→ transaction record
→ check thresholds
→ response
```

Another:

> "Create Rahul's bill and record his payment."

Backend:

```text
Find customer
→ identify items
→ fetch DB prices
→ verify stock
→ create bill
→ reduce stock
→ record payment
→ calculate balance
→ respond
```

These should be backend workflows, not arbitrary model-generated execution.

---

# 31. Phase 21 — Flutter App

Build the visual control center after backend APIs are stable.

Screens:

```text
Dashboard
Robot
Inventory
Billing
Customers
Payments
Reminders
Reports
WhatsApp
Automation
Settings
```

Do not create a second local business database inside Flutter.

---

# 32. Phase 22 — App Security

Server must enforce:

```text
Who is the user?
What role do they have?
What action are they allowed to perform?
```

Client-side restrictions are UI only.

---

# 33. Phase 23 — WhatsApp

Add only after billing and customer workflows are stable.

Initial:

```text
Send invoice
Payment reminder
Order confirmation
Customer inquiry
AI-generated replies
```

Use the official WhatsApp Business API.

---

# 34. Phase 24 — Cloud Deployment

Production target:

```text
Google Cloud Run
+
Cloud SQL PostgreSQL
```

Final architecture:

```text
🤖 ESP32
  ↓
HTTPS
  ↓
☁️ Cloud Run
  ├── Gemini
  ├── Cloud SQL
  ├── Business services
  └── Robot API
       ^
       |
📱 Flutter
```

PC is removed from runtime.

The audit's final roadmap explicitly makes Cloud Run + managed PostgreSQL the production target. fileciteturn1file0L71-L71

---

# 35. Phase 25 — Robot Provisioning

Each robot needs:

```text
robot_id
business_id
backend URL
robot authentication
Wi-Fi configuration
robot name
language
```

Do not embed production secrets in public firmware.

---

# 36. Phase 26 — Failure Handling

Test:

```text
Wi-Fi failure
Backend failure
Gemini failure
Database failure
Robot reboot
Microphone failure
Speaker failure
Duplicate command
```

Robot should retry safely, display status and never falsely claim success.

---

# 37. Phase 27 — Data Integrity

Important operations must be transactional.

### Billing

Do not allow:

```text
bill created
+
inventory reduced
+
customer update missing
```

unless the transaction is safely handled.

### Payments

Prevent duplicate payment processing.

### Robot

Prevent duplicate execution of the same command ID.

---

# 38. Phase 28 — Observability

Provide:

```text
/health
structured logs
robot heartbeat
command logs
AI activity
audit logs
error logs
```

Owner-facing status example:

```text
Robot Offline
Reason: Wi-Fi disconnected
Last heartbeat: 18:42:21
```

---

# 39. Phase 29 — Full Testing

### Unit
- calculations
- permissions
- stock
- bills
- balances
- automation
- command validation

### Integration
- Backend ↔ PostgreSQL
- Backend ↔ Gemini
- Backend ↔ Robot
- App ↔ Backend

### End-to-end
- Voice → business action
- Voice → physical action
- App → backend → robot

---

# 40. Phase 30 — Hardware Reliability

Run repeated cycles and long tests:

```text
1 hour
4 hours
8 hours
```

Test:

```text
Listen
Process
Speak
Relay
Reconnect
Restart
```

Watch for:
- brownouts,
- audio distortion,
- freezes,
- Wi-Fi instability,
- relay failures,
- thermal issues.

---

# 41. Phase 31 — Security Audit

Verify:

```text
No secrets in Git
No public unrestricted robot endpoints
No raw SQL from AI
No arbitrary shell access
No unauthorized robot commands
No privilege escalation
No cross-business data leakage
Sensitive actions protected
Audit logs exist
```

---

# 42. Phase 32 — Exhibition Preparation

Target:

```text
🤖 Robot
📱 Phone
🌐 Wi-Fi / Internet
☁️ Cloud Backend
🧠 Gemini
🗄️ Database
```

No PC.

Prepare:
- production build,
- demo business data,
- robot credentials,
- cloud deployment,
- backup hotspot/Wi-Fi plan,
- spare cables,
- power backup,
- architecture poster,
- fixed demo script.

---

# 43. Phase 33 — Exhibition Demo

Recommended sequence:

### Demo 1
Introduce the robot.

### Demo 2
Ask:

> "Robot, how much sugar is left?"

### Demo 3
Ask:

> "Robot, turn on relay one."

### Demo 4
Ask:

> "Robot, create a bill for Rahul for five kg sugar and two kg rice."

### Demo 5
Ask:

> "How was business today?"

### Demo 6
Show a proactive low-stock/payment/reminder alert.

### Demo 7
Show the phone app and demonstrate that it contains the same updated business data.

---

# 44. Phase 34 — Product Polish

Only after the system is stable:

- final enclosure,
- clean wiring,
- polished OLED,
- polished app,
- improved audio,
- better error messages,
- startup sequence,
- exhibition branding.

Do not polish broken functionality.

---

# 45. Phase 35 — Documentation

Keep:

```text
README
Product specification
Hardware specification
Pinout
Wiring
API documentation
Database documentation
Setup guide
Deployment guide
Security guide
Testing guide
Troubleshooting guide
Exhibition guide
```

---

# 46. Phase 36 — Final Acceptance

## Robot

- [ ] Boot
- [ ] Wi-Fi
- [ ] Backend authentication
- [ ] Heartbeat
- [ ] Relay
- [ ] Mic
- [ ] Speaker
- [ ] OLED
- [ ] Buttons
- [ ] Robot-name activation
- [ ] Recovery

## AI

- [ ] English
- [ ] Hindi
- [ ] Marathi
- [ ] Natural language
- [ ] Structured tool output
- [ ] Business context
- [ ] TXT instructions
- [ ] Sensitive-action protection

## Business

- [ ] Inventory
- [ ] Billing
- [ ] Customers
- [ ] Payments
- [ ] Reminders
- [ ] Reports
- [ ] Automation

## App

- [ ] Login
- [ ] Dashboard
- [ ] Inventory
- [ ] Billing
- [ ] Customers
- [ ] Payments
- [ ] Reminders
- [ ] Reports
- [ ] Robot
- [ ] Settings

## Production

- [ ] Cloud deployment
- [ ] PostgreSQL
- [ ] Secure APIs
- [ ] Backup
- [ ] Audit
- [ ] Monitoring
- [ ] WhatsApp where used
- [ ] PC not required

---

# 47. Current Exact Starting Point

The audit verifies:

```text
Specifications        ✅
Hardware plan         ✅
Roadmap               ✅

Backend               ❌
Database              ❌
ESP32 firmware        ❌
Voice pipeline        ❌
Flutter app           ❌
Cloud deployment      ❌
```

The immediate work is therefore:

```text
PHASE 0
 ↓
PHASE 1 FastAPI
 ↓
PHASE 2 PostgreSQL
 ↓
PHASE 3 Security
 ↓
PHASE 4 Robot API
 ↓
PHASE 5 ESP32
 ↓
MILESTONE 1
```

---

# 48. Definition of Done for Milestone 1

A milestone is complete only if:

```text
PC microphone
    ↓
Speech-to-text
    ↓
Gemini
    ↓
validated command
    ↓
FastAPI
    ↓
ESP32
    ↓
physical Relay 1
    ↓
success acknowledgment
    ↓
spoken confirmation
```

This is the first demonstration that the architecture actually works end-to-end.

