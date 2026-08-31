# task_runner.py
import sys
import io
import traceback

# --- Heavy Imports Pre-loaded Once at Startup ---
import os
import time
import json
import requests
from lucy_tts import speak

# Persistent global namespace for the runner environment
RUNNER_GLOBALS = {
    "speak": speak,
    "os": os,
    "time": time,
    "json": json,
    "requests": requests,
    "__builtins__": __builtins__,
}

def execute_code(script_content: str) -> str:
    """Runs code inside the pre-loaded environment and returns structured output."""
    stdout_capture = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = stdout_capture

    try:
        # Code executes inside the persistent RUNNER_GLOBALS dictionary
        exec(script_content, RUNNER_GLOBALS)
        output_str = stdout_capture.getvalue().replace("\x00", "").strip()
        
        return f"EXECUTION_STATUS=SUCCESS\nCOMMAND_EXIT_CODE=0\nSTDOUT_OUTPUT:\n{output_str or '[No output]'}"

    except Exception as e:
        output_str = stdout_capture.getvalue().replace("\x00", "").strip()
        exc_type, exc_obj, tb = sys.exc_info()
        
        # Extract precise line number and error category
        error_type = type(e).__name__
        line_num = "Unknown"
        
        # Parse traceback frames to find the exact line in the executed string
        tb_frames = traceback.extract_tb(tb)
        for frame in reversed(tb_frames):
            if frame.filename == "<string>":
                line_num = frame.lineno
                break

        full_traceback = traceback.format_exc()
        
        return (
            f"EXECUTION_STATUS=FAILED\n"
            f"COMMAND_EXIT_CODE=1\n"
            f"ERROR_TYPE={error_type}\n"
            f"ERROR_LINE={line_num}\n"
            f"STDOUT_OUTPUT:\n{output_str or '[No output]'}\n\n"
            f"FULL_TRACEBACK:\n{full_traceback}"
        )

    finally:
        sys.stdout = original_stdout