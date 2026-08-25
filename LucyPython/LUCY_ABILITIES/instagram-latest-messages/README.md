# Instagram Latest Messages

Reads the user's signed-in Instagram inbox from the paired Pixel phone.

## Proven workflow

- ADB device: Pixel 10 at 172.16.0.26:42251
- Instagram package: com.instagram.android
- Initialize UIAutomator2 before foregrounding Instagram.
- Launch Instagram explicitly with ADB.
- Read the UI hierarchy using UIAutomator2.
- Locate the Messages control semantically, with a coordinate fallback.
- Extract visible conversation names, previews, unread state, and relative timestamps.

## Important discovery

Instagram uses FLAG_SECURE, so normal ADB screenshots are black. Basic uiautomator dump was insufficient, but UIAutomator2 successfully exposed the inbox hierarchy.
