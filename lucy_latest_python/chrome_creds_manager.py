# import os
from Utils.lucy_logging import log, LogColors
# import pandas as pd

# local_app_data = os.environ.get("LOCALAPPDATA", "")
# lucy_dir = os.path.join(local_app_data, "Lucy")
# credentials_dir = os.path.join(lucy_dir, "Creds")
# passwords_file = os.path.join(credentials_dir, "Chrome Passwords.csv")


# def load_csv(file_path: str) -> pd.DataFrame:
#     """Loads a CSV file into a pandas DataFrame."""
#     if not os.path.isfile(file_path):
#         raise FileNotFoundError(f"No valid file found at '{file_path}'")
#     return pd.read_csv(file_path)


# def get_available_fields(df: pd.DataFrame) -> list[str]:
#     """Returns a list of all searchable column names in the CSV."""
#     return df.columns.tolist()

# def search_fields(df: pd.DataFrame, search_column: str, value) -> dict[str, list]:
#     """Filters data where `search_column` matches `value` and returns matching row fields."""
#     available = get_available_fields(df)
#     if search_column not in available:
#         raise KeyError(
#             f"Column '{search_column}' not found. Available fields: {available}"
#         )

#     # Cast value to match column type if needed (e.g., strings vs numbers)
#     matching_rows = df[df[search_column].astype(str) == str(value)]
#     return matching_rows.to_dict(orient="list")

# data = load_csv(passwords_file)


# what_is_searchable = get_available_fields(data)

# search_results = search_fields(data, search_column="name", value="Instagram")
# print(search_results)


import asyncio
from playwright.async_api import async_playwright


async def scan_page_elements_interactive(url: str) -> list[dict]:
    """Scans a web page in headful mode, logs a clean snippet of interactable elements,

    and keeps the browser window open until manually dismissed.
    """
    playwright = await async_playwright().start()

    # Launch in headful mode
    browser = await playwright.chromium.launch(headless=False)
    page = await browser.new_page()

    print(f"Navigating to {url}...")
    await page.goto(url, wait_until="networkidle")

    # Dismiss native alert dialogs automatically if they appear
    page.on("dialog", lambda dialog: dialog.dismiss())

    selector = (
        "button, a[href], input, select, textarea, "
        "[role='button'], [role='link'], [role='checkbox'], "
        "[role='menuitem'], [role='tab'], [onclick]"
    )

    elements = await page.locator(selector).all()
    interactables = []

    for index, el in enumerate(elements):
        if not await el.is_visible():
            continue

        tag = await el.evaluate("e => e.tagName.toLowerCase()")
        role = await el.get_attribute("role") or tag
        element_type = await el.get_attribute("type") or ""

        # Extract visible text or fall back to metadata labels
        text = (await el.inner_text()).strip()
        if not text:
            text = (
                await el.get_attribute("aria-label")
                or await el.get_attribute("placeholder")
                or await el.get_attribute("title")
                or await el.get_attribute("value")
                or ""
            ).strip()

        el_id = await el.get_attribute("id")
        name = await el.get_attribute("name")

        if el_id:
            loc = f"#{el_id}"
        elif name:
            loc = f"[name='{name}']"
        else:
            loc = f"({selector}) >> nth={index}"

        # Store the live Playwright Locator instance directly in the item dictionary
        item = {
            "id": el_id or f"elem_{index}",
            "text": text,
            "locator": el  # <--- Live Playwright Locator object
        }
        interactables.append(item)

        await el.click(timeout=3000)

        # Short single-line snippet logging
        display_text = f"\"{text}\"" if text else "<no text>"
        print(f"{display_text} -> ({el})")

    print(f"-----------------------------------\nTotal: {len(interactables)} items")

    # Keep browser open until manually stopped in terminal
    input("\n[Browser is open] Press ENTER in this console to close the browser...")

    await browser.close()
    await playwright.stop()

    return interactables





# --- Execution ---
if __name__ == "__main__":
    target_url = "https://example.com"
    data = asyncio.run(scan_page_elements_interactive(target_url))
  
