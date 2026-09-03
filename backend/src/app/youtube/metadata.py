from dataclasses import dataclass
from datetime import date

import yt_dlp


class MetadataFetchError(RuntimeError):
    pass


@dataclass
class VideoMetadata:
    title: str
    thumbnail_url: str
    publish_date: date
    channel_id: str


def fetch_metadata(video_id: str) -> VideoMetadata:
    try:
        with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True, "extract_flat": False}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise MetadataFetchError(f"Couldn't fetch video metadata: {exc}") from exc
    if not info:
        raise MetadataFetchError("yt-dlp returned no metadata for this video.")
    raw_date = info.get("upload_date")
    if not raw_date:
        raise MetadataFetchError("This video has no publish date available.")
    channel_id = info.get("channel_id") or info.get("uploader_id")
    if not channel_id:
        raise MetadataFetchError("This video's channel ID is unavailable.")
    thumbnails = info.get("thumbnails") or []
    thumbnail = info.get("thumbnail") or (thumbnails[-1].get("url", "") if thumbnails else "")
    return VideoMetadata(
        title=info.get("title") or video_id,
        thumbnail_url=thumbnail,
        publish_date=date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])),
        channel_id=channel_id,
    )
