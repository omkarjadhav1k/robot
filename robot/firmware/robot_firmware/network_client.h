#ifndef ROBOT_NETWORK_CLIENT_H
#define ROBOT_NETWORK_CLIENT_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "config.h"
#include "status_led.h"
#include "relay_controller.h"
#include "display_manager.h"

class RobotNetworkClient {
private:
    StatusLED* _led;
    RelayController* _relays;
    DisplayManager* _display;
    unsigned long _lastHeartbeatTime;
    unsigned long _lastWifiCheckTime;
    bool _isConnected;
    WiFiClientSecure _secureClient;
    WiFiClient _plainClient;

    bool _beginHttp(HTTPClient& http, const String& url) {
        if (url.startsWith("https://")) {
            _secureClient.setInsecure(); // Connect via HTTPS without hardcoded Root CA certificate
            return http.begin(_secureClient, url);
        } else {
            return http.begin(_plainClient, url);
        }
    }

    // Helper: Extract JSON string value by key
    String _extractJsonString(const String& json, const String& key) {
        String searchKey = "\"" + key + "\":\"";
        int start = json.indexOf(searchKey);
        if (start == -1) return "";
        start += searchKey.length();
        int end = json.indexOf("\"", start);
        if (end == -1) return "";
        return json.substring(start, end);
    }

    // Helper: Extract JSON int value by key
    int _extractJsonInt(const String& json, const String& key, int defaultVal = 0) {
        String searchKey = "\"" + key + "\":";
        int start = json.indexOf(searchKey);
        if (start == -1) return defaultVal;
        start += searchKey.length();
        while (start < json.length() && (json[start] == ' ' || json[start] == '\t')) start++;
        int end = start;
        while (end < json.length() && (isDigit(json[end]) || json[end] == '-')) end++;
        if (start == end) return defaultVal;
        return json.substring(start, end).toInt();
    }

public:
    RobotNetworkClient(StatusLED* led, RelayController* relays, DisplayManager* display)
        : _led(led), _relays(relays), _display(display),
          _lastHeartbeatTime(0), _lastWifiCheckTime(0), _isConnected(false) {}

    void begin() {
        Serial.println(F("\n[WIFI] Initializing Wi-Fi connection..."));
        _display->showStatus("WIFI CONNECTING", WIFI_SSID);
        _led->setPattern(PATTERN_CONNECTING);

        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

        int attempts = 0;
        while (WiFi.status() != WL_CONNECTED && attempts < 20) {
            delay(500);
            _led->update();
            Serial.print(F("."));
            attempts++;
        }

        if (WiFi.status() == WL_CONNECTED) {
            _isConnected = true;
            Serial.println(F("\n[WIFI] Connected successfully!"));
            Serial.print(F("[WIFI] IP Address: "));
            Serial.println(WiFi.localIP());
            Serial.print(F("[WIFI] RSSI: "));
            Serial.print(WiFi.RSSI());
            Serial.println(F(" dBm"));

            _led->setPattern(PATTERN_ONLINE);
            _display->showStatus("ONLINE", WiFi.localIP().toString(), _relays->getRelaysJson());
        } else {
            _isConnected = false;
            Serial.println(F("\n[WIFI] Initial connection timed out. Will retry in background."));
            _led->setPattern(PATTERN_ERROR);
            _display->showStatus("WIFI FAILED", "Retrying...");
        }
    }

    void update() {
        unsigned long now = millis();

        // 1. Maintain Wi-Fi
        if (now - _lastWifiCheckTime >= WIFI_RETRY_INTERVAL_MS) {
            _lastWifiCheckTime = now;
            if (WiFi.status() != WL_CONNECTED) {
                _isConnected = false;
                _led->setPattern(PATTERN_CONNECTING);
                Serial.println(F("[WIFI] Disconnected! Reconnecting..."));
                WiFi.reconnect();
                return;
            } else if (!_isConnected) {
                _isConnected = true;
                _led->setPattern(PATTERN_ONLINE);
                _display->showStatus("ONLINE", WiFi.localIP().toString(), _relays->getRelaysJson());
            }
        }

        // 2. Periodic Heartbeat & Command Polling
        if (_isConnected && (now - _lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS)) {
            _lastHeartbeatTime = now;
            sendHeartbeat();
        }
    }

    void sendHeartbeat() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/heartbeat";

        _beginHttp(http, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(5000);

        String micStatus = VIRTUAL_AUDIO_MODE ? "virtual" : "ok";
        String spkStatus = VIRTUAL_AUDIO_MODE ? "virtual" : "ok";
        String oledStatus = VIRTUAL_DISPLAY_MODE ? "virtual" : "ok";

        String payload = "{";
        payload += "\"robot_id\":\"" + String(ROBOT_ID) + "\",";
        payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\",";
        payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
        payload += "\"uptime_seconds\":" + String(millis() / 1000) + ",";
        payload += "\"relays_state\":" + _relays->getRelaysJson() + ",";
        payload += "\"peripherals\":{";
        payload += "\"mic\":\"" + micStatus + "\",";
        payload += "\"speaker\":\"" + spkStatus + "\",";
        payload += "\"oled\":\"" + oledStatus + "\",";
        payload += "\"relays\":\"ok\"";
        payload += "}";
        payload += "}";

        int httpCode = http.POST(payload);
        if (httpCode == 200) {
            String response = http.getString();
            int pendingCount = _extractJsonInt(response, "pending_commands_count", 0);
            if (pendingCount > 0) {
                Serial.printf("[ROBOT] %d pending command(s) waiting on server! Fetching...\n", pendingCount);
                fetchAndExecuteCommands();
            }
        } else {
            Serial.printf("[HEARTBEAT] POST failed with HTTP code: %d\n", httpCode);
        }
        http.end();
    }

    void fetchAndExecuteCommands() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/pending";

        _beginHttp(http, url);
        http.setTimeout(5000);

        int httpCode = http.GET();
        if (httpCode == 200) {
            String body = http.getString();
            parseAndExecuteCommands(body);
        } else {
            Serial.printf("[COMMAND] GET pending failed, code: %d\n", httpCode);
        }
        http.end();
    }

    void parseAndExecuteCommands(const String& jsonArray) {
        // The endpoint returns a JSON array of commands: [{"command_id": "...", "action": "...", ...}]
        int searchIdx = 0;
        while (true) {
            int cmdStart = jsonArray.indexOf("{\"command_id\":", searchIdx);
            if (cmdStart == -1) break;

            int cmdEnd = jsonArray.indexOf("}", cmdStart);
            if (cmdEnd == -1) break;

            String cmdJson = jsonArray.substring(cmdStart, cmdEnd + 1);
            executeSingleCommand(cmdJson);

            searchIdx = cmdEnd + 1;
        }
    }

    void executeSingleCommand(const String& cmdJson) {
        String cmdId = _extractJsonString(cmdJson, "command_id");
        String action = _extractJsonString(cmdJson, "action");

        Serial.printf("[COMMAND] Received: ID=%s, Action=%s\n", cmdId.c_str(), action.c_str());
        _led->setPattern(PATTERN_COMMAND_EXEC);

        bool success = false;
        String message = "";

        if (action == "set_relay") {
            int relayNum = _extractJsonInt(cmdJson, "relay", 0);
            String stateStr = _extractJsonString(cmdJson, "state");
            bool state = (stateStr == "on" || stateStr == "1" || stateStr == "true");

            success = _relays->setRelay(relayNum, state);
            if (success) {
                message = "Relay " + String(relayNum) + " turned " + (state ? "ON" : "OFF");
                Serial.printf("[RELAY] %s\n", message.c_str());
                _display->showStatus("EXECUTED", message, _relays->getRelaysJson());
            } else {
                message = "Invalid relay index: " + String(relayNum);
            }
        } else if (action == "set_all_relays") {
            String stateStr = _extractJsonString(cmdJson, "state");
            bool state = (stateStr == "on" || stateStr == "1" || stateStr == "true");
            _relays->setAllRelays(state);
            success = true;
            message = "All relays turned " + String(state ? "ON" : "OFF");
            Serial.printf("[RELAY] %s\n", message.c_str());
            _display->showStatus("EXECUTED", message, _relays->getRelaysJson());
        } else if (action == "blink_led") {
            _led->setPattern(PATTERN_COMMAND_EXEC);
            success = true;
            message = "Blinking status LED";
        } else if (action == "ping") {
            success = true;
            message = "Pong from ESP32";
        } else {
            message = "Unknown action: " + action;
        }

        // Send ACK back to Central Brain
        sendAck(cmdId, success ? "success" : "error", message);
    }

    void sendAck(const String& cmdId, const String& status, const String& message) {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/" + cmdId + "/ack";

        _beginHttp(http, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(5000);

        String payload = "{";
        payload += "\"status\":\"" + status + "\",";
        payload += "\"message\":\"" + message + "\",";
        payload += "\"relays_state\":" + _relays->getRelaysJson();
        payload += "}";

        int httpCode = http.POST(payload);
        Serial.printf("[ACK] Sent for %s -> HTTP code %d\n", cmdId.c_str(), httpCode);
        http.end();
    }

    void sendChatToBrain(const String& prompt) {
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println(F("❌ Cannot send chat: ESP32 is not connected to Wi-Fi."));
            return;
        }

        Serial.println();
        Serial.println(F("--------------------------------------------------"));
        Serial.print(F("👤 YOU: "));
        Serial.println(prompt);
        Serial.println(F("⏳ Thinking with Gemini AI..."));
        _led->setPattern(PATTERN_COMMAND_EXEC);

        HTTPClient http;
        String url = String(BACKEND_BASE_URL) + "/api/v1/voice/interact";

        _beginHttp(http, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(25000); // 25s timeout for cloud LLM reasoning

        // Escape JSON quotes
        String cleanPrompt = prompt;
        cleanPrompt.replace("\"", "\\\"");

        String payload = "{\"text\":\"" + cleanPrompt + "\",\"robot_id\":\"" + ROBOT_ID + "\"}";

        int httpCode = http.POST(payload);
        if (httpCode == 200) {
            String respBody = http.getString();
            String aiResponse = _extractJsonString(respBody, "response_text");
            if (aiResponse.length() == 0) {
                aiResponse = respBody;
            }

            Serial.println();
            Serial.print(F("🤖 [GEMINI AI]: "));
            Serial.println(aiResponse);
            Serial.println(F("--------------------------------------------------"));
            _display->showStatus("GEMINI REPLIED", aiResponse, _relays->getRelaysJson());

            // Check if there was a hardware command dispatched
            int cmdStart = respBody.indexOf("\"command_dispatched\":{");
            if (cmdStart != -1) {
                int cmdEnd = respBody.indexOf("}", cmdStart);
                if (cmdEnd != -1) {
                    String cmdJson = respBody.substring(cmdStart + 21, cmdEnd + 1);
                    executeSingleCommand(cmdJson);
                }
            }
        } else {
            Serial.printf("❌ Backend chat error (HTTP %d)\n", httpCode);
        }
        http.end();
        _led->setPattern(PATTERN_ONLINE);
        Serial.println(F("\n💬 Type next question or command:"));
    }
};

#endif // ROBOT_NETWORK_CLIENT_H
