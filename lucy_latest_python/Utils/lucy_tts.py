# only important EXACTLY what we need instead of entire modules.
from pyttsx3 import init
from sys import platform

def speak(text, rate=150, voice_actor="zira"):
    try:
        engine = init()
        voices = engine.getProperty('voices')
        # Loop through available voices to find Mira
        LUCY_VOICE_FOUND = False
        v_index = 0
        for voice in voices:
            if voice_actor.lower() in voice.name.lower():
                v_index = voice.id
                LUCY_VOICE_FOUND = True
                break

        if not LUCY_VOICE_FOUND:
            print(f"\nVoice actor {voice_actor} not found. You may need to install the language pack in your OS settings. Defaulting to index 0.")

        # Set speed/rate
        engine.setProperty('voice', v_index)
        engine.setProperty('rate', rate)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        print("Success: Content spoken.")
    except Exception as e:
        print(f"Error in TTS: {e}")

