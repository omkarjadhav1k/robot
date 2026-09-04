# BUSINESS AI ROBOT — DESIGN.md

## 1. Purpose

This document is the visual and implementation design reference for the Business AI Robot mobile application.

The app should feel like a **clean, premium iPhone/iOS business app**, not a generic admin dashboard.

### Design direction

- White / near-white background
- Minimalistic iOS-style interface
- Large clean typography
- Rounded cards with very subtle borders/shadows
- Blue as the primary action/accent color
- Small semantic colors only where useful:
  - Green = success/online/paid
  - Red = danger/due/low stock
  - Orange = warning
  - Purple/teal = secondary categories
- Generous spacing
- Simple line icons
- No dark theme for V1
- No excessive gradients
- No crowded screens
- No unnecessary decorative elements
- Smooth, subtle animations
- iPhone-style navigation and interaction patterns

The attached/generated UI collage is the visual inspiration for this design.

---

# 2. Product Feel

The user should feel:

> "This is my digital business manager."

The interface must make important information visible within seconds.

Priorities:

1. Business status
2. Robot status
3. Sales/orders
4. Pending payments
5. Low stock
6. Fast actions
7. Voice command
8. Detailed management screens

The app must remain useful even when the robot is offline.

---

# 3. Global UI System

## Colors

Primary:
- iOS-style blue: `#007AFF`

Background:
- `#FFFFFF`
- Secondary background: `#F7F8FA`

Text:
- Primary: near-black
- Secondary: gray
- Muted: light gray

Semantic:
- Success: green
- Danger: red
- Warning: orange

Do not hard-code colors throughout the application. Create a centralized theme/color system.

## Typography

Use a clean iOS-like font stack.

Recommended Flutter font:
- SF Pro where available / system sans fallback

Hierarchy:

- Screen title: 24–28px, semibold
- Section title: 16–18px, semibold
- Card title: 14–16px, medium/semibold
- Body: 14–16px
- Caption: 11–13px
- Large KPI number: 24–30px, semibold

Avoid excessive bold text.

## Shape

Default:
- Card radius: 14–18px
- Button radius: 12–14px
- Search field radius: 14px
- Full/large action button: 12–14px

## Spacing

Use a consistent spacing scale:

- 4
- 8
- 12
- 16
- 20
- 24
- 32

Avoid arbitrary spacing values.

---

# 4. Navigation

Use a simple iOS-style bottom navigation.

Primary destinations:

- Home
- Robot
- Reports
- More

Contextual sections such as Inventory, Billing, Customers, Payments and Reminders can be accessed from Home/More and from contextual actions.

The navigation must be easy to use with one hand.

---

# 5. Dashboard

## Goal

Give the owner an immediate business overview.

### Header

- Hamburger/menu icon
- "Dashboard"
- Notification icon

### Robot status card

Show:

- Robot image/avatar
- Robot Status
- Online/Offline indicator
- Listening state
- Small voice waveform when active

Example:

`Robot Status`
`Online ●`
`Listening...`

### Today Overview

KPI cards:

- Sales
- Orders
- Pending Payments
- Low Stock Items

Each card may include:
- value
- small trend
- small semantic indicator

### Quick Actions

Four compact actions:

- New Bill
- Add Stock
- Voice Command
- Reminders

Keep these visually simple.

---

# 6. Robot Screen

The Robot screen is the emotional center of the app.

Show:

- Large robot illustration/avatar
- Online/offline state
- Listening state
- "I'm Listening..." or "Tap to Speak"
- Large circular microphone button
- Stop button
- History

Voice interaction should feel immediate.

Example state flow:

`Idle → Listening → Processing → Speaking → Idle`

Do not create a complex visual interface for voice.

---

# 7. Inventory

Inventory should be extremely fast to scan.

### Header

- Back/menu
- "Inventory"
- Add button

### Search

Search field:

`Search products...`

### Product cards

Each row/card:

- Product image/icon
- Product name
- Current stock
- Minimum stock
- Stock status
- Small stock indicator

Example:

`Sugar          32 kg`
`Min: 20 kg`

Low-stock products should be clearly identifiable without making the whole UI red.

Actions:

- Add stock
- Reduce stock
- Edit
- Delete
- View history

---

# 8. Billing

Billing must be optimized for speed.

### New Bill

Customer selector/card:

- Customer name
- Phone
- Edit/select

Items:

- Product
- Quantity
- Price
- Total
- Remove item

Then:

- Add Item
- Subtotal
- Discount
- GST (when enabled)
- Total

Payment:

- Cash
- UPI
- Credit

Primary CTA:

`Generate Bill`

The total should be visually prominent.

---

# 9. Customers

Customer screen:

- Search
- Add customer

Each customer row:

- Initial/avatar
- Name
- Phone
- Outstanding amount
- Paid/Due status

Customer detail should contain:

- Purchase history
- Payment history
- Current balance
- Bills
- Optional notes

---

# 10. Payments

Show two primary summary cards:

- Total Pending
- Received Today

Then:

`Recent Payments`

Each row:

- Customer
- Date
- Amount
- Payment method

Include:

`View All Payments`

---

# 11. Reminders

Use a clean list.

Tabs/filters:

- All
- Today
- Upcoming
- Done

Each reminder:

- Small colored status dot
- Title
- Date/time
- Status

Examples:

- Call Supplier
- Check Oil Stock
- Pay Electricity Bill
- Weekly Inventory Check
- Shop Cleaning

Support:

- Add
- Complete
- Delete
- Recurring reminders

---

# 12. Reports

Reports should look analytical without becoming complicated.

Top controls:

- Date range
- This Week
- This Month
- Custom

Summary:

- Sales
- Orders

Charts:

- Sales trend
- Product performance
- Inventory
- Customer/payment data

Add an AI summary section:

`AI Business Summary`

Example:

- Sales increased this week.
- Oil is approaching minimum stock.
- Three customer payments are overdue.

AI recommendations must be based on real backend data.

---

# 13. Robot Control

Show:

- Robot online/offline
- Last seen
- Relay 1
- Relay 2
- Relay 3
- Relay 4
- Microphone status
- Speaker status

Each relay gets:

- ON/OFF state
- Safe control button
- Current status

Important:

The app must NOT directly control GPIO.

Flow:

`Flutter → FastAPI → validated command → ESP32`

---

# 14. Settings

Keep Settings simple.

Sections:

### Account
- Owner profile
- Users & Roles

### Business
- Business Profile
- Product Settings

### AI & Robot
- AI & Voice Settings
- Robot Settings
- Language

### Notifications
- Alerts
- Reminders

### Data
- Backup & Restore

### About
- About App
- Logout

Dangerous actions should require confirmation.

---

# 15. Component Rules

Create reusable Flutter components instead of rebuilding UI repeatedly.

Recommended components:

- `AppScaffold`
- `AppHeader`
- `PrimaryButton`
- `SecondaryButton`
- `StatCard`
- `StatusBadge`
- `SearchField`
- `ListCard`
- `EmptyState`
- `LoadingState`
- `ErrorState`
- `RobotStatusCard`
- `ProductCard`
- `CustomerCard`
- `PaymentCard`
- `ReminderCard`
- `BottomNavigation`

Components should receive data/configuration rather than containing business logic.

---

# 16. Responsive Behavior

The primary target is modern iPhone-sized mobile screens.

However:

- Do not hard-code a single screen size.
- Use Flutter responsive layout principles.
- Handle small Android screens gracefully.
- Respect safe areas.
- Support light mode cleanly.

---

# 17. UX Rules

1. One primary action per screen.
2. Avoid unnecessary dialogs.
3. Use inline feedback where possible.
4. Confirm destructive actions.
5. Show loading states.
6. Show useful empty states.
7. Show useful error states.
8. Never make the user wonder whether an action succeeded.
9. Do not block the UI unnecessarily.
10. Voice actions must display what the robot understood before executing sensitive actions.
11. Financial/inventory-changing actions must be validated by the backend.
12. The backend remains the source of truth.

---

# 18. Architecture Rules

Final stack:

```text
Flutter / Dart
       |
      HTTPS
       |
FastAPI Backend
       |
PostgreSQL
       |
Gemini AI
       |
ESP32 Robot
```

The Flutter app must NOT:

- connect directly to PostgreSQL
- contain database credentials
- call Gemini with secret API keys
- directly control ESP32 GPIO
- contain authoritative business calculations
- maintain a separate business database

Backend is authoritative.

---

# 19. Current Implementation Strategy

Do not attempt to build every feature at once.

Build vertically.

Order:

1. Backend foundation
2. Database
3. Authentication/RBAC
4. Robot API
5. ESP32 base firmware
6. Voice relay vertical slice
7. Virtual voice bridge
8. Real audio hardware
9. OLED/buttons
10. Robot-name activation
11. Inventory
12. Billing
13. Customers
14. Payments
15. Reminders
16. Reports
17. Automation
18. Proactive AI
19. Multi-action commands
20. Flutter application UI
21. App security
22. WhatsApp
23. Cloud deployment
24. Reliability/security/testing
25. Exhibition preparation

Do not skip ahead simply because a UI screen is visually available.

---

# 20. NEXT PHASE — START THE REAL WORKING APP

## Antigravity Execution Prompt

Copy the following prompt into Antigravity:

---

You are now starting the REAL implementation of the Business AI Robot project.

This is no longer a design-only task.

Before changing code:

1. Read:
   - `docs/PRODUCT_SPEC.md`
   - `docs/HARDWARE_SPEC.md`
   - `docs/DEVELOPMENT_PLAN.md`
   - `docs/ANTIGRAVITY_MASTER_PROMPT.md`
   - `docs/DESIGN.md`

2. Inspect the complete repository structure.

3. Determine what already exists.

4. Do NOT assume that files, APIs, database tables, firmware, or UI are implemented merely because they are described in documentation.

5. Preserve the locked architecture.

## Current architecture

```text
Flutter App
    ↓ HTTPS
FastAPI Backend
    ↓
PostgreSQL
    ↓
Gemini AI
    ↓
ESP32 Robot
```

Backend = source of truth.

---

# PHASE 1 — FASTAPI FOUNDATION

Start with Phase 1 only.

Do not jump to inventory, billing, WhatsApp, Gemini actions, or advanced Flutter screens yet.

## Objective

Create a clean, runnable FastAPI backend foundation.

## Required work

### 1. Backend structure

Create a maintainable structure similar to:

```text
backend/
  app/
    main.py
    core/
    api/
    models/
    schemas/
    services/
    repositories/
    tests/
  requirements.txt
  .env.example
```

Use the existing repository structure if one already exists and is consistent with the specification. Do not unnecessarily reorganize working code.

### 2. Environment configuration

Create safe environment configuration.

Secrets must NOT be hard-coded.

At minimum prepare configuration for:

- database URL
- JWT/auth secret
- Gemini API key
- robot authentication/configuration
- application environment

Provide `.env.example`.

Never commit real secrets.

### 3. FastAPI application

Create the application entry point.

Add:

`GET /health`

Expected response should clearly indicate that the backend is running.

Example:

```json
{
  "status": "ok"
}
```

### 4. API organization

Prepare versioned API routing:

```text
/api/v1/
```

Do not implement all business endpoints yet.

### 5. Error handling

Create a clean foundation for:

- validation errors
- application errors
- unexpected server errors

Responses should be predictable.

### 6. Logging

Add basic structured application logging.

Do not log:

- passwords
- API keys
- JWT secrets
- sensitive credentials

### 7. Testing

Create backend tests.

At minimum test:

- application starts
- `/health` returns HTTP 200
- response structure is correct

Tests must run locally.

### 8. Documentation

Ensure FastAPI Swagger/OpenAPI documentation works.

Expected development endpoints:

```text
/health
/docs
/openapi.json
```

### 9. Run the backend

Actually start the backend.

Do not merely create files.

Verify:

- server starts
- health endpoint works
- tests pass
- no import errors
- no configuration errors

---

# Important Development Rules

- Do not fake successful functionality.
- Do not create mock business data and call it production functionality.
- Do not connect Gemini yet unless this phase explicitly requires it.
- Do not connect PostgreSQL until Phase 2.
- Do not implement ESP32 GPIO in this phase.
- Do not hard-code credentials.
- Do not silently change architecture.
- Keep code modular.
- Keep functions small and testable.
- Add tests with meaningful functionality.
- If an existing implementation is better than the suggested structure, preserve it and document the decision.

If something is ambiguous, choose the smallest implementation consistent with the locked specification.

---

# Completion Gate

Do NOT declare Phase 1 complete until all are true:

- [ ] FastAPI starts successfully
- [ ] `/health` returns 200
- [ ] `/docs` works
- [ ] API versioning foundation exists
- [ ] environment configuration exists
- [ ] no secrets are hard-coded
- [ ] error handling foundation exists
- [ ] logging foundation exists
- [ ] automated tests exist
- [ ] tests pass
- [ ] no unrelated feature was implemented

After completion, STOP.

Do not automatically start Phase 2.

---

# Required Final Report

At the end, report exactly:

```text
PHASE:
TASK:
FILES CREATED:
FILES CHANGED:
WHAT WORKS:
TESTS RUN:
RESULT: PASS/FAIL
KNOWN ISSUES:
NEXT EXACT STEP:
```

The `NEXT EXACT STEP` must be:

`Phase 2 — PostgreSQL foundation`

unless Phase 1 failed.

---

# Golden Rule

Build a REAL working system incrementally.

Do not optimize for the number of files created.

Optimize for:

`working code → tested code → integrated code → reliable product`

The goal is eventually:

```text
Owner speaks
   ↓
Robot understands
   ↓
AI reasons
   ↓
Backend validates
   ↓
Database updates
   ↓
Robot/App acts
   ↓
Owner receives confirmation
```

Every phase must move the project closer to that real end-to-end experience.

---

# END OF NEXT PHASE PROMPT
