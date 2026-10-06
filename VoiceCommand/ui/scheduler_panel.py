"""
Scheduler management panel (Scheduler Panel)
UI for listing, adding, deleting, and toggling scheduled tasks.
Shares its structure with the FloatingPanel base class.
"""
import logging
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from i18n.translator import _
from ui.common import (
    FloatingPanel, clear_layout, create_input_field,
    create_icon_button, show_temp_status,
)
from ui.theme import (
    FONT_KO, FONT_SIZE_NORMAL, FONT_SIZE_SMALL,
    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_DANGER, COLOR_MUTED,
    COLOR_BG_WHITE, COLOR_BORDER_CARD,
    scrollbar_thin_style, primary_btn_style,
    WINDOW_W_SCHEDULER, WINDOW_H_SCHEDULER,
)

logger = logging.getLogger(__name__)


class TaskRow(QFrame):
    """Widget for a single scheduled task row."""

    toggle_requested  = Signal(str)
    delete_requested  = Signal(str)
    run_now_requested = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task_id = task.task_id
        self._build_ui(task)

    def _build_ui(self, task) -> None:
        self.setStyleSheet(f"""
            QFrame {{ background: {COLOR_BG_WHITE}; border-radius: 10px;
                      border: 1px solid {COLOR_BORDER_CARD}; }}
            QFrame:hover {{ border: 1px solid {COLOR_PRIMARY}; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)

        # Name + action button row
        top = QHBoxLayout()
        display_name = task.name if getattr(task, "name", "") else task.goal[:30]
        name_lbl = QLabel(f"📋 {display_name}")
        name_lbl.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL, QFont.Bold))
        name_lbl.setWordWrap(True)
        name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        name_lbl.setMinimumWidth(0)
        top.addWidget(name_lbl)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)
        action_layout.addWidget(create_icon_button(
            "▶", _("Run now"), 28, COLOR_SUCCESS,
            lambda: self.run_now_requested.emit(self.task_id)
        ))
        toggle_color = COLOR_PRIMARY if task.enabled else COLOR_MUTED
        toggle_icon  = "⏸" if task.enabled else "▷"
        action_layout.addWidget(create_icon_button(
            toggle_icon, _("Enable/disable"), 28, toggle_color,
            lambda: self.toggle_requested.emit(self.task_id)
        ))
        action_layout.addWidget(create_icon_button(
            "✕", _("Delete"), 28, COLOR_DANGER,
            lambda: self.delete_requested.emit(self.task_id)
        ))
        top.addStretch()
        top.addLayout(action_layout)
        outer.addLayout(top)

        # Goal text (abbreviated)
        goal_lbl = QLabel(task.goal[:60] + ("…" if len(task.goal) > 60 else ""))
        goal_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
        goal_lbl.setStyleSheet("color: #555;")
        goal_lbl.setWordWrap(True)
        goal_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        goal_lbl.setMinimumWidth(0)
        outer.addWidget(goal_lbl)

        # Schedule + next run time
        try:
            next_str = datetime.fromisoformat(task.next_run).strftime("%m/%d %H:%M")
        except Exception:
            next_str = task.next_run
        info_color = COLOR_PRIMARY if task.enabled else COLOR_MUTED
        info_lbl = QLabel(_("🕐 {schedule}  →  next {next}").format(schedule=task.schedule_expr, next=next_str))
        info_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
        info_lbl.setStyleSheet(f"color: {info_color};")
        info_lbl.setWordWrap(True)
        info_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_lbl.setMinimumWidth(0)
        outer.addWidget(info_lbl)

        # Last run result
        if task.last_run:
            try:
                last_str = datetime.fromisoformat(task.last_run).strftime("%m/%d %H:%M")
            except Exception:
                last_str = task.last_run
            snippet = task.last_result[:50] + ("…" if len(task.last_result) > 50 else "")
            result_lbl = QLabel(_("✅ Last: {time}  |  {result}").format(time=last_str, result=snippet))
            result_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
            result_lbl.setStyleSheet(f"color: {COLOR_SUCCESS};")
            result_lbl.setWordWrap(True)
            result_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            result_lbl.setMinimumWidth(0)
            outer.addWidget(result_lbl)


class SchedulerPanel(FloatingPanel):
    """Scheduled task management panel."""

    def __init__(self, scheduler=None, parent=None):
        super().__init__("📅  Scheduled task management", WINDOW_W_SCHEDULER, WINDOW_H_SCHEDULER, parent)
        self._scheduler = scheduler
        self._build_content()
        self._connect_signals()
        self._refresh_list()

    # ── Content layout ───────────────────────────────────────────────────────────

    def _build_content(self) -> None:
        # Task list scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(scrollbar_thin_style())
        self._scroll = scroll

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.setSpacing(8)
        self._list_layout.setContentsMargins(12, 12, 12, 8)
        scroll.setWidget(self._list_widget)
        self.content_layout.addWidget(scroll)

        # Add-task form
        form = QFrame()
        form.setStyleSheet("""
            QFrame {{ background: white; border-top: 1px solid #eee;
                      border-bottom-left-radius: 14px;
                      border-bottom-right-radius: 14px; }}
        """)
        form_lay = QVBoxLayout(form)
        form_lay.setContentsMargins(14, 12, 14, 14)
        form_lay.setSpacing(8)

        add_title = QLabel(_("Add a new task"))
        add_title.setFont(QFont(FONT_KO, FONT_SIZE_SMALL, QFont.Bold))
        add_title.setStyleSheet(f"color: {COLOR_PRIMARY};")
        form_lay.addWidget(add_title)

        self._name_input  = create_input_field(_("Task name (e.g. News summary)"))
        self._goal_input  = create_input_field(_("Goal (e.g. summarize the latest news and save it)"))
        self._sched_input = create_input_field(_("Schedule (e.g. daily 09:00  /  Mondays 09:00  /  every 30 minutes)"))
        for w in (self._name_input, self._goal_input, self._sched_input):
            form_lay.addWidget(w)

        add_btn = QPushButton(_("+ Add task"))
        add_btn.setFixedHeight(36)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFont(QFont(FONT_KO, FONT_SIZE_SMALL, QFont.Bold))
        add_btn.setStyleSheet(primary_btn_style())
        add_btn.clicked.connect(self._on_add)
        form_lay.addWidget(add_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont(FONT_KO, FONT_SIZE_SMALL))
        self._status_lbl.setStyleSheet(f"color: {COLOR_MUTED};")
        form_lay.addWidget(self._status_lbl)

        self.content_layout.addWidget(form)

    # ── Signal connections ───────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        if not self._scheduler:
            return
        # ProactiveScheduler uses QTimer polling instead of Qt signals
        from PySide6.QtCore import QTimer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_list)
        self._refresh_timer.start(5000)  # Auto-refresh every 5 seconds

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        name  = self._name_input.text().strip()
        goal  = self._goal_input.text().strip()
        sched = self._sched_input.text().strip()
        if not (name and goal and sched):
            show_temp_status(self._status_lbl, _("⚠️ Please enter a name, a goal, and a schedule."))
            return
        if not self._scheduler:
            show_temp_status(self._status_lbl, _("⚠️ The scheduler is not connected."))
            return
        try:
            self._scheduler.add_task(name, goal, sched)
            for w in (self._name_input, self._goal_input, self._sched_input):
                w.clear()
            show_temp_status(self._status_lbl, _("✅ '{name}' registered").format(name=name))
        except Exception as e:
            show_temp_status(self._status_lbl, _("⚠️ Registration failed: {error}").format(error=e))

    def _refresh_list(self) -> None:
        clear_layout(self._list_layout)
        tasks = self._scheduler.list_tasks() if self._scheduler else []
        if not tasks:
            empty = QLabel(_("No scheduled tasks have been registered."))
            empty.setFont(QFont(FONT_KO, FONT_SIZE_NORMAL))
            empty.setStyleSheet(f"color: {COLOR_MUTED}; padding: 20px;")
            empty.setAlignment(Qt.AlignCenter)
            self._list_layout.addWidget(empty)
            return
        for task in sorted(tasks, key=lambda t: t.next_run):
            row = TaskRow(task)
            row.toggle_requested.connect(lambda tid: self._scheduler and self._scheduler.toggle_task(tid))
            row.delete_requested.connect(lambda tid: self._scheduler and self._scheduler.remove_task(tid))
            row.run_now_requested.connect(self._on_run_now)
            self._list_layout.addWidget(row)

    def _on_run_now(self, task_id: str) -> None:
        if self._scheduler and self._scheduler.run_task_now(task_id):
            show_temp_status(self._status_lbl, _("▶ Immediate run requested"))

    def refresh_theme(self) -> None:
        name_text = self._name_input.text() if hasattr(self, "_name_input") else ""
        goal_text = self._goal_input.text() if hasattr(self, "_goal_input") else ""
        sched_text = self._sched_input.text() if hasattr(self, "_sched_input") else ""
        self.refresh_shell_theme()
        clear_layout(self.content_layout)
        self._build_content()
        self._name_input.setText(name_text)
        self._goal_input.setText(goal_text)
        self._sched_input.setText(sched_text)
        self._refresh_list()
