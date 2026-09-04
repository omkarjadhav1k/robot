# ☁️ Real Cloud Backend Deployment Guide

Deploy the Business AI Robot Central Brain to a real cloud server so the physical robot operates independently anywhere with **no laptop required**.

---

## 🎯 Target Architecture
```text
  🤖 Physical ESP32 Robot (Any Wi-Fi / Hotspot)
                   │
                   ▼  HTTPS
  ☁️ Cloud FastAPI Server (Render / Railway / Cloud Run)
                   │
                   ▼
  🐘 Cloud PostgreSQL Database (Neon / Supabase / Render Postgres)
```

---

## 🚀 Option 1: Render.com (Recommended — 100% Free & Automatic)

Render gives you both a **Free Cloud Web Service** and a **Free Managed Cloud PostgreSQL Database**:

1. Go to [Render.com](https://render.com) and log in (with your GitHub account).
2. Click **New +** → **Blueprint**.
3. Select your repository (`omkarjadhav1k/bytechsoftware`).
4. Point to the blueprint file: `deployment/render.yaml`.
5. Enter your `GEMINI_API_KEY` when prompted.
6. Click **Apply**.

Render will automatically:
- Provision a real Cloud PostgreSQL Database.
- Build and deploy your FastAPI Central Brain.
- Provide a public HTTPS URL: `https://business-ai-robot-backend.onrender.com`

---

## 🚀 Option 2: Railway.app (Fastest 1-Click)

1. Go to [Railway.app](https://railway.app).
2. Click **New Project** → **Deploy from GitHub Repo**.
3. Add a **PostgreSQL** plugin (Railway creates a cloud DB in 5 seconds).
4. Set Environment Variables:
   - `GEMINI_API_KEY` = your key
   - `GEMINI_MODEL` = `gemini-3.7-flash`
   - `DATABASE_URL` = automatically connected from Railway Postgres
5. Click **Deploy** to get your public HTTPS domain.

---

## 🚀 Option 3: Free Cloud PostgreSQL (Neon.tech / Supabase)

If you only want the cloud database right now:
1. Go to [Neon.tech](https://neon.tech) and create a free PostgreSQL database.
2. Copy your connection string:
   ```env
   DATABASE_URL="postgresql://username:password@ep-xyz.neon.tech/neondb?sslmode=require"
   ```
3. Paste it into `backend/.env`.

---

## 🤖 Step After Deployment: Connect Your ESP32

Once your cloud backend is live, open [`config.h`](file:///c:/project/Robot/robot/firmware/robot_firmware/config.h) on your ESP32 and replace the local IP with your real cloud HTTPS URL:

```cpp
#define BACKEND_BASE_URL    "https://your-cloud-app.onrender.com"
```

Re-upload to ESP32. Now your robot is completely wireless, connected to the cloud, and requires **NO laptop or localhost**!
