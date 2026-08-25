import importlib.util
from pathlib import Path

ROOT = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython")
HANDLER = ROOT / "Services[IGNORE]" / "Emailing" / "Gmailhandler.py"

spec = importlib.util.spec_from_file_location("lucy_gmailhandler", str(HANDLER))
gmail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gmail)

creds = gmail.run_new_oauth_flow()

if creds and creds.valid:
    print("GMAIL_OAUTH_SUCCESS=True")
else:
    print("GMAIL_OAUTH_SUCCESS=False")
