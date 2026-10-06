"""
Plugin management settings page widget (extensions tab)
"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from i18n.translator import _
from ui.theme import secondary_btn_style, BUTTON_LG
from ui.common import create_muted_label
from ui.marketplace_browser import MarketplaceFetchThread, MarketplaceInstallThread

_live_marketplace_threads: set[QThread] = set()


def _track_marketplace_thread(thread: QThread) -> None:
    _live_marketplace_threads.add(thread)
    thread.finished.connect(lambda tracked=thread: _live_marketplace_threads.discard(tracked))


class _PluginSettingsPage(QWidget):
    """Plugin management and marketplace tab widget."""

    _ACTION_BUTTON_HEIGHT = BUTTON_LG + 6
    # Keeps a few rows of the list visible even when the window is small and the tab scrolls.
    _LIST_MIN_HEIGHT = 96

    def __init__(self, parent=None):
        super().__init__(parent)
        self._market_fetch_thread: MarketplaceFetchThread | None = None
        self._market_install_thread: MarketplaceInstallThread | None = None
        self._market_items: list[dict] = []
        self._market_installing_plugin_name = ""
        self._closed = False
        self._init_ui()

    # ── UI layout ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        vbox = QVBoxLayout(self)

        # Marketplace group
        marketplace_group = QGroupBox(_("Marketplace"))
        mvbox = QVBoxLayout(marketplace_group)
        mvbox.addWidget(create_muted_label(
            _("Search for and install plugins directly from the settings window.")
        ))

        search_row = QHBoxLayout()
        self.market_search_input = QLineEdit()
        self.market_search_input.setPlaceholderText(_("Search plugins"))
        search_row.addWidget(self.market_search_input)
        market_search_btn = QPushButton(_("Search"))
        market_search_btn.setStyleSheet(secondary_btn_style())
        market_search_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        market_search_btn.clicked.connect(self._refresh_marketplace_list)
        search_row.addWidget(market_search_btn)
        mvbox.addLayout(search_row)

        self.marketplace_list = QListWidget()
        self.marketplace_list.setMinimumHeight(self._LIST_MIN_HEIGHT)
        mvbox.addWidget(self.marketplace_list)

        self.marketplace_status_label = create_muted_label("")
        mvbox.addWidget(self.marketplace_status_label)

        market_btn_row = QHBoxLayout()
        self.market_install_btn = QPushButton(_("Install selected plugin"))
        self.market_install_btn.setStyleSheet(secondary_btn_style())
        self.market_install_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        self.market_install_btn.clicked.connect(self._install_selected_marketplace_plugin)
        market_refresh_btn = QPushButton(_("Refresh the list"))
        market_refresh_btn.setStyleSheet(secondary_btn_style())
        market_refresh_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        market_refresh_btn.clicked.connect(self._refresh_marketplace_list)
        market_open_btn = QPushButton(_("Open the web marketplace"))
        market_open_btn.setStyleSheet(secondary_btn_style())
        market_open_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        market_open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://ari-voice-command.vercel.app/marketplace"))
        )
        market_btn_row.addWidget(self.market_install_btn)
        market_btn_row.addWidget(market_refresh_btn)
        market_btn_row.addWidget(market_open_btn)
        mvbox.addLayout(market_btn_row)

        vbox.addWidget(marketplace_group)

        # User plugins group
        plugin_group = QGroupBox(_("User plugins"))
        pvbox = QVBoxLayout(plugin_group)

        try:
            from core.resource_manager import ResourceManager
            plugin_dir = ResourceManager.ensure_plugin_files()
        except Exception:
            plugin_dir = os.path.join(os.getcwd(), "plugins")

        pvbox.addWidget(QLabel(_("Plugins folder:")))
        self.plugin_dir_input = QLineEdit(plugin_dir)
        self.plugin_dir_input.setReadOnly(True)
        pvbox.addWidget(self.plugin_dir_input)

        self.plugin_list = QListWidget()
        self.plugin_list.setMinimumHeight(self._LIST_MIN_HEIGHT)
        pvbox.addWidget(self.plugin_list)

        btn_row = QHBoxLayout()
        open_btn = QPushButton(_("Open the plugins folder"))
        open_btn.setStyleSheet(secondary_btn_style())
        open_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        open_btn.clicked.connect(self._open_plugin_folder)
        reload_btn = QPushButton(_("Refresh the plugin list"))
        reload_btn.setStyleSheet(secondary_btn_style())
        reload_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        reload_btn.clicked.connect(self._refresh_plugin_list)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(reload_btn)
        pvbox.addLayout(btn_row)

        vbox.addWidget(plugin_group)

        skill_group = QGroupBox(_("Agent Skills"))
        svbox = QVBoxLayout(skill_group)
        svbox.addWidget(
            create_muted_label(_("SKILL.md format skill. Can be shared with other agents such as Claude Code."))
        )

        skill_row = QHBoxLayout()
        self.skill_source_input = QLineEdit()
        self.skill_source_input.setPlaceholderText(
            _("GitHub (e.g. NomaDamas/k-skill), URL, or local path")
        )
        skill_row.addWidget(self.skill_source_input, 1)
        skill_install_btn = QPushButton(_("Install"))
        skill_install_btn.setStyleSheet(secondary_btn_style())
        skill_install_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        skill_install_btn.clicked.connect(self._install_skill)
        skill_row.addWidget(skill_install_btn)
        svbox.addLayout(skill_row)

        self.skill_list_widget = QListWidget()
        self.skill_list_widget.setMinimumHeight(self._LIST_MIN_HEIGHT)
        self.skill_list_widget.setMaximumHeight(120)
        svbox.addWidget(self.skill_list_widget)

        skill_btn_row = QHBoxLayout()
        manage_btn = QPushButton(_("Open the skill management window"))
        manage_btn.setStyleSheet(secondary_btn_style())
        manage_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        manage_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        manage_btn.clicked.connect(self._open_skill_manager)
        refresh_btn = QPushButton(_("Refresh the list"))
        refresh_btn.setStyleSheet(secondary_btn_style())
        refresh_btn.setMinimumHeight(self._ACTION_BUTTON_HEIGHT)
        refresh_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        refresh_btn.clicked.connect(self._refresh_skill_list)
        skill_btn_row.addWidget(manage_btn, 1)
        skill_btn_row.addWidget(refresh_btn, 1)
        svbox.addLayout(skill_btn_row)

        vbox.addWidget(skill_group)
        vbox.addStretch()

        self._refresh_plugin_list()
        self._refresh_marketplace_list()
        self._refresh_skill_list()

    # ── Plugin list ──────────────────────────────────────────────────────────

    def _refresh_plugin_list(self):
        self.plugin_list.clear()
        try:
            from core.plugin_loader import get_plugin_manager
            plugins = get_plugin_manager().discover_plugins()
        except Exception as exc:
            item = QListWidgetItem(_("Failed to load the plugin list: {error}").format(error=exc))
            self.plugin_list.addItem(item)
            return

        if not plugins:
            self.plugin_list.addItem(
                QListWidgetItem(_("No plugins found. You can start by copying sample_plugin.py."))
            )
            return
        for plugin in plugins:
            label = _("{name} ({version}) - {description}").format(
                name=plugin.name,
                version=plugin.version,
                description=plugin.description or _("No description")
            )
            self.plugin_list.addItem(QListWidgetItem(label))

    def _installed_plugin_names(self) -> set[str]:
        try:
            from core.plugin_loader import get_plugin_manager
            return {plugin.name for plugin in get_plugin_manager().discover_plugins()}
        except Exception:
            return set()

    def _open_plugin_folder(self):
        path = self.plugin_dir_input.text().strip()
        if not path:
            return
        try:
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            if not opened:
                raise RuntimeError("Failed to open folder")
        except Exception:
            QMessageBox.information(self, _("Plugins folder"), path)

    # ── Marketplace ──────────────────────────────────────────────────────────

    def _refresh_marketplace_list(self):
        if self._market_fetch_thread and self._market_fetch_thread.isRunning():
            return

        self.marketplace_status_label.setText(_("Loading the marketplace list..."))
        self.marketplace_status_label.setStyleSheet("color: #888;")
        self.market_install_btn.setEnabled(False)
        self.marketplace_list.clear()

        self._market_fetch_thread = MarketplaceFetchThread(
            search=self.market_search_input.text(),
        )
        _track_marketplace_thread(self._market_fetch_thread)
        self._market_fetch_thread.done.connect(self._on_marketplace_fetch_done)
        self._market_fetch_thread.start()

    def _on_marketplace_fetch_done(self, success: bool, items: object, message: str):
        if self._closed:
            return
        self._market_fetch_thread = None
        self.marketplace_list.clear()
        self._market_items = list(items) if isinstance(items, list) else []

        if not success:
            self.marketplace_status_label.setText(_("Failed to load the list: {message}").format(message=message))
            self.marketplace_status_label.setStyleSheet("color: #e74c3c;")
            self.market_install_btn.setEnabled(False)
            return

        installed_names = self._installed_plugin_names()
        for item in self._market_items:
            name = str(item.get("name", _("No name")))
            version = str(item.get("version", "0.0.0"))
            install_count = int(item.get("install_count", 0) or 0)
            desc = str(item.get("description", "") or _("No description"))
            status = _("Installed") if name in installed_names else _("Available to install")
            label = _("{name} v{version} [{status}] ({count} installs)\n{desc}").format(
                name=name, version=version, status=status, count=install_count, desc=desc
            )
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.UserRole, item)
            self.marketplace_list.addItem(list_item)

        if self._market_items:
            self.marketplace_status_label.setText(_("Loaded {count} plugins.").format(count=len(self._market_items)))
            self.marketplace_status_label.setStyleSheet("color: #27ae60;")
            self.market_install_btn.setEnabled(True)
        else:
            self.marketplace_status_label.setText(_("No plugins to display."))
            self.marketplace_status_label.setStyleSheet("color: #888;")
            self.market_install_btn.setEnabled(False)

    def _install_selected_marketplace_plugin(self):
        item = self.marketplace_list.currentItem()
        if item is None:
            QMessageBox.information(self, _("Marketplace"), _("Select a plugin to install first."))
            return

        payload = item.data(Qt.UserRole) or {}
        plugin_id = str(payload.get("id", "") or "")
        plugin_name = str(payload.get("name", "") or _("Plugins"))
        if not plugin_id:
            QMessageBox.warning(self, _("Marketplace"), _("Could not find the ID of the selected plugin."))
            return

        confirm = QMessageBox.question(
            self,
            _("Install plugin"),
            _("Install the plugin {name}?").format(name=plugin_name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return

        self.market_install_btn.setEnabled(False)
        self.marketplace_status_label.setText(_("Installing {name}...").format(name=plugin_name))
        self.marketplace_status_label.setStyleSheet("color: #888;")

        self._market_installing_plugin_name = plugin_name
        self._market_install_thread = MarketplaceInstallThread(
            plugin_id,
            self.plugin_dir_input.text().strip(),
        )
        _track_marketplace_thread(self._market_install_thread)
        self._market_install_thread.done.connect(self._on_marketplace_install_done)
        self._market_install_thread.start()

    def _on_marketplace_install_done(self, success: bool, message: str):
        if self._closed:
            return
        self._market_install_thread = None
        if success:
            try:
                self._activate_installed_marketplace_plugin()
            except Exception as exc:
                success = False
                message = _(
                    "The plugin file was saved, but enabling it failed: {error}"
                ).format(error=exc)

        if success:
            self.marketplace_status_label.setText(message)
            self.marketplace_status_label.setStyleSheet("color: #27ae60;")
            self._refresh_plugin_list()
            self._refresh_marketplace_list()
            QMessageBox.information(self, _("Marketplace"), message)
        else:
            self.market_install_btn.setEnabled(True)
            self.marketplace_status_label.setText(message)
            self.marketplace_status_label.setStyleSheet("color: #e74c3c;")
            QMessageBox.warning(self, _("Marketplace"), message)
        self._market_installing_plugin_name = ""

    def _activate_installed_marketplace_plugin(self) -> None:
        from core.marketplace_client import _plugin_target_filename
        from core.plugin_loader import get_plugin_manager

        manager = get_plugin_manager()
        plugin_path = os.path.join(
            self.plugin_dir_input.text().strip(),
            _plugin_target_filename(self._market_installing_plugin_name),
        )
        if not os.path.isfile(plugin_path):
            raise RuntimeError(_("No installed plugins were found."))
        loaded = manager.load_plugin(plugin_path)
        if not loaded.loaded:
            raise RuntimeError(loaded.error)

    def _refresh_skill_list(self):
        from agent.skill_manager import get_skill_manager

        self.skill_list_widget.clear()
        for skill in get_skill_manager().load_all():
            prefix = "✓" if skill.enabled else "○"
            suffix = " [MCP]" if skill.is_mcp_skill else ""
            self.skill_list_widget.addItem(f"{prefix}  {skill.name}{suffix}")

    def _install_skill(self):
        from ui.skills_dialog import SkillsDialog

        dialog = SkillsDialog(parent=self)
        dialog.source_input.setText(self.skill_source_input.text().strip())
        dialog.exec()
        self._refresh_skill_list()

    def _open_skill_manager(self):
        from ui.skills_dialog import SkillsDialog

        SkillsDialog(parent=self).exec()
        self._refresh_skill_list()

    # ── Public interface ────────────────────────────────────────────────────────

    def cleanup_threads(self):
        """Clean up the running thread when the dialog closes."""
        self._closed = True
        for thread in (self._market_fetch_thread, self._market_install_thread):
            if thread and thread.isRunning():
                thread.quit()
