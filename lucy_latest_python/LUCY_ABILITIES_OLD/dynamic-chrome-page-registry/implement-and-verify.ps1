$ErrorActionPreference = "Stop"

$root = "C:\Users\ragha\Downloads\LUCY\LucyPython"
$main = Join-Path $root "main.py"
$abilityDir = Join-Path $root "LUCY_ABILITIES\dynamic-chrome-page-registry"
$backupDir = Join-Path $abilityDir "backup"
$watchdogState = Join-Path $root "LUCY_ABILITIES\lucy-watchdog\watchdog-state.txt"
$fixer = Join-Path $abilityDir "fix_registry.py"
$tester = Join-Path $abilityDir "test_dynamic_pages_v2.py"
$workflow = Join-Path $abilityDir "implement-and-verify.ps1"
$readme = Join-Path $abilityDir "README.md"

New-Item -ItemType Directory -Force -Path $abilityDir,$backupDir | Out-Null

function Speak([string]$Text) {
    try {
        Add-Type -AssemblyName System.Speech -ErrorAction Stop
        $v = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $v.Speak($Text)
    } catch {}
}

function Get-WatchdogState {
    $r = @{}
    if (Test-Path $watchdogState) {
        foreach ($line in Get-Content $watchdogState) {
            if ($line -match '^([^=]+)=(.*)$') {
                $r[$matches[1]] = $matches[2]
            }
        }
    }
    return $r
}

function Restore-Backup([string]$Backup) {
    if ($Backup -and (Test-Path $Backup)) {
        Copy-Item $Backup $main -Force
        & py -m py_compile $main
        Write-Output "ROLLBACK_COMPILE_OK=$($LASTEXITCODE -eq 0)"
        Write-Output "ROLLBACK_MAIN_RESTORED=True"
    }
}

try {
    Write-Output "=== OODA: FIX TRUE MULTI-WINDOW DISCOVERY ==="

    # Observe: current patch works for tabs but Playwright did not surface
    # a raw Target.createTarget(newWindow=True) page inside context.pages.
    # Fix: maintain BOTH Playwright Page objects and raw browser-level CDP
    # target inventory. This gives Lucy browser-wide awareness even when a
    # newly-created Chrome window has not yet been materialized as a Page.

    $latestOriginal = Get-ChildItem $backupDir -Filter "main-*.py" -ErrorAction SilentlyContinue |
        Where-Object {
            (Get-FileHash $_.FullName -Algorithm SHA256).Hash -eq "2755DBA0284473F6A6F8803984650294CBFFCE9E0A52B3B3972622945EEE40B2"
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $latestOriginal) {
        throw "Known-good pre-patch backup could not be found."
    }

    $knownGood = $latestOriginal.FullName
    Write-Output "KNOWN_GOOD_BACKUP=$knownGood"

    # Start from known-good main.py so we don't layer patches.
    Copy-Item $knownGood $main -Force

    & py -m py_compile $main
    if ($LASTEXITCODE -ne 0) {
        throw "Known-good backup failed compilation."
    }

    $freshBackup = Join-Path $backupDir ("main-pre-multitarget-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".py")
    Copy-Item $main $freshBackup -Force
    Write-Output "FRESH_BACKUP=$freshBackup"

@'
from pathlib import Path
import re

path = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
text = path.read_text(encoding="utf-8-sig")

marker = "LUCY_DYNAMIC_BROWSER_REGISTRY_V2"

registry = r'''
# LUCY_DYNAMIC_BROWSER_REGISTRY_V2
_PAGE_REGISTRY = {}
_TRACKED_CONTEXT_IDS = set()
_PAGE_REGISTRY_LOCK = threading.Lock()
_BROWSER_CDP_SESSION = None


def _page_key(page):
    return id(page)


def _remove_page(key):
    with _PAGE_REGISTRY_LOCK:
        _PAGE_REGISTRY.pop(key, None)


def _register_page(page):
    key = _page_key(page)

    with _PAGE_REGISTRY_LOCK:
        _PAGE_REGISTRY[key] = page

    try:
        page.on("close", lambda: _remove_page(key))
    except Exception:
        pass

    return page


def _track_context(context):
    context_key = id(context)

    if context_key not in _TRACKED_CONTEXT_IDS:
        _TRACKED_CONTEXT_IDS.add(context_key)
        try:
            context.on("page", _register_page)
        except Exception:
            pass

    try:
        for existing_page in context.pages:
            _register_page(existing_page)
    except Exception:
        pass


def _ensure_browser_cdp_session(browser):
    global _BROWSER_CDP_SESSION

    if _BROWSER_CDP_SESSION is not None:
        return _BROWSER_CDP_SESSION

    _BROWSER_CDP_SESSION = browser.new_browser_cdp_session()

    try:
        _BROWSER_CDP_SESSION.send(
            "Target.setDiscoverTargets",
            {"discover": True}
        )
    except Exception:
        pass

    return _BROWSER_CDP_SESSION


def raw_browser_targets(browser):
    """
    Browser-process-wide target inventory.

    Unlike context.pages, Target.getTargets can see Chrome targets that
    exist at the browser level even if Playwright has not materialized
    them into Page objects yet.
    """
    session = _ensure_browser_cdp_session(browser)

    try:
        result = session.send("Target.getTargets")
    except Exception:
        return []

    targets = []

    for info in result.get("targetInfos", []):
        target_type = info.get("type", "")

        if target_type not in ("page", "webview"):
            continue

        targets.append({
            "target_id": info.get("targetId", ""),
            "type": target_type,
            "title": info.get("title", ""),
            "url": info.get("url", ""),
            "attached": bool(info.get("attached", False)),
            "browser_context_id": info.get("browserContextId", ""),
        })

    return targets


def refresh_page_registry(browser):
    active_keys = set()

    try:
        contexts = list(browser.contexts)
    except Exception:
        contexts = []

    for browser_context in contexts:
        _track_context(browser_context)

        try:
            pages = list(browser_context.pages)
        except Exception:
            pages = []

        for browser_page in pages:
            try:
                if browser_page.is_closed():
                    continue
            except Exception:
                continue

            key = _page_key(browser_page)
            active_keys.add(key)

            with _PAGE_REGISTRY_LOCK:
                _PAGE_REGISTRY[key] = browser_page

    with _PAGE_REGISTRY_LOCK:
        for key in list(_PAGE_REGISTRY):
            if key not in active_keys:
                _PAGE_REGISTRY.pop(key, None)

        return list(_PAGE_REGISTRY.values())


def all_pages(browser):
    """
    Live Playwright Page objects across every CDP-visible context.
    """
    return refresh_page_registry(browser)


def browser_target_snapshot(browser):
    """
    Complete browser-process-level inventory of tabs/windows.

    Combines Playwright pages with raw CDP targets and de-duplicates by
    URL/title where possible. Raw target_id remains available so Lucy can
    later address a target directly through CDP when needed.
    """
    snapshot = []
    seen = set()

    for index, browser_page in enumerate(all_pages(browser), start=1):
        try:
            if browser_page.is_closed():
                continue
        except Exception:
            continue

        try:
            title = browser_page.title()
        except Exception:
            title = ""

        try:
            url = browser_page.url
        except Exception:
            url = ""

        key = ("page", url, title)

        if key in seen:
            continue

        seen.add(key)

        snapshot.append({
            "source": "playwright",
            "index": index,
            "title": title,
            "url": url,
            "target_id": "",
            "page": browser_page,
        })

    for target in raw_browser_targets(browser):
        title = target.get("title", "")
        url = target.get("url", "")

        # If this target is already represented by a Playwright Page,
        # enrich the existing entry with its browser target id.
        matching = None
        for item in snapshot:
            if (
                item["source"] == "playwright"
                and item["url"] == url
                and item["title"] == title
            ):
                matching = item
                break

        if matching is not None:
            matching["target_id"] = target.get("target_id", "")
            continue

        snapshot.append({
            "source": "cdp",
            "index": len(snapshot) + 1,
            "title": title,
            "url": url,
            "target_id": target.get("target_id", ""),
            "page": None,
        })

    return snapshot


def browser_page_snapshot(browser):
    """
    Serializable view of every Chrome tab/window target Lucy can see.
    """
    result = []

    for item in browser_target_snapshot(browser):
        result.append({
            "source": item["source"],
            "index": item["index"],
            "title": item["title"],
            "url": item["url"],
            "target_id": item["target_id"],
        })

    return result


def find_lucy_page(browser):
    for browser_page in all_pages(browser):
        try:
            if browser_page.url.startswith(LUCY_URL):
                return browser_page
        except Exception:
            pass

    return None


def install_page_tracking(browser):
    for browser_context in list(browser.contexts):
        _track_context(browser_context)

    _ensure_browser_cdp_session(browser)
    pages = refresh_page_registry(browser)
    targets = raw_browser_targets(browser)

    print(
        f"{GREEN}LUCY_DYNAMIC_BROWSER_REGISTRY_READY=True "
        f"PAGES={len(pages)} TARGETS={len(targets)}{RESET}"
    )


'''

m = re.search(r'(?m)^def connect_to_lucy\(p\):\s*$', text)
if not m:
    raise RuntimeError("connect_to_lucy(p) not found")

text = text[:m.start()] + registry + "\n" + text[m.start():]

start = text.find("def connect_to_lucy(p):")
end_match = re.search(
    r'(?m)^def is_target_closed_error\(error\):\s*$',
    text[start:]
)

if not end_match:
    raise RuntimeError("Could not locate connect_to_lucy end")

end = start + end_match.start()
block = text[start:end]

pattern = re.compile(
    r'(\n[ \t]+if not browser\.contexts:\s*\n'
    r'[ \t]+raise RuntimeError\("No Chrome browser context found\."\)\s*\n)',
    re.M
)

block, n = pattern.subn(
    r'\1\n    install_page_tracking(browser)\n',
    block,
    count=1
)

if n != 1:
    raise RuntimeError("Could not insert install_page_tracking")

block, n = re.subn(
    r'for existing_page in context\.pages:',
    'for existing_page in all_pages(browser):',
    block,
    count=1
)

if n != 1:
    raise RuntimeError("Could not replace Lucy page enumeration")

text = text[:start] + block + text[end:]

required = [
    marker,
    "def raw_browser_targets(browser):",
    "def browser_target_snapshot(browser):",
    "def all_pages(browser):",
    'Target.getTargets',
    'Target.setDiscoverTargets',
    "install_page_tracking(browser)",
    "for existing_page in all_pages(browser):",
]

missing = [item for item in required if item not in text]

if missing:
    raise RuntimeError("Missing markers: " + ", ".join(missing))

path.write_text(text, encoding="utf-8")

print("V2_PATCH_WRITE_OK=True")
print("V2_PATCH_MARKERS_OK=True")
'@ | Set-Content $fixer -Encoding UTF8

    $patchResult = & py $fixer 2>&1
    $patchCode = $LASTEXITCODE
    $patchResult | ForEach-Object { Write-Output $_ }

    if ($patchCode -ne 0) {
        Restore-Backup $freshBackup
        throw "V2 patcher failed."
    }

    & py -m py_compile $main
    if ($LASTEXITCODE -ne 0) {
        Restore-Backup $freshBackup
        throw "V2 patched main.py failed compilation."
    }

    Write-Output "PY_COMPILE_OK=True"

@'
import importlib.util
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

MAIN = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
CDP = "http://127.0.0.1:9223"

spec = importlib.util.spec_from_file_location("lucy_v2_test", MAIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP, no_defaults=True)

    if not browser.contexts:
        raise RuntimeError("No browser contexts")

    mod.install_page_tracking(browser)

    before = mod.browser_page_snapshot(browser)
    context = browser.contexts[0]

    # ----------------------------------------------------------
    # TEST A: ordinary new tab -> must become Playwright Page.
    # ----------------------------------------------------------
    tab = context.new_page()
    tab.goto(
        "data:text/html,<title>LUCY_V2_TAB_TEST</title><h1>tab</h1>",
        wait_until="domcontentloaded",
    )

    time.sleep(0.5)

    tab_snapshot = mod.browser_page_snapshot(browser)

    tab_seen = any(
        item["title"] == "LUCY_V2_TAB_TEST"
        for item in tab_snapshot
    )

    tab_as_playwright = any(
        item["title"] == "LUCY_V2_TAB_TEST"
        and item["source"] == "playwright"
        for item in tab_snapshot
    )

    # ----------------------------------------------------------
    # TEST B: true Chrome-level separate window.
    # This is the exact scenario that failed before.
    # ----------------------------------------------------------
    session = browser.new_browser_cdp_session()

    created = session.send(
        "Target.createTarget",
        {
            "url": "data:text/html,<title>LUCY_V2_WINDOW_TEST</title><h1>window</h1>",
            "newWindow": True,
        },
    )

    target_id = created["targetId"]

    window_seen = False
    window_source = ""
    window_item = None

    deadline = time.time() + 5.0

    while time.time() < deadline:
        snapshot = mod.browser_page_snapshot(browser)

        for item in snapshot:
            if (
                item["target_id"] == target_id
                or item["title"] == "LUCY_V2_WINDOW_TEST"
                or "LUCY_V2_WINDOW_TEST" in item["url"]
            ):
                window_seen = True
                window_source = item["source"]
                window_item = item
                break

        if window_seen:
            break

        time.sleep(0.2)

    # We do NOT require Playwright to materialize it.
    # Raw browser-level CDP awareness is sufficient to prove Lucy sees it.
    chatgpt_seen = any(
        "chatgpt.com" in item["url"]
        for item in mod.browser_page_snapshot(browser)
    )

    raw_target_seen = any(
        target["target_id"] == target_id
        for target in mod.raw_browser_targets(browser)
    )

    print(f"INITIAL_TARGET_COUNT={len(before)}")
    print(f"NEW_TAB_DISCOVERED={tab_seen}")
    print(f"NEW_TAB_IS_PLAYWRIGHT_PAGE={tab_as_playwright}")
    print(f"NEW_WINDOW_DISCOVERED={window_seen}")
    print(f"NEW_WINDOW_SOURCE={window_source}")
    print(f"RAW_CDP_WINDOW_TARGET_DISCOVERED={raw_target_seen}")
    print(f"EXISTING_CHATGPT_PRESERVED={chatgpt_seen}")
    print(f"NEW_WINDOW_TARGET_ID={target_id}")

    # Cleanup.
    try:
        tab.close()
    except Exception:
        pass

    try:
        session.send(
            "Target.closeTarget",
            {"targetId": target_id}
        )
    except Exception:
        pass

    time.sleep(0.5)

    cleaned = mod.browser_page_snapshot(browser)

    test_targets_left = [
        item for item in cleaned
        if (
            item["title"] in ("LUCY_V2_TAB_TEST", "LUCY_V2_WINDOW_TEST")
            or "LUCY_V2_TAB_TEST" in item["url"]
            or "LUCY_V2_WINDOW_TEST" in item["url"]
        )
    ]

    cleanup_ok = len(test_targets_left) == 0

    print(f"CLOSED_TEST_TARGETS_REMOVED={cleanup_ok}")

    if not tab_seen:
        raise RuntimeError("Normal new tab not discovered")

    if not tab_as_playwright:
        raise RuntimeError("Normal new tab was not represented as Page")

    if not window_seen:
        raise RuntimeError("Separate Chrome window not discovered")

    if not raw_target_seen:
        raise RuntimeError("Separate window missing from raw CDP target inventory")

    if not chatgpt_seen:
        raise RuntimeError("Lucy ChatGPT target disappeared")

    if not cleanup_ok:
        raise RuntimeError("Closed test targets remained visible")

    print("DYNAMIC_MULTIWINDOW_TEST_PASSED=True")
'@ | Set-Content $tester -Encoding UTF8

    # Use System.Diagnostics.Process so stderr cannot become a PowerShell
    # terminating RemoteException.
    function Run-PythonCaptured([string]$Script) {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "py"
        $psi.Arguments = "`"$Script`""
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true

        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        $null = $proc.Start()

        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()

        [pscustomobject]@{
            ExitCode = $proc.ExitCode
            Stdout = $stdout
            Stderr = $stderr
        }
    }

    $pre = Run-PythonCaptured $tester

    Write-Output "PRETEST_STDOUT_BEGIN"
    Write-Output $pre.Stdout
    Write-Output "PRETEST_STDOUT_END"

    if ($pre.Stderr) {
        Write-Output "PRETEST_STDERR_BEGIN"
        Write-Output $pre.Stderr
        Write-Output "PRETEST_STDERR_END"
    }

    if (
        $pre.ExitCode -ne 0 -or
        $pre.Stdout -notmatch "DYNAMIC_MULTIWINDOW_TEST_PASSED=True"
    ) {
        Restore-Backup $freshBackup
        throw "V2 pre-restart test failed; restored known-good main.py."
    }

    Write-Output "PRE_RESTART_MULTIWINDOW_TEST_PASSED=True"

    # Save proven workflow.
    Set-Content $workflow $MyInvocation.MyCommand.ScriptBlock.ToString() -Encoding UTF8

@"
# Dynamic Chrome Browser Registry V2

## Goal
Let Lucy maintain awareness of all tabs and windows belonging to the Chrome browser instance on CDP port 9223.

## Why V2 was required
The first implementation successfully detected new Playwright tabs, but Chrome's browser-level `Target.createTarget(newWindow=True)` produced a true window that was not immediately materialized in `context.pages`.

V2 tracks two layers:

1. Playwright Page registry
   - Existing tabs
   - Newly created tabs
   - Popups
   - Page close events

2. Raw Chrome browser-level CDP target registry
   - `Target.setDiscoverTargets`
   - `Target.getTargets`
   - Browser-level page targets
   - Separate Chrome windows even if Playwright has not yet exposed a Page object

## Key APIs
- `all_pages(browser)`
- `raw_browser_targets(browser)`
- `browser_target_snapshot(browser)`
- `browser_page_snapshot(browser)`

Lucy retains her dedicated ChatGPT `page` object for the main conversation loop, while browser-wide awareness is maintained separately.

## Verification before restart
- main.py Python compilation passed.
- Ordinary new tab was detected as a Playwright Page.
- True `newWindow=True` Chrome target was detected through browser-level CDP.
- Existing ChatGPT target remained visible.
- Test targets were successfully closed and removed.

## Rollback
Known-good main.py backup:
$freshBackup

If any verification fails, the workflow restores the known-good file.

## Risk
Moderate because main.py changes, but the original conversational page behavior remains intact and rollback is automatic.
"@ | Set-Content $readme -Encoding UTF8

    if (-not (Test-Path $workflow) -or -not (Test-Path $readme)) {
        Restore-Backup $freshBackup
        throw "Ability files failed to save."
    }

    Write-Output "WORKFLOW_SAVED=True"

    # --------------------------------------------------------------
    # Restart only now, after successful test.
    # --------------------------------------------------------------
    $state = Get-WatchdogState
    $oldPid = 0

    if (
        $state.ContainsKey("LUCY_PID") -and
        $state["LUCY_PID"] -match '^\d+$'
    ) {
        $oldPid = [int]$state["LUCY_PID"]
    }

    if (-not $oldPid) {
        $lucy = Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^python(w)?\.exe$' -and
                $_.CommandLine -match [regex]::Escape($main)
            } |
            Select-Object -First 1

        if ($lucy) {
            $oldPid = [int]$lucy.ProcessId
        }
    }

    if (-not $oldPid) {
        Restore-Backup $freshBackup
        throw "Could not identify running Lucy PID."
    }

    Write-Output "OLD_LUCY_PID=$oldPid"
    Write-Output "ALL_PRE_RESTART_CHECKS_PASSED=True"

    Stop-Process -Id $oldPid -Force

    $deadline = (Get-Date).AddSeconds(20)
    $newPid = 0

    do {
        Start-Sleep -Milliseconds 250
        $postState = Get-WatchdogState

        if (
            $postState.ContainsKey("LUCY_PID") -and
            $postState["LUCY_PID"] -match '^\d+$'
        ) {
            $candidate = [int]$postState["LUCY_PID"]

            if (
                $candidate -ne $oldPid -and
                (Get-Process -Id $candidate -ErrorAction SilentlyContinue)
            ) {
                $newPid = $candidate
                break
            }
        }
    } while ((Get-Date) -lt $deadline)

    if (-not $newPid) {
        Restore-Backup $freshBackup

        $partial = Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^python(w)?\.exe$' -and
                $_.CommandLine -match [regex]::Escape($main)
            } |
            Select-Object -First 1

        if ($partial) {
            Stop-Process -Id $partial.ProcessId -Force -ErrorAction SilentlyContinue
        }

        throw "Lucy did not restart successfully. Backup restored."
    }

    Write-Output "NEW_LUCY_PID=$newPid"
    Write-Output "WATCHDOG_RESTART_VERIFIED=True"

    # --------------------------------------------------------------
    # Verify restarted Lucy loaded V2 and connected.
    # --------------------------------------------------------------
    $ready = $false
    $connected = $false
    $activeLog = ""
    $logDeadline = (Get-Date).AddSeconds(15)

    do {
        $s = Get-WatchdogState

        if ($s.ContainsKey("LOG")) {
            $activeLog = $s["LOG"]
        }

        if ($activeLog -and (Test-Path $activeLog)) {
            $log = Get-Content $activeLog -Raw -ErrorAction SilentlyContinue

            $ready = $log -match "LUCY_DYNAMIC_BROWSER_REGISTRY_READY=True"
            $connected = $log -match "Connected to Lucy"
        }

        if ($ready -and $connected) {
            break
        }

        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $logDeadline)

    if (-not ($ready -and $connected)) {
        Restore-Backup $freshBackup
        Stop-Process -Id $newPid -Force -ErrorAction SilentlyContinue

        Write-Output "PATCH_REVERTED=True"
        throw "Restarted Lucy failed V2 initialization. Backup restored and watchdog restart triggered."
    }

    Write-Output "V2_REGISTRY_INITIALIZED_AFTER_RESTART=True"
    Write-Output "LUCY_CONNECTED_AFTER_RESTART=True"

    # Final full test after restart.
    $post = Run-PythonCaptured $tester

    Write-Output "POSTTEST_STDOUT_BEGIN"
    Write-Output $post.Stdout
    Write-Output "POSTTEST_STDOUT_END"

    if ($post.Stderr) {
        Write-Output "POSTTEST_STDERR_BEGIN"
        Write-Output $post.Stderr
        Write-Output "POSTTEST_STDERR_END"
    }

    if (
        $post.ExitCode -ne 0 -or
        $post.Stdout -notmatch "DYNAMIC_MULTIWINDOW_TEST_PASSED=True"
    ) {
        Restore-Backup $freshBackup
        Stop-Process -Id $newPid -Force -ErrorAction SilentlyContinue

        Write-Output "PATCH_REVERTED=True"
        throw "Post-restart multi-window verification failed. Backup restored."
    }

    Start-Sleep -Seconds 1

    if (-not (Get-Process -Id $newPid -ErrorAction SilentlyContinue)) {
        Restore-Backup $freshBackup
        throw "Patched Lucy exited during final verification."
    }

    Add-Content $readme @"

## Live restart result
- Old Lucy PID: $oldPid
- New Lucy PID: $newPid
- Watchdog automatic restart: verified
- V2 browser registry startup marker: verified
- ChatGPT connection after restart: verified
- New tab detection after restart: passed
- Separate Chrome window target detection after restart: passed
- Closed-target cleanup after restart: passed
- Lucy remained running after verification: passed
"@

    Speak "Lucy now tracks the entire Chrome debugging instance, including normal tabs and separate Chrome window targets. I tested it, restarted Lucy automatically, and verified it again."

    Write-Output "POST_RESTART_MULTIWINDOW_TEST_PASSED=True"
    Write-Output "LUCY_STILL_RUNNING=True"
    Write-Output "SCRIPT_EXISTS=$(Test-Path $workflow)"
    Write-Output "README_EXISTS=$(Test-Path $readme)"
    Write-Output "ABILITY_DIR=$abilityDir"
    Write-Output "BACKUP_RETAINED=$freshBackup"
    Write-Output "IMPLEMENTATION_VERIFIED=True"
    Write-Output "GOAL_COMPLETED=True"
}
catch {
    Speak "The browser tracking upgrade did not pass every safety check. The known-good Lucy main script was preserved or restored."

    Write-Output "IMPLEMENTATION_FAILED=True"
    Write-Output "ERROR_TYPE=$($_.Exception.GetType().FullName)"
    Write-Output "ERROR=$($_.Exception.Message)"
    Write-Output "MAIN_EXISTS=$(Test-Path $main)"
    Write-Output "ABILITY_DIR=$abilityDir"
    exit 1
}
