#!/usr/bin/env python3
"""
🤖 Business AI Robot — Laptop Virtual Peripherals Bridge

Provides temporary virtual hardware emulation for the robot while physical
components (microphone, speaker/amplifier, OLED, and relays) are in transit:
  • 🎤 Laptop Mic: Captures speech and sends to Central Brain
  • 🔊 Laptop Speaker: Speaks AI responses using native Windows TTS
  • 🖥️ Virtual OLED HUD: Renders a live 128x64 ASCII OLED display
  • ⚡ Physical Hardware Sync: Relays commands directly to the ESP32!
"""

import os
import sys
import time
import subprocess
import threading
from typing import Optional
import urllib.request
import json

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
ROBOT_ID = os.getenv("ROBOT_ID", "ROBOT-001")


def speak_text(text: str):
    """Speak text using native Windows speech synthesis without requiring external packages."""
    clean_text = text.replace('"', '\\"').replace("'", "")
    ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as e:
        print(f"[TTS Error] Could not synthesize audio: {e}")


def fetch_robot_status() -> dict:
    """Fetch real-time status of the physical ESP32 from the Central Brain."""
    url = f"{BACKEND_URL}/api/v1/robots/{ROBOT_ID}/status"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VirtualBridge/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return {"is_online": False, "relays_state": [0, 0, 0, 0], "wifi_rssi": None}


def send_voice_interact(text: str) -> dict:
    """Send voice query to Central Brain for Gemini reasoning and hardware dispatch."""
    url = f"{BACKEND_URL}/api/v1/voice/interact"
    payload = json.dumps({"text": text, "robot_id": ROBOT_ID}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "VirtualBridge/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def render_hud(robot_status: dict, last_input: str, last_response: str, state_tag: str):
    """Render the 128x64 Virtual OLED display frame in the terminal."""
    is_online = robot_status.get("is_online", False)
    rssi = robot_status.get("wifi_rssi")
    relays = robot_status.get("relays_state", [0, 0, 0, 0])
    
    online_str = "🟢 ONLINE" if is_online else "🔴 WAITING FOR ESP32"
    rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"

    r_tags = []
    for i, r in enumerate(relays, start=1):
        tag = f"R{i}:[ON ]" if r else f"R{i}:[OFF]"
        r_tags.append(tag)
    relays_line = "  ".join(r_tags)

    oled_box = f"""
    ┌────────────────────────────────────────────────────────┐
    │                🤖 BUSINESS AI ROBOT                    │
    │ ────────────────────────────────────────────────────── │
    │  Status: {online_str:<22} Wi-Fi: {rssi_str:<15} │
    │  State:  [{state_tag:<43}] │
    │                                                        │
    │  Relays: {relays_line:<44} │
    │                                                        │
    │  Last Input:  {last_input[:40]:<40} │
    │  Robot Voice: {last_response[:40]:<40} │
    └────────────────────────────────────────────────────────┘
    """
    print(oled_box)


def try_mic_listen() -> Optional[str]:
    """Attempt to capture speech from laptop microphone if SpeechRecognition is installed."""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            print("\n🎤 [MIC ACTIVE] Listening through laptop microphone... (Speak now!)")
            r.adjust_for_ambient_noise(source, duration=0.6)
            audio = r.listen(source, timeout=5, phrase_time_limit=8)
            print("⏳ [PROCESSING] Recognizing speech...")
            return r.recognize_google(audio)
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️ Mic capture note: {e}")
        return None


def main():
    print("\n" + "=" * 62)
    print(" 🤖 Business AI Robot — Virtual Peripherals & Hardware Bridge")
    print(f"    Target Robot ID: {ROBOT_ID} | Backend: {BACKEND_URL}")
    print("=" * 62)

    last_input = "System Booted"
    last_response = "Ready and waiting for commands."
    state = "READY"

    # Initial boot greeting
    threading.Thread(target=speak_text, args=("Robot brain online. Ready for commands.",), daemon=True).start()

    while True:
        status = fetch_robot_status()
        os.system("cls" if os.name == "nt" else "clear")
        render_hud(status, last_input, last_response, state)

        print("\nOptions:")
        print(" [1] Speak into Laptop Microphone (Press 1 or M)")
        print(" [2] Type Voice Command (e.g. 'Turn on relay 1', 'Turn off relay 2', 'Status')")
        print(" [3] Refresh Hardware Status")
        print(" [Q] Quit")

        try:
            choice = input("\nEnter your choice or command: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not choice:
            continue

        if choice.lower() in ["q", "quit", "exit"]:
            print("Exiting Virtual Bridge.")
            break

        state = "LISTENING..."
        user_text = ""

        if choice.lower() in ["1", "m", "mic"]:
            spoken = try_mic_listen()
            if spoken:
                user_text = spoken
                print(f"🗣️ You said: \"{user_text}\"")
            else:
                print("💡 Tip: Type your command below:")
                user_text = input("Say/Type to Robot: ").strip()
        elif choice in ["3", "r", "refresh"]:
            continue
        else:
            # Treat choice directly as the voice utterance!
            user_text = choice

        if not user_text:
            state = "READY"
            continue

        last_input = user_text
        state = "THINKING & DISPATCHING..."
        render_hud(status, last_input, "Processing...", state)

        try:
            interact_result = send_voice_interact(user_text)
            resp_text = interact_result.get("response_text", "Acknowledged.")
            last_response = resp_text
            state = "SPEAKING..."
            render_hud(fetch_robot_status(), last_input, last_response, state)

            # Speak out loud through laptop speaker
            speak_text(resp_text)

            state = "READY"

        except Exception as err:
            last_response = f"Error: {err}"
            state = "ERROR"
            print(f"❌ Backend connection failed: {err}")
            time.sleep(2)


if __name__ == "__main__":
    main()
