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
    String _conversationId;

    bool _beginHttp(HTTPClient& http, WiFiClientSecure& sec, WiFiClient& plain, const String& url) {
        if (url.startsWith("https://")) {
            sec.setInsecure();
            sec.setTimeout(15);
            return http.begin(sec, url);
        } else {
            plain.setTimeout(10);
            return http.begin(plain, url);
        }
    }

    void _endHttp(HTTPClient& http, WiFiClientSecure& sec, WiFiClient& plain) {
        http.end();
        sec.stop();
        plain.stop();
    }

    // Helper: Extract JSON string value by key
    String _extractJsonString(const String& json, const String& key) {
        String searchKey = "\"" + key + "\":\"";
        int start = json.indexOf(searchKey);
        if (start == -1) return "";
        start += searchKey.length();
        int end = start;
        while (end < json.length()) {
            if (json[end] == '"' && json[end - 1] != '\\') break;
            end++;
        }
        if (end >= json.length()) return "";
        String val = json.substring(start, end);
        val.replace("\\\"", "\"");
        val.replace("\\n", " ");
        val.replace("\\r", "");
        val.replace("\\\\", "\\");
        return val;
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
          _lastHeartbeatTime(0), _lastWifiCheckTime(0), _isConnected(false), _conversationId("") {}

    void resetConversation() {
        _conversationId = "";
        Serial.println(F("🔄 Conversation session reset on ESP32."));
    }

    String getConversationId() const {
        return _conversationId;
    }

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
            _display->showStatus("ONLINE", WiFi.localIP().toString(), _relays->getRelaysJson());
            _led->setPattern(PATTERN_ONLINE);
        } else {
            Serial.println(F("\n❌ Wi-Fi Connection failed!"));
            _display->showStatus("WIFI ERROR", "Failed to connect");
            _led->setPattern(PATTERN_ERROR);
        }
    }

    void update() {
        if (WiFi.status() != WL_CONNECTED) {
            _isConnected = false;
            unsigned long now = millis();
            if (now - _lastWifiCheckTime > 5000) {
                _lastWifiCheckTime = now;
                Serial.println(F("[WIFI] Disconnected! Reconnecting..."));
                WiFi.reconnect();
            }
            return;
        }

        _isConnected = true;
        unsigned long now = millis();

        // Send Heartbeat periodically
        if (now - _lastHeartbeatTime > HEARTBEAT_INTERVAL_MS || _lastHeartbeatTime == 0) {
            _lastHeartbeatTime = now;
            sendHeartbeat();
            pollPendingCommands();
        }
    }

    void sendHeartbeat() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/heartbeat";

        _beginHttp(http, sec, plain, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(12000);

        String payload = "{";
        payload += "\"robot_id\":\"" + String(ROBOT_ID) + "\",";
        payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\",";
        payload += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
        payload += "\"uptime_seconds\":" + String(millis() / 1000) + ",";
        payload += "\"relays_state\":" + _relays->getRelaysJson() + ",";
        payload += "\"peripherals\":{\"mic\":\"ok\",\"speaker\":\"ok\",\"oled\":\"ok\",\"relays\":\"ok\"}";
        payload += "}";

        int httpCode = http.POST(payload);
        if (httpCode != 200) {
            Serial.printf("[HEARTBEAT] POST failed with HTTP code: %d\n", httpCode);
        }
        _endHttp(http, sec, plain);
    }

    void pollPendingCommands() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/pending";

        _beginHttp(http, sec, plain, url);
        http.setTimeout(10000);

        int httpCode = http.GET();
        if (httpCode == 200) {
            String payload = http.getString();
            if (payload != "[]" && payload.length() > 2) {
                Serial.printf("[CMD] Received command payload: %s\n", payload.c_str());
                int start = payload.indexOf('{');
                int end = payload.lastIndexOf('}');
                if (start != -1 && end != -1) {
                    String singleCmd = payload.substring(start, end + 1);
                    executeSingleCommand(singleCmd);
                }
            }
        }
        _endHttp(http, sec, plain);
    }

    void executeSingleCommand(const String& cmdJson) {
        String cmdId = _extractJsonString(cmdJson, "command_id");
        String action = _extractJsonString(cmdJson, "action");

        Serial.printf("[EXEC] Processing command %s: %s\n", cmdId.c_str(), action.c_str());
        bool success = false;
        String message = "";

        if (action == "set_relay") {
            int relay = _extractJsonInt(cmdJson, "relay", 1);
            String state = _extractJsonString(cmdJson, "state");
            bool turnOn = (state == "on" || state == "1" || state == "true");
            _relays->setRelay(relay, turnOn);
            success = true;
            message = "Relay " + String(relay) + " set to " + (turnOn ? "ON" : "OFF");
            _display->showStatus("RELAY SWITCHED", message, _relays->getRelaysJson());
        } else if (action == "set_all_relays") {
            String state = _extractJsonString(cmdJson, "state");
            bool turnOn = (state == "on" || state == "1" || state == "true");
            _relays->setAllRelays(turnOn);
            success = true;
            message = "All relays set to " + String(turnOn ? "ON" : "OFF");
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
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/" + cmdId + "/ack";

        _beginHttp(http, sec, plain, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(12000);

        String payload = "{";
        payload += "\"status\":\"" + status + "\",";
        payload += "\"message\":\"" + message + "\",";
        payload += "\"relays_state\":" + _relays->getRelaysJson();
        payload += "}";

        int httpCode = http.POST(payload);
        Serial.printf("[ACK] Sent for %s -> HTTP code %d\n", cmdId.c_str(), httpCode);
        _endHttp(http, sec, plain);
    }

    void sendChatToBrain(const String& prompt) {
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println(F("❌ Cannot send chat: ESP32 is not connected to Wi-Fi."));
            return;
        }

        // Check for session reset trigger
        if (prompt.equalsIgnoreCase("new chat") || prompt.equalsIgnoreCase("reset")) {
            resetConversation();
            return;
        }

        Serial.println();
        Serial.println(F("--------------------------------------------------"));
        Serial.print(F("👤 YOU: "));
        Serial.println(prompt);
        Serial.println(F("⏳ Thinking with Gemini AI..."));
        _led->setPattern(PATTERN_COMMAND_EXEC);

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/voice/interact";

        _beginHttp(http, sec, plain, url);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(30000); // 30s timeout for cloud LLM reasoning

        // Escape JSON quotes
        String cleanPrompt = prompt;
        cleanPrompt.replace("\"", "\\\"");

        String payload = "{\"text\":\"" + cleanPrompt + "\",\"robot_id\":\"" + ROBOT_ID + "\"";
        if (_conversationId.length() > 0) {
            payload += ",\"conversation_id\":\"" + _conversationId + "\"";
        }
        payload += "}";

        int httpCode = http.POST(payload);
        if (httpCode == 200) {
            String respBody = http.getString();
            String aiResponse = _extractJsonString(respBody, "response_text");
            if (aiResponse.length() == 0) {
                aiResponse = respBody;
            }

            // Retain persistent conversation_id from response
            String returnedConvId = _extractJsonString(respBody, "conversation_id");
            if (returnedConvId.length() > 0) {
                _conversationId = returnedConvId;
            }

            // Extract TTS audio stream URL
            String audioUrl = _extractJsonString(respBody, "audio_url");
            if (audioUrl.length() > 0) {
                Serial.printf("🔊 [SPEAKER AUDIO READY]: %s%s\n", BACKEND_BASE_URL, audioUrl.c_str());
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
        _endHttp(http, sec, plain);
        _led->setPattern(PATTERN_ONLINE);
        Serial.println(F("\n💬 Type next question or command:"));
    }
};

#endif // ROBOT_NETWORK_CLIENT_H
