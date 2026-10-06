"""Agent skill management dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from i18n.translator import _
from ui.common import create_muted_label
from ui.theme import secondary_btn_style, BUTTON_LG


_live_install_threads: set[QThread] = set()


def _release_install_thread(thread: QThread) -> None:
    _live_install_threads.discard(thread)
    thread.deleteLater()


def _install_running() -> bool:
    """Reports whether a previously started installation is still running after the window is closed and reopened."""
    for thread in list(_live_install_threads):
        try:
            if thread.isRunning():
                return True
        except RuntimeError:
            # A Qt object that has already been deleted is not running.
            continue
    return False


class _SkillInstallThread(QThread):
    done = Signal(object)
    error = Signal(str)

    def __init__(self, source: str, skills_dir: str, skill_dir: str | None = None):
        super().__init__()
        self.source = source
        self.skills_dir = skills_dir
        self.skill_dir = skill_dir

    def run(self) -> None:
        try:
            from agent.skill_installer import SkillInstaller

            installer = SkillInstaller(self.skills_dir)
            installed = (
                installer.update(self.skill_dir)
                if self.skill_dir is not None
                else installer.install(self.source)
            )
            self.done.emit(installed)
        except Exception as exc:
            self.error.emit(str(exc))


class SkillsDialog(QDialog):
    """Preview, install, enable, and delete installed SKILL.md skills."""

    _ACTION_BUTTON_HEIGHT = BUTTON_LG + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._install_thread: _SkillInstallThread | None = None
        self._closed = False
        self._close_notice_shown = False
        self._app_quitting = False
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._mark_app_quitting)
        self.setWindowTitle(_("🧩 Skill management"))
        self.resize(860, 580)
        self._init_ui()
        self._refresh_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(create_muted_label(_("Select a skill to see its SKILL.md contents.")))

        source_row = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText(
            _("GitHub (e.g. NomaDamas/k-skill), URL, or local path")
        )
        source_row.addWidget(self.source_input, 1)
        install_button = QPushButton(_("Install"))
        install_button.setStyleSheet(secondary_btn_style())
        install_button.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        install_button.clicked.connect(self._on_install)
        source_row.addWidget(install_button)
        layout.addLayout(source_row)

        content_row = QHBoxLayout()
        self.skill_list = QListWidget()
        self.skill_list.currentItemChanged.connect(self._on_select)
        content_row.addWidget(self.skill_list, 1)

        preview_column = QVBoxLayout()
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        preview_column.addWidget(self.summary_label)
        self.mcp_label = create_muted_label("")
        self.mcp_label.setVisible(False)
        preview_column.addWidget(self.mcp_label)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        preview_column.addWidget(self.preview, 1)
        content_row.addLayout(preview_column, 2)
        layout.addLayout(content_row, 1)

        button_row = QHBoxLayout()
        self.toggle_button = QPushButton(_("Disable"))
        self.toggle_button.setStyleSheet(secondary_btn_style())
        self.toggle_button.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        self.toggle_button.setMinimumWidth(120)
        self.toggle_button.clicked.connect(self._on_toggle)
        update_button = QPushButton(_("Update"))
        update_button.setStyleSheet(secondary_btn_style())
        update_button.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        update_button.setMinimumWidth(120)
        update_button.clicked.connect(self._on_update)
        delete_button = QPushButton(_("Delete"))
        delete_button.setStyleSheet(secondary_btn_style())
        delete_button.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        delete_button.setMinimumWidth(120)
        delete_button.clicked.connect(self._on_delete)
        close_button = QPushButton(_("Close"))
        close_button.setStyleSheet(secondary_btn_style())
        close_button.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        close_button.setMinimumWidth(120)
        close_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        close_button.clicked.connect(self.accept)
        button_row.addWidget(self.toggle_button)
        button_row.addWidget(update_button)
        button_row.addWidget(delete_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def _refresh_list(self) -> None:
        from agent.skill_manager import get_skill_manager

        self.skill_list.clear()
        for skill in get_skill_manager().load_all():
            prefix = "✓" if skill.enabled else "○"
            suffix = " [MCP]" if skill.is_mcp_skill else ""
            item = QListWidgetItem(f"{prefix} {skill.name}{suffix}")
            item.setData(Qt.UserRole, skill.name)
            self.skill_list.addItem(item)
        if self.skill_list.count():
            self.skill_list.setCurrentRow(0)

    def _selected_skill_name(self) -> str:
        item = self.skill_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item else ""

    def _on_select(self, item, _previous) -> None:
        del _previous
        from agent.skill_manager import get_skill_manager

        if item is None:
            self.summary_label.clear()
            self.preview.clear()
            self.mcp_label.setVisible(False)
            return
        skill = get_skill_manager().get_skill(str(item.data(Qt.UserRole) or ""))
        if skill is None:
            return
        self.summary_label.setText(skill.description)
        self.preview.setPlainText(skill.content)
        self.toggle_button.setText(_("Enable") if not skill.enabled else _("Disable"))
        if skill.is_mcp_skill:
            self.mcp_label.setText(f"🔌 MCP: {skill.mcp_endpoint}")
            self.mcp_label.setVisible(True)
        else:
            self.mcp_label.setVisible(False)

    def _on_install(self) -> None:
        source = self.source_input.text().strip()
        if not source:
            return
        if self._install_thread and self._install_thread.isRunning():
            return
        if _install_running():
            QMessageBox.information(self, _("Installing"), _("A previously started installation is still running. Please try again once it finishes."))
            return

        from agent.skill_manager import get_skill_manager

        progress = QProgressDialog(_("Installing"), None, 0, 0, self)
        progress.setLabelText(_("Installing skill..."))
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        self._install_thread = _SkillInstallThread(source, get_skill_manager().skills_dir)
        _live_install_threads.add(self._install_thread)
        self._install_thread.finished.connect(
            lambda thread=self._install_thread: _release_install_thread(thread)
        )
        self._install_thread.finished.connect(
            lambda thread=self._install_thread: self._on_install_thread_finished(thread)
        )
        self._install_thread.done.connect(lambda names: self._on_install_done(names, progress))
        self._install_thread.error.connect(lambda message: self._on_install_error(message, progress))
        self._install_thread.start()

    def _on_install_done(self, names: object, progress: QProgressDialog) -> None:
        if self._closed:
            return
        progress.close()
        installed_names = list(names) if isinstance(names, (list, tuple)) else []
        if installed_names:
            QMessageBox.information(
                self,
                _("Installation complete"),
                _("Installed skills: {names}").format(names=", ".join(installed_names)),
            )
            self._refresh_list()
        else:
            QMessageBox.warning(self, _("Installation failed"), _("The skill could not be installed."))

    def _on_install_error(self, message: str, progress: QProgressDialog) -> None:
        if self._closed:
            return
        progress.close()
        QMessageBox.warning(self, _("Installation failed"), message)

    def _on_install_thread_finished(self, thread: _SkillInstallThread) -> None:
        if self._install_thread is thread:
            self._install_thread = None

    def _on_toggle(self) -> None:
        from agent.skill_manager import get_skill_manager

        name = self._selected_skill_name()
        skill = get_skill_manager().get_skill(name)
        if skill is None:
            return
        if skill.enabled:
            get_skill_manager().disable(name)
        else:
            get_skill_manager().enable(name)
        self._refresh_list()

    def _on_update(self) -> None:
        from agent.skill_manager import get_skill_manager

        name = self._selected_skill_name()
        if not name:
            return
        if self._install_thread and self._install_thread.isRunning():
            return
        if _install_running():
            QMessageBox.information(self, _("Update"), _("A previously started installation is still running. Please try again once it finishes."))
            return
        skill_manager = get_skill_manager()
        skill = skill_manager.get_skill(name)
        if skill is None:
            return

        progress = QProgressDialog(_("Update"), None, 0, 0, self)
        progress.setLabelText(_("Updating skill..."))
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        self._install_thread = _SkillInstallThread(
            "", skill_manager.skills_dir, skill.skill_dir
        )
        _live_install_threads.add(self._install_thread)
        self._install_thread.finished.connect(
            lambda thread=self._install_thread: _release_install_thread(thread)
        )
        self._install_thread.finished.connect(
            lambda thread=self._install_thread: self._on_install_thread_finished(thread)
        )
        self._install_thread.done.connect(
            lambda result: self._on_update_done(result, name, progress)
        )
        self._install_thread.error.connect(
            lambda message: self._on_update_error(message, progress)
        )
        self._install_thread.start()

    def _on_update_done(self, result: object, name: str, progress: QProgressDialog) -> None:
        if self._closed:
            return
        progress.close()
        if result:
            self._refresh_list()
            QMessageBox.information(self, _("Update"), _("{name} updated").format(name=name))
        else:
            QMessageBox.warning(self, _("Update failed"), _("No source information is available for this installation."))

    def _on_update_error(self, message: str, progress: QProgressDialog) -> None:
        if self._closed:
            return
        progress.close()
        QMessageBox.warning(self, _("Update failed"), message)

    def _mark_app_quitting(self) -> None:
        self._app_quitting = True

    def _defer_close_during_install(self) -> bool:
        if self._app_quitting or not _install_running():
            return False
        if not self._close_notice_shown:
            self._close_notice_shown = True
            QMessageBox.information(
                self,
                _("Installing"),
                _("A previously started installation is still running. Please try again once it finishes."),
            )
        return True

    def done(self, result: int) -> None:
        if self._defer_close_during_install():
            return
        self._closed = True
        super().done(result)

    def closeEvent(self, event) -> None:
        if self._defer_close_during_install():
            event.ignore()
            return
        self._closed = True
        super().closeEvent(event)

    def _on_delete(self) -> None:
        from agent.skill_manager import get_skill_manager

        name = self._selected_skill_name()
        if not name:
            return
        confirmed = QMessageBox.question(
            self,
            _("Delete skill"),
            _("Delete the skill {name}?").format(name=name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmed != QMessageBox.Yes:
            return
        get_skill_manager().remove(name)
        self._refresh_list()
