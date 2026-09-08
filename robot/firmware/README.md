# 🤖 ESP32 Robot Firmware — Standalone Exhibition & Production Guide

This directory contains the standalone production firmware for your **ESP32 DevKit V1** powering **MAX — Manager AI eXecutive**.

In production mode, the robot is **100% standalone**:
- **Zero Laptop Required**: Power ON the robot, and it connects directly to the Render cloud backend via Wi-Fi or your mobile phone hotspot.
- **Automated Boot Sequence**: `BOOTING` ➔ `WIFI_CONNECTING` ➔ `WIFI_CONNECTED` ➔ `BACKEND_CONNECTING` ➔ `HEALTH CHECK OK` ➔ `READY` ➔ Announces *"Namaste! Main ready hoon."*
- **No-Laptop Wi-Fi Provisioning**: If you move to a new exhibition venue or switch Wi-Fi hotspots, the robot automatically starts a setup hotspot (`MAX-Robot-Setup`). Connect your phone, open `http://192.168.4.1`, select your network, and the robot reconnects and saves credentials permanently to ESP32 NVS.
- **Resilient Reconnection**: Automatically recovers from temporary network hiccups without freezing or continuous reboot loops. Offline relay controls continue to work even if the internet briefly drops.

---

## ⚙️ Step 1: Choose Environment Mode in `config.h`

Open [`config.h`](file:///c:/project/Robot/robot/firmware/robot_firmware/config.h):

```cpp
// Set to TRUE for Exhibition / Standalone Cloud Mode (No laptop needed)
// Set to FALSE for Local PC Development (192.168.1.33:8000)
#define USE_PRODUCTION_CLOUD    true
```

When `USE_PRODUCTION_CLOUD` is `true`:
- **Backend URL**: `https://business-ai-robot-backend.onrender.com`
- **Backend WebSocket**: `wss://business-ai-robot-backend.onrender.com/api/v1/voice/ws`
- **Transport**: HTTPS with secure TLS and automatic Render warm-up handling.

When `USE_PRODUCTION_CLOUD` is `false`:
- **Backend URL**: `http://192.168.1.33:8000` (Your local PC backend)

---

## 🔌 Step 2: Upload Firmware to ESP32

### Option A: Using Arduino IDE (Recommended & Easiest)
1. Open **Arduino IDE**.
2. Go to **File -> Open...** and select:
   `c:\project\Robot\robot\firmware\robot_firmware\robot_firmware.ino`
3. In **Tools -> Board -> esp32**, select:
   - **DOIT ESP32 DEVKIT V1** (or **ESP32 Dev Module**)
4. In **Tools -> Port**, select your ESP32's COM port (e.g. `COM3` or `COM4`).
5. Click the **Upload (➔)** button.
6. Open **Tools -> Serial Monitor** and set baud rate to **115200**.

> [!TIP]
> If upload stops at `Connecting........_____.....`:
> Press and hold the **BOOT** button on your ESP32 until upload progress percentage begins, then release it.

### Option B: Using PlatformIO
From terminal or VS Code PlatformIO extension:
```bash
cd robot/firmware
pio run --target upload
pio device monitor
```

---

## 📱 Exhibition Wi-Fi Setup (Without Any Laptop)

When you take the robot to an exhibition venue:
1. **Turn ON the Robot** (via USB power bank or 5V DC adapter).
2. If the saved Wi-Fi is not reachable, the robot waits 15 seconds, then starts its own setup hotspot:
   - **Wi-Fi SSID**: `MAX-Robot-Setup`
   - **Password**: `12345678`
3. **On your phone**:
   - Connect Wi-Fi to `MAX-Robot-Setup`.
   - Open browser to: `http://192.168.4.1`
   - Select your exhibition Wi-Fi or turn on your mobile phone hotspot and enter the password.
   - Click **Save & Connect Robot**.
4. The robot saves the credentials to internal non-volatile memory (NVS), connects to the hotspot, verifies the Render cloud backend, and announces:
   `"Namaste! Main ready hoon."`
5. You can now talk to the robot directly!

---

## 💡 Onboard Status LED Indications (GPIO 2)

| LED Pattern | Status | Meaning |
| :--- | :--- | :--- |
| **Fast Flash (150ms)** | `WIFI_CONNECTING` / `BACKEND_CONNECTING` | Connecting to Wi-Fi or Cloud Backend |
| **Double Pulse (800ms)**| `PROVISIONING` | Hotspot active (`MAX-Robot-Setup`). Connect phone! |
| **Solid Blue ON** | `READY` | Connected to Render Cloud, health OK, ready to talk |
| **Rapid Double Flash** | `COMMAND_EXEC` | Executing relay or fast-path hardware action |
| **Slow Blink (1000ms)** | `ERROR` / `RECONNECTING` | Waiting for network recovery |

---

## 💬 Serial Monitor Testing & Debug Commands

If connected to a PC for monitoring:
- Type questions: `Tata Salt kitna hai?`, `Is week ki strategy bana.`, `Light on`
- Type `status` to print IP, RSSI, Cloud Backend URL, and uptime.
- Type `reset wifi` to clear saved Wi-Fi credentials and trigger the phone setup hotspot.
- Type `wifi <SSID> <PASSWORD>` to switch Wi-Fi directly.
