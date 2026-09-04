#ifndef RELAY_CONTROLLER_H
#define RELAY_CONTROLLER_H

#include <Arduino.h>
#include "config.h"

class RelayController {
private:
    uint8_t _pins[4];
    bool _states[4];
    bool _activeLow;

    uint8_t _pinState(bool on) const {
        if (_activeLow) {
            return on ? LOW : HIGH;
        } else {
            return on ? HIGH : LOW;
        }
    }

public:
    RelayController(bool activeLow = RELAY_ACTIVE_LOW) : _activeLow(activeLow) {
        _pins[0] = PIN_RELAY_1;
        _pins[1] = PIN_RELAY_2;
        _pins[2] = PIN_RELAY_3;
        _pins[3] = PIN_RELAY_4;

        for (int i = 0; i < 4; i++) {
            _states[i] = false;
        }
    }

    void begin() {
        for (int i = 0; i < 4; i++) {
            pinMode(_pins[i], OUTPUT);
            digitalWrite(_pins[i], _pinState(false)); // Safe initial OFF state
            _states[i] = false;
        }
    }

    bool setRelay(int relayNum, bool state) {
        if (relayNum < 1 || relayNum > 4) {
            return false;
        }
        int idx = relayNum - 1;
        _states[idx] = state;
        digitalWrite(_pins[idx], _pinState(state));
        return true;
    }

    void setAllRelays(bool state) {
        for (int i = 0; i < 4; i++) {
            _states[i] = state;
            digitalWrite(_pins[i], _pinState(state));
        }
    }

    bool getRelayState(int relayNum) const {
        if (relayNum < 1 || relayNum > 4) return false;
        return _states[relayNum - 1];
    }

    String getRelaysJson() const {
        String json = "[";
        for (int i = 0; i < 4; i++) {
            json += _states[i] ? "1" : "0";
            if (i < 3) json += ",";
        }
        json += "]";
        return json;
    }
};

#endif // RELAY_CONTROLLER_H
