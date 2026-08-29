import logging
from RealtimeSTT import AudioToTextRecorder
import time

def live_speech_detected(text):
    print(f"\r[Live]: {text}", end="", flush=True)

def process_final_speech(text):
    print(f"\n[Final]: {text}\n")

if __name__ == "__main__":
    recorder = AudioToTextRecorder(
        level=logging.ERROR,
        model="tiny.en",
        realtime_model_type="tiny.en",
        language="en",
        enable_realtime_transcription=True,
        on_realtime_transcription_update=live_speech_detected,
#         fine tuning here
        realtime_processing_pause=0.02, # interval between live transcription checks
        post_speech_silence_duration=0.5,  # Wait 0.5s of silence before triggering 'final' callback
        min_length_of_recording=0.5,        # Ignore sound bursts under 0.5s
        silero_sensitivity=0.4             # Filter background noise
    )

    print("Listening with custom silence delay... (Ctrl+C to exit)")

    try:
        while True:
            recorder.text(process_final_speech)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.")