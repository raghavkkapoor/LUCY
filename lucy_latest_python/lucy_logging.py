from enum import Enum

class LogColors(str, Enum):
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"

# Reset constant to safely reset console color
RESET = "\033[0m"

def log(text_to_log: str, color: LogColors) -> None:
         print(f"{RESET}{color.value}{text_to_log}{RESET}")