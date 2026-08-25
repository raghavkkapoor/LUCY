$ErrorActionPreference = 'Stop'

# Verified workflow:
# 1. Connect to Lucy's authenticated visible Chrome on CDP 9223.
# 2. Read its normal browser UA and ChatGPT/OpenAI cookies in memory.
# 3. Start isolated Chrome with --headless=new on CDP 9333.
# 4. Match the visible browser UA.
# 5. Inject authenticated ChatGPT session cookies.
# 6. Read/control the JavaScript-rendered ChatGPT DOM via Playwright CDP.
#
# The actual validated probe is stored alongside this script.

$probe = Join-Path $PSScriptRoot "headless_chatgpt_probe.py"
if (-not (Test-Path $probe)) {
    throw "Probe file missing: $probe"
}
python $probe
