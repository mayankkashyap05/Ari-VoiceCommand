"""
Settings window GUI — tab-based layout (RP, LLM, TTS, devices, extensions)
The detailed implementation of each tab is delegated to settings_llm_page / settings_tts_page / settings_plugin_page.
"""
import logging
from html import escape
from urllib.parse import urlsplit

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton,
    QComboBox, QGroupBox, QWidget, QCheckBox,
    QTabWidget, QMessageBox, QFrame, QSlider, QSpinBox, QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.app_version import compare_versions, get_build_info
from core.activity_monitor import refresh_activity_monitor
from core.config_manager import ConfigManager
from core.update_checker import get_update_status
from core.custom_llm_providers import is_custom_secret_key
from i18n.translator import _, set_language, get_language
from ui.theme import (
    FONT_KO, FONT_SIZE_NORMAL, COLOR_SUCCESS,
    TAB_STYLE, INPUT_STYLE, scrollbar_style,
    available_theme_presets, secondary_btn_style, theme_dir, load_theme_palette,
)
from ui.theme_editor import ThemeEditorDialog
from ui.common import create_muted_label
from ui.settings_llm_page import _LLMSettingsPage
from ui.settings_tts_page import _TTSSettingsPage
from ui.settings_plugin_page import _PluginSettingsPage
from ui.settings_agent_page import _AgentSettingsPage
from ui.audio_diagnostic_panel import AudioDiagnosticPanel


def should_apply_microphone(dialog, character_widget) -> bool:
    """Decide whether to re-apply the microphone settings to the speech thread after saving.

    If speech recognition has stopped because no microphone is available, re-apply even when the selection is unchanged (for example a default device that was just connected),
    treating the settings save as a user retry.
    """
    if dialog.microphone_settings_changed():
        return True
    voice_thread = getattr(character_widget, "voice_thread", None)
    return getattr(voice_thread, "microphone_available", None) is False


def reinitialize_tts_async() -> None:
    """Re-initialize TTS in the background so that a TTS settings change does not block the GUI."""
    import threading
    from VoiceCommand import initialize_tts, _tts_init_event
    _tts_init_event.clear()

    def _reinit():
        try:
            initialize_tts()
        except Exception as e:
            logging.error(f"TTS Reinitialization failed: {e}")
        finally:
            # Even on failure, a later speech request must not block while waiting for initialization to finish.
            _tts_init_event.set()

    threading.Thread(target=_reinit, daemon=True, name="TTS-Reinit").start()
    logging.info("TTS-related settings changed, starting TTS reinitialization.")


class SettingsDialog(QDialog):
    TTS_KEYS = {
        "tts_mode", "fish_api_key", "fish_reference_id", "fish_model", "tts_volume",
        "cosyvoice_reference_text", "tts_reference_wav",
        "cosyvoice_speed", "cosyvoice_dir", "openai_tts_api_key", "openai_tts_voice", "openai_tts_model",
        "openai_tts_custom_voice_id",
        "openai_compat_tts_base_url", "openai_compat_tts_api_key", "openai_compat_tts_model",
        "openai_compat_tts_voice", "openai_compat_tts_clone_mode", "openai_compat_tts_emotion_mode",
        "elevenlabs_api_key", "elevenlabs_voice_id", "elevenlabs_model_id",
        "edge_tts_voice", "edge_tts_rate",
        "tts_emotion_enabled",
    }
    LLM_KEYS = {
        "llm_provider", "llm_model",
        "llm_planner_provider", "llm_planner_model",
        "llm_execution_provider", "llm_execution_model",
        "llm_memory_extractor_provider", "llm_memory_extractor_model",
        "llm_router_enabled",
        "ollama_base_url", "custom_llm_providers",
        "groq_api_key", "openai_api_key", "anthropic_api_key", "mistral_api_key",
        "gemini_api_key", "openrouter_api_key", "nvidia_nim_api_key", "system_prompt", "personality",
        "scenario", "history_instruction", "response_verbosity",
        "personality_examples_en", "personality_examples_ja",
    }
    THEME_KEYS = {"ui_theme_preset", "ui_theme_scale", "ui_font_family"}
    CHARACTER_KEYS = {"character_scale", "character_ground_offset"}
    STT_KEYS = {
        "stt_provider", "whisper_model", "whisper_device", "whisper_compute_type",
        "wake_words", "stt_energy_threshold", "stt_dynamic_energy",
    }
    AGENT_KEYS = {"agent_timeout_seconds", "agent_dashboard_enabled", "audit_log_enabled", "mcp_server_enabled"}

    def __init__(self, parent=None, update_checker=None):
        super().__init__(parent)
        self.setWindowTitle(_("Ari Settings"))
        self.setMinimumWidth(600)
        self.setMinimumHeight(550)
        self.settings = ConfigManager.load_settings()
        self.update_checker = update_checker
        self.original_settings = dict(self.settings)
        self.changed_keys: set = set()
        self._editor_dialog: ThemeEditorDialog | None = None
        self._init_ui()

    # ── UI layout ────────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
        self.setStyleSheet(INPUT_STYLE)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)
        layout.addWidget(self.tabs)

        # 1. RP settings tab
        self.tabs.addTab(self._create_rp_tab(), _("RP Settings"))

        # 2. LLM settings tab
        self._llm_page = _LLMSettingsPage(self.settings, self)
        self.tabs.addTab(self._llm_page, _("AI Settings"))

        # 3. TTS settings tab
        self._tts_page = _TTSSettingsPage(self.settings, self)
        self.tabs.addTab(self._tts_page, _("TTS Settings"))

        # 4. Device settings tab
        self.tabs.addTab(self._create_device_tab(), _("Device settings"))

        # 5. Activity reactions tab
        self.tabs.addTab(self._create_scroll_area(self._create_activity_tab()), _("Activity reactions"))

        # 6. Extensions tab
        self._agent_page = _AgentSettingsPage(self.settings, self)
        self.tabs.addTab(self._create_scroll_area(self._agent_page), _("Agent"))

        try:
            from ui.settings_learning_page import _LearningSettingsPage

            self._learning_page = _LearningSettingsPage(self)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logging.warning("[SettingsDialog] Learning page load failed: %s", exc)
        else:
            self.tabs.addTab(self._create_scroll_area(self._learning_page), _("Learning"))

        # 7. Extensions tab
        self._plugin_page = _PluginSettingsPage(self)
        self.tabs.addTab(self._create_scroll_area(self._plugin_page), _("Extensions"))

        self._update_page = self._create_update_tab()
        self.tabs.addTab(self._create_scroll_area(self._update_page), _("About & updates"))

        build_info = get_build_info()
        commit = build_info["commit"][:7] or "—"
        version_label = QLabel(
            _("Version: {version} · Commit: {commit}").format(
                version=build_info["version"],
                commit=commit,
            )
        )
        layout.addWidget(version_label)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(_("Save"))
        save_btn.setMinimumHeight(45)
        save_btn.setMinimumWidth(120)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SUCCESS};
                color: white;
                font-weight: bold;
                font-size: {FONT_SIZE_NORMAL + 1}px;
                border-radius: 10px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: #219150;
            }}
            QPushButton:pressed {{
                background-color: #1a7a43;
            }}
        """)
        save_btn.clicked.connect(self._save)

        cancel_btn = QPushButton(_("Cancel"))
        cancel_btn.setMinimumHeight(45)
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setStyleSheet("""
            QPushButton {{
                background-color: #f1f3f5;
                color: #333;
                font-weight: normal;
                border-radius: 10px;
                padding: 0 15px;
            }}
            QPushButton:hover {{
                background-color: #e9ecef;
            }}
        """)
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    # ── Tab creation ───────────────────────────────────────────────────────────────

    @staticmethod
    def _create_scroll_area(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(scrollbar_style())
        scroll.setWidget(widget)
        return scroll

    def _create_rp_tab(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(10)

        group = QGroupBox(_("Character persona settings"))
        gvbox = QVBoxLayout(group)
        gvbox.setSpacing(8)

        rp_fields = [
            ("personality_input",  _("Personality:"),           "personality",         _("e.g. a kind and cute AI assistant")),
            ("examples_en_input",  _("Example English dialogue:"), "personality_examples_en", ""),
            ("examples_ja_input",  _("Example Japanese dialogue:"), "personality_examples_ja", ""),
            ("scenario_input",     _("Scenario:"),        "scenario",            _("e.g. a roleplay where she serves her master")),
            ("system_input",       _("System prompt:"), "system_prompt",       _("System instructions passed directly to the AI")),
            ("history_input",      _("Conversation guidance:"),       "history_instruction", _("Attitude when referring to earlier conversations")),
        ]

        for attr, label, key, ph in rp_fields:
            label_widget = QLabel(label)
            gvbox.addWidget(label_widget)
            edit = QTextEdit()
            edit.setPlainText(self.settings.get(key, ""))
            edit.setPlaceholderText(ph)
            edit.setMinimumHeight(
                56 if key in {"personality_examples_en", "personality_examples_ja"} else 90
            )
            setattr(self, attr, edit)
            gvbox.addWidget(edit, 1)

        gvbox.addWidget(QLabel(_("Response length:")))
        self.verbosity_combo = QComboBox()
        self.verbosity_combo.addItem(_("Concise (one or two sentences)"), "concise")
        self.verbosity_combo.addItem(_("Normal"), "normal")
        self.verbosity_combo.addItem(_("Chatty"), "chatty")
        self._set_combo(self.verbosity_combo, self.settings.get("response_verbosity", "concise"))
        gvbox.addWidget(self.verbosity_combo)

        vbox.addWidget(group, 1)
        return self._create_scroll_area(widget)

    def _create_activity_tab(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        group = QGroupBox(_("Activity reactions"))
        group_layout = QVBoxLayout(group)

        self.activity_idle_checkbox = QCheckBox(_("Away and return reactions"))
        self.activity_idle_checkbox.setChecked(
            bool(self.settings.get("activity_idle_reaction_enabled", True))
        )
        group_layout.addWidget(self.activity_idle_checkbox)

        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel(_("Away threshold (minutes)")))
        self.activity_away_threshold_spin = QSpinBox()
        self.activity_away_threshold_spin.setRange(1, 240)
        self.activity_away_threshold_spin.setValue(
            int(self.settings.get("activity_away_threshold_minutes", 5))
        )
        threshold_layout.addWidget(self.activity_away_threshold_spin)
        threshold_layout.addStretch()
        group_layout.addLayout(threshold_layout)

        self.activity_lock_checkbox = QCheckBox(_("Hide the character when the screen is locked"))
        self.activity_lock_checkbox.setChecked(
            bool(self.settings.get("activity_session_lock_reaction_enabled", True))
        )
        group_layout.addWidget(self.activity_lock_checkbox)

        self.activity_quiet_checkbox = QCheckBox(_("Do Not Disturb and fullscreen reactions"))
        self.activity_quiet_checkbox.setChecked(
            bool(self.settings.get("activity_quiet_reaction_enabled", True))
        )
        group_layout.addWidget(self.activity_quiet_checkbox)

        self.activity_quiet_bubble_checkbox = QCheckBox(
            _("Respond only with a speech bubble during Do Not Disturb")
        )
        self.activity_quiet_bubble_checkbox.setChecked(
            bool(self.settings.get("activity_quiet_bubble_only_enabled", False))
        )
        group_layout.addWidget(self.activity_quiet_bubble_checkbox)

        self.activity_app_checkbox = QCheckBox(_("App category reactions (off by default)"))
        self.activity_app_checkbox.setChecked(
            bool(self.settings.get("activity_app_category_reaction_enabled", False))
        )
        group_layout.addWidget(self.activity_app_checkbox)

        self.activity_auto_game_mode_checkbox = QCheckBox(
            _("Automatically apply game mode for games and video apps")
        )
        self.activity_auto_game_mode_checkbox.setChecked(
            bool(self.settings.get("activity_auto_game_mode_enabled", False))
        )
        group_layout.addWidget(self.activity_auto_game_mode_checkbox)

        self.activity_ide_long_use_checkbox = QCheckBox(
            _("Notify after 3 hours of continuous IDE use")
        )
        self.activity_ide_long_use_checkbox.setChecked(
            bool(self.settings.get("activity_ide_long_use_reaction_enabled", True))
        )
        group_layout.addWidget(self.activity_ide_long_use_checkbox)

        privacy_note = QLabel(_(
            "Activity information includes only the app category and elapsed time; window titles and process names are never sent."
        ))
        privacy_note.setWordWrap(True)
        group_layout.addWidget(privacy_note)
        group_layout.addWidget(QLabel(_("Wake detection is always paused while the screen is locked.")))
        vbox.addWidget(group)
        vbox.addStretch()
        return widget

    def _create_device_tab(self):
        widget = QWidget()
        vbox = QVBoxLayout(widget)

        group = QGroupBox(_("Audio device settings"))
        gvbox = QVBoxLayout(group)

        gvbox.addWidget(QLabel(_("Select the microphone input device:")))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem(_("System default microphone"), "")
        try:
            from VoiceCommand import list_microphone_names
            mics = list_microphone_names()
            for mic in mics:
                self.mic_combo.addItem(mic, mic)
        except Exception as e:
            logging.error(f"Error loading the microphone list: {e}")
        self._set_combo(self.mic_combo, self.settings.get("microphone", ""))
        gvbox.addWidget(self.mic_combo)

        gvbox.addSpacing(15)
        gvbox.addWidget(QLabel(_("Select the speaker output device:")))
        self.speaker_combo = QComboBox()
        self.speaker_combo.addItem(_("System default speaker"), "")
        try:
            from audio.audio_manager import list_output_devices
            out_devices = list_output_devices()
            seen_names = set()
            for dev in out_devices:
                name = dev["name"]
                if name not in seen_names:
                    self.speaker_combo.addItem(name, name)
                    seen_names.add(name)
        except Exception as e:
            logging.error(f"Error loading the output device list: {e}")
        self._set_combo(self.speaker_combo, self.settings.get("audio_output_device", ""))
        gvbox.addWidget(self.speaker_combo)

        stt_group = QGroupBox(_("speech recognition"))
        stt_vbox = QVBoxLayout(stt_group)
        stt_vbox.addWidget(create_muted_label(_("Configure the STT engine, Whisper settings, microphone sensitivity, and wake words.")))
        stt_btn = QPushButton(_("speech recognition Settings..."))
        stt_btn.clicked.connect(self._open_stt_settings)
        stt_vbox.addWidget(stt_btn)

        vbox.addWidget(stt_group)
        vbox.addWidget(group)

        self.audio_diagnostic_panel = AudioDiagnosticPanel(
            lambda: str(self.mic_combo.currentData() or ""),
            lambda: str(self.speaker_combo.currentData() or ""),
            self,
        )
        vbox.addWidget(self.audio_diagnostic_panel)

        vbox.addWidget(self._create_character_group())

        theme_group = QGroupBox(_("UI Theme Settings"))
        tvbox = QVBoxLayout(theme_group)

        tvbox.addWidget(QLabel(_("Theme preset:")))
        self.theme_preset_combo = QComboBox()
        for preset_key, preset_name in available_theme_presets():
            self.theme_preset_combo.addItem(preset_name, preset_key)
        self._set_combo(self.theme_preset_combo, self.settings.get("ui_theme_preset", "default"))
        tvbox.addWidget(self.theme_preset_combo)

        tvbox.addWidget(QLabel(_("Font scale (0.9 ~ 1.35):")))
        self.theme_scale_input = QLineEdit(str(self.settings.get("ui_theme_scale", 1.0)))
        self.theme_scale_input.setPlaceholderText(_("e.g. 1.0"))
        tvbox.addWidget(self.theme_scale_input)

        tvbox.addWidget(QLabel(_("Override the font family (optional):")))
        self.theme_font_input = QLineEdit(self.settings.get("ui_font_family", ""))
        self.theme_font_input.setPlaceholderText(_("Leave empty to use the theme default font"))
        tvbox.addWidget(self.theme_font_input)

        self.theme_preview_frame = QFrame()
        self.theme_preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(self.theme_preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        self.theme_preview_title = QLabel(_("Theme preview"))
        self.theme_preview_colors = QLabel("")
        self.theme_preview_colors.setWordWrap(True)
        preview_layout.addWidget(self.theme_preview_title)
        preview_layout.addWidget(self.theme_preview_colors)
        tvbox.addWidget(self.theme_preview_frame)

        preview_btn = QPushButton(_("Theme folder guide"))
        preview_btn.setStyleSheet(secondary_btn_style())
        preview_btn.clicked.connect(self._show_theme_hint)
        tvbox.addWidget(preview_btn)

        self.editor_toggle_btn = QPushButton(_("🎨 Edit the palette directly"))
        self.editor_toggle_btn.clicked.connect(self._toggle_theme_editor)
        tvbox.addWidget(self.editor_toggle_btn)

        self.theme_preset_combo.currentIndexChanged.connect(self._on_theme_preset_changed)
        self._refresh_theme_preview()

        vbox.addWidget(theme_group)

        lang_group = QGroupBox(_("Language Settings"))
        lvbox = QVBoxLayout(lang_group)
        lvbox.addWidget(QLabel(_("Interface language:")))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Korean", "ko")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Japanese", "ja")
        self._set_combo(self.lang_combo, get_language())
        lvbox.addWidget(self.lang_combo)
        vbox.addWidget(lang_group)

        log_btn = QPushButton(_("Open the log file folder"))
        log_btn.setStyleSheet(secondary_btn_style())
        log_btn.clicked.connect(self._open_log_folder)
        vbox.addWidget(log_btn)

        import_btn = QPushButton(_("Import data from an older version"))
        import_btn.setStyleSheet(secondary_btn_style())
        import_btn.clicked.connect(self._import_legacy_data)
        vbox.addWidget(import_btn)

        vbox.addStretch()
        return self._create_scroll_area(widget)

    def _create_update_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.update_check_enabled = QCheckBox(_("Automatically check for new versions"))
        update_enabled = self.settings.get("update_check_enabled", True)
        self.update_check_enabled.setChecked(
            update_enabled if isinstance(update_enabled, bool) else True
        )
        self.update_check_enabled.setEnabled(self.update_checker is not None)
        layout.addWidget(self.update_check_enabled)
        network_notice = QLabel(
            _("Automatic checks fetch only version information from GitHub and send no personally identifying information.")
        )
        network_notice.setWordWrap(True)
        layout.addWidget(network_notice)

        self.update_status_label = QLabel()
        self.update_status_label.setWordWrap(True)
        layout.addWidget(self.update_status_label)

        self.update_notes_link = QLabel()
        layout.addWidget(self.update_notes_link)

        buttons = QHBoxLayout()
        self.check_updates_button = QPushButton(_("Check now"))
        self.check_updates_button.setEnabled(self.update_checker is not None)
        self.check_updates_button.clicked.connect(self._check_updates_now)
        buttons.addWidget(self.check_updates_button)

        self.skip_update_button = QPushButton(_("Skip this version"))
        self.skip_update_button.clicked.connect(self._skip_update_version)
        buttons.addWidget(self.skip_update_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        self._refresh_update_status(get_update_status())
        if self.update_checker is not None:
            self.update_checker.status_changed.connect(self._refresh_update_status)
        return widget

    def _refresh_update_status(self, status=None):
        if not isinstance(status, dict):
            status = get_update_status()
        build_info = get_build_info()
        pending_version = status.get("pending_version")
        if isinstance(pending_version, str) and pending_version:
            minimum = status.get("pending_min_updatable_from")
            if (
                isinstance(minimum, str)
                and compare_versions(build_info["version"], minimum) < 0
            ):
                message = _("Ari {version} must be installed manually.")
            else:
                message = _("An update to Ari {version} is available.")
            self.update_status_label.setText(message.format(version=pending_version))
        elif status.get("skipped_version"):
            self.update_status_label.setText(_("This version was skipped."))
        elif status.get("last_checked_at"):
            self.update_status_label.setText(_("No new update is available."))
        else:
            self.update_status_label.setText(_("No update checks recorded yet."))
        self.skip_update_button.setEnabled(
            self.update_checker is not None
            and isinstance(pending_version, str)
            and bool(pending_version)
        )

        notes_url = status.get("pending_notes_url")
        if not isinstance(notes_url, str) or not notes_url:
            if build_info.get("channel") in {"stable", "beta"}:
                notes_url = (
                    "https://github.com/DO0OG/Ari-VoiceCommand/releases/tag/v"
                    f"{build_info['version']}"
                )
        try:
            parsed_notes_url = urlsplit(notes_url) if isinstance(notes_url, str) else None
        except ValueError:
            parsed_notes_url = None
        if (
            parsed_notes_url is not None
            and parsed_notes_url.scheme == "https"
            and parsed_notes_url.netloc == "github.com"
            and not parsed_notes_url.query
            and not parsed_notes_url.fragment
        ):
            self.update_notes_link.setText(
                f'<a href="{escape(notes_url, quote=True)}">{_("Changelog")}</a>'
            )
            self.update_notes_link.setOpenExternalLinks(True)
        else:
            self.update_notes_link.clear()

    def _check_updates_now(self):
        if self.update_checker is not None:
            self.update_status_label.setText(_("Checking for a new version."))
            self.update_checker.check_now()

    def _skip_update_version(self):
        if self.update_checker is not None:
            self.update_checker.skip_pending_version()
            self._refresh_update_status()

    # ── Character display settings ──────────────────────────────────────────────────────

    def _create_character_group(self) -> QGroupBox:
        """Adjust the character size and ground offset with sliders. The preview updates the moment they move."""
        group = QGroupBox(_("Character display settings"))
        layout = QVBoxLayout(group)
        layout.addWidget(create_muted_label(
            _("Moving the sliders updates Ari on screen immediately. Cancel restores the original values.")
        ))

        self._original_char_scale = float(self.settings.get("character_scale", 1.0))
        self._original_char_offset = int(self.settings.get("character_ground_offset", 4))

        # Size — showing a percentage is easier to read than a scale factor.
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(_("Size")))
        self.char_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.char_scale_slider.setRange(30, 300)
        self.char_scale_slider.setSingleStep(5)
        self.char_scale_slider.setPageStep(10)
        self.char_scale_slider.setValue(int(round(self._original_char_scale * 100)))
        size_row.addWidget(self.char_scale_slider, 1)
        self.char_scale_value = QLabel()
        self.char_scale_value.setMinimumWidth(56)
        size_row.addWidget(self.char_scale_value)
        layout.addLayout(size_row)
        layout.addWidget(create_muted_label(_("Small 30% ↔ large 300% (default 100%)")))

        # Ground offset — the label makes the sign convention explicit.
        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel(_("Ground offset")))
        self.char_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.char_offset_slider.setRange(-200, 200)
        self.char_offset_slider.setSingleStep(1)
        self.char_offset_slider.setPageStep(5)
        self.char_offset_slider.setValue(self._original_char_offset)
        offset_row.addWidget(self.char_offset_slider, 1)
        self.char_offset_value = QLabel()
        self.char_offset_value.setMinimumWidth(56)
        offset_row.addWidget(self.char_offset_value)
        layout.addLayout(offset_row)
        layout.addWidget(create_muted_label(
            _("Left moves up, right moves down. Adjust this when a custom image floats above the ground or sinks into it.")
        ))

        reset_btn = QPushButton(_("Reset to defaults"))
        reset_btn.setStyleSheet(secondary_btn_style())
        reset_btn.clicked.connect(self._reset_character_display)
        layout.addWidget(reset_btn)

        self.char_scale_slider.valueChanged.connect(self._on_character_display_changed)
        self.char_offset_slider.valueChanged.connect(self._on_character_display_changed)
        self._refresh_character_labels()
        return group

    def _refresh_character_labels(self):
        self.char_scale_value.setText(f"{self.char_scale_slider.value()}%")
        offset = self.char_offset_slider.value()
        self.char_offset_value.setText(f"{offset:+d}px")

    def _on_character_display_changed(self, _value=None):
        self._refresh_character_labels()
        self._apply_character_display(
            self.char_scale_slider.value() / 100.0,
            self.char_offset_slider.value(),
        )

    def _reset_character_display(self):
        defaults = ConfigManager.DEFAULT_SETTINGS
        self.char_scale_slider.setValue(int(round(float(defaults.get("character_scale", 1.0)) * 100)))
        self.char_offset_slider.setValue(int(defaults.get("character_ground_offset", 4)))

    @staticmethod
    def _apply_character_display(scale: float, ground_offset: int):
        """Apply the display settings to the running character widget. Silently skipped when there is no widget."""
        try:
            from core.VoiceCommand import _state
            widget = getattr(_state, "character_widget", None)
            if widget is not None and hasattr(widget, "apply_display_settings"):
                widget.apply_display_settings(scale=scale, ground_offset=ground_offset)
        except Exception as exc:
            logging.debug(f"Character Display settings reflection skipped: {exc}")

    def _restore_character_display(self):
        """Restore the preview when the window is closed without saving."""
        if hasattr(self, "_original_char_scale"):
            self._apply_character_display(self._original_char_scale, self._original_char_offset)

    def reject(self):
        self._restore_character_display()
        super().reject()

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _set_combo(combo: QComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    @staticmethod
    def _float(text: str, default: float) -> float:
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    def _open_log_folder(self):
        import os
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from core.resource_manager import ResourceManager
        log_dir = ResourceManager.get_writable_path("logs")
        os.makedirs(log_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    def _import_legacy_data(self):
        """Import .ari_runtime data from an older zip-based release without overwriting existing files."""
        from PySide6.QtWidgets import QFileDialog
        from core.resource_manager import ResourceManager
        path = QFileDialog.getExistingDirectory(
            self, _("Select the .ari_runtime folder from an older version"), "",
        )
        if not path:
            return
        title = _("Import data from an older version")
        try:
            copied = ResourceManager.import_legacy_runtime_data(path)
        except ValueError:
            QMessageBox.warning(self, title, _(
                "Could not find Ari data in the selected folder.\n"
                "Select the .ari_runtime folder, or the folder that contains it."
            ))
            return
        except OSError as exc:
            logging.warning("Previous version data import failed: %s", exc)
            QMessageBox.warning(self, title, _("Could not import the data: {error}", error=exc))
            return
        QMessageBox.information(self, title, _(
            "Imported {count} files. Existing files were left untouched.\n"
            "Restart Ari to apply the imported data.",
            count=copied,
        ))

    def _open_stt_settings(self):
        from ui.stt_settings_dialog import STTSettingsDialog
        dlg = STTSettingsDialog(self)
        if dlg.exec():
            self.original_settings.update(ConfigManager.load_settings())
            parent_widget = self.parent()
            refresh_voice_settings = getattr(
                parent_widget, "refresh_voice_input_settings", None
            )
            if callable(refresh_voice_settings):
                refresh_voice_settings()

    def _show_theme_hint(self):
        QMessageBox.information(
            self,
            _("Theme folder"),
            _("Theme JSON files can be edited directly in the folder below.\n\n{path}\n\nAfter saving, re-applying in the settings window updates the open UI immediately.").format(path=theme_dir()),
        )

    def _refresh_theme_preview(self):
        theme_key = self.theme_preset_combo.currentData() or "default"
        palette = load_theme_palette(theme_key)
        primary = palette.colors.get("primary", "#4a90e2")
        accent = palette.colors.get("accent", "#ff7b54")
        panel = palette.colors.get("bg_panel", "#f5f7fa")
        text = palette.colors.get("text_primary", "#333333")
        self.theme_preview_frame.setStyleSheet(
            f"QFrame {{ background: {panel}; border: 1px solid {primary}; border-radius: 10px; }}"
            f"QLabel {{ color: {text}; }}"
        )
        self.theme_preview_title.setText(_("{name} preview").format(name=palette.name))
        self.theme_preview_colors.setText(
            f"Primary {primary} | Accent {accent} | Font {palette.font_family}"
        )

    def _toggle_theme_editor(self):
        if self._editor_dialog is None:
            initial_palette = load_theme_palette(self.settings.get("ui_theme_preset", ""))
            self._editor_dialog = ThemeEditorDialog(initial_palette.colors, self)
            self._editor_dialog.palette_changed.connect(self._on_palette_changed)
            self._editor_dialog.theme_saved.connect(self._on_theme_saved)
        self._editor_dialog.show()
        self._editor_dialog.raise_()
        self._editor_dialog.activateWindow()

    def _on_palette_changed(self):
        if self._editor_dialog is None:
            return
        colors = self._editor_dialog.get_current_colors()
        primary = colors.get("primary", "#4a90e2")
        accent = colors.get("accent", "#ff7b54")
        self.theme_preview_colors.setText(f"Primary {primary} | Accent {accent} | Custom editing")

    def _on_theme_saved(self, theme_key: str):
        from ui.theme_runtime import apply_live_theme
        self.theme_preset_combo.blockSignals(True)
        self.theme_preset_combo.clear()
        for key, name in available_theme_presets():
            self.theme_preset_combo.addItem(name, key)
        idx = self.theme_preset_combo.findData(theme_key)
        if idx >= 0:
            self.theme_preset_combo.setCurrentIndex(idx)
        self.theme_preset_combo.blockSignals(False)
        try:
            apply_live_theme(character_widget=self.parent())
        except Exception as exc:
            logging.debug(f"Real-time theme apply failed: {exc}")
        self._refresh_theme_preview()

    def _on_theme_preset_changed(self, index: int):
        key = self.theme_preset_combo.currentData()
        palette = load_theme_palette(key)
        self._refresh_theme_preview()
        if self._editor_dialog is not None:
            self._editor_dialog.load_preset(palette.colors)

    # ── Save logic ─────────────────────────────────────────────────────────────

    def _save(self):
        new_settings = {
            # RP
            "personality": self.personality_input.toPlainText().strip(),
            "personality_examples_en": self.examples_en_input.toPlainText().strip(),
            "personality_examples_ja": self.examples_ja_input.toPlainText().strip(),
            "scenario": self.scenario_input.toPlainText().strip(),
            "system_prompt": self.system_input.toPlainText().strip(),
            "history_instruction": self.history_input.toPlainText().strip(),
            "response_verbosity": self.verbosity_combo.currentData(),

            # Device / Theme / Language
            "microphone": self.mic_combo.currentData(),
            "audio_output_device": self.speaker_combo.currentData(),
            "character_scale": round(self.char_scale_slider.value() / 100.0, 2),
            "character_ground_offset": self.char_offset_slider.value(),
            "ui_theme_preset": self.theme_preset_combo.currentData(),
            "ui_theme_scale": max(0.9, min(1.35, self._float(self.theme_scale_input.text(), 1.0))),
            "ui_font_family": self.theme_font_input.text().strip(),
            "language": self.lang_combo.currentData(),
            "update_check_enabled": self.update_check_enabled.isChecked(),

            # Activity reactions
            "activity_idle_reaction_enabled": self.activity_idle_checkbox.isChecked(),
            "activity_session_lock_reaction_enabled": self.activity_lock_checkbox.isChecked(),
            "activity_quiet_reaction_enabled": self.activity_quiet_checkbox.isChecked(),
            "activity_away_threshold_minutes": self.activity_away_threshold_spin.value(),
            "activity_app_category_reaction_enabled": self.activity_app_checkbox.isChecked(),
            "activity_quiet_bubble_only_enabled": self.activity_quiet_bubble_checkbox.isChecked(),
            "activity_auto_game_mode_enabled": self.activity_auto_game_mode_checkbox.isChecked(),
            "activity_ide_long_use_reaction_enabled": self.activity_ide_long_use_checkbox.isChecked(),
        }

        # Collect LLM / TTS values from each page
        new_settings.update(self._llm_page.get_values())
        new_settings.update(self._tts_page.get_values())
        new_settings.update(self._agent_page.get_values())

        self.changed_keys = {
            key for key, value in new_settings.items()
            if self.original_settings.get(key) != value
        }
        # Only the values changed in this window are layered onto the current settings. If another path saved after the window was opened,
        # Do not overwrite settings that were read late with the values captured when the window opened.
        merged_settings = {
            **ConfigManager.load_settings(),
            **{key: new_settings[key] for key in self.changed_keys},
        }
        if not ConfigManager.save_settings(merged_settings):
            self.changed_keys = set()
            QMessageBox.warning(self, _("settings.save_failed"), _("settings.secret_save_failed"))
            return
        try:
            refresh_activity_monitor()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            logging.debug("Activity settings apply skipped: %s", exc)

        if "update_check_enabled" in self.changed_keys and self.update_checker:
            self.update_checker.settings_changed()

        if "embedding_remote_enabled" in self.changed_keys:
            try:
                from agent.embedder import reset_embedder
                reset_embedder()
            except (ImportError, RuntimeError):
                logging.debug("Embedder settings apply skipped")

        if self.character_settings_changed():
            self._apply_character_display(
                merged_settings["character_scale"],
                merged_settings["character_ground_offset"],
            )

        if self.llm_settings_changed():
            import threading

            def _reload_llm_provider():
                try:
                    from agent.llm_provider import reload_llm_provider
                    reload_llm_provider()
                except Exception as exc:
                    logging.warning("LLM Provider reconfiguration failed: %s", exc)

            try:
                threading.Thread(
                    target=_reload_llm_provider,
                    daemon=True,
                    name="LLM-Reload",
                ).start()
            except Exception as exc:
                logging.warning("LLM Provider reconfiguration failed: %s", exc)

        if self.theme_settings_changed():
            QMessageBox.information(
                self,
                _("Theme Save"),
                _("Theme settings saved.\nThe open UI updates immediately; TTS and workers are not restarted."),
            )

        selected_lang = self.lang_combo.currentData()
        if selected_lang != get_language():
            set_language(selected_lang)

        self.accept()

    def tts_settings_changed(self) -> bool:
        return any(key in self.changed_keys for key in self.TTS_KEYS)

    def microphone_settings_changed(self) -> bool:
        return "microphone" in self.changed_keys

    def llm_settings_changed(self) -> bool:
        return any(key in self.LLM_KEYS or is_custom_secret_key(key) for key in self.changed_keys)

    def character_settings_changed(self) -> bool:
        return any(key in self.changed_keys for key in self.CHARACTER_KEYS)

    def theme_settings_changed(self) -> bool:
        return any(key in self.changed_keys for key in self.THEME_KEYS)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def done(self, result):
        # The Save, Cancel, and Close buttons all go through done(), so threads are cleaned up here.
        self._llm_page.cleanup_threads()
        self._agent_page.cleanup_threads()
        self._tts_page.cleanup_threads()
        self._plugin_page.cleanup_threads()
        super().done(result)
