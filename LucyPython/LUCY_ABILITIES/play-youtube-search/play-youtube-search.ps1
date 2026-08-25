param(
    [Parameter(Mandatory=$true)]
    [string]$Query,

    [int]$CdpPort = 9223
)

$ErrorActionPreference = "Stop"

$env:LUCY_YT_QUERY = $Query
$env:LUCY_CDP_PORT = "$CdpPort"

$py = @"
from playwright.sync_api import sync_playwright
import os, time, urllib.parse

query = os.environ["LUCY_YT_QUERY"]
port = os.environ["LUCY_CDP_PORT"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]
    cdp = browser.new_browser_cdp_session()

    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)

    target = cdp.send("Target.createTarget", {
        "url": search_url,
        "newWindow": True
    })

    target_id = target["targetId"]
    page = None

    for _ in range(80):
        for pg in context.pages:
            try:
                info = cdp.send("Target.getTargetInfo", {"targetId": target_id})["targetInfo"]
                if info.get("targetId") == target_id and "youtube.com" in pg.url:
                    page = pg
                    break
            except Exception:
                pass

        if page:
            break
        time.sleep(0.25)

    if page is None:
        yt = [pg for pg in context.pages if "youtube.com" in pg.url]
        if yt:
            page = yt[-1]

    if page is None:
        raise RuntimeError("Could not locate new YouTube window.")

    page.wait_for_load_state("domcontentloaded", timeout=30000)

    try:
        page.get_by_text("Accept all", exact=False).first.click(timeout=2000)
    except Exception:
        pass

    page.wait_for_selector("ytd-video-renderer a#video-title", timeout=30000)

    videos = page.locator("ytd-video-renderer a#video-title")

    chosen = None
    chosen_title = None

    for i in range(min(videos.count(), 15)):
        v = videos.nth(i)
        title = (v.get_attribute("title") or v.inner_text()).strip()
        low = title.lower()

        if ("ford" in low and ("ferrari" in low or "ferrerri" in low)) and (
            "remix" in low or "edit" in low or "music" in low
        ):
            chosen = v
            chosen_title = title
            break

    if chosen is None:
        chosen = videos.first
        chosen_title = (chosen.get_attribute("title") or chosen.inner_text()).strip()

    chosen.click()
    page.wait_for_url("**/watch?v=*", timeout=30000)
    page.wait_for_selector("video", timeout=30000)
    page.wait_for_timeout(2500)

    video = page.locator("video").first

    state = video.evaluate("""v => ({
        paused: v.paused,
        currentTime: v.currentTime,
        duration: v.duration,
        muted: v.muted,
        volume: v.volume
    })""")

    if state["paused"]:
        try:
            page.locator("button.ytp-play-button").click(timeout=3000)
        except Exception:
            video.evaluate("v => v.play()")

    page.wait_for_timeout(1500)

    after = video.evaluate("""v => ({
        paused: v.paused,
        currentTime: v.currentTime,
        duration: v.duration
    })""")

    if after["paused"]:
        raise RuntimeError("YouTube video is loaded but playback did not start.")

    print("YOUTUBE_PLAYING=True")
    print("VIDEO_TITLE=" + chosen_title)
    print("VIDEO_URL=" + page.url)
    print("CURRENT_TIME=" + str(round(after["currentTime"], 2)))
"@

$tmp = Join-Path $env:TEMP "lucy-play-youtube-search.py"
Set-Content -Path $tmp -Value $py -Encoding UTF8

python $tmp

if ($LASTEXITCODE -ne 0) {
    throw "YouTube playback failed."
}
