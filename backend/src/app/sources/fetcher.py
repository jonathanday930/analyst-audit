from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from app.sources.blog import BlogFetchError, fetch_blog_post
from app.youtube.metadata import MetadataFetchError, fetch_metadata
from app.youtube.transcript import TranscriptUnavailableError, fetch_transcript
from app.youtube.video_id import InvalidYoutubeUrlError, extract_video_id


class SourceFetchError(RuntimeError):
    pass


@dataclass
class FetchedSource:
    type: str
    original_url: str
    canonical_url: str
    source_key: str
    title: str
    content: str
    published_at: date | None = None
    youtube_video_id: str | None = None
    youtube_channel_id: str | None = None
    blog_domain: str | None = None

    @property
    def matching_identity(self) -> str:
        return self.youtube_channel_id if self.type == "video" else (self.blog_domain or "")


def detect_source_type(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return "video" if host in {"youtube.com", "music.youtube.com", "youtu.be"} else "blog"


def fetch_source(url: str) -> FetchedSource:
    source_type = detect_source_type(url)
    if source_type == "video":
        try:
            video_id = extract_video_id(url)
            metadata = fetch_metadata(video_id)
            transcript = fetch_transcript(video_id)
        except (InvalidYoutubeUrlError, MetadataFetchError, TranscriptUnavailableError) as exc:
            raise SourceFetchError(str(exc)) from exc
        return FetchedSource(
            type="video",
            original_url=url,
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
            source_key=video_id,
            title=metadata.title,
            content=transcript,
            published_at=metadata.publish_date,
            youtube_video_id=video_id,
            youtube_channel_id=metadata.channel_id,
        )
    try:
        post = fetch_blog_post(url)
    except BlogFetchError as exc:
        raise SourceFetchError(str(exc)) from exc
    return FetchedSource(
        type="blog",
        original_url=url,
        canonical_url=post.url,
        source_key=post.url,
        title=post.title,
        content=post.content,
        blog_domain=post.domain,
    )
