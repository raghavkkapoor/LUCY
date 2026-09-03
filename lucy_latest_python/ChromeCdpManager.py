import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from Utils.lucy_logging import log, LogColors
from preview_window_helper import make_process_window_click_through
from Utils.Constants import GEMINI_GEM_URL, CHROME_ACCOUNT_PAGE

def is_cdp_port_active(port):
    """Utility to test if a CDP endpoint is responsive on a given port."""
    cdp_url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(cdp_url, timeout=1) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return "webSocketDebuggerUrl" in data
    except Exception:
        pass
    return False

def get_running_lucy_chrome():
    """Checks running Windows processes for Chrome using PowerShell CIM queries."""
    ps_command = (
        'Get-CimInstance Win32_Process -Filter "Name = \'chrome.exe\'" | '
        'Select-Object ProcessId, CommandLine | '
        'ConvertTo-Json -Compress'
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()
        if not output:
            return None

        data = json.loads(output)
        processes = [data] if isinstance(data, dict) else data

        for proc in processes:
            cmd_line = proc.get("CommandLine") or ""
            pid = proc.get("ProcessId")

            if "--remote-debugging-port=" in cmd_line:
                port_match = re.search(r'--remote-debugging-port=(\d+)', cmd_line)
                dir_match = re.search(r'--user-data-dir=(?:"([^"]+)"|([^\s]+))', cmd_line)

                if port_match:
                    port = int(port_match.group(1))
                    
                    profile_dir = None
                    if dir_match:
                        profile_dir = dir_match.group(1) if dir_match.group(1) else dir_match.group(2)

                    if is_cdp_port_active(port):
                        return {
                            "Port": port,
                            "ProfileDir": profile_dir,
                            "ProcessId": pid,
                            "Running": True,
                            "url": f"http://127.0.0.1:{port}/"
                        }

    except Exception:
        pass

    return None

def launch_lucy_chrome(preferred_port=9223):
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    lucy_dir = os.path.join(local_app_data, "Lucy")
    profile_dir = os.path.join(lucy_dir, "LucyChrome")
    state_file = os.path.join(lucy_dir, "chrome_state.json")

    os.makedirs(profile_dir, exist_ok=True)

    # 1. Check if an instance is already running
    existing_instance = get_running_lucy_chrome()
    if existing_instance:
        log(f"\nLUCY:\nLucy Chrome already running.\nPort:    {existing_instance['Port']}\nProfile: {existing_instance['ProfileDir']}\n", LogColors.YELLOW)
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(existing_instance, f, indent=2)
            
        return existing_instance

    # 2. Locate Chrome binary
    chrome_candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    
    chrome_exe = next((path for path in chrome_candidates if os.path.isfile(path)), None)
    if not chrome_exe:
        log("\nLUCY:\nError: Google Chrome executable could not be found.\n", LogColors.RED)
        raise FileNotFoundError("Google Chrome executable could not be found.")

    # 3. Find an available port starting from preferred_port
    port = preferred_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                break
            port += 1

    log(f"\nLUCY:\nStarting Lucy Chrome...\nProfile: {profile_dir}\nPort:    {port}\n", LogColors.GRAY)

    # 4. Launch Process
    args = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        # f"--app=https://example.com/" # holy fuck, i pray for llms cuz lucy's architecture will work only if the LLM has at least 2 fucking braincells. Its all on the llm. If this mf can't think properly, we are all DOOMED. Genuinely. I mean it. 
    ]
    
    proc = subprocess.Popen(args)

    # 5. Wait for CDP endpoint readiness
    ready = False
    for _ in range(30):
        time.sleep(0.3)
        if is_cdp_port_active(port):
            ready = True
            break

    if not ready:
        log("\nLUCY:\nError: Chrome launched, but CDP failed to become available.\n", LogColors.RED)
        raise RuntimeError("Chrome launched, but CDP failed to become available.")

    # turn into preview window for now
    # make_process_window_click_through(proc.pid)

    # 6. Save state file
    state = {
        "Port": port,
        "ProfileDir": profile_dir,
        "ProcessId": proc.pid,
        "Running": True,
        "url": f"http://127.0.0.1:{port}/"
    }

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


    log("\nLUCY:\nLucy Chrome ready.\n", LogColors.GREEN)

    return state