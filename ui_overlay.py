import os
import sys
import time
import ctypes
from typing import Optional

from PyQt5.QtCore import (
    Qt, QTimer, QPoint, pyqtSlot, QRectF, QRect, QEvent,
    QVariantAnimation, QEasingCurve, QPointF, QSize, QObject,
    QPropertyAnimation, QAbstractAnimation, QElapsedTimer, QSettings
)
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QTextCursor, QTextCharFormat, QKeySequence,
    QDragEnterEvent, QDropEvent, QMouseEvent, QPaintEvent, QKeyEvent,
    QRadialGradient, QBrush, QPainterPath, QRegion, QBitmap, QWheelEvent
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QFileDialog,
    QApplication, QMenu, QAction, QShortcut,
    QSlider, QWidgetAction, QHBoxLayout, QLabel,
    QToolButton, QAbstractButton, QPushButton,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QMessageBox, QDialog, QDialogButtonBox, QScrollArea,
    QStackedWidget,
)

# Assumed external dependencies based on your project structure
from audio_worker import AudioWorker
from matching_engine import MatchingEngine
from settings_dialog import SettingsDialog


class AnimatedCloseButton(QAbstractButton):
    """
    A minimal button that morphs from a Line (-) to a Cross (X) on hover.
    The two lines start overlapped (horizontal) and rotate apart.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        
        # 0.0 = Line (Rest), 1.0 = Cross (Hover)
        self._progress = 0.0 

        # Animation Setup
        self._anim = QVariantAnimation()
        self._anim.setDuration(200)  # ms
        self._anim.setEasingCurve(QEasingCurve.OutBack) # Slight overshoot for organic feel
        self._anim.valueChanged.connect(self._on_anim_value)

    def _on_anim_value(self, value):
        self._progress = value
        self.update()

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Center point
        cx, cy = self.width() / 2, self.height() / 2
        
        # Color: both themes stay gray (avoids glitch when animating to X)
        overlay = self.parent()
        while overlay and not hasattr(overlay, '_dark_theme'):
            overlay = overlay.parent()
        dark = getattr(overlay, '_dark_theme', True) if overlay else True
        if dark:
            c_val = int(136 + (44 * self._progress))  # gray (136) -> darker gray (180) on hover
        else:
            c_val = int(100 - (20 * self._progress))  # gray (100) -> darker gray (80) on hover
        color = QColor(c_val, c_val, c_val)
        
        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        # Animation Math
        # Target angle is 45 degrees for X
        angle = self._progress * 45.0
        arm_len = 5.0 

        # Draw First Line (Rotates +45)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(angle)
        painter.drawLine(QPointF(-arm_len, 0), QPointF(arm_len, 0))
        painter.restore()

        # Draw Second Line (Rotates -45)
        # We only draw the second line if we have started animating,
        # otherwise, drawing two lines at exactly 0 degrees looks 
        # slightly thicker due to anti-aliasing.
        if self._progress > 0.05:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-angle)
            painter.drawLine(QPointF(-arm_len, 0), QPointF(arm_len, 0))
            painter.restore()


class CogButton(QAbstractButton):
    """
    Minimalist gear/cog icon for settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        overlay = self.parent()
        while overlay and not hasattr(overlay, '_dark_theme'):
            overlay = overlay.parent()
        dark = getattr(overlay, '_dark_theme', True) if overlay else True
        color = (QColor("#b0b0b0") if self._hover else QColor("#888888")) if dark else (QColor("#555555") if self._hover else QColor("#333333"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)

        cx, cy = self.width() / 2, self.height() / 2

        # 1. Draw gear body as donut (outer circle minus inner hole) — avoids CompositionMode_Clear
        #    which can show black center in light mode on some systems
        body = QPainterPath()
        body.addEllipse(QPointF(cx, cy), 5.5, 5.5)
        body.addEllipse(QPointF(cx, cy), 2.5, 2.5)  # hole; OddEvenFill makes it subtract
        painter.drawPath(body)

        # 2. Draw Teeth
        painter.save()
        painter.translate(cx, cy)
        for _ in range(8):
            painter.drawRoundedRect(QRectF(-1.2, -8.0, 2.4, 3.0), 0.5, 0.5)
            painter.rotate(45)
        painter.restore()


class MicButton(QAbstractButton):
    """
    Toggle mic mute (Notch mode). Icon: mic when unmuted, mic with slash when muted.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self._muted = False  # updated by parent

    def set_muted(self, muted: bool):
        if self._muted != muted:
            self._muted = muted
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        overlay = self.parent()
        while overlay and not hasattr(overlay, '_dark_theme'):
            overlay = overlay.parent()
        dark = getattr(overlay, '_dark_theme', True) if overlay else True
        if self._muted:
            color = QColor("#666666") if dark else QColor("#888888")
        else:
            color = (QColor("#b0b0b0") if self._hover else QColor("#888888")) if dark else (QColor("#555555") if self._hover else QColor("#333333"))
        painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        # Mic capsule (rounded rect for body)
        body_h, body_w = 10, 6
        painter.drawRoundedRect(QRectF(cx - body_w/2, cy - body_h/2 - 1, body_w, body_h), 3, 3)
        # Stem (a bit longer)
        stem_top = cy + body_h/2 - 1
        stem_bottom = cy + 10
        base_y = stem_bottom
        painter.drawLine(QPointF(cx, stem_top), QPointF(cx, base_y))
        # Base: horizontal line with dome above it (dome nudged up a tiny bit)
        painter.drawArc(QRectF(cx - 5, base_y - 8, 10, 5), 180 * 16, 180 * 16)
        if self._muted:
            # Diagonal slash through mic
            painter.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 6, cy + 6))

class CompactButton(QAbstractButton):
    """
    Toggle narrow (2-word width) vs normal. Icon: || = go narrow, = = go wide.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self._compact = False  # updated by parent when toggling

    def set_compact(self, compact: bool):
        if self._compact != compact:
            self._compact = compact
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        overlay = self.parent()
        while overlay and not hasattr(overlay, '_dark_theme'):
            overlay = overlay.parent()
        dark = getattr(overlay, '_dark_theme', True) if overlay else True
        color = (QColor("#b0b0b0") if self._hover else QColor("#888888")) if dark else (QColor("#555555") if self._hover else QColor("#333333"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        cx, cy = self.width() / 2, self.height() / 2
        r = 2  # corner radius
        if self._compact:
            # Wide icon: wider rounded rectangle (click to expand)
            w, h = 14, 8
            painter.drawRoundedRect(QRectF(cx - w/2, cy - h/2, w, h), r, r)
        else:
            # Narrow icon: tall narrow rounded rectangle (click to go 2-word width)
            w, h = 10, 10
            painter.drawRoundedRect(QRectF(cx - w/2, cy - h/2, w, h), r, r)


class _RoundedMenu(QMenu):
    """
    QMenu with smooth rounded corners via custom painting.
    We don't use a mask (which is pixelated); instead we paint a rounded rect
    and set the menu to have a transparent background.
    Excluded from screenshare/capture on Windows when shown.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._radius = 12

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            QTimer.singleShot(0, self._apply_capture_exclusion)

    def _apply_capture_exclusion(self):
        """Exclude menu from screenshare/capture on Windows."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            WDA_EXCLUDEFROMCAPTURE = 0x11
            WDA_MONITOR = 0x1
            ok = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if not ok:
                user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw rounded background
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QColor("#1e1e1e"))
        painter.drawPath(path)
        
        # Let the base class paint the items
        # We need to clip to the rounded rect
        painter.setClipPath(path)
        super().paintEvent(event)


class HelpDialog(QDialog):
    """First-time guide / Help dialog — frameless, rounded, pill-style."""
    CORNER_RADIUS = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(360, 310)
        self._drag_pos = None
        self._close_pending = None
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_anim.setDuration(300)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setEndValue(1.0)
        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_out_anim.setDuration(300)
        self._fade_out_anim.setEasingCurve(QEasingCurve.InCubic)
        self._fade_out_anim.setStartValue(1.0)
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.finished.connect(self._on_fade_out_finished)

        self.setStyleSheet("""
            QDialog { background: transparent; }
            QLabel {
                color: #c8c8c8;
                font-family: "Poppins", "Segoe UI", sans-serif;
                font-weight: 400;
                font-size: 10px;
                background: transparent;
            }
            QPushButton {
                background: #2a2a2a;
                color: #b0b0b0;
                border: 1px solid #444;
                border-radius: 8px;
                padding: 5px 16px;
                font-family: "Poppins", "Segoe UI", sans-serif;
                font-size: 10px;
            }
            QPushButton:hover { background: #007aff; color: #ffffff; border-color: #007aff; }
            QPushButton:pressed { background: #005ecb; color: #ffffff; }
            QScrollBar:vertical {
                border: none;
                background: #2a2a2a;
                width: 8px;
                border-radius: 4px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        # Header label (small, subtle)
        header = QLabel("Help")
        header.setStyleSheet("font-size: 13px; font-weight: 600; color: #ffffff; background: transparent;")
        layout.addWidget(header)

        label_style = """
            QLabel {
                color: #c8c8c8;
                font-family: "Poppins", "Segoe UI", sans-serif;
                font-weight: 400;
                font-size: 10px;
                background: transparent;
                padding-right: 12px;
            }
        """
        def _make_label(html):
            lbl = QLabel(html)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.RichText)
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            lbl.setStyleSheet(label_style)
            return lbl

        def _make_line():
            line = QWidget()
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #444;")
            return line

        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        body_layout.addWidget(_make_label(
            "<p style='margin:4px 0'>Notch is a smart, invisible to screensharing teleprompter that stays on top of your screen.</p>"
            "<p style='margin:6px 0 2px 0'><b>Main features:</b></p>"
            "<ul style='margin:0; padding-left:16px;'>"
            "<li><b>Invisible to screenshare</b> — Not shown in screen recordings or video calls</li>"
            "<li><b>Stays on top</b> — Always visible above other windows</li>"
            "<li><b>Voice-follow</b> (Notch mode) or <b>manual scroll</b> (Keys & Scroll mode)</li>"
            "<li><b>Local speech recognition</b> — Runs offline, no data sent to the cloud</li>"
            "</ul>"
        ))
        body_layout.addWidget(_make_line())
        body_layout.addWidget(_make_label(
            "<p style='margin:6px 0 2px 0'><b>Get started:</b></p>"
            "<ul style='margin:0; padding-left:16px;'>"
            "<li><b>Load a script</b> — Double-click Notch to edit, drag a .txt file, or use <i>Load Script</i> from the menu.</li>"
            "<li><b>Notch mode</b> — Script follows your voice. Switch modes via the gear menu.</li>"
            "<li><b>Keys & Scroll</b> — Hold <b>Space</b> to scroll. <b>Arrow keys</b> adjust speed.</li>"
            "<li>Click the <b>gear</b> (or right-click) for mode, font, theme, and settings.</li>"
            "</ul>"
        ))
        body_layout.addWidget(_make_line())
        body_layout.addWidget(_make_label(
            "<p style='margin:6px 0 2px 0'><b>Voice commands</b> (Notch mode):</p>"
            "<ul style='margin:0; padding-left:16px;'>"
            "<li><i>\"Notch Restart\"</i> — Restart from the beginning</li>"
            "<li><i>\"Notch Expand\"</i> — Open edit mode</li>"
            "<li><i>\"Notch Mute\"</i> — Mute/unmute the mic</li>"
            "<li><i>\"Notch Close\"</i> — Close Notch</li>"
            "</ul>"
        ))
        body_layout.addWidget(_make_line())
        body_layout.addWidget(_make_label(
            "<p style='margin:6px 0 2px 0'><b>Shortcuts:</b></p>"
            "<ul style='margin:0; padding-left:16px;'>"
            "<li><i>Ctrl+R</i> — Restart script</li>"
            "<li><i>Esc</i> — Close Notch</li>"
            "</ul>"
        ))
        body_layout.addWidget(_make_line())
        credit = QLabel('<a href="https://socia.ae/products/notch" style="color:#888; font-size:9px; text-decoration:none;">Notch by Socia</a>')
        credit.setOpenExternalLinks(True)
        credit.setTextFormat(Qt.RichText)
        credit.setStyleSheet("QLabel { color: #888; font-size: 9px; background: transparent; padding-right: 12px; }")
        credit.setCursor(Qt.PointingHandCursor)
        credit.setTextInteractionFlags(Qt.TextBrowserInteraction)
        body_layout.addWidget(credit)

        scroll = QScrollArea()
        scroll.setWidget(body_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        layout.addWidget(scroll, 1)

        ok = QPushButton("Got it")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok)
        layout.addLayout(btn_layout)

    def _on_fade_out_finished(self):
        pending = self._close_pending
        self._close_pending = None
        if pending == "accept":
            super(HelpDialog, self).accept()
        elif pending == "reject":
            super(HelpDialog, self).reject()

    def closeEvent(self, event):
        if self._close_pending is not None or self._fade_out_anim.state() == QAbstractAnimation.Running:
            event.ignore()
            return
        self._close_pending = "reject"
        self._fade_out_anim.start()
        event.ignore()

    def reject(self):
        if self._fade_out_anim.state() == QAbstractAnimation.Running:
            return
        if self._close_pending is not None:
            return
        self._close_pending = "reject"
        self._fade_out_anim.start()

    def accept(self):
        if self._fade_out_anim.state() == QAbstractAnimation.Running:
            return
        if self._close_pending is not None:
            return
        self._close_pending = "accept"
        self._fade_out_anim.start()

    # ── Custom rounded painting (matches pill / settings) ──────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QColor("#1e1e1e"))
        painter.drawPath(path)

    # ── Draggable ──────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Position below parent (fade-in only, no slide) ──────────────
    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        if parent and parent.isVisible() and parent.width() > 0:
            gap = 8
            pt = parent.mapToGlobal(parent.rect().topLeft())
            x = pt.x() + (parent.width() - self.width()) // 2
            y_final = pt.y() + parent.height() + gap
            self.setGeometry(QRect(x, y_final, self.width(), self.height()))
            self.setWindowOpacity(0.0)
            self._opacity_anim.start()


class NotchOverlay(QWidget):
    """
    Minimalist 'Dynamic Island' style teleprompter.
    Pulses with voice activity.
    """

    # (display name, actual font family for QFont)
    FONT_OPTIONS = [
        ("Consolas", "Consolas"),
        ("Arial", "Arial"),
        ("Open Sans", "Open Sans"),
        ("Times", "Times New Roman"),
        ("Helvetica", "Helvetica"),
    ]

    # Dimensions (60% narrower default)
    DEFAULT_W, DEFAULT_H = 200, 110
    MIN_W, MIN_H = 300, 80
    COMPACT_W = 100   # ~2 word width with compact font
    COMPACT_FONT = 6  # smallest allowed text size
    MODEL_PATH = "model"  # overridden in __init__ when running as frozen exe

    # Aesthetic Constants
    CORNER_RADIUS = 24      # Pill shape (lower = less curved)
    GLOW_COLOR = QColor(41, 98, 255)       # Blue = Notch (follows voice)
    MANUAL_GLOW_COLOR = QColor(46, 204, 113)  # Green = Keys & Scroll

    def __init__(self):
        super().__init__()
        # When packaged as exe, look for model next to the executable
        if getattr(sys, "frozen", False):
            self.MODEL_PATH = os.path.join(os.path.dirname(sys.executable), "model")
            self._log_install_paths()
        else:
            self.MODEL_PATH = NotchOverlay.MODEL_PATH

        # ── State ────────────────────────────────────────────────────
        self._font_size = 10
        self._font_family = "Consolas"
        self._dark_theme = True  # False = light (white pill in Notch/Keys & Scroll)
        self._opacity = 1.0
        self._voice_mode = True
        self._voice_wpm = 60
        self._manual_wpm = 150
        self._manual_running = False
        self._manual_scroll_accum = 0.0
        self._voice_scroll_accum = 0.0
        self._drag_pos: Optional[QPoint] = None
        self._is_speaking = False
        self._checkpoints = {}
        self._edit_mode = False
        self._text_fade_for_expand = True
        self._collapsed_size = None
        self._prev_voice_mode = True
        self._compact_mode = False
        self._size_before_compact: Optional[QSize] = None
        self._font_size_before_compact = 10

        # ── DPI scaling (so UI looks similar on different screen sizes) ─
        desktop = QApplication.desktop()
        if desktop and hasattr(desktop, 'logicalDpiX'):
            dpi = desktop.logicalDpiX()
        else:
            screen = QApplication.primaryScreen()
            if screen and hasattr(screen, 'devicePixelRatio'):
                dpi = 96.0 * screen.devicePixelRatio()
            else:
                dpi = 96
        self._scale = max(0.75, min(2.0, dpi / 96.0))
        self.DEFAULT_W = int(200 * self._scale)
        self.DEFAULT_H = int(110 * self._scale)
        self.MIN_W = int(300 * self._scale)
        self.MIN_H = int(80 * self._scale)
        self.COMPACT_W = int(100 * self._scale)
        self.CORNER_RADIUS = int(24 * self._scale)
        self.COMPACT_FONT = max(4, min(12, int(6 * self._scale)))
        self._font_size = max(6, min(24, int(10 * self._scale)))
        self._font_size_before_compact = self._font_size

        # ── Animation State ──────────────────────────────────────────
        self._current_glow_alpha = 28  # Base glow (0-255); lower = more transparent
        self._target_glow_alpha = 28
        self._smoothed_volume_level = 0.0  # EMA of raw mic level for smooth bar

        # ── Workers ──────────────────────────────────────────────────
        self._audio_worker: Optional[AudioWorker] = None
        self._stopping_worker = None  # Worker being stopped; _start_listening waits for it
        self._device_index: Optional[int] = None
        self._noise_gate: float = 0.01
        self._input_gain: float = 2.0
        self._matching = MatchingEngine()
        self._script_text = ""
        self._last_match_time: Optional[float] = None
        self._last_match_pos = -1
        self._speech_active_until = 0.0
        # Voice mode: target scroll position (pixels) to keep ~1.5 lines unread visible
        self._voice_target_scroll: Optional[float] = None
        self._last_manual_scroll_time = 0.0  # don't override scroll for this long after user scrolls (seconds)

        # ── Timers ───────────────────────────────────────────────────
        # Scroll timer (glow + manual scroll); 60 FPS for smooth response
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(17)  # ~60 FPS
        self._scroll_timer.timeout.connect(self._tick)

        # ── Window Setup ─────────────────────────────────────────────
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.resize(self.DEFAULT_W, self.DEFAULT_H)
        self._center_top()
        self._collapsed_size = self.size()

        # ── Fade-in animation ─────────────────────────────────────────
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(400)  # 0.4s
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ── Edit mode expand/collapse geometry animation ──────────────
        self._geometry_anim = QPropertyAnimation(self, b"geometry")
        self._geometry_anim.setDuration(450)  # ~0.45s, smooth expand/collapse
        self._geometry_anim.setEasingCurve(QEasingCurve.InOutCubic)  # smooth start and end
        self._geometry_anim_entering = False  # True = expanding into edit, False = collapsing out
        self._geometry_anim.finished.connect(self._on_edit_geometry_anim_finished)

        # ── Glow fade out/in during expand/collapse (0.4s) ──────────────
        self._glow_anim = QVariantAnimation(self)
        self._glow_anim.setDuration(400)
        self._glow_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._glow_anim.valueChanged.connect(self._on_glow_anim_value)

        # ── Narrow/wide (compact) geometry animation ──────────────────
        # Animate width only and keep window centered (so it expands from center, not sticks to one side)
        self._compact_width_anim = QVariantAnimation()
        self._compact_width_anim.setDuration(350)
        self._compact_width_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._compact_width_anim.valueChanged.connect(self._on_compact_width_anim_value)
        self._compact_anim_going_narrow = False
        self._compact_anim_center_x = 0
        self._compact_anim_y = 0
        self._compact_anim_h = 0
        self._compact_width_anim.finished.connect(self._on_compact_geometry_anim_finished)

        # ── Build UI ─────────────────────────────────────────────────
        self._build_ui()
        self._setup_shortcuts()
        self._update_window_mask()
        QTimer.singleShot(0, self._apply_capture_exclusion)
        QTimer.singleShot(0, self._apply_blur_effect)
        
        # Start timer immediately for animation loop
        self._scroll_timer.start()
        print("[Notch] Overlay ready (mode: Notch=voice follow, Keys & Scroll=manual)", flush=True)

    def _on_glow_anim_value(self, value):
        self._current_glow_alpha = int(round(value))
        self._target_glow_alpha = self._current_glow_alpha
        self.update()

    def _on_text_fade_out_finished(self):
        """Text has faded out; apply styling while invisible, then fade back in (or defer for collapse)."""
        if self._text_fade_for_expand:
            self._edit_mode = True
            self._text_edit.setReadOnly(False)
            self._text_edit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._text_edit.setStyleSheet("""
                QTextEdit { background: #ffffff; color: #111111; border: none; }
                QScrollBar:vertical {
                    background: #f0f0f0;
                    width: 10px;
                    border-radius: 5px;
                    margin: 2px 0;
                }
                QScrollBar::handle:vertical {
                    background: #c0c0c0;
                    min-height: 24px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0;
                    background: none;
                }
                QScrollBar:horizontal {
                    background: #f0f0f0;
                    height: 10px;
                    border-radius: 5px;
                    margin: 0 2px;
                }
                QScrollBar::handle:horizontal {
                    background: #c0c0c0;
                    min-width: 24px;
                    border-radius: 5px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #a0a0a0;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0;
                    background: none;
                }
            """)
            self._clear_edit_mode_char_formats()
            self._text_edit.setFocus()
            self._text_fade_in.start()
        else:
            # Collapsing: apply pill styling while text is invisible (no snap)
            new_text = self._text_edit.toPlainText()
            script_changed = new_text != self._script_text
            self._script_text = new_text
            self._matching.load_script(self._script_text)
            self._last_match_time = None
            self._last_match_pos = -1
            self._edit_mode = False
            self._text_edit.setReadOnly(True)
            self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._text_edit.setAlignment(Qt.AlignCenter)
            self._apply_read_mode_style()
            self._apply_highlight(-1)
            if script_changed:
                self._text_edit.moveCursor(QTextCursor.Start)
                self._text_edit.verticalScrollBar().setValue(0)
            # Text stays invisible; fade-in deferred to _on_edit_geometry_anim_finished

    # ═══════════════════════════════════════════════════════════════════
    #  UI Construction (Ultra Minimal)
    # ═══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QVBoxLayout(self)
        s = self._scale
        root.setContentsMargins(int(18 * s), int(8 * s), int(18 * s), int(10 * s))
        root.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        # REPLACED: Custom AnimatedCloseButton
        self._close_btn = AnimatedCloseButton()
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.close)
        
        top_bar.addWidget(self._close_btn)
        top_bar.addStretch()

        # Top-right icons (mic, compact, settings) – fade in/out on contract/expand
        self._icons_container = QWidget()
        icons_layout = QHBoxLayout(self._icons_container)
        icons_layout.setContentsMargins(0, 0, 0, 0)
        icons_layout.setSpacing(6)
        self._muted = False
        self._mic_btn = MicButton()
        self._mic_btn.setToolTip("Mute mic (stop voice from advancing script)")
        self._mic_btn.clicked.connect(self._toggle_mic_mute)
        icons_layout.addWidget(self._mic_btn)
        self._compact_btn = CompactButton()
        self._compact_btn.setToolTip("Narrow (2 words)")
        self._compact_btn.clicked.connect(self._toggle_compact_mode)
        icons_layout.addWidget(self._compact_btn)
        self._settings_btn = CogButton()
        self._settings_btn.setToolTip("Menu")
        self._settings_btn.clicked.connect(self._open_menu_from_button)
        icons_layout.addWidget(self._settings_btn)
        self._icons_opacity = QGraphicsOpacityEffect(self._icons_container)
        self._icons_container.setGraphicsEffect(self._icons_opacity)
        self._icons_opacity.setOpacity(1.0)
        self._icon_fade_in = QPropertyAnimation(self._icons_opacity, b"opacity")
        self._icon_fade_in.setDuration(200)
        self._icon_fade_in.setStartValue(0.0)
        self._icon_fade_in.setEndValue(1.0)
        self._icon_fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._icon_fade_out = QPropertyAnimation(self._icons_opacity, b"opacity")
        self._icon_fade_out.setDuration(200)
        self._icon_fade_out.setStartValue(1.0)
        self._icon_fade_out.setEndValue(0.0)
        self._icon_fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._icon_fade_out.finished.connect(self._icons_container.hide)
        top_bar.addWidget(self._icons_container)
        self._set_top_bar_icon_size(int(24 * self._scale))

        root.addLayout(top_bar)

        # ── Script text area ─────────────────────────────────────────
        self._text_edit = QTextEdit()
        self._text_edit.setAcceptRichText(False)  # Paste as plain text only (no colors, bg, etc.)
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont(self._font_family, self._font_size))
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self._text_edit.setAlignment(Qt.AlignCenter)
        self._text_edit.setPlaceholderText("Notch\n(Double click or drop script)")
        self._apply_read_mode_style()
        self._text_edit.installEventFilter(self)
        self._text_edit.viewport().installEventFilter(self)
        root.addWidget(self._text_edit)

        # Text fade out/in for smooth mode transitions (expand/collapse)
        self._text_opacity = QGraphicsOpacityEffect(self._text_edit)
        self._text_edit.setGraphicsEffect(self._text_opacity)
        self._text_opacity.setOpacity(1.0)
        self._text_fade_out = QPropertyAnimation(self._text_opacity, b"opacity")
        self._text_fade_out.setDuration(150)
        self._text_fade_out.setStartValue(1.0)
        self._text_fade_out.setEndValue(0.0)
        self._text_fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._text_fade_out.finished.connect(self._on_text_fade_out_finished)
        self._text_fade_in = QPropertyAnimation(self._text_opacity, b"opacity")
        self._text_fade_in.setDuration(150)
        self._text_fade_in.setStartValue(0.0)
        self._text_fade_in.setEndValue(1.0)
        self._text_fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # Speed feedback popup (manual mode: bottom right, fade in/out)
        self._speed_feedback_lbl = QLabel(self)
        self._speed_feedback_lbl.setStyleSheet("""
            background-color: rgba(44, 44, 46, 0.55);
            color: #ffffff;
            padding: 4px 10px;
            border-radius: 6px;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: 11px;
        """)
        self._speed_feedback_lbl.hide()
        self._speed_feedback_opacity = QGraphicsOpacityEffect(self._speed_feedback_lbl)
        self._speed_feedback_lbl.setGraphicsEffect(self._speed_feedback_opacity)
        self._speed_feedback_fade_in = QPropertyAnimation(self._speed_feedback_opacity, b"opacity")
        self._speed_feedback_fade_in.setDuration(100)
        self._speed_feedback_fade_in.setStartValue(0.0)
        self._speed_feedback_fade_in.setEndValue(1.0)
        self._speed_feedback_fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._speed_feedback_fade_out = QPropertyAnimation(self._speed_feedback_opacity, b"opacity")
        self._speed_feedback_fade_out.setDuration(100)
        self._speed_feedback_fade_out.setStartValue(1.0)
        self._speed_feedback_fade_out.setEndValue(0.0)
        self._speed_feedback_fade_out.setEasingCurve(QEasingCurve.InCubic)
        self._speed_feedback_fade_out.finished.connect(self._speed_feedback_lbl.hide)
        self._speed_feedback_timer = QTimer(self)
        self._speed_feedback_timer.setSingleShot(True)
        self._speed_feedback_timer.timeout.connect(self._start_speed_feedback_fade_out)

    def _setup_shortcuts(self):
        def _mk(seq, handler):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(handler)
            return sc

        self._sc_space = _mk("Space", self._toggle_manual_run)
        self._sc_reset = _mk("Ctrl+R", self._reset_position)
        self._sc_cp1 = _mk("Ctrl+1", lambda: self._set_checkpoint(1))
        self._sc_cp2 = _mk("Ctrl+2", lambda: self._set_checkpoint(2))
        self._sc_cp3 = _mk("Ctrl+3", lambda: self._set_checkpoint(3))
        self._sc_cp4 = _mk("Ctrl+4", lambda: self._set_checkpoint(4))
        self._sc_go1 = _mk("Ctrl+Shift+1", lambda: self._go_to_checkpoint(1))
        self._sc_go2 = _mk("Ctrl+Shift+2", lambda: self._go_to_checkpoint(2))
        self._sc_go3 = _mk("Ctrl+Shift+3", lambda: self._go_to_checkpoint(3))
        self._sc_go4 = _mk("Ctrl+Shift+4", lambda: self._go_to_checkpoint(4))
        self._sc_left = _mk("Left", lambda: self._adjust_speed_dir(-1))
        self._sc_right = _mk("Right", lambda: self._adjust_speed_dir(1))
        self._sc_esc = _mk("Escape", self.close)

    # ═══════════════════════════════════════════════════════════════════
    #  Custom Painting (Floating Pill & Reactive Glow)
    # ═══════════════════════════════════════════════════════════════════

    def _update_window_mask(self):
        """
        Clear any mask so the window is transparent.
        We rely on paintEvent + WA_TranslucentBackground for smooth anti-aliased edges.
        """
        self.clearMask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # No mask needed - edges are smooth via paintEvent anti-aliasing

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Define Shape (Rounded Pill)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # 2. Draw Background
        painter.setPen(Qt.NoPen)
        if self._edit_mode:
            bg_color = QColor("#ffffff")
        else:
            bg_color = QColor("#ffffff") if not self._dark_theme else QColor("#000000")
        # Edit mode and light-mode pill: full opacity white; dark pill: 0.95
        bg_color.setAlphaF(1.0 if (self._edit_mode or not self._dark_theme) else 0.95)
        painter.setBrush(bg_color)
        painter.drawPath(path)

        # 3. Draw Reactive Glow
        # The glow is a radial gradient at the bottom center
        # Intensity depends on self._current_glow_alpha
        if self._edit_mode:
            return

        glow_center = QPoint(int(w/2), int(h)) # Bottom center
        radius = w / 1.5
        
        radialGrad = QRadialGradient(glow_center, radius)
        
        glow_base = self.GLOW_COLOR if self._voice_mode else self.MANUAL_GLOW_COLOR
        glow_col = QColor(glow_base)
        glow_col.setAlpha(int(self._current_glow_alpha))
        
        radialGrad.setColorAt(0.0, glow_col)
        radialGrad.setColorAt(0.5, QColor(0, 0, 0, 0)) # Fade out
        
        painter.setBrush(QBrush(radialGrad))
        painter.setClipPath(path) # Keep glow inside the pill
        painter.drawRect(0, 0, w, h)

    # ═══════════════════════════════════════════════════════════════════
    #  Animation & Scrolling Loop
    # ═══════════════════════════════════════════════════════════════════

    def _tick(self):
        """
        Handles both text scrolling AND glow animation smoothing.
        Runs at ~30 FPS.
        """
        # 1. Animate Glow (smooth lerp toward target; skip while expand/collapse glow anim runs)
        if self._glow_anim.state() != QAbstractAnimation.Running:
            diff = self._target_glow_alpha - self._current_glow_alpha
            self._current_glow_alpha += diff * 0.12  # Slower follow = smoother bar
            if self._current_glow_alpha < 0: self._current_glow_alpha = 0
            if self._current_glow_alpha > 255: self._current_glow_alpha = 255
        
        # During collapse from edit mode, clip window to pill so top bar doesn't "separate" visually
        if (self._geometry_anim.state() == QAbstractAnimation.Running
                and not self._geometry_anim_entering):
            self._update_collapse_mask()
        
        # Trigger repaint to show new glow
        self.update()

        # 2. Handle Scrolling
        if self._edit_mode:
            return
        bar = self._text_edit.verticalScrollBar()

        if self._voice_mode and self._voice_target_scroll is not None:
            # Don't override scroll for a short time after user scrolls manually
            if time.monotonic() - self._last_manual_scroll_time >= 2.5:
                current = float(bar.value())
                target = self._voice_target_scroll
                rate = 0.945 if self._compact_mode else 0.63  # 0.63 * 1.5
                step = (target - current) * rate
                if self._compact_mode:
                    step = max(-10.0, min(10.0, step))  # cap step for smoother motion
                if abs(step) < 0.5 and abs(target - current) < 2:
                    bar.setValue(int(round(target)))
                else:
                    bar.setValue(int(round(current + step)))
        elif not self._voice_mode and self._manual_running:
            if bar.value() < bar.maximum():
                interval_sec = self._scroll_timer.interval() / 1000.0
                pixels_per_tick = (self._manual_wpm / 60.0) * 12.0 * interval_sec
                self._manual_scroll_accum += max(0.0, pixels_per_tick)
                step = int(self._manual_scroll_accum)
                if step > 0:
                    self._manual_scroll_accum -= step
                    bar.setValue(bar.value() + step)

    # ═══════════════════════════════════════════════════════════════════
    #  Audio Integration
    # ═══════════════════════════════════════════════════════════════════

    def _start_listening(self):
        self._stop_listening()
        self._stop_listening_sync()  # Wait for old worker before starting new one (only blocks when restarting)
        print("[Notch] Starting audio worker...", flush=True)
        self._audio_worker = AudioWorker(
            self._device_index,
            self._noise_gate,
            self._input_gain,
            self.MODEL_PATH,
        )
        self._audio_worker.speaking_signal.connect(self._on_speaking_changed)
        self._audio_worker.volume_level_signal.connect(self._on_volume_level)
        self._audio_worker.speech_text_signal.connect(self._on_speech_text)
        self._audio_worker.error_signal.connect(self._on_audio_error)
        self._audio_worker.start()
        print("[Notch] Audio worker started", flush=True)

    def _stop_listening(self):
        """Stop audio worker. Non-blocking: worker exits in background. Use _stop_listening_sync to wait."""
        worker = self._audio_worker
        self._audio_worker = None
        if not worker:
            self._is_speaking = False
            self._target_glow_alpha = 28
            self._smoothed_volume_level = 0.0
            return
        try:
            worker.blockSignals(True)
            worker.speaking_signal.disconnect()
            worker.volume_level_signal.disconnect()
            worker.speech_text_signal.disconnect()
            worker.error_signal.disconnect()
        except Exception:
            pass
        worker.stop()
        self._stopping_worker = worker  # so _start_listening can wait before starting new one
        self._is_speaking = False
        self._target_glow_alpha = 28
        self._smoothed_volume_level = 0.0

    def _stop_listening_sync(self):
        """Block until any stopping worker has exited. Use before starting new worker."""
        w = getattr(self, "_stopping_worker", None)
        if not w or not w.isRunning():
            self._stopping_worker = None
            return
        et = QElapsedTimer()
        et.start()
        while w.isRunning() and et.elapsed() < 3000:
            QApplication.processEvents()
            w.wait(50)
        self._stopping_worker = None

    def _log_install_paths(self):
        """When running as installed exe, write data path and existence to a log for debugging."""
        try:
            log_path = os.path.join(os.path.dirname(sys.executable), "notch_log.txt")
            exists = os.path.isdir(self.MODEL_PATH)
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"data_path={self.MODEL_PATH}\n")
                f.write(f"data_exists={exists}\n")
        except Exception:
            pass

    @pyqtSlot(str)
    def _on_audio_error(self, message: str):
        """Show mic/speech errors to the user (installed exe has no console)."""
        QMessageBox.warning(self, "Notch – Audio", message)

    @pyqtSlot(bool)
    def _on_speaking_changed(self, is_speaking):
        self._is_speaking = is_speaking

    @pyqtSlot(float)
    def _on_volume_level(self, level):
        """
        Receives volume level (0.0 to 1.0 approx) from audio worker.
        Smooth with EMA so the glow bar isn't jittery, then update target.
        """
        if self._voice_mode:
            # Exponential moving average: smooth over many updates
            self._smoothed_volume_level = self._smoothed_volume_level * 0.75 + level * 0.25
            intensity = min(1.0, self._smoothed_volume_level * 5.0)
            self._target_glow_alpha = 28 + int(140 * intensity)

    def _toggle_mic_mute(self):
        self._muted = not self._muted
        self._mic_btn.set_muted(self._muted)
        if self._audio_worker:
            self._audio_worker.set_muted(self._muted)  # worker skips emitting when muted; resets recognizer on unmute
        self._mic_btn.setToolTip("Unmute mic" if self._muted else "Mute mic (stop voice from advancing script)")

    # Filler words often recognised from ambient noise when nothing is said
    _SPEECH_IGNORE_WORDS = frozenset({"huh", "uh", "um", "hmm", "hm", "eh", "ah"})

    # Voice commands: "Notch X" — checked case-insensitive, final results only
    # Include "not" variant (common misrecognition of "notch")
    _VOICE_COMMANDS = {
        "notch restart": lambda s: s._reset_position(),
        "not restart": lambda s: s._reset_position(),
        "notch expand": lambda s: s._toggle_edit_mode(),
        "not expand": lambda s: s._toggle_edit_mode(),
        "notch mute": lambda s: s._toggle_mic_mute(),
        "not mute": lambda s: s._toggle_mic_mute(),
        "notch close": lambda s: s.close(),
        "not close": lambda s: s.close(),
    }

    @pyqtSlot(str, bool)
    def _on_speech_text(self, text: str, is_final: bool):
        if self._muted:
            return
        txt = " ".join(text.strip().lower().split())  # normalize spaces
        if txt in self._SPEECH_IGNORE_WORDS and not self._is_speaking:
            return  # Skip filler false positives when not actively speaking
        if text.strip():
            print(f"[Notch speech] {'(final)' if is_final else '(partial)'}: {text!r}", flush=True)

        # Voice commands (final only, work even without script)
        if is_final and txt in self._VOICE_COMMANDS:
            self._VOICE_COMMANDS[txt](self)
            return

        if not self._script_text:
            return

        # Partials: match with strict advance for fast, low-jitter response.
        # Finals: match with larger advance and allow extended catch-up.
        if is_final:
            max_jump = 12 if self._last_match_pos >= 0 else 20
            position = self._matching.match_spoken(
                text,
                allow_extended=True,
                max_advance=max_jump,
            )
            if position is not None:
                self._apply_highlight(position)
                self._voice_target_scroll = self._target_scroll_for_reading_position(position)
                self._update_voice_speed(position, True)
                self._speech_active_until = time.monotonic() + 1.0
        else:
            # Partial: small advance so we follow in real time without big jumps
            position = self._matching.match_spoken(
                text,
                allow_extended=False,
                max_advance=5,
            )
            if position is not None:
                self._apply_highlight(position)
                self._voice_target_scroll = self._target_scroll_for_reading_position(position)
                self._speech_active_until = max(
                    self._speech_active_until,
                    time.monotonic() + 0.8,
                )

    # ═══════════════════════════════════════════════════════════════════
    #  Context Menu
    # ═══════════════════════════════════════════════════════════════════

    def _build_menu(self) -> QMenu:
        menu = _RoundedMenu(self)
        scale = self._scale
        radius = max(6, int(12 * scale))
        compact = getattr(self, "_compact_mode", False)
        font_sz = f"{int(9 * scale)}px" if compact else f"{int(11 * scale)}px"
        pad = "2px 6px" if compact else "4px 10px"
        # ── Poppins Regular, rounded corners ────────────────────────────
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: transparent;
                border: none;
                padding: {4 if compact else 4}px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: #b0b0b0;
                padding: {pad};
                border-radius: 6px;
                font-family: "Poppins", "Segoe UI", sans-serif;
                font-weight: 400;
                font-size: {font_sz};
                margin: 1px 0;
            }}
            QMenu::item:selected {{
                background-color: #2a2a2a;
                color: #ffffff;
            }}
            QMenu::separator {{
                background-color: #333;
                height: 1px;
                margin: 2px 6px;
            }}
        """)
        menu._radius = radius
        if compact:
            menu.setMaximumWidth(int(150 * scale))
        
        # ── 1. Mode (Notch = follows voice / Keys & Scroll = manual) ──
        voice_widget = QWidget(menu)
        voice_widget.setCursor(Qt.PointingHandCursor)
        voice_layout = QHBoxLayout(voice_widget)
        m = (6, 2, 6, 2) if compact else (10, 4, 10, 4)
        voice_layout.setContentsMargins(*m)
        voice_layout.setSpacing(8 if compact else 10)

        # Notch = blue (follows voice), Keys & Scroll = green (manual)
        ind_color = "#007aff" if self._voice_mode else "#4cd964"
        mode_tag = "Notch" if self._voice_mode else "Keys & Scroll"
        if not self._voice_mode:
            voice_widget.setToolTip(
                '<span style="font-size: 6pt">Hold Space to scroll · Use arrow keys to adjust speed</span>'
            )

        # Style for the whole row with hover
        voice_widget.setStyleSheet(f"""
            QWidget {{
                background-color: transparent;
                border-radius: 6px;
            }}
            QWidget:hover {{
                background-color: #2a2a2a;
            }}
        """)

        v_label = QLabel("Mode")
        v_label.setStyleSheet(f"""
            color: #b0b0b0; 
            font-family: "Poppins", "Segoe UI", sans-serif; 
            font-weight: 400; 
            font-size: {font_sz};
            background: transparent;
        """)
        voice_layout.addWidget(v_label)
        voice_layout.addStretch()

        # Mode tag (e.g., "Notch" or "Keys & Scroll") — store ref so we can update on mode switch
        tag_label = QLabel(mode_tag)
        tag_font = f"{int(8 * scale)}px" if compact else f"{int(9 * scale)}px"
        tag_label.setStyleSheet(f"""
            color: {ind_color};
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {tag_font};
            padding: 1px 6px;
            border: 1px solid {ind_color};
            border-radius: 6px;
            background: transparent;
        """)
        voice_layout.addWidget(tag_label)

        # Glowing indicator dot — store ref for refresh on mode switch
        indicator = QLabel()
        indicator.setFixedSize(int(8 * scale), int(8 * scale))
        indicator.setStyleSheet(f"""
            background-color: {ind_color}; 
            border-radius: 4px;
        """)
        voice_layout.addWidget(indicator)

        # Store refs so menu can refresh mode display when user toggles (keep menu open)
        menu._mode_tag_label = tag_label
        menu._mode_indicator = indicator
        menu._mode_tag_font = tag_font

        # Click handler: install filter on the widget we control (avoids createWidget returning None)
        class VoiceRowClickFilter(QObject):
            def __init__(self, menu, callback, parent=None):
                super().__init__(parent)
                self._menu = menu
                self._callback = callback

            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    self._callback()
                    # Keep menu open so user can change other settings after switching mode
                    return True
                return False

        def _toggle_action():
            self._toggle_mode(not self._voice_mode)
            self._refresh_menu_mode_display(menu)

        voice_widget.installEventFilter(VoiceRowClickFilter(menu, _toggle_action, parent=menu))

        voice_action = QWidgetAction(menu)
        voice_action.setDefaultWidget(voice_widget)
        menu.addAction(voice_action)
        
        menu.addSeparator()

        # ── 2. Speed or "Voice Follow Active" (QStackedWidget so they occupy same space on mode switch) ─
        sm = (int(6 * scale), int(2 * scale), int(6 * scale), int(2 * scale)) if compact else (int(10 * scale), int(2 * scale), int(10 * scale), int(2 * scale))
        speed_section = QStackedWidget(menu)

        # Page 0: Notch mode — "Voice Follow Active"
        voice_follow_row = QWidget(menu)
        voice_follow_row_layout = QHBoxLayout(voice_follow_row)
        voice_follow_row_layout.setContentsMargins(0, 0, 0, 0)
        voice_follow_row_layout.setSpacing(0)
        voice_follow_lbl = QLabel("Voice Follow Active")
        voice_follow_lbl.setStyleSheet(f"""
            color: #88ccff;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {font_sz};
            background: transparent;
        """)
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(8)
        glow.setColor(QColor(0x40, 0x90, 0xff, 140))
        glow.setOffset(0, 0)
        voice_follow_lbl.setGraphicsEffect(glow)
        voice_follow_lbl.setCursor(Qt.ArrowCursor)
        voice_follow_row_layout.addWidget(voice_follow_lbl)
        voice_follow_row_layout.addStretch()
        speed_section.addWidget(voice_follow_row)

        # Page 1: Keys & Scroll — speed slider
        speed_row = QWidget(menu)
        speed_row_layout = QHBoxLayout(speed_row)
        speed_row_layout.setContentsMargins(0, 0, 0, 0)
        speed_row_layout.setSpacing(6 if compact else 8)
        speed_label = QLabel("Speed")
        speed_label.setStyleSheet(f"""
            color: #b0b0b0;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {font_sz};
        """)
        speed_row_layout.addWidget(speed_label)
        speed_slider = QSlider(Qt.Horizontal)
        speed_slider.setRange(1, 400)
        speed_slider.setValue(self._manual_wpm)
        speed_slider.setFixedWidth(int(60 * scale) if compact else int(70 * scale))
        speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #3a3a3c;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    fx:0.3, fy:0.3, stop:0 #ffffff, stop:1 #8e8e93);
                border-radius: 7px;
                border: 1px solid #555;
            }
            QSlider::handle:horizontal:hover {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    fx:0.3, fy:0.3, stop:0 #ffffff, stop:1 #007aff);
            }
        """)
        speed_row_layout.addWidget(speed_slider)
        speed_value = QLabel(str(self._manual_wpm))
        speed_value.setAlignment(Qt.AlignCenter)
        speed_value.setFixedSize(int(28 * scale), int(18 * scale))
        speed_value.setStyleSheet(f"""
            background-color: #2c2c2e;
            color: #b0b0b0;
            border-radius: 4px;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {int(10 * scale)}px;
        """)
        speed_row_layout.addWidget(speed_value)

        def _on_speed_change(value):
            speed_value.setText(str(value))
            self._set_speed(value, "manual")
        speed_slider.valueChanged.connect(_on_speed_change)

        speed_section.addWidget(speed_row)
        speed_section.setCurrentIndex(0 if self._voice_mode else 1)
        menu._speed_section = speed_section

        speed_widget = QWidget(menu)
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(*sm)
        speed_layout.setSpacing(6 if compact else 8)
        speed_layout.addWidget(speed_section)

        speed_action = QWidgetAction(menu)
        speed_action.setDefaultWidget(speed_widget)
        menu.addAction(speed_action)

        # ── 3. Font Size row with − / + buttons ──────────────────────
        font_widget = QWidget(menu)
        font_layout = QHBoxLayout(font_widget)
        font_layout.setContentsMargins(*sm)
        font_layout.setSpacing(6 if compact else 8)

        font_label = QLabel("Font Size")
        font_label.setStyleSheet(f"""
            color: #b0b0b0;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {font_sz};
        """)
        font_layout.addWidget(font_label)
        font_layout.addStretch()

        btn_font_sz = int(14 * scale)
        btn_sz = int(28 * scale)
        btn_style = f"""
            QPushButton {{
                background-color: #2c2c2e;
                color: #b0b0b0;
                border: 1px solid #444;
                border-radius: 4px;
                font-family: "Poppins", "Segoe UI", sans-serif;
                font-weight: 400;
                font-size: {btn_font_sz}px;
                min-width: {btn_sz}px;
                max-width: {btn_sz}px;
            }}
            QPushButton:hover {{
                background-color: #3a3a3c;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #007aff;
                color: #ffffff;
            }}
        """
        font_minus_btn = QPushButton("−")
        font_minus_btn.setStyleSheet(btn_style)
        font_minus_btn.setCursor(Qt.PointingHandCursor)
        font_minus_btn.clicked.connect(self._font_decrease)
        font_layout.addWidget(font_minus_btn)

        font_plus_btn = QPushButton("+")
        font_plus_btn.setStyleSheet(btn_style)
        font_plus_btn.setCursor(Qt.PointingHandCursor)
        font_plus_btn.clicked.connect(self._font_increase)
        font_layout.addWidget(font_plus_btn)

        font_action = QWidgetAction(menu)
        font_action.setDefaultWidget(font_widget)
        menu.addAction(font_action)

        # ── 3b. Font: cycle through Consolas, Arial, Open Sans, Times, Helvetica ──
        font_options = getattr(self, "FONT_OPTIONS", (("Consolas", "Consolas"), ("Arial", "Arial")))
        try:
            current_idx = next(i for i, (_, fam) in enumerate(font_options) if fam == self._font_family)
        except StopIteration:
            current_idx = 0
            self._font_family = font_options[0][1]
        display_name, family_name = font_options[current_idx]
        font_type_widget = QWidget(menu)
        font_type_layout = QHBoxLayout(font_type_widget)
        font_type_layout.setContentsMargins(*sm)
        font_type_layout.setSpacing(6 if compact else 8)
        font_type_label = QLabel("Font")
        font_type_label.setStyleSheet(f"""
            color: #b0b0b0;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {font_sz};
        """)
        font_type_layout.addWidget(font_type_label)
        font_type_layout.addStretch()
        font_type_btn = QPushButton(display_name)
        btn_font_size = int(9 * scale)
        font_type_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2c2c2e;
                color: #b0b0b0;
                border: 1px solid #444;
                border-radius: 4px;
                font-family: "{family_name}", sans-serif;
                font-weight: 400;
                font-size: {btn_font_size}px;
                min-width: {int(56 * scale)}px;
            }}
            QPushButton:hover {{
                background-color: #3a3a3c;
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: #007aff;
                color: #ffffff;
            }}
        """)
        font_type_btn.setCursor(Qt.PointingHandCursor)
        font_type_btn.setToolTip("Click to cycle: " + ", ".join(d for d, _ in font_options))
        def _apply_font_btn_style(btn, idx):
            disp, fam = font_options[idx]
            btn.setText(disp)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2c2c2e;
                    color: #b0b0b0;
                    border: 1px solid #444;
                    border-radius: 4px;
                    font-family: "{fam}", sans-serif;
                    font-weight: 400;
                    font-size: {btn_font_size}px;
                    min-width: {int(56 * scale)}px;
                }}
                QPushButton:hover {{
                    background-color: #3a3a3c;
                    color: #ffffff;
                }}
                QPushButton:pressed {{
                    background-color: #007aff;
                    color: #ffffff;
                }}
            """)
        def _toggle_font_type():
            try:
                idx = next(i for i, (_, fam) in enumerate(font_options) if fam == self._font_family)
            except StopIteration:
                idx = 0
            next_idx = (idx + 1) % len(font_options)
            _, next_family = font_options[next_idx]
            self._font_family = next_family
            self._text_edit.setFont(QFont(self._font_family, self._font_size))
            _apply_font_btn_style(font_type_btn, next_idx)
        font_type_btn.clicked.connect(_toggle_font_type)
        font_type_layout.addWidget(font_type_btn)
        font_type_action = QWidgetAction(menu)
        font_type_action.setDefaultWidget(font_type_widget)
        menu.addAction(font_type_action)

        # ── 3c. Theme: Dark / Light ──────────────────────────────────
        theme_widget = QWidget(menu)
        theme_layout = QHBoxLayout(theme_widget)
        theme_layout.setContentsMargins(*sm)
        theme_layout.setSpacing(6 if compact else 8)
        theme_label = QLabel("Theme")
        theme_label.setStyleSheet(f"""
            color: #b0b0b0;
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {font_sz};
        """)
        theme_layout.addWidget(theme_label)
        theme_layout.addStretch()
        theme_btn = QPushButton("Dark" if self._dark_theme else "Light")
        def _theme_btn_stylesheet(dark: bool) -> str:
            if dark:
                return f"""
                    QPushButton {{
                        background-color: #2c2c2e;
                        color: #b0b0b0;
                        border: 1px solid #444;
                        border-radius: 4px;
                        font-family: "Poppins", "Segoe UI", sans-serif;
                        font-weight: 400;
                        font-size: {int(9 * scale)}px;
                        min-width: {int(56 * scale)}px;
                    }}
                    QPushButton:hover {{
                        background-color: #3a3a3c;
                        color: #ffffff;
                    }}
                    QPushButton:pressed {{
                        background-color: #007aff;
                        color: #ffffff;
                    }}
                """
            else:
                return f"""
                    QPushButton {{
                        background-color: #ffffff;
                        color: #111111;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        font-family: "Poppins", "Segoe UI", sans-serif;
                        font-weight: 400;
                        font-size: {int(9 * scale)}px;
                        min-width: {int(56 * scale)}px;
                    }}
                    QPushButton:hover {{
                        background-color: #e8e8e8;
                        color: #111111;
                    }}
                    QPushButton:pressed {{
                        background-color: #007aff;
                        color: #ffffff;
                    }}
                """
        theme_btn.setStyleSheet(_theme_btn_stylesheet(self._dark_theme))
        theme_btn.setCursor(Qt.PointingHandCursor)
        theme_btn.setToolTip("Switch to light (white pill) or dark (black pill)")
        def _toggle_theme():
            self._dark_theme = not self._dark_theme
            theme_btn.setText("Dark" if self._dark_theme else "Light")
            theme_btn.setStyleSheet(_theme_btn_stylesheet(self._dark_theme))
            self._apply_read_mode_style()
            self.update()
            for btn in (self._close_btn, self._mic_btn, self._compact_btn, self._settings_btn):
                if btn:
                    btn.update()
            self._apply_highlight(self._matching.position if self._matching else -1)
        theme_btn.clicked.connect(_toggle_theme)
        theme_layout.addWidget(theme_btn)
        theme_action = QWidgetAction(menu)
        theme_action.setDefaultWidget(theme_widget)
        menu.addAction(theme_action)

        menu.addSeparator()

        # ── 4. Other Actions ─────────────────────────────────────────
        menu.addAction("Load Script...", self._load_file)
        menu.addAction("Help", self._show_help)
        menu.addAction("Setup", self._open_settings)
        menu.addAction("Quit", self.close)

        return menu

    def _open_menu_from_button(self):
        if self._edit_mode:
            return
        menu = self._build_menu()
        
        btn_pos = self._settings_btn.mapToGlobal(QPoint(0, 0))
        btn_w = self._settings_btn.width()
        btn_h = self._settings_btn.height()
        menu_size = menu.sizeHint()
        
        if self._compact_mode:
            # Place menu to the right of notch so it doesn't cover it
            x = btn_pos.x() + btn_w + 6
            y = btn_pos.y() + btn_h + 4
        else:
            # Align right edge of menu with right edge of button
            x = btn_pos.x() + btn_w - menu_size.width()
            y = btn_pos.y() + btn_h + 8
        menu.exec_(QPoint(x, y))

    def _show_menu(self, global_pos):
        if self._edit_mode:
            return
        menu = self._build_menu()
        menu.exec_(global_pos)

    def contextMenuEvent(self, event):
        self._show_menu(event.globalPos())

    # ═══════════════════════════════════════════════════════════════════
    #  Standard Logic (Load, Save, Drag)
    # ═══════════════════════════════════════════════════════════════════

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.RightButton:
            self._show_menu(event.globalPos())
            return
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".txt"):
                self._load_script_from_file(path)
                break

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Script", "", "Text Files (*.txt)")
        if path: self._load_script_from_file(path)

    def _load_script_from_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f: text = f.read()
            print(f"[Notch] Script loaded: {path}", flush=True)
            self._text_edit.setPlainText(text)
            self._text_edit.setAlignment(Qt.AlignCenter) 
            self._script_text = text
            self._matching.load_script(text)
            self._last_match_time = None
            self._last_match_pos = -1
            self._voice_wpm = 60
            self._manual_scroll_accum = 0.0
            self._voice_scroll_accum = 0.0
            self._voice_target_scroll = None
            self._checkpoints = {}
            self._apply_highlight(-1)
            self._text_edit.moveCursor(QTextCursor.Start)
            self._text_edit.verticalScrollBar().setValue(0)
            if self._voice_mode: self._start_listening()
        except: pass

    def _toggle_mode(self, checked):
        self._voice_mode = checked
        if self._voice_mode:
            self._start_listening()
        else:
            self._stop_listening()
            self._target_glow_alpha = 28  # Dim glow in manual mode
            self._smoothed_volume_level = 0.0
            self._manual_running = False
            self._manual_scroll_accum = 0.0
            self._voice_scroll_accum = 0.0
            self._voice_target_scroll = None

    def _refresh_menu_mode_display(self, menu):
        """Update mode tag, indicator, and speed section visibility so menu reflects current mode without closing."""
        if not hasattr(menu, "_mode_tag_label"):
            return
        scale = getattr(self, "_scale", 1.0)
        compact = getattr(self, "_compact_mode", False)
        tag_font = getattr(menu, "_mode_tag_font", "9px")
        ind_color = "#007aff" if self._voice_mode else "#4cd964"
        mode_tag = "Notch" if self._voice_mode else "Keys & Scroll"
        menu._mode_tag_label.setText(mode_tag)
        menu._mode_tag_label.setStyleSheet(f"""
            color: {ind_color};
            font-family: "Poppins", "Segoe UI", sans-serif;
            font-weight: 400;
            font-size: {tag_font};
            padding: 1px 6px;
            border: 1px solid {ind_color};
            border-radius: 6px;
            background: transparent;
        """)
        menu._mode_indicator.setStyleSheet(f"""
            background-color: {ind_color};
            border-radius: 4px;
        """)
        if hasattr(menu, "_speed_section"):
            menu._speed_section.setCurrentIndex(0 if self._voice_mode else 1)

    def _on_compact_width_anim_value(self, width_value):
        """Keep window centered while width animates (expand/contract from center)."""
        w = int(width_value)
        x = self._compact_anim_center_x - w // 2
        self.setGeometry(x, self._compact_anim_y, w, self._compact_anim_h)

    def _set_top_bar_icon_size(self, size: int):
        """Set all top bar icons to the same fixed size (e.g. 18 in narrow, 24 in wide)."""
        self._close_btn.setFixedSize(size, size)
        self._mic_btn.setFixedSize(size, size)
        self._compact_btn.setFixedSize(size, size)
        self._settings_btn.setFixedSize(size, size)

    def _on_compact_geometry_anim_finished(self):
        """Called when narrow/wide width animation finishes."""
        if self._compact_anim_going_narrow:
            self._center_top()
        else:
            self.setMinimumSize(self.MIN_W, self.MIN_H)  # restore min size after wide animation
            self._font_size = self._font_size_before_compact
            self._text_edit.setFont(QFont(self._font_family, self._font_size))
            self._size_before_compact = None
            self._center_top()

    def _toggle_compact_mode(self):
        """Switch between normal width and ~2-word width (smaller font), with animated width (centered)."""
        screen = QApplication.primaryScreen().availableGeometry()
        y = screen.y() + 8
        center_x = screen.x() + screen.width() // 2

        if self._compact_mode:
            # Animate to wide (normal): width grows, center stays fixed (set MIN_W after anim to avoid snap)
            self._compact_mode = False
            self._set_top_bar_icon_size(int(24 * self._scale))
            self._settings_btn.show()  # show settings again in wide mode
            self._compact_btn.set_compact(False)
            self._compact_btn.setToolTip("Narrow (2 words)")
            if self._size_before_compact is None:
                return
            target_w = self._size_before_compact.width()
            target_h = self._size_before_compact.height()
            self._compact_anim_going_narrow = False
            self._compact_anim_center_x = center_x
            self._compact_anim_y = y
            self._compact_anim_h = target_h
            self._compact_width_anim.stop()
            self._compact_width_anim.setStartValue(self.width())
            self._compact_width_anim.setEndValue(target_w)
            self._compact_width_anim.start()
        else:
            # Animate to narrow: set font first so text reflows, then animate width (center stays fixed)
            self._compact_mode = True
            self._set_top_bar_icon_size(int(18 * self._scale))
            self._settings_btn.hide()  # more space in narrow mode
            self._compact_btn.set_compact(True)
            self._compact_btn.setToolTip("Wide")
            self._size_before_compact = self.size()
            self._font_size_before_compact = self._font_size
            self.setMinimumSize(self.COMPACT_W, self.MIN_H)
            self._font_size = self.COMPACT_FONT
            self._text_edit.setFont(QFont(self._font_family, self._font_size))
            self._compact_anim_going_narrow = True
            self._compact_anim_center_x = center_x
            self._compact_anim_y = y
            self._compact_anim_h = self.height()
            self._compact_width_anim.stop()
            self._compact_width_anim.setStartValue(self.width())
            self._compact_width_anim.setEndValue(self.COMPACT_W)
            self._compact_width_anim.start()

    def _reset_position(self):
        self._text_edit.moveCursor(QTextCursor.Start)
        self._matching.reset()
        self._last_match_time = None
        self._last_match_pos = -1
        self._voice_wpm = 60
        self._manual_scroll_accum = 0.0
        self._voice_scroll_accum = 0.0
        self._voice_target_scroll = None
        self._checkpoints = {}
        self._apply_highlight(-1)

    def _font_increase(self):
        self._font_size += max(1, int(2 * self._scale))
        QTimer.singleShot(0, lambda: self._text_edit.setFont(QFont(self._font_family, self._font_size)))

    def _font_decrease(self):
        self._font_size = max(self.COMPACT_FONT, self._font_size - max(1, int(2 * self._scale)))
        QTimer.singleShot(0, lambda: self._text_edit.setFont(QFont(self._font_family, self._font_size)))

    def _set_speed(self, wpm, mode: str = "manual"):
        value = max(1, wpm)
        if mode == "voice":
            self._voice_wpm = value
        else:
            self._manual_wpm = value

    def _speed_step_for(self, value: int) -> int:
        # 5 levels of step size based on current speed
        if value < 10:
            return 1
        if value < 30:
            return 2
        if value < 60:
            return 5
        if value < 120:
            return 10
        return 20

    def _adjust_speed_dir(self, direction: int):
        if self._voice_mode:
            step = self._speed_step_for(self._voice_wpm)
            self._voice_wpm = max(1, self._voice_wpm + (step * direction))
        else:
            step = 10
            prev = self._manual_wpm
            self._manual_wpm = max(1, self._manual_wpm + (step * direction))
            delta = self._manual_wpm - prev
            if delta != 0:
                self._show_speed_feedback(delta)

    def _start_speed_feedback_fade_out(self):
        self._speed_feedback_fade_out.start()

    def _show_speed_feedback(self, delta: int):
        """Show a short popup: bottom right, less opaque, fade in/out 0.1s."""
        self._speed_feedback_timer.stop()
        self._speed_feedback_fade_in.stop()
        self._speed_feedback_fade_out.stop()
        self._speed_feedback_lbl.setText(f"Speed {delta:+d}")
        self._speed_feedback_lbl.adjustSize()
        margin = 8
        x = self.width() - self._speed_feedback_lbl.width() - margin
        y = self.height() - self._speed_feedback_lbl.height() - margin
        self._speed_feedback_lbl.move(x, y)
        self._speed_feedback_opacity.setOpacity(0.0)
        self._speed_feedback_lbl.show()
        self._speed_feedback_lbl.raise_()
        self._speed_feedback_fade_in.start()
        self._speed_feedback_timer.start(500)  # hold then fade out (total ~700ms)

    def _update_voice_speed(self, position: int, is_final: bool):
        now = time.monotonic()
        if self._last_match_time is not None and position > self._last_match_pos:
            delta_words = position - self._last_match_pos
            delta_time = now - self._last_match_time
            if delta_time > 0.2 and delta_words > 0:
                wpm = (delta_words / delta_time) * 60.0
                wpm = max(60.0, min(wpm, 300.0))
                if wpm > self._voice_wpm:
                    weight = 0.2 if is_final else 0.1
                    self._voice_wpm = int(round(self._voice_wpm + (wpm - self._voice_wpm) * weight))
        self._last_match_time = now
        self._last_match_pos = position

    def _doc_y_for_word(self, position: int) -> float:
        """Document Y (pixels from top) of the line containing the word at index.
        Uses line-within-block so wrapped paragraphs scroll correctly (notch is small)."""
        doc = self._text_edit.document()
        doc_layout = doc.documentLayout()
        start, _ = self._matching.word_span(position)
        cursor = QTextCursor(doc)
        cursor.setPosition(start)
        block = cursor.block()
        block_top = 0.0
        b = doc.firstBlock()
        while b.isValid() and b != block:
            block_top += doc_layout.blockBoundingRect(b).height()
            b = b.next()
        block_layout = block.layout()
        if block_layout is not None and block_layout.lineCount() > 0:
            pos_in_block = min(cursor.positionInBlock(), max(0, block.length() - 1))
            line = block_layout.lineForTextPosition(pos_in_block)
            line_y = line.position().y()
            return block_top + line_y
        return block_top

    def _target_scroll_for_reading_position(self, position: int) -> float:
        doc_y = self._doc_y_for_word(position)
        viewport_height = self._text_edit.viewport().height()
        bar = self._text_edit.verticalScrollBar()
        line_height = float(self._text_edit.fontMetrics().lineSpacing())
        # Narrow: scroll earlier and keep more lines ahead (small font = many lines visible)
        lines_below = 5.5 if self._compact_mode else 4
        target = doc_y - (viewport_height - lines_below * line_height)
        return max(0.0, min(float(bar.maximum()), target))

    def _scroll_to_word(self, position: int):
        start, _ = self._matching.word_span(position)
        cursor = QTextCursor(self._text_edit.document())
        cursor.setPosition(start)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.ensureCursorVisible()

    def _apply_read_mode_style(self):
        """Set text edit stylesheet for read mode (Notch/Keys & Scroll). Dark = white text, light = dark text."""
        color = "#111111" if not self._dark_theme else "#ffffff"
        self._text_edit.setStyleSheet(
            "QTextEdit {"
            "  background: transparent;"
            f"  color: {color};"
            "  border: none;"
            "}"
        )

    def _apply_highlight(self, position: int):
        if not self._script_text:
            return
        doc = self._text_edit.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()

        dim_hex = "#999999" if not self._dark_theme else "#7a7a7a"
        bright_hex = "#111111" if not self._dark_theme else "#ffffff"
        dim_format = QTextCharFormat()
        dim_format.setForeground(QColor(dim_hex))
        bright_format = QTextCharFormat()
        bright_format.setForeground(QColor(bright_hex))

        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(dim_format)

        if position >= 0:
            _, end = self._matching.word_span(position)
            cursor.setPosition(0)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.setCharFormat(bright_format)

        cursor.endEditBlock()

    def _center_top(self):
        screen = QApplication.primaryScreen()
        screen_geom = screen.availableGeometry()
        x = screen_geom.x() + (screen_geom.width() - self.width()) // 2
        # Small padding from top edge (8px)
        y = screen_geom.y() + 8
        self.move(x, y)

    def _show_help(self):
        """Open the How to use Notch guide (same as first-time popup)."""
        HelpDialog(self).exec_()

    def _open_settings(self):
        self._stop_listening()
        dlg = SettingsDialog(self._device_index, self._noise_gate, self._input_gain, self.MODEL_PATH, self)
        if dlg.exec_():
            self._device_index = dlg.selected_device
            self._noise_gate = dlg.noise_gate
            self._input_gain = dlg.input_gain
        if self._voice_mode: self._start_listening()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key_Escape:
            self.close()
            return

        if mods == Qt.ControlModifier and key == Qt.Key_R:
            self._reset_position()
            return

        if mods == Qt.ControlModifier and key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4):
            self._set_checkpoint(int(chr(key)))
            return

        if mods == (Qt.ControlModifier | Qt.ShiftModifier) and key in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4):
            self._go_to_checkpoint(int(chr(key)))
            return

        super().keyPressEvent(event)

    def _set_checkpoint(self, idx: int):
        bar = self._text_edit.verticalScrollBar()
        self._checkpoints[idx] = {
            "scroll": bar.value(),
            "match": self._last_match_pos,
        }

    def _toggle_manual_run(self):
        if not self._voice_mode:
            self._manual_running = not self._manual_running

    def _go_to_checkpoint(self, idx: int):
        cp = self._checkpoints.get(idx)
        if not cp:
            return
        if self._voice_mode:
            self._voice_mode = False
            self._stop_listening()
            self._target_glow_alpha = 28
            self._smoothed_volume_level = 0.0
        self._manual_running = False
        bar = self._text_edit.verticalScrollBar()
        bar.setValue(cp["scroll"])
        if cp["match"] is not None and cp["match"] >= 0:
            self._last_match_pos = cp["match"]
            self._apply_highlight(self._last_match_pos)
        else:
            self._apply_highlight(-1)

    def eventFilter(self, obj, event):
        if hasattr(self, "_text_edit") and (
            obj == self._text_edit or obj == self._text_edit.viewport()
        ):
            if event.type() == QEvent.ContextMenu:
                self._show_menu(event.globalPos())
                return True
            if event.type() == QEvent.MouseButtonDblClick:
                self._toggle_edit_mode()
                return True
            if event.type() == QEvent.Wheel and isinstance(event, QWheelEvent):
                bar = self._text_edit.verticalScrollBar()
                delta_y = event.angleDelta().y()
                if delta_y != 0:
                    self._last_manual_scroll_time = time.monotonic()  # so voice doesn't override for 2.5s
                    line_h = self._text_edit.fontMetrics().lineSpacing()
                    step = max(1, int(line_h * 0.45))  # ~0.45 lines per tick (less sensitive)
                    step = step * (1 if delta_y > 0 else -1)
                    bar.setValue(bar.value() - step)
                    # Move read position with scroll: up = undo words, down = complete words (skip back / skip ahead)
                    if self._script_text and self._matching.word_count > 0:
                        SCROLL_WORDS = 2
                        current = self._last_match_pos if self._last_match_pos >= 0 else 0
                        if delta_y > 0:  # scroll up -> move position back
                            new_pos = max(0, current - SCROLL_WORDS)
                            self._matching.set_position(new_pos)
                            self._last_match_pos = self._matching.position
                            self._apply_highlight(self._last_match_pos)
                        else:  # scroll down -> move position forward
                            new_pos = min(self._matching.word_count - 1, current + SCROLL_WORDS)
                            self._matching.set_position(new_pos)
                            self._last_match_pos = self._matching.position
                            self._apply_highlight(self._last_match_pos)
                return True
        return super().eventFilter(obj, event)

    def _clear_edit_mode_char_formats(self):
        """Clear character formats so all text uses stylesheet color (#111111) in edit mode. Deferred so expand animation starts without pause."""
        doc = self._text_edit.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#111111"))
        cursor.setCharFormat(fmt)

    def _on_edit_geometry_anim_finished(self):
        """Called when expand/collapse animation finishes. Text styling is handled by fade out/in."""
        if self._geometry_anim_entering:
            # Expansion finished (text styling already applied in fade out/in)
            pass
        else:
            # Collapse finished: styling already applied in _on_text_fade_out_finished
            if not self._compact_mode:
                self._settings_btn.show()
            else:
                self._settings_btn.hide()
            self._icons_container.show()
            self._icons_opacity.setOpacity(0.0)
            self._icon_fade_in.stop()
            self._icon_fade_in.start()
            self.clearMask()
            self.resize(self._collapsed_size)
            self._center_top()
            # Fade pill text in now that the pill is at its final size
            self._text_fade_in.start()
            if self._prev_voice_mode:
                self._voice_mode = True
                self._start_listening()

    def _update_collapse_mask(self):
        """Clip window to current pill shape during collapse so the top bar doesn't appear to separate."""
        w, h = self.width(), self.height()
        if w < 2 or h < 2:
            return
        bm = QBitmap(w, h)
        bm.fill(Qt.color0)
        p = QPainter(bm)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, self.CORNER_RADIUS, self.CORNER_RADIUS)
        p.fillPath(path, Qt.color1)
        p.end()
        self.setMask(QRegion(bm))

    def _toggle_edit_mode(self):
        # Ignore double-click while expand/collapse is animating (prevents wrong pill size and re-entrant _stop_listening)
        if self._geometry_anim.state() == QAbstractAnimation.Running:
            return
        if not self._edit_mode:
            # Expand: fade text out, apply edit mode, fade in (geometry anim runs in parallel)
            self.clearMask()
            self._geometry_anim_entering = True
            self._prev_voice_mode = self._voice_mode
            self._manual_running = False
            self._stop_listening()  # Non-blocking now; worker stops in background
            if self.width() < int(500 * self._scale) and self.height() < int(280 * self._scale):
                self._collapsed_size = self.size()
            self._icon_fade_out.stop()
            self._icons_opacity.setOpacity(1.0)
            self._icon_fade_out.start()
            self._text_fade_for_expand = True
            self._text_fade_out.start()
            screen = QApplication.primaryScreen().availableGeometry()
            tw, th = int(860 * self._scale), int(320 * self._scale)
            x = screen.x() + (screen.width() - tw) // 2
            y = screen.y() + 8
            self._geometry_anim.stop()
            self._geometry_anim.setStartValue(self.geometry())
            self._geometry_anim.setEndValue(QRect(x, y, tw, th))
            self._glow_anim.stop()
            self._glow_anim.setStartValue(float(self._current_glow_alpha))
            self._glow_anim.setEndValue(0.0)
            self._glow_anim.start()
            self._geometry_anim.start()
            return

        # Exit edit mode: fade text out (hides styling swap), shrink pill, fade text in when done
        self._geometry_anim_entering = False
        self._text_fade_for_expand = False
        self._text_fade_out.start()
        screen = QApplication.primaryScreen().availableGeometry()
        w = self._collapsed_size.width()
        h = self._collapsed_size.height()
        # If _collapsed_size was ever overwritten by spam (e.g. mid-animation), fall back to default pill size
        if w >= int(500 * self._scale) or h >= int(280 * self._scale):
            w, h = self.DEFAULT_W, self.DEFAULT_H
            self._collapsed_size = QSize(w, h)
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + 8
        self._geometry_anim.stop()
        self._geometry_anim.setStartValue(self.geometry())
        self._geometry_anim.setEndValue(QRect(x, y, w, h))
        self._glow_anim.stop()
        self._glow_anim.setStartValue(0.0)
        self._glow_anim.setEndValue(28.0)
        self._glow_anim.start()
        self._geometry_anim.start()

    def _apply_capture_exclusion(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            WDA_EXCLUDEFROMCAPTURE = 0x11
            WDA_MONITOR = 0x1
            ok = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if not ok:
                user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)
        except Exception:
            pass

    def _apply_blur_effect(self):
        """
        Blur effect disabled - Windows Acrylic/blur applies to the entire
        rectangular window, causing visible borders around the rounded pill.
        The solid dark background with 95% opacity already looks good.
        """
        pass

    def showEvent(self, event):
        super().showEvent(event)
        # First-time guide (persist with QSettings so we only show once per machine)
        settings = QSettings("Notch", "Notch")
        if not settings.value("guide_seen", False, type=bool):
            settings.setValue("guide_seen", True)
            QTimer.singleShot(300, self._show_help)  # Slight delay so overlay is visible first
        # Start fade-in animation
        if self._fade_anim.state() != QAbstractAnimation.Running:
            self._fade_anim.start()
        if self._voice_mode:
            print("[Notch] Voice mode on — starting mic + speech recognition", flush=True)
            self._start_listening()

    def closeEvent(self, event):
        self._scroll_timer.stop()
        self._stop_listening()
        super().closeEvent(event)
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NotchOverlay()
    window.show()
    sys.exit(app.exec_())