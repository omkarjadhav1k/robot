#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ==============================================================================
// 🤖 MAX — Manager AI eXecutive — ESP32 Firmware Configuration
// ==============================================================================

// --- Robot Identity ---
#define ROBOT_ID            "ROBOT-001"
#define FIRMWARE_VERSION    "1.0.0"

// --- Wi-Fi Credentials (CONFIGURE FOR YOUR NETWORK) ---
// Note: ESP32 only supports 2.4 GHz Wi-Fi networks
#define WIFI_SSID           "Airtel_yash_8260"
#define WIFI_PASSWORD       "Kavni@143"

// --- Central Brain Backend URL (Live Cloud Backend on Render) ---
#define BACKEND_BASE_URL    "https://business-ai-robot-backend.onrender.com"

// --- Timing & Intervals ---
#define HEARTBEAT_INTERVAL_MS   6000   // Send heartbeat & poll commands every 6s
#define WIFI_RETRY_INTERVAL_MS  5000   // Check Wi-Fi every 5s if disconnected
#define SERIAL_BAUD_RATE        115200

// --- HTTP Timeouts (milliseconds) ---
#define HTTP_TIMEOUT_HEARTBEAT  10000  // 10s for heartbeat POST
#define HTTP_TIMEOUT_COMMAND    10000  // 10s for command polling
#define HTTP_TIMEOUT_CHAT       60000  // 60s for voice/chat (Render cold start + Gemini reasoning)
#define HTTP_TIMEOUT_ACK        10000  // 10s for command ACK

// --- Hardware Abstraction & Virtual Emulation Modes ---
// Set to TRUE while waiting for physical parcels to arrive.
// When physical parcels arrive, wire them and set to FALSE!
#define VIRTUAL_AUDIO_MODE      true   // True: Use Laptop Mic & Speaker
#define VIRTUAL_DISPLAY_MODE    true   // True: Use Laptop Virtual OLED / Serial

// --- Pinout Definitions (ESP32 DevKit V1) ---

// 1. Onboard Status LED
#define PIN_STATUS_LED          2      // Built-in Blue LED on ESP32 DevKit V1

// 2. 4-Channel 5V Relay Module
// Most 5V relay boards are Active-LOW (LOW = Relay ON, HIGH = Relay OFF)
#define RELAY_ACTIVE_LOW        true
#define PIN_RELAY_1             16     // Relay Channel 1
#define PIN_RELAY_2             17     // Relay Channel 2
#define PIN_RELAY_3             18     // Relay Channel 3
#define PIN_RELAY_4             19     // Relay Channel 4

// 3. 0.96" SSD1306 I2C OLED (When Arrived)
#define PIN_OLED_SDA            21
#define PIN_OLED_SCL            22
#define OLED_SCREEN_WIDTH       128
#define OLED_SCREEN_HEIGHT      64
#define OLED_I2C_ADDRESS        0x3C

// 4. INMP441 I2S Digital Microphone (When Arrived)
#define PIN_I2S_MIC_SCK         27     // Serial Clock
#define PIN_I2S_MIC_WS          14     // Word Select (L/R)
#define PIN_I2S_MIC_SD          34     // Serial Data In

// 5. MAX98357A I2S Audio Amplifier (When Arrived)
#define PIN_I2S_SPK_BCLK        27     // Bit Clock (Shared with Mic clock)
#define PIN_I2S_SPK_LRC         14     // Left/Right Clock (Shared with Mic WS)
#define PIN_I2S_SPK_DIN         13     // Data Out to Amp

#endif // CONFIG_H
