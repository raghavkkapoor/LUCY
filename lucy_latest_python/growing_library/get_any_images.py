# TODO: Make this shit faster. Its slow af.


import asyncio
import io
import sys
import urllib.parse
import urllib.request
import customtkinter as ctk
from PIL import Image
from playwright.async_api import async_playwright

CDP_HOST = "127.0.0.1"
CDP_PORT = 9223
MINIMUM_IMAGES = 3
MAX_IMAGES_TO_OPEN = 3


def test_cdp_port():
    """Check if the Chrome DevTools Protocol port is active."""
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except Exception:
        return False


def show_image_strip_window(images, duration_seconds=8):
    """Renders a frameless CTk strip with containers that tightly bound each image's dimensions."""
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTk()
    root.overrideredirect(True)  # Frameless/no OS window controls
    root.attributes("-topmost", True)
    root.configure(fg_color="#000000")

    # Center window initial frame
    width, height = 1500, 760
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")

    # Main Framed Outer Border
    container = ctk.CTkFrame(
        root,
        fg_color="#181818",
        border_color="#3c3c3c",
        border_width=1,
        corner_radius=18,
    )
    container.pack(fill="both", expand=True, padx=16, pady=16)

    # Header Frame
    header = ctk.CTkFrame(container, fg_color="transparent")
    header.pack(fill="x", padx=16, pady=(16, 12))

    title_label = ctk.CTkLabel(
        header, text="Google Images", font=("Segoe UI", 22, "bold"), text_color="#ffffff"
    )
    title_label.pack(side="left")

    remaining_time = [duration_seconds]
    countdown_label = ctk.CTkLabel(
        header,
        text=f"Auto-closing in {duration_seconds} seconds",
        font=("Segoe UI", 12),
        text_color="#b4b4b4",
    )
    countdown_label.pack(side="left", padx=16)

    # Single integrated Close Button
    close_btn = ctk.CTkButton(
        header,
        text="Close",
        command=root.destroy,
        fg_color="#e6e6e6",
        hover_color="#cccccc",
        text_color="#000000",
        font=("Segoe UI", 12, "bold"),
        width=92,
        height=34,
        corner_radius=8,
    )
    close_btn.pack(side="right")

    # Image Grid Layout
    grid_frame = ctk.CTkFrame(container, fg_color="transparent")
    grid_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    grid_frame.columnconfigure((0, 1, 2), weight=1, uniform="col")
    grid_frame.rowconfigure(0, weight=1)

    ctk_image_refs = []  # Prevents garbage collection

    for i in range(3):
        # Column slot wrapper
        col_cell = ctk.CTkFrame(grid_frame, fg_color="transparent")
        col_cell.grid(row=0, column=i, sticky="nsew", padx=8, pady=8)

        if i < len(images):
            try:
                req = urllib.request.Request(
                    images[i]["url"],
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://www.google.com/",
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw_data = resp.read()

                pil_img = Image.open(io.BytesIO(raw_data))
                
                # Scale down to fit layout limits while preserving strict aspect ratio
                pil_img.thumbnail((450, 600), Image.Resampling.LANCZOS)
                
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                ctk_image_refs.append(ctk_img)

                # Card container shrink-wraps to scaled image size with no extra margin padding
                card = ctk.CTkFrame(
                    col_cell,
                    fg_color="#000000",
                    border_color="#464646",
                    border_width=1,
                    corner_radius=16,
                )
                card.place(relx=0.5, rely=0.5, anchor="center")

                lbl = ctk.CTkLabel(card, image=ctk_img, text="")
                lbl.pack(padx=2, pady=2)

            except Exception:
                card = ctk.CTkFrame(
                    col_cell,
                    fg_color="#000000",
                    border_color="#464646",
                    border_width=1,
                    corner_radius=16,
                )
                card.pack(fill="both", expand=True)
                lbl = ctk.CTkLabel(card, text="Image unavailable", text_color="#ffffff")
                lbl.pack(expand=True)
        else:
            card = ctk.CTkFrame(
                col_cell,
                fg_color="#000000",
                border_color="#464646",
                border_width=1,
                corner_radius=16,
            )
            card.pack(fill="both", expand=True)
            lbl = ctk.CTkLabel(card, text="Missing image", text_color="#b4b4b4")
            lbl.pack(expand=True)

    def tick():
        remaining_time[0] -= 1
        if remaining_time[0] <= 0:
            root.destroy()
        else:
            countdown_label.configure(text=f"Auto-closing in {remaining_time[0]} seconds")
            root.after(1000, tick)

    root.after(1000, tick)
    root.mainloop()


async def extract_google_images(search_term):
    """Executes search via CDP directly on active port 9223."""

    encoded_search = urllib.parse.quote(search_term.strip())
    google_url = f"https://www.google.com/search?tbm=isch&safe=active&q={encoded_search}"

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://{CDP_HOST}:{CDP_PORT}")
        context = browser.contexts[0]
        page = await context.new_page()

        print("\nOpening Google Images search...")
        await page.goto(google_url, wait_until="domcontentloaded")

        js_extractor = """
        async () => {
            const needed = 3;
            const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

            function cleanText(value) { return (value || "").replace(/\\s+/g, " ").trim(); }
            function normalizeUrl(value) {
                if (!value) return null;
                try { return new URL(value, location.href).href; } catch { return null; }
            }
            function fromGoogleImageResultHref(href) {
                const normalized = normalizeUrl(href);
                if (!normalized) return null;
                try {
                    const url = new URL(normalized);
                    const imageUrl = url.searchParams.get("imgurl") || url.searchParams.get("mediaurl") || url.searchParams.get("url");
                    if (imageUrl && /^https?:\\/\\//i.test(imageUrl)) return imageUrl;
                } catch {}
                return null;
            }
            function usableImageUrl(src) {
                const normalized = normalizeUrl(src);
                if (!normalized || !/^https?:\\/\\//i.test(normalized)) return null;
                if (/google\\.com\\/logos|gstatic\\.com\\/images\\/branding/i.test(normalized)) return null;
                return normalized;
            }
            function addUnique(results, item) {
                if (!item || !item.url || results.some(existing => existing.url === item.url)) return;
                results.push(item);
            }
            function collectResults() {
                const results = [];
                document.querySelectorAll('a[href*="/imgres"], a[href*="imgurl="]').forEach(anchor => {
                    const url = fromGoogleImageResultHref(anchor.href);
                    if (!url) return;
                    const img = anchor.querySelector("img");
                    addUnique(results, {
                        url,
                        title: cleanText(anchor.getAttribute("aria-label") || img?.alt || anchor.innerText),
                        source: "imgres"
                    });
                });
                document.querySelectorAll("img").forEach(img => {
                    const box = img.getBoundingClientRect();
                    const src = usableImageUrl(img.currentSrc || img.src);
                    if (!src || box.width < 120 || box.height < 90) return;
                    addUnique(results, { url: src, title: cleanText(img.alt), source: "thumbnail" });
                });
                return results;
            }

            let results = [];
            for (let attempt = 0; attempt < 6; attempt++) {
                results = collectResults();
                if (results.length >= needed) break;
                window.scrollBy(0, Math.max(window.innerHeight, 900));
                await sleep(900);
            }
            return {
                success: results.length >= needed,
                count: results.length,
                images: results.slice(0, 10),
                error: results.length >= needed ? null : `Only found ${results.length} usable image URLs.`
            };
        }
        """

        print("Finding image result URLs...")
        data = await page.evaluate(js_extractor)
        await page.close()

        if not data or not data.get("success"):
            print(f"Extraction failed: {data.get('error') if data else 'No response data'}")
            return

        images_to_open = data["images"][:MAX_IMAGES_TO_OPEN]
        if len(images_to_open) < MINIMUM_IMAGES:
            print(f"Expected at least {MINIMUM_IMAGES} images, but only found {len(images_to_open)}.")
            return

        print(f"\nShowing {len(images_to_open)} images...\n")
        show_image_strip_window(images_to_open, duration_seconds=8)
        print("Done.")


def main():
    """Main operational block."""
    if not test_cdp_port():
        raise RuntimeError(
            f"Unable to connect to existing Chrome instance on CDP port {CDP_PORT}. "
            "Please ensure Chrome is running with `--remote-debugging-port=9223`."
        )
    search_term = input("Enter image search term: ").strip()
    if not search_term:
        print("No search term entered.")
        sys.exit(0)

    try:
        asyncio.run(extract_google_images(search_term))
    except Exception as err:
        print(f"\nERROR:\n{err}")



if __name__ == "__main__":
    main()