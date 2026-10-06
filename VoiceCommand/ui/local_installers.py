"""Local installation UI component for the settings window."""
from __future__ import annotations

import logging
from typing import Callable, Iterable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
)

from i18n.translator import _
from ui.common import create_muted_label


def installer_btn_style() -> str:
    return """
        QPushButton {
            background-color: #1f6feb;
            color: white;
            font-weight: bold;
            font-size: 13px;
            border: none;
            border-radius: 10px;
            padding: 10px 16px;
        }
        QPushButton:hover {
            background-color: #2b7fff;
        }
        QPushButton:pressed {
            background-color: #195ec8;
        }
    """


class OllamaInstallerThread(QThread):
    done = Signal(bool, str, dict)

    def __init__(self, install_dir: str, models_dir: str, models: Iterable[str]):
        super().__init__()
        self.install_dir = install_dir.strip()
        self.models_dir = models_dir.strip()
        self.models = list(models)

    def run(self):
        try:
            from core.ollama_installer import install_ollama

            result = install_ollama(
                install_dir=self.install_dir or None,
                models_dir=self.models_dir or None,
                models=self.models,
            )
            model_text = ", ".join(result.get("installed_models", [])) or _("No models installed")
            self.done.emit(True, _("✓ Ollama installed ({models})").format(models=model_text), result)
        except Exception as exc:
            self.done.emit(False, _("✗ Ollama installation failed: {error}").format(error=exc), {})


class CosyVoiceInstallerThread(QThread):
    done = Signal(bool, str, str)

    def __init__(self, install_dir: str):
        super().__init__()
        self.install_dir = install_dir.strip()

    def run(self):
        try:
            from core.cosyvoice_installer import install_cosyvoice

            installed_path = install_cosyvoice(self.install_dir)
            self.done.emit(True, _("✓ CosyVoice3 installed"), installed_path)
        except Exception as exc:
            self.done.emit(False, _("✗ CosyVoice3 installation failed: {error}").format(error=exc), "")


class OllamaInstallDialog(QDialog):
    def __init__(self, parent=None, installed: bool = False):
        super().__init__(parent)
        self._installed = installed
        self.setWindowTitle(_("Download Ollama models") if installed else _("Install Ollama"))
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self):
        from core.ollama_installer import COMMON_OLLAMA_MODELS

        layout = QVBoxLayout(self)
        if self._installed:
            layout.addWidget(create_muted_label(
                _("Ollama is already installed. Choose the models to download.")
            ))
        else:
            layout.addWidget(create_muted_label(
                _("Installs Ollama and downloads the models to use. ") +
                _("You can select several models; they are applied to the settings right after installation.")
            ))

        layout.addWidget(QLabel(_("Recommended models:")))
        self.model_list = QListWidget()
        for option in COMMON_OLLAMA_MODELS:
            item = QListWidgetItem(f"{option.label}  [{option.model}]  -  {option.summary}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if option.model == "llama3.2:3b" else Qt.CheckState.Unchecked)
            item.setData(Qt.UserRole, option.model)
            self.model_list.addItem(item)
        self.model_list.setMinimumHeight(160)
        layout.addWidget(self.model_list)

        layout.addWidget(QLabel(_("Additional model names (comma-separated):")))
        self.custom_models_input = QLineEdit()
        self.custom_models_input.setPlaceholderText(_("e.g. qwen2.5-coder:7b, mistral-small"))
        layout.addWidget(self.custom_models_input)

        if self._installed:
            # If it is already installed the install step is skipped, so the install path is not requested.
            self.install_dir_input = QLineEdit()
        else:
            layout.addWidget(QLabel(_("Ollama install path (optional):")))
            self.install_dir_input = self._build_path_input(
                layout,
                placeholder=_("Leave empty to use the default Ollama path"),
                title=_("Select the Ollama installation folder"),
            )

        layout.addWidget(QLabel(_("Model storage path (optional):")))
        self.models_dir_input = self._build_path_input(
            layout,
            placeholder=_("Leave empty to use the default model path"),
            title=_("Select the Ollama model folder"),
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_path_input(self, layout: QVBoxLayout, placeholder: str, title: str) -> QLineEdit:

        row = QHBoxLayout()
        path_input = QLineEdit()
        path_input.setPlaceholderText(placeholder)
        row.addWidget(path_input)
        browse_btn = QPushButton(_("Browse"))
        browse_btn.setFixedWidth(72)
        browse_btn.clicked.connect(lambda: self._browse_dir(path_input, title))
        row.addWidget(browse_btn)
        layout.addLayout(row)
        return path_input

    def _browse_dir(self, target_input: QLineEdit, title: str):
        path = QFileDialog.getExistingDirectory(self, title, target_input.text() or "C:/")
        if path:
            target_input.setText(path)

    def selected_models(self) -> list[str]:
        from core.ollama_installer import normalize_models

        selected = []
        for index in range(self.model_list.count()):
            item = self.model_list.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        custom = self.custom_models_input.text().strip()
        if custom:
            selected.extend(part.strip() for part in custom.split(","))
        return normalize_models(selected)


class LocalInstallDetectThread(QThread):
    """Look for an existing Ollama and CosyVoice3 installation outside the UI thread."""

    done = Signal(object)

    def __init__(self, configured_cosyvoice_dir: str):
        super().__init__()
        self.configured_cosyvoice_dir = configured_cosyvoice_dir.strip()

    def run(self):
        result = {"ollama_path": "", "ollama_models": None, "cosyvoice_dir": ""}
        try:
            from core.ollama_installer import find_ollama_executable, list_installed_models

            result["ollama_path"] = find_ollama_executable() or ""
            if result["ollama_path"]:
                result["ollama_models"] = list_installed_models()
        except Exception as exc:
            logging.debug("Ollama installation check failed: %s", exc)
        try:
            from core.cosyvoice_installer import find_cosyvoice_dir

            result["cosyvoice_dir"] = find_cosyvoice_dir(self.configured_cosyvoice_dir)
        except Exception as exc:
            logging.debug("CosyVoice installation check failed: %s", exc)
        self.done.emit(result)


class LocalInstallSection(QGroupBox):
    ollama_install_requested = Signal()
    cosyvoice_install_requested = Signal()
    ollama_locate_requested = Signal()
    detection_finished = Signal(object)

    def __init__(self, parent=None, cosyvoice_dir_provider: Callable[[], str] | None = None):
        super().__init__(_("Local installation"), parent)
        self._cosyvoice_dir_provider = cosyvoice_dir_provider or (lambda: "")
        self._detect_thread: LocalInstallDetectThread | None = None
        self.ollama_path = ""
        self.cosyvoice_dir = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(create_muted_label(
            _("Install the engine you want to run locally first, then adjust the paths and models in the settings below.")
        ))
        self.redetect_btn = QPushButton(_("Search again"))
        self.redetect_btn.clicked.connect(self.start_detection)
        layout.addWidget(self.redetect_btn)

        layout.addWidget(self._build_card(
            title="Ollama",
            description=_("Installs the local LLM engine and downloads models in one step."),
            button_text=_("Install Ollama / download models"),
            click_handler=self.ollama_install_requested.emit,
        ))
        layout.addWidget(self._build_card(
            title="CosyVoice3",
            description=_("Installs the local TTS engine and the default model and configures the settings paths automatically."),
            button_text=_("Install CosyVoice"),
            click_handler=self.cosyvoice_install_requested.emit,
        ))

    def _build_card(self, title: str, description: str, button_text: str, click_handler) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.addWidget(create_muted_label(description))
        status = create_muted_label("")
        layout.addWidget(status)
        button = QPushButton(button_text)
        button.setMinimumHeight(42)
        button.setStyleSheet(installer_btn_style())
        button.clicked.connect(click_handler)
        layout.addWidget(button)
        if title == "Ollama":
            self.ollama_install_btn = button
            self.ollama_status = status
            self.ollama_models_label = create_muted_label("")
            layout.insertWidget(layout.indexOf(status) + 1, self.ollama_models_label)
            self.ollama_locate_btn = QPushButton(_("Choose location"))
            self.ollama_locate_btn.clicked.connect(self.ollama_locate_requested.emit)
            layout.addWidget(self.ollama_locate_btn)
        else:
            self.cosyvoice_install_btn = button
            self.cosyvoice_status = status
        return group

    # ── Installation status check ─────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self.start_detection()

    def start_detection(self):
        """Re-check the installation status in the background. Ignored if a check is already running."""
        if self._detect_thread is not None:
            return
        self.ollama_status.setText(_("Checking..."))
        self.ollama_models_label.setText("")
        self.cosyvoice_status.setText(_("Checking..."))
        self.redetect_btn.setEnabled(False)
        self._detect_thread = LocalInstallDetectThread(self._cosyvoice_dir_provider())
        self._detect_thread.done.connect(self._on_detected)
        self._detect_thread.start()

    def stop_detection(self):
        """Briefly wait for the check thread to finish when the window closes."""
        if self._detect_thread is not None and self._detect_thread.isRunning():
            self._detect_thread.wait(3000)

    def _on_detected(self, result: dict):
        thread, self._detect_thread = self._detect_thread, None
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self.redetect_btn.setEnabled(True)
        self.ollama_path = result.get("ollama_path") or ""
        self.cosyvoice_dir = result.get("cosyvoice_dir") or ""
        self.ollama_status.setText(_status_text(self.ollama_path))
        self.ollama_models_label.setText(_models_text(self.ollama_path, result.get("ollama_models")))
        self.ollama_install_btn.setText(_("Download models") if self.ollama_path else _("Install Ollama / download models"))
        self.cosyvoice_status.setText(_status_text(self.cosyvoice_dir))
        self.cosyvoice_install_btn.setText(
            _("Reinstall CosyVoice") if self.cosyvoice_dir else _("Install CosyVoice")
        )
        self.detection_finished.emit(result)


def _status_text(path: str) -> str:
    return _("Installed: {path}", path=path) if path else _("Not installed")


def _models_text(ollama_path: str, models: list[str] | None) -> str:
    if not ollama_path:
        return ""
    if models is None:
        return _("The Ollama server did not respond, so the installed models could not be checked.")
    if not models:
        return _("No models are installed.")
    return _("Installed models: {models}", models=", ".join(models))
