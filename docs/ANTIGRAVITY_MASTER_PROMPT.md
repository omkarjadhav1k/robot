# 🤖 ANTIGRAVITY MASTER SPECIFICATION & RULES

## 1. Core Architecture Lock
- Robot (ESP32) ➔ HTTPS ➔ FastAPI Backend ➔ PostgreSQL / Gemini API / Business Logic / Robot API
- Flutter App ➔ HTTPS ➔ Same FastAPI Backend & Same PostgreSQL Database
- **One Brain Principle:** Mobile app and robot NEVER maintain separate business databases or conflicting business logic.
- **Exhibition Target:** Robot + Phone + Internet. NO PC REQUIRED in final production. PC is temporary development bridge for audio only.

## 1.1 Approved Technology Stack Lock
- **Backend:** FastAPI + Python 3.11 on Google Cloud Run (Serverless)
- **Database:** Supabase PostgreSQL (with Realtime WebSockets)
- **AI/LLM:** Google Gemini Flash (Google AI Studio)
- **Speech-to-Text:** Groq Whisper (whisper-large-v3)
- **Text-to-Speech:** Edge TTS (Indian English, Hindi, Marathi neural voices)
- **Mobile App:** Flutter Cross-Platform
- **Notifications:** Firebase Cloud Messaging (FCM)
- **Development/CI:** GitHub + GitHub Actions
- **Testing Tunnel:** Cloudflare Tunnel (`cloudflared`)
- **Robot Controller:** ESP32 DevKit V1

## 2. Authority & Source of Truth
- **Database (PostgreSQL):** Authoritative for inventory, prices, bills, customers, payments, reminders, reports.
- **Backend (FastAPI):** Authority for auth, permissions, validation, business rules, robot commands, and financial math.
- **Gemini (LLM):** Reasoning and conversational interface layer. Strictly emits structured tool calls.
  - NEVER directly executes SQL.
  - NEVER directly controls GPIO.
  - NEVER executes shell commands.
  - NEVER invents authoritative prices or stock levels.
  - NEVER bypasses permissions.

## 3. Mandatory Development Progression
```text
Phase 0  Workspace Scaffolding & Setup
Phase 1  FastAPI Foundation (/health, robot status/heartbeat)
Phase 2  PostgreSQL Models & Migrations
Phase 3  Security & RBAC (Owner, Staff, Robot)
Phase 4  Robot API & Command Lifecycle
Phase 5  ESP32 Firmware (Wi-Fi + Relay Control)
★ Milestone 1 — Voice Relay Control
Phase 6  Virtual Voice Bridge (PC Mic/TTS)
Phase 7  Real Audio Hardware (INMP441 + MAX98357A + Speaker)
Phase 8  OLED + Buttons
Phase 9  Robot Name Activation
Phase 10 Business Instructions (.txt upload)
Phase 11 Inventory
Phase 12 Billing
Phase 13 Customers
Phase 14 Payments
Phase 15 Reminders
Phase 16 Reports
Phase 17 Automation
Phase 18 Proactive AI
Phase 19 Multi-action commands
Phase 20 Flutter App
...
```

## 4. Hardware Safety
- Do NOT connect mains AC (220V/110V) during early development.
- MAX98357A speaker outputs (`SPK+`, `SPK-`) are bridged outputs; NEVER connect `SPK-` to GND.
- Dedicated 5V 2A external power supply to isolate high-current relay coils and audio amplifier from ESP32 logic.
- Active-LOW / Active-HIGH relay logic level verification.
