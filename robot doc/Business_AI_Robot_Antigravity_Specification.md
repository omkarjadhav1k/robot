# Business AI Robot — Antigravity Development Specification

## 0. Document Purpose

This document is the single implementation specification for the Business AI Robot project.

It is intended to be given to an AI coding/development agent (referred to here as "Antigravity") so that the agent understands:
- what the product is,
- why it exists,
- how the robot works,
- how the ESP32, backend, database, AI and mobile app interact,
- what must be implemented,
- what must NOT be implemented yet,
- how to structure the code,
- how to test each module,
- and what the final exhibition system must look like.

Important development rule:
**Do not replace the architecture with a different stack unless explicitly approved.**
Build the system incrementally and keep interfaces modular.

---

# 1. Product Definition

## 1.1 Product Name

Business AI Robot

Working concept:
**A 24/7 digital business assistant/manager that combines voice interaction, business software, AI reasoning and physical IoT control.**

## 1.2 Product Goal

The robot is intended to automate repetitive operational work normally handled by a small-business manager, while keeping the owner in control of important or sensitive decisions.

The product should allow the owner to talk naturally to the robot for business tasks such as:
- checking stock,
- adding stock,
- creating a bill,
- checking customer balances,
- recording payments,
- creating reminders,
- asking for sales summaries,
- receiving proactive alerts,
- controlling connected hardware,
- and receiving business recommendations.

The robot is NOT intended to claim that a human manager is unnecessary in every situation. The correct product position is:
**automate repetitive operational management and act as a digital manager assistant.**

---

# 2. Core Differentiator

The product is not unique merely because it uses AI.

The differentiator is the combination of:

1. Natural voice interaction
2. Business context and memory
3. Business database
4. Voice-to-business actions
5. Voice-to-physical actions
6. Proactive alerts
7. Multi-step workflows
8. Mobile business-management app
9. Physical ESP32 robot
10. One shared backend/database ("one brain")

The core idea:

```text
OWNER SPEAKS
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
    +---------------------+
    |                     |
    v                     v
BUSINESS SERVICES      ROBOT SERVICES
    |                     |
    v                     v
DATABASE             ESP32 / HARDWARE
    |
    v
VOICE RESPONSE / APP UPDATE
```

---

# 3. Final System Architecture

```text
                         INTERNET
                            |
                  +---------v---------+
                  |  CLOUD BACKEND   |
                  |                  |
                  | FastAPI          |
                  | AI service       |
                  | Business logic   |
                  | Auth             |
                  | Automation       |
                  | Robot API        |
                  +---------+--------+
                            |
              +-------------+-------------+
              |                           |
          HTTPS / API                HTTPS / API
              |                           |
      +-------v-------+           +-------v-------+
      |   MOBILE APP  |           |   ESP32 ROBOT |
      |    Flutter    |           |               |
      +---------------+           | Mic           |
                                  | Speaker       |
                                  | OLED          |
                                  | Buttons       |
                                  | Relay         |
                                  +---------------+
```

## 3.1 Shared Brain Principle

The mobile app and robot MUST NOT maintain separate business databases.

Both must use the same backend and business database.

Example:

```text
Robot: "Add 20 kg sugar"
        |
        v
Backend
        |
        v
Database: Sugar stock +20 kg
        |
        +--> App automatically shows new stock
```

---

# 4. Runtime Modes

## 4.1 Development Mode (current)

Physical microphone and speaker are pending delivery.

Use:

```text
PC Microphone
    |
    v
PC Voice Service
    |
    v
Gemini / Backend
    |
    v
ESP32
    |
    v
Relay
    |
    v
PC Speaker / TTS
```

The PC is temporary development infrastructure.

## 4.2 Hardware V1

When components arrive:

```text
INMP441 -> ESP32
ESP32 -> MAX98357A -> Speaker
ESP32 -> OLED
ESP32 -> Buttons
ESP32 -> Relay
```

## 4.3 Exhibition / Production Mode

The PC must not be required.

```text
ROBOT
  |
  | Wi-Fi
  v
INTERNET
  |
  v
CLOUD BACKEND
  |
  +--> Gemini
  +--> Database
  +--> Business services
  |
  +<-> MOBILE APP
```

The exhibition system must work with:
- Robot
- Phone
- Internet/Wi-Fi
- Cloud backend
- AI API
- Database

No development PC.

---

# 5. Hardware Specification

## 5.1 Current Hardware

Already available:
- ESP32 DevKit V1
- 4-channel relay module
- ESP32 USB cable

## 5.2 V1 Hardware / Pending Delivery

- INMP441 I2S microphone
- MAX98357A I2S amplifier
- 4 ohm 3W speaker
- 5V 2A power adapter
- Breadboard
- Jumper wires
- 0.96 inch SSD1306 OLED
- 3-5 push buttons

Motors/movement/sensors are intentionally skipped for V1.

---

# 6. Robot Responsibilities

The ESP32 is the physical controller, not the place where Gemini runs.

The ESP32 must handle:
- Wi-Fi connection
- device identity
- secure backend communication
- microphone input
- speaker output
- OLED display
- buttons
- relay control
- health/heartbeat reporting
- local state management
- safe fallback behavior
- command acknowledgment

The backend must handle:
- authentication
- AI
- speech services where applicable
- business database
- business logic
- permissions
- automation
- reporting
- integrations

---

# 7. ESP32 Hardware Pin Plan

The following is a **provisional starting pin map**. It MUST be verified against the actual hardware modules before final wiring and firmware lock.

| Component | ESP32 Pin |
|---|---|
| OLED SDA | GPIO 21 |
| OLED SCL | GPIO 22 |
| INMP441 BCLK | GPIO 27 |
| INMP441 WS/LRCLK | GPIO 14 |
| INMP441 DATA | GPIO 34 |
| MAX98357A BCLK | GPIO 27 |
| MAX98357A LRC | GPIO 14 |
| MAX98357A DATA | GPIO 13 |
| Relay 1 | GPIO 16 |
| Relay 2 | GPIO 17 |
| Relay 3 | GPIO 18 |
| Relay 4 | GPIO 19 |
| Listen button | GPIO 32 |
| Stop button | GPIO 33 |
| Confirm button | GPIO 25 |
| Menu button | GPIO 26 |

### Important hardware rules

1. Do not assume the relay module input/power arrangement.
2. Verify whether the relay board is active-LOW or active-HIGH before final firmware.
3. Do not connect speaker terminals to GND when using a bridged MAX98357A output.
4. INMP441 logic power should use the appropriate 3.3V supply.
5. Final power wiring must be designed so the amplifier/relay load does not brown-out/reset the ESP32.
6. Pin conflicts must be rechecked when the real modules are assembled.

---

# 8. Robot State Machine

The robot must use explicit states instead of uncontrolled blocking loops.

Recommended states:

```text
BOOT
  |
  v
WIFI_CONNECTING
  |
  v
BACKEND_CONNECTING
  |
  v
READY / IDLE
  |
  +--> LISTENING
  |
  +--> PROCESSING
  |
  +--> EXECUTING
  |
  +--> SPEAKING
  |
  +--> ERROR
```

Additional state:
`OFFLINE_FALLBACK`

## 8.1 State meaning

### BOOT
Initialize hardware and configuration.

### WIFI_CONNECTING
Connect to configured Wi-Fi.

### BACKEND_CONNECTING
Authenticate with backend and register/heartbeat.

### READY
Robot is ready to receive a command.

### LISTENING
Capture user speech.

### PROCESSING
Wait for speech processing/AI result.

### EXECUTING
Execute validated business or hardware action.

### SPEAKING
Play response audio.

### ERROR
Display/report error and recover safely.

### OFFLINE_FALLBACK
Use limited local commands and explain that cloud AI is unavailable.

---

# 9. Voice Interaction

## 9.1 Primary Interaction

The robot is voice-first.

Text chat is NOT a primary product feature.

The user can:
- press a listen button,
- or use robot-name activation.

## 9.2 Robot Name Activation

The robot should not react to normal background conversation.

Expected behavior:

```text
People talking
    -> Ignore

"ROBOT_NAME, turn on relay one."
    -> Wake
    -> Listen
    -> Process
```

The actual robot name will be configurable.

## 9.3 Push-to-Talk

Push-to-talk is required as the reliable fallback.

Button flow:

```text
Press Listen
    |
    v
Listening
    |
    v
Capture command
    |
    v
Process
```

## 9.4 Languages

Initial language targets:
- English
- Hindi
- Marathi

The app should allow selection of robot speaking language.

---

# 10. Voice Pipeline

```text
Microphone
   |
   v
Audio capture
   |
   v
Speech-to-text
   |
   v
User text
   |
   v
Intent / AI service
   |
   v
Structured action OR answer
   |
   v
Business/robot execution
   |
   v
Text response
   |
   v
Text-to-speech
   |
   v
Speaker
```

During development, PC microphone and PC speaker may temporarily replace the physical audio hardware.

---

# 11. AI Architecture

## 11.1 Gemini's Role

Gemini should:
- understand natural language,
- identify user intent,
- extract entities,
- choose approved tools/actions,
- explain business information,
- generate conversational responses,
- use business context when answering.

Gemini should NOT:
- directly execute SQL,
- directly control GPIO,
- directly write arbitrary files,
- bypass permissions,
- be treated as the database source of truth,
- invent prices or stock values.

## 11.2 Structured Command Principle

Natural language:

> "Turn on the first relay."

AI output:

```json
{
  "type": "action",
  "action": "relay",
  "relay": 1,
  "state": "on"
}
```

Backend validates the structure before execution.

---

# 12. Business AI Tool/Action Layer

Recommended controlled actions:

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

The actual list can grow, but every action must have:
- schema,
- permission requirements,
- validation,
- audit behavior,
- expected result,
- error behavior.

---

# 13. Business Instruction TXT File

The owner can upload a business instruction `.txt` file.

Example:

```text
Business Name: Example General Store
Business Type: Grocery

Working Hours: 8 AM - 9 PM

Minimum Sugar Stock: 20 kg
Minimum Rice Stock: 30 kg

Credit is allowed only for regular customers.

Payment reminders should be created after 3 days overdue.

Owner prefers Marathi voice responses.
```

Purpose:
- customize AI context,
- teach business-specific rules,
- configure preferences,
- provide operational guidance.

The file is business configuration/context, not a security bypass.

The backend must sanitize/validate uploaded content and never allow the file to override code-level permissions.

---

# 14. Business Modules

## 14.1 Inventory

Core:
- Product list
- Add product using barcode
- Edit product
- Add stock
- Reduce stock
- Current stock
- Minimum stock
- Low stock alert
- Stock history
- Supplier information
- Purchase history
- Reorder suggestion

Future:
- richer barcode/QR workflows

### Inventory rule

Every stock change must create an inventory transaction record.

Never silently mutate stock without history.

---

# 15. Billing

Core:
- Create bill
- Add products
- Quantity
- Price from database
- Total calculation
- Generate invoice
- Billing history
- AI voice billing through robot

Useful:
- GST/tax
- discount
- print
- PDF
- digital sharing
- cancellation/refund

### Billing rule

Never let the model invent authoritative prices.

Price must come from the business database.

Example:

```text
Owner speech
 -> identify customer
 -> identify products
 -> retrieve prices from DB
 -> calculate totals in backend
 -> create bill
 -> update inventory
 -> update customer history
 -> record payment/outstanding
 -> respond
```

---

# 16. Customer Management

Core:
- Customer list
- Add customer
- Edit customer
- Purchase history
- Pending balance
- Payment history
- Top customers
- AI customer insights

Optional:
- customer notes
- preferences

---

# 17. Payments

Core:
- Record payment
- Pending payments
- Payment history
- Outstanding balance

Later:
- online payments
- automatic payment reconciliation

Payment updates must be transactional and auditable.

---

# 18. Reminders

Core:
- Create reminder
- View reminders
- Complete/delete reminder
- Voice-created reminders
- Due-task notifications

Useful:
- recurring reminders
- AI suggested reminders

Future:
- pattern learning / repeated routine detection

---

# 19. Reports

Core:
- Daily sales
- Weekly sales
- Inventory report
- Pending payment report
- AI-generated business summary

Useful:
- Monthly sales
- Profit report
- Product report
- Customer report
- charts
- AI recommendations

The database is the source of truth. AI only explains/analyzes the data.

---

# 20. Automation Engine

Core workflows:

```text
LOW STOCK
  -> alert owner

SALE CREATED
  -> reduce inventory

BILL CREATED
  -> update customer history

PAYMENT CREATED
  -> update outstanding balance
```

Useful:
- due reminder -> notification
- daily closing
- purchase list generation

Future:
- AI-created workflows
- custom IF/THEN automation

Automation must be deterministic where possible.

---

# 21. Proactive Manager Behavior

The robot should proactively notify the owner about meaningful business events.

Examples:
- low stock,
- pending payment,
- overdue payment,
- important reminder,
- daily business summary.

The system should avoid noisy notifications.

Recommended rule:
**notify when the event is meaningful and actionable.**

---

# 22. Multi-Action Command Handling

The AI should be capable of turning one natural-language instruction into a validated workflow.

Example:

> "Add 20 kg sugar and tell me what is now below minimum stock."

Workflow:

```text
1. Find sugar
2. Validate unit
3. Add stock
4. Record inventory transaction
5. Recalculate stock state
6. Check all minimum-stock rules
7. Return results
```

Another example:

> "Make Rahul's bill and record his payment."

Workflow:

```text
1. Identify Rahul
2. Create bill
3. Calculate price from DB
4. Create bill record
5. Update inventory
6. Record payment
7. Recalculate balance
8. Return confirmation
```

These workflows should be implemented as backend services, not as free-form model behavior.

---

# 23. Mobile App

Technology:
**Flutter**

The app is the owner's visual business control center.

## Main sections

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

## Dashboard

Show:
- today's sales,
- orders/transactions,
- pending payments,
- low-stock alerts,
- important notifications,
- robot online/offline state.

## Robot screen

Show:
- online/offline,
- microphone status,
- speaker status,
- OLED state,
- relay state,
- diagnostics,
- remote controls where permitted.

---

# 24. WhatsApp

Later integration layer.

Useful capabilities:
- send invoice,
- payment reminder,
- order confirmation,
- customer inquiry handling,
- AI-generated replies.

Future:
- automated WhatsApp workflows,
- promotions.

WhatsApp integration must respect the platform's official API and messaging rules.

---

# 25. Authentication and Permissions

Roles:

```text
OWNER
STAFF
```

The system must be ready for multiple users even if initial deployment has one owner.

Every sensitive action requires:
- authentication,
- permission check,
- validation,
- audit record.

Examples of sensitive actions:
- deleting important records,
- changing financial/business configuration,
- destructive operations,
- changing permissions.

---

# 26. Robot Security

Each robot must have a unique identity.

Example:

```text
ROBOT-001
```

The backend maps the robot to its business/tenant.

Robot requests should be authenticated.

Do NOT:
- expose uncontrolled public GPIO endpoints,
- embed unrestricted Gemini/API secrets in firmware,
- trust arbitrary commands,
- trust arbitrary AI-generated SQL,
- allow a client to impersonate a robot.

---

# 27. Backend API Principles

Use REST/HTTPS initially.

Suggested endpoints:

```text
GET  /health

POST /auth/login

POST /robots/register
POST /robots/heartbeat
GET  /robots/{robot_id}/status

POST /robots/{robot_id}/commands
POST /robots/{robot_id}/commands/{command_id}/result

POST /ai/process

GET  /products
POST /products
PATCH /products/{id}

POST /inventory/transactions
GET  /inventory

POST /customers
GET  /customers
GET  /customers/{id}

POST /bills
GET  /bills
GET  /bills/{id}

POST /payments
GET  /payments

POST /reminders
GET  /reminders

GET  /reports/daily
GET  /reports/weekly
GET  /reports/monthly

POST /business/instructions
GET  /business/instructions

GET  /audit
```

These are logical API contracts; exact route naming can be normalized during implementation.

---

# 28. Robot Command Lifecycle

Use an explicit command lifecycle.

```text
PENDING
  |
  v
VALIDATED
  |
  v
SENT
  |
  v
RECEIVED
  |
  v
EXECUTING
  |
  v
SUCCESS / FAILED
```

Example:

```json
{
  "command_id": "cmd_123",
  "robot_id": "ROBOT-001",
  "action": "relay",
  "relay": 1,
  "state": "on"
}
```

Robot responds:

```json
{
  "command_id": "cmd_123",
  "status": "success",
  "message": "relay_1_on"
}
```

The backend must handle duplicate/retry cases safely.

---

# 29. Heartbeat

Robot periodically reports health.

Example:

```json
{
  "robot_id": "ROBOT-001",
  "wifi": "connected",
  "backend": "connected",
  "mic": "ok",
  "speaker": "ok",
  "oled": "ok",
  "relay": "ok",
  "firmware": "0.1.0"
}
```

Backend stores:
- last heartbeat,
- online state,
- firmware version,
- health status.

---

# 30. Offline/Fallback Mode

Cloud AI cannot be guaranteed during an exhibition.

The robot must degrade gracefully.

Possible local fallback:
- relay ON/OFF for approved local commands,
- display system state,
- basic button functions,
- show "Cloud unavailable",
- retry connection.

The robot should not freeze merely because Gemini/backend is temporarily unavailable.

---

# 31. Database Design

Core entities:

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

Relationships:

```text
Business
 ├── Users
 ├── Robots
 ├── Products
 ├── Customers
 ├── Bills
 ├── Payments
 ├── Reminders
 └── Instructions
```

Every important business record should belong to a business/tenant ID.

---

# 32. Multi-Tenant Design

Even if the first demo uses one business, build with a business/tenant identifier.

Example:

```text
business_id = BUSINESS_001
robot_id = ROBOT_001
```

This makes future branch/multiple-business support possible without redesigning the core database.

---

# 33. Audit Logging

Record:
- user,
- robot,
- action,
- timestamp,
- source,
- status,
- relevant entity,
- result/error.

Example:

```text
18:20:21
Owner
Robot ROBOT-001
ADD_INVENTORY
Sugar +20 kg
SUCCESS
```

---

# 34. Error Handling

Every layer must return controlled errors.

Examples:

```text
UNKNOWN_PRODUCT
INSUFFICIENT_STOCK
CUSTOMER_NOT_FOUND
PERMISSION_DENIED
ROBOT_OFFLINE
AI_UNAVAILABLE
INVALID_COMMAND
DUPLICATE_COMMAND
NETWORK_ERROR
```

Errors must be:
- logged,
- human-readable,
- recoverable where possible,
- safe.

---

# 35. Development Repository Structure

Recommended:

```text
business-ai-robot/
│
├── README.md
├── docs/
│   └── ANTIGRAVITY_SPEC.md
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── security/
│   │   ├── automation/
│   │   └── ai/
│   ├── tests/
│   └── requirements.txt
│
├── robot/
│   ├── firmware/
│   │   ├── main/
│   │   ├── hardware/
│   │   ├── network/
│   │   ├── audio/
│   │   ├── display/
│   │   ├── commands/
│   │   └── config/
│   └── tests/
│
├── app/
│   └── flutter_app/
│
└── deployment/
    ├── Dockerfile
    └── cloud/
```

---

# 36. Development Order

DO NOT attempt all features simultaneously.

## Phase 0 — Foundation

Deliver:
- repository,
- environment,
- configuration,
- Git,
- basic README.

## Phase 1 — Backend

Deliver:
- FastAPI,
- `/health`,
- configuration,
- structured logging.

## Phase 2 — Database

Deliver:
- schema,
- migrations,
- core CRUD.

## Phase 3 — Security

Deliver:
- authentication,
- authorization,
- robot identity,
- audit log.

## Phase 4 — Robot API

Deliver:
- robot registration,
- heartbeat,
- command,
- result acknowledgment.

## Phase 5 — ESP32 Base

Deliver:
- Wi-Fi,
- secure backend connection,
- heartbeat,
- relay control.

## Phase 6 — Virtual Voice

Deliver:
- PC microphone,
- speech-to-text,
- AI processing,
- ESP32 command,
- PC text-to-speech.

This is the current development target because physical audio parts are pending.

## Phase 7 — Real Audio Hardware

Deliver:
- INMP441,
- I2S capture,
- MAX98357A,
- speaker playback.

## Phase 8 — Robot UI

Deliver:
- OLED states,
- buttons,
- error displays.

## Phase 9 — AI Context

Deliver:
- business instruction file,
- structured tools,
- business context.

## Phase 10 — Inventory

Deliver complete core inventory workflow.

## Phase 11 — Billing

Deliver complete core billing workflow.

## Phase 12 — Customers

Deliver customer records/history/balance.

## Phase 13 — Payments

Deliver payment records and balances.

## Phase 14 — Reminders

Deliver reminders and notifications.

## Phase 15 — Reports

Deliver daily/weekly/business summaries.

## Phase 16 — Automation

Deliver deterministic workflows and proactive alerts.

## Phase 17 — Flutter App

Build app on stable backend APIs.

## Phase 18 — WhatsApp

Add official API integration.

## Phase 19 — Cloud Deployment

Deploy backend and database.

## Phase 20 — Exhibition Hardening

Test:
- Wi-Fi failure,
- backend failure,
- AI failure,
- robot reconnect,
- duplicate commands,
- power restart,
- long runtime,
- security,
- demo sequence.

---

# 37. Current First Milestone

The immediate target is NOT inventory or billing.

The immediate target is:

```text
PC / temporary voice
       |
       v
AI command understanding
       |
       v
Backend command validation
       |
       v
ESP32
       |
       v
Relay 1 ON/OFF
       |
       v
Response
```

Success example:

User says:
> "Robot, turn on relay one."

Expected sequence:

```text
Speech captured
-> wake recognized
-> text created
-> AI returns structured command
-> backend validates
-> command sent to ESP32
-> relay 1 turns ON
-> success reported
-> robot/PC speaks confirmation
```

---

# 38. Acceptance Tests

## Robot

- [ ] Boots correctly
- [ ] Connects Wi-Fi
- [ ] Registers with backend
- [ ] Sends heartbeat
- [ ] Handles command
- [ ] Acknowledges result
- [ ] Controls relay safely
- [ ] Recovers from network loss

## Voice

- [ ] Push-to-talk works
- [ ] Robot-name activation works
- [ ] Background conversation is ignored
- [ ] English works
- [ ] Hindi works
- [ ] Marathi works
- [ ] TTS works
- [ ] Failure is handled

## AI

- [ ] Natural language understood
- [ ] Structured output validated
- [ ] Unknown request safely rejected
- [ ] No direct database access
- [ ] Business context works
- [ ] Business TXT instructions work
- [ ] Sensitive actions require permissions/confirmation

## Business

- [ ] Inventory updates correctly
- [ ] Bills calculate from database prices
- [ ] Customer balance is correct
- [ ] Payment updates balance
- [ ] Reminders fire correctly
- [ ] Reports use database values
- [ ] Automation is deterministic

## App

- [ ] Login
- [ ] Dashboard
- [ ] Inventory
- [ ] Billing
- [ ] Customers
- [ ] Payments
- [ ] Reminders
- [ ] Reports
- [ ] Robot status
- [ ] Settings

## Exhibition

- [ ] PC not required
- [ ] Robot works over Wi-Fi
- [ ] Phone connects to same backend
- [ ] Backend is online
- [ ] API is authenticated
- [ ] Fallback behavior works
- [ ] Full demo works repeatedly

---

# 39. Non-Goals / Things Not to Build Yet

Do NOT start with:
- motors,
- movement,
- complex sensors,
- computer vision,
- autonomous navigation,
- multi-branch complexity,
- custom automation builder,
- advanced routine learning,
- online payment reconciliation,
- firmware OTA,
- unnecessary UI animations.

Do not add features just because they are technically interesting.

Priority is:
**reliable business workflow + reliable robot interaction.**

---

# 40. Design Principles

1. Database is the source of truth.
2. Backend is the authority.
3. AI is a reasoning/interface layer, not unrestricted system authority.
4. ESP32 is the physical controller.
5. App and robot share the same backend/database.
6. Sensitive actions need permissions.
7. Every important action is auditable.
8. Hardware failures must be recoverable.
9. Cloud failure must not crash the robot.
10. Build and test one vertical workflow at a time.

---

# 41. Recommended First Vertical Slice

The first complete end-to-end feature should be:

**VOICE RELAY CONTROL**

```text
Owner
  |
  v
"Robot, turn on relay one"
  |
  v
Speech-to-text
  |
  v
AI
  |
  v
{
  "action": "relay",
  "relay": 1,
  "state": "on"
}
  |
  v
Backend validation
  |
  v
Robot command
  |
  v
ESP32
  |
  v
Relay 1 ON
  |
  v
Confirmation
```

After that succeeds, use the exact same architecture for:
- inventory,
- billing,
- customers,
- payments,
- reminders,
- reports,
- automation.

---

# 42. Antigravity Agent Instructions

When implementing this project:

1. Read this specification before changing architecture.
2. Do not create fake integrations when a real interface is available.
3. Do not hard-code secrets into source code.
4. Do not bypass backend validation.
5. Do not allow Gemini to directly execute arbitrary system/database operations.
6. Preserve modular interfaces.
7. Write tests with each meaningful backend feature.
8. Build one working vertical slice before moving to the next.
9. Keep robot firmware non-blocking where practical.
10. Report implementation status clearly.
11. Do not silently change approved product features.
12. When a hardware detail is uncertain, mark it as provisional instead of inventing certainty.
13. Keep development and production configurations separate.
14. Do not make the PC a hidden production dependency.
15. Keep the system deployable to cloud infrastructure.
16. Prefer simple, reliable implementation over unnecessary complexity.
17. Every business write operation must be auditable.
18. Every robot command needs an ID and result.
19. Every major failure should have a recovery path.
20. The final acceptance test is "Robot + Phone + Internet, no PC."

---

# 43. Product Success Definition

The project is successful when, at an exhibition, a visitor can see:

```text
                 🤖 ROBOT
                    |
             "Robot, add 20 kg
                sugar."
                    |
                    v
                  AI
                    |
                    v
                DATABASE
                    |
          +---------+---------+
          |                   |
          v                   v
      📦 Inventory       📱 Mobile App
          |
          v
      Robot speaks:
      "20 kg sugar
       added."
```

Then:

```text
"Robot, how much sugar is left?"
```

and the robot answers using live business data.

Then:

```text
"Turn on relay one."
```

and a real physical relay responds.

This proves the product is not:
- just a chatbot,
- just an inventory app,
- just an ESP32 project,
- or just a voice assistant.

It is a connected **AI business operations system with a physical robot interface**.

---

# 44. Final Architecture Lock

Use this stack unless explicitly changed:

```text
ROBOT
ESP32 DevKit V1

AUDIO
INMP441
MAX98357A
4 ohm 3W speaker

UI
SSD1306 OLED
Buttons

ACTUATION
4-channel relay

BACKEND
Python + FastAPI

AI
Gemini API

APP
Flutter

DATABASE
PostgreSQL or approved equivalent

AUTH
Secure user + robot authentication

TRANSPORT
HTTPS initially

DEPLOYMENT
Google Cloud Run for backend production

DEVELOPMENT
PC may temporarily provide microphone/speaker and local backend

EXHIBITION
Robot + Phone + Cloud backend + Internet
NO PC
```

This is the reference architecture for implementation.
