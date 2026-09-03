from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

_PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]


class TranscriptUnavailableError(RuntimeError):
    pass


def fetch_transcript(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
    except TranscriptsDisabled as exc:
        raise TranscriptUnavailableError("This video has captions/transcripts disabled.") from exc
    except VideoUnavailable as exc:
        raise TranscriptUnavailableError("This video is unavailable.") from exc
    try:
        transcript = transcript_list.find_transcript(_PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        available = list(transcript_list)
        if not available:
            raise TranscriptUnavailableError("No transcript is available for this video.")
        transcript = available[0]
    return " ".join(segment.text.strip() for segment in transcript.fetch() if segment.text.strip())
