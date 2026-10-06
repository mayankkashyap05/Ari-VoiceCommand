"""Agent execution settings page."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from agent.learning_metrics import get_learning_metrics
from i18n.translator import _


_google_auth_threads: set[QThread] = set()


class _GoogleAuthThread(QThread):
    result = Signal(bool, str)

    def __init__(self, action: str, client_id: str, client_secret: str):
        super().__init__()
        self.action = action
        self.client_id = client_id
        self.client_secret = client_secret
        self.cancel_event = threading.Event()

    def run(self):
        try:
            from services import google_auth
            if self.action == "connect":
                google_auth.authorize(
                    self.client_id,
                    self.client_secret,
                    cancel_event=self.cancel_event,
                )
                self.result.emit(True, "settings.agent.google_auth_success")
            else:
                google_auth.sign_out()
                self.result.emit(True, "settings.agent.google_disconnected")
        except Exception as exc:
            self.result.emit(
                False,
                "settings.agent.google_auth_cancelled"
                if self.action == "connect" and self.cancel_event.is_set()
                else str(exc),
            )


def _live_decision_engine():
    """Return the running local decision engine without importing the app core modules."""
    state = getattr(sys.modules.get("core.VoiceCommand"), "_state", None)
    registry = getattr(state, "command_registry", None)
    for command in getattr(registry, "commands", ()) or ():
        get_engine = getattr(command, "decision_engine", None)
        if get_engine is not None:
            return get_engine()
    return None


class _AgentSettingsPage(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._settings = settings
        layout = QVBoxLayout(self)

        group = QGroupBox(_("Agent execution"))
        box = QVBoxLayout(group)

        self.timeout_label = QLabel("")
        self.timeout_slider = QSlider(Qt.Horizontal)
        self.timeout_slider.setRange(30, 600)
        self.timeout_slider.setSingleStep(10)
        self.timeout_slider.setPageStep(30)
        self.timeout_slider.setValue(int(settings.get("agent_timeout_seconds", 120)))
        self.timeout_slider.valueChanged.connect(self._update_timeout_label)
        box.addWidget(QLabel(_("Overall execution timeout (seconds)")))
        box.addWidget(self.timeout_slider)
        box.addWidget(self.timeout_label)

        self.dashboard_checkbox = QCheckBox(_("Use the agent dashboard"))
        self.dashboard_checkbox.setChecked(bool(settings.get("agent_dashboard_enabled", True)))
        box.addWidget(self.dashboard_checkbox)

        self.audit_checkbox = QCheckBox(_("Record a tool execution audit log"))
        self.audit_checkbox.setChecked(bool(settings.get("audit_log_enabled", True)))
        box.addWidget(self.audit_checkbox)

        self.mcp_checkbox = QCheckBox(_("Use the local MCP server"))
        self.mcp_checkbox.setChecked(bool(settings.get("mcp_server_enabled", False)))
        box.addWidget(self.mcp_checkbox)

        self.subagent_spin = QSpinBox()
        self.subagent_spin.setRange(1, 8)
        self.subagent_spin.setValue(int(settings.get("max_subagents", 3)))
        box.addWidget(QLabel(_("settings.agent.max_subagents")))
        box.addWidget(self.subagent_spin)

        self.google_checkbox = QCheckBox(_("settings.agent.google_tools"))
        self.google_checkbox.setChecked(bool(settings.get("google_calendar_enabled", False)))
        box.addWidget(self.google_checkbox)
        self.google_client_id = QLineEdit(str(settings.get("google_client_id", "") or ""))
        self.google_client_id.setPlaceholderText(_("settings.agent.google_client_id"))
        box.addWidget(self.google_client_id)
        self.google_client_secret = QLineEdit(str(settings.get("google_client_secret", "") or ""))
        self.google_client_secret.setPlaceholderText(_("settings.agent.google_client_secret"))
        self.google_client_secret.setEchoMode(QLineEdit.Password)
        box.addWidget(self.google_client_secret)
        self.google_status = QLabel("")
        box.addWidget(self.google_status)
        google_buttons = QHBoxLayout()
        self.google_connect_button = QPushButton(_("settings.agent.google_connect"))
        self.google_disconnect_button = QPushButton(_("settings.agent.google_disconnect"))
        self.google_connect_button.clicked.connect(self._connect_google)
        self.google_disconnect_button.clicked.connect(self._disconnect_google)
        google_buttons.addWidget(self.google_connect_button)
        google_buttons.addWidget(self.google_disconnect_button)
        box.addLayout(google_buttons)
        self._google_auth_thread = None
        self._refresh_google_status()

        self.image_checkbox = QCheckBox(_("settings.agent.image_generation"))
        self.image_checkbox.setChecked(bool(settings.get("image_generation_enabled", False)))
        box.addWidget(self.image_checkbox)
        self.image_provider = QLineEdit(str(settings.get("image_gen_provider", "openai") or "openai"))
        box.addWidget(self.image_provider)

        layout.addWidget(group)
        layout.addWidget(self._build_embedding_group(settings))
        layout.addWidget(self._build_learning_metrics_group())
        developer_group = QGroupBox(_("Developer settings"))
        developer_box = QVBoxLayout(developer_group)
        self.plugin_hot_reload_checkbox = QCheckBox(_("Use plugin hot reload"))
        self.plugin_hot_reload_checkbox.setChecked(
            bool(settings.get("plugin_hot_reload_enabled", False))
        )
        developer_box.addWidget(self.plugin_hot_reload_checkbox)
        note = QLabel(_("Applied on the next app start."))
        note.setWordWrap(True)
        developer_box.addWidget(note)
        layout.addWidget(developer_group)
        layout.addWidget(self._build_local_decision_group(settings))
        layout.addStretch(1)
        self._update_timeout_label(self.timeout_slider.value())

    def _build_embedding_group(self, settings: dict) -> QGroupBox:
        group = QGroupBox(_("Strategy search"))
        box = QVBoxLayout(group)
        self.embedding_remote_checkbox = QCheckBox(
            _("Use OpenAI embeddings (sends strategy text externally)")
        )
        self.embedding_remote_checkbox.setChecked(
            settings.get("embedding_remote_enabled") is True
        )
        box.addWidget(self.embedding_remote_checkbox)
        self.embedding_status = QLabel("")
        self.embedding_status.setWordWrap(True)
        box.addWidget(self.embedding_status)
        self.embedding_status_timer = QTimer(self)
        self.embedding_status_timer.setInterval(1000)
        self.embedding_status_timer.timeout.connect(self._refresh_embedding_status)
        self.embedding_status_timer.start()
        self._refresh_embedding_status()
        return group

    def _refresh_embedding_status(self) -> None:
        from agent.embedder import get_embedder

        embedder = get_embedder()
        if embedder.backend == "openai" and embedder.status == "remote":
            text = _("Using remote embeddings")
        elif embedder.status == "ready":
            text = _("Local embedding model: ready")
        elif embedder.status == "downloading":
            progress = int(embedder.progress * 100)
            text = _("Downloading the local embedding model: {progress}%").format(
                progress=progress
            )
        elif embedder.status == "loading":
            text = _("Loading the local embedding model")
        elif embedder.status == "failed":
            text = _("Embeddings are unavailable. Using lexical scores only.")
        else:
            text = _("Local embedding model: waiting to download")
        self.embedding_status.setText(text)

    def _refresh_google_status(self) -> None:
        from services.google_auth import is_connected
        connected = is_connected()
        self.google_status.setText(_(
            "settings.agent.google_connected" if connected
            else "settings.agent.google_not_connected"
        ))
        self.google_disconnect_button.setEnabled(connected)

    def _connect_google(self) -> None:
        thread = self._google_auth_thread
        if thread is not None and thread.action == "connect":
            thread.cancel_event.set()
            return
        client_id = self.google_client_id.text().strip()
        client_secret = self.google_client_secret.text().strip()
        if not client_id or not client_secret:
            self.google_status.setText(_("settings.agent.google_credentials_required"))
            return
        self._start_google_auth("connect", client_id, client_secret)

    def _disconnect_google(self) -> None:
        self._start_google_auth("disconnect", "", "")

    def _start_google_auth(self, action: str, client_id: str, client_secret: str) -> None:
        thread = _GoogleAuthThread(action, client_id, client_secret)
        self._google_auth_thread = thread
        self.google_connect_button.setEnabled(action == "connect")
        self.google_connect_button.setText(_(
            "settings.agent.google_cancel" if action == "connect"
            else "settings.agent.google_connect"
        ))
        self.google_disconnect_button.setEnabled(False)
        self.google_status.setText(_(
            "settings.agent.google_connecting" if action == "connect"
            else "settings.agent.google_disconnecting"
        ))
        thread.result.connect(self._on_google_auth_result)
        thread.finished.connect(lambda t=thread: _google_auth_threads.discard(t))
        thread.finished.connect(self._google_auth_finished)
        _google_auth_threads.add(thread)
        thread.start()

    def _on_google_auth_result(self, success: bool, message: str) -> None:
        from services.google_auth import is_connected
        connected = is_connected()
        state = _("settings.agent.google_connected" if connected else "settings.agent.google_not_connected")
        if success:
            detail = _(message)
        elif message == "settings.agent.google_auth_cancelled":
            detail = _(message)
        else:
            detail = _("settings.agent.google_auth_failed").format(error=_(message))
        self.google_status.setText(f"{state}\n{detail}")
        self.google_disconnect_button.setEnabled(connected)

    def _google_auth_finished(self) -> None:
        thread = self.sender()
        if self._google_auth_thread is thread:
            self._google_auth_thread = None
        self.google_connect_button.setText(_("settings.agent.google_connect"))
        self.google_connect_button.setEnabled(True)

    def _build_learning_metrics_group(self) -> QGroupBox:
        group = QGroupBox(_("Learning contribution diagnostics"))
        box = QVBoxLayout(group)
        self.learning_metrics_status = QLabel("")
        self.learning_metrics_status.setWordWrap(True)
        box.addWidget(self.learning_metrics_status)
        self._refresh_learning_metrics_status()
        return group

    def _refresh_learning_metrics_status(self) -> None:
        labels = {
            "pending": _("Decision pending (not enough samples)"),
            "disabled": _("Disable"),
            "active": _("Enable"),
        }
        rows = get_learning_metrics().get_component_diagnostics()
        self.learning_metrics_status.setText(
            "\n".join(
                _("{component}: {status}").format(
                    component=row["name"],
                    status=labels[row["state"]],
                )
                for row in rows
            )
        )

    def _build_local_decision_group(self, settings: dict) -> QGroupBox:
        group = QGroupBox(_("Fast local processing"))
        box = QVBoxLayout(group)
        mode = settings.get("local_decision_mode", "fast")
        if mode not in ("off", "shadow", "fast"):
            mode = "off"
        direct = settings.get("local_decision_direct_execution", mode == "fast") is True

        self.local_decision_checkbox = QCheckBox(_("Handle simple commands locally right away"))
        self.local_decision_checkbox.setChecked(mode == "fast" and direct)
        box.addWidget(self.local_decision_checkbox)
        note = QLabel(_("Fast processing is on by default. Diagnostic recording mode can be selected separately."))
        note.setWordWrap(True)
        box.addWidget(note)

        box.addWidget(QLabel(_("Advanced: operation mode")))
        self.local_decision_mode = QComboBox()
        for value, label in (("off", _("Off")), ("shadow", _("Log only (diagnostic)")), ("fast", _("Fast processing"))):
            self.local_decision_mode.addItem(label, value)
        self.local_decision_mode.setCurrentIndex(self.local_decision_mode.findData(mode))
        box.addWidget(self.local_decision_mode)
        # A single toggle writes two saved values, and the advanced list follows the toggle.
        self.local_decision_checkbox.toggled.connect(self._on_local_decision_toggled)
        self.local_decision_mode.currentIndexChanged.connect(
            lambda _index: self.local_decision_checkbox.setChecked(
                self.local_decision_mode.currentData() == "fast"
            )
        )

        self.local_decision_status = QLabel("")
        box.addWidget(self.local_decision_status)
        reload_button = QPushButton(_("Reload the model"))
        reload_button.clicked.connect(self._reload_local_decision)
        box.addWidget(reload_button)
        self._refresh_local_decision_status()
        return group

    def _on_local_decision_toggled(self, checked: bool) -> None:
        current = self.local_decision_mode.currentData()
        # Unchecking clears fast only. A shadow mode chosen from the list for diagnostics is kept.
        if checked and current != "fast":
            target = "fast"
        elif not checked and current == "fast":
            target = "off"
        else:
            return
        self.local_decision_mode.setCurrentIndex(self.local_decision_mode.findData(target))

    def _refresh_local_decision_status(self) -> None:
        engine = _live_decision_engine()
        health = engine.health() if engine is not None else {"state": "not_loaded", "error_code": ""}
        if health.get("state") == "ready":
            text = _("Local decision model: ready")
        elif health.get("state") == "error":
            text = _("Local decision model: Error ({code})").format(code=health.get("error_code") or "-")
        else:
            text = _("Local decision model: not loaded yet (it loads on the first command)")
        self.local_decision_status.setText(text)

    def _reload_local_decision(self) -> None:
        engine = _live_decision_engine()
        if engine is not None:
            engine.reload()
            engine.load()
        self._refresh_local_decision_status()

    def _update_timeout_label(self, value: int) -> None:
        self.timeout_label.setText(_("{seconds} s").format(seconds=int(value)))

    def get_values(self) -> dict:
        mode = self.local_decision_mode.currentData() or "fast"
        # The checkbox is the source of truth. A stored fast + direct=false combination must not switch to direct execution
        # merely because other settings were saved.
        direct = mode == "fast" and self.local_decision_checkbox.isChecked()
        return {
            "agent_timeout_seconds": int(self.timeout_slider.value()),
            "plugin_hot_reload_enabled": self.plugin_hot_reload_checkbox.isChecked(),
            "agent_dashboard_enabled": self.dashboard_checkbox.isChecked(),
            "audit_log_enabled": self.audit_checkbox.isChecked(),
            "mcp_server_enabled": self.mcp_checkbox.isChecked(),
            "max_subagents": int(self.subagent_spin.value()),
            "google_calendar_enabled": self.google_checkbox.isChecked(),
            "google_client_id": self.google_client_id.text().strip(),
            "google_client_secret": self.google_client_secret.text().strip(),
            "image_generation_enabled": self.image_checkbox.isChecked(),
            "image_gen_provider": self.image_provider.text().strip() or "openai",
            "local_decision_mode": mode,
            "local_decision_direct_execution": direct,
            "embedding_remote_enabled": self.embedding_remote_checkbox.isChecked(),
        }

    def cleanup_threads(self):
        self.embedding_status_timer.stop()
        thread = self._google_auth_thread
        if thread is None:
            return
        thread.cancel_event.set()
        if thread.isRunning():
            thread.wait(1500)
        if not thread.isRunning():
            _google_auth_threads.discard(thread)
            self._google_auth_thread = None
        else:
            thread.result.disconnect(self._on_google_auth_result)
            thread.finished.disconnect(self._google_auth_finished)
