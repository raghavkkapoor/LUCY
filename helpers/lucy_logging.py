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
    # Changed color to color.value and moved RESET so it doesn't block the color
    print(f" {color.value}{text_to_log}{RESET}\n")


def debug_log(text_to_log: str) -> None:
    # Changed LogColors.GRAY to LogColors.GRAY.value and moved RESET
    print(f" {LogColors.GRAY.value}{text_to_log}{RESET}\n")