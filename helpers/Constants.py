from pathlib import Path
from sys import platform

OPERATING_SYSTEM = platform # outputs 'win32', 'darwin' for macOS, 'linux', etc.


#TODO: Update instructions into a clean, structured markdown format with clear sections, bullet points, and examples. Ensure that the instructions are concise, easy to follow, and provide context for each step. Include any necessary prerequisites or dependencies, and provide links to relevant resources or documentation.


# working legacy prompts DO NOT CHANGE!!!
MAGIC_STOP_WORD = "lucy_done_3030"


PROMPT_PREFIX = "Can you pass me a python code block that helps me with '"


PROMPT_SUFFIX = f"'? - When browsing use playwright 9223 instance but always use a seperate tabs and don't touch gemini tabs with urls and /app. Every script has a timeout of 2 mins max. You'll be thrown errors if/as they come up. Be curious and continuously try new approaches, work on the problem, fix it, improve it, repeat until its verified by you properly. Once done, simply output a seperate response without codeblocks containing only {MAGIC_STOP_WORD}."

MAX_PROMPTS_PER_CHAT = 5
PORT = 9223
CHROME_ACCOUNT_PAGE = "chrome://settings/people"
GEMINI_GEM_URL = "https://gemini.google.com/app"
CHATGPT_URL = "https://chatgpt.com/c"

def FORM_CONTEXT_PROMPT(task, last_command_ran, last_command_output):
    return (
    f"{PROMPT_PREFIX}{task}{PROMPT_SUFFIX}\n\n"
    "IMPORTANT: This is a continuation in a fresh chat because the previous "
    "chat reached its prompt limit.\n\n"
    "LATEST PYTHON CODE THAT WAS EXECUTED:\n"
    "```python\n"
    f"{last_command_ran}\n"
    "```\n\n"
    "OUTPUT FROM THAT CODE:\n"
    f"{last_command_output}\n\n"
    "Continue working on the original task from this state. "
    "Do not restart the work from scratch."
    )