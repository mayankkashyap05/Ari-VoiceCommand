"""Settings panel for microphone level and record/playback checks."""

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from i18n.translator import _
from ui.audio_diagnostics import AudioDiagnosticThread, _live_audio_diagnostic_threads
from ui.theme import secondary_btn_style


class _SafeAudioDiagnosticThread(AudioDiagnosticThread):
    def run(self):
        try:
            super().run()
        except Exception as exc:
            self.done.emit(self, False, str(exc))


class AudioDiagnosticPanel(QGroupBox):
    def __init__(self, input_device, output_device, parent=None):
        super().__init__(_("Microphone and Speaker Diagnostics"), parent)
        self._input_device = input_device
        self._output_device = output_device
        self._thread: AudioDiagnosticThread | None = None
        self._mode = ""
        self._closing = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Microphone Input Level:")))
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setFormat("%p%")
        layout.addWidget(self.level_bar)

        buttons = QHBoxLayout()
        self.monitor_button = QPushButton(_("Microphone Level Check"))
        self.monitor_button.setStyleSheet(secondary_btn_style())
        self.monitor_button.clicked.connect(self._toggle_monitor)
        buttons.addWidget(self.monitor_button)
        self.record_button = QPushButton(_("Record for 3 seconds, then play"))
        self.record_button.setStyleSheet(secondary_btn_style())
        self.record_button.clicked.connect(self._start_record_playback)
        buttons.addWidget(self.record_button)
        layout.addLayout(buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        finished = getattr(self.window(), "finished", None)
        if finished is not None:
            finished.connect(self.cancel)

    def _toggle_monitor(self):
        if self._thread is not None and self._thread.isRunning():
            if self._mode == "monitor":
                self._thread.requestInterruption()
                self.status.setText(_("Stopping microphone level check..."))
            return
        self._start(monitor_only=True)

    def _start_record_playback(self):
        if self._thread is None or not self._thread.isRunning():
            self._start(monitor_only=False)

    def _start(self, monitor_only: bool):
        self._closing = False
        self._mode = "monitor" if monitor_only else "record_playback"
        self.monitor_button.setText(_("Stop") if monitor_only else _("Microphone Level Check"))
        self.record_button.setEnabled(not monitor_only)
        self.status.setText(
            _("Checking microphone input...")
            if monitor_only
            else _("Recording for 3 seconds. Please speak for a moment...")
        )
        self.status.setStyleSheet("color: #888;")
        thread = _SafeAudioDiagnosticThread(
            self._input_device(), self._output_device(), monitor_only=monitor_only
        )
        thread.level_changed.connect(self.level_bar.setValue)
        thread.done.connect(self._on_done)
        thread.finished.connect(lambda t=thread: _live_audio_diagnostic_threads.discard(t))
        _live_audio_diagnostic_threads.add(thread)
        self._thread = thread
        thread.start()

    def _on_done(self, thread: AudioDiagnosticThread, success: bool, message: str):
        if self._closing or self._thread is not thread:
            return
        self._thread = None
        self._mode = ""
        self.monitor_button.setText(_("Microphone Level Check"))
        self.record_button.setEnabled(True)
        if message:
            self.status.setText(message)
            self.status.setStyleSheet(
                f"color: {'#27ae60' if success else '#e74c3c'}; font-weight: bold;"
            )
        elif success:
            self.status.setText("")
            self.level_bar.setValue(0)

    def cancel(self, *_args):
        self._closing = True
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()