"""The configuration window. It also hosts the driver while it is open."""
from __future__ import annotations

import collections
import copy
import json
import sys
import time

from PySide6.QtCore import QLockFile, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .. import profile as profiles
from ..driver import Driver
from ..engine import apply_ghosts, detect_ghosts, lightbar_color
from ..state import BUTTONS
from .i18n import LANGUAGES, set_language, tr
from .padview import PadView
from .widgets import (
    ActionDialog,
    ComboDialog,
    LabeledSlider,
    TargetPicker,
    action_label,
    button_label,
    target_label,
)

DIAGNOSE_SECONDS = 40

STYLE = """
QWidget { background: #1b1f29; color: #d8deea; font-size: 10pt; }
QGroupBox { border: 1px solid #333a4a; border-radius: 8px; margin-top: 14px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8fa1c2; }
QPushButton { background: #2c3342; border: 1px solid #3d4558; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #364056; }
QPushButton:disabled { color: #6c7486; }
QPushButton#primary { background: #1f8f76; border-color: #27a98c; color: white; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QListWidget, QPlainTextEdit {
  background: #232834; border: 1px solid #3d4558; border-radius: 6px; padding: 4px; }
QTabWidget::pane { border: 1px solid #333a4a; border-radius: 8px; }
QTabBar::tab { background: #232834; padding: 7px 11px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #2f3748; color: white; }
QLabel#hint { color: #8fa1c2; }
QLabel#warn { color: #f0b35a; }
QLabel#status { font-size: 11pt; font-weight: bold; }
"""


def app_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1f8f76"))
    p.drawRoundedRect(4, 16, 56, 34, 16, 16)
    p.setBrush(QColor("#ffffff"))
    p.drawRect(15, 30, 14, 5)
    p.drawRect(19, 26, 5, 14)
    p.drawEllipse(40, 25, 7, 7)
    p.drawEllipse(47, 33, 7, 7)
    p.end()
    return QIcon(pix)


def hint(text: str, name: str = "hint") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def scrolled(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = profiles.load_settings()
        set_language(self.settings["language"])
        if not profiles.list_profiles():
            profiles.save_profile(profiles.default_profile())
        self.profile = profiles.load_profile(self.settings["active_profile"])
        self._logs: collections.deque[str] = collections.deque(maxlen=200)
        self._log_dirty = False
        self._capture_end = 0.0
        self._found: list[list[str]] = []
        self._quitting = False

        self.setWindowTitle(f"GambiPad {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1120, 680)

        self.driver = Driver(self.profile, self.settings, log=self._log)
        self._build()
        self.driver.start()

        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(lambda: profiles.save_profile(self.profile))
        self._tick = QTimer(self, interval=33)
        self._tick.timeout.connect(self._refresh)
        self._tick.start()

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(app_icon(), self)
            menu = QMenu()
            menu.addAction(tr("Open GambiPad"), self._show)
            menu.addAction(tr("Quit"), self._quit)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip("GambiPad")
            self.tray.activated.connect(lambda reason: self._show() if reason == QSystemTrayIcon.Trigger else None)
            self.tray.show()

    # ------------------------------------------------------------- lifecycle

    def _log(self, text: str) -> None:  # called from the driver thread
        self._logs.append(f"{time.strftime('%H:%M:%S')}  {text}")
        self._log_dirty = True

    def _show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self._quitting = True
        self.close()

    def closeEvent(self, event) -> None:
        if self.tray and not self._quitting:
            event.ignore()
            self.hide()
            if not self.settings.get("_tray_told"):
                self.settings["_tray_told"] = True
                self.tray.showMessage("GambiPad", tr("Still running here in the tray. Right-click to quit."))
            return
        self._tick.stop()
        if self._save_timer.isActive():
            profiles.save_profile(self.profile)
        self.driver.stop()
        if self.tray:
            self.tray.hide()
        event.accept()
        QApplication.quit()

    def _changed(self) -> None:
        """The profile dict was edited: apply it live and save soon."""
        self.profile = profiles.normalize(self.profile)
        self.driver.set_profile(self.profile)
        self._save_timer.start()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)

        top = QHBoxLayout()
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top.addWidget(self.status, 1)
        top.addWidget(QLabel(tr("Profile")))
        self.profile_box = QComboBox()
        self.profile_box.setMinimumWidth(160)
        top.addWidget(self.profile_box)
        more = QPushButton(tr("Profiles…"))
        menu = QMenu(more)
        menu.addAction(tr("New"), self._profile_new)
        menu.addAction(tr("Duplicate"), self._profile_duplicate)
        menu.addAction(tr("Delete"), self._profile_delete)
        menu.addSeparator()
        menu.addAction(tr("Import…"), self._profile_import)
        menu.addAction(tr("Export…"), self._profile_export)
        more.setMenu(menu)
        top.addWidget(more)
        self.language = QComboBox()
        for code, label in LANGUAGES:
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(self.settings["language"])))
        self.language.currentIndexChanged.connect(self._language_changed)
        top.addWidget(self.language)
        outer.addLayout(top)

        self.note = hint("", "warn")
        outer.addWidget(self.note)

        middle = QHBoxLayout()
        left = QVBoxLayout()
        self.view_mode = QComboBox()
        self.view_mode.addItem(tr("Show what the controller sends"), "raw")
        self.view_mode.addItem(tr("Show what the game receives"), "out")
        left.addWidget(self.view_mode)
        self.pad_view = PadView()
        left.addWidget(self.pad_view, 1)
        self.live = hint("")
        left.addWidget(self.live)
        middle.addLayout(left, 5)
        self.tabs = QTabWidget()
        middle.addWidget(self.tabs, 6)
        outer.addLayout(middle, 1)
        self.setCentralWidget(root)

        self._fill_profiles()
        self.profile_box.currentTextChanged.connect(self._profile_selected)
        self._reload()

    def _fill_profiles(self) -> None:
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        self.profile_box.addItems(profiles.list_profiles())
        self.profile_box.setCurrentText(self.profile["name"])
        self.profile_box.blockSignals(False)

    def _reload(self) -> None:
        """Rebuild every page from the current profile."""
        current = max(0, self.tabs.currentIndex())
        self.tabs.clear()
        for title, builder in (
            (tr("Buttons"), self._page_buttons),
            (tr("Sticks"), self._page_sticks),
            (tr("Light && rumble"), self._page_light),
            (tr("Touchpad"), self._page_touchpad),
            (tr("Macros"), self._page_macros),
            (tr("Diagnose"), self._page_diagnose),
        ):
            self.tabs.addTab(scrolled(builder()), title)
        self.tabs.setCurrentIndex(current)

    # --------------------------------------------------------------- profiles

    def _switch(self, profile: dict) -> None:
        self.profile = profiles.normalize(profile)
        profiles.save_profile(self.profile)
        self.settings["active_profile"] = self.profile["name"]
        profiles.save_settings(self.settings)
        self.driver.set_profile(self.profile)
        self._fill_profiles()
        self._reload()

    def _profile_selected(self, name: str) -> None:
        if name and name != self.profile["name"]:
            profiles.save_profile(self.profile)
            self._switch(profiles.load_profile(name))

    def _ask_name(self, title: str, suggestion: str) -> str | None:
        name, ok = QInputDialog.getText(self, title, tr("Profile name:"), text=suggestion)
        name = name.strip()
        if not ok or not name:
            return None
        if name in profiles.list_profiles():
            QMessageBox.warning(self, title, tr("A profile with this name already exists."))
            return None
        return name

    def _profile_new(self) -> None:
        name = self._ask_name(tr("New profile"), tr("My profile"))
        if name:
            fresh = profiles.default_profile(name)
            fresh["ghosts"] = copy.deepcopy(self.profile["ghosts"])  # the pad's defects do not change
            self._switch(fresh)

    def _profile_duplicate(self) -> None:
        name = self._ask_name(tr("Duplicate profile"), self.profile["name"] + " 2")
        if name:
            clone = copy.deepcopy(self.profile)
            clone["name"] = name
            self._switch(clone)

    def _profile_delete(self) -> None:
        if len(profiles.list_profiles()) <= 1:
            QMessageBox.information(self, tr("Delete"), tr("This is the only profile."))
            return
        question = tr("Delete the profile “{name}”?").format(name=self.profile["name"])
        if QMessageBox.question(self, tr("Delete"), question) != QMessageBox.Yes:
            return
        self._save_timer.stop()
        profiles.delete_profile(self.profile["name"])
        self._switch(profiles.load_profile(profiles.list_profiles()[0]))

    def _profile_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Import…"), "", "GambiPad (*.json)")
        if not path:
            return
        try:
            data = profiles.load_profile_file(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr("Import…"), str(error))
            return
        names = profiles.list_profiles()
        base, n = data["name"], 2
        while data["name"] in names:
            data["name"] = f"{base} {n}"
            n += 1
        self._switch(data)

    def _profile_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Export…"), f"{self.profile['name']}.json", "GambiPad (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.profile, handle, indent=2, ensure_ascii=False)

    def _language_changed(self) -> None:
        self.settings["language"] = self.language.currentData()
        profiles.save_settings(self.settings)
        QMessageBox.information(self, "GambiPad", tr("The language changes the next time GambiPad starts."))

    # ---------------------------------------------------------- page: buttons

    def _page_buttons(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(hint(tr("Click a button to choose what it does. Changes apply immediately.")))
        grid = QGridLayout()
        sources = BUTTONS if self.profile["touchpad"]["mode"] != "buttons" else BUTTONS + ("touch_left", "touch_right")
        for row, source in enumerate(sources):
            grid.addWidget(QLabel(button_label(source)), row, 0)
            button = QPushButton(action_label(self.profile["buttons"][source], source))
            button.clicked.connect(lambda _=False, s=source, b=button: self._edit_button(s, b))
            grid.addWidget(button, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        out = QGroupBox(tr("Virtual controller"))
        form = QFormLayout(out)
        box = QComboBox()
        box.addItem(tr("Xbox 360 (works everywhere)"), "xbox360")
        box.addItem(tr("DualShock 4 (touchpad and motion; Windows only)"), "ds4")
        box.addItem(tr("None (keyboard/mouse mappings only)"), "none")
        box.setCurrentIndex(max(0, box.findData(self.profile["output"])))
        box.currentIndexChanged.connect(lambda: self._set(("output",), box.currentData()))
        form.addRow(tr("Games see"), box)
        layout.addWidget(out)
        reset = QPushButton(tr("Reset all buttons to default"))
        reset.clicked.connect(self._reset_buttons)
        layout.addWidget(reset, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return page

    def _set(self, path: tuple, value) -> None:
        node = self.profile
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        self._changed()

    def _edit_button(self, source: str, button: QPushButton) -> None:
        dialog = ActionDialog(button_label(source), self.profile["buttons"][source], self.profile["macros"], self)
        if dialog.exec():
            self.profile["buttons"][source] = dialog.action()
            self._changed()
            button.setText(action_label(self.profile["buttons"][source], source))

    def _reset_buttons(self) -> None:
        self.profile["buttons"] = profiles.default_profile()["buttons"]
        self._changed()
        self._reload()

    # ----------------------------------------------------------- page: sticks

    def _page_sticks(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        for side, title in (("left", tr("Left stick")), ("right", tr("Right stick"))):
            cfg = self.profile["sticks"][side]
            group = QGroupBox(title)
            form = QFormLayout(group)
            for key, label, low, high, percent in (
                ("deadzone", tr("Dead zone"), 0.0, 0.5, True),
                ("outer", tr("Full tilt reached at"), 0.5, 1.0, True),
                ("curve", tr("Curve (1 = linear, more = finer aim)"), 0.5, 3.0, False),
            ):
                slider = LabeledSlider(low, high, cfg[key], percent)
                slider.changed.connect(lambda v, s=side, k=key: self._set(("sticks", s, k), v))
                form.addRow(label, slider)
            for key, label in (("invert_x", tr("Invert horizontal")), ("invert_y", tr("Invert vertical"))):
                box = QCheckBox(label)
                box.setChecked(cfg[key])
                box.toggled.connect(lambda v, s=side, k=key: self._set(("sticks", s, k), v))
                form.addRow("", box)
            layout.addWidget(group)
        swap = QCheckBox(tr("Swap left and right sticks"))
        swap.setChecked(self.profile["sticks"]["swap"])
        swap.toggled.connect(lambda v: self._set(("sticks", "swap"), v))
        layout.addWidget(swap)
        for side in ("l2", "r2"):
            cfg = self.profile["triggers"][side]
            group = QGroupBox(f"{tr('Trigger')} {side.upper()}")
            form = QFormLayout(group)
            for key, label, low, high in (("deadzone", tr("Dead zone"), 0.0, 0.5), ("max", tr("Full press reached at"), 0.3, 1.0)):
                slider = LabeledSlider(low, high, cfg[key])
                slider.changed.connect(lambda v, s=side, k=key: self._set(("triggers", s, k), v))
                form.addRow(label, slider)
            hair = QCheckBox(tr("Hair trigger (any press counts as a full press)"))
            hair.setChecked(cfg["hair"])
            hair.toggled.connect(lambda v, s=side: self._set(("triggers", s, "hair"), v))
            form.addRow("", hair)
            layout.addWidget(group)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------ page: light

    def _page_light(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        cfg = self.profile["lightbar"]
        light = QGroupBox(tr("Light bar"))
        form = QFormLayout(light)
        mode = QComboBox()
        for key, label in (
            ("static", tr("Fixed colour")),
            ("battery", tr("Battery level (green to red)")),
            ("rainbow", tr("Rainbow")),
            ("off", tr("Off")),
        ):
            mode.addItem(label, key)
        mode.setCurrentIndex(max(0, mode.findData(cfg["mode"])))
        mode.currentIndexChanged.connect(lambda: self._set(("lightbar", "mode"), mode.currentData()))
        form.addRow(tr("Mode"), mode)
        swatch = QPushButton()
        swatch.setFixedWidth(120)

        def paint():
            swatch.setStyleSheet("background: rgb({},{},{});".format(*self.profile["lightbar"]["color"]))

        def choose():
            color = QColorDialog.getColor(QColor(*self.profile["lightbar"]["color"]), self, tr("Colour"))
            if color.isValid():
                self._set(("lightbar", "color"), [color.red(), color.green(), color.blue()])
                paint()

        paint()
        swatch.clicked.connect(choose)
        form.addRow(tr("Colour"), swatch)
        bright = LabeledSlider(0.0, 1.0, cfg["brightness"])
        bright.changed.connect(lambda v: self._set(("lightbar", "brightness"), v))
        form.addRow(tr("Brightness"), bright)
        layout.addWidget(light)

        rcfg = self.profile["rumble"]
        rumble = QGroupBox(tr("Rumble"))
        form = QFormLayout(rumble)
        enabled = QCheckBox(tr("Let games vibrate the controller"))
        enabled.setChecked(rcfg["enabled"])
        enabled.toggled.connect(lambda v: self._set(("rumble", "enabled"), v))
        form.addRow("", enabled)
        for key, label, weak, strong in (
            ("strong", tr("Strong motor (left)"), 0, 255),
            ("weak", tr("Weak motor (right)"), 255, 0),
        ):
            slider = LabeledSlider(0.0, 2.0, rcfg[key])
            slider.changed.connect(lambda v, k=key: self._set(("rumble", k), v))
            test = QPushButton(tr("Test"))
            test.clicked.connect(lambda _=False, w=weak, s=strong: self.driver.test_rumble(w, s))
            row = QHBoxLayout()
            row.addWidget(slider, 1)
            row.addWidget(test)
            form.addRow(label, row)
        layout.addWidget(rumble)
        layout.addStretch(1)
        return page

    # --------------------------------------------------------- page: touchpad

    def _page_touchpad(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        cfg = self.profile["touchpad"]
        group = QGroupBox(tr("Touchpad"))
        form = QFormLayout(group)
        mode = QComboBox()
        for key, label in (
            ("native", tr("Pass through (needs the DualShock 4 virtual controller)")),
            ("mouse", tr("Move the mouse pointer")),
            ("buttons", tr("Two buttons: left half and right half")),
            ("off", tr("Ignore touches")),
        ):
            mode.addItem(label, key)
        mode.setCurrentIndex(max(0, mode.findData(cfg["mode"])))

        def set_mode():
            self._set(("touchpad", "mode"), mode.currentData())
            QTimer.singleShot(0, self._reload)  # the Buttons page gains or loses the two halves

        mode.currentIndexChanged.connect(set_mode)
        form.addRow(tr("Mode"), mode)
        speed = LabeledSlider(0.1, 5.0, cfg["sensitivity"], percent=False)
        speed.changed.connect(lambda v: self._set(("touchpad", "sensitivity"), v))
        form.addRow(tr("Pointer speed"), speed)
        frozen = QCheckBox(tr("Ignore touches that never move (clones that report a finger that is not there)"))
        frozen.setChecked(cfg["drop_frozen"])
        frozen.toggled.connect(lambda v: self._set(("touchpad", "drop_frozen"), v))
        form.addRow("", frozen)
        layout.addWidget(group)
        layout.addWidget(
            hint(
                tr(
                    "Many clones have no real touch sensor: the touchpad is only a button. "
                    "Watch the yellow dots on the drawing while you slide a finger to find out."
                )
            )
        )
        layout.addStretch(1)
        return page

    # ----------------------------------------------------------- page: macros

    def _page_macros(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        macros = self.profile["macros"]

        group = QGroupBox(tr("Macros"))
        box = QVBoxLayout(group)
        row = QHBoxLayout()
        self.macro_box = QComboBox()
        self.macro_box.addItems(sorted(macros))
        if getattr(self, "_macro_name", None) in macros:
            self.macro_box.setCurrentText(self._macro_name)
        self.macro_box.currentTextChanged.connect(self._macro_selected)
        add = QPushButton(tr("New macro"))
        add.clicked.connect(self._macro_new)
        delete = QPushButton(tr("Delete macro"))
        delete.clicked.connect(self._macro_delete)
        row.addWidget(self.macro_box, 1)
        row.addWidget(add)
        row.addWidget(delete)
        box.addLayout(row)

        name = self.macro_box.currentText()
        self._macro_name = name
        if name:
            macro = macros[name]
            mode = QComboBox()
            for key, label in (
                ("once", tr("Play once per press")),
                ("hold", tr("Repeat while the button is held")),
                ("toggle", tr("Repeat until the button is pressed again")),
            ):
                mode.addItem(label, key)
            mode.setCurrentIndex(max(0, mode.findData(macro["mode"])))
            mode.currentIndexChanged.connect(lambda: self._set(("macros", name, "mode"), mode.currentData()))
            box.addWidget(mode)
            self.steps = QListWidget()
            self.steps.setMinimumHeight(130)
            for step in macro["steps"]:
                self.steps.addItem(self._step_label(step))
            box.addWidget(self.steps)

            add_row = QHBoxLayout()
            kind = QComboBox()
            for key, label in (("tap", tr("Tap")), ("press", tr("Hold down")), ("release", tr("Release")), ("wait", tr("Wait"))):
                kind.addItem(label, key)
            picker = TargetPicker()
            ms = QSpinBox()
            ms.setRange(20, 60000)
            ms.setValue(50)
            ms.setSuffix(" ms")
            plus = QPushButton(tr("Add step"))

            def sync():
                picker.setEnabled(kind.currentData() != "wait")
                ms.setEnabled(kind.currentData() in ("tap", "wait"))

            def add_step():
                what = kind.currentData()
                if what == "wait":
                    step = {"wait": ms.value()}
                elif what == "tap":
                    step = {"tap": picker.value(), "ms": ms.value()}
                else:
                    step = {what: picker.value()}
                macro["steps"].append(step)
                self._changed()
                self._reload()

            kind.currentIndexChanged.connect(sync)
            sync()
            plus.clicked.connect(add_step)
            add_row.addWidget(kind)
            add_row.addWidget(picker, 1)
            box.addLayout(add_row)
            add_row2 = QHBoxLayout()
            add_row2.addWidget(ms)
            add_row2.addWidget(plus)
            add_row2.addStretch(1)
            box.addLayout(add_row2)

            edit_row = QHBoxLayout()
            for label, delta in ((tr("Remove step"), 0), (tr("Move up"), -1), (tr("Move down"), 1)):
                button = QPushButton(label)
                button.clicked.connect(lambda _=False, d=delta: self._step_edit(name, d))
                edit_row.addWidget(button)
            edit_row.addStretch(1)
            box.addLayout(edit_row)
            box.addWidget(hint(tr("To use a macro, open the Buttons tab, click a button and choose “Run a macro”.")))
        else:
            box.addWidget(hint(tr("A macro is a recorded sequence of presses and pauses played by one button.")))
        layout.addWidget(group)

        combos = QGroupBox(tr("Combos"))
        cbox = QVBoxLayout(combos)
        cbox.addWidget(hint(tr("A combo fires an action when several buttons are held together.")))
        self.combo_list = QListWidget()
        self.combo_list.setMaximumHeight(110)
        for combo in self.profile["combos"]:
            held = " + ".join(button_label(b) for b in combo["buttons"])
            self.combo_list.addItem(f"{held}  →  {action_label(combo['action'])}")
        cbox.addWidget(self.combo_list)
        crow = QHBoxLayout()
        new = QPushButton(tr("New combo"))
        new.clicked.connect(self._combo_new)
        remove = QPushButton(tr("Remove combo"))
        remove.clicked.connect(self._combo_remove)
        crow.addWidget(new)
        crow.addWidget(remove)
        crow.addStretch(1)
        cbox.addLayout(crow)
        layout.addWidget(combos)
        layout.addStretch(1)
        return page

    def _step_label(self, step: dict) -> str:
        if "wait" in step:
            return f"{tr('Wait')} {step['wait']} ms"
        if "tap" in step:
            return f"{tr('Tap')} {target_label(step['tap'])} ({step['ms']} ms)"
        if "press" in step:
            return f"{tr('Hold down')} {target_label(step['press'])}"
        return f"{tr('Release')} {target_label(step['release'])}"

    def _macro_selected(self, name: str) -> None:
        self._macro_name = name
        QTimer.singleShot(0, self._reload)

    def _macro_new(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New macro"), tr("Macro name:"))
        name = name.strip()
        if ok and name and name not in self.profile["macros"]:
            self.profile["macros"][name] = {"mode": "once", "steps": []}
            self._macro_name = name
            self._changed()
            self._reload()

    def _macro_delete(self) -> None:
        name = self.macro_box.currentText()
        if name:
            del self.profile["macros"][name]
            self._changed()  # normalize() disables buttons that pointed at it
            self._reload()

    def _step_edit(self, name: str, delta: int) -> None:
        steps = self.profile["macros"][name]["steps"]
        row = self.steps.currentRow()
        if not 0 <= row < len(steps):
            return
        if delta == 0:
            del steps[row]
        elif 0 <= row + delta < len(steps):
            steps[row], steps[row + delta] = steps[row + delta], steps[row]
        else:
            return
        self._changed()
        self._reload()

    def _combo_new(self) -> None:
        dialog = ComboDialog(self)
        if not dialog.exec():
            return
        buttons = dialog.buttons()
        if len(buttons) < 2:
            QMessageBox.information(self, tr("New combo"), tr("Pick at least two buttons."))
            return
        title = " + ".join(button_label(b) for b in buttons)
        action = ActionDialog(title, {"type": "button", "to": []}, self.profile["macros"], self)
        if action.exec() and action.action()["type"] != "none":
            self.profile["combos"].append({"buttons": buttons, "action": action.action(), "suppress": dialog.suppress.isChecked()})
            self._changed()
            self._reload()

    def _combo_remove(self) -> None:
        row = self.combo_list.currentRow()
        if 0 <= row < len(self.profile["combos"]):
            del self.profile["combos"][row]
            self._changed()
            self._reload()

    # --------------------------------------------------------- page: diagnose

    def _page_diagnose(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        group = QGroupBox(tr("Ghost button test"))
        box = QVBoxLayout(group)
        box.addWidget(
            hint(
                tr(
                    "Some clones report a second button together with the one you pressed (for example L1 also "
                    "sending PS). Start the test and press every button, ONE AT A TIME, for about a second each."
                )
            )
        )
        self.diag_start = QPushButton(tr("Start the test"))
        self.diag_start.setObjectName("primary")
        self.diag_start.clicked.connect(self._diagnose_start)
        box.addWidget(self.diag_start, 0, Qt.AlignLeft)
        self.diag_bar = QProgressBar()
        self.diag_bar.setRange(0, DIAGNOSE_SECONDS * 10)
        self.diag_bar.setTextVisible(False)
        box.addWidget(self.diag_bar)
        self.diag_text = hint("")
        box.addWidget(self.diag_text)
        self.diag_apply = QPushButton(tr("Apply the fix"))
        self.diag_apply.setObjectName("primary")
        self.diag_apply.setVisible(False)
        self.diag_apply.clicked.connect(self._diagnose_apply)
        box.addWidget(self.diag_apply, 0, Qt.AlignLeft)
        layout.addWidget(group)

        fixes = QGroupBox(tr("Active fixes"))
        fbox = QVBoxLayout(fixes)
        self.fix_list = QListWidget()
        self.fix_list.setMaximumHeight(90)
        for trigger, ghost in self.profile["ghosts"]:
            self.fix_list.addItem(
                tr("While {a} is held, ignore {b}").format(a=button_label(trigger), b=button_label(ghost))
            )
        fbox.addWidget(self.fix_list)
        remove = QPushButton(tr("Remove selected"))
        remove.clicked.connect(self._fix_remove)
        fbox.addWidget(remove, 0, Qt.AlignLeft)
        layout.addWidget(fixes)

        logs = QGroupBox(tr("Driver log"))
        lbox = QVBoxLayout(logs)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        self.log_view.setPlainText("\n".join(self._logs))
        lbox.addWidget(self.log_view)
        layout.addWidget(logs)
        layout.addStretch(1)
        return page

    def _diagnose_start(self) -> None:
        if self.driver.raw is None:
            self.diag_text.setText(tr("No controller connected."))
            return
        self._found = []
        self.diag_apply.setVisible(False)
        self.diag_start.setEnabled(False)
        self.driver.start_capture()
        self._capture_end = time.monotonic() + DIAGNOSE_SECONDS

    def _diagnose_tick(self) -> None:
        left = self._capture_end - time.monotonic()
        samples = self.driver.capture or []
        seen = {b for s in samples[-20000:] for b in s} | getattr(self, "_diag_seen", set())
        self._diag_seen = seen
        missing = [button_label(b) for b in BUTTONS if b not in seen]
        try:
            if left > 0:
                self.diag_bar.setValue(int((DIAGNOSE_SECONDS - left) * 10))
                rest = ", ".join(missing) if missing else tr("all buttons seen, you can wait or keep pressing")
                self.diag_text.setText(tr("{n} s left. Still to press: {rest}").format(n=int(left) + 1, rest=rest))
                return
            self._capture_end = 0.0
            self._diag_seen = set()
            samples = self.driver.stop_capture()
            self._found = [pair for pair in detect_ghosts(samples) if pair not in self.profile["ghosts"]]
            self.diag_bar.setValue(0)
            self.diag_start.setEnabled(True)
            lines = []
            if missing:
                lines.append(tr("Never detected: {rest}").format(rest=", ".join(missing)))
            if self._found:
                for trigger, ghost in self._found:
                    lines.append(
                        tr("Found: pressing {a} also reports {b}").format(a=button_label(trigger), b=button_label(ghost))
                    )
            else:
                lines.append(tr("No new ghost buttons found."))
            self.diag_text.setText("\n".join(lines))
            self.diag_apply.setVisible(bool(self._found))
        except RuntimeError:  # the page was rebuilt while the test ran
            self._capture_end = 0.0
            self.driver.stop_capture()

    def _diagnose_apply(self) -> None:
        self.profile["ghosts"] = self.profile["ghosts"] + self._found
        self._found = []
        self._changed()
        self._reload()

    def _fix_remove(self) -> None:
        row = self.fix_list.currentRow()
        if 0 <= row < len(self.profile["ghosts"]):
            del self.profile["ghosts"][row]
            self._changed()
            self._reload()

    # ---------------------------------------------------------------- refresh

    def _refresh(self) -> None:
        driver = self.driver
        raw, frame = driver.raw, driver.frame
        if driver.status == "running" and raw is not None:
            battery = "" if raw.battery is None else f"  ·  {tr('battery')} {raw.battery}%{' ⚡' if raw.charging else ''}"
            bus = "Bluetooth" if driver.bluetooth else "USB"
            self.status.setText(f"🟢 {driver.device_name}  ·  {bus}{battery}")
        elif driver.status.startswith("error"):
            self.status.setText(f"🔴 {driver.status}")
        else:
            self.status.setText(f"🟡 {tr('Looking for a controller… plug it in.')}")

        notes = []
        defect = getattr(driver, "defect", "")
        if defect == "smear":
            notes.append(
                tr(
                    "DEFECTIVE CONTROLLER: it corrupts its own data (every fourth byte repeats the one before). "
                    "Right stick left/right, PS and touchpad never arrive, so they are disabled. "
                    "Try another cable or USB port, or Bluetooth."
                )
            )
        if driver.output_note:
            notes.append(driver.output_note)
        if driver.status == "running" and driver.hide_note not in ("hidden", "not hidden", ""):
            notes.append(driver.hide_note)
        elif driver.status == "running" and driver.hide_note == "hidden":
            notes.append(
                tr("The real controller is hidden from games. If a game still sees two controllers, unplug and replug it once.")
            )
        text = "  ·  ".join(notes)
        if text != self.note.text():
            self.note.setText(text)
            self.note.setObjectName("warn" if driver.output_note or defect else "hint")
            self.note.setStyleSheet("")  # re-polish for the new object name

        if raw is None:
            self.pad_view.show_state(None)
            self.live.setText("")
        else:
            light = lightbar_color(self.profile["lightbar"], raw, time.monotonic())
            if self.view_mode.currentData() == "raw" or frame is None:
                ghosted = raw.buttons - apply_ghosts(set(raw.buttons), self.profile["ghosts"])
                self.pad_view.show_state(raw, ghosted, light)
            else:
                self.pad_view.show_state(frame.pad, (), light)
            extra = []
            if self.pad_view.ghosted:
                extra.append(tr("red = ghost signal being ignored"))
            if frame is not None and frame.keys:
                extra.append(tr("keys") + ": " + " ".join(sorted(k.upper() for k in frame.keys)))
            if frame is not None and frame.mouse_buttons:
                extra.append(tr("mouse") + ": " + " ".join(sorted(frame.mouse_buttons)))
            self.live.setText(f"{driver.reports_per_second} Hz" + ("  ·  " + "  ·  ".join(extra) if extra else ""))

        if self._capture_end:
            self._diagnose_tick()
        if self._log_dirty:
            self._log_dirty = False
            try:
                self.log_view.setPlainText("\n".join(self._logs))
            except RuntimeError:
                pass


def run(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("GambiPad")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    profiles.config_dir().mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(profiles.config_dir() / "gambipad.lock"))
    if not lock.tryLock(100):
        set_language(profiles.load_settings()["language"])
        QMessageBox.information(None, "GambiPad", tr("GambiPad is already running (look in the system tray)."))
        return 0
    window = MainWindow()
    if "--minimized" not in argv or window.tray is None:
        window.show()
    code = app.exec()
    lock.unlock()
    return code
