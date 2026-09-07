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
    Serial.println(F("=================================================="));

    // 2. Initialize Hardware Peripherals
    statusLed.begin();
    relayController.begin();
    displayManager.begin();

    // 3. Connect to Wi-Fi and Central Brain Backend
    networkClient.begin();

    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F(" 💬 SERIAL MONITOR CHAT ACTIVE!"));
    Serial.println(F(" Type any question or command here & press Enter."));
    Serial.println(F(" Examples:"));
    Serial.println(F("   • What is 50 * 12?"));
    Serial.println(F("   • Who are you?"));
    Serial.println(F("   • Turn on relay 1"));
    Serial.println(F("   • Turn off relay 1"));
    Serial.println(F("   • Blink the LED"));
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