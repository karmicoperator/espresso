"""
Local video storage for rendered Manim visualizations.

Stores videos in the media/videos/ directory and serves them via the API.
"""

import os
from pathlib import Path
from typing import Optional

# Get media directory from environment or use default
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "./media/videos"))

# Ensure directory exists
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


async def save_video(video_bytes: bytes, filename: str) -> str:
    """
    Save video bytes to local storage.

    Args:
        video_bytes: MP4 video data
        filename: Filename to save as (e.g., "viz_001.mp4")

    Returns:
        URL path to access the video (e.g., "/api/video/viz_001")
    """
    # Ensure filename has .mp4 extension
    if not filename.endswith(".mp4"):
        filename = f"{filename}.mp4"

    # Save to media directory
    file_path = MEDIA_DIR / filename
    file_path.write_bytes(video_bytes)

    # Return the API URL (without .mp4 extension for cleaner URLs)
    video_id = filename.replace(".mp4", "")
    return f"/api/video/{video_id}"


def get_video_path(video_id: str) -> Optional[Path]:
    """
    Get the file path for a video by its ID.

    Args:
        video_id: Video identifier (e.g., "viz_001")

    Returns:
        Path to the video file, or None if not found
    """
    # Try with .mp4 extension
    file_path = MEDIA_DIR / f"{video_id}.mp4"
    if file_path.exists():
        return file_path

    # Try without extension (in case ID already has it)
    file_path = MEDIA_DIR / video_id
    if file_path.exists():
        return file_path

    return None


def get_video_url(video_id: str) -> Optional[str]:
    """
    Get the API URL for a video if it exists.

    Args:
        video_id: Video identifier (e.g., "viz_001")

    Returns:
        URL path (e.g., "/api/video/viz_001"), or None if not found
    """
    if get_video_path(video_id):
        return f"/api/video/{video_id}"
    return None


def list_videos() -> list[str]:
    """List all video IDs in storage."""
    videos = []
    for f in MEDIA_DIR.glob("*.mp4"):
        videos.append(f.stem)  # filename without extension
    return sorted(videos)


def delete_video(video_id: str) -> bool:
    """
    Delete a video from storage.

    Returns:
        True if deleted, False if not found
    """
    path = get_video_path(video_id)
    if path:
        path.unlink()
        return True
    return False
