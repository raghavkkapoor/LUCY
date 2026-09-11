import time
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def play_song(song_name: str):
    """
    Connects to an existing browser instance on port 9223, opens a separate tab 
    (avoiding Gemini /usage and /app tabs), searches for the specified song on YouTube, 
    and plays it.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9223")
        except Exception as e:
            print(f"Failed to connect to browser instance on port 9223: {e}")
            return False

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        
        # Guard against restricted tabs
        for page in context.pages:
            url = page.url
            if "/usage" in url or "/app" in url:
                print(f"Skipping restricted tab: {url}")

        # Open a separate tab for searching and playing
        page = context.new_page()
        
        try:
            page.set_default_timeout(45000)
            
            query = quote_plus(song_name)
            search_url = f"https://www.youtube.com/results?search_query={query}"
            print(f"Searching YouTube for: {song_name}")
            page.goto(search_url)
            
            page.wait_for_selector("ytd-video-renderer", timeout=30000)
            first_video = page.locator("ytd-video-renderer #video-title").first
            video_title = first_video.inner_text()
            print(f"Found target content: {video_title}")
            
            first_video.click()
            page.wait_for_url("**/watch*", timeout=20000)
            
            # Verify and resume playback if paused
            time.sleep(2)
            video_element = page.locator("video")
            if video_element.count() > 0:
                is_paused = page.evaluate("document.querySelector('video').paused")
                if is_paused:
                    print("Video paused. Resuming playback...")
                    page.keyboard.press("Space")
            
            print("Playback successfully started.")
            return True
            
        except PlaywrightTimeoutError as te:
            print(f"Timeout encountered: {te}")
            return False
        except Exception as e:
            print(f"Error encountered: {e}")
            return False

if __name__ == "__main__":
    import sys
    song = sys.argv[1] if len(sys.argv) > 1 else "Danza Kuduro Don Omar"
    play_song(song)
