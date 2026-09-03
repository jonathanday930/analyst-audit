import pytest

from app.youtube.video_id import InvalidYoutubeUrlError, extract_video_id


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ?t=5",
    "https://www.youtube.com/shorts/dQw4w9WgXcQ", "youtube.com/embed/dQw4w9WgXcQ",
])
def test_extract_video_id(url: str) -> None:
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_rejects_non_youtube() -> None:
    with pytest.raises(InvalidYoutubeUrlError):
        extract_video_id("https://example.com/watch?v=dQw4w9WgXcQ")
