"""Microphone checks and recording playback tasks for the settings screen."""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from audio.audio_manager import (
    GlobalAudio,
    find_output_device_candidates,
    get_audio_lock,
    get_audio_output_lock,
)
from i18n.translator import _
from ui.diagnostic_helpers import pcm_level_percent, resolve_input_device_index


_live_audio_diagnostic_threads: set[QThread] = set()


class AudioDiagnosticThread(QThread):
    level_changed = Signal(int)
    done = Signal(object, bool, str)

    def __init__(
        self,
        input_device_name: str,
        output_device_name: str,
        monitor_only: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.input_device_name = input_device_name
        self.output_device_name = output_device_name
        self.monitor_only = monitor_only

    def run(self):
        import pyaudio

        input_lock = get_audio_lock()
        output_lock = get_audio_output_lock()
        input_stream = None
        input_acquired = False
        pa = None
        try:
            pa = GlobalAudio.get_instance()
            input_devices = [pa.get_device_info_by_index(i) for i in range(pa.get_device_count())]
            input_device_index = resolve_input_device_index(self.input_device_name, input_devices)

            output_device_indices = []
            if not self.monitor_only:
                if self.output_device_name:
                    output_device_indices = find_output_device_candidates(self.output_device_name)
                    if not output_device_indices:
                        raise RuntimeError(_("The selected speaker could not be found. Please choose the device again."))
                else:
                    output_device_indices = [None]

            if not input_lock.acquire(timeout=3):
                raise RuntimeError(_("The microphone is in use by another task. Please try again in a moment."))
            input_acquired = True
            input_stream = GlobalAudio.open_stream(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=input_device_index,
                frames_per_buffer=1024,
            )

            chunks: list[bytes] = []
            started = time.monotonic()
            capture_seconds = None if self.monitor_only else 3.0
            while not self.isInterruptionRequested():
                if capture_seconds is not None and time.monotonic() - started >= capture_seconds:
                    break
                chunk = input_stream.read(1024, exception_on_overflow=False)
                self.level_changed.emit(pcm_level_percent(chunk))
                if not self.monitor_only:
                    chunks.append(chunk)

            GlobalAudio.close_stream(input_stream)
            input_stream = None
            input_lock.release()
            input_acquired = False

            if self.isInterruptionRequested():
                self.done.emit(self, True, "")
                return
            if self.monitor_only:
                self.done.emit(self, True, "")
                return

            if not output_lock.acquire(timeout=3):
                raise RuntimeError(_("The speaker is in use by another task. Please try again in a moment."))
            try:
                audio_data = b"".join(chunks)
                last_error = None
                output_stream = None
                for device_index in output_device_indices:
                    try:
                        output_stream = GlobalAudio.open_stream(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=16000,
                            output=True,
                            output_device_index=device_index,
                            frames_per_buffer=1024,
                        )
                        break
                    except Exception as exc:
                        last_error = exc
                if output_stream is None:
                    raise RuntimeError(
                        _("Could not open the speaker output device: {error}").format(error=last_error)
                    )
                try:
                    frame_bytes = 1024 * 2
                    for offset in range(0, len(audio_data), frame_bytes):
                        if self.isInterruptionRequested():
                            break
                        output_stream.write(audio_data[offset:offset + frame_bytes])
                finally:
                    GlobalAudio.close_stream(output_stream)
            finally:
                output_lock.release()

            if self.isInterruptionRequested():
                self.done.emit(self, True, "")
            else:
                self.done.emit(self, True, _("Played the recording through the selected speaker."))
        except Exception as exc:
            self.done.emit(self, False, str(exc))
        finally:
            if input_stream is not None:
                GlobalAudio.close_stream(input_stream)
            if input_acquired:
                input_lock.release()
