#ifndef STATUS_LED_H
#define STATUS_LED_H

#include <Arduino.h>
#include "config.h"

enum LedPattern {
    PATTERN_OFF,
    PATTERN_ON,
    PATTERN_CONNECTING,      // Fast flash (150ms)
    PATTERN_ONLINE,          // Solid ON
    PATTERN_COMMAND_EXEC,    // Rapid double-blink
    PATTERN_ERROR,           // Slow blink (1000ms)
    PATTERN_PROVISIONING     // SoftAP Provisioning pulse
};

class StatusLED {
private:
    uint8_t _pin;
    LedPattern _pattern;
    unsigned long _lastToggle;
    bool _state;
    int _blinkCount;

public:
    StatusLED(uint8_t pin = PIN_STATUS_LED) : _pin(pin), _pattern(PATTERN_OFF), _lastToggle(0), _state(false), _blinkCount(0) {}

    void begin() {
        pinMode(_pin, OUTPUT);
        digitalWrite(_pin, LOW);
    }

    void setPattern(LedPattern pattern) {
        if (_pattern != pattern) {
            _pattern = pattern;
            _lastToggle = millis();
            _blinkCount = 0;
            if (_pattern == PATTERN_ON || _pattern == PATTERN_ONLINE) {
                _state = true;
                digitalWrite(_pin, HIGH);
            } else if (_pattern == PATTERN_OFF) {
                _state = false;
                digitalWrite(_pin, LOW);
            }
        }
    }

    void update() {
        unsigned long now = millis();

        switch (_pattern) {
            case PATTERN_CONNECTING:
                if (now - _lastToggle >= 150) {
                    _lastToggle = now;
                    _state = !_state;
                    digitalWrite(_pin, _state ? HIGH : LOW);
                }
                break;

            case PATTERN_ONLINE:
                if (!_state) {
                    _state = true;
                    digitalWrite(_pin, HIGH);
                }
                break;

            case PATTERN_COMMAND_EXEC:
                if (now - _lastToggle >= 80) {
                    _lastToggle = now;
                    _state = !_state;
                    digitalWrite(_pin, _state ? HIGH : LOW);
                    _blinkCount++;
                    if (_blinkCount >= 6) { // 3 fast blinks
                        setPattern(PATTERN_ONLINE);
                    }
                }
                break;

            case PATTERN_ERROR:
                if (now - _lastToggle >= 1000) {
                    _lastToggle = now;
                    _state = !_state;
                    digitalWrite(_pin, _state ? HIGH : LOW);
                }
                break;

            case PATTERN_PROVISIONING:
                {
                    unsigned long cycle = (now - _lastToggle) % 800;
                    bool active = (cycle < 100) || (cycle >= 200 && cycle < 300);
                    if (_state != active) {
                        _state = active;
                        digitalWrite(_pin, _state ? HIGH : LOW);
                    }
                }
                break;

            case PATTERN_ON:
                digitalWrite(_pin, HIGH);
                break;

            case PATTERN_OFF:
            default:
                digitalWrite(_pin, LOW);
                break;
        }
    }
};

#endif // STATUS_LED_H
