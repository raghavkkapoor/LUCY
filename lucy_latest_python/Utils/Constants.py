from pathlib import Path

# working legacy prompts

MAGIC_STOP_WORD = "lucy_done_3030"
PROMPT_PREFIX = "Can you pass me python code that helps me with '"
PROMPT_SUFFIX = "'? - When browsing use playwright 9223 instance but always use a seperate tabs and don't touch gemini tabs with urls /usage and /app. Every script on my machine has a physical timeout of 2 mins max so be careful. You'll be thrown errors if/as they come up. Be curious and continuously try new approaches, work on the problem, fix it, improve it, repeat until its verified  by you properly. Once done, simply output a separate response containing only lucy_done_3030."


PORT = 9223
CHROME_ACCOUNT_PAGE = "chrome://settings/people"
GEMINI_GEM_URL = "https://gemini.google.com/app"
CHATGPT_URL = "https://chatgpt.com/c"
PROJECT_DIR = Path.cwd()