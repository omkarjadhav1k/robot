#ifndef DISPLAY_MANAGER_H
#define DISPLAY_MANAGER_H

#include <Arduino.h>
#include "config.h"

#if !VIRTUAL_DISPLAY_MODE
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#endif

class DisplayManager {
private:
    bool _virtualMode;
    String _currentStatus;
    String _subMessage;

#if !VIRTUAL_DISPLAY_MODE
    Adafruit_SSD1306 _oled;
#endif

public:
    DisplayManager(bool virtualMode = VIRTUAL_DISPLAY_MODE)
        : _virtualMode(virtualMode), _currentStatus("INITIALIZING"), _subMessage("")
#if !VIRTUAL_DISPLAY_MODE
        , _oled(OLED_SCREEN_WIDTH, OLED_SCREEN_HEIGHT, &Wire, -1)
#endif
    {}

    void begin() {
        if (_virtualMode) {
            Serial.println(F("[DISPLAY] Running in VIRTUAL DISPLAY MODE."));
            Serial.println(F("[DISPLAY] Output mirrored to Serial & Virtual Laptop HUD."));
        } else {
#if !VIRTUAL_DISPLAY_MODE
            Wire.begin(PIN_OLED_SDA, PIN_OLED_SCL);
            if (!_oled.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS)) {
                Serial.println(F("[DISPLAY] ERROR: SSD1306 OLED allocation failed!"));
            } else {
                _oled.clearDisplay();
                _oled.setTextSize(1);
                _oled.setTextColor(SSD1306_WHITE);
                _oled.setCursor(0, 0);
                _oled.println(F("BUSINESS AI ROBOT"));
                _oled.display();
            }
#endif
        }
    }

    void showStatus(const String& status, const String& subMsg = "", const String& relays = "") {
        _currentStatus = status;
        _subMessage = subMsg;

        if (_virtualMode) {
            Serial.println(F("========================================"));
            Serial.print(F(" 🤖 [VIRTUAL OLED] "));
            Serial.println(status);
            if (subMsg.length() > 0) {
                Serial.print(F("    Info: "));
                Serial.println(subMsg);
            }
            if (relays.length() > 0) {
                Serial.print(F("    Relays: "));
                Serial.println(relays);
            }
            Serial.println(F("========================================"));
        } else {
#if !VIRTUAL_DISPLAY_MODE
            _oled.clearDisplay();
            _oled.setTextSize(1);
            _oled.setCursor(0, 0);
            _oled.println(F("BUSINESS AI ROBOT"));
            _oled.drawLine(0, 10, 128, 10, SSD1306_WHITE);

            _oled.setTextSize(2);
            _oled.setCursor(0, 16);
            _oled.println(status);

            _oled.setTextSize(1);
            _oled.setCursor(0, 38);
            if (subMsg.length() > 0) {
                _oled.println(subMsg);
            }

            if (relays.length() > 0) {
                _oled.setCursor(0, 50);
                _oled.println(relays);
            }
            _oled.display();
#endif
        }
    }
};

#endif // DISPLAY_MANAGER_H
