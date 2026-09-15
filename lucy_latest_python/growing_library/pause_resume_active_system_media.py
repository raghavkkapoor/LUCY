import asyncio
import re
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus,
)

# Global flag to track state across sequential calls
IS_CURRENTLY_PAUSED = False


async def get_target_browser_session():
    """Finds the first media session originating from a browser."""
    manager = (
        await GlobalSystemMediaTransportControlsSessionManager.request_async()
    )
    sessions = manager.get_sessions()
    browser_pattern = re.compile(
        r"chrome|msedge|firefox|brave|opera", re.IGNORECASE
    )

    for session in sessions:
        app_id = session.source_app_user_model_id
        if browser_pattern.search(app_id):
            return session

    return None


async def toggle_browser_media():
    """Pauses browser media if playing, or resumes it if previously paused."""
    global IS_CURRENTLY_PAUSED

    session = await get_target_browser_session()
    if not session:
        print("No target browser media session found.")
        return False

    playback = session.get_playback_info()
    status = playback.playback_status if playback else None
    props = await session.try_get_media_properties_async()
    title = props.title if props else "Unknown Track"

    print(f"\nAPP:    {session.source_app_user_model_id}")
    print(f"TITLE:  {title}")
    print(f"STATUS: {status.name if status else 'Unknown'}")

    playing_status = (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
    )

    # Action Logic: Pause if currently playing; Play if paused or flagged as toggled
    if status == playing_status and not IS_CURRENTLY_PAUSED:
        print(f"\nAttempting to PAUSE: {title}")
        success = await session.try_pause_async()
        if success:
            IS_CURRENTLY_PAUSED = True
            print("Successfully paused.")
            return True
    else:
        print(f"\nAttempting to RESUME/PLAY: {title}")
        success = await session.try_play_async()
        if success:
            IS_CURRENTLY_PAUSED = False
            print("Successfully resumed playback.")
            return True

    print("Failed to perform toggle operation.")
    return False


def pause_play_active_system_media():
    """Synchronous entry point for single execution."""
    return asyncio.run(toggle_browser_media())


if __name__ == "__main__":
    pause_play_active_system_media()