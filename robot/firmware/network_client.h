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

    // Reusable HTTPS helper — creates WiFiClientSecure for Render HTTPS
    bool _beginHttp(HTTPClient& http, WiFiClientSecure& sec, const String& url, int timeoutMs) {
        sec.setInsecure();  // Skip certificate verification for Render
        sec.setTimeout(timeoutMs / 1000);
        http.setTimeout(timeoutMs);
        return http.begin(sec, url);
    }

    void _endHttp(HTTPClient& http, WiFiClientSecure& sec) {
        http.end();
        sec.stop();
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

    // Helper: Extract JSON number/float/int as String
    String _extractJsonNumber(const String& json, const String& key) {
        String searchKey = "\"" + key + "\":";
        int start = json.indexOf(searchKey);
        if (start == -1) return "";
        start += searchKey.length();
        while (start < json.length() && (json[start] == ' ' || json[start] == '\t')) start++;
        int end = start;
        while (end < json.length() && (isDigit(json[end]) || json[end] == '.' || json[end] == '-')) end++;
        if (start == end) return "";
        return json.substring(start, end);
    }

    // Translate HTTP error codes to friendly Hindi/Hinglish messages
    String _translateHttpError(int httpCode) {
        if (httpCode == -1 || httpCode == -11) {
            return "Server se connect hone mein thodi dikkat ho rahi hai. Ek baar phir try karein.";
        } else if (httpCode == 503 || httpCode == 504) {
            return "Backend server abhi busy hai, thodi der mein phir boliye.";
        } else if (httpCode == 408 || httpCode == -4) {
            return "Server ne response dene mein bahut time liya. Phir se try karein.";
        } else {
            return "Response lene mein issue aaya (Code " + String(httpCode) + "). Phir try karein.";
        }
    }

public:
    RobotNetworkClient(StatusLED* led, RelayController* relays, DisplayManager* display)
        : _led(led), _relays(relays), _display(display),
          _lastHeartbeatTime(0), _lastWifiCheckTime(0), _isConnected(false), _conversationId("") {}

    void resetConversation() {
        _conversationId = "";
        Serial.println(F("🔄 Conversation session reset."));
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
            _isConnected = false;
            Serial.println(F("\n❌ Wi-Fi Connection failed! Will retry..."));
            _display->showStatus("WIFI ERROR", "Failed to connect");
            _led->setPattern(PATTERN_ERROR);
        }
    }

    void update() {
        unsigned long now = millis();

        // Maintain Wi-Fi
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

        // Periodic Heartbeat & Command Polling
        if (_isConnected && (now - _lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS)) {
            _lastHeartbeatTime = now;
            sendHeartbeat();
        }
    }

    void sendHeartbeat() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/heartbeat";

        _beginHttp(http, sec, url, HTTP_TIMEOUT_HEARTBEAT);
        http.addHeader("Content-Type", "application/json");

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
                Serial.printf("[MAX] %d pending command(s) waiting! Fetching...\n", pendingCount);
                _endHttp(http, sec);
                fetchAndExecuteCommands();
                return;
            }
        } else if (httpCode > 0) {
            Serial.printf("[HEARTBEAT] HTTP %d\n", httpCode);
        }
        // Silently ignore negative codes for heartbeat (expected during cold start)
        _endHttp(http, sec);
    }

    void fetchAndExecuteCommands() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/pending";

        _beginHttp(http, sec, url, HTTP_TIMEOUT_COMMAND);

        int httpCode = http.GET();
        if (httpCode == 200) {
            String body = http.getString();
            if (body != "[]" && body.length() > 2) {
                Serial.printf("[CMD] Received: %s\n", body.c_str());
                int start = body.indexOf('{');
                int end = body.lastIndexOf('}');
                if (start != -1 && end != -1) {
                    String singleCmd = body.substring(start, end + 1);
                    executeSingleCommand(singleCmd);
                }
            }
        }
        _endHttp(http, sec);
    }

    void executeSingleCommand(const String& cmdJson) {
        String cmdId = _extractJsonString(cmdJson, "command_id");
        String action = _extractJsonString(cmdJson, "action");

        Serial.printf("[EXEC] Processing %s: %s\n", cmdId.c_str(), action.c_str());
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
                _display->showStatus("RELAY SWITCHED", message, _relays->getRelaysJson());
            } else {
                message = "Invalid relay index: " + String(relayNum);
            }
        } else if (action == "set_all_relays") {
            String stateStr = _extractJsonString(cmdJson, "state");
            bool state = (stateStr == "on" || stateStr == "1" || stateStr == "true");
            _relays->setAllRelays(state);
            success = true;
            message = "All relays set to " + String(state ? "ON" : "OFF");
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

        sendAck(cmdId, success ? "success" : "error", message);
    }

    void sendAck(const String& cmdId, const String& status, const String& message) {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/" + cmdId + "/ack";

        _beginHttp(http, sec, url, HTTP_TIMEOUT_ACK);
        http.addHeader("Content-Type", "application/json");

        String payload = "{";
        payload += "\"status\":\"" + status + "\",";
        payload += "\"message\":\"" + message + "\",";
        payload += "\"relays_state\":" + _relays->getRelaysJson();
        payload += "}";

        int httpCode = http.POST(payload);
        Serial.printf("[ACK] Sent for %s -> HTTP %d\n", cmdId.c_str(), httpCode);
        _endHttp(http, sec);
    }

    void sendChatToBrain(const String& prompt) {
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println(F("❌ Cannot send: WiFi disconnected."));
            return;
        }

        // Session reset triggers
        if (prompt.equalsIgnoreCase("new chat") || prompt.equalsIgnoreCase("reset")) {
            resetConversation();
            return;
        }

        Serial.println();
        Serial.println(F("========================================"));
        Serial.print(F("👤 YOU: "));
        Serial.println(prompt);

        // Start response timer
        unsigned long t0 = millis();

        Serial.println(F("⏳ MAX is thinking..."));
        _led->setPattern(PATTERN_COMMAND_EXEC);
        _display->showStatus("MAX THINKING...", prompt);

        HTTPClient http;
        WiFiClientSecure sec;
        String url = String(BACKEND_BASE_URL) + "/api/v1/voice/interact";

        _beginHttp(http, sec, url, HTTP_TIMEOUT_CHAT);
        http.addHeader("Content-Type", "application/json");

        // Escape JSON quotes
        String cleanPrompt = prompt;
        cleanPrompt.replace("\"", "\\\"");

        String payload = "{\"text\":\"" + cleanPrompt + "\",\"robot_id\":\"" + ROBOT_ID + "\"";
        if (_conversationId.length() > 0) {
            payload += ",\"conversation_id\":\"" + _conversationId + "\"";
        }
        payload += "}";

        int httpCode = http.POST(payload);
        unsigned long elapsed = millis() - t0;

        if (httpCode == 200) {
            String respBody = http.getString();
            String aiResponse = _extractJsonString(respBody, "response_text");
            if (aiResponse.length() == 0) {
                aiResponse = respBody;
            }

            // Retain persistent conversation_id
            String returnedConvId = _extractJsonString(respBody, "conversation_id");
            if (returnedConvId.length() > 0) {
                _conversationId = returnedConvId;
            }

            // Extract latency metrics from backend
            String totalMs = _extractJsonNumber(respBody, "total_ms");
            String fastPathMs = _extractJsonNumber(respBody, "fast_path_ms");
            String geminiMs = _extractJsonNumber(respBody, "gemini_ms");

            Serial.println();
            Serial.print(F("🤖 [MAX]: "));
            Serial.println(aiResponse);
            Serial.println();
            Serial.println(F("----------------------------------------"));
            Serial.printf( "⏱️  ROUND-TRIP TIME: %lu ms\n", elapsed);
            if (totalMs.length() > 0) {
                Serial.printf("    Backend Core: %s ms", totalMs.c_str());
                if (fastPathMs.length() > 0 && fastPathMs.toFloat() > 0) {
                    Serial.printf(" (⚡ Fast-Path: %s ms)", fastPathMs.c_str());
                } else if (geminiMs.length() > 0 && geminiMs.toFloat() > 0) {
                    Serial.printf(" (🧠 Gemini AI: %s ms)", geminiMs.c_str());
                }
                Serial.println();
            }
            Serial.println(F("========================================"));

            _display->showStatus("MAX REPLIED", aiResponse, _relays->getRelaysJson());

            // Check if there was a hardware command dispatched
            int cmdStart = respBody.indexOf("\"command_dispatched\":{");
            if (cmdStart != -1) {
                int cmdEnd = respBody.indexOf("}", cmdStart + 21);
                if (cmdEnd != -1) {
                    String cmdJson = respBody.substring(cmdStart + 21, cmdEnd + 1);
                    executeSingleCommand(cmdJson);
                }
            }
        } else {
            String friendlyErr = _translateHttpError(httpCode);
            Serial.println();
            Serial.printf("🤖 [MAX]: %s\n", friendlyErr.c_str());
            Serial.printf("⏱️  Failed after: %lums (HTTP %d)\n", elapsed, httpCode);
            Serial.println(F("========================================"));
            _display->showStatus("MAX NOTICE", friendlyErr);
        }

        _endHttp(http, sec);
        _led->setPattern(PATTERN_ONLINE);
        Serial.println(F("\n💬 Type next question or command:"));
    }
};

#endif // ROBOT_NETWORK_CLIENT_H
