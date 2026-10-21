from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    # Only needed for an "identity-linked" API key (one generated against a specific org member
    # rather than a plain workspace key) — Anthropic rejects those with a 400 unless every
    # request also carries the target workspace's id. Find it in the Console under Settings ->
    # Workspaces (it's the id in that workspace's URL). Leave unset for a plain API key.
    anthropic_workspace_id: str | None = None
    database_url: str = "sqlite:///./analyst_audit.db"
    port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # Routes YouTube transcript fetches through Webshare's rotating residential proxies — this
    # dev machine's own IP gets rate-limit-blocked by YouTube after a batch of concurrent
    # transcript fetches (youtube_transcript_api raises IpBlocked), and those bans can last
    # hours. Both unset (the default) means "no proxy" — fetch_transcript falls back to a
    # direct connection, today's behavior. Get credentials from a Webshare account (proxy
    # username/password, not your account login) and set both to enable.
    webshare_proxy_username: str | None = None
    webshare_proxy_password: str | None = None

    # Final fallback for transcript fetching (see app/youtube/transcript.py): a hosted API
    # (supadata.ai) that fetches the transcript from YouTube on ITS OWN infrastructure, not
    # ours — so a ban on this machine's IP doesn't affect it at all, unlike the yt-dlp fallback
    # which still hits YouTube directly. Unset (the default) means this fallback is skipped.
    supadata_api_key: str | None = None

    # Additional hosted fallback for transcript fetching. Unset (the default) means this
    # fallback is skipped.
    transcriptfetch_api_key: str | None = None

    # Third fallback for transcript fetching (see app/youtube/transcript.py). EasyTranscriber
    # accepts the canonical YouTube URL and fetches the transcript from its own infrastructure.
    # Unset (the default) means this fallback is skipped.
    easytranscriber_api_key: str | None = None

    # Minimum spacing (seconds) enforced between ANY two YouTube requests (transcript or
    # metadata) from this machine, across processes — see app/youtube/rate_limit.py and
    # testing/README.md's "Never fetch YouTube sources in parallel". A burst of concurrent
    # fetches, not steady sequential traffic, is what triggers YouTube's IpBlocked.
    youtube_min_request_interval_seconds: float = 5.0

    # All four pipeline passes default to claude-sonnet-5 for now, deliberately: Claude is the
    # quality benchmark before cheaper open-weight models are introduced. The model strings are
    # currently sent through the Anthropic-only client in app/llm/client.py, so changing one to a
    # Hugging Face model ID does not work until the provider-neutral client migration is done.
    # Don't downgrade any pass without re-validating its output first — see CLAUDE.md's Model
    # choice section for the reasoning and attribution failures this is intended to catch.
    claim_finder_model: str = "claude-sonnet-5"
    stance_extractor_model: str = "claude-sonnet-5"
    claim_analyzer_model: str = "claude-sonnet-5"
    meta_analyst_model: str = "claude-sonnet-5"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Make Fly-style PostgreSQL URLs explicitly select psycopg 3."""
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
