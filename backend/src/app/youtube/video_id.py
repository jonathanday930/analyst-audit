import re
from urllib.parse import parse_qs, urlparse


class InvalidYoutubeUrlError(ValueError):
    pass


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url: str) -> str:
    url = url.strip()
    if _VIDEO_ID_RE.match(url):
        return url
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in {"youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        else:
            for prefix in ("/shorts/", "/embed/", "/live/"):
                if parsed.path.startswith(prefix):
                    candidate = parsed.path.removeprefix(prefix).split("/")[0]
                    break
    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    raise InvalidYoutubeUrlError("Couldn't find a YouTube video in that URL.")
