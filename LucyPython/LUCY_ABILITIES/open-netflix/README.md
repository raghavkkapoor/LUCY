# Open Netflix
Goal: Open Netflix in Lucy's existing Chrome instance without disturbing the current ChatGPT tab.
Method: Connects to Chrome DevTools Protocol on port 9223 and creates a new Netflix tab, then verifies the tab exists.
Risk/Stability: Low risk. Uses Chrome's local CDP endpoint and does not modify the existing tab. Stable while Lucy Chrome is running with CDP port 9223.
