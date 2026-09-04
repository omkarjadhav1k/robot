# 🤖 ESP32 Robot Firmware — Quick Flashing Guide

This directory contains the production firmware for your **ESP32 DevKit V1**.

It connects to your local Wi-Fi, registers with your FastAPI backend, reports real-time heartbeats and Wi-Fi RSSI, listens for hardware commands, and controls GPIO pins (relays & onboard status LED).

---

## ⚙️ Step 1: Configure Your Network & Backend URL

Open [`config.h`](file:///c:/project/Robot/robot/firmware/robot_firmware/config.h) and set:

```cpp
// 1. Your Wi-Fi network (Must be 2.4 GHz)
#define WIFI_SSID           "Your_WiFi_Name"
#define WIFI_PASSWORD       "Your_WiFi_Password"

// 2. Your Laptop's local IP address
// Run 'ipconfig' in terminal to find your IPv4 address (e.g., 192.168.1.15)
#define BACKEND_BASE_URL    "http://192.168.1.15:8000"
```

> [!WARNING]
> Do NOT use `localhost` or `127.0.0.1` for `BACKEND_BASE_URL` because the ESP32 is a separate physical device on your local Wi-Fi network.

---

## 🔌 Step 2: Upload to ESP32

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
> If the upload stops at `Connecting........_____.....`:
> Press and hold the **BOOT** button on your ESP32 until the upload progress percentage begins, then release it.

### Option B: Using PlatformIO
From terminal or VS Code PlatformIO extension:
```bash
cd robot/firmware
pio run --target upload
pio device monitor
```

---

## 💡 Onboard Status LED Indications (GPIO 2)

| LED Pattern | Meaning |
| :--- | :--- |
| **Fast Blinking (150ms)** | Connecting to Wi-Fi... |
| **Solid Blue ON** | Connected to Wi-Fi & Central Brain Online! |
| **Rapid Double Flash** | Executing hardware command (Relay/LED) |
| **Slow Blink (1s)** | Wi-Fi connection lost / retrying |

---

## 🚚 Drop-In Hardware Upgrade (When Parcels Arrive)

When your hardware arrives, wire the modules to these pre-configured pins:

1. **INMP441 I2S Microphone**:
   - `SCK` ➔ GPIO 27
   - `WS` ➔ GPIO 14
   - `SD` ➔ GPIO 34
   - `VDD` ➔ 3.3V, `GND` ➔ GND, `L/R` ➔ GND

2. **MAX98357A I2S Amplifier**:
   - `BCLK` ➔ GPIO 27
   - `LRC` ➔ GPIO 14
   - `DIN` ➔ GPIO 13
   - `VIN` ➔ 5V, `GND` ➔ GND

3. **0.96" SSD1306 OLED (I2C)**:
   - `SDA` ➔ GPIO 21
   - `SCL` ➔ GPIO 22
   - `VCC` ➔ 3.3V, `GND` ➔ GND

4. **4-Channel 5V Relay Module**:
   - `IN1` ➔ GPIO 16
   - `IN2` ➔ GPIO 17
   - `IN3` ➔ GPIO 18
   - `IN4` ➔ GPIO 19
   - `VCC` ➔ 5V, `GND` ➔ GND

Then, in [`config.h`](file:///c:/project/Robot/robot/firmware/robot_firmware/config.h), simply change:
```cpp
#define VIRTUAL_AUDIO_MODE    false  // Now uses INMP441 + MAX98357A!
#define VIRTUAL_DISPLAY_MODE  false  // Now uses physical SSD1306 OLED!
```
and re-upload!
