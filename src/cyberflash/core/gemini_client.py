"""Gemini API client for CyberFlash AI assistant.

Wraps the ``google-genai`` SDK with device-context-aware prompting.
Gracefully falls back to local heuristics if the package is not installed
or no API key has been configured.

Free tier (as of 2026): Gemini 2.5 Flash — 10 RPM, 250 RPD, no credit card.
Get your key at: https://aistudio.google.com/apikey
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ── Package availability ──────────────────────────────────────────────────────

_GENAI_AVAILABLE = False
try:
    import google.genai as _genai  # type: ignore[import-untyped]

    _GENAI_AVAILABLE = True
except ImportError:
    _genai = None  # type: ignore[assignment]

# ── Model catalogue ───────────────────────────────────────────────────────────

AVAILABLE_MODELS: list[str] = [
    "gemini-2.5-flash",        # Best free tier — 10 RPM / 250 RPD
    "gemini-2.5-flash-lite",   # Fastest free — 15 RPM / 1000 RPD
    "gemini-2.5-pro",          # Smartest — 5 RPM / 100 RPD (free)
]

DEFAULT_MODEL = "gemini-2.5-flash"

# API key — loaded from CYBERFLASH_GEMINI_API_KEY env var or user config.
# Get your key at: https://aistudio.google.com/apikey
_BUILTIN_API_KEY = os.environ.get("CYBERFLASH_GEMINI_API_KEY", "")

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the CyberFlash AI assistant — an expert in Android device modding.
CyberFlash is a professional Android ROM flashing tool used by power users and developers.

Your expertise covers:
- Flashing custom ROMs, kernels, and recovery images via ADB / fastboot
- Rooting Android devices (Magisk, KernelSU, APatch)
- Creating and restoring full/media/partition backups
- Unlocking bootloaders safely
- Kali NetHunter installation and penetration testing setup
- A/B partition slot management
- Device rescue and unbrick via EDL (Qualcomm), Heimdall (Samsung), and stock fastboot
- Diagnosing ADB/fastboot errors and USB issues

Response style:
- Be concise and actionable — users are technically proficient
- Use markdown: **bold** for key terms, bullet lists for steps, `code` for commands
- Always warn about irreversible operations (data loss, bootloader unlock)
- When you have device context, tailor your answer to that specific device
- Never make up firmware download links — direct users to official/XDA sources
"""


# ── Client ────────────────────────────────────────────────────────────────────


class GeminiClient:
    """Calls the Google Gemini API for intelligent chat responses.

    Usage::

        client = GeminiClient(api_key="AIza...", model="gemini-2.5-flash")
        ok, msg = client.test_connection()
        if ok:
            reply = client.chat("How do I root a OnePlus 7 Pro?", device_context="guacamole")
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key.strip()
        self._model = model
        self._client = None

        if _GENAI_AVAILABLE and self._api_key:
            try:
                self._client = _genai.Client(api_key=self._api_key)
                logger.debug("GeminiClient initialised with model=%s", model)
            except Exception as exc:
                logger.warning("GeminiClient init failed: %s", exc)

    # ── Class-level helpers ───────────────────────────────────────────────────

    @staticmethod
    def is_package_available() -> bool:
        """Return True if google-genai is installed."""
        return _GENAI_AVAILABLE

    def is_configured(self) -> bool:
        """Return True if an API key is set and the client was created."""
        return self._client is not None

    # ── API calls ─────────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        device_context: str = "",
        page: str = "",
    ) -> str:
        """Send a message to Gemini with optional device context.

        Args:
            user_message:   The user's question or command.
            device_context: Human-readable device description (model, state, etc.)
            page:           Which CyberFlash page the user is currently on.

        Returns:
            The model's text response.

        Raises:
            RuntimeError:  If the client is not configured.
            Exception:     Any network / API error from the SDK.
        """
        if not self._client:
            raise RuntimeError("Gemini client not configured — no API key")

        # Prepend context lines so the model knows the device and page
        context_parts: list[str] = []
        if device_context:
            context_parts.append(f"Connected device: {device_context}")
        if page:
            context_parts.append(f"Current CyberFlash page: {page}")

        full_prompt = user_message
        if context_parts:
            full_prompt = "\n".join(context_parts) + "\n\n" + user_message

        response = self._client.models.generate_content(
            model=self._model,
            contents=full_prompt,
            config={"system_instruction": _SYSTEM_PROMPT},
        )
        return response.text or ""

    def test_connection(self) -> tuple[bool, str]:
        """Verify the API key and model are working.

        Returns:
            ``(True, success_message)`` or ``(False, error_message)``.
        """
        if not _GENAI_AVAILABLE:
            return (
                False,
                "google-genai package not installed. Run: pip install google-genai",
            )
        if not self._api_key:
            return False, "No API key configured"
        if not self._client:
            return False, "Client failed to initialise — check your API key"

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents="Reply with exactly: OK",
            )
            _ = response.text  # force evaluation
            return True, f"Connected — {self._model} ✓"
        except Exception as exc:
            return False, str(exc)
