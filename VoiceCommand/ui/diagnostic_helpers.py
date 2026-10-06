"""Small helper used by the device diagnostics on the settings screen."""
from __future__ import annotations

import logging
import math
import struct

from i18n.translator import _


def run_tts_diagnostic(
    settings: dict,
    selected_mode: str,
    output_device_name: str,
    sentence: str,
    provider_factory=None,
    is_cancelled=None,
) -> tuple[bool, str]:
    """Run TTS with the current selection and return whether the selected engine actually ran."""
    from audio.audio_manager import output_device_override
    from tts.tts_factory import create_tts_provider

    factory = provider_factory or create_tts_provider
    provider = None
    try:
        with output_device_override(output_device_name):
            provider, actual_mode = factory(settings)
            if is_cancelled is not None and is_cancelled():
                return False, ""
            if actual_mode != selected_mode:
                return False, _(
                    "The selected TTS engine could not be initialized, so another engine was used instead. Please check the settings."
                )
            if not provider.speak(sentence):
                return False, _("The TTS test playback failed. Please check the settings and the output device.")
        return True, _("Test playback with the currently selected TTS engine finished.")
    except Exception as exc:
        return False, _("The TTS test playback failed: {error}").format(error=exc)
    finally:
        _cleanup_provider(provider)


def transcribe_diagnostic_sample(audio_data, settings: dict, provider_factory=None) -> tuple[bool, str]:
    """Recognize the sample captured with the current STT settings."""
    from core.stt_provider import create_stt_provider

    factory = provider_factory or create_stt_provider
    provider = None
    try:
        provider = factory(settings)
        text = provider.transcribe(audio_data)
        if not text or not str(text).strip():
            return False, _("Speech was not recognized. Please say it again.")
        return True, _("Recognition result: {text}").format(text=str(text).strip())
    except Exception as exc:
        return False, _("The speech recognition test failed: {error}").format(error=exc)
    finally:
        _cleanup_provider(provider)


def _cleanup_provider(provider) -> None:
    """Clean up the provider created for diagnostics. A cleanup failure does not affect the diagnostic result."""
    if provider is None or not hasattr(provider, "cleanup"):
        return
    try:
        provider.cleanup()
    except Exception as exc:
        logging.debug("Diagnostic provider cleanup failed: %s", exc)


def resolve_input_device_index(selected_name: str, devices: list[dict]) -> int | None:
    """Convert the input device name selected before saving into a PyAudio input device index."""
    if not selected_name:
        return None
    wanted = _normalize_device_name(selected_name)
    for index, device in enumerate(devices):
        if device.get("maxInputChannels", 0) > 0 and _normalize_device_name(
            str(device.get("name", ""))
        ) == wanted:
            return index
    raise ValueError(_("The selected microphone could not be found. Please choose the device again."))


def pcm_level_percent(pcm_data: bytes) -> int:
    """Compute the RMS level of 16-bit little-endian PCM on a 0~100 scale."""
    usable_length = len(pcm_data) - len(pcm_data) % 2
    if usable_length == 0:
        return 0
    sample_count = usable_length // 2
    square_total = sum(
        sample * sample
        for (sample,) in struct.iter_unpack("<h", pcm_data[:usable_length])
    )
    rms = math.sqrt(square_total / sample_count)
    return min(100, round(rms * 100 / 32768))


def _normalize_device_name(name: str) -> str:
    return "".join(name.split()).casefold()
