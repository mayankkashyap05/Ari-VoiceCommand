"""
Shimeji-style character widget (optimized version)
"""
import json
import os
import secrets
import threading
import time
import sys
import logging
import ctypes
from queue import Queue
from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QApplication
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve, Signal, Slot, Property
from PySide6.QtGui import QPixmap, QImage, QCursor, QTransform, QAction
from ui.speech_bubble import SpeechBubble, register_fonts
from i18n.translator import _
from core.emotions import EMOTION_CATALOG, PET_EMOTIONS
from core.config_manager import ConfigManager
from core.mood_state import get_mood_state
from core import window_inspector
from core.constants import (
    GRAVITY, BOUNCE_Y, BOUNCE_X, FRICTION_GROUND, FRICTION_AIR,
)

_RNG = secrets.SystemRandom()
_BUBBLE_HISTORY_LOCK = threading.Lock()
_BUBBLE_HISTORY_QUEUE: Queue[str] = Queue()
_BUBBLE_HISTORY_WORKER_LOCK = threading.Lock()
_BUBBLE_HISTORY_WORKER: Optional[threading.Thread] = None


def _is_thinking_bubble_text(text: str) -> bool:
    normalized = (text or "").strip()
    thinking_texts = {
        _("thinking"),
        _("Thinking..."),
        "생각 중...",
        "Thinking...",
        "考え中...",
    }
    return normalized in thinking_texts


from ui.character_geometry import _is_geometry_animation_running, _sync_walk_animation_end_value


def _append_bubble_history(text: str) -> None:
    from core.resource_manager import ResourceManager
    from datetime import datetime

    path = ResourceManager.get_writable_path("bubble_history.json")
    try:
        with _BUBBLE_HISTORY_LOCK:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            else:
                data = {"history": []}
            history = data.setdefault("history", [])
            history.insert(
                0,
                {
                    "text": str(text),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                },
            )
            data["history"] = history[:50]
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        logging.debug("History save failed: %s", exc)


def _bubble_history_worker() -> None:
    while True:
        text = _BUBBLE_HISTORY_QUEUE.get()
        try:
            _append_bubble_history(text)
        finally:
            _BUBBLE_HISTORY_QUEUE.task_done()


def _ensure_bubble_history_worker() -> None:
    global _BUBBLE_HISTORY_WORKER
    with _BUBBLE_HISTORY_WORKER_LOCK:
        if _BUBBLE_HISTORY_WORKER is not None and _BUBBLE_HISTORY_WORKER.is_alive():
            return
        _BUBBLE_HISTORY_WORKER = threading.Thread(
            target=_bubble_history_worker,
            daemon=True,
            name="ari-bubble-hist",
        )
        _BUBBLE_HISTORY_WORKER.start()


def _enqueue_bubble_history(text: str) -> None:
    _ensure_bubble_history_worker()
    _BUBBLE_HISTORY_QUEUE.put(str(text))


def _load_random_custom_message() -> str:
    from core.resource_manager import ResourceManager

    path = ResourceManager.get_writable_path("custom_messages.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        messages = data.get("messages", [])
        return secrets.SystemRandom().choice(messages) if messages else ""
    except Exception as exc:
        logging.debug("Custom message load failed: %s", exc)
        return ""


def _invoke_level_up_callback(callback_obj: object) -> None:
    callback = getattr(callback_obj, "__call__", None)
    if callable(callback):
        callback()


from ui.image_cache import LRUCache


class CharacterWidget(QWidget):
    # Allowed range for the character display scale. The default assets are authored at display resolution, so 1.0 is the default.
    SCALE_MIN = 0.3
    SCALE_MAX = 3.0
    # Allowed range for the ground alignment offset (px). Lets users correct the bottom margin of custom images.
    GROUND_OFFSET_MIN = -200
    GROUND_OFFSET_MAX = 200
    GROUND_OFFSET_DEFAULT = 4

    _ANIMATION_SPECS = {
        "idle": 10,
        "walk": 10,
        "drag": 10,
        "fall": 10,
        "sit": 10,
        "climb": 6,
        "ceiling": 4,
        "sleep": 4,
        "surprised": 2,
    }
    # Thread-safe signal
    show_speech_bubble_signal = Signal(str, int)  # text, duration
    hide_speech_bubble_signal = Signal()
    change_emotion_signal = Signal(str)
    thinking_signal = Signal(bool)
    stream_token_signal = Signal(str)  # Streaming token delta

    def get_char_x(self):
        return self.x()

    def set_char_x(self, x):
        self.move(x, self.y())

    char_x = Property(int, get_char_x, set_char_x)

    def __init__(self, activity_monitor=None):
        super().__init__()
        self.activity_monitor = activity_monitor
        self.voice_thread = None
        register_fonts()  # Register the font on the main thread
        self._screen_geom_cache = None
        self._screen_geom_cache_time = 0
        self.dragging = False
        self.offset = QPoint()
        self.target_pos = QPoint() # Target position while dragging
        self._drag_start_global_pos = QPoint()
        self._drag_moved = False
        self._suppress_release_click = False
        self._voice_press_eligible = False
        self._voice_press_long = False
        self._character_ptt_active = False
        self._voice_press_stop_speaking = False
        self._listen_press_timer = QTimer(self)
        self._listen_press_timer.setSingleShot(True)
        self._listen_press_timer.setInterval(350)
        self._listen_press_timer.timeout.connect(self._begin_character_push_to_talk)
        self.current_animation = "idle"
        self._activity_away = False
        self._activity_locked = False
        self._activity_quiet = False
        self._activity_category_quiet = False
        self._activity_was_visible = False
        self._last_unlock_greeting_at = None
        self.frame_index = 0
        self.animations = {}
        self._character_packs = {}
        self._active_character_pack: Optional[str] = None
        self._base_images_dir = ""
        self.image_cache = LRUCache()
        self.image_head_top_cache: dict[str, int] = {}
        self.image_scale = 1.0
        self._current_head_top_offset = 0
        self.ground_offset = self.GROUND_OFFSET_DEFAULT
        self._load_display_settings()
        self.facing_right = True  # Character direction
        self.is_thinking = False   # Added: whether the character is thinking

        # Physics engine
        self.velocity_x = 0
        self.velocity_y = 0
        self.gravity = GRAVITY
        self.is_falling = False
        self.is_climbing = False # Add the wall-climbing state
        self.climbing_direction = 0 # -1: left wall, 1: right wall
        self.drag_history = []

        # Elasticity and friction coefficients
        self.bounce_y = BOUNCE_Y
        self.bounce_x = BOUNCE_X
        self.friction_ground = FRICTION_GROUND
        self.friction_air = FRICTION_AIR   

        # Mouse tracking
        self.mouse_tracker = QTimer(self)
        self.mouse_tracker.timeout.connect(self.track_mouse)
        self.mouse_tracker.start(100)
        self.mouse_tracking_enabled = False
        self._pet_hover_duration: float = 0.0
        self._prev_cursor_pos: QPoint = QPoint()
        self._pet_cooldown: float = 0.0
        self._is_being_petted: bool = False

        # Speech bubble
        self.speech_bubble = None

        # Speech bubble auto-hide timer
        self.bubble_hide_timer = QTimer(self)
        self.bubble_hide_timer.setSingleShot(True)
        self.bubble_hide_timer.timeout.connect(self._hide_speech_bubble_slot)

        # Shared tray menu (injected via set_tray_menu)
        self._tray_menu = None
        # Update checker to also pass into a settings window opened without a tray
        self._update_checker = None
        # Flag that lets plugins suppress the right-click context menu
        self._context_menu_enabled = True

        self._stream_buffer = ""

        # Signal connections
        self.show_speech_bubble_signal.connect(self._show_speech_bubble_slot)
        self.hide_speech_bubble_signal.connect(self._hide_speech_bubble_slot)
        self.change_emotion_signal.connect(self._change_emotion_slot)
        self.thinking_signal.connect(self.set_thinking)
        self.stream_token_signal.connect(self._on_stream_token_slot)

        # Hourly greeting timer
        self.greeting_timer = QTimer(self)
        self.greeting_timer.timeout.connect(self.time_based_greeting)
        self.greeting_timer.start(5000)
        self._sleepy_mode: bool = False
        self._sleepy_check_timer = QTimer(self)
        self._sleepy_check_timer.timeout.connect(self._update_sleepy_mode)
        self._sleepy_check_timer.start(60_000)
        self._yawn_timer = QTimer(self)
        self._yawn_timer.setSingleShot(True)
        self._yawn_timer.timeout.connect(self._do_yawn)

        # Window settings
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.BypassWindowManagerHint |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # The move animation state must be ready before the first update_frame().
        self.move_animation = None
        self._walk_target_y: Optional[int] = None
        # Screen the character is currently on (multi-monitor support)
        self._current_screen = QApplication.primaryScreen()

        # Animation loading
        # Label creation
        self.label = QLabel(self)
        self.load_animations()
        self.update_frame()

        # Animation timer (sped up: 100ms -> 70ms)
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.next_frame)
        self.animation_timer.start(70)

        # Behavior timer (every 3~10 seconds)
        self.behavior_timer = QTimer(self)
        self.behavior_timer.timeout.connect(self.random_behavior)
        self.start_behavior_timer()

        # Physics timer (optimized to 30 FPS)
        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self.update_physics)
        self.physics_timer.start(33)

        if self.activity_monitor is not None:
            self.activity_monitor.user_away.connect(self._on_user_away)
            self.activity_monitor.user_returned.connect(self._on_user_returned)
            self.activity_monitor.session_locked.connect(self._on_session_locked)
            self.activity_monitor.session_unlocked.connect(self._on_session_unlocked)
            self.activity_monitor.quiet_state_changed.connect(self._on_quiet_state_changed)
            self.activity_monitor.foreground_category_changed.connect(
                self._on_foreground_category_changed
            )
            self.activity_monitor.settings_refreshed.connect(
                self._sync_session_lock_visibility
            )
            self._activity_away = self.activity_monitor.is_user_away
            self._activity_locked = self.activity_monitor.session_is_locked
            self._activity_quiet = self.activity_monitor.quiet_reason != "none"
            self._activity_category_quiet = self.activity_monitor.foreground_category in (
                "game",
                "video",
            )
            self._refresh_activity_behavior()

        # Move to the bottom of the screen
        self.move_to_bottom()
        self.show()
        if self._activity_locked and ConfigManager.get(
            "activity_session_lock_reaction_enabled", True
        ):
            self._activity_was_visible = True
            self.hide()
        self._update_sleepy_mode()

        # Force HWND_TOPMOST on Windows
        if sys.platform == 'win32':
            self._enforce_topmost()
            # Periodically re-apply the topmost state (every 0.5 seconds)
            self.topmost_timer = QTimer(self)
            self.topmost_timer.timeout.connect(self._enforce_topmost)
            self.topmost_timer.start(500)

    @Slot(bool)
    def set_thinking(self, thinking: bool):
        """Set the thinking state (call on the main thread)"""
        self.is_thinking = thinking
        if thinking:
            self.set_animation("idle")
            # While thinking, the animation speed can be slowed or a visual effect applied
            self.animation_timer.setInterval(120)
            current_text = self.speech_bubble.text if self.speech_bubble else ""
            if not _is_thinking_bubble_text(current_text):
                self.say(_("thinking"), duration=0)
        else:
            self.animation_timer.setInterval(110 if self._sleepy_mode else 70)
            current_text = self.speech_bubble.text if self.speech_bubble else ""
            if _is_thinking_bubble_text(current_text):
                self._hide_speech_bubble_slot()

    def load_and_cache_image(self, path, flip=False, rotation=0):
        """Image loading, caching, and transforms (flip, rotate)"""
        cache_key = f"{path}_{'flip' if flip else 'normal'}_{rotation}"
        cached = self.image_cache.get(cache_key)
        if cached:
            return cached

        if not os.path.exists(path):
            return None

        image = QImage(path)
        if image.isNull():
            return None

        # Horizontal flip
        if flip:
            image = image.mirrored(True, False)
            
        # Rotation
        if rotation != 0:
            transform = QTransform().rotate(rotation)
            image = image.transformed(transform, Qt.SmoothTransformation)

        scaled_image = image.scaled(
            max(1, int(image.width() * self.image_scale)),
            max(1, int(image.height() * self.image_scale)),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        pixmap = QPixmap.fromImage(scaled_image)
        self.image_cache.put(cache_key, pixmap)
        self.image_head_top_cache[cache_key] = self._opaque_top(scaled_image)
        return pixmap

    @staticmethod
    def _opaque_top(image: QImage) -> int:
        """First row where opaque pixels begin. Used to attach the speech bubble right above the head."""
        if not image.hasAlphaChannel():
            return 0
        import numpy as np

        argb = image.convertToFormat(QImage.Format.Format_ARGB32)
        rows = np.frombuffer(argb.constBits(), np.uint8).reshape(argb.height(), argb.bytesPerLine())
        opaque_rows = np.flatnonzero(rows[:, 3:argb.width() * 4:4].any(axis=1))
        return int(opaque_rows[0]) if opaque_rows.size else 0

    @classmethod
    def _clamp(cls, value, low, high, default):
        """Clamp the setting to the allowed range. Invalid values fall back to the default."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if number != number:  # NaN
            return default
        return max(low, min(high, number))

    def _load_display_settings(self) -> tuple[float, int]:
        """Read the display scale and ground offset from the settings and apply them."""
        settings = ConfigManager.load_settings()
        self.image_scale = self._clamp(
            settings.get("character_scale", 1.0), self.SCALE_MIN, self.SCALE_MAX, 1.0
        )
        self.ground_offset = int(self._clamp(
            settings.get("character_ground_offset", self.GROUND_OFFSET_DEFAULT),
            self.GROUND_OFFSET_MIN, self.GROUND_OFFSET_MAX, self.GROUND_OFFSET_DEFAULT
        ))
        return self.image_scale, self.ground_offset

    def apply_display_settings(self, scale=None, ground_offset=None):
        """Re-apply the display scale and ground offset.

        When no values are passed, the saved settings are read. The live preview in the settings window
        passes the unsaved values directly.
        """
        if scale is None and ground_offset is None:
            self._load_display_settings()
        else:
            if scale is not None:
                self.image_scale = self._clamp(scale, self.SCALE_MIN, self.SCALE_MAX, self.image_scale)
            if ground_offset is not None:
                self.ground_offset = int(self._clamp(
                    ground_offset, self.GROUND_OFFSET_MIN, self.GROUND_OFFSET_MAX, self.ground_offset
                ))
        self.image_cache.cache.clear()
        self.image_head_top_cache.clear()
        self.update_frame()

    def load_animations(self):
        """Load animation frames"""
        from core.resource_manager import ResourceManager

        self._base_images_dir = ResourceManager.get_images_dir()
        self._reload_animation_set(self._active_images_dir())

    def _load_animation_frames(self, images_dir: str) -> dict[str, list[str]]:
        loaded = {}
        for anim_name, frame_count in self._ANIMATION_SPECS.items():
            frames = []
            for i in range(1, frame_count + 1):
                img_path = os.path.join(images_dir, f"{anim_name}{i}.png")
                if not os.path.exists(img_path):
                    continue
                pixmap = self.load_and_cache_image(img_path)
                if pixmap:
                    frames.append(img_path)
            if frames:
                loaded[anim_name] = frames
        return loaded

    def _active_images_dir(self) -> str:
        if self._active_character_pack:
            pack_dir = self._character_packs.get(self._active_character_pack)
            if pack_dir:
                return pack_dir
        return self._base_images_dir

    def _reload_animation_set(self, images_dir: str) -> bool:
        loaded = self._load_animation_frames(images_dir)
        if not loaded:
            return False
        self.image_cache.cache.clear()
        self.image_head_top_cache.clear()
        self.animations = loaded
        if not self.animations:
            logging.error("No character animations could be loaded. Please check the images path.")
        else:
            total_frames = sum(len(frames) for frames in self.animations.values())
            logging.info(f"Character Animation loading complete: {len(self.animations)}types / {total_frames}frames")
        if self.current_animation not in self.animations:
            self.current_animation = "idle" if "idle" in self.animations else next(iter(self.animations))
            self.frame_index = 0
        if hasattr(self, "label"):
            self.update_frame()
        return True

    def register_character_pack(self, pack_name: str, directory: str, activate: bool = False) -> bool:
        """Plugins register character image sets."""
        normalized_name = str(pack_name or "").strip()
        normalized_dir = os.path.abspath(str(directory or "").strip())
        if not normalized_name or not os.path.isdir(normalized_dir):
            return False
        if not self._load_animation_frames(normalized_dir):
            return False
        self._character_packs[normalized_name] = normalized_dir
        if activate:
            return self.activate_character_pack(normalized_name)
        return True

    def activate_character_pack(self, pack_name: Optional[str]) -> bool:
        """Activate a registered character image set. None restores the default set."""
        if not pack_name:
            self._active_character_pack = None
            return self._reload_animation_set(self._base_images_dir)
        normalized_name = str(pack_name).strip()
        directory = self._character_packs.get(normalized_name)
        if not directory:
            return False
        if not self._reload_animation_set(directory):
            return False
        self._active_character_pack = normalized_name
        return True

    def unregister_character_pack(self, pack_name: str) -> bool:
        """Remove a registered character image set."""
        normalized_name = str(pack_name or "").strip()
        if normalized_name not in self._character_packs:
            return False
        del self._character_packs[normalized_name]
        if self._active_character_pack == normalized_name:
            self._active_character_pack = None
            self._reload_animation_set(self._base_images_dir)
        return True

    def _get_virtual_desktop_rect(self) -> QRect:
        """Return the whole virtual desktop area covering every screen."""
        screens = QApplication.screens()
        if not screens:
            primary = QApplication.primaryScreen()
            return primary.geometry() if primary else QRect()

        left = min(screen.geometry().left() for screen in screens)
        top = min(screen.geometry().top() for screen in screens)
        right = max(screen.geometry().right() for screen in screens)
        bottom = max(screen.geometry().bottom() for screen in screens)
        return QRect(left, top, right - left + 1, bottom - top + 1)

    def _update_current_screen(self) -> None:
        """Update _current_screen to the screen containing the character center."""
        screens = QApplication.screens()
        if not screens:
            return

        center = self.geometry().center()
        for screen in screens:
            if screen.geometry().contains(center):
                if screen is not self._current_screen:
                    self._current_screen = screen
                    self._screen_geom_cache = None
                    self._screen_geom_cache_time = 0
                return

        nearest = min(
            screens,
            key=lambda screen: (
                (screen.geometry().center().x() - center.x()) ** 2
                + (screen.geometry().center().y() - center.y()) ** 2
            ),
        )
        if nearest is not self._current_screen:
            self._current_screen = nearest
            self._screen_geom_cache = None
            self._screen_geom_cache_time = 0

    def get_screen_geometry(self):
        """Detect whether the taskbar is hidden or covered and return the available screen information dynamically"""
        if (
            not hasattr(self, '_screen_geom_cache_time')
            or self._screen_geom_cache is None
            or time.time() - self._screen_geom_cache_time > 0.25
        ):
            screen = self._current_screen or QApplication.primaryScreen()
            if screen is None:
                return QRect()
            full_geom = screen.geometry()
            avail_geom = screen.availableGeometry()
            
            # The default is the available area (excluding the taskbar)
            self._screen_geom_cache = avail_geom

            if sys.platform == 'win32':
                try:
                    # 1. Check whether the foreground window is fullscreen (YouTube fullscreen, games, etc.)
                    fullscreen = self.activity_monitor is not None and (
                        self.activity_monitor.foreground_covers(
                            full_geom.width(), full_geom.height()
                        )
                    )
                    if fullscreen:
                        self._screen_geom_cache = full_geom
                        self._screen_geom_cache_time = time.time()
                        return self._screen_geom_cache

                    # 2. Check whether the taskbar itself is hidden (auto-hide mode, etc.)
                    taskbar_hidden = (
                        self.activity_monitor.taskbar_hidden
                        if self.activity_monitor is not None
                        else window_inspector.is_taskbar_hidden()
                    )
                    if taskbar_hidden:
                        self._screen_geom_cache = full_geom
                        self._screen_geom_cache_time = time.time()
                        return self._screen_geom_cache
                except Exception as exc:
                    logging.debug(f"Using screen state detection fallback: {exc}")
            
            # 3. General available-height check (when the system settings have no taskbar)
            if avail_geom.height() >= full_geom.height() - 10:
                self._screen_geom_cache = full_geom

            if self._screen_geom_cache is None:
                self._screen_geom_cache = avail_geom
            self._screen_geom_cache_time = time.time()
        return self._screen_geom_cache or QRect()

    def get_ground_y(self, height=None):
        """Compute the ground Y coordinate (reflects live screen information)"""
        if height is None:
            height = self.height()
        screen = self.get_screen_geometry()
        ground_bottom = screen.y() + screen.height()
        
        # In fullscreen (available area == full area) the offset is reduced so the character sits flush on the ground
        current_screen = self._current_screen or QApplication.primaryScreen()
        screen_full = current_screen.geometry() if current_screen else screen
        is_full_screen = screen.height() >= screen_full.height() - 10
        
        offset = self.ground_offset
        if is_full_screen:
            offset -= 4 # Lowered slightly when fullscreen
            
        return ground_bottom - height + offset

    def update_frame(self):
        """Update the current frame (optimized by minimizing layout calls)"""
        self._current_head_top_offset = 0
        if self.current_animation not in self.animations:
            return
            
        frames = self.animations[self.current_animation]
        if not frames:
            return
            
        frame_path = frames[self.frame_index % len(frames)]
        flip = not self.facing_right
        pixmap = self.load_and_cache_image(frame_path, flip=flip)
        
        if not pixmap:
            return

        cache_key = f"{frame_path}_{'flip' if flip else 'normal'}_0"
        self._current_head_top_offset = self.image_head_top_cache.get(cache_key, 0)

        # Check whether the size changed
        size_changed = (pixmap.size() != self.label.size())
        
        self.label.setPixmap(pixmap)
        if size_changed:
            self.label.adjustSize()
            self.setFixedSize(pixmap.width(), pixmap.height())
        
        # Position correction while on the ground (synced with update_physics)
        anim_running = _is_geometry_animation_running(self.move_animation)
        if not self.dragging and not self.is_falling and not self.is_climbing and not anim_running:
            target_y = self.get_ground_y(pixmap.height())
            screen = self.get_screen_geometry()
            margin = max(0, (pixmap.width() // 2) - 30)
            new_x = max(screen.x() - margin, min(self.x(), screen.x() + screen.width() - pixmap.width() + margin))
            
            # Prevent movement only when the values match exactly at integer precision
            if abs(self.x() - new_x) >= 1 or abs(self.y() - target_y) >= 1:
                self.move(int(new_x), int(target_y))

        if self.speech_bubble:
            self.speech_bubble.update_position()

    def head_top_offset(self) -> int:
        return self._current_head_top_offset

    def next_frame(self):
        """Advance to the next frame (avoids unnecessary calls)"""
        if self.current_animation in self.animations:
            frame_count = len(self.animations[self.current_animation])
            if frame_count > 0:
                self.frame_index = (self.frame_index + 1) % frame_count
                self.update_frame()

    def set_animation(self, animation_name):
        """Change the animation (ignores the same animation)"""
        if animation_name == self.current_animation:
            return
            
        if animation_name in self.animations:
            # Prevent forced animation changes while landing
            if getattr(self, '_is_landing', False) and animation_name not in ["sit", "idle"]:
                return
                
            self.current_animation = animation_name
            self.frame_index = 0
            self.update_frame()

    def start_behavior_timer(self):
        """Start the behavior timer at a random interval"""
        if self._activity_paused():
            self.behavior_timer.stop()
            return
        interval = _RNG.randint(3000, 10000)  # 3~10 seconds
        self.behavior_timer.start(interval)

    def _activity_paused(self) -> bool:
        return any((
            self._activity_away,
            self._activity_locked,
            self._activity_quiet,
            self._activity_category_quiet,
        ))

    def _refresh_activity_behavior(self) -> None:
        if self._activity_paused():
            self.behavior_timer.stop()
            if not self.dragging and not self.is_climbing and not self.is_falling:
                self.set_animation("idle")
        else:
            self.start_behavior_timer()

    @Slot()
    def _on_user_away(self) -> None:
        self._activity_away = True
        self._refresh_activity_behavior()

    @Slot(int)
    def _on_user_returned(self, away_seconds: int) -> None:
        self._activity_away = False
        self._refresh_activity_behavior()
        if away_seconds >= 30 * 60:
            animation = "surprised" if "surprised" in self.animations else "idle"
            self.set_animation(animation)
            QTimer.singleShot(
                1000,
                lambda: self.set_animation("idle")
                if self.current_animation == animation
                else None,
            )

    @Slot()
    def _on_session_locked(self) -> None:
        self._activity_locked = True
        self._sync_session_lock_visibility()
        self._refresh_activity_behavior()

    @Slot()
    def _on_session_unlocked(self) -> None:
        self._activity_locked = False
        self._sync_session_lock_visibility()
        self._refresh_activity_behavior()
        now = time.monotonic()
        if (
            self.isVisible()
            and not self._activity_paused()
            and (
                self._last_unlock_greeting_at is None
                or now - self._last_unlock_greeting_at >= 60
            )
        ):
            self._last_unlock_greeting_at = now
            self.say(_("The screen was unlocked."), duration=3000)

    @Slot()
    def _sync_session_lock_visibility(self) -> None:
        hide_when_locked = ConfigManager.get(
            "activity_session_lock_reaction_enabled", True
        )
        if self._activity_locked and hide_when_locked:
            if self.isVisible():
                self._activity_was_visible = True
                self.hide()
        elif self._activity_was_visible:
            self.show()
            self._activity_was_visible = False

    @Slot(str)
    def _on_quiet_state_changed(self, reason: str) -> None:
        self._activity_quiet = reason != "none"
        self._refresh_activity_behavior()

    @Slot(str)
    def _on_foreground_category_changed(self, category: str) -> None:
        self._activity_category_quiet = category in ("game", "video")
        self._refresh_activity_behavior()

    def _update_sleepy_mode(self):
        from datetime import datetime

        hour = datetime.now().hour
        should_be_sleepy = hour >= 22 or hour < 6
        if should_be_sleepy == self._sleepy_mode:
            return
        self._sleepy_mode = should_be_sleepy
        if should_be_sleepy:
            if not self.is_thinking:
                self.animation_timer.setInterval(110)
            self._schedule_yawn()
        else:
            if not self.is_thinking:
                self.animation_timer.setInterval(70)
            self._yawn_timer.stop()

    def _schedule_yawn(self):
        if not self._sleepy_mode:
            return
        delay_ms = _RNG.randint(3 * 60_000, 8 * 60_000)
        self._yawn_timer.start(delay_ms)

    def _do_yawn(self):
        from i18n.translator import _

        if (
            not self._sleepy_mode
            or self.dragging
            or self.is_climbing
            or self._activity_paused()
        ):
            if self._sleepy_mode and self._activity_paused():
                self._schedule_yawn()
            return
        yawn_messages = [
            _("Yaawn~... I am sleepy."),
            _("Hnn... my eyes are closing."),
            _("Nodding off..."),
            _("May I rest for a moment..."),
            _("Yaaawn... it is time for bed."),
        ]
        self.say(_RNG.choice(yawn_messages), duration=3000)
        self.set_animation("sleep")
        recover_ms = _RNG.randint(5000, 15000)
        QTimer.singleShot(
            recover_ms,
            lambda: self.set_animation("idle") if not self.dragging else None,
        )
        self._schedule_yawn()

    def _trigger_pet(self):
        from i18n.translator import _

        if self._pet_cooldown > 0 or self.dragging:
            return

        self._is_being_petted = True
        self._pet_cooldown = 3.0

        self.set_emotion(_RNG.choice(PET_EMOTIONS))
        pet_messages = [
            _("...All right."),
            _("That tickles."),
            _("Stop that."),
            _("Don't pet me."),
            _("Um... this is embarrassing."),
            _("That is enough."),
        ]
        # Pet reactions use original_say to avoid duplicate chat points
        _say = getattr(self, "_affinity_original_say", self.say)
        _say(_RNG.choice(pet_messages), duration=3000)

        affinity_mgr = getattr(self, "_affinity_manager", None)
        if affinity_mgr:
            leveled_up = affinity_mgr.add_points(3, "pet")
            if leveled_up:
                _invoke_level_up_callback(getattr(self, "_affinity_on_level_up", None))

    def random_behavior(self):
        """Random behavior (adds a chance of wall climbing)"""
        if self._activity_paused():
            return
        # If another task is already running, return without restarting the timer.
        # The timer restarts when the task finishes (on_walk_finished, stop_climbing, etc.).
        if self.dragging or self.is_climbing or getattr(self, '_is_landing', False) or _is_geometry_animation_running(self.move_animation):
            return

        vd = self._get_virtual_desktop_rect()
        margin = max(0, (self.width() // 2) - 30)
        # Wall contact detection (when more than 40% of the character width is outside)
        at_left_edge = self.x() <= vd.x() - margin + 10
        at_right_edge = self.x() >= vd.x() + vd.width() - self.width() + margin - 10

        # Attempt to climb (30% chance at the screen edge)
        if (at_left_edge or at_right_edge) and _RNG.random() < 0.3:
            self.climbing_direction = -1 if at_left_edge else 1
            self.smooth_climb()
            return

        if self._sleepy_mode:
            rand = _RNG.random()
            if rand < 0.5:
                behavior = "sleep"
            elif rand < 0.8:
                behavior = "sit"
            else:
                behavior = "idle"
            self.set_animation(behavior)
            if behavior in ("idle", "sit") and _RNG.random() < 0.2:
                message = _load_random_custom_message()
                if message:
                    self.say(message, duration=4000)
            self.start_behavior_timer()
            return

        # Adjusts only the share of normal behaviors slightly, based on mood.
        valence = 0.0
        mood_state = get_mood_state()
        if mood_state is not None:
            valence, _arousal = mood_state.values()
        weights = [0.4, 0.2, 0.15, 0.1, 0.15]
        if valence >= 0.2:
            weights = [0.3, 0.2, 0.25, 0.1, 0.15]
        elif valence <= -0.2:
            weights = [0.35, 0.3, 0.1, 0.1, 0.15]
        behavior = _RNG.choices(
            ("idle", "sit", "walk", "sleep", "ceiling"),
            weights=weights,
            k=1,
        )[0]
        if behavior == "ceiling" and not (at_left_edge or at_right_edge):
            behavior = "idle"

        self.set_animation(behavior)

        if behavior == "walk":
            self.smooth_walk(at_left_edge, at_right_edge)
        elif behavior == "ceiling":
            self.smooth_ceiling()
        else:
            if behavior in ("idle", "sit") and _RNG.random() < 0.2:
                message = _load_random_custom_message()
                if message:
                    self.say(message, duration=4000)
            # idle, sit, sleep, and similar states wait until the next timer tick
            self.start_behavior_timer()

    def smooth_ceiling(self):
        """Crawl up to the ceiling (top of the screen)"""
        self.is_climbing = True
        self.set_animation("climb")
        
        screen = self.get_screen_geometry()
        # Move to the top of the available area (opposite the taskbar)
        target_y = screen.y() - 5 # Slightly off-screen

        if self.move_animation:
            self.move_animation.stop()

        self._walk_target_y = None
        self.move_animation = QPropertyAnimation(self, b"geometry")
        # Time proportional to the distance from the current position to the top (max 5 seconds)
        distance = abs(self.y() - target_y)
        self.move_animation.setDuration(max(100, min(5000, distance * 10)))
        self.move_animation.setStartValue(self.geometry())
        self.move_animation.setEndValue(QRect(self.x(), target_y, self.width(), self.height()))
        self.move_animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        def on_ceiling_reached():
            self.set_animation("ceiling")
            # Hang on the ceiling for 2~5 seconds, then fall
            QTimer.singleShot(2000 + secrets.randbelow(3001), self.stop_climbing)
            
        self.move_animation.finished.connect(on_ceiling_reached)
        self.move_animation.start()

    def smooth_climb(self):
        """Climb up the wall"""
        self.is_climbing = True
        self.set_animation("climb")
        
        # Move up by about 20~50% of the screen height
        climb_height = _RNG.randint(200, 500)
        new_y = max(50, self.y() - climb_height)

        if self.move_animation:
            self.move_animation.stop()

        self._walk_target_y = None
        self.move_animation = QPropertyAnimation(self, b"geometry")
        self.move_animation.setDuration(climb_height * 10) # Speed control
        self.move_animation.setStartValue(self.geometry())
        self.move_animation.setEndValue(QRect(self.x(), new_y, self.width(), self.height()))
        self.move_animation.setEasingCurve(QEasingCurve.Linear)
        self.move_animation.finished.connect(self.stop_climbing)
        self.move_animation.start()

    def stop_climbing(self):
        """Stop climbing the wall and fall"""
        self.is_climbing = False
        self.is_falling = True
        self.set_animation("fall")
        self.start_behavior_timer()

    def smooth_walk(self, at_left_edge=False, at_right_edge=False):
        """Smooth, slow walking movement (includes moving away from a wall)"""
        margin = max(0, (self.width() // 2) - 30)

        # Decide the movement direction (forced the other way when against a wall)
        if at_left_edge:
            direction = 1
        elif at_right_edge:
            direction = -1
        else:
            direction = _RNG.choice([-1, 1])

        # Travel distance (150~400px)
        distance = _RNG.randint(150, 400)
        new_x = self.x() + (distance * direction)

        # Screen boundary check
        vd = self._get_virtual_desktop_rect()
        new_x = max(vd.x() - margin, min(new_x, vd.x() + vd.width() - self.width() + margin))
        
        # Keep the current ground height
        target_y = self.get_ground_y()
        self._walk_target_y = int(target_y)

        # Character direction setting and frame update
        self.facing_right = (new_x > self.x())
        self.update_frame()

        if self.move_animation:
            self.move_animation.stop()

        # Change the QPropertyAnimation target (char_x -> geometry)
        self.move_animation = QPropertyAnimation(self, b"geometry")
        self.move_animation.setDuration(4000) # Move slowly for 4 seconds
        self.move_animation.setStartValue(self.geometry())
        self.move_animation.setEndValue(QRect(int(new_x), int(target_y), self.width(), self.height()))
        self.move_animation.setEasingCurve(QEasingCurve.InOutQuad)
        
        def on_walk_finished():
            self._walk_target_y = None
            self.set_animation("idle")
            if not self.dragging and not self.is_climbing:
                self.start_behavior_timer()
        
        self.move_animation.finished.connect(on_walk_finished)
        self.move_animation.start()

    def _enforce_topmost(self):
        """Force always-on-top through the Win32 API (Windows only)"""
        if sys.platform != 'win32':
            return
        try:
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
        except Exception as exc:
            logging.debug(f"Topmost window force apply failed: {exc}")

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == 'win32':
            QTimer.singleShot(100, self._enforce_topmost)

    def move_to_bottom(self):
        """Move to the bottom of the screen"""
        screen = self.get_screen_geometry()
        x = _RNG.randint(screen.x(), max(screen.x(), screen.x() + screen.width() - self.width()))
        y = int(self.get_ground_y(self.height()))
        self.move(x, y)

    def mousePressEvent(self, event):
        """Mouse click"""
        if event.button() == Qt.LeftButton:
            affinity_mgr = getattr(self, "_affinity_manager", None)

            # Double-click detection
            if not hasattr(self, '_last_click'):
                self._last_click = 0
            now = time.time()
            if now - self._last_click < 0.3:
                from i18n.translator import _

                if affinity_mgr:
                    reaction = affinity_mgr.get_greeting()
                    # On a double-click press, show the reaction without incrementing
                    # (already incremented by +1 on the first click release)
                    _say = getattr(self, "_affinity_original_say", self.say)
                else:
                    reactions = [
                        _("Why?"),
                        _("What is it?"),
                        _("Huh?"),
                        _("What do you want."),
                        _("Just leave me alone."),
                    ]
                    reaction = _RNG.choice(reactions)
                    _say = self.say
                _say(reaction, duration=2000)
                self.set_animation("surprised")
                QTimer.singleShot(1000, lambda: self.set_animation("idle"))
                self._last_click = 0
                self._suppress_release_click = True
                return
            self._last_click = now

            self._voice_press_stop_speaking = False
            if self.voice_thread is not None:
                try:
                    from VoiceCommand import is_tts_playing
                    self._voice_press_stop_speaking = is_tts_playing()
                except (ImportError, AttributeError, RuntimeError) as exc:
                    logging.debug("TTS Play state OK skipped: %s", exc)
            self._voice_press_eligible = (
                self.voice_thread is not None
                and not self._voice_press_stop_speaking
            )
            self._voice_press_long = False
            self._character_ptt_active = False
            self._listen_press_timer.stop()
            if (
                self._voice_press_eligible
                and ConfigManager.get("voice_activation_mode", "push_to_talk")
                == "push_to_talk"
            ):
                self._listen_press_timer.start()

            self.dragging = True
            self._is_landing = False # Reset the landing flag while dragging
            self._drag_start_global_pos = event.globalPos()
            self._drag_moved = False
            self.offset = event.globalPos() - self.pos()
            self.set_animation("drag")

            self.velocity_x = 0
            self.velocity_y = 0
            self.drag_history = [(event.globalPos(), time.time())]

            if self.move_animation:
                self.move_animation.stop()
                self._walk_target_y = None

            # Reset is_climbing when dragging during wall or ceiling climbing
            # (move_animation.stop() does not emit the finished signal,
            # stop_climbing() is not called, so is_climbing stays True)
            if self.is_climbing:
                self.is_climbing = False

            self.physics_timer.stop()
            self.behavior_timer.stop()

    def mouseMoveEvent(self, event):
        """Mouse drag (immediate 1:1 movement and direction change)"""
        if self.dragging:
            moved_delta = event.globalPos() - self._drag_start_global_pos
            if abs(moved_delta.x()) >= 3 or abs(moved_delta.y()) >= 3:
                self._drag_moved = True
                self._voice_press_eligible = False
                self._listen_press_timer.stop()
                if self._character_ptt_active and self.voice_thread is not None:
                    self.voice_thread.release_listening()
                    self._character_ptt_active = False

            # Target position calculation (no lerp, moves instantly)
            nx = event.globalPos().x() - self.offset.x()
            ny = event.globalPos().y() - self.offset.y()
            
            # Screen boundary limits (half off-screen left and right, 0 at the top, ground at the bottom)
            vd = self._get_virtual_desktop_rect()
            margin = max(0, (self.width() // 2) - 30)
            nx = max(vd.x() - margin, min(nx, vd.x() + vd.width() - self.width() + margin))
            ny = max(vd.y(), min(ny, vd.y() + vd.height() - self.height() + 25))

            # Direction detection and frame update
            dx = nx - self.x()
            if abs(dx) > 2: # Minimum travel distance threshold
                self.facing_right = (dx > 0)
                self.update_frame()

            self.move(nx, ny)
            
            # History recording
            self.drag_history.append((event.globalPos(), time.time()))
            if len(self.drag_history) > 5:
                self.drag_history.pop(0)

            # Speech bubble position update
            if self.speech_bubble:
                self.speech_bubble.update_position()

    def mouseReleaseEvent(self, event):
        """Mouse release"""
        if event.button() == Qt.LeftButton:
            should_activate_voice = (
                self.dragging
                and not self._drag_moved
                and not self._suppress_release_click
            )
            self._listen_press_timer.stop()
            if self._character_ptt_active and self.voice_thread is not None:
                self.voice_thread.release_listening()
            elif (
                should_activate_voice
                and not self._voice_press_long
                and self.voice_thread is not None
            ):
                if self._voice_press_stop_speaking:
                    from VoiceCommand import stop_speaking
                    stop_speaking()
                else:
                    self.voice_thread.request_listening()
            self._voice_press_eligible = False
            self._character_ptt_active = False
            self._voice_press_stop_speaking = False

            affinity_mgr = getattr(self, "_affinity_manager", None)
            on_level_up = getattr(self, "_affinity_on_level_up", None)
            should_reward_click = self.dragging and not self._drag_moved and not self._suppress_release_click

            self.dragging = False
            self._suppress_release_click = False
            self._update_current_screen()

            # Restart the timer
            self.animation_timer.start(70)
            self.physics_timer.start(33)
            self.start_behavior_timer()

            if should_reward_click and affinity_mgr:
                leveled_up = affinity_mgr.add_points(1, "click")
                if leveled_up:
                    _invoke_level_up_callback(on_level_up)

            # Throw velocity calculation (factor 0.02, slightly damped for stability)
            current_time = time.time()
            valid_history = [h for h in self.drag_history if current_time - h[1] < 0.2]
            
            if len(valid_history) >= 2:
                old_pos, old_time = valid_history[0]
                curr_pos, curr_time = valid_history[-1]
                dt = curr_time - old_time
                if dt > 0:
                    vx = (curr_pos.x() - old_pos.x()) / dt * 0.02
                    vy = (curr_pos.y() - old_pos.y()) / dt * 0.02
                    self.velocity_x = max(-25, min(25, vx))
                    self.velocity_y = max(-25, min(25, vy))
            else:
                self.velocity_x = 0
                self.velocity_y = 0

            self.is_falling = True
            self.set_animation("fall")
            # Return to idle a while after release (avoids a forced landing animation)
            QTimer.singleShot(800, lambda: self.set_animation("idle") if not self.dragging and not self.is_falling and not getattr(self, '_is_landing', False) else None)

    def set_text_interface(self, text_interface):
        """Text interface reference settings"""
        self.text_interface = text_interface

    def apply_microphone_settings(self):
        """Apply a saved microphone selection on the voice worker thread."""
        if self.voice_thread is None:
            logging.warning("speech recognition thread unavailable, cannot Microphone apply settings.")
            return False

        microphone = ConfigManager.load_settings().get("microphone", "")
        self.voice_thread.set_microphone(microphone)
        return True

    def open_text_interface(self):
        """Open the text chat window (relative to the character position)"""
        if hasattr(self, 'text_interface') and self.text_interface:
            self.text_interface.show_near(self.x(), self.y(), self.width(), self.height())

    def set_tray_menu(self, menu) -> None:
        """Share the tray icon menu. A later right-click shows that menu."""
        self._tray_menu = menu

    def set_update_checker(self, update_checker) -> None:
        """Keep the update checker to pass to the settings window."""
        self._update_checker = update_checker

    def set_context_menu_enabled(self, enabled: bool) -> None:
        """Configure whether the character right-click context menu is shown.
        Plugins can suppress it with context.set_character_menu_enabled(False)."""
        self._context_menu_enabled = bool(enabled)

    def contextMenuEvent(self, event):
        """Right-click menu — shares and shows the injected tray menu when one is available."""
        if not self._context_menu_enabled:
            return

        if self._tray_menu is not None:
            # The aboutToShow signal refreshes the checkbox state and theme automatically
            self._tray_menu.exec(event.globalPos())
            return

        # Fallback menu when running standalone without a tray
        from VoiceCommand import learning_mode, is_game_mode, enable_game_mode, disable_game_mode
        from ui import theme as theme_module
        menu = QMenu(self)
        menu.setStyleSheet(theme_module.MENU_STYLE)

        chat_action = QAction(_("💬 Text chat"), self)
        chat_action.triggered.connect(self.open_text_interface)
        menu.addAction(chat_action)

        menu.addSeparator()

        settings_action = QAction(_("Settings"), self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        game_action = QAction(_("🎮 Game mode (save GPU)"), self)
        game_action.setCheckable(True)
        game_action.setChecked(is_game_mode())
        def toggle_game_mode(checked):
            if checked:
                enable_game_mode()
                self.say(_("Game mode on. GPU memory released."), duration=3000)
            else:
                disable_game_mode()
                self.say(_("Game mode off. Restoring TTS..."), duration=3000)
        game_action.triggered.connect(toggle_game_mode)
        menu.addAction(game_action)

        smart_action = QAction(_("Smart assistant mode"), self)
        smart_action.setCheckable(True)
        smart_action.setChecked(learning_mode['enabled'])
        def toggle_smart_mode(checked):
            learning_mode['enabled'] = checked
            status = _("Enable") if checked else _("Disable")
            self.say(_("Smart assistant mode has been {status}.").format(status=status), duration=3000)
        smart_action.triggered.connect(toggle_smart_mode)
        menu.addAction(smart_action)

        mouse_action = QAction(_("Mouse reactions"), self)
        mouse_action.setCheckable(True)
        mouse_action.setChecked(self.mouse_tracking_enabled)
        mouse_action.triggered.connect(self.toggle_mouse_tracking)
        menu.addAction(mouse_action)

        hide_action = QAction(_("Hide character"), self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.addSeparator()

        exit_action = QAction(_("Quit"), self)
        exit_action.triggered.connect(self.exit_program)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())

    def toggle_mouse_tracking(self):
        """Toggle mouse tracking"""
        self.mouse_tracking_enabled = not self.mouse_tracking_enabled

    def open_settings(self):
        """Open the settings window"""
        from ui.settings_dialog import (
            SettingsDialog, reinitialize_tts_async, should_apply_microphone,
        )
        dialog = SettingsDialog(self, update_checker=self._update_checker)
        if dialog.exec():
            if should_apply_microphone(dialog, self):
                self.apply_microphone_settings()
            if dialog.tts_settings_changed():
                reinitialize_tts_async()
            if dialog.theme_settings_changed():
                try:
                    from ui.theme_runtime import apply_live_theme
                    apply_live_theme(character_widget=self)
                except Exception as e:
                    logging.error(f"Real-time theme reflection failed: {e}")

    def _begin_character_push_to_talk(self):
        if not self._voice_press_eligible or self.voice_thread is None:
            return
        self._voice_press_long = True
        self._character_ptt_active = self.voice_thread.request_listening(
            push_to_talk=True
        )

    def refresh_voice_input_settings(self):
        """Apply the voice settings to the running input path."""
        try:
            if self.voice_thread is not None:
                self.voice_thread.refresh_voice_settings()
            hotkey_filter = getattr(self, "voice_hotkey_filter", None)
            if hotkey_filter is not None:
                hotkey_filter.configure()
        except (AttributeError, OSError, RuntimeError, ValueError) as exc:
            logging.warning("Applying the voice input settings failed: %s", exc)

    def refresh_theme(self):
        """Refresh the character-related UI after a theme change."""
        if self.speech_bubble:
            text = self.speech_bubble.text
            self._hide_speech_bubble_slot()
            self._show_speech_bubble_slot(text, 5000)

    def exit_program(self):
        """Application exit requested"""
        logging.info("Character Exit request via menu")
        app = QApplication.instance()
        if app:
            app.quit()

    def _schedule_finish_landing(self, delay_ms: int) -> None:
        def _finish_landing_animation():
            self._is_landing = False
            if not self.is_falling and not self.dragging:
                self.set_animation("idle")
                self.start_behavior_timer()

        QTimer.singleShot(delay_ms, _finish_landing_animation)

    def update_physics(self):
        """Physics engine (stronger landing detection and motion sync)"""
        if self.dragging or self.is_climbing:
            return

        self._update_current_screen()
        target_y = self.get_ground_y()
        current_y = self.y()
        moved = False
        anim_running = _is_geometry_animation_running(self.move_animation)

        if anim_running and self._walk_target_y is not None:
            self._walk_target_y = _sync_walk_animation_end_value(
                self.move_animation,
                self._walk_target_y,
                int(target_y),
            )

        lock_vertical_position = anim_running and self._walk_target_y is not None and self.velocity_y == 0

        # Gravity application logic (threshold reduced to 10px for more accurate snapping)
        if not lock_vertical_position and (current_y < target_y - 10 or self.velocity_y < 0):
            self.is_falling = True
            self.velocity_y = min(self.velocity_y + self.gravity, 20)
            new_y = current_y + self.velocity_y

            # Landing detection
            if new_y >= target_y:
                new_y = target_y
                # Save the velocity right before landing
                impact_vel = abs(self.velocity_y)
                
                if impact_vel > 3:
                    self.velocity_y *= self.bounce_y
                else:
                    self.velocity_y = 0
                    self.is_falling = False
                    
                    # Smart landing animation
                    if self.current_animation == "fall":
                        if impact_vel > 8: # Strong fall threshold
                            self._is_landing = True
                            self.set_animation("sit")
                            self._schedule_finish_landing(600)
                        else: # Small drop
                            self.set_animation("idle")
                            self.start_behavior_timer()

            if int(new_y) != current_y:
                self.move(self.x(), int(new_y))
                moved = True
                self._update_current_screen()

        else:
            # When resting stably on the ground (snap)
            if not anim_running:
                if abs(current_y - target_y) > 0.5:
                    self.move(self.x(), int(target_y))
                    moved = True

                if self.is_falling or self.current_animation == "fall":
                    self.is_falling = False
                    self._is_landing = True
                    self.set_animation("sit")
                    self._schedule_finish_landing(700)
            else:
                self.is_falling = False
            
            self.velocity_y = 0

        # Horizontal movement (throw and friction)
        if self.velocity_x != 0:
            new_x = int(self.x() + self.velocity_x)
            margin = max(0, (self.width() // 2) - 30)
            vd = self._get_virtual_desktop_rect()
            
            # Wall collision and bounce (allows up to half of the character off-screen)
            if new_x < vd.x() - margin:
                new_x = vd.x() - margin
                self.velocity_x *= self.bounce_x
            elif new_x > vd.x() + vd.width() - self.width() + margin:
                new_x = vd.x() + vd.width() - self.width() + margin
                self.velocity_x *= self.bounce_x

            if new_x != self.x():
                self.move(new_x, self.y())
                moved = True
                self._update_current_screen()

            # Apply friction
            if self.is_falling:
                self.velocity_x *= self.friction_air
            else:
                self.velocity_x *= self.friction_ground
                
            if abs(self.velocity_x) < 0.5:
                self.velocity_x = 0

        if self._pet_cooldown > 0:
            self._pet_cooldown -= 0.033
            if self._pet_cooldown <= 0:
                self._pet_cooldown = 0.0
                self._is_being_petted = False

        # Speech bubble position update
        if moved and self.speech_bubble:
            self.speech_bubble.update_position()

    def track_mouse(self):
        """Mouse reaction — curious or fleeing behavior depending on distance"""
        if self.dragging or self.is_climbing:
            return

        cursor_pos = QCursor.pos()
        char_rect = self.geometry()

        if char_rect.contains(cursor_pos):
            dx = cursor_pos.x() - self._prev_cursor_pos.x()
            dy = cursor_pos.y() - self._prev_cursor_pos.y()
            speed = ((dx * dx + dy * dy) ** 0.5) / 0.1 if self._prev_cursor_pos != QPoint() else 0.0

            if speed < 30:
                self._pet_hover_duration += 0.1
                if self._pet_hover_duration >= 1.5 and self._pet_cooldown <= 0:
                    self._trigger_pet()
                    self._pet_hover_duration = 0.0
            else:
                self._pet_hover_duration = 0.0

            self._prev_cursor_pos = cursor_pos
            return

        self._pet_hover_duration = 0.0
        self._prev_cursor_pos = cursor_pos
        if not self.mouse_tracking_enabled:
            return

        char_center = self.geometry().center()

        dx = cursor_pos.x() - char_center.x()
        distance = abs(dx)

        margin = max(0, (self.width() // 2) - 30)
        vd = self._get_virtual_desktop_rect()
        at_edge = self.x() <= vd.x() - margin + 5 or self.x() >= vd.x() + vd.width() - self.width() + margin - 5

        if distance < 80:
            # Very close — startled, runs away (faster)
            if not getattr(self, '_mouse_scared', False):
                self._mouse_scared = True
                self.set_animation("surprised")
                QTimer.singleShot(400, lambda: self.set_animation("walk") if self.mouse_tracking_enabled else None)

            if not at_edge:
                # Apply velocity in the opposite direction (delegated to the physics engine)
                self.velocity_x = -8 if dx > 0 else 8
                self.facing_right = (self.velocity_x > 0)
            else:
                # Cornered against a wall — escape by climbing
                if not self.is_climbing:
                    self.smooth_climb()

        elif distance < 200:
            # Medium distance — walks away slowly
            self._mouse_scared = False
            if not at_edge and not self.is_falling:
                self.velocity_x = -3 if dx > 0 else 3
                self.facing_right = (self.velocity_x > 0)
                self.set_animation("walk")

        else:
            # Far away — returns to normal
            self._mouse_scared = False

    def set_emotion(self, emotion):
        """Emotion settings (called externally - thread safe)"""
        self.change_emotion_signal.emit(emotion)

    @Slot(str)
    def _change_emotion_slot(self, emotion):
        """Actual emotion expression handling (main thread)"""
        logging.debug(f"Character Emotion expression: {emotion}")
        
        details = EMOTION_CATALOG.get(emotion)
        if not details:
            return
        mood_state = get_mood_state()
        valence = 0.0
        if mood_state is not None:
            valence, _arousal = mood_state.values()
        animations = details["animations"]
        weights = [
            1 + max(0.0, valence) * 3 if animation == "walk" else
            1 + max(0.0, -valence) * 3 if animation == "sit" else 1
            for animation in animations
        ]
        self.set_animation(_RNG.choices(animations, weights=weights, k=1)[0])

        if (
            details.get("jump")
            and not self.is_falling
            and (mood_state is None or mood_state.claim_big_motion())
        ):
            self.velocity_y = -8
            self.is_falling = True

    def say(self, text, duration=5000):
        """Show the speech bubble (called externally - thread safe)"""
        # Delivered via a signal (safe from any thread)
        self.show_speech_bubble_signal.emit(text, duration)

    @Slot(str)
    def _on_stream_token_slot(self, delta: str) -> None:
        """Accumulate and update the speech bubble text as streaming tokens arrive."""
        self._stream_buffer += delta
        if self.speech_bubble and self.speech_bubble.isVisible():
            self.speech_bubble.update_text(self._stream_buffer)
            if self.bubble_hide_timer.isActive():
                self.bubble_hide_timer.start()
        else:
            # Slots routed through signals clear the buffer, so display directly while keeping the buffer intact
            self._present_speech_bubble(self._stream_buffer, 0)

    def _reset_stream_buffer(self) -> None:
        """Clear the buffer after streaming completes."""
        self._stream_buffer = ""

    @Slot(str, int)
    def _show_speech_bubble_slot(self, text, duration):
        """Actual speech bubble display (runs only on the main thread)"""
        self._stream_buffer = ""
        self._present_speech_bubble(text, duration)

    def _present_speech_bubble(self, text, duration):
        """Create and show a fresh speech bubble (leaves the stream buffer untouched)."""
        # Stop the existing timer
        self.bubble_hide_timer.stop()

        # Remove the existing speech bubble
        if self.speech_bubble:
            self.speech_bubble.hide()
            self.speech_bubble.deleteLater()

        # Create a new speech bubble
        self.speech_bubble = SpeechBubble(text, self)
        self.speech_bubble.show()
        self.speech_bubble.raise_()
        self.update()

        # Start the auto-hide timer (on the main thread)
        if duration > 0:
            self.bubble_hide_timer.start(duration)
        else:
            # Safety setting so the bubble disappears after at most 60 seconds even when duration=0 (waiting for TTS), which handles long sentences
            self.bubble_hide_timer.start(60000)
            logging.debug("Speech bubble wait mode (60-second safety mechanism active)")

        _enqueue_bubble_history(text)

    def hide_speech_bubble(self):
        """Hide the speech bubble (called externally)"""
        self.hide_speech_bubble_signal.emit()

    @Slot()
    def _hide_speech_bubble_slot(self):
        """Actual speech bubble hiding (runs only on the main thread)"""
        if self.speech_bubble:
            logging.debug("Speech bubble hide handling")
            self.speech_bubble.hide()
            self.speech_bubble.deleteLater()
            self.speech_bubble = None
        self.bubble_hide_timer.stop()

    def time_based_greeting(self):
        """Checks for event utterances."""
        try:
            from agent.speech_scheduler import get_speech_scheduler
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            return
        scheduler = get_speech_scheduler()
        if scheduler is not None:
            try:
                scheduler.tick()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                logging.debug("Skipping event speech OK: %s", exc)

    def cleanup(self):
        """Cleanup"""
        if self._listen_press_timer:
            self._listen_press_timer.stop()
        if self._character_ptt_active and self.voice_thread is not None:
            self.voice_thread.release_listening()
        if self.animation_timer:
            self.animation_timer.stop()
        if self.behavior_timer:
            self.behavior_timer.stop()
        if self.move_animation:
            self.move_animation.stop()
        if self.physics_timer:
            self.physics_timer.stop()
        if self.mouse_tracker:
            self.mouse_tracker.stop()
        if hasattr(self, 'greeting_timer'):
            self.greeting_timer.stop()
        if hasattr(self, "_sleepy_check_timer"):
            self._sleepy_check_timer.stop()
        if hasattr(self, "_yawn_timer"):
            self._yawn_timer.stop()
        if hasattr(self, 'bubble_hide_timer'):
            self.bubble_hide_timer.stop()
        if self.speech_bubble:
            self.speech_bubble.close()
        self.image_cache.cache.clear()
        self.image_head_top_cache.clear()
        self.close()
