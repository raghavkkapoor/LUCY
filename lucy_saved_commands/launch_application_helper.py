
"""
LLM Automation Capability:
Provides a reusable Windows application launcher helper.

Functions:
- launch_application(search_terms=None)

Parameters:
- search_terms: Optional list of application name fragments.

Behavior:
- Searches common Windows locations.
- Opens the first matching shortcut or executable.
- Returns a compact result string.

Use this helper when an LLM needs to launch installed applications
without hardcoding a single application path.
"""

import os
import glob

def launch_application(search_terms=None):
    if search_terms is None:
        search_terms = []

    locations = [
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu"),
        r"C:\Program Files",
        r"C:\Program Files (x86)"
    ]

    for location in locations:
        if not os.path.exists(location):
            continue

        for term in search_terms:
            matches = glob.glob(
                os.path.join(location, "**", f"*{term}*"),
                recursive=True
            )

            if matches:
                os.startfile(matches[0])
                return f"Opened: {matches[0]}"

    return "No matching application found."
