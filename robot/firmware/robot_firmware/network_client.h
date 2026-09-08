#ifndef ROBOT_NETWORK_CLIENT_H
#define ROBOT_NETWORK_CLIENT_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include "config.h"
#include "status_led.h"
#include "relay_controller.h"
#include "display_manager.h"

class RobotNetworkClient {
private:
    StatusLED* _led;
    RelayController* _relays;
    DisplayManager* _display;
    WebServer* _server;
    Preferences _prefs;

    RobotStartupState _state;
    String _currentSsid;
    String _currentPass;
    String _conversationId;

    unsigned long _lastHeartbeatTime;
    unsigned long _lastWifiCheckTime;
    unsigned long _lastHealthRetryTime;
    bool _isConnected;
    bool _isBackendHealthy;

    volatile bool _isSpeakerPlaying;
    volatile bool _bargeInTriggered;

    // Dual HTTP/HTTPS Transport Helper
    bool _beginHttp(HTTPClient& http, WiFiClientSecure& sec, WiFiClient& plain, const String& url, int timeoutMs) {
        http.setTimeout(timeoutMs);
        if (url.startsWith("https://")) {
            sec.setInsecure();  // Skip certificate verification for cloud
            sec.setTimeout(timeoutMs / 1000);
            return http.begin(sec, url);
        } else {
            plain.setTimeout(timeoutMs / 1000);
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

    // Helper: Extract JSON number/float as String
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
            return "Server se connection nahi hai.";
        } else if (httpCode == 503 || httpCode == 504) {
            return "Backend server abhi busy hai, thodi der mein phir boliye.";
        } else if (httpCode == 408 || httpCode == -4) {
            return "Server ne response dene mein bahut time liya. Phir se try karein.";
        } else {
            return "Server se connection nahi hai.";
        }
    }

    bool _handleOfflineFallback(const String& prompt) {
        String lower = prompt;
        lower.toLowerCase();
        lower.trim();

        if (lower.indexOf("relay 1 on") != -1 || lower.indexOf("light on") != -1) {
            _relays->setRelay(1, true);
            Serial.println(F("\n🤖 [MAX]: Light on kar di (Offline mode)."));
            _display->showStatus("OFFLINE CMD", "Light ON", _relays->getRelaysJson());
            return true;
        } else if (lower.indexOf("relay 1 off") != -1 || lower.indexOf("light off") != -1 || lower.indexOf("light band") != -1) {
            _relays->setRelay(1, false);
            Serial.println(F("\n🤖 [MAX]: Light band kar diya (Offline mode)."));
            _display->showStatus("OFFLINE CMD", "Light OFF", _relays->getRelaysJson());
            return true;
        } else if (lower.indexOf("relay 2 on") != -1 || lower.indexOf("fan on") != -1) {
            _relays->setRelay(2, true);
            Serial.println(F("\n🤖 [MAX]: Fan on kar diya (Offline mode)."));
            _display->showStatus("OFFLINE CMD", "Fan ON", _relays->getRelaysJson());
            return true;
        } else if (lower.indexOf("relay 2 off") != -1 || lower.indexOf("fan off") != -1 || lower.indexOf("fan band") != -1) {
            _relays->setRelay(2, false);
            Serial.println(F("\n🤖 [MAX]: Fan band kar diya (Offline mode)."));
            _display->showStatus("OFFLINE CMD", "Fan OFF", _relays->getRelaysJson());
            return true;
        }
        return false;
    }

public:
    RobotNetworkClient(StatusLED* led, RelayController* relays, DisplayManager* display)
        : _led(led), _relays(relays), _display(display), _server(nullptr),
          _state(STATE_BOOTING), _conversationId(""),
          _lastHeartbeatTime(0), _lastWifiCheckTime(0), _lastHealthRetryTime(0),
          _isConnected(false), _isBackendHealthy(false),
          _isSpeakerPlaying(false), _bargeInTriggered(false) {}

    RobotStartupState getState() const {
        return _state;
    }

    String getStateName() const {
        switch (_state) {
            case STATE_BOOTING:             return "BOOTING";
            case STATE_WIFI_CONNECTING:     return "WIFI_CONNECTING";
            case STATE_WIFI_CONNECTED:      return "WIFI_CONNECTED";
            case STATE_PROVISIONING:        return "PROVISIONING";
            case STATE_BACKEND_CONNECTING:  return "BACKEND_CONNECTING";
            case STATE_BACKEND_CONNECTED:   return "BACKEND_CONNECTED";
            case STATE_READY:               return "READY";
            case STATE_RECONNECTING:        return "RECONNECTING";
            case STATE_ERROR:               return "ERROR";
            default:                        return "UNKNOWN";
        }
    }

    // --- Wi-Fi Credentials Storage (ESP32 NVS) ---
    void loadWifiCredentials() {
        _prefs.begin("robot_wifi", true);
        _currentSsid = _prefs.getString("ssid", "");
        _currentPass = _prefs.getString("pass", "");
        _prefs.end();

        if (_currentSsid.length() == 0) {
            _currentSsid = WIFI_SSID_DEFAULT;
            _currentPass = WIFI_PASSWORD_DEFAULT;
            Serial.println(F("[WIFI] Using default development credentials."));
        } else {
            Serial.printf("[WIFI] Loaded saved credentials from NVS (SSID: %s)\n", _currentSsid.c_str());
        }
    }

    void saveWifiCredentials(const String& ssid, const String& pass) {
        _prefs.begin("robot_wifi", false);
        _prefs.putString("ssid", ssid);
        _prefs.putString("pass", pass);
        _prefs.end();
        _currentSsid = ssid;
        _currentPass = pass;
        Serial.printf("[WIFI] Saved credentials for SSID '%s' to NVS.\n", ssid.c_str());
    }

    void clearWifiCredentials() {
        _prefs.begin("robot_wifi", false);
        _prefs.clear();
        _prefs.end();
        _currentSsid = WIFI_SSID_DEFAULT;
        _currentPass = WIFI_PASSWORD_DEFAULT;
        Serial.println(F("[WIFI] Cleared saved credentials. Reset to default."));
    }

    // --- Wi-Fi Connection Routine ---
    bool connectWifi() {
        _state = STATE_WIFI_CONNECTING;
        _led->setPattern(PATTERN_CONNECTING);
        _display->showStatus("WIFI CONNECTING", _currentSsid);

        Serial.printf("[WIFI] Connecting to '%s'...\n", _currentSsid.c_str());

        WiFi.mode(WIFI_STA);
        WiFi.begin(_currentSsid.c_str(), _currentPass.c_str());

        unsigned long startAttempt = millis();
        while (WiFi.status() != WL_CONNECTED && (millis() - startAttempt < WIFI_CONNECT_TIMEOUT_MS)) {
            delay(400);
            _led->update();
            Serial.print(F("."));
        }
        Serial.println();

        if (WiFi.status() == WL_CONNECTED) {
            _state = STATE_WIFI_CONNECTED;
            _isConnected = true;
            Serial.println(F("[WIFI] Connected"));
            Serial.print(F("[WIFI] IP Address: "));
            Serial.println(WiFi.localIP());
            Serial.printf("[WIFI] RSSI: %d dBm\n", WiFi.RSSI());

            _display->showStatus("WIFI CONNECTED", WiFi.localIP().toString(), _relays->getRelaysJson());
            return true;
        } else {
            _isConnected = false;
            Serial.printf("[WIFI] Failed to connect to '%s' within %d seconds.\n",
                          _currentSsid.c_str(), WIFI_CONNECT_TIMEOUT_MS / 1000);
            return false;
        }
    }

    // --- SoftAP Wi-Fi Provisioning Portal (No Laptop Needed at Exhibition) ---
    void startProvisioningAP() {
        _state = STATE_PROVISIONING;
        _led->setPattern(PATTERN_PROVISIONING);
        _display->showStatus("WIFI SETUP AP", AP_SSID);

        WiFi.mode(WIFI_AP);
        WiFi.softAP(AP_SSID, AP_PASSWORD);
        IPAddress apIP(192, 168, 4, 1);
        WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));

        Serial.println();
        Serial.println(F("=================================================="));
        Serial.println(F(" 📶 EXHIBITION WI-FI SETUP HOTSPOT ACTIVE!"));
        Serial.printf( F(" 1. Connect phone/laptop to Wi-Fi: %s\n"), AP_SSID);
        Serial.printf( F(" 2. Password: %s\n"), AP_PASSWORD);
        Serial.println(F(" 3. Open browser to: http://192.168.4.1"));
        Serial.println(F(" 4. Select your Wi-Fi/Hotspot & enter password."));
        Serial.println(F("=================================================="));

        if (_server != nullptr) {
            delete _server;
        }
        _server = new WebServer(80);

        _server->on("/", HTTP_GET, [this]() {
            int n = WiFi.scanNetworks();
            String html = F("<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'>");
            html += F("<title>MAX Robot Wi-Fi Setup</title><style>");
            html += F("body{font-family:Arial,sans-serif;margin:0;padding:20px;background:#0d1117;color:#c9d1d9;}");
            html += F(".card{max-width:400px;margin:auto;background:#161b22;padding:24px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.5);}");
            html += F("h2{color:#58a6ff;text-align:center;margin-top:0;}p{color:#8b949e;text-align:center;font-size:14px;}");
            html += F("label{font-weight:bold;font-size:13px;display:block;margin-top:12px;margin-bottom:4px;}");
            html += F("input,select{width:100%;padding:10px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#fff;box-sizing:border-box;}");
            html += F("button{width:100%;margin-top:20px;padding:12px;background:#238636;color:#fff;font-weight:bold;border:none;border-radius:6px;cursor:pointer;}");
            html += F(".badge{display:inline-block;padding:2px 8px;border-radius:10px;background:#1f6feb;font-size:12px;margin-bottom:12px;}");
            html += F("</style></head><body><div class='card'>");
            html += F("<h2>🤖 MAX AI Robot</h2>");
            html += F("<p>Exhibition Standalone Wi-Fi Setup</p>");
            html += F("<form method='POST' action='/save'>");
            html += F("<label>Select Wi-Fi Network (SSID):</label>");
            html += F("<select name='ssid'>");
            if (n == 0) {
                html += F("<option value=''>No networks found. Enter manually below.</option>");
            } else {
                for (int i = 0; i < n; ++i) {
                    html += "<option value='" + WiFi.SSID(i) + "'>" + WiFi.SSID(i) + " (" + String(WiFi.RSSI(i)) + " dBm)</option>";
                }
            }
            html += F("</select>");
            html += F("<label>Or Enter Custom SSID (Phone Hotspot):</label>");
            html += F("<input type='text' name='custom_ssid' placeholder='Hotspot SSID'>");
            html += F("<label>Wi-Fi Password:</label>");
            html += F("<input type='password' name='pass' placeholder='Enter password'>");
            html += F("<button type='submit'>Save & Connect Robot</button>");
            html += F("</form></div></body></html>");
            _server->send(200, "text/html", html);
        });

        _server->on("/save", HTTP_POST, [this]() {
            String ssid = _server->arg("custom_ssid");
            ssid.trim();
            if (ssid.length() == 0) {
                ssid = _server->arg("ssid");
            }
            String pass = _server->arg("pass");

            String resp = F("<!DOCTYPE html><html><body style='font-family:Arial;background:#0d1117;color:#fff;text-align:center;padding:40px;'>");
            resp += "<h2>Credentials Saved!</h2>";
            resp += "<p>Connecting to: <b>" + ssid + "</b>...</p>";
            resp += "<p>Robot will restart Wi-Fi and verify cloud backend.</p>";
            resp += "</body></html>";
            _server->send(200, "text/html", resp);
            delay(1000);

            saveWifiCredentials(ssid, pass);
            stopProvisioningAP();
            connectWifi();
            if (_isConnected) {
                verifyBackendHealth(true);
            }
        });

        _server->begin();
    }

    void stopProvisioningAP() {
        if (_server != nullptr) {
            _server->stop();
            delete _server;
            _server = nullptr;
        }
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_STA);
    }

    // --- Backend Health Check & Warm-up Routine ---
    bool verifyBackendHealth(bool allowWarmupWait = true) {
        if (WiFi.status() != WL_CONNECTED) {
            _state = STATE_RECONNECTING;
            return false;
        }

        _state = STATE_BACKEND_CONNECTING;
        _led->setPattern(PATTERN_CONNECTING);
        _display->showStatus("BACKEND CONNECTING", BACKEND_BASE_URL);

        Serial.println(F("[BACKEND] Connecting..."));

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/health";

        unsigned long startCheck = millis();
        unsigned long timeoutLimit = allowWarmupWait ? 50000 : HTTP_TIMEOUT_HEALTH;
        bool isHealthy = false;

        while (!isHealthy && (millis() - startCheck < timeoutLimit)) {
            _beginHttp(http, sec, plain, url, HTTP_TIMEOUT_HEALTH);
            int httpCode = http.GET();

            if (httpCode == 200) {
                String body = http.getString();
                if (body.indexOf("\"status\":\"ok\"") != -1 || body.indexOf("\"status\"") != -1) {
                    isHealthy = true;
                    _endHttp(http, sec, plain);
                    break;
                }
            } else if (allowWarmupWait) {
                Serial.printf("[BACKEND] Waiting for server warm-up (HTTP %d)... retrying\n", httpCode);
                delay(HEALTH_RETRY_INTERVAL_MS);
            }
            _endHttp(http, sec, plain);

            if (!allowWarmupWait) {
                break;
            }
        }

        if (isHealthy) {
            _state = STATE_BACKEND_CONNECTED;
            _isBackendHealthy = true;
            Serial.println(F("[BACKEND] Connected"));
            Serial.println(F("[BACKEND] Health check OK"));

            _state = STATE_READY;
            Serial.println(F("[ROBOT] READY"));

            _led->setPattern(PATTERN_ONLINE);
            _display->showStatus("READY", "MAX Online", _relays->getRelaysJson());

            announceStartupReady();
            return true;
        } else {
            _isBackendHealthy = false;
            _state = STATE_RECONNECTING;
            Serial.println(F("[BACKEND] Health check failed or timed out. Will retry in background."));
            _led->setPattern(PATTERN_ERROR);
            _display->showStatus("BACKEND RETRY", "Waiting for server...");
            return false;
        }
    }

    void announceStartupReady() {
        Serial.println(F("\n🔊 [VOICE]: \"Namaste! Main ready hoon.\""));
        _display->showStatus("MAX READY", STARTUP_SPEECH_TEXT, _relays->getRelaysJson());
    }

    // --- Main Initialization ---
    void begin() {
        _state = STATE_BOOTING;
        Serial.println(F("[BOOT] Initializing robot..."));

        loadWifiCredentials();

        // Attempt saved or default Wi-Fi
        if (!connectWifi()) {
            // Wi-Fi failed -> start SoftAP provisioning hotspot
            startProvisioningAP();
            return;
        }

        // Wi-Fi succeeded -> verify backend health & declare READY
        verifyBackendHealth(true);
    }

    // --- Non-blocking Update Loop ---
    void update() {
        unsigned long now = millis();

        // 1. SoftAP Provisioning Mode
        if (_state == STATE_PROVISIONING && _server != nullptr) {
            _server->handleClient();
            return;
        }

        // 2. Wi-Fi Reconnection & Maintenance
        if (now - _lastWifiCheckTime >= WIFI_RETRY_INTERVAL_MS) {
            _lastWifiCheckTime = now;
            if (WiFi.status() != WL_CONNECTED) {
                _isConnected = false;
                _state = STATE_RECONNECTING;
                _led->setPattern(PATTERN_CONNECTING);
                Serial.println(F("[WIFI] Disconnected! Reconnecting..."));
                WiFi.reconnect();
                return;
            } else if (!_isConnected) {
                _isConnected = true;
                Serial.println(F("[WIFI] Reconnected successfully!"));
                verifyBackendHealth(false);
            }
        }

        // 3. Backend Health Recovery (if Wi-Fi is OK but backend was offline)
        if (_isConnected && !_isBackendHealthy && (now - _lastHealthRetryTime >= HEALTH_RETRY_INTERVAL_MS)) {
            _lastHealthRetryTime = now;
            verifyBackendHealth(false);
        }

        // 4. Periodic Heartbeat & Command Polling (keeps Render service warm)
        if (_isConnected && _isBackendHealthy && (now - _lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS)) {
            _lastHeartbeatTime = now;
            sendHeartbeat();
        }
    }

    void triggerBargeIn() {
        if (_isSpeakerPlaying) {
            _bargeInTriggered = true;
            _isSpeakerPlaying = false;
        }
    }

    void stopSpeakerPlayback() {
        _isSpeakerPlaying = false;
        _bargeInTriggered = true;
    }

    void resetConversation() {
        _conversationId = "";
        Serial.println(F("🔄 Conversation session reset."));
    }

    String getConversationId() const {
        return _conversationId;
    }

    void sendHeartbeat() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/heartbeat";

        _beginHttp(http, sec, plain, url, HTTP_TIMEOUT_HEARTBEAT);
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
                _endHttp(http, sec, plain);
                fetchAndExecuteCommands();
                return;
            }
        }
        _endHttp(http, sec, plain);
    }

    void fetchAndExecuteCommands() {
        if (WiFi.status() != WL_CONNECTED) return;

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/pending";

        _beginHttp(http, sec, plain, url, HTTP_TIMEOUT_COMMAND);

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
        _endHttp(http, sec, plain);
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
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/robots/" + ROBOT_ID + "/commands/" + cmdId + "/ack";

        _beginHttp(http, sec, plain, url, HTTP_TIMEOUT_ACK);
        http.addHeader("Content-Type", "application/json");

        String payload = "{";
        payload += "\"status\":\"" + status + "\",";
        payload += "\"message\":\"" + message + "\",";
        payload += "\"relays_state\":" + _relays->getRelaysJson();
        payload += "}";

        int httpCode = http.POST(payload);
        Serial.printf("[ACK] Sent for %s -> HTTP %d\n", cmdId.c_str(), httpCode);
        _endHttp(http, sec, plain);
    }

    // --- Voice & Chat Interaction Handler ---
    void sendChatToBrain(const String& prompt) {
        // Handle special serial commands
        if (prompt.equalsIgnoreCase("status")) {
            Serial.println();
            Serial.println(F("========================================"));
            Serial.printf( "🤖 ROBOT STATUS: %s\n", getStateName().c_str());
            Serial.printf( "   Environment: %s\n", USE_PRODUCTION_CLOUD ? "PRODUCTION (Render Cloud)" : "DEVELOPMENT (Local PC)");
            Serial.printf( "   Backend URL: %s\n", BACKEND_BASE_URL);
            Serial.printf( "   Wi-Fi SSID:  %s (%d dBm)\n", _currentSsid.c_str(), WiFi.RSSI());
            Serial.printf( "   Local IP:    %s\n", WiFi.localIP().toString().c_str());
            Serial.printf( "   Uptime:      %lu seconds\n", millis() / 1000);
            Serial.printf( "   Relays:      %s\n", _relays->getRelaysJson().c_str());
            Serial.println(F("========================================"));
            Serial.println(F("\n💬 Type next question or command:"));
            return;
        }

        if (prompt.equalsIgnoreCase("reset wifi") || prompt.equalsIgnoreCase("wifi reset")) {
            clearWifiCredentials();
            startProvisioningAP();
            return;
        }

        if (prompt.startsWith("wifi ") || prompt.startsWith("WIFI ")) {
            int space1 = prompt.indexOf(' ');
            int space2 = prompt.indexOf(' ', space1 + 1);
            if (space2 != -1) {
                String newSsid = prompt.substring(space1 + 1, space2);
                String newPass = prompt.substring(space2 + 1);
                newSsid.trim();
                newPass.trim();
                saveWifiCredentials(newSsid, newPass);
                Serial.printf("[WIFI] Reconnecting to '%s'...\n", newSsid.c_str());
                connectWifi();
                if (_isConnected) {
                    verifyBackendHealth(true);
                }
                return;
            }
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

        // Check Barge-in command
        String lower = prompt;
        lower.toLowerCase();
        lower.trim();
        if (lower == "ruko" || lower == "stop" || lower == "chup" || lower == "shant" || lower == "arre ruko") {
            triggerBargeIn();
            Serial.println(F("\n🛑 [BARGE-IN]: Playback cancelled immediately."));
            _display->showStatus("INTERRUPTED", "Audio Stopped");
            Serial.println(F("\n💬 Type next question or command:"));
            return;
        }

        // Check offline fallback
        if (WiFi.status() != WL_CONNECTED || !_isBackendHealthy) {
            if (_handleOfflineFallback(prompt)) {
                Serial.println(F("\n💬 Type next question or command:"));
                return;
            }
            Serial.println(F("\n🤖 [MAX]: Server se connection nahi hai."));
            _display->showStatus("OFFLINE", "Server se connection nahi hai.");
            Serial.println(F("\n💬 Type next question or command:"));
            return;
        }

        // Start response timer
        unsigned long t0 = millis();

        Serial.println(F("⏳ MAX is thinking..."));
        _led->setPattern(PATTERN_COMMAND_EXEC);
        _display->showStatus("MAX THINKING...", prompt);

        HTTPClient http;
        WiFiClientSecure sec;
        WiFiClient plain;
        String url = String(BACKEND_BASE_URL) + "/api/v1/voice/interact";

        _beginHttp(http, sec, plain, url, HTTP_TIMEOUT_CHAT);
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

        _endHttp(http, sec, plain);
        _led->setPattern(PATTERN_ONLINE);
        Serial.println(F("\n💬 Type next question or command:"));
    }
};

#endif // ROBOT_NETWORK_CLIENT_H
