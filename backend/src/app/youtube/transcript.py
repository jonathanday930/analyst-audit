import re

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.config import get_settings
from app.youtube import transcript_cache
from app.youtube.rate_limit import throttle

_PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]


class TranscriptUnavailableError(RuntimeError):
    pass


def _client() -> YouTubeTranscriptApi:
    """A direct connection by default; routed through Webshare's rotating proxies when
    configured (see Settings.webshare_proxy_username/password) — this machine's own IP gets
    blocked by YouTube after a burst of concurrent transcript fetches, and that ban can outlast
    a single debugging session."""
    settings = get_settings()
    if settings.webshare_proxy_username and settings.webshare_proxy_password:
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=settings.webshare_proxy_username,
                proxy_password=settings.webshare_proxy_password,
            )
        )
    return YouTubeTranscriptApi()


_VTT_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def _vtt_to_plain_text(vtt_text: str) -> str:
    """Strip WebVTT structure (header, cue numbers, timestamps, inline `<...>` tags) down to
    plain spoken text, dropping consecutive duplicate lines — YouTube's auto-caption VTT repeats
    the same line across several rolling cues, which would otherwise triple up the transcript."""
    lines: list[str] = []
    last_line: str | None = None
    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.isdigit() or _VTT_TIMESTAMP_RE.match(line):
            continue
        line = re.sub(r"\s+", " ", _VTT_TAG_RE.sub("", line)).strip()
        if line and line != last_line:
            lines.append(line)
            last_line = line
    return " ".join(lines)


def _fetch_via_ytdlp(video_id: str) -> str:
    """Fallback caption fetch using yt-dlp instead of youtube_transcript_api — a different
    request shape (different endpoints, headers, client emulation) that doesn't always trip
    YouTube's anti-bot block at the exact same moment as the primary path, even from the same
    IP. Not a guarantee, just a second chance; see fetch_transcript below for when this gets
    tried."""
    throttle()
    try:
        with yt_dlp.YoutubeDL(
            {
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": _PREFERRED_LANGUAGES,
            }
        ) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise TranscriptUnavailableError(f"yt-dlp fallback also failed: {exc}") from exc

    tracks_by_lang = {**(info.get("automatic_captions") or {}), **(info.get("subtitles") or {})}
    tracks = next((tracks_by_lang[lang] for lang in _PREFERRED_LANGUAGES if lang in tracks_by_lang), None)
    if not tracks:
        raise TranscriptUnavailableError("yt-dlp found no English captions for this video either.")
    track = next((t for t in tracks if t.get("ext") == "vtt"), tracks[0])

    import httpx

    try:
        response = httpx.get(track["url"], timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TranscriptUnavailableError(f"Fetching yt-dlp's caption track failed: {exc}") from exc
    text = _vtt_to_plain_text(response.text)
    if not text:
        raise TranscriptUnavailableError("yt-dlp's caption track for this video was empty.")
    return text


def _fetch_via_supadata(video_id: str) -> str:
    """Final fallback: fetches the transcript via supadata.ai's hosted API, which pulls it from
    YouTube on ITS OWN infrastructure rather than this machine's — so a ban on this machine's IP
    is irrelevant to it, unlike the yt-dlp fallback above, which still hits YouTube directly and
    fails the same way the primary path does. Skipped (raises TranscriptUnavailableError, caught
    like every other fallback) when no API key is configured."""
    settings = get_settings()
    if not settings.supadata_api_key:
        raise TranscriptUnavailableError("Supadata fallback not configured (no SUPADATA_API_KEY).")

    import httpx

    try:
        response = httpx.get(
            "https://api.supadata.ai/v1/youtube/transcript",
            params={"videoId": video_id, "text": "true"},
            headers={"x-api-key": settings.supadata_api_key},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TranscriptUnavailableError(f"Supadata request failed: {exc}") from exc

    text = response.json().get("content")
    if not isinstance(text, str) or not text.strip():
        raise TranscriptUnavailableError("Supadata returned no transcript text for this video.")
    return text.strip()


def _fetch_via_transcriptfetch(video_id: str) -> str:
    """Additional hosted fallback via TranscriptFetch's timestamped transcript API."""
    settings = get_settings()
    if not settings.transcriptfetch_api_key:
        raise TranscriptUnavailableError(
            "TranscriptFetch fallback not configured (no TRANSCRIPTFETCH_API_KEY)."
        )

    import httpx

    try:
        response = httpx.post(
            "https://transcriptfetch.com/api/v2/transcripts/video",
            headers={"Authorization": f"Bearer {settings.transcriptfetch_api_key}"},
            json={"video": f"https://www.youtube.com/watch?v={video_id}"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TranscriptUnavailableError(f"TranscriptFetch request failed: {exc}") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    segments = data.get("segments") if isinstance(data, dict) else None
    text = (
        " ".join(segment.get("text", "").strip() for segment in segments)
        if isinstance(segments, list)
        else ""
    )
    if not text.strip():
        raise TranscriptUnavailableError(
            "TranscriptFetch returned no transcript text for this video."
        )
    return text.strip()


def _fetch_via_easytranscriber(video_id: str) -> str:
    """Third fallback via EasyTranscriber's URL-based transcript API."""
    settings = get_settings()
    if not settings.easytranscriber_api_key:
        raise TranscriptUnavailableError(
            "EasyTranscriber fallback not configured (no EASYTRANSCRIBER_API_KEY)."
        )

    import httpx

    try:
        response = httpx.post(
            "https://www.easytranscriber.com/api/v1/transcribe",
            headers={"Authorization": f"Bearer {settings.easytranscriber_api_key}"},
            json={"url": f"https://www.youtube.com/watch?v={video_id}"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TranscriptUnavailableError(f"EasyTranscriber request failed: {exc}") from exc

    text = payload.get("transcript") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise TranscriptUnavailableError(
            "EasyTranscriber returned no transcript text for this video."
        )
    return text.strip()


def _fetch_via_primary(video_id: str) -> str:
    transcript_list = _client().list(video_id)
    try:
        transcript = transcript_list.find_transcript(_PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        available = list(transcript_list)
        if not available:
            raise TranscriptUnavailableError("No transcript is available for this video.")
        transcript = available[0]
    return " ".join(segment.text.strip() for segment in transcript.fetch() if segment.text.strip())


def fetch_transcript(video_id: str) -> str:
    cached = transcript_cache.read(video_id)
    if cached is not None:
        return cached

    throttle()
    try:
        text = _fetch_via_primary(video_id)
    except TranscriptsDisabled as exc:
        raise TranscriptUnavailableError("This video has captions/transcripts disabled.") from exc
    except VideoUnavailable as exc:
        raise TranscriptUnavailableError("This video is unavailable.") from exc
    except TranscriptUnavailableError:
        # "No transcript is available at all" from _fetch_via_primary — a fact about the video,
        # not a network block, so a different request path won't change the answer.
        raise
    except Exception as primary_exc:
        # Anything else — youtube_transcript_api's own RequestBlocked/IpBlocked/PoTokenRequired,
        # or a raw network/retry error surfacing from requests/urllib3 underneath it — is worth
        # trying every fallback path before giving up. Ordered cheapest/most-likely-to-work
        # first: yt-dlp still hits YouTube directly from this machine (fails the same way as the
        # primary path if this IS an IP ban), EasyTranscriber and Supadata hit YouTube from their
        # own infrastructure (unaffected by an IP ban on this machine either way). Keep the
        # hosted fallbacks in this order: EasyTranscriber, then Supadata, then TranscriptFetch.
        errors = [f"primary fetch failed ({primary_exc})"]
        text = None
        for fallback in (
            _fetch_via_ytdlp,
            _fetch_via_easytranscriber,
            _fetch_via_supadata,
            _fetch_via_transcriptfetch,
        ):
            try:
                text = fallback(video_id)
                break
            except TranscriptUnavailableError as fallback_exc:
                errors.append(f"{fallback.__name__} failed ({fallback_exc})")
        if text is None:
            raise TranscriptUnavailableError("; ".join(errors)) from primary_exc

    transcript_cache.write(video_id, text)
    return text
