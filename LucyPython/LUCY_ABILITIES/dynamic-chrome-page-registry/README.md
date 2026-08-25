# Dynamic Chrome Browser Registry V2

## Goal
Let Lucy maintain awareness of all tabs and windows belonging to the Chrome browser instance on CDP port 9223.

## Why V2 was required
The first implementation successfully detected new Playwright tabs, but Chrome's browser-level Target.createTarget(newWindow=True) produced a true window that was not immediately materialized in context.pages.

V2 tracks two layers:

1. Playwright Page registry
   - Existing tabs
   - Newly created tabs
   - Popups
   - Page close events

2. Raw Chrome browser-level CDP target registry
   - Target.setDiscoverTargets
   - Target.getTargets
   - Browser-level page targets
   - Separate Chrome windows even if Playwright has not yet exposed a Page object

## Key APIs
- ll_pages(browser)
- aw_browser_targets(browser)
- rowser_target_snapshot(browser)
- rowser_page_snapshot(browser)

Lucy retains her dedicated ChatGPT page object for the main conversation loop, while browser-wide awareness is maintained separately.

## Verification before restart
- main.py Python compilation passed.
- Ordinary new tab was detected as a Playwright Page.
- True 
ewWindow=True Chrome target was detected through browser-level CDP.
- Existing ChatGPT target remained visible.
- Test targets were successfully closed and removed.

## Rollback
Known-good main.py backup:
C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\dynamic-chrome-page-registry\backup\main-pre-multitarget-20260823-014944.py

If any verification fails, the workflow restores the known-good file.

## Risk
Moderate because main.py changes, but the original conversational page behavior remains intact and rollback is automatic.

## Live restart result
- Old Lucy PID: 16852
- New Lucy PID: 2228
- Watchdog automatic restart: verified
- V2 browser registry startup marker: verified
- ChatGPT connection after restart: verified
- New tab detection after restart: passed
- Separate Chrome window target detection after restart: passed
- Closed-target cleanup after restart: passed
- Lucy remained running after verification: passed
