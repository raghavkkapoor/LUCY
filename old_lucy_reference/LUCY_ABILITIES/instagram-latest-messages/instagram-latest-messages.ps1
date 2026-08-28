$ErrorActionPreference = "Stop"

$root = "C:\Users\ragha\Downloads\LUCY\LucyPython"
$adb = Join-Path $root "LUCY_ABILITIES\android-adb\platform-tools\adb.exe"
$serial = "172.16.0.26:42251"
$pyFile = Join-Path $env:TEMP "lucy_instagram_latest_messages.py"

if (-not (Test-Path $adb)) {
    throw "ADB not found."
}

& py -c "import uiautomator2 as u2; d=u2.connect('172.16.0.26:42251'); print('U2_READY=True')" | Out-Null

& $adb -s $serial shell am start -W -n "com.instagram.android/.activity.MainTabActivity" | Out-Null
Start-Sleep -Seconds 3

$python = @'
import re
import time
import uiautomator2 as u2

d = u2.connect("172.16.0.26:42251")
time.sleep(1)

xml = d.dump_hierarchy(compressed=False)

def extract(xml):
    out = []
    for m in re.finditer(r'<node\b([^>]*)', xml):
        attrs = m.group(1)

        def attr(name):
            x = re.search(rf'{re.escape(name)}="([^"]*)"', attrs)
            return x.group(1) if x else ""

        text = attr("text").strip()
        desc = attr("content-desc").strip()
        bounds = attr("bounds")

        if text or desc:
            out.append((text, desc, bounds))

    return out

nodes = extract(xml)
joined = "\n".join((t + " " + d) for t, d, _ in nodes)

if "Messages" not in joined:
    opened = False

    for selector in [
        {"descriptionContains": "Message"},
        {"descriptionContains": "Direct"},
        {"textContains": "Messages"},
    ]:
        try:
            obj = d(**selector)
            if obj.exists(timeout=1):
                obj.click()
                opened = True
                break
        except Exception:
            pass

    if not opened:
        d.click(999, 158)

    time.sleep(4)
    xml = d.dump_hierarchy(compressed=False)
    nodes = extract(xml)

print("INSTAGRAM_INBOX_TEXT_BEGIN")

for text, desc, bounds in nodes:
    if text or desc:
        print(f"TEXT={text} | DESC={desc} | BOUNDS={bounds}")

print("INSTAGRAM_INBOX_TEXT_END")
print("INSTAGRAM_INBOX_READ=True")
'@

Set-Content -Path $pyFile -Value $python -Encoding UTF8
& py $pyFile
