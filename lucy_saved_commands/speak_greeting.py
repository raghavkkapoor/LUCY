"""
Lucy reusable speech helper.

Capability:
    speak(text)

Parameters:
    text (str):
        Text message to speak aloud.

Usage:
    Call speak("message") to provide audible feedback.
"""

def speak(text):
    import pyttsx3

    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()