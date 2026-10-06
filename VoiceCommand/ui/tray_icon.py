"""UI wrapper that provides the system tray menu and the entry point to the settings dialog."""

import logging
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog
from ui.settings_dialog import SettingsDialog, reinitialize_tts_async, should_apply_microphone
from i18n.translator import _

class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super(SystemTrayIcon, self).__init__(icon, parent)
        self.setToolTip("Ari Voice Command")
        self.should_exit = False
        self.character_widget = None
        self.text_interface = None
        self.update_checker = None
        self._scheduled_tasks_dialog = None

        self.menu = QMenu(parent)
        self._apply_menu_theme()
        self.setContextMenu(self.menu)

        self.chat_action = self.menu.addAction(_("💬 Text chat"))
        self.chat_action.triggered.connect(self.open_text_interface)

        self.stop_speaking_action = self.menu.addAction(_("Stop speaking"))
        self.stop_speaking_action.triggered.connect(self.stop_speaking)

        self.character_action = self.menu.addAction(_("Show character"))
        self.character_action.triggered.connect(self.toggle_character)

        self.menu.addSeparator()

        self.game_mode_action = self.menu.addAction(_("🎮 Game mode (save GPU)"))
        self.game_mode_action.setCheckable(True)
        self.game_mode_action.triggered.connect(self.toggle_game_mode)

        self.smart_mode_action = self.menu.addAction(_("Smart assistant mode"))
        self.smart_mode_action.setCheckable(True)
        self.smart_mode_action.triggered.connect(self.toggle_smart_mode)

        self.mouse_reaction_action = self.menu.addAction(_("Mouse reactions"))
        self.mouse_reaction_action.setCheckable(True)
        self.mouse_reaction_action.triggered.connect(self.toggle_mouse_reaction)

        self._plugin_separator = self.menu.addSeparator()
        self._plugin_actions: list = []

        self.skills_action = self.menu.addAction(_("🧩 Skill management"))
        self.skills_action.triggered.connect(self.open_skills_dialog)

        self.settings_action = self.menu.addAction(_("Settings"))
        self.settings_action.triggered.connect(self.open_settings)

        self.scheduled_tasks_action = self.menu.addAction(_("Scheduled task management"))
        self.scheduled_tasks_action.triggered.connect(self.open_scheduled_tasks)

        self.menu.addSeparator()

        self.exit_action = self.menu.addAction(_("Quit"))
        self.exit_action.triggered.connect(self.exit)

        self.menu.aboutToShow.connect(self.update_character_menu_text)
        self.menu.aboutToShow.connect(self.update_game_mode_status)
        self.menu.aboutToShow.connect(self.update_smart_mode_status)
        self.menu.aboutToShow.connect(self.update_mouse_reaction_status)
        self.menu.aboutToShow.connect(self._apply_menu_theme)

    def add_plugin_menu_action(self, label: str, callback) -> None:
        """Public API that lets plugins add items to the tray menu."""
        action = QAction(label, self.menu)
        action.triggered.connect(callback)
        self.menu.insertAction(self.settings_action, action)
        self._plugin_actions.append(action)
        return action

    def remove_plugin_menu_action(self, action) -> None:
        if action in self._plugin_actions:
            self._plugin_actions.remove(action)
        self.menu.removeAction(action)
        action.deleteLater()

    def _apply_menu_theme(self):
        from ui import theme as theme_module
        self.menu.setStyleSheet(theme_module.MENU_STYLE)

    def stop_speaking(self):
        from VoiceCommand import stop_speaking
        stop_speaking()

    def toggle_game_mode(self):
        from VoiceCommand import enable_game_mode, disable_game_mode
        if self.game_mode_action.isChecked():
            enable_game_mode()
            if self.character_widget:
                self.character_widget.say(_("Game mode on. GPU memory released."), duration=3000)
        else:
            disable_game_mode()
            if self.character_widget:
                self.character_widget.say(_("Game mode off. Restoring TTS..."), duration=3000)

    def update_game_mode_status(self):
        from VoiceCommand import is_game_mode
        self.game_mode_action.setChecked(is_game_mode())

    def toggle_smart_mode(self):
        from VoiceCommand import learning_mode
        learning_mode['enabled'] = self.smart_mode_action.isChecked()
        status = _("Enable") if learning_mode['enabled'] else _("Disable")
        logging.info(f"Smart assistant mode {status}")
        if self.character_widget:
            message = _("Smart assistant mode has been {status}.").format(status=status)
            self.character_widget.say(message, duration=3000)

    def update_smart_mode_status(self):
        from VoiceCommand import learning_mode
        self.smart_mode_action.setChecked(learning_mode['enabled'])

    def toggle_mouse_reaction(self):
        if self.character_widget:
            self.character_widget.toggle_mouse_tracking()

    def update_mouse_reaction_status(self):
        if self.character_widget:
            self.mouse_reaction_action.setChecked(self.character_widget.mouse_tracking_enabled)

    def open_settings(self):
        dialog = SettingsDialog(update_checker=self.update_checker)
        if dialog.exec() == QDialog.Accepted:
            if should_apply_microphone(dialog, self.character_widget):
                if self.character_widget:
                    self.character_widget.apply_microphone_settings()
                else:
                    logging.warning("Character Widget unavailable, cannot Microphone apply settings.")

            if dialog.tts_settings_changed():
                reinitialize_tts_async()

            if dialog.theme_settings_changed():
                try:
                    from ui.theme_runtime import apply_live_theme
                    apply_live_theme(tray_icon=self, character_widget=self.character_widget)
                except Exception as e:
                    logging.error(f"Real-time theme reflection failed: {e}")

    def open_skills_dialog(self):
        try:
            from ui.skills_dialog import SkillsDialog

            SkillsDialog(parent=None).exec()
        except Exception as e:
            logging.error("Failed to open the skill management window: %s", e)

    def open_scheduled_tasks(self):
        try:
            from agent.proactive_scheduler import get_scheduler
            from ui.scheduled_tasks_dialog import ScheduledTasksDialog

            if self._scheduled_tasks_dialog is None:
                self._scheduled_tasks_dialog = ScheduledTasksDialog(get_scheduler())
            self._scheduled_tasks_dialog.show()
            self._scheduled_tasks_dialog.raise_()
            self._scheduled_tasks_dialog.activateWindow()
        except Exception as e:
            logging.error(f"Failed to open the scheduled task window: {e}")

    def exit(self):
        self.should_exit = True
        QApplication.instance().quit()

    def set_character_widget(self, character_widget):
        self.character_widget = character_widget
        self.update_character_menu_text()
        logging.info("The character widget reference has been set on the system tray.")

    def set_text_interface(self, text_interface):
        self.text_interface = text_interface

    def set_update_checker(self, update_checker):
        self.update_checker = update_checker

    def open_text_interface(self):
        if self.text_interface:
            screen = QApplication.primaryScreen().geometry()
            self.text_interface.show_near(screen.width() - 100, screen.height() - 100, 0, 0)

    def toggle_character(self):
        if not self.character_widget:
            logging.warning("Character Widget has not been initialized.")
            return
        if self.character_widget.isVisible():
            self.character_widget.hide()
            logging.info("Character hidden.")
        else:
            self.character_widget.show()
            logging.info("Character shown.")

    def update_character_menu_text(self):
        if self.character_widget and self.character_widget.isVisible():
            self.character_action.setText(_("Hide character"))
        else:
            self.character_action.setText(_("Show character"))

    def refresh_language(self) -> None:
        """Refresh the tray menu text immediately when the language changes."""
        self.chat_action.setText(_("💬 Text chat"))
        self.stop_speaking_action.setText(_("Stop speaking"))
        self.game_mode_action.setText(_("🎮 Game mode (save GPU)"))
        self.smart_mode_action.setText(_("Smart assistant mode"))
        self.mouse_reaction_action.setText(_("Mouse reactions"))
        self.skills_action.setText(_("🧩 Skill management"))
        self.settings_action.setText(_("Settings"))
        self.scheduled_tasks_action.setText(_("Scheduled task management"))
        self.exit_action.setText(_("Quit"))
        self.update_character_menu_text()
