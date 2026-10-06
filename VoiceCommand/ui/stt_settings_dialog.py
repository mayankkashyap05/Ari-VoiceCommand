"""
Speech recognition (STT) settings dialog — STT engine, Whisper options, microphone sensitivity, wake words
"""
import logging
import threading
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox,
    QListWidget, QListWidgetItem, QCheckBox,
    QInputDialog, QSlider, QMessageBox, QDialogButtonBox, QKeySequenceEdit,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont, QKeySequence
from core.config_manager import ConfigManager
from i18n.translator import _
from ui.theme import FONT_KO, FONT_SIZE_NORMAL, INPUT_STYLE
from ui.stt_diagnostics import STTSampleDiagnosticPanel
from ui.global_hotkey import parse_global_hotkey


class _DownloadSignals(QObject):
    finished = Signal(bool, str)  # (success, message)


class STTSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("speech recognition Settings"))
        self.setMinimumWidth(500)
        self.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
        self.setStyleSheet(INPUT_STYLE)
        self.settings = ConfigManager.load_settings()
        parent_mic_combo = getattr(parent, "mic_combo", None)
        self.microphone_name = (
            str(parent_mic_combo.currentData() or "")
            if parent_mic_combo is not None
            else str(self.settings.get("microphone", "") or "")
        )
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── Voice input ──────────────────────────────────────────────────────────
        input_group = QGroupBox(_("Hotkey and click to listen"))
        ivbox = QVBoxLayout(input_group)
        ivbox.addWidget(QLabel(_("Global hotkey:")))
        self.voice_hotkey_edit = QKeySequenceEdit()
        self.voice_hotkey_edit.setKeySequence(QKeySequence(
            str(self.settings.get("voice_activation_hotkey", "Ctrl+Alt+Space"))
        ))
        ivbox.addWidget(self.voice_hotkey_edit)
        ivbox.addWidget(QLabel(_("Listening mode:")))
        self.voice_activation_mode_combo = QComboBox()
        self.voice_activation_mode_combo.addItem(
            _("Listen while held (push-to-talk)"), "push_to_talk"
        )
        self.voice_activation_mode_combo.addItem(
            _("Press once to start (toggle)"), "toggle"
        )
        self._set_combo(
            self.voice_activation_mode_combo,
            self.settings.get("voice_activation_mode", "push_to_talk"),
        )
        ivbox.addWidget(self.voice_activation_mode_combo)
        self.wake_word_enabled_checkbox = QCheckBox(_("Use wake words"))
        self.wake_word_enabled_checkbox.setChecked(
            bool(self.settings.get("wake_word_enabled", True))
        )
        ivbox.addWidget(self.wake_word_enabled_checkbox)
        input_hint = QLabel(
            _("A short click on the character detects the end of speech; holding it down listens while pressed.")
        )
        input_hint.setWordWrap(True)
        ivbox.addWidget(input_hint)
        hotkey_hint = QLabel(
            _("If another app is using the hotkey it will not be registered. The app keeps running.")
        )
        hotkey_hint.setWordWrap(True)
        ivbox.addWidget(hotkey_hint)
        layout.addWidget(input_group)

        # ── STT engine ──────────────────────────────────────────────────────────
        engine_group = QGroupBox(_("STT engine"))
        eg_vbox = QVBoxLayout(engine_group)
        eg_vbox.addWidget(QLabel(_("Speech recognition engine:")))
        self.stt_provider_combo = QComboBox()
        self.stt_provider_combo.addItem(_("Google STT (online)"), "google")
        self.stt_provider_combo.addItem(_("Whisper (offline)"), "whisper")
        self._set_combo(self.stt_provider_combo, self.settings.get("stt_provider", "google"))
        self.stt_provider_combo.currentIndexChanged.connect(self._on_stt_changed)
        eg_vbox.addWidget(self.stt_provider_combo)

        # ── Whisper Settings ───────────────────────────────────────────────────────
        self.whisper_group = QGroupBox(_("Whisper Settings"))
        wg_vbox = QVBoxLayout(self.whisper_group)
        wg_vbox.addWidget(QLabel(_("Model size:")))
        self.whisper_model_combo = QComboBox()
        for model_name in ("tiny", "small", "medium"):
            self.whisper_model_combo.addItem(model_name, model_name)
        self._set_combo(self.whisper_model_combo, self.settings.get("whisper_model", "small"))
        wg_vbox.addWidget(self.whisper_model_combo)
        self.whisper_download_btn = QPushButton(_("Download model"))
        self.whisper_download_btn.clicked.connect(self._download_whisper_model)
        wg_vbox.addWidget(self.whisper_download_btn)
        eg_vbox.addWidget(self.whisper_group)

        layout.addWidget(engine_group)

        self.stt_diagnostic_panel = STTSampleDiagnosticPanel(
            self._stt_diagnostic_settings, self.microphone_name, self
        )
        layout.addWidget(self.stt_diagnostic_panel)

        # ── Microphone sensitivity ────────────────────────────────────────────────────────
        mic_group = QGroupBox(_("Microphone sensitivity"))
        mg_vbox = QVBoxLayout(mic_group)
        self.stt_energy_slider = QSlider(Qt.Horizontal)
        energy_threshold = int(self.settings.get("stt_energy_threshold", 300))
        self.stt_energy_slider.setRange(1, max(4000, energy_threshold))
        self.stt_energy_slider.setValue(energy_threshold)
        self.stt_energy_slider.valueChanged.connect(self._on_energy_changed)
        mg_vbox.addWidget(self.stt_energy_slider)
        self.stt_energy_label = QLabel("")
        mg_vbox.addWidget(self.stt_energy_label)
        self.stt_dynamic_checkbox = QCheckBox(_("Use automatic sensitivity adjustment"))
        self.stt_dynamic_checkbox.setChecked(bool(self.settings.get("stt_dynamic_energy", False)))
        mg_vbox.addWidget(self.stt_dynamic_checkbox)
        layout.addWidget(mic_group)

        # ── Wake word ─────────────────────────────────────────────────────────
        wake_group = QGroupBox(_("Wake word list"))
        wk_vbox = QVBoxLayout(wake_group)
        self.wake_words_list = QListWidget()
        for word in self.settings.get("wake_words", ["Hey Ari", "Start"]):
            self.wake_words_list.addItem(QListWidgetItem(str(word)))
        wk_vbox.addWidget(self.wake_words_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton(_("Add"))
        add_btn.clicked.connect(self._add_wake_word)
        remove_btn = QPushButton(_("Delete"))
        remove_btn.clicked.connect(self._remove_wake_word)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        wk_vbox.addLayout(btn_row)
        layout.addWidget(wake_group)

        # ── OK / Cancel ────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(_("Save"))
        buttons.button(QDialogButtonBox.Cancel).setText(_("Cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_energy_changed(self.stt_energy_slider.value())
        self._on_stt_changed()

    # ── Helpers ──────────────────────────────────────────────────────────────────

    def _set_combo(self, combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _on_stt_changed(self):
        is_whisper = self.stt_provider_combo.currentData() == "whisper"
        self.whisper_group.setVisible(is_whisper)
        self.adjustSize()

    def _stt_diagnostic_settings(self) -> dict:
        settings = dict(self.settings)
        settings.update({
            "stt_provider": self.stt_provider_combo.currentData(),
            "whisper_model": self.whisper_model_combo.currentData(),
            "stt_energy_threshold": int(self.stt_energy_slider.value()),
            "stt_dynamic_energy": self.stt_dynamic_checkbox.isChecked(),
            "microphone": self.microphone_name,
        })
        return settings

    def _on_energy_changed(self, value: int):
        self.stt_energy_label.setText(_("Current sensitivity: {value}").format(value=value))

    def _download_whisper_model(self):
        model_name = self.whisper_model_combo.currentData() or "small"
        device = self.settings.get("whisper_device", "auto")
        compute_type = self.settings.get("whisper_compute_type", "int8")

        self.whisper_download_btn.setEnabled(False)
        self.whisper_download_btn.setText(_("Downloading..."))

        signals = _DownloadSignals()
        signals.finished.connect(self._on_download_finished)

        def _run():
            try:
                from core.stt_provider import WhisperSTTProvider
                provider = WhisperSTTProvider(
                    model_size=model_name, device=device, compute_type=compute_type
                )
                # Worker started successfully, checked and shut down immediately
                del provider
                signals.finished.emit(True, _("The '{model}' model is ready.").format(model=model_name))
            except Exception as exc:
                signals.finished.emit(False, _("Failed to prepare the model.\n{error}").format(error=exc))

        # Keep a reference (prevents GC)
        self._download_signals = signals
        threading.Thread(target=_run, daemon=True, name="Whisper-Download").start()

    def _on_download_finished(self, success: bool, message: str):
        self.whisper_download_btn.setEnabled(True)
        self.whisper_download_btn.setText(_("Download model"))
        self._download_signals = None
        if success:
            QMessageBox.information(self, _("Download Whisper"), message)
        else:
            QMessageBox.warning(self, _("Download Whisper"), message)

    def _add_wake_word(self):
        text, ok = QInputDialog.getText(self, _("Add wake word"), _("Please enter a new wake word:"))
        value = text.strip()
        if ok and value:
            self.wake_words_list.addItem(QListWidgetItem(value))

    def _remove_wake_word(self):
        row = self.wake_words_list.currentRow()
        if row < 0:
            return
        if self.wake_words_list.count() <= 1:
            QMessageBox.warning(self, _("Wake word"), _("At least one wake word is required."))
            return
        self.wake_words_list.takeItem(row)

    def _save(self):
        hotkey = self.voice_hotkey_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        try:
            parse_global_hotkey(hotkey)
        except ValueError:
            QMessageBox.warning(
                self,
                _("Hotkey settings"),
                _("Specify a modifier together with a default key, such as Ctrl+Alt+Space."),
            )
            return

        wake_words = [
            self.wake_words_list.item(i).text().strip()
            for i in range(self.wake_words_list.count())
            if self.wake_words_list.item(i).text().strip()
        ]
        if not wake_words:
            QMessageBox.warning(self, _("Wake word"), _("At least one wake word is required."))
            return

        current = ConfigManager.load_settings()
        current.update({
            "stt_provider": self.stt_provider_combo.currentData(),
            "whisper_model": self.whisper_model_combo.currentData(),
            "wake_words": wake_words,
            "wake_word_enabled": self.wake_word_enabled_checkbox.isChecked(),
            "voice_activation_hotkey": hotkey,
            "voice_activation_mode": self.voice_activation_mode_combo.currentData(),
            "stt_energy_threshold": int(self.stt_energy_slider.value()),
            "stt_dynamic_energy": self.stt_dynamic_checkbox.isChecked(),
        })
        if not ConfigManager.save_settings(current):
            QMessageBox.warning(self, _("settings.save_failed"), _("settings.secret_save_failed"))
            return
        logging.info("[STTSettingsDialog] STT Settings Save complete")
        self.accept()
