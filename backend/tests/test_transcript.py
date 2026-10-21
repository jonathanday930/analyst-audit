from types import SimpleNamespace

import httpx
import pytest

from app.youtube import transcript


def test_easytranscriber_uses_bearer_auth_and_canonical_video_url(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {"transcript": "  transcript from EasyTranscriber  "}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(
        transcript,
        "get_settings",
        lambda: SimpleNamespace(easytranscriber_api_key="et_test_key"),
    )
    monkeypatch.setattr(httpx, "post", post)

    assert transcript._fetch_via_easytranscriber("dQw4w9WgXcQ") == "transcript from EasyTranscriber"
    assert calls == [
        (
            "https://www.easytranscriber.com/api/v1/transcribe",
            {
                "headers": {"Authorization": "Bearer et_test_key"},
                "json": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                "timeout": 30.0,
            },
        )
    ]


def test_easytranscriber_is_skipped_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        transcript,
        "get_settings",
        lambda: SimpleNamespace(easytranscriber_api_key=None),
    )

    with pytest.raises(transcript.TranscriptUnavailableError, match="EASYTRANSCRIBER_API_KEY"):
        transcript._fetch_via_easytranscriber("dQw4w9WgXcQ")


def test_easytranscriber_http_errors_are_normalized(monkeypatch) -> None:
    monkeypatch.setattr(
        transcript,
        "get_settings",
        lambda: SimpleNamespace(easytranscriber_api_key="et_test_key"),
    )
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )

    with pytest.raises(transcript.TranscriptUnavailableError, match="EasyTranscriber request failed"):
        transcript._fetch_via_easytranscriber("dQw4w9WgXcQ")


def test_successful_primary_fetch_is_cached(monkeypatch) -> None:
    cache = SimpleNamespace(read=lambda _video_id: None, write=lambda *_args: None)
    writes = []
    cache.write = lambda *args: writes.append(args)
    monkeypatch.setattr(transcript, "transcript_cache", cache)
    monkeypatch.setattr(transcript, "throttle", lambda: None)
    monkeypatch.setattr(transcript, "_fetch_via_primary", lambda _video_id: "primary transcript")

    assert transcript.fetch_transcript("video-1") == "primary transcript"
    assert writes == [("video-1", "primary transcript")]


def test_successful_fallback_fetch_is_cached(monkeypatch) -> None:
    cache = SimpleNamespace(read=lambda _video_id: None, write=lambda *_args: None)
    writes = []
    cache.write = lambda *args: writes.append(args)
    monkeypatch.setattr(transcript, "transcript_cache", cache)
    monkeypatch.setattr(transcript, "throttle", lambda: None)
    monkeypatch.setattr(
        transcript,
        "_fetch_via_primary",
        lambda _video_id: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    monkeypatch.setattr(
        transcript,
        "_fetch_via_ytdlp",
        lambda _video_id: (_ for _ in ()).throw(
            transcript.TranscriptUnavailableError("yt-dlp unavailable")
        ),
    )
    monkeypatch.setattr(transcript, "_fetch_via_easytranscriber", lambda _video_id: "fallback transcript")
    monkeypatch.setattr(
        transcript,
        "_fetch_via_supadata",
        lambda _video_id: (_ for _ in ()).throw(
            AssertionError("Supadata should not run after EasyTranscriber succeeds")
        ),
    )

    assert transcript.fetch_transcript("video-2") == "fallback transcript"
    assert writes == [("video-2", "fallback transcript")]


def test_transcriptfetch_joins_timestamped_segments(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"ok": True, "data": {"segments": [{"text": " first "}, {"text": "second"}]}}

    monkeypatch.setattr(
        transcript,
        "get_settings",
        lambda: SimpleNamespace(transcriptfetch_api_key="tf_test_key"),
    )
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kwargs: (calls.append((url, kwargs)) or Response()),
    )

    assert transcript._fetch_via_transcriptfetch("dQw4w9WgXcQ") == "first second"
    assert calls[0][0] == "https://transcriptfetch.com/api/v2/transcripts/video"
    assert calls[0][1]["headers"] == {"Authorization": "Bearer tf_test_key"}
    assert calls[0][1]["json"] == {"video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
