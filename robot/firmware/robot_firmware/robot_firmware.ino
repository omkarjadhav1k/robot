#include <Arduino.h>
#include "config.h"
#include "status_led.h"
#include "relay_controller.h"
#include "display_manager.h"
#include "network_client.h"

// Hardware sub-controllers
StatusLED statusLed(PIN_STATUS_LED);
RelayController relayController(RELAY_ACTIVE_LOW);
DisplayManager displayManager(VIRTUAL_DISPLAY_MODE);
RobotNetworkClient networkClient(&statusLed, &relayController, &displayManager);

void setup() {
    // 1. Initialize Serial Communication
    Serial.begin(SERIAL_BAUD_RATE);
    delay(1000);

    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F(" 🤖 MAX — MANAGER AI EXECUTIVE HARDWARE CONTROLLER"));
    Serial.printf( F("    Device ID: %s | Firmware: v%s\n"), ROBOT_ID, FIRMWARE_VERSION);
    Serial.printf( F("    Mode:      %s\n"), USE_PRODUCTION_CLOUD ? "PRODUCTION (Render Cloud)" : "DEVELOPMENT (Local PC)");
    Serial.println(F("=================================================="));

    // 2. Initialize Hardware Peripherals
    statusLed.begin();
    relayController.begin();
    displayManager.begin();

    // 3. Connect to Wi-Fi, Verify Health, and Enter READY State
    networkClient.begin();

    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F(" 💬 MAX ROBOT ACTIVE & READY FOR VOICE/TEXT!"));
    Serial.println(F(" Type any question or command here & press Enter."));
    Serial.println(F(" Examples:"));
    Serial.println(F("   • Tata Salt kitna hai?"));
    Serial.println(F("   • Is week ki strategy bana."));
    Serial.println(F("   • Light on / Fan off"));
    Serial.println(F("   • Kal wali strategy batao."));
    Serial.println(F("   • status (view connection & IP details)"));
    Serial.println(F("   • reset wifi (start phone hotspot setup)"));
    Serial.println(F("=================================================="));
    Serial.println(F("\n💬 Type a message:"));
}

void loop() {
    // Update Non-blocking Controllers
    statusLed.update();
    networkClient.update();

    // Check for user input from Serial Monitor
    if (Serial.available() > 0) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        if (input.length() > 0) {
            networkClient.sendChatToBrain(input);
        }
    }

    // Small yield to let ESP32 Wi-Fi / RTOS tasks process smoothly
    delay(10);
}