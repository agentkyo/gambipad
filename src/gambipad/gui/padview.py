"""Live drawing of the controller: what is pressed, sticks, triggers, touches."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..state import TOUCH_HEIGHT, TOUCH_WIDTH, PadState

W, H = 560.0, 360.0
BODY = QColor("#262b36")
EDGE = QColor("#3b4252")
IDLE = QColor("#4a5266")
TEXT = QColor("#cfd6e6")
ACCENT = QColor("#35c9a5")
GHOST = QColor("#e5534b")

FACE = {"triangle": (430, 128, "△"), "circle": (466, 164, "○"), "cross": (430, 200, "✕"), "square": (394, 164, "□")}
DPAD = {"up": (118, 132, 24, 30), "down": (118, 182, 24, 30), "left": (88, 160, 30, 24), "right": (142, 160, 30, 24)}


class PadView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state: PadState | None = None
        self.ghosted: frozenset[str] = frozenset()
        self.light = QColor(0, 0, 0)
        self.setMinimumSize(420, 270)

    def show_state(self, state: PadState | None, ghosted=frozenset(), light=(0, 0, 0)) -> None:
        self.state, self.ghosted, self.light = state, frozenset(ghosted), QColor(*light)
        self.update()

    def _fill(self, name: str) -> QColor:
        if name in self.ghosted:
            return GHOST
        if self.state is not None and name in self.state.buttons:
            return ACCENT
        return IDLE

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width() / W, self.height() / H)
        p.translate((self.width() - W * scale) / 2, (self.height() - H * scale) / 2)
        p.scale(scale, scale)
        state = self.state or PadState()
        p.setOpacity(1.0 if self.state is not None else 0.45)

        # triggers and shoulders
        for name, x, value in (("l2", 78, state.l2), ("r2", 398, state.r2)):
            box = QRectF(x, 14, 84, 30)
            p.setPen(QPen(EDGE, 2))
            p.setBrush(BODY)
            p.drawRoundedRect(box, 8, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(GHOST if name in self.ghosted else ACCENT)
            p.drawRoundedRect(QRectF(x + 3, 17, 78 * value, 24), 6, 6)
            self._label(p, box, f"{name.upper()}  {int(value * 100)}%")
        for name, x in (("l1", 78), ("r1", 398)):
            box = QRectF(x, 50, 84, 20)
            p.setPen(QPen(EDGE, 2))
            p.setBrush(self._fill(name))
            p.drawRoundedRect(box, 7, 7)
            self._label(p, box, name.upper())

        # body
        body = QPainterPath()
        body.addRoundedRect(QRectF(50, 78, 460, 180), 60, 60)
        for x in (50, 400):
            grip = QPainterPath()
            grip.addRoundedRect(QRectF(x, 150, 110, 190), 50, 50)
            body = body.united(grip)
        p.setPen(QPen(EDGE, 2))
        p.setBrush(BODY)
        p.drawPath(body)

        # light bar
        p.setPen(Qt.NoPen)
        p.setBrush(self.light if self.light.value() > 8 else QColor("#141821"))
        p.drawRoundedRect(QRectF(215, 80, 130, 7), 3, 3)

        # touchpad
        pad = QRectF(200, 96, 160, 78)
        p.setPen(QPen(EDGE, 2))
        p.setBrush(self._fill("touchpad"))
        p.drawRoundedRect(pad, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffd166"))
        for touch in state.touches:
            cx = pad.left() + pad.width() * min(1.0, touch.x / TOUCH_WIDTH)
            cy = pad.top() + pad.height() * min(1.0, touch.y / TOUCH_HEIGHT)
            p.drawEllipse(QPointF(cx, cy), 6, 6)

        # share / options / ps
        for name, x in (("share", 170), ("options", 372)):
            p.setPen(QPen(EDGE, 1.5))
            p.setBrush(self._fill(name))
            p.drawRoundedRect(QRectF(x, 102, 18, 30), 7, 7)
        p.setPen(QPen(EDGE, 2))
        p.setBrush(self._fill("ps"))
        p.drawEllipse(QPointF(280, 214), 15, 15)
        self._label(p, QRectF(265, 199, 30, 30), "PS")

        # d-pad
        for name, (x, y, w, h) in DPAD.items():
            p.setPen(QPen(EDGE, 1.5))
            p.setBrush(self._fill(name))
            p.drawRoundedRect(QRectF(x, y, w, h), 5, 5)

        # face buttons
        font = QFont(self.font())
        font.setPointSizeF(13)
        font.setBold(True)
        for name, (x, y, glyph) in FACE.items():
            p.setPen(QPen(EDGE, 2))
            p.setBrush(self._fill(name))
            p.drawEllipse(QPointF(x, y), 17, 17)
            p.setFont(font)
            p.setPen(TEXT)
            p.drawText(QRectF(x - 17, y - 17, 34, 34), Qt.AlignCenter, glyph)

        # sticks
        for name, cx, cy, sx, sy in (("l3", 204, 232, state.lx, state.ly), ("r3", 356, 232, state.rx, state.ry)):
            p.setPen(QPen(EDGE, 2))
            p.setBrush(QColor("#1b1f29"))
            p.drawEllipse(QPointF(cx, cy), 34, 34)
            p.setBrush(self._fill(name))
            p.drawEllipse(QPointF(cx + sx * 18, cy + sy * 18), 20, 20)

        p.end()

    def _label(self, p: QPainter, rect: QRectF, text: str) -> None:
        font = QFont(self.font())
        font.setPointSizeF(8)
        font.setBold(True)
        p.setFont(font)
        p.setPen(TEXT)
        p.drawText(rect, Qt.AlignCenter, text)
