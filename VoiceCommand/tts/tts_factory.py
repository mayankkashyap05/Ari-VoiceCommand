"""Factory that creates TTS providers based on settings and computes signatures."""

import logging
import os
from core.config_manager import ConfigManager

_TTS_SIGNATURE_KEYS = (
    "tts_mode",
    "fish_api_key",
    "fish_reference_id",
    "cosyvoice_reference_text",
    "cosyvoice_speed",
    "cosyvoice_dir",
    "tts_reference_wav",
    "tts_volume",
    "openai_compat_tts_base_url",
    "openai_compat_tts_api_key",
    "openai_compat_tts_model",
    "openai_compat_tts_voice",
    "openai_compat_tts_clone_mode",
    "openai_compat_tts_emotion_mode",
    "fish_model",
    "openai_tts_api_key",
    "openai_api_key",
    "openai_tts_voice",
    "openai_tts_model",
    "openai_tts_custom_voice_id",
    "elevenlabs_api_key",
    "elevenlabs_voice_id",
    "elevenlabs_model_id",
    "edge_tts_voice",
    "edge_tts_rate",
    "tts_emotion_enabled",
    "tts_sentence_timeout_seconds",
    "tts_cache_max_bytes",
)


def build_tts_signature(settings=None):
    """Compute a comparison signature of the current TTS settings."""
    settings = settings or ConfigManager.load_settings()
    return tuple(settings.get(key) for key in _TTS_SIGNATURE_KEYS)


def _create_local(settings, wait_ready=True):
    provider = None
    try:
        from tts.cosyvoice_tts import CosyVoiceTTS
        from tts.voice_reference import get_reference_text, get_reference_wav
        # Uses the configured path even for trial playback from the settings screen.
        configured_dir = settings.get("cosyvoice_dir", "")
        provider = CosyVoiceTTS(
            reference_wav=get_reference_wav(settings),
            reference_text=get_reference_text(settings),
            speed=float(settings.get("cosyvoice_speed", 0.9)),
            cosyvoice_dir=configured_dir if configured_dir and os.path.isdir(configured_dir) else None,
        )
        if wait_ready and not provider.wait_until_ready():
            raise RuntimeError(
                getattr(provider, "_worker_error", None)
                or "CosyVoice3 worker did not become ready"
            )
        logging.info("CosyVoice3 local TTS initialization complete")
        return provider, "local"
    except Exception as e:
        if provider is not None:
            try:
                provider.cleanup()
            except (
                AttributeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as cleanup_error:
                logging.debug("Failed to clean up failed CosyVoice3 worker: %s", cleanup_error)
        logging.error("CosyVoice3 worker initialization failed: %s", e)
        raise RuntimeError("CosyVoice3 worker initialization failed") from e


def _create_openai_compat_tts(settings):
    try:
        from i18n.translator import get_language
        from tts.tts_openai_compat import OpenAICompatTTS
        from tts.voice_reference import get_reference_text, get_reference_wav

        provider = OpenAICompatTTS(
            base_url=settings.get("openai_compat_tts_base_url", ""),
            api_key=settings.get("openai_compat_tts_api_key", ""),
            model=settings.get("openai_compat_tts_model", ""),
            voice=settings.get("openai_compat_tts_voice", ""),
            clone_mode=settings.get("openai_compat_tts_clone_mode", "none"),
            emotion_mode=settings.get("openai_compat_tts_emotion_mode", "instructions"),
            reference_wav=get_reference_wav(settings),
            reference_text=get_reference_text(settings),
            emotion_enabled=settings.get("tts_emotion_enabled", True),
            language=get_language(),
            tts_volume=settings.get("tts_volume", 1.0),
        )
        logging.info("OpenAI-compatible TTS initialization complete")
        return provider, "openai_compat_tts"
    except Exception as e:
        logging.error("OpenAI-compatible TTS init failed, falling back to Edge TTS: %s", e)
        return None


def _create_openai_tts(settings):
    try:
        from tts.tts_openai import OpenAITTS
        provider = OpenAITTS(
            api_key=settings.get("openai_tts_api_key", "") or settings.get("openai_api_key", ""),
            voice=settings.get("openai_tts_voice", "nova"),
            model=settings.get("openai_tts_model", "tts-1"),
            emotion_enabled=settings.get("tts_emotion_enabled", True),
            custom_voice_id=settings.get("openai_tts_custom_voice_id", ""),
            tts_volume=settings.get("tts_volume", 1.0),
        )
        logging.info("OpenAI TTS initialization complete")
        return provider, "openai_tts"
    except Exception as e:
        logging.error(f"OpenAI TTS init failed, falling back to Edge TTS: {e}")
        return None


def _create_elevenlabs(settings):
    try:
        from tts.tts_elevenlabs import ElevenLabsTTS
        provider = ElevenLabsTTS(
            api_key=settings.get("elevenlabs_api_key", ""),
            voice_id=settings.get("elevenlabs_voice_id", ""),
            model_id=settings.get("elevenlabs_model_id", "eleven_multilingual_v2"),
            emotion_enabled=settings.get("tts_emotion_enabled", True),
            tts_volume=settings.get("tts_volume", 1.0),
        )
        logging.info("ElevenLabs TTS initialization complete")
        return provider, "elevenlabs"
    except Exception as e:
        logging.error(f"ElevenLabs TTS init failed, falling back to Edge TTS: {e}")
        return None


def _create_fish(settings):
    api_key = settings.get("fish_api_key", "")
    if api_key:
        try:
            from tts.fish_tts_ws import FishTTSWebSocket
            provider = FishTTSWebSocket(
                api_key=api_key,
                reference_id=settings.get("fish_reference_id", ""),
                model=settings.get("fish_model", "s2.1-pro-free"),
                tts_volume=settings.get("tts_volume", 1.0),
            )
            logging.info("Fish Audio TTS initialization complete")
            return provider, "fish"
        except Exception as e:
            logging.error(f"Fish Audio TTS init failed, falling back to Edge TTS: {e}")
            return None
    else:
        logging.warning("No Fish API key configured, switching to Edge TTS.")
        return None


def _create_edge(settings):
    # Default & Fallback: Edge TTS (free & high quality)
    try:
        from tts.tts_edge import EdgeTTS
        provider = EdgeTTS(
            voice=settings.get("edge_tts_voice", "en-US-JennyNeural"),
            rate=settings.get("edge_tts_rate", "+0%"),
            emotion_enabled=settings.get("tts_emotion_enabled", True),
            synthesis_timeout_seconds=settings.get("tts_sentence_timeout_seconds", 10),
            cache_max_bytes=settings.get("tts_cache_max_bytes", 50 * 1024 * 1024),
            tts_volume=settings.get("tts_volume", 1.0),
        )
        logging.info("Edge TTS initialization complete")
        return provider, "edge"
    except Exception as e:
        logging.error(f"Edge TTS initialization failed: {e}")
        raise


_TTS_PROVIDER_CREATORS = {
    "local": _create_local,
    "openai_compat_tts": _create_openai_compat_tts,
    "openai_tts": _create_openai_tts,
    "elevenlabs": _create_elevenlabs,
    "fish": _create_fish,
    "edge": _create_edge,
}


def create_tts_provider(settings=None, wait_ready=True):
    """Create a TTS provider instance based on tts_mode setting.

    If wait_ready=False, the caller handles waiting for the local engine's READY signal.
    """
    settings = settings or ConfigManager.load_settings()
    tts_mode = settings.get("tts_mode", "edge")
    for provider_mode, creator in _TTS_PROVIDER_CREATORS.items():
        if tts_mode == provider_mode:
            if creator is _create_local:
                provider = creator(settings, wait_ready=wait_ready)
            else:
                provider = creator(settings)
            if provider is not None:
                return provider
            tts_mode = "edge"
    return _create_edge(settings)
