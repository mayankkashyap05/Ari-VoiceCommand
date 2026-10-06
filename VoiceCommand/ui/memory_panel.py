"""
Memory visualization & editing panel (Memory Panel)
Shows the user information Ari remembers in real time and lets you edit or delete it directly.
Shares its structure with the FloatingPanel base class.

Tabs:
  Default info  — edit name, location, interests, notes
  Facts         — saved facts list (confidence, expiry, delete)
  Statistics    — command frequency, preferences, conversation topics
"""
import html
import logging
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from i18n.translator import _
from memory.fact_suggestions import get_fact_suggestion_store
from ui.common import (
    FloatingPanel, clear_layout, create_input_field,
    create_section_label, create_muted_label, show_temp_status,
)
from ui.theme import (
    FONT_KO, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
    COLOR_PRIMARY, COLOR_DANGER, COLOR_MUTED,
    COLOR_BG_WHITE, COLOR_BG_CHIP_PRIMARY, COLOR_BG_CHIP_WARN,
    scrollbar_thin_style, TAB_STYLE, primary_btn_style,
    WINDOW_W_MEMORY, WINDOW_H_MEMORY,
)

logger = logging.getLogger(__name__)


# ── Fact row ─────────────────────────────────────────────────────────────

class FactRow(QFrame):
    """Row that displays a single fact entry in the Facts tab."""

    delete_requested = Signal(str)  # key

    def __init__(self, key: str, entry: dict, parent=None):
        super().__init__(parent)
        self._key = key
        self.setStyleSheet(f"QFrame {{ background: {COLOR_BG_WHITE}; border-radius: 8px; border: 1px solid #eee; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)

        value = entry.get("value", "")
        conf  = int(entry.get("confidence", 0) * 100)
        exp   = entry.get("expires_at", "")[:10] if entry.get("expires_at") else "∞"

        if str(key) != str(value):
            key_lbl = QLabel(f"<b>{html.escape(str(key))}</b>")
            key_lbl.setTextFormat(Qt.RichText)
            key_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
            key_lbl.setMinimumWidth(110)
            lay.addWidget(key_lbl)

        val_lbl = QLabel(str(value)[:50])
        val_lbl.setTextFormat(Qt.PlainText)
        val_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
        val_lbl.setStyleSheet("color: #333;")
        lay.addWidget(val_lbl, 1)

        meta_lbl = QLabel(f"{conf}%  exp:{exp}")
        meta_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL - 1))
        meta_lbl.setStyleSheet(f"color: {COLOR_MUTED};")
        lay.addWidget(meta_lbl)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {COLOR_DANGER}; color: white; "
            f"border: none; border-radius: 11px; font-size: 10px; }}"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._key))
        lay.addWidget(del_btn)


# ── Tab: default info ─────────────────────────────────────────────────────────────

class _BioTab(QWidget):
    def __init__(self, ctx_manager, parent=None):
        super().__init__(parent)
        self._ctx = ctx_manager
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        bio = self._ctx.context.get("user_bio", {}) if self._ctx else {}
        self._fields: dict = {}

        for label, field_key, placeholder in [
            (_("Name"), "name", _("User name")),
            (_("Location"), "location", _("City or region")),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL, QFont.Bold))
            lbl.setFixedWidth(50)
            inp = create_input_field(placeholder)
            inp.setText(str(bio.get(field_key, "")))
            row.addWidget(lbl)
            row.addWidget(inp)
            lay.addLayout(row)
            self._fields[field_key] = inp

        lay.addWidget(create_section_label(_("Interests (comma-separated)")))
        self._interests = create_input_field(_("e.g. music, movies, reading"))
        self._interests.setText(", ".join(bio.get("interests", [])))
        lay.addWidget(self._interests)

        lay.addWidget(create_section_label(_("Notes (comma-separated)")))
        self._memos = create_input_field(_("e.g. likes cats, nocturnal"))
        self._memos.setText(", ".join(bio.get("memos", [])))
        lay.addWidget(self._memos)

        save_btn = QPushButton(_("Save"))
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL, QFont.Bold))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(primary_btn_style())
        save_btn.clicked.connect(self._save)
        lay.addWidget(save_btn)

        self._status = QLabel("")
        self._status.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
        self._status.setStyleSheet(f"color: {COLOR_MUTED};")
        lay.addWidget(self._status)

        self._pending_title = create_section_label(_("Information awaiting confirmation"))
        lay.addWidget(self._pending_title)
        self._pending_layout = QVBoxLayout()
        self._pending_layout.setSpacing(6)
        lay.addLayout(self._pending_layout)
        self._refresh_pending_bio()
        lay.addStretch()

    def _refresh_pending_bio(self) -> None:
        clear_layout(self._pending_layout)
        pending = self._ctx.context.get("pending_bio", []) if self._ctx else []
        self._pending_title.setVisible(bool(pending))
        for item in pending:
            field = item["field"]
            value = item["value"]
            field_label = {
                "name": _("Name"),
                "location": _("Location"),
                "interests": _("Interests"),
                "memos": _("Notes"),
            }.get(field, field)
            row = QHBoxLayout()
            pending_label = QLabel(
                _("{field}: {value}").format(field=field_label, value=value)
            )
            pending_label.setTextFormat(Qt.PlainText)
            row.addWidget(pending_label, 1)
            approve_btn = QPushButton(_("Approve"))
            approve_btn.clicked.connect(
                lambda checked=False, target=field, candidate=value:
                self._approve_pending_bio(target, candidate)
            )
            row.addWidget(approve_btn)
            self._pending_layout.addLayout(row)

    def _approve_pending_bio(self, field: str, value: str) -> None:
        if not self._ctx or not self._ctx.approve_pending_bio(field, value):
            return
        bio = self._ctx.context.get("user_bio", {})
        if field in self._fields:
            self._fields[field].setText(str(bio.get(field, "")))
        elif field == "interests":
            self._interests.setText(", ".join(bio.get(field, [])))
        elif field == "memos":
            self._memos.setText(", ".join(bio.get(field, [])))
        self._refresh_pending_bio()

    def _save(self) -> None:
        if not self._ctx:
            return
        try:
            for key, inp in self._fields.items():
                self._ctx.update_bio(key, inp.text().strip())
            interests = [s.strip() for s in self._interests.text().split(",") if s.strip()]
            memos     = [s.strip() for s in self._memos.text().split(",") if s.strip()]
            self._ctx.update_bio("interests", interests)
            self._ctx.update_bio("memos", memos)
            self._refresh_pending_bio()
            show_temp_status(self._status, _("✅ Save complete"))
        except Exception as e:
            show_temp_status(self._status, _("⚠️ Saving failed: {error}").format(error=e))

    def refresh(self) -> None:
        self._refresh_pending_bio()


# ── Tab: facts ─────────────────────────────────────────────────────────

class _FactsTab(QWidget):
    def __init__(self, ctx_manager, parent=None):
        super().__init__(parent)
        self._ctx = ctx_manager
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollbar_thin_style())

        self._container = QWidget()
        self._inner = QVBoxLayout(self._container)
        self._inner.setAlignment(Qt.AlignTop)
        self._inner.setSpacing(6)
        self._inner.setContentsMargins(12, 10, 12, 10)
        scroll.setWidget(self._container)
        lay.addWidget(scroll)

        self._populate()

    def _populate(self) -> None:
        clear_layout(self._inner)
        facts = self._ctx.context.get("facts", {}) if self._ctx else {}
        if not facts:
            self._inner.addWidget(create_muted_label(_("No facts saved yet.")))
            return
        sorted_facts = sorted(
            facts.items(),
            key=lambda kv: (kv[1].get("updated_at", ""), kv[1].get("confidence", 0)),
            reverse=True,
        )
        for key, entry in sorted_facts:
            row = FactRow(key, entry)
            row.delete_requested.connect(self._delete_fact)
            self._inner.addWidget(row)

    def _delete_fact(self, key: str) -> None:
        if not self._ctx:
            return
        dialog = QMessageBox(
            QMessageBox.Question,
            _("Delete fact"),
            _("Delete the fact '{key}'?").format(key=key),
            QMessageBox.Yes | QMessageBox.No,
            self,
        )
        dialog.setTextFormat(Qt.PlainText)
        dialog.setDefaultButton(QMessageBox.No)
        delete_conversations = QCheckBox(
            _("Also delete conversation history that mentions this fact"), dialog
        )
        dialog.setCheckBox(delete_conversations)
        if dialog.exec() == QMessageBox.Yes and self._ctx.delete_fact(
            key, delete_conversations=delete_conversations.isChecked()
        ):
            self._populate()

    def refresh(self) -> None:
        self._populate()


# ── Tab: memory suggestions ─────────────────────────────────────────────────────────────

class _SuggestionsTab(QWidget):
    def __init__(self, ctx_manager, parent=None):
        super().__init__(parent)
        self._ctx = ctx_manager
        try:
            self._store = get_fact_suggestion_store()
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning("Failed to load memory suggestions: %s", exc)
            self._store = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollbar_thin_style())
        self._container = QWidget()
        self._inner = QVBoxLayout(self._container)
        self._inner.setAlignment(Qt.AlignTop)
        self._inner.setSpacing(6)
        self._inner.setContentsMargins(12, 10, 12, 10)
        scroll.setWidget(self._container)
        lay.addWidget(scroll)
        self._populate()

    def _populate(self) -> None:
        clear_layout(self._inner)
        if not self._store:
            self._inner.addWidget(create_muted_label(_("Could not load the suggestions.")))
            return

        stats = self._store.get_stats()
        approved = stats["approved"]
        rejected = stats["rejected"]
        total = approved + rejected
        if total:
            rate = round(approved * 100 / total)
            summary = _("Approval rate {rate}% ({approved}/{total})").format(
                rate=rate, approved=approved, total=total
            )
        else:
            summary = _("No approve/reject records")
        self._inner.addWidget(create_muted_label(summary))

        suggestions = self._store.get_suggestions()
        if not suggestions:
            self._inner.addWidget(create_muted_label(_("No saved suggestions.")))
            return
        for suggestion in reversed(suggestions):
            self._add_suggestion(suggestion)

    def _add_suggestion(self, suggestion: dict) -> None:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {COLOR_BG_WHITE}; border-radius: 8px; "
            "border: 1px solid #eee; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        heading = (
            _("Preference: {key} = {value}")
            if suggestion["type"] == "preference"
            else _("Fact: {key} = {value}")
        )
        title = QLabel(heading.format(**suggestion))
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        evidence = QLabel(_("Evidence: {evidence}").format(evidence=suggestion["evidence"]))
        evidence.setTextFormat(Qt.PlainText)
        evidence.setWordWrap(True)
        evidence.setStyleSheet(f"color: {COLOR_MUTED};")
        layout.addWidget(evidence)

        actions = QHBoxLayout()
        actions.addStretch()
        approve_btn = QPushButton(_("Approve"))
        approve_btn.clicked.connect(
            lambda checked=False, item_id=suggestion["id"]: self._approve(item_id)
        )
        reject_btn = QPushButton(_("Reject"))
        reject_btn.clicked.connect(
            lambda checked=False, item_id=suggestion["id"]: self._reject(item_id)
        )
        actions.addWidget(approve_btn)
        actions.addWidget(reject_btn)
        layout.addLayout(actions)
        self._inner.addWidget(card)

    def _approve(self, suggestion_id: str) -> None:
        if not self._store or not self._ctx:
            return
        try:
            from memory.memory_manager import get_memory_manager

            manager = get_memory_manager()
            if manager.approve_fact_suggestion(suggestion_id, self._ctx):
                self._populate()
        except (OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            logger.warning("Failed to approve memory suggestion: %s", exc)

    def _reject(self, suggestion_id: str) -> None:
        if self._store and self._store.resolve(suggestion_id, approved=False):
            self._populate()

    def refresh(self) -> None:
        self._populate()


# ── Tab: statistics ──────────────────────────────────────────────────────────────────

class _StatsTab(QWidget):
    def __init__(self, ctx_manager, parent=None):
        super().__init__(parent)
        self._ctx = ctx_manager
        self._build()

    def _build(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(14)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        ctx = self._ctx.context if self._ctx else {}

        # Frequently used commands
        lay.addWidget(create_section_label(_("Frequently used commands")))
        cmd_freq = sorted(ctx.get("command_frequency", {}).items(), key=lambda x: x[1], reverse=True)[:8]
        if cmd_freq:
            grid = QGridLayout()
            grid.setSpacing(6)
            for i, (cmd, cnt) in enumerate(cmd_freq):
                chip = QLabel(f"{cmd}  ×{cnt}")
                chip.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
                chip.setAlignment(Qt.AlignCenter)
                chip.setStyleSheet(
                    f"QLabel {{ background: {COLOR_BG_CHIP_PRIMARY}; color: {COLOR_PRIMARY}; "
                    f"border-radius: 12px; padding: 4px 10px; }}"
                )
                grid.addWidget(chip, i // 3, i % 3)
            lay.addLayout(grid)
        else:
            lay.addWidget(create_muted_label(_("No records")))

        # Conversation topics
        lay.addWidget(create_section_label(_("Conversation topics")))
        topics = sorted(ctx.get("conversation_topics", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        if topics:
            topic_grid = QGridLayout()
            topic_grid.setHorizontalSpacing(6)
            topic_grid.setVerticalSpacing(6)
            for i, (topic, cnt) in enumerate(topics):
                chip = QLabel(f"#{topic}  {cnt}")
                chip.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
                chip.setStyleSheet(
                    f"QLabel {{ background: {COLOR_BG_CHIP_WARN}; color: #e67e22; "
                    f"border-radius: 12px; padding: 4px 10px; }}"
                )
                chip.setWordWrap(True)
                chip.setMinimumWidth(0)
                topic_grid.addWidget(chip, i // 2, i % 2)
            lay.addLayout(topic_grid)
        else:
            lay.addWidget(create_muted_label(_("No records")))

        # Preferences
        lay.addWidget(create_section_label(_("Preferences")))
        prefs = ctx.get("preferences", {})
        if prefs:
            for cat, vals in list(prefs.items())[:6]:
                if not vals:
                    continue
                top_val, top_cnt = max(vals.items(), key=lambda x: x[1])
                row_lbl = QLabel(f"<b>{cat}</b>: {top_val}  ×{top_cnt}")
                row_lbl.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
                row_lbl.setStyleSheet("color: #444;")
                lay.addWidget(row_lbl)
        else:
            lay.addWidget(create_muted_label(_("No records")))

        lay.addStretch()


# ── Main panel ─────────────────────────────────────────────────────────────────

class MemoryPanel(FloatingPanel):
    """Ari memory visualization & editing panel."""

    def __init__(self, ctx_manager=None, parent=None):
        super().__init__("🧠  Ari's memory", WINDOW_W_MEMORY, WINDOW_H_MEMORY, parent)
        self._ctx = ctx_manager
        self._build_content()

    def _build_content(self) -> None:
        tabs = QTabWidget()
        tabs.setStyleSheet(TAB_STYLE)
        self._tabs = tabs

        self._bio_tab   = _BioTab(self._ctx)
        self._facts_tab = _FactsTab(self._ctx)
        self._suggestions_tab = _SuggestionsTab(self._ctx)
        self._stats_tab = _StatsTab(self._ctx)

        tabs.addTab(self._bio_tab,   _("Default info"))
        tabs.addTab(self._facts_tab, _("Facts"))
        tabs.addTab(self._suggestions_tab, _("Suggestions"))
        tabs.addTab(self._stats_tab, _("Statistics"))

        self.content_layout.addWidget(tabs)

    def refresh(self) -> None:
        """Called when a data refresh is requested from outside."""
        self._bio_tab.refresh()
        self._facts_tab.refresh()
        self._suggestions_tab.refresh()

    def show_near(self, x: int, y: int) -> None:
        super().show_near(x, y)
        self.refresh()

    def refresh_theme(self) -> None:
        current_index = self._tabs.currentIndex() if hasattr(self, "_tabs") else 0
        self.refresh_shell_theme()
        clear_layout(self.content_layout)
        self._build_content()
        self._tabs.setCurrentIndex(current_index)
        self.refresh()
