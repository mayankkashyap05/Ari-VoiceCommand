"""
TTS settings page widget
"""
import logging
import os
import threading
from types import SimpleNamespace

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QComboBox, QGroupBox,
    QScrollArea, QProgressDialog, QMessageBox, QFileDialog, QCheckBox,
)
from PySide6.QtCore import QObject, Qt, Signal, Slot

from i18n.translator import _
from ui.theme import scrollbar_style, secondary_btn_style
from ui.common import create_muted_label
from ui.local_installers import (
    CosyVoiceInstallerThread,
    LocalInstallSection,
    OllamaInstallDialog,
    OllamaInstallerThread,
)
from ui.tts_diagnostics import TTSDiagnosticPanel


_live_installer_threads = set()


def _track_installer_thread(thread):
    _live_installer_threads.add(thread)
    thread.finished.connect(lambda tracked=thread: _release_installer_thread(tracked))


def _release_installer_thread(thread):
    _live_installer_threads.discard(thread)
    thread.deleteLater()


def _installer_running(thread_type) -> bool:
    """Reports whether an installation of the same type started earlier is still running after the settings window is closed and reopened."""
    return any(
        isinstance(thread, thread_type) and thread.isRunning()
        for thread in _live_installer_threads
    )


class _TTSActionRelay(QObject):
    """Relays worker thread results to the GUI thread. Kept as a single module-level instance because it must outlive the settings window."""

    completed = Signal(object, object, str)


_ACTION_RELAY: _TTSActionRelay | None = None


def _action_relay() -> _TTSActionRelay:
    global _ACTION_RELAY
    if _ACTION_RELAY is None:
        _ACTION_RELAY = _TTSActionRelay()
    return _ACTION_RELAY


# ── TTS engine definitions ──────────────────────────────────────────────────────────────

def _tts_modes():
    return [
        (_("Fish Audio (API)"),    "fish"),
        (_("Local (CosyVoice3)"),   "local"),
        (_("OpenAI-compatible TTS"), "openai_compat_tts"),
        (_("OpenAI TTS"),          "openai_tts"),
        (_("ElevenLabs"),          "elevenlabs"),
        (_("Edge TTS (free)"),     "edge"),
    ]


class _TTSSettingsPage(QWidget):
    """TTS engine settings tab widget."""

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._tts_groups: dict[str, QGroupBox] = {}
        self._ollama_install_thread: OllamaInstallerThread | None = None
        self._ollama_progress_dialog: QProgressDialog | None = None
        self._cosyvoice_install_thread: CosyVoiceInstallerThread | None = None
        self._cosyvoice_progress_dialog: QProgressDialog | None = None
        self._closed = False
        self._tts_action_job: SimpleNamespace | None = None
        # Create and connect the relay on the GUI thread so results are always handled there.
        _action_relay().completed.connect(self._finish_elevenlabs_action)
        self._init_ui()

    # ── UI layout ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(scrollbar_style())

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setSpacing(15)

        # Local installation section
        self._ollama_executable_path = str(self._settings.get("ollama_executable_path", "") or "")
        self.local_install_section = LocalInstallSection(
            self, cosyvoice_dir_provider=lambda: self.cosyvoice_dir_input.text()
        )
        self.local_install_section.ollama_install_requested.connect(self._open_ollama_installer)
        self.local_install_section.cosyvoice_install_requested.connect(self._install_cosyvoice)
        self.local_install_section.ollama_locate_requested.connect(self._locate_ollama)
        self.local_install_section.detection_finished.connect(self._on_local_install_detected)
        vbox.addWidget(self.local_install_section)

        tts_group = self._build_tts_group()
        vbox.addWidget(tts_group)
        vbox.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._on_tts_changed()

    def _build_tts_group(self):
        # TTS settings group
        tts_group = QGroupBox(_("Speech synthesis (TTS) settings"))
        tts_vbox = QVBoxLayout(tts_group)

        tts_vbox.addWidget(QLabel(_("TTS engine:")))
        self.tts_mode_combo = QComboBox()
        for label, data in _tts_modes():
            self.tts_mode_combo.addItem(label, data)
        self._set_combo(self.tts_mode_combo, self._settings.get("tts_mode", "fish"))
        self.tts_mode_combo.currentIndexChanged.connect(self._on_tts_changed)
        tts_vbox.addWidget(self.tts_mode_combo)

        self.tts_diagnostic_panel = TTSDiagnosticPanel(self._tts_diagnostic_values, self)
        tts_vbox.addWidget(self.tts_diagnostic_panel)
        self.tts_emotion_checkbox = QCheckBox(_("TTS emotion control"))
        self.tts_emotion_checkbox.setChecked(
            bool(self._settings.get("tts_emotion_enabled", True))
        )
        tts_vbox.addWidget(self.tts_emotion_checkbox)

        self._build_general_group(tts_vbox)
        self._build_voice_cloning_group(tts_vbox)
        self._build_fish_group(tts_vbox)
        self._build_cosyvoice_group(tts_vbox)
        self._build_openai_compat_group(tts_vbox)
        self._build_openai_tts_group(tts_vbox)
        self._build_elevenlabs_group(tts_vbox)
        self._build_edge_group(tts_vbox)
        return tts_group

    def _build_general_group(self, tts_vbox):
        general_grp = QGroupBox(_("Common TTS settings"))
        general_layout = QVBoxLayout(general_grp)
        general_layout.addWidget(QLabel(_("Playback volume scale (0.0 ~ 2.0, 1.0 = original):")))
        self.tts_volume_input = QLineEdit(str(self._settings.get("tts_volume", 1.0)))
        general_layout.addWidget(self.tts_volume_input)
        tts_vbox.addWidget(general_grp)

    def _build_voice_cloning_group(self, tts_vbox):
        self._voice_cloning_group = QGroupBox(_("Voice cloning"))
        cloning_layout = QVBoxLayout(self._voice_cloning_group)
        cloning_layout.addWidget(QLabel(_("Reference WAV file (leave empty to use the default reference.wav):")))
        reference_row = QHBoxLayout()
        self.tts_reference_wav_input = QLineEdit(
            self._settings.get("tts_reference_wav", "")
        )
        reference_row.addWidget(self.tts_reference_wav_input)
        reference_button = QPushButton(_("Browse"))
        reference_button.clicked.connect(self._browse_reference_wav)
        reference_row.addWidget(reference_button)
        cloning_layout.addLayout(reference_row)
        cloning_layout.addWidget(QLabel(_("Reference WAV transcript:")))
        self.cosyvoice_ref_text = QTextEdit()
        self.cosyvoice_ref_text.setPlainText(
            self._settings.get("cosyvoice_reference_text", "")
        )
        self.cosyvoice_ref_text.setMaximumHeight(60)
        cloning_layout.addWidget(self.cosyvoice_ref_text)
        tts_vbox.addWidget(self._voice_cloning_group)

    def _build_fish_group(self, tts_vbox):
        # Fish Audio Settings
        fish_grp = QGroupBox(_("Fish Audio Settings"))
        fl = QVBoxLayout(fish_grp)
        fl.addWidget(QLabel(_("API Key:")))
        self.fish_key_input = QLineEdit(self._settings.get("fish_api_key", ""))
        self.fish_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addWidget(self.fish_key_input)
        fl.addWidget(QLabel(_("Reference ID:")))
        self.fish_ref_input = QLineEdit(self._settings.get("fish_reference_id", ""))
        fl.addWidget(self.fish_ref_input)
        fl.addWidget(QLabel(_("Model:")))
        self.fish_model_combo = QComboBox()
        self.fish_model_combo.setEditable(True)
        for m in ["s2.1-pro-free", "s1", "speech-1.6", "speech-1.5"]:
            self.fish_model_combo.addItem(m, m)
        self._set_combo(self.fish_model_combo,
                        self._settings.get("fish_model", "s2.1-pro-free"))
        fl.addWidget(self.fish_model_combo)
        tts_vbox.addWidget(fish_grp)
        self._tts_groups["fish"] = fish_grp

    def _build_cosyvoice_group(self, tts_vbox):
        # CosyVoice3 Settings
        cv_grp = QGroupBox(_("CosyVoice3 settings (local GPU)"))
        cvl = QVBoxLayout(cv_grp)
        cvl.addWidget(QLabel(_("CosyVoice install path (leave empty to auto-detect):")))
        dir_row = QHBoxLayout()
        self.cosyvoice_dir_input = QLineEdit(self._settings.get("cosyvoice_dir", ""))
        self.cosyvoice_dir_input.setPlaceholderText(_("e.g. C:/CosyVoice"))
        dir_row.addWidget(self.cosyvoice_dir_input)
        browse_btn = QPushButton(_("Browse"))
        browse_btn.setFixedWidth(72)
        browse_btn.setStyleSheet(secondary_btn_style())
        browse_btn.clicked.connect(self._browse_cosyvoice_dir)
        dir_row.addWidget(browse_btn)
        detect_btn = QPushButton(_("Auto-detect"))
        detect_btn.setFixedWidth(72)
        detect_btn.setStyleSheet(secondary_btn_style())
        detect_btn.clicked.connect(self._detect_cosyvoice_dir)
        dir_row.addWidget(detect_btn)
        cvl.addLayout(dir_row)
        self.cosyvoice_dir_status = create_muted_label("")
        cvl.addWidget(self.cosyvoice_dir_status)
        cvl.addWidget(QLabel(_("Speaking rate (0.7 ~ 1.2):")))
        self.cosyvoice_speed_input = QLineEdit(str(self._settings.get("cosyvoice_speed", 0.9)))
        cvl.addWidget(self.cosyvoice_speed_input)
        tts_vbox.addWidget(cv_grp)
        self._tts_groups["local"] = cv_grp

    def _build_openai_compat_group(self, tts_vbox):
        compat_grp = QGroupBox(_("OpenAI-compatible TTS settings"))
        compat_layout = QVBoxLayout(compat_grp)
        compat_layout.addWidget(QLabel(_("Server URL (e.g. http://127.0.0.1:8880/v1):")))
        self.openai_compat_base_url_input = QLineEdit(
            self._settings.get("openai_compat_tts_base_url", "")
        )
        compat_layout.addWidget(self.openai_compat_base_url_input)
        compat_layout.addWidget(QLabel(_("API key (optional):")))
        self.openai_compat_api_key_input = QLineEdit(
            self._settings.get("openai_compat_tts_api_key", "")
        )
        self.openai_compat_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_compat_api_key_input.setPlaceholderText(_("Leave empty to send not-needed."))
        compat_layout.addWidget(self.openai_compat_api_key_input)
        compat_layout.addWidget(QLabel(_("Model:")))
        self.openai_compat_model_input = QLineEdit(
            self._settings.get("openai_compat_tts_model", "")
        )
        compat_layout.addWidget(self.openai_compat_model_input)
        compat_layout.addWidget(QLabel(_("Voice:")))
        self.openai_compat_voice_input = QLineEdit(
            self._settings.get("openai_compat_tts_voice", "")
        )
        compat_layout.addWidget(self.openai_compat_voice_input)
        compat_options = QHBoxLayout()
        self.openai_compat_clone_combo = QComboBox()
        self.openai_compat_clone_combo.addItem(_("Default voice"), "none")
        self.openai_compat_clone_combo.addItem(_("Reference voice clone"), "ref_audio")
        self._set_combo(
            self.openai_compat_clone_combo,
            self._settings.get("openai_compat_tts_clone_mode", "none"),
        )
        compat_options.addWidget(QLabel(_("Cloning:")))
        compat_options.addWidget(self.openai_compat_clone_combo)
        self.openai_compat_emotion_combo = QComboBox()
        self.openai_compat_emotion_combo.addItem(_("Use an emotion instruction"), "instructions")
        self.openai_compat_emotion_combo.addItem(_("Not used"), "none")
        self._set_combo(
            self.openai_compat_emotion_combo,
            self._settings.get("openai_compat_tts_emotion_mode", "instructions"),
        )
        compat_options.addWidget(QLabel(_("Emotion:")))
        compat_options.addWidget(self.openai_compat_emotion_combo)
        compat_layout.addLayout(compat_options)
        tts_vbox.addWidget(compat_grp)
        self._tts_groups["openai_compat_tts"] = compat_grp

    def _build_openai_tts_group(self, tts_vbox):
        # OpenAI TTS Settings
        oai_grp = QGroupBox(_("OpenAI TTS Settings"))
        oail = QVBoxLayout(oai_grp)
        oail.addWidget(QLabel(_("API key (optional):")))
        self.openai_tts_key_input = QLineEdit(self._settings.get("openai_tts_api_key", ""))
        self.openai_tts_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_tts_key_input.setPlaceholderText(_("Leave empty to follow the AI settings."))
        oail.addWidget(self.openai_tts_key_input)
        row = QHBoxLayout()
        row.addWidget(QLabel(_("Voice:")))
        self.openai_tts_voice_combo = QComboBox()
        for v in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
            self.openai_tts_voice_combo.addItem(v, v)
        self._set_combo(self.openai_tts_voice_combo, self._settings.get("openai_tts_voice", "nova"))
        row.addWidget(self.openai_tts_voice_combo)
        row.addWidget(QLabel(_("Model:")))
        self.openai_tts_model_combo = QComboBox()
        for m in ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]:
            self.openai_tts_model_combo.addItem(m, m)
        self._set_combo(self.openai_tts_model_combo, self._settings.get("openai_tts_model", "tts-1"))
        row.addWidget(self.openai_tts_model_combo)
        oail.addLayout(row)
        oail.addWidget(QLabel(_("Available to approved organizations only: custom voice ID (voice_...):")))
        self.openai_tts_custom_voice_input = QLineEdit(
            self._settings.get("openai_tts_custom_voice_id", "")
        )
        oail.addWidget(self.openai_tts_custom_voice_input)
        tts_vbox.addWidget(oai_grp)
        self._tts_groups["openai_tts"] = oai_grp

    def _build_elevenlabs_group(self, tts_vbox):
        # ElevenLabs Settings
        el_grp = QGroupBox(_("ElevenLabs Settings"))
        ell = QVBoxLayout(el_grp)
        ell.addWidget(QLabel(_("API Key:")))
        self.elevenlabs_key_input = QLineEdit(self._settings.get("elevenlabs_api_key", ""))
        self.elevenlabs_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        ell.addWidget(self.elevenlabs_key_input)
        ell.addWidget(QLabel(_("Model:")))
        self.elevenlabs_model_combo = QComboBox()
        self.elevenlabs_model_combo.setEditable(True)
        for model_id in ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_v3"):
            self.elevenlabs_model_combo.addItem(model_id, model_id)
        self._select_or_add(
            self.elevenlabs_model_combo,
            self._settings.get("elevenlabs_model_id", "eleven_multilingual_v2"),
        )
        ell.addWidget(self.elevenlabs_model_combo)
        eleven_button_row = QHBoxLayout()
        self.elevenlabs_models_button = QPushButton(_("Load models"))
        self.elevenlabs_models_button.clicked.connect(self._load_elevenlabs_models)
        eleven_button_row.addWidget(self.elevenlabs_models_button)
        self.elevenlabs_voices_button = QPushButton(_("Load voices"))
        self.elevenlabs_voices_button.clicked.connect(self._load_elevenlabs_voices)
        eleven_button_row.addWidget(self.elevenlabs_voices_button)
        ell.addLayout(eleven_button_row)
        ell.addWidget(QLabel(_("Voice name:")))
        self.elevenlabs_voice_combo = QComboBox()
        self.elevenlabs_voice_combo.setEditable(True)
        self._select_or_add(self.elevenlabs_voice_combo, self._settings.get("elevenlabs_voice_id", ""))
        ell.addWidget(self.elevenlabs_voice_combo)
        self.elevenlabs_clone_button = QPushButton(_("Create my voice from a reference voice"))
        self.elevenlabs_clone_button.clicked.connect(self._create_elevenlabs_clone)
        ell.addWidget(self.elevenlabs_clone_button)
        tts_vbox.addWidget(el_grp)
        self._tts_groups["elevenlabs"] = el_grp

    def _build_edge_group(self, tts_vbox):
        # Edge TTS Settings
        edge_grp = QGroupBox(_("Edge TTS settings (free)"))
        edgel = QVBoxLayout(edge_grp)
        edgel.addWidget(QLabel(_("Voice selection:")))
        self.edge_voice_combo = QComboBox()
        for vid, vlbl in [
            ("ko-KR-SunHiNeural", _("SunHi (female)")),
            ("ko-KR-InJoonNeural", _("InJoon (Male)")),
            ("ko-KR-HyunsuNeural", _("Hyunsu (Male)")),
        ]:
            self.edge_voice_combo.addItem(vlbl, vid)
        self._set_combo(self.edge_voice_combo, self._settings.get("edge_tts_voice", "ko-KR-SunHiNeural"))
        edgel.addWidget(self.edge_voice_combo)
        edgel.addWidget(QLabel(_("Rate (e.g. +0%, -10%):")))
        self.edge_rate_input = QLineEdit(self._settings.get("edge_tts_rate", "+0%"))
        edgel.addWidget(self.edge_rate_input)
        tts_vbox.addWidget(edge_grp)
        self._tts_groups["edge"] = edge_grp

    def _browse_reference_wav(self):
        selection = QFileDialog.getOpenFileName(
            self,
            _("Select reference WAV"),
            self.tts_reference_wav_input.text() or "",
            _("WAV files (*.wav)"),
        )
        if selection[0]:
            self.tts_reference_wav_input.setText(selection[0])

    def _start_elevenlabs_action(self, button: QPushButton, action, callback):
        if self._tts_action_job is not None:
            return
        button.setEnabled(False)
        job = SimpleNamespace(button=button, callback=callback)
        self._tts_action_job = job
        relay = _action_relay()

        def run():
            try:
                result, error = action(), ""
            except Exception as exc:
                result, error = None, str(exc)
            try:
                relay.completed.emit(job, result, error)
            except RuntimeError:
                pass  # Discard the result while the app is shutting down.

        # Because it is a daemon thread, quitting the app mid-request neither blocks shutdown nor crashes on Qt thread destruction.
        threading.Thread(target=run, name="ElevenLabsAction", daemon=True).start()

    @Slot(object, object, str)
    def _finish_elevenlabs_action(self, job, result, error: str):
        # Ignored when the task belongs to another settings window, or the window was closed and the task cleaned up.
        if job is not self._tts_action_job:
            return
        self._tts_action_job = None
        job.button.setEnabled(True)
        job.callback(result, error)

    def _load_elevenlabs_models(self):
        api_key = self.elevenlabs_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, _("ElevenLabs"), _("Please enter the API key."))
            return

        def finish(models, error):
            if error:
                QMessageBox.warning(self, _("Failed to load models"), error)
                return
            selected = self._combo_id(self.elevenlabs_model_combo)
            self.elevenlabs_model_combo.clear()
            for model in models:
                self.elevenlabs_model_combo.addItem(model["name"], model["model_id"])
            self._select_or_add(self.elevenlabs_model_combo, selected)

        def fetch():
            from tts.tts_elevenlabs import fetch_models

            return fetch_models(api_key)

        self._start_elevenlabs_action(self.elevenlabs_models_button, fetch, finish)

    def _load_elevenlabs_voices(self):
        api_key = self.elevenlabs_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, _("ElevenLabs"), _("Please enter the API key."))
            return

        def finish(voices, error):
            if error:
                QMessageBox.warning(self, _("Failed to load voices"), error)
                return
            selected = self._combo_id(self.elevenlabs_voice_combo)
            self.elevenlabs_voice_combo.clear()
            for voice in voices:
                self.elevenlabs_voice_combo.addItem(voice["name"], voice["voice_id"])
            self._select_or_add(self.elevenlabs_voice_combo, selected)

        def fetch():
            from tts.tts_elevenlabs import fetch_voices

            return fetch_voices(api_key)

        self._start_elevenlabs_action(self.elevenlabs_voices_button, fetch, finish)

    def _create_elevenlabs_clone(self):
        api_key = self.elevenlabs_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, _("ElevenLabs"), _("Please enter the API key."))
            return
        from tts.voice_reference import get_reference_wav

        reference_wav = get_reference_wav(self.get_values())
        if not os.path.isfile(reference_wav):
            QMessageBox.warning(self, _("Clone voice"), _("The reference WAV file could not be found."))
            return
        voice_name = os.path.splitext(os.path.basename(reference_wav))[0] or "Ari Voice"

        def finish(result, error):
            if error:
                QMessageBox.warning(self, _("Voice cloning failed"), error)
                return
            voice_id, requires_verification = result
            self.elevenlabs_voice_combo.addItem(voice_name, voice_id)
            self.elevenlabs_voice_combo.setCurrentIndex(self.elevenlabs_voice_combo.count() - 1)
            if requires_verification:
                QMessageBox.information(
                    self,
                    _("Clone voice"),
                    _("You must complete additional verification in ElevenLabs to use this voice."),
                )

        def clone():
            from tts.tts_elevenlabs import create_voice_clone

            return create_voice_clone(api_key, reference_wav, voice_name)

        self._start_elevenlabs_action(self.elevenlabs_clone_button, clone, finish)

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_tts_changed(self):
        selected = self.tts_mode_combo.currentData()
        for key in [data for _label, data in _tts_modes()]:
            grp = self._tts_groups.get(key)
            if grp:
                grp.setVisible(key == selected)
        self._voice_cloning_group.setVisible(
            selected in {"local", "openai_compat_tts", "elevenlabs"}
        )

    def _tts_diagnostic_values(self):
        selected_mode = self.tts_mode_combo.currentData()
        settings = dict(self._settings)
        dialog = self.window()
        llm_page = getattr(dialog, "_llm_page", None)
        if llm_page is not None:
            settings.update(llm_page.get_values())
        settings.update(self.get_values())
        speaker_combo = getattr(dialog, "speaker_combo", None)
        output_device_name = speaker_combo.currentData() if speaker_combo is not None else ""
        return settings, selected_mode, str(output_device_name or "")

    def _open_ollama_installer(self):
        from PySide6.QtWidgets import QDialog
        if _installer_running(OllamaInstallerThread):
            QMessageBox.information(self, _("Install Ollama"), _("A previously started installation is still running. Please try again once it finishes."))
            return
        installed = bool(self.local_install_section.ollama_path)
        dialog = OllamaInstallDialog(self, installed=installed)
        if dialog.exec() != QDialog.Accepted:
            return

        selected_models = dialog.selected_models()
        if not selected_models and installed:
            QMessageBox.information(self, _("Download Ollama models"), _("No models are selected."))
            return
        if not selected_models:
            confirm = QMessageBox.question(
                self,
                _("Install without models"),
                _("No models are selected. Install only the Ollama program?"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

        self._ollama_install_thread = OllamaInstallerThread(
            dialog.install_dir_input.text(),
            dialog.models_dir_input.text(),
            selected_models,
        )
        _track_installer_thread(self._ollama_install_thread)
        self._ollama_install_thread.done.connect(self._on_ollama_install_done)
        self._ollama_progress_dialog = QProgressDialog(
            _("Downloading Ollama models.\nThe model download continues in the background without a console.") if installed else
            _("Preparing the Ollama installation.\nProceed in the installer window that appears; the model download continues in the background without a console."),
            None, 0, 0, self,
        )
        self._ollama_progress_dialog.setWindowTitle(_("Download Ollama models") if installed else _("Install Ollama"))
        self._ollama_progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._ollama_progress_dialog.setCancelButton(None)
        self._ollama_progress_dialog.setMinimumDuration(0)
        self._ollama_progress_dialog.show()
        self._ollama_install_thread.start()

    def _on_ollama_install_done(self, success: bool, message: str, result: dict):
        if self._closed:
            return
        if self._ollama_progress_dialog is not None:
            self._ollama_progress_dialog.close()
            self._ollama_progress_dialog = None

        if success and result:
            QMessageBox.information(self, _("Install Ollama"), message)
        else:
            QMessageBox.warning(self, _("Install Ollama"), message)

        self._ollama_install_thread = None
        self.local_install_section.start_detection()

    def _locate_ollama(self):
        """When the user picks ollama.exe manually it is saved to the settings and the status is checked again."""
        path, _filter = QFileDialog.getOpenFileName(
            self, _("Select the location of ollama.exe"),
            os.path.dirname(self._ollama_executable_path) or "C:/",
            "ollama.exe (ollama.exe)",
        )
        if not path:
            return
        if os.path.basename(path).lower() not in {"ollama.exe", "ollama"}:
            QMessageBox.warning(self, _("Choose location"), _("Please select the ollama.exe file."))
            return
        self._ollama_executable_path = os.path.abspath(path)
        # Record the path immediately so the installation uses it even before saving. It is also saved through get_values when the settings window is saved.
        from core.config_manager import ConfigManager
        from core.ollama_installer import OLLAMA_EXECUTABLE_SETTING
        if not ConfigManager.set_value(OLLAMA_EXECUTABLE_SETTING, self._ollama_executable_path):
            logging.warning("ollama.exe Could not save path directly. SettingsWill save again at window save.")
        self.local_install_section.start_detection()

    def _on_local_install_detected(self, result: dict):
        path = result.get("cosyvoice_dir") or ""
        if path:
            self.cosyvoice_dir_input.setText(path)
            self._check_cosyvoice_dir(path)
        else:
            self.cosyvoice_dir_status.setText(
                _("No CosyVoice installation was detected. Install it or specify the folder.")
            )
            self.cosyvoice_dir_status.setStyleSheet("color: #e67e22;")

    def _install_cosyvoice(self):
        if _installer_running(CosyVoiceInstallerThread):
            QMessageBox.information(self, _("Install CosyVoice"), _("A previously started installation is still running. Please try again once it finishes."))
            return
        target_dir = self.cosyvoice_dir_input.text().strip()
        if not target_dir:
            target_dir = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "CosyVoice")
            self.cosyvoice_dir_input.setText(target_dir)

        installed_dir = self.local_install_section.cosyvoice_dir
        if installed_dir:
            # If it is already installed, ask before reinstalling, with 'No' as the default choice.
            confirm = QMessageBox.question(
                self,
                _("Install CosyVoice"),
                _("CosyVoice3 is already installed.\n\n{path}\n\nReinstall it?", path=installed_dir),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
        else:
            confirm = QMessageBox.question(
                self,
                _("Install CosyVoice"),
                _("Install CosyVoice3 to the path below?\n\n{path}").format(path=target_dir),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
        if confirm != QMessageBox.Yes:
            return

        self._cosyvoice_install_thread = CosyVoiceInstallerThread(target_dir)
        _track_installer_thread(self._cosyvoice_install_thread)
        self._cosyvoice_install_thread.done.connect(self._on_cosyvoice_install_done)
        self._cosyvoice_progress_dialog = QProgressDialog(
            _("CosyVoice3 installation is in progress.\nDownloading dependencies and models may take a little while."),
            None, 0, 0, self,
        )
        self._cosyvoice_progress_dialog.setWindowTitle(_("Install CosyVoice3"))
        self._cosyvoice_progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._cosyvoice_progress_dialog.setCancelButton(None)
        self._cosyvoice_progress_dialog.setMinimumDuration(0)
        self._cosyvoice_progress_dialog.show()
        self._cosyvoice_install_thread.start()

    def _on_cosyvoice_install_done(self, success: bool, message: str, installed_path: str):
        if self._closed:
            return
        if self._cosyvoice_progress_dialog is not None:
            self._cosyvoice_progress_dialog.close()
            self._cosyvoice_progress_dialog = None

        if success:
            self.cosyvoice_dir_input.setText(installed_path)
            self._check_cosyvoice_dir(installed_path)
            if self.tts_mode_combo.currentData() != "local":
                self._set_combo(self.tts_mode_combo, "local")
                self._on_tts_changed()
            QMessageBox.information(self, _("Install CosyVoice3"), message)
        else:
            self.cosyvoice_dir_status.setText(message)
            self.cosyvoice_dir_status.setStyleSheet("color: #e74c3c;")
            QMessageBox.warning(self, _("Install CosyVoice3"), message)

        self._cosyvoice_install_thread = None

    def _browse_cosyvoice_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, _("Select the CosyVoice installation folder"),
            self.cosyvoice_dir_input.text() or "C:/",
        )
        if path:
            self.cosyvoice_dir_input.setText(path)
            self._check_cosyvoice_dir(path)

    def _detect_cosyvoice_dir(self):
        try:
            from tts.cosyvoice_tts import _get_cosyvoice_dir
            path = _get_cosyvoice_dir()
        except Exception:
            path = ""
        if path:
            self.cosyvoice_dir_input.setText(path)
            self.cosyvoice_dir_status.setText(_("✓ Detected: {path}").format(path=path))
            self.cosyvoice_dir_status.setStyleSheet("color: #27ae60;")
        else:
            self.cosyvoice_dir_status.setText(_("✗ Auto-detection failed — please enter the path manually."))
            self.cosyvoice_dir_status.setStyleSheet("color: #e74c3c;")

    def _check_cosyvoice_dir(self, path: str):
        from core.cosyvoice_installer import is_valid_cosyvoice_dir
        if is_valid_cosyvoice_dir(path):
            self.cosyvoice_dir_status.setText(_("✓ Valid CosyVoice path"))
            self.cosyvoice_dir_status.setStyleSheet("color: #27ae60;")
        else:
            self.cosyvoice_dir_status.setText(_("⚠ The pretrained_models folder is missing. Please check the path."))
            self.cosyvoice_dir_status.setStyleSheet("color: #e67e22;")

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _set_combo(combo: QComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    @staticmethod
    def _select_or_add(combo: QComboBox, value: str):
        """Adds saved IDs that are missing from the list as items so the selection is preserved."""
        if not value:
            return
        index = combo.findData(value)
        if index < 0:
            combo.addItem(value, value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    @staticmethod
    def _combo_id(combo: QComboBox) -> str:
        """Prefers an ID typed directly into the editable combo over the item data."""
        text = combo.currentText().strip()
        data = combo.currentData()
        if data and text == combo.itemText(combo.currentIndex()):
            return data
        return text

    @staticmethod
    def _float(text: str, default: float) -> float:
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    # ── Public interface ────────────────────────────────────────────────────────

    def get_values(self) -> dict:
        """Return the current TTS settings as a dict."""
        return {
            "tts_mode": self.tts_mode_combo.currentData(),
            "tts_emotion_enabled": self.tts_emotion_checkbox.isChecked(),
            "fish_api_key": self.fish_key_input.text().strip(),
            "fish_reference_id": self.fish_ref_input.text().strip(),
            # Because the combo is editable, a model name typed by the user is accepted as is.
            "fish_model": (self.fish_model_combo.currentText().strip()
                           or "s2.1-pro-free"),
            "cosyvoice_dir": self.cosyvoice_dir_input.text().strip(),
            "cosyvoice_reference_text": self.cosyvoice_ref_text.toPlainText().strip(),
            "tts_reference_wav": self.tts_reference_wav_input.text().strip(),
            "cosyvoice_speed": self._float(self.cosyvoice_speed_input.text(), 0.9),
            "tts_volume": self._float(self.tts_volume_input.text(), 1.0),
            "openai_compat_tts_base_url": self.openai_compat_base_url_input.text().strip(),
            "openai_compat_tts_api_key": self.openai_compat_api_key_input.text().strip(),
            "openai_compat_tts_model": self.openai_compat_model_input.text().strip(),
            "openai_compat_tts_voice": self.openai_compat_voice_input.text().strip(),
            "openai_compat_tts_clone_mode": self.openai_compat_clone_combo.currentData(),
            "openai_compat_tts_emotion_mode": self.openai_compat_emotion_combo.currentData(),
            "openai_tts_api_key": self.openai_tts_key_input.text().strip(),
            "openai_tts_voice": self.openai_tts_voice_combo.currentData(),
            "openai_tts_model": self.openai_tts_model_combo.currentData(),
            "openai_tts_custom_voice_id": self.openai_tts_custom_voice_input.text().strip(),
            "elevenlabs_api_key": self.elevenlabs_key_input.text().strip(),
            "elevenlabs_voice_id": self._combo_id(self.elevenlabs_voice_combo),
            "elevenlabs_model_id": (self._combo_id(self.elevenlabs_model_combo)
                                    or "eleven_multilingual_v2"),
            "edge_tts_voice": self.edge_voice_combo.currentData(),
            "edge_tts_rate": self.edge_rate_input.text().strip() or "+0%",
            "ollama_executable_path": self._ollama_executable_path,
        }

    def cleanup_threads(self):
        """Clean up the running thread when the dialog closes."""
        self._closed = True
        self.local_install_section.stop_detection()
        self.tts_diagnostic_panel.cancel()
        # ElevenLabs requests cannot be cancelled midway, so instead of waiting we only stop handling the result.
        self._tts_action_job = None
