"""Reusable editors: target picker, action dialog, combo dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..keys import KEY_NAMES
from ..profile import MOUSE_TARGETS
from ..state import BUTTONS
from .i18n import tr

BUTTON_LABELS = {
    "cross": "✕ Cross",
    "circle": "○ Circle",
    "square": "□ Square",
    "triangle": "△ Triangle",
    "l1": "L1",
    "r1": "R1",
    "l2": "L2",
    "r2": "R2",
    "share": "Share",
    "options": "Options",
    "ps": "PS",
    "touchpad": "Touchpad click",
    "l3": "L3 (left stick click)",
    "r3": "R3 (right stick click)",
    "up": "D-pad up",
    "down": "D-pad down",
    "left": "D-pad left",
    "right": "D-pad right",
    "touch_left": "Touchpad left half",
    "touch_right": "Touchpad right half",
}
MOUSE_LABELS = {
    "left": "Left button",
    "right": "Right button",
    "middle": "Middle button",
    "wheel_up": "Wheel up",
    "wheel_down": "Wheel down",
}
KINDS = (("pad", "Controller button"), ("key", "Keyboard key"), ("mouse", "Mouse"))


def button_label(name: str) -> str:
    return tr(BUTTON_LABELS.get(name, name))


def target_label(target: str) -> str:
    kind, _, name = target.partition(":")
    if kind == "pad":
        return button_label(name)
    if kind == "mouse":
        return f"{tr('Mouse')}: {tr(MOUSE_LABELS.get(name, name))}"
    return f"{tr('Key')} {name.upper()}"


def action_label(action: dict, source: str | None = None) -> str:
    kind = action["type"]
    if kind == "none":
        return tr("Disabled")
    if kind == "macro":
        return f"{tr('Macro')}: {action['macro']}"
    targets = " + ".join(target_label(t) for t in action["to"])
    if kind == "turbo":
        return f"{tr('Turbo')} {action['hz']:.0f} Hz: {targets}"
    if kind == "toggle":
        return f"{tr('Toggle')}: {targets}"
    if source and action["to"] == [f"pad:{source}"]:
        return tr("Default")
    return targets


class TargetPicker(QWidget):
    """Pick one output target: a controller button, a key or a mouse action."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = QComboBox()
        for key, label in KINDS:
            self.kind.addItem(tr(label), key)
        self.name = QComboBox()
        self.name.setMinimumWidth(120)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.kind)
        row.addWidget(self.name, 1)
        self.kind.currentIndexChanged.connect(self._fill)
        self._fill()

    def _fill(self) -> None:
        kind = self.kind.currentData()
        self.name.clear()
        if kind == "pad":
            for name in BUTTONS:
                self.name.addItem(button_label(name), name)
        elif kind == "mouse":
            for name in MOUSE_TARGETS:
                self.name.addItem(tr(MOUSE_LABELS[name]), name)
        else:
            for name in KEY_NAMES:
                self.name.addItem(name.upper(), name)

    def value(self) -> str:
        return f"{self.kind.currentData()}:{self.name.currentData()}"


class TargetList(QWidget):
    """A small list of targets with add/remove."""

    def __init__(self, targets=(), parent=None):
        super().__init__(parent)
        self.targets = list(targets)
        self.view = QListWidget()
        self.view.setMaximumHeight(110)
        self.picker = TargetPicker()
        add = QPushButton(tr("Add"))
        remove = QPushButton(tr("Remove selected"))
        add.clicked.connect(self._add)
        remove.clicked.connect(self._remove)
        row = QHBoxLayout()
        row.addWidget(self.picker, 1)
        row.addWidget(add)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        layout.addLayout(row)
        layout.addWidget(remove, 0, Qt.AlignLeft)
        self._refresh()

    def _refresh(self) -> None:
        self.view.clear()
        self.view.addItems([target_label(t) for t in self.targets])

    def _add(self) -> None:
        value = self.picker.value()
        if value not in self.targets:
            self.targets.append(value)
            self._refresh()

    def _remove(self) -> None:
        row = self.view.currentRow()
        if 0 <= row < len(self.targets):
            del self.targets[row]
            self._refresh()


class ActionDialog(QDialog):
    TYPES = (
        ("button", "Press button(s) / key(s)"),
        ("turbo", "Turbo (rapid fire while held)"),
        ("toggle", "Toggle (press once to hold, again to release)"),
        ("macro", "Run a macro"),
        ("none", "Disabled"),
    )

    def __init__(self, title: str, action: dict, macros, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.kind = QComboBox()
        for key, label in self.TYPES:
            self.kind.addItem(tr(label), key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(action["type"])))
        self.targets = TargetList(action.get("to", []))
        self.hz = QDoubleSpinBox()
        self.hz.setRange(1, 30)
        self.hz.setDecimals(0)
        self.hz.setSuffix(" Hz")
        self.hz.setValue(action.get("hz", 12))
        self.macro = QComboBox()
        self.macro.addItems(sorted(macros))
        if action.get("macro") in macros:
            self.macro.setCurrentText(action["macro"])
        self.no_macros = QLabel(tr("No macros yet. Create one in the Macros tab first."))
        self.no_macros.setWordWrap(True)

        self.form = QFormLayout()
        self.form.addRow(tr("Action"), self.kind)
        self.form.addRow(tr("Sends"), self.targets)
        self.form.addRow(tr("Speed"), self.hz)
        self.form.addRow(tr("Macro"), self.macro)
        self.form.addRow("", self.no_macros)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self._sync)
        self._has_macros = bool(macros)
        self._sync()

    def _sync(self) -> None:
        kind = self.kind.currentData()
        self.form.setRowVisible(self.targets, kind in ("button", "turbo", "toggle"))
        self.form.setRowVisible(self.hz, kind == "turbo")
        self.form.setRowVisible(self.macro, kind == "macro" and self._has_macros)
        self.form.setRowVisible(self.no_macros, kind == "macro" and not self._has_macros)

    def action(self) -> dict:
        kind = self.kind.currentData()
        if kind == "macro":
            return {"type": "macro", "macro": self.macro.currentText()} if self._has_macros else {"type": "none"}
        if kind == "none" or not self.targets.targets:
            return {"type": "none"}
        out = {"type": kind, "to": list(self.targets.targets)}
        if kind == "turbo":
            out["hz"] = self.hz.value()
        return out


class ComboDialog(QDialog):
    """Choose the buttons of a combination; the action is edited afterwards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("New combo"))
        self.boxes: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        for index, name in enumerate(BUTTONS):
            box = QCheckBox(button_label(name))
            self.boxes[name] = box
            grid.addWidget(box, index // 3, index % 3)
        self.suppress = QCheckBox(tr("Do not send the individual buttons while the combo is held"))
        self.suppress.setChecked(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Pick two or more buttons that must be held together:")))
        layout.addLayout(grid)
        layout.addWidget(self.suppress)
        layout.addWidget(buttons)

    def buttons(self) -> list[str]:
        return [name for name, box in self.boxes.items() if box.isChecked()]


class LabeledSlider(QWidget):
    """Horizontal slider over a float range with its value shown next to it."""

    changed = Signal(float)

    def __init__(self, low: float, high: float, value: float, percent: bool = True, parent=None):
        super().__init__(parent)
        self.low, self.high, self.percent = low, high, percent
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 200)
        self.label = QLabel()
        self.label.setMinimumWidth(48)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.slider, 1)
        row.addWidget(self.label)
        self.set_value(value)
        self.slider.valueChanged.connect(self._moved)

    def value(self) -> float:
        return self.low + (self.high - self.low) * self.slider.value() / 200

    def set_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(round((value - self.low) / (self.high - self.low) * 200))
        self.slider.blockSignals(False)
        self._show()

    def _show(self) -> None:
        value = self.value()
        self.label.setText(f"{value * 100:.0f}%" if self.percent else f"{value:.2f}")

    def _moved(self) -> None:
        self._show()
        self.changed.emit(self.value())
