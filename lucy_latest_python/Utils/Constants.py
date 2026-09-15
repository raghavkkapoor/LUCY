from pathlib import Path

# working legacy constants/prompts

PROJECT_DIR = Path.cwd()
PORT = 9223


MAGIC_STOP_WORD = "lucy_done_3030"
PROMPT_PREFIX = "Python code that can help with this request:\n"
PROMPT_SUFFIX = "\n\nIf browsing, open new windows/tabs in the playwright 9223 instance. Your script's timeout is 2 mins. You'll be thrown errors if/as they come up. Do NOT prematurely exit or claim success early. Always verify results through system state checks and what's on the user's screen without heavy screen capturing. Only output a separate response containing exclusively 'lucy_done_3030' after you're done."
CHROME_ACCOUNT_PAGE = "chrome://settings/people"
GEMINI_GEM_URL = "https://gemini.google.com/app"
# CHATGPT_URL = "https://chatgpt.com/c"
