"""Runtime configuration, loaded from environment / .env file.

Nothing secret is hardcoded here. Every value can be overridden with an
environment variable of the same name (case-insensitive).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "AI DeskMate Backend"
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # --- MongoDB Atlas ------------------------------------------------------ #
    # Atlas connection string, e.g.
    #   mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
    # Leave empty and the app starts in a degraded state that says so clearly
    # rather than crashing on import.
    mongodb_uri: str = Field(default="")
    mongodb_db: str = Field(default="deskmate")
    # Atlas free tier (M0) is 512 MB, and the event log is the only collection
    # that grows without bound. A TTL index expires it automatically.
    event_retention_days: int = Field(default=14, ge=1, le=365)
    mongo_timeout_ms: int = Field(default=8000, ge=1000, le=60000)

    # --- Networking ---
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS: the dashboard in dev, plus Capacitor's native origins.
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://localhost",
            "https://localhost",
            "capacitor://localhost",
            "ionic://localhost",
        ]
    )
    cors_allow_all: bool = Field(default=False)

    # --- Auth ---
    require_auth: bool = Field(default=False)
    api_key: str | None = Field(default=None)
    device_token: str | None = Field(default=None)

    # --- Demo seed ---
    seed_demo_data: bool = Field(default=True)
    default_device_id: str = "deskmate-01"
    default_device_name: str = "AI DeskMate"
    default_user_email: str = "demo@deskmate.local"

    # --- Device liveness ---
    device_offline_after_seconds: int = 30
    scheduler_interval_seconds: float = 1.0

    # --- AI: Groq ----------------------------------------------------------- #
    # "groq" uses GroqCloud. "mock" keeps the assistant fully offline: the local
    # intent parser still handles every device command, and open-ended questions
    # get a short canned reply. The demo works either way.
    ai_provider: str = Field(default="groq")  # groq | mock
    groq_api_key: str | None = Field(default=None)
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")
    # Self-serve production models as of Sep 2026. The Llama models are
    # Enterprise-only on GroqCloud now and will 404 on a free key.
    #   openai/gpt-oss-20b   ~1000 tok/s, cheapest  <- default
    #   openai/gpt-oss-120b  ~500 tok/s,  stronger
    groq_model: str = Field(default="openai/gpt-oss-20b")
    # gpt-oss are reasoning models. Left at "default" they burn most of the
    # token budget thinking before emitting anything: measured 109 reasoning
    # tokens vs 5 at "low", and 220 ms vs 85 ms. We want two short sentences,
    # not deliberation. One of:
    #   none default minimal low medium high xhigh max   ("" = omit the field)
    groq_reasoning_effort: str = Field(default="low")
    groq_max_completion_tokens: int = Field(default=400, ge=32, le=8192)
    groq_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    groq_timeout_seconds: float = Field(default=25.0)
    # Speech-to-text. Available on the same key at $0.04/hour.
    groq_transcribe_model: str = Field(default="whisper-large-v3-turbo")
    # Whisper accepts up to 100 MB; this device sends a few hundred kB.
    transcribe_max_bytes: int = Field(default=8 * 1024 * 1024)
    # "" lets Whisper auto-detect, which is required for Hindi: forcing "en"
    # makes it translate or garble "light chalu karo". Forcing "hi" would break
    # English the other way round (it writes English in Devanagari).
    groq_transcribe_language: str = Field(default="")
    # Optional Whisper `prompt`. Off by default on purpose: tested 16 Oct 2026, a
    # prompt listing example commands made Whisper repeat them ("light band karo,
    # light chalu karo, light chalu karo"), which could flip the light the wrong
    # way. With no prompt, Hindi comes back in Devanagari and the intent parser
    # handles that directly.
    groq_transcribe_prompt: str = Field(default="")
    # Optional confidence gate on Whisper's `avg_logprob`. OFF by default (-99):
    # real speech from the device mic scored -1.31, the same range as synthetic
    # noise (-1.24..-1.33), so it rejected genuine commands. Silence is caught
    # by the hallucination phrase check in ai.py instead. Groq's no_speech_prob
    # is always 0, so it cannot be used either.
    transcribe_min_avg_logprob: float = Field(default=-99.0)
    # If set, every clip uploaded to /api/voice/transcribe is saved here as a
    # WAV (last 20 kept) so recording quality can be checked by ear or analysed.
    # Diagnostic only — leave empty normally; the files contain your voice.
    voice_debug_dir: str = Field(default="")

    # --- Weather: Open-Meteo ------------------------------------------------ #
    # No API key, no account, free for non-commercial use. Set either a city
    # name (geocoded once and cached) or explicit coordinates.
    weather_city: str = Field(default="")
    weather_latitude: float | None = Field(default=None)
    weather_longitude: float | None = Field(default=None)
    # "celsius" or "fahrenheit"
    weather_units: str = Field(default="celsius")
    # The device polls this; the backend caches so a dozen devices asking every
    # minute still means one upstream call per interval.
    weather_cache_minutes: int = Field(default=10, ge=1, le=180)
    weather_timeout_seconds: float = Field(default=12.0)

    @property
    def weather_configured(self) -> bool:
        return bool(self.weather_city.strip()) or (
            self.weather_latitude is not None and self.weather_longitude is not None
        )

    # --- TTS: Edge TTS (free, no key) --------------------------------------- #
    # Microsoft Edge TTS voice. No API key or account required.
    # Indian English: en-IN-NeerjaNeural (F), en-IN-PrabhatNeural (M)
    # US English: en-US-JennyNeural (F), en-US-GuyNeural (M)
    tts_voice: str = Field(default="en-IN-NeerjaNeural")
    # Must match the firmware's AUDIO_SAMPLE_RATE (chime.cpp I2S config).
    tts_sample_rate: int = Field(default=22050)

    # --- Study notes -------------------------------------------------------- #
    # Upload size cap. 10 MB covers a long PDF of notes; bigger uploads are
    # usually scans we cannot read anyway.
    notes_max_upload_bytes: int = Field(default=10 * 1024 * 1024)
    # Extracted text is truncated to this many characters before storage, both to
    # stay well inside Atlas's document limit and to bound what a quiz call sends.
    notes_max_extract_chars: int = Field(default=200_000)
    # How many notes to keep per device; the oldest is dropped past this.
    notes_max_count: int = Field(default=50, ge=1, le=500)

    @property
    def mongo_configured(self) -> bool:
        return bool(self.mongodb_uri.strip())

    @property
    def ai_live(self) -> bool:
        return self.ai_provider == "groq" and bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
