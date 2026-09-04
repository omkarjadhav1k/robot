# 🤖 Business AI Robot — V1 Component Instructions

## Purpose

This file is the hardware reference for the Business AI Robot V1 prototype.

It covers:
- What each component does
- What variant to order
- Why the component is needed
- Basic connection purpose
- Safety/caution notes
- V1 assembly order
- Antigravity hardware-development instructions

V1 intentionally does **not** include motors, wheels, cameras, ultrasonic sensors, or other unnecessary sensors.

---

# 1. Components Already Available

## 1.1 ESP32 DevKit V1

**Quantity:** 1

### Purpose
Main controller of the physical robot.

### Responsibilities
- Wi-Fi communication
- Backend communication
- Microphone input
- Speaker/audio control
- OLED control
- Push-button input
- Relay control
- Robot status/heartbeat
- Command acknowledgment
- Local state management

### Important
The ESP32 is the **physical controller**. Gemini does not run directly on the ESP32.

---

## 1.2 4-Channel Relay Module

**Quantity:** 1

### Purpose
Provides four controllable outputs for external devices.

Example:

```text
Relay 1 → Light
Relay 2 → Fan
Relay 3 → Device 3
Relay 4 → Device 4
```

### Before wiring
Verify the exact module:
- Power voltage
- Input logic
- Whether inputs are active-LOW or active-HIGH
- ESP32 input compatibility

### Safety
Do not use mains AC appliances during early testing.

Start with safe low-voltage test loads.

---

## 1.3 ESP32 USB Cable

**Quantity:** 1

### Purpose
- Firmware upload
- Serial monitoring
- Development power

### Final robot
The exhibition robot must not require a PC.

---

# 2. Components to Order

## 2.1 INMP441 I2S Microphone Module

**Quantity:** 1

### Buy
**INMP441 I2S MEMS digital microphone module**

### Purpose
The robot's ears.

It captures the owner's speech and sends digital audio to the ESP32 using I2S.

### Connection concept

```text
INMP441
├── VDD  → 3.3V
├── GND  → GND
├── SCK  → I2S clock
├── WS   → I2S word select
├── SD   → ESP32 I2S data input
└── L/R  → channel selection
```

### Provisional ESP32 pins

```text
BCLK / SCK → GPIO 27
WS / LRCLK → GPIO 14
SD         → GPIO 34
```

### Important
Verify the actual module's printed pin labels when it arrives.

---

## 2.2 MAX98357A I2S Amplifier Module

**Quantity:** 1

### Buy
**MAX98357A I2S digital audio amplifier module**

Prefer a board explicitly intended for ESP32/I2S use.

### Purpose
Amplifies digital audio from the ESP32 so the robot can speak through its speaker.

### Flow

```text
ESP32
  ↓ I2S
MAX98357A
  ↓
Speaker
```

### Provisional pins

```text
BCLK → GPIO 27
LRC  → GPIO 14
DIN  → GPIO 13
```

### Important
Verify actual module labels and power input before wiring.

---

## 2.3 4Ω 3W Speaker

**Quantity:** 1

### Buy
**4 ohm, 3 watt speaker**

### Purpose
The robot's voice output.

Example:

> "20 kg sugar has been added."

### Connection

```text
MAX98357A SPK+ → Speaker +
MAX98357A SPK- → Speaker -
```

### Critical warning
Do **not** connect either speaker output terminal to ESP32 GND.

---

## 2.4 0.96-inch SSD1306 OLED

**Quantity:** 1

### Buy
- 0.96 inch
- SSD1306
- 128×64
- I2C

### Purpose
Robot visual/status display.

### Examples

```text
BUSINESS AI
READY
```

```text
LISTENING...
```

```text
THINKING...
```

```text
RELAY 1
ON
```

```text
CLOUD OFFLINE
```

### Provisional I2C pins

```text
SDA → GPIO 21
SCL → GPIO 22
```

Verify the board's actual labels before final connection.

---

## 2.5 5V 2A Power Adapter

**Quantity:** 1

### Buy
**5V DC, 2A adapter**

### Purpose
Main external V1 power source.

### Important
Do not connect every module directly to a common rail without checking:
- voltage
- current
- polarity
- grounding
- brownout risk

The amplifier and relay load must not cause ESP32 resets.

During development, the ESP32 can still use USB power.

---

## 2.6 Breadboard

**Quantity:** 1–2

### Purpose
Temporary V1 prototyping.

### Recommendation
Prefer a full-size breadboard because the build has:
- ESP32
- audio modules
- OLED
- buttons
- relay wiring
- multiple power/ground connections

---

## 2.7 Male-to-Male Jumper Wires

**Quantity:** 1 set

### Purpose
ESP32 ↔ breadboard and general breadboard connections.

---

## 2.8 Male-to-Female Jumper Wires

**Quantity:** 1 set

### Purpose
ESP32 ↔ breakout modules.

Useful for:
- INMP441
- OLED
- MAX98357A
- relay inputs where applicable

---

## 2.9 Female-to-Female Jumper Wires

**Quantity:** 1 set

### Purpose
Header-to-header/module-to-module connections where required.

---

## 2.10 Push Buttons

**Quantity:** 5

### Planned functions

```text
Button 1 → Listen
Button 2 → Stop / Cancel
Button 3 → Confirm
Button 4 → Menu
Button 5 → Spare
```

### Wiring concept

```text
ESP32 GPIO
    |
  Button
    |
   GND
```

Firmware can use:

```cpp
pinMode(BUTTON_PIN, INPUT_PULLUP);
```

Expected logic:

```text
Not pressed → HIGH
Pressed     → LOW
```

Implement debouncing in firmware.

---

# 3. Optional but Useful

These are not required for the core V1 build.

```text
Extra jumper wires
Extra push buttons
220Ω resistors
10kΩ resistors
Terminal blocks / screw connectors
Small project enclosure
```

Do not let optional parts delay the core build.

---

# 4. Components NOT Required for V1

Do not order:

```text
❌ Motors
❌ Motor drivers
❌ Wheels
❌ Servo motors
❌ Ultrasonic sensors
❌ Camera modules
❌ PIR sensors
❌ Complex sensors
❌ Autonomous navigation hardware
```

V1 focuses on:

```text
Voice
+
AI
+
Business functions
+
ESP32
+
Relay
+
OLED
+
Buttons
```

---

# 5. V1 Hardware Architecture

```text
                    5V POWER
                       |
          +------------+------------+
          |            |            |
          v            v            v
       ESP32       MAX98357A     Relay Module
          |            |
          |            v
          |        4Ω 3W Speaker
          |
     +----+---------+---------+
     |              |         |
     v              v         v
 INMP441          OLED      Buttons
 Mic              Display
```

---

# 6. Provisional ESP32 Pin Map

This is a **starting map only**. It must be verified with the real hardware before firmware/wiring is locked.

| Function | GPIO |
|---|---:|
| OLED SDA | 21 |
| OLED SCL | 22 |
| INMP441 BCLK | 27 |
| INMP441 WS | 14 |
| INMP441 DATA | 34 |
| MAX98357A BCLK | 27 |
| MAX98357A LRC | 14 |
| MAX98357A DATA | 13 |
| Relay 1 | 16 |
| Relay 2 | 17 |
| Relay 3 | 18 |
| Relay 4 | 19 |
| Listen button | 32 |
| Stop button | 33 |
| Confirm button | 25 |
| Menu button | 26 |

Before final firmware lock, verify:
- actual board labels,
- relay active level,
- I2S configuration,
- voltage/current requirements,
- pin conflicts,
- boot/strap-pin constraints.

---

# 7. What Each Component Means in the Robot

| Component | Robot role |
|---|---|
| ESP32 | Brain/body controller for hardware and networking |
| INMP441 | Ears / microphone |
| MAX98357A | Audio amplifier |
| 4Ω 3W speaker | Voice |
| SSD1306 OLED | Face/status display |
| Push buttons | Physical controls |
| 4-channel relay | Physical action/output interface |
| 5V 2A adapter | External power |
| Breadboard | Development platform |
| Jumper wires | Prototype connections |

---

# 8. Example — Asking About Inventory

Owner:

> "Robot, how much sugar is left?"

```text
INMP441
   ↓
ESP32
   ↓
Wi-Fi
   ↓
Backend
   ↓
AI + Business Database
   ↓
Response
   ↓
ESP32
   ↓
MAX98357A
   ↓
Speaker
```

Robot:

> "You have 32 kilograms of sugar."

OLED:

```text
Sugar: 32 kg
```

---

# 9. Example — Physical Control

Owner:

> "Robot, turn on relay one."

```text
Voice
 ↓
INMP441
 ↓
ESP32
 ↓
Backend / AI
 ↓
Validated command
 ↓
ESP32
 ↓
Relay 1 ON
```

Robot:

> "Relay one is now on."

---

# 10. Order Checklist

## Already have

```text
☑ ESP32 DevKit V1 ×1
☑ 4-Channel Relay Module ×1
☑ ESP32 USB Cable ×1
```

## Order

```text
☐ INMP441 I2S Microphone Module ×1
☐ MAX98357A I2S Amplifier Module ×1
☐ 4Ω 3W Speaker ×1
☐ 0.96" SSD1306 128×64 I2C OLED ×1
☐ 5V 2A Power Adapter ×1
☐ Breadboard ×1–2
☐ Male-Male Jumper Wire Set ×1
☐ Male-Female Jumper Wire Set ×1
☐ Female-Female Jumper Wire Set ×1
☐ Push Buttons ×5
```

---

# 11. Assembly Order

Do not connect everything simultaneously.

Use this sequence:

```text
1. ESP32
   ↓
2. OLED
   ↓
3. Buttons
   ↓
4. Relay
   ↓
5. INMP441
   ↓
6. MAX98357A + Speaker
   ↓
7. Power system
   ↓
8. Full hardware integration
```

Test each stage before proceeding.

---

# 12. Hardware Verification Rule

Do **not** treat this document's provisional pin map as the final wiring diagram.

When the actual modules arrive:

1. Read the printed labels.
2. Identify exact module variants.
3. Verify voltage requirements.
4. Verify current/power requirements.
5. Verify relay input logic.
6. Verify I2S connections.
7. Check for pin conflicts.
8. Then lock the final firmware and wiring.

This is especially important for relay and audio modules because breakout-board implementations can differ.

---

# 13. Antigravity Hardware Instructions

Antigravity must use this file as the V1 hardware reference.

### Do

- Keep hardware drivers separate from business logic.
- Keep GPIO assignments configurable.
- Add hardware diagnostics.
- Add safe startup states.
- Add relay-off default where appropriate.
- Handle network/hardware failures gracefully.
- Allow temporary PC microphone/speaker substitution during development.
- Do not assume module pin labels without checking the actual boards.

### Do not

- Add unnecessary hardware.
- Finalize power wiring without checking module specifications.
- Assume relay active-LOW/active-HIGH.
- Put API secrets directly into firmware.
- Connect mains AC during early testing.
- Make a PC a hidden production dependency.
- Lock the provisional pin map without hardware verification.

---

# 14. V1 Hardware Success Criteria

The hardware phase is complete when:

```text
☐ ESP32 boots
☐ ESP32 connects to Wi-Fi
☐ OLED displays status
☐ Buttons are detected
☐ Relay 1–4 can be controlled safely
☐ INMP441 captures audio
☐ MAX98357A plays audio
☐ Speaker produces clear voice
☐ Robot reports hardware/network status
☐ Robot recovers after reboot
☐ Hardware passes a long-duration test
```

Final exhibition target:

```text
🤖 ROBOT + 📱 PHONE + ☁️ BACKEND + INTERNET

NO PC REQUIRED
```
