import sys
import time
import ctypes
import re
import json
from pathlib import Path


from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    Slot,
    QTimer,
    QUrl,
    QObject,
    QEvent,
)

from PySide6.QtGui import (
    QFont,
    QImage,
    QPalette,
    QPixmap,
    QShortcut,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QKeySequence,
)

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import boltu_core


# ============================================================
# Windows title bar
# ============================================================

def apply_windows_dark_titlebar(window):
    """Ask Windows to render the native title bar in dark mode."""
    if sys.platform != "win32":
        return

    try:
        hwnd = int(window.winId())
        dwmapi = ctypes.windll.dwmapi
        use_dark_mode = ctypes.c_int(1)

        # Explicit caption colors are a useful fallback when Qt/Windows does
        # not honor the immersive-dark-mode attribute for a dialog.
        caption_color = ctypes.c_uint32(0x001F1B18)  # BGR: #181B1F
        caption_text = ctypes.c_uint32(0x00E7E9ED)   # BGR-ish light text

        # Windows 10/11 have used both attribute numbers.
        for attribute in (20, 19):
            result = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_int(attribute),
                ctypes.byref(use_dark_mode),
                ctypes.sizeof(use_dark_mode),
            )
            if result == 0:
                break

        # DWMWA_CAPTION_COLOR / DWMWA_TEXT_COLOR. Unsupported builds simply
        # return an error, so this remains safe on older Windows 10 builds.
        for attribute, value in ((35, caption_color), (36, caption_text)):
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_int(attribute),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        pass

    # Windows 10 fallback for builds that ignore the normal DWM
    # immersive-dark-mode title-bar attribute.
    try:
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint32),
                ("AnimationId", ctypes.c_int),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        set_composition = getattr(
            ctypes.windll.user32,
            "SetWindowCompositionAttribute",
            None,
        )

        if set_composition is not None:
            policy = ACCENTPOLICY()
            policy.AccentState = 3
            policy.AccentFlags = 0
            policy.GradientColor = 0x001F1B18
            policy.AnimationId = 0

            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = 19
            data.Data = ctypes.cast(
                ctypes.pointer(policy),
                ctypes.c_void_p,
            )
            data.SizeOfData = ctypes.sizeof(policy)

            set_composition(
                ctypes.c_void_p(hwnd),
                ctypes.byref(data),
            )
    except Exception:
        pass


# ============================================================
# Dark theme
# ============================================================

APP_BACKGROUND = "#181a1f"
TOPBAR_BACKGROUND = "#202329"
INPUT_BACKGROUND = "#202329"
INPUT_FIELD = "#15171b"

BORDER_COLOR = "#30343b"

TEXT_COLOR = "#e7e9ed"
SECONDARY_TEXT = "#8d949f"
MUTED_TEXT = "#666d78"

ACCENT_COLOR = "#4f8cff"
ACCENT_HOVER = "#6a9dff"

STATUS_GREEN = "#35d07f"
STATUS_ORANGE = "#f0ad4e"
STATUS_RED = "#ef5b65"

USER_NAME_COLOR = "#d9dde5"
BOLTU_NAME_COLOR = "#7da8ff"

USER_BUBBLE = "#252b35"
BOLTU_BUBBLE = "#20242b"
BUBBLE_BORDER = "#303641"

CHAT_DIR = Path(__file__).resolve().parent.parent / "chats"
CHAT_DIR.mkdir(parents=True, exist_ok=True)


# Equation blocks supported by the local renderer.
# Qwen commonly emits \[ ... \] or $$ ... $$.
BLOCK_EQUATION_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\])"
)

# Inline equations such as $V$, $I = V/R$, or \(V\).
INLINE_EQUATION_RE = re.compile(
    r"(\$[^$\n]+?\$|\\\([^\n]+?\\\))"
)

# Combined matcher: block equations are checked first so $$...$$ is never
# accidentally interpreted as two inline equations.
EQUATION_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\]|\$[^$\n]+?\$|\\\([^\n]+?\\\))"
)


def render_equation_pixmap(equation, dpi=120):
    """Render a LaTeX-style equation locally using Matplotlib MathText."""
    try:
        import numpy as np
        from matplotlib.mathtext import MathTextParser

        expression = equation.strip()
        if expression.startswith("$$") and expression.endswith("$$"):
            expression = expression[2:-2].strip()
        elif expression.startswith(r"\[") and expression.endswith(r"\]"):
            expression = expression[2:-2].strip()
        elif expression.startswith("$") and expression.endswith("$"):
            expression = expression[1:-1].strip()
        elif expression.startswith(r"\(") and expression.endswith(r"\)"):
            expression = expression[2:-2].strip()

        parsed = MathTextParser("agg").parse(
            "$" + expression + "$",
            dpi=dpi,
        )

        alpha = np.asarray(parsed.image)
        rgb = np.empty((alpha.shape[0], alpha.shape[1], 3), dtype=np.uint8)
        text_rgb = tuple(
            int(TEXT_COLOR[i:i + 2], 16)
            for i in (1, 3, 5)
        )
        rgb[:, :, 0] = text_rgb[0]
        rgb[:, :, 1] = text_rgb[1]
        rgb[:, :, 2] = text_rgb[2]
        rgba = np.dstack((rgb, alpha))

        image = QImage(
            rgba.data,
            rgba.shape[1],
            rgba.shape[0],
            rgba.shape[1] * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()

        return QPixmap.fromImage(image)

    except Exception:
        return None


class BoltuDialogThemeFilter(QObject):
    """Keep every native dialog visually consistent with Boltu."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QDialog):
            obj.setWindowTitle("Boltu")
            QTimer.singleShot(0, lambda o=obj: apply_windows_dark_titlebar(o))
            QTimer.singleShot(100, lambda o=obj: apply_windows_dark_titlebar(o))
            QTimer.singleShot(500, lambda o=obj: apply_windows_dark_titlebar(o))
            QTimer.singleShot(1200, lambda o=obj: apply_windows_dark_titlebar(o))
        return False


# ============================================================
# Server worker
# ============================================================

class ServerWorker(QThread):

    success = Signal()
    error = Signal(str)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            boltu_core.start_server(self.model_name)
            self.success.emit()

        except Exception as e:
            self.error.emit(str(e))


# ============================================================
# Chat worker
# ============================================================

class ChatWorker(QThread):

    token = Signal(str)
    thinking = Signal(str)
    stats = Signal(dict)
    finished = Signal()
    error = Signal(str)

    def run(self):
        try:
            boltu_core.stream_chat(
                token_callback=self.receive_token,
                thinking_callback=self.receive_thinking,
                error_callback=self.receive_error,
                stats_callback=self.receive_stats,
            )

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

    def receive_token(self, text):
        self.token.emit(text)

    def receive_thinking(self, text):
        self.thinking.emit(text)

    def receive_stats(self, stats):
        self.stats.emit(stats)

    def receive_error(self, text):
        self.error.emit(text)


# ============================================================
# Settings dialog
# ============================================================

class SettingsDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Boltu")
        self.setMinimumWidth(400)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.black)
        self.setPalette(palette)

        settings = boltu_core.get_settings()

        # ----------------------------------------------------
        # Controls
        # ----------------------------------------------------

        # Dropdowns keep the tuning options sensible for this PC.
        self.cpu_threads = QComboBox()
        self.cpu_threads.addItems(
            ["1", "2", "3", "4"]
        )

        self.context_size = QComboBox()
        self.context_size.addItems(
            ["1024", "2048", "3072", "4096"]
        )

        self.max_tokens = QComboBox()
        self.max_tokens.addItems(
            ["128", "256", "384", "512", "768", "1024"]
        )

        self.temperature = QComboBox()
        self.temperature.addItems(
            [
                "0.3", "0.4", "0.5", "0.6",
                "0.7", "0.8", "0.9", "1.0"
            ]
        )

        self.thinking = QComboBox()
        self.thinking.addItems(["Off", "On"])

        self._set_combo_value(
            self.cpu_threads,
            settings.get("cpu_threads", 2)
        )
        self._set_combo_value(
            self.context_size,
            settings.get("context_size", 2048)
        )
        self._set_combo_value(
            self.max_tokens,
            settings.get("max_tokens", 384)
        )
        self._set_combo_value(
            self.temperature,
            f'{float(settings.get("temperature", 0.7)):.1f}'
        )
        self._set_combo_value(
            self.thinking,
            "On" if settings.get("thinking", False) else "Off"
        )

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        title = QLabel("Model Settings")
        title.setObjectName("settingsTitle")

        description = QLabel(
            "These settings control how Boltu runs the local language model."
        )

        description.setObjectName(
            "settingsDescription"
        )

        description.setWordWrap(True)

        # ----------------------------------------------------
        # Form
        # ----------------------------------------------------

        form = QFormLayout()

        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft
        )

        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        form.addRow(
            self._form_label("CPU Threads"),
            self.cpu_threads
        )

        form.addRow(
            self._form_label("Context Size"),
            self.context_size
        )

        form.addRow(
            self._form_label("Max Output Tokens"),
            self.max_tokens
        )

        form.addRow(
            self._form_label("Temperature"),
            self.temperature
        )

        form.addRow(
            self._form_label("Thinking"),
            self.thinking
        )

        # ----------------------------------------------------
        # Note
        # ----------------------------------------------------

        note = QLabel(
            "Changes are saved to Boltu's configuration "
            "and take effect after restarting the model server."
        )

        note.setObjectName(
            "settingsNote"
        )

        note.setWordWrap(True)

        # ----------------------------------------------------
        # Buttons
        # ----------------------------------------------------

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            |
            QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            22,
            20,
            22,
            20
        )

        layout.setSpacing(14)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch()
        layout.addWidget(buttons)

    def _form_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 12px;"
        )
        return label

    def showEvent(self, event):
        super().showEvent(event)
        # Qt can recreate the native dialog window during showing, so apply
        # the DWM setting after the HWND is fully established as well.
        apply_windows_dark_titlebar(self)
        QTimer.singleShot(100, lambda: apply_windows_dark_titlebar(self))
        QTimer.singleShot(400, lambda: apply_windows_dark_titlebar(self))

    def _set_combo_value(self, combo, value):
        value = str(value)
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)

        # ----------------------------------------------------
        # Dark style
        # ----------------------------------------------------

        self.setStyleSheet(
            f"""
            QDialog {{
                background: {APP_BACKGROUND};
                color: {TEXT_COLOR};
            }}

            QDialog QLabel {{
                color: {TEXT_COLOR};
            }}

            QLabel#settingsTitle {{
                color: {TEXT_COLOR};
                font-size: 18px;
                font-weight: 600;
            }}

            QLabel#settingsDescription {{
                color: {SECONDARY_TEXT};
                font-size: 12px;
            }}

            QLabel#settingsNote {{
                color: {SECONDARY_TEXT};
                font-size: 11px;
            }}

            QFormLayout QLabel {{
                color: {TEXT_COLOR};
                font-size: 12px;
            }}

                    QFrame#settingsPanel QComboBox {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 5px 8px;
                min-height: 18px;
                min-width: 105px;
                font-size: 12px;
            }}

            QFrame#settingsPanel QComboBox:hover {{
                border: 1px solid #454b54;
            }}

            QFrame#settingsPanel QComboBox:focus {{
                border: 1px solid {ACCENT_COLOR};
            }}

            QFrame#settingsPanel QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}

            QFrame#settingsPanel QComboBox QAbstractItemView {{
                background: #22252b;
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: #303d55;
                selection-color: {TEXT_COLOR};
                outline: none;
                padding: 3px;
            }}

            QPushButton {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 6px 14px;
            }}

            QPushButton:hover {{
                background: #292d34;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical {{
                background: #363b43;
                border-radius: 4px;
                min-height: 28px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: #454c56;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
            }}

            QDialogButtonBox QPushButton[text="Save"] {{
                background: {ACCENT_COLOR};
                color: white;
                border: none;
                font-weight: 600;
            }}

            QDialogButtonBox QPushButton[text="Save"]:hover {{
                background: {ACCENT_HOVER};
            }}
            """
        )


class SettingsPanel(QFrame):
    """Settings presented inside the main Boltu window."""

    apply_requested = Signal(int, int, int, float, bool)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        settings = boltu_core.get_settings()

        self.cpu_threads = QComboBox()
        self.cpu_threads.addItems(["1", "2", "3", "4"])
        self.context_size = QComboBox()
        self.context_size.addItems(["1024", "2048", "3072", "4096"])
        self.max_tokens = QComboBox()
        self.max_tokens.addItems(["128", "256", "384", "512", "768", "1024"])
        self.temperature = QComboBox()
        self.temperature.addItems(["0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0"])
        self.thinking = QComboBox()
        self.thinking.addItems(["Off", "On"])

        def set_value(combo, value):
            idx = combo.findText(str(value))
            combo.setCurrentIndex(idx if idx >= 0 else 0)

        set_value(self.cpu_threads, settings.get("cpu_threads", 2))
        set_value(self.context_size, settings.get("context_size", 2048))
        set_value(self.max_tokens, settings.get("max_tokens", 384))
        set_value(self.temperature, f'{float(settings.get("temperature", 0.7)):.1f}')
        set_value(self.thinking, "On" if settings.get("thinking", False) else "Off")

        title_row = QHBoxLayout()
        title = QLabel("Model Settings")
        title.setObjectName("settingsTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        description = QLabel("These settings control how Boltu runs the local language model.")
        description.setWordWrap(True)
        description.setObjectName("settingsDescription")

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        for label_text, combo in [
            ("CPU Threads", self.cpu_threads),
            ("Context Size", self.context_size),
            ("Max Output Tokens", self.max_tokens),
            ("Temperature", self.temperature),
            ("Thinking", self.thinking),
        ]:
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px;")
            form.addRow(label, combo)

        note = QLabel("Changes are saved to Boltu's configuration. Restart the model server to apply them.")
        note.setWordWrap(True)
        note.setObjectName("settingsNote")

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.cancel_requested.emit)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primaryButton")
        apply_btn.clicked.connect(self._apply)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(apply_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        layout.addLayout(title_row)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addStretch()
        layout.addLayout(buttons)

    def _apply(self):
        self.apply_requested.emit(
            int(self.cpu_threads.currentText()),
            int(self.context_size.currentText()),
            int(self.max_tokens.currentText()),
            float(self.temperature.currentText()),
            self.thinking.currentText() == "On",
        )


# ============================================================
# Main window
# ============================================================

class BoltuWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("Boltu")

        # Compact window
        self.resize(
            800,
            600
        )

        self.setMinimumSize(
            620,
            440
        )

        self.server_worker = None
        self.chat_worker = None
        self.pending_model_selection = None
        self._restoring_model_selection = False

        self.chat_finished_handled = False

        self.current_thinking_text = ""

        self.assistant_message = None

        self.assistant_start_time = None
        self.generated_characters = 0
        self.generated_chunks = 0
        self.generation_stats = None

        self.build_ui()
        self.apply_style()

        self.start_selected_model()

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        central = QWidget()

        central.setObjectName(
            "centralWidget"
        )

        self.setCentralWidget(
            central
        )

        root_layout = QVBoxLayout(
            central
        )

        root_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        root_layout.setSpacing(0)

        # ====================================================
        # Top bar
        # ====================================================

        top_bar = QFrame()

        top_bar.setObjectName(
            "topBar"
        )

        top_layout = QHBoxLayout(
            top_bar
        )

        top_layout.setContentsMargins(
            14,
            8,
            14,
            8
        )

        top_layout.setSpacing(6)

        # ----------------------------------------------------
        # Title
        # ----------------------------------------------------

        title = QLabel("Boltu")

        title.setObjectName(
            "appTitle"
        )

        subtitle = QLabel(
            "Offline AI"
        )

        subtitle.setObjectName(
            "appSubtitle"
        )

        title_group = QVBoxLayout()

        title_group.setContentsMargins(
            0,
            0,
            0,
            0
        )

        title_group.setSpacing(0)

        title_group.addWidget(
            title
        )

        title_group.addWidget(
            subtitle
        )

        top_layout.addLayout(
            title_group
        )

        top_layout.addStretch()

        # ----------------------------------------------------
        # Model
        # ----------------------------------------------------

        self.model_selector = QComboBox()
        self.model_selector.setObjectName(
            "modelSelector"
        )

        self.model_selector.setMinimumWidth(
            220
        )

        self.model_selector.setFixedHeight(
            30
        )
        self.model_selector.setPlaceholderText(
            "Select other models"
        )

        # Include the configured model during startup so there is a model to launch.
        # After startup, refresh_models() hides the currently running model.
        self.refresh_models(include_current=True)

        top_layout.addWidget(
            self.model_selector
        )

        # ----------------------------------------------------
        # Buttons
        # ----------------------------------------------------

        self.settings_button = QPushButton(
            "Settings"
        )

        self.settings_button.setObjectName(
            "secondaryButton"
        )

        top_layout.addWidget(
            self.settings_button
        )

        self.save_chat_button = QPushButton(
            "Save"
        )

        self.save_chat_button.setObjectName(
            "secondaryButton"
        )

        top_layout.addWidget(
            self.save_chat_button
        )

        self.open_chat_button = QPushButton(
            "Open"
        )

        self.open_chat_button.setObjectName(
            "secondaryButton"
        )

        top_layout.addWidget(
            self.open_chat_button
        )

        self.new_chat_button = QPushButton(
            "New Chat"
        )

        self.new_chat_button.setObjectName(
            "primaryButton"
        )

        top_layout.addWidget(
            self.new_chat_button
        )

        # Clicking another top-level action while an inline panel is open
        # cancels that panel first, then lets the requested action continue.
        for action_widget in (
            self.settings_button,
            self.save_chat_button,
            self.open_chat_button,
            self.new_chat_button,
        ):
            action_widget.installEventFilter(self)

        root_layout.addWidget(
            top_bar
        )

        # ====================================================
        # Status bar
        # ====================================================

        status_bar = QFrame()

        status_bar.setObjectName(
            "statusBar"
        )

        status_layout = QHBoxLayout(
            status_bar
        )

        status_layout.setContentsMargins(
            14,
            4,
            14,
            4
        )

        status_layout.setSpacing(5)

        self.status_dot = QLabel(
            "●"
        )

        self.status_dot.setObjectName(
            "statusDot"
        )

        self.status_label = QLabel(
            "Starting..."
        )

        self.status_label.setObjectName(
            "statusLabel"
        )

        self.model_status = QLabel(
            ""
        )

        self.model_status.setObjectName(
            "modelStatus"
        )

        status_layout.addWidget(
            self.status_dot
        )

        status_layout.addWidget(
            self.status_label
        )

        status_layout.addSpacing(
            8
        )

        status_layout.addWidget(
            self.model_status
        )

        status_layout.addStretch()

        root_layout.addWidget(
            status_bar
        )

        # ====================================================
        # Conversation
        # ====================================================

        self.scroll_area = QScrollArea()

        self.scroll_area.setWidgetResizable(
            True
        )

        self.scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.chat_container = QWidget()

        self.chat_container.setObjectName(
            "chatContainer"
        )

        self.chat_layout = QVBoxLayout(
            self.chat_container
        )

        self.chat_layout.setContentsMargins(
            16,
            12,
            16,
            12
        )

        self.chat_layout.setSpacing(
            12
        )

        self.chat_layout.addStretch()

        self.scroll_area.setWidget(
            self.chat_container
        )
        self.scroll_area.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.scroll_area.customContextMenuRequested.connect(self.show_conversation_context_menu)

        # Keep the conversation pinned to the newest message.
        # rangeChanged fires whenever the scrollable content changes,
        # including streamed text and rendered equation widgets.
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            self._conversation_range_changed
        )

        # The main content area switches pages without creating extra windows.
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        self.conversation_page = QWidget()
        conversation_page_layout = QVBoxLayout(self.conversation_page)
        conversation_page_layout.setContentsMargins(0, 0, 0, 0)
        conversation_page_layout.setSpacing(0)
        conversation_page_layout.addWidget(self.scroll_area)
        self.settings_panel = SettingsPanel()
        self.settings_panel.apply_requested.connect(self.apply_settings_panel)
        self.settings_panel.cancel_requested.connect(self.hide_inline_panel)
        self.content_stack.addWidget(self.conversation_page)
        self.content_stack.addWidget(self.settings_panel)
        root_layout.addWidget(self.content_stack, 1)

        # ====================================================
        # Input
        # ====================================================

        input_area = QFrame()

        input_area.setObjectName(
            "inputArea"
        )

        input_layout = QHBoxLayout(
            input_area
        )

        input_layout.setContentsMargins(
            14,
            8,
            14,
            10
        )

        input_layout.setSpacing(
            8
        )

        self.input = QPlainTextEdit()

        self.input.setObjectName(
            "messageInput"
        )

        self.input.setPlaceholderText(
            "Message Boltu..."
        )

        self.input.setFixedHeight(
            62
        )

        self.input.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
        )

        input_layout.addWidget(
            self.input,
            1
        )

        self.send_button = QPushButton(
            "Send"
        )

        self.send_button.setObjectName(
            "sendButton"
        )

        self.send_button.setFixedWidth(
            68
        )

        self.send_button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding
        )

        input_layout.addWidget(
            self.send_button
        )

        root_layout.addWidget(
            input_area
        )

        # ====================================================
        # Signals
        # ====================================================

        self.send_button.clicked.connect(
            self.send_message
        )

        self.input.installEventFilter(
            self
        )

        self.new_chat_button.clicked.connect(
            self.new_chat
        )

        self.settings_button.clicked.connect(
            self.open_settings
        )

        self.model_selector.currentIndexChanged.connect(
            self.model_selection_changed
        )

        self.save_chat_button.clicked.connect(
            self.save_chat
        )

        self.open_chat_button.clicked.connect(
            self.open_chat
        )

        self.set_chat_controls(
            False
        )

        # Global desktop-style shortcuts.
        self.shortcut_new_chat = QShortcut(
            QKeySequence("Ctrl+N"), self
        )
        self.shortcut_new_chat.activated.connect(self.new_chat)

        self.shortcut_save_chat = QShortcut(
            QKeySequence("Ctrl+S"), self
        )
        self.shortcut_save_chat.activated.connect(self.save_chat)

        self.shortcut_open_chat = QShortcut(
            QKeySequence("Ctrl+O"), self
        )
        self.shortcut_open_chat.activated.connect(self.open_chat)

        self.shortcut_settings = QShortcut(
            QKeySequence("Ctrl+,"), self
        )
        self.shortcut_settings.activated.connect(self.open_settings)

        self.shortcut_focus_input = QShortcut(
            QKeySequence("Ctrl+L"), self
        )
        self.shortcut_focus_input.activated.connect(self.focus_input)

        self.set_chat_controls(
            False
        )

    # ========================================================
    # Dark theme
    # ========================================================

    def apply_style(self):

        self.setStyleSheet(
            f"""
            QMainWindow {{
                background: {APP_BACKGROUND};
            }}

            QWidget#centralWidget {{
                background: {APP_BACKGROUND};
            }}

            QStackedWidget#contentStack {{
                background: {APP_BACKGROUND};
            }}

            QFrame#settingsPanel {{
                background: {APP_BACKGROUND};
                color: {TEXT_COLOR};
            }}

            /* In-window panels */

            QLabel#settingsTitle {{
                color: {TEXT_COLOR};
                font-size: 18px;
                font-weight: 600;
            }}

            QLabel#settingsDescription {{
                color: {SECONDARY_TEXT};
                font-size: 12px;
            }}

            QLabel#settingsNote {{
                color: {SECONDARY_TEXT};
                font-size: 11px;
            }}

            QFormLayout QLabel {{
                color: {TEXT_COLOR};
                font-size: 12px;
            }}

            /* Settings / inline-panel dropdowns */

            QFrame#settingsPanel QComboBox {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 5px 8px;
                min-height: 18px;
                min-width: 105px;
                font-size: 12px;
            }}

            QFrame#settingsPanel QComboBox:hover {{
                border: 1px solid #454b54;
            }}

            QFrame#settingsPanel QComboBox:focus {{
                border: 1px solid {ACCENT_COLOR};
            }}

            QFrame#settingsPanel QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}

            QFrame#settingsPanel QComboBox QAbstractItemView {{
                background: #22252b;
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: #303d55;
                selection-color: {TEXT_COLOR};
                outline: none;
                padding: 3px;
            }}

            /* Top bar */

            QFrame#topBar {{
                background: {TOPBAR_BACKGROUND};
                border-bottom: 1px solid {BORDER_COLOR};
            }}

            QLabel#appTitle {{
                color: {TEXT_COLOR};
                font-size: 17px;
                font-weight: 700;
            }}

            QLabel#appSubtitle {{
                color: {SECONDARY_TEXT};
                font-size: 10px;
            }}

            /* Status */

            QFrame#statusBar {{
                background: #1b1e23;
                border-bottom: 1px solid {BORDER_COLOR};
            }}

            QLabel#statusDot {{
                color: {STATUS_ORANGE};
                font-size: 9px;
            }}

            QLabel#statusLabel {{
                color: {SECONDARY_TEXT};
                font-size: 11px;
            }}

            QLabel#modelStatus {{
                color: {MUTED_TEXT};
                font-size: 11px;
            }}

            /* Conversation */

            QWidget#chatContainer {{
                background: {APP_BACKGROUND};
            }}

            /* Scrollbar */

            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical {{
                background: #363b43;
                border-radius: 4px;
                min-height: 30px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: #454c56;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
                border: none;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
                margin: 2px;
            }}

            QScrollBar::handle:horizontal {{
                background: #363b43;
                border-radius: 4px;
                min-width: 30px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: #454c56;
            }}

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
                border: none;
            }}

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}

            /* Input */

            QFrame#inputArea {{
                background: {TOPBAR_BACKGROUND};
                border-top: 1px solid {BORDER_COLOR};
            }}

            QPlainTextEdit#messageInput {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 7px;
                padding: 7px 9px;
                font-size: 13px;
            }}

            QPlainTextEdit#messageInput:focus {{
                background: #181a1f;
                border: 1px solid {ACCENT_COLOR};
            }}

            /* Model selector */

            QComboBox#modelSelector {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                border-radius: 7px;
                padding: 4px 10px;
                min-height: 18px;
                font-size: 11px;
            }}

            QComboBox#modelSelector:hover {{
                border: 1px solid #454b54;
                background: #181a1f;
            }}

            QComboBox#modelSelector:focus {{
                border: 1px solid {ACCENT_COLOR};
            }}

            QComboBox#modelSelector::drop-down {{
                border: none;
                width: 26px;
            }}

            QComboBox#modelSelector QAbstractItemView {{
                background: #22252b;
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                selection-background-color: #303d55;
                selection-color: {TEXT_COLOR};
                padding: 4px;
                outline: none;
            }}

            /* Conversation bubbles */

            QWidget#conversationRow {{
                background: transparent;
            }}

            /* Buttons */

            QPushButton {{
                font-size: 11px;
                border-radius: 6px;
                padding: 5px 10px;
            }}

            QPushButton#secondaryButton {{
                background: {INPUT_FIELD};
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
            }}

            QPushButton#secondaryButton:hover {{
                background: #292d34;
            }}

            QPushButton#primaryButton {{
                background: #292d34;
                color: {TEXT_COLOR};
                border: 1px solid {BORDER_COLOR};
                font-weight: 600;
            }}

            QPushButton#primaryButton:hover {{
                background: #333840;
            }}

            QPushButton#stopButton {{
                background: #8d3f48;
                color: white;
                border: none;
                font-weight: 600;
                font-size: 12px;
            }}

            QPushButton#stopButton:hover {{
                background: #a64b56;
            }}

            QPushButton#sendButton {{
                background: {ACCENT_COLOR};
                color: white;
                border: none;
                font-weight: 600;
                font-size: 12px;
            }}

            QPushButton#sendButton:hover {{
                background: {ACCENT_HOVER};
            }}

            QPushButton#sendButton:disabled {{
                background: #34415a;
            }}

            QPushButton:disabled {{
                color: #666d78;
            }}
            """
        )

    # ========================================================
    # Keyboard
    # ========================================================

    def eventFilter(
        self,
        obj,
        event
    ):

        # eventFilter() can receive events while build_ui() is still
        # constructing the window, so some widgets (especially input) may
        # not exist yet. Always access them defensively here.
        action_widgets = tuple(
            widget
            for widget in (
                getattr(self, "settings_button", None),
                getattr(self, "save_chat_button", None),
                getattr(self, "open_chat_button", None),
                getattr(self, "new_chat_button", None),
            )
            if widget is not None
        )

        if obj in action_widgets:
            if event.type() == QEvent.Type.MouseButtonPress and self._inline_panel_visible():
                # Settings acts as a toggle when its own panel is visible.
                # Consume the click so the connected slot does not immediately
                # reopen the panel. Other buttons cancel the panel and continue
                # with their normal action.
                if (
                    obj is getattr(self, "settings_button", None)
                    and getattr(self, "settings_panel", None) is not None
                    and self.content_stack.currentWidget() is self.settings_panel
                ):
                    self.hide_inline_panel()
                    return True
                self.hide_inline_panel()

        input_widget = getattr(self, "input", None)
        if input_widget is not None and obj is input_widget:

            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
                if self._inline_panel_visible():
                    self.hide_inline_panel()

            if event.type() == event.Type.KeyPress:

                if event.key() == Qt.Key_Return:

                    if (
                        event.modifiers()
                        &
                        Qt.KeyboardModifier.ShiftModifier
                    ):
                        return False

                    self.send_message()

                    return True

                if event.key() == Qt.Key_Escape:
                    if self.chat_worker is not None and self.chat_worker.isRunning():
                        self.stop_generation()
                        return True

        return super().eventFilter(
            obj,
            event
        )

    def focus_input(self):
        self.input.setFocus()
        self.input.moveCursor(QTextCursor.MoveOperation.End)

    # ========================================================
    # Inline panel helpers
    # ========================================================

    def _inline_panel_visible(self):
        return self.content_stack.currentWidget() is not self.conversation_page

    def _cancel_inline_panel_for_action(self):
        if self._inline_panel_visible():
            self.hide_inline_panel()

    # ========================================================
    # Models
    # ========================================================

    def refresh_models(self, include_current=False):

        self._restoring_model_selection = True
        self.model_selector.clear()

        current = boltu_core.get_current_model()
        available = list(boltu_core.get_available_models())

        if include_current and current and current not in available:
            available.insert(0, current)

        if include_current:
            models = available
        else:
            models = [model for model in available if model != current]

        self.model_selector.addItems(models)

        if include_current and current:
            idx = self.model_selector.findText(current)
            if idx >= 0:
                self.model_selector.setCurrentIndex(idx)
            elif self.model_selector.count() > 0:
                self.model_selector.setCurrentIndex(0)
        else:
            self.model_selector.setCurrentIndex(-1)

        self._restoring_model_selection = False

    # ========================================================
    # Controls
    # ========================================================

    def set_chat_controls(
        self,
        enabled
    ):

        self.input.setEnabled(
            enabled
        )

        # During generation the same button becomes Stop.
        # It remains enabled so the user can interrupt a response.
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.send_button.setEnabled(True)
        else:
            self.send_button.setEnabled(enabled)

        self.new_chat_button.setEnabled(
            enabled
        )

        self.save_chat_button.setEnabled(
            enabled
        )

        self.open_chat_button.setEnabled(
            enabled
        )

        self.model_selector.setEnabled(
            enabled
        )

        self.settings_button.setEnabled(
            enabled
        )

    # ========================================================
    # Status
    # ========================================================

    def set_status(
        self,
        text,
        state="ready"
    ):

        self.status_label.setText(
            text
        )

        if state == "ready":

            self.status_dot.setStyleSheet(
                f"color: {STATUS_GREEN};"
            )

        elif state == "busy":

            self.status_dot.setStyleSheet(
                f"color: {STATUS_ORANGE};"
            )

        elif state == "error":

            self.status_dot.setStyleSheet(
                f"color: {STATUS_RED};"
            )

    # ========================================================
    # Timestamp
    # ========================================================

    def timestamp(self):

        return time.strftime(
            "%H:%M:%S"
        )

    # ========================================================
    # Scroll
    # ========================================================

    def scroll_to_bottom(self):

        # The layout may not have been recalculated yet, especially while
        # text/equations are being streamed. Queue the scroll after Qt has
        # processed the current layout change, then do a second pass after
        # the geometry settles.
        QTimer.singleShot(
            0,
            self._scroll_to_bottom
        )
        QTimer.singleShot(
            30,
            self._scroll_to_bottom
        )

    def _conversation_range_changed(self, minimum, maximum):

        # Always pin the conversation to the newest content whenever the
        # scrollable range changes.
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):

        scrollbar = (
            self.scroll_area
            .verticalScrollBar()
        )

        scrollbar.setValue(
            scrollbar.maximum()
        )

    def _resize_message_content(self, message_widget):
        """Resize a bubble to its content without leaving artificial empty space."""
        if message_widget is None:
            return
        content = getattr(message_widget, "content", None)
        if content is None:
            return

        max_width = max(280, message_widget.maximumWidth())
        document = content.document()

        # First measure the natural width. This keeps short messages compact
        # while still allowing long messages to wrap at the bubble limit.
        document.setTextWidth(-1)
        natural_width = int(document.idealWidth()) + 8
        width = min(max_width - 20, max(90, natural_width))

        content.setFixedWidth(width)
        document.setTextWidth(max(80, width - 2))
        height = max(24, int(document.size().height()) + 6)
        content.setFixedHeight(height)

    def _resize_all_messages(self):
        viewport_width = max(360, self.scroll_area.viewport().width())
        for i in range(self.chat_layout.count() - 1):
            row = self.chat_layout.itemAt(i).widget()
            if row is None:
                continue
            for child in row.findChildren(QFrame, "conversationMessage"):
                child.setMaximumWidth(max(280, int(viewport_width * 0.78)))
                self._resize_message_content(child)
        self.scroll_to_bottom()

    # ========================================================
    # Add conversation message
    # ========================================================

    def add_message(
        self,
        speaker,
        text="",
        timestamp=None
    ):
        """
        Creates a compact plain-text conversation entry.

        Uses QLabel rather than a fixed-height QTextEdit.
        This avoids the previous long-response clipping issue.
        """

        row = QWidget()
        row.setObjectName("conversationRow")

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        message_widget = QFrame()
        message_widget.setObjectName("conversationMessage")
        message_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred
        )

        message_layout = QVBoxLayout(message_widget)

        message_layout.setContentsMargins(
            10,
            7,
            10,
            8
        )

        message_layout.setSpacing(
            3
        )

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        header = QHBoxLayout()

        header.setContentsMargins(
            0,
            0,
            0,
            0
        )

        header.setSpacing(
            6
        )

        name_label = QLabel(
            speaker
        )

        name_label.setObjectName(
            "conversationName"
        )

        time_label = QLabel(
            timestamp or ""
        )

        time_label.setObjectName(
            "conversationTime"
        )

        header.addWidget(
            name_label
        )

        header.addWidget(
            time_label
        )

        header.addStretch()

        message_layout.addLayout(
            header
        )

        # ----------------------------------------------------
        # Content
        # ----------------------------------------------------

        # QTextEdit gives us a compact, selectable rich-text surface while
        # still allowing equations to appear inline with normal sentences.
        content = QTextEdit()
        content.setObjectName(
            "conversationContent"
        )
        content.setReadOnly(True)
        content.setAcceptRichText(True)
        content.setFrameShape(QFrame.Shape.NoFrame)
        content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        content.setPlainText(text)
        content.setMinimumHeight(24)

        # Keep a dedicated content area so equation images can be inserted
        # after streaming finishes without changing the compact chat layout.
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        content_layout.addWidget(content)

        message_layout.addWidget(
            content_area
        )

        # ----------------------------------------------------
        # Styling
        # ----------------------------------------------------

        if speaker == "You":

            name_color = USER_NAME_COLOR

        else:

            name_color = BOLTU_NAME_COLOR

        name_label.setStyleSheet(
            f"""
            color: {name_color};
            font-size: 11px;
            font-weight: 600;
            """
        )

        time_label.setStyleSheet(
            f"""
            color: {MUTED_TEXT};
            font-size: 10px;
            """
        )

        bubble_color = (
            USER_BUBBLE if speaker == "You" else BOLTU_BUBBLE
        )

        message_widget.setStyleSheet(
            f"""
            QFrame#conversationMessage {{
                background: {bubble_color};
                border: 1px solid {BUBBLE_BORDER};
                border-radius: 9px;
            }}
            """
        )

        content.setStyleSheet(
            f"""
            QTextEdit#conversationContent {{
                background: transparent;
                color: {TEXT_COLOR};
                border: none;
                font-size: 13px;
                padding: 0px;
            }}
            """
        )

        # ----------------------------------------------------
        # Store references
        # ----------------------------------------------------

        message_widget.content = content
        message_widget.content_area = content_area
        message_widget.content_layout = content_layout
        message_widget.name_label = name_label
        message_widget.time_label = time_label
        message_widget.raw_text = text
        message_widget.speaker = speaker
        message_widget.is_startup = False

        # Make the bubble responsive without imposing a fixed message height.
        viewport_width = max(360, self.scroll_area.viewport().width())
        message_widget.setMaximumWidth(
            max(280, int(viewport_width * 0.78))
        )

        if speaker == "You":
            row_layout.addStretch(1)
            row_layout.addWidget(message_widget)
        else:
            row_layout.addWidget(message_widget)
            row_layout.addStretch(1)

        # ----------------------------------------------------
        # Insert
        # ----------------------------------------------------

        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1,
            row
        )

        message_widget.row = row
        self._resize_message_content(message_widget)
        self.scroll_to_bottom()

        return message_widget

    # ========================================================
    # Start selected model
    # ========================================================

    def start_selected_model(self):

        model = (
            self.model_selector.currentText()
        )

        if not model:

            QMessageBox.critical(
                self,
                "Boltu",
                "No GGUF model was found in the models folder."
            )

            self.close()

            return

        self.set_chat_controls(
            False
        )

        self.set_status(
            "Starting model...",
            "busy"
        )

        self.model_status.setText(
            model
        )

        self.server_worker = (
            ServerWorker(model)
        )

        self.server_worker.success.connect(
            self.server_started
        )

        self.server_worker.error.connect(
            self.server_error
        )

        self.server_worker.start()

    # ========================================================
    # Server started
    # ========================================================

    def server_started(self):

        model_start_time = self.timestamp()

        self.set_status(
            "Ready",
            "ready"
        )

        self.model_status.setText(
            boltu_core.get_current_model()
        )

        self.set_chat_controls(
            True
        )

        self.show_startup_message(
            model_start_time
        )

        # Do not offer the model that is already running as a switch target.
        self.refresh_models()

        self.input.setFocus()

        self.scroll_to_bottom()

    # ========================================================
    # Startup message
    # ========================================================

    def show_startup_message(self, model_start_time):
        model = boltu_core.get_current_model() or "local model"

        if model.lower().endswith(".gguf"):
            model = model[:-5]

        boltu_core.reset_conversation()

        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        startup = self.add_message(
            "Boltu",
            f"Hi! I am up and running with {model}. How can I help you?",
            model_start_time
        )
        startup.is_startup = True

        self.scroll_to_bottom()

    # ========================================================
    # Startup event
    # ========================================================

    def add_event(
        self,
        text
    ):

        event_label = QLabel(
            text
        )

        event_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        event_label.setStyleSheet(
            f"""
            QLabel {{
                color: {MUTED_TEXT};
                font-size: 10px;
                padding: 2px 0px;
            }}
            """
        )

        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1,
            event_label
        )

        self.scroll_to_bottom()

    # ========================================================
    # Server error
    # ========================================================

    def server_error(
        self,
        error
    ):

        self.set_status(
            "Server error",
            "error"
        )

        QMessageBox.critical(
            self,
            "Boltu",
            error
        )

        self.close()

    # ========================================================
    # Send message
    # ========================================================

    def send_message(self):

        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.stop_generation()
            return

        text = (
            self.input
            .toPlainText()
            .strip()
        )

        if not text:

            return

        self.input.clear()

        # ----------------------------------------------------
        # User message timestamp
        # ----------------------------------------------------

        user_time = self.timestamp()

        self.add_message(
            "You",
            text,
            user_time
        )

        boltu_core.add_user_message(
            text
        )

        # ----------------------------------------------------
        # Assistant message
        #
        # IMPORTANT:
        # Do NOT put a timestamp here.
        # The timestamp is added when generation finishes.
        # ----------------------------------------------------

        self.assistant_message = (
            self.add_message(
                "Boltu",
                "",
                ""
            )
        )

        self.assistant_start_time = (
            time.time()
        )
        self.generated_characters = 0
        self.generated_chunks = 0
        self.generation_stats = None

        self.chat_finished_handled = False
        self.current_thinking_text = ""

        settings = (
            boltu_core.get_settings()
        )

        self.set_status(
            "Thinking..."
            if settings["thinking"]
            else "Generating...",
            "busy"
        )

        # ----------------------------------------------------
        # Worker
        # ----------------------------------------------------

        self.chat_worker = ChatWorker()

        # Keep Stop clickable while the worker is running.
        self.input.setEnabled(False)
        self.send_button.setEnabled(True)
        self.send_button.setText("Stop")
        self.send_button.setObjectName("stopButton")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

        self.chat_worker.token.connect(
            self.receive_token
        )

        self.chat_worker.thinking.connect(
            self.receive_thinking
        )

        self.chat_worker.stats.connect(
            self.receive_generation_stats
        )

        self.chat_worker.finished.connect(
            self.chat_finished
        )

        self.chat_worker.error.connect(
            self.chat_error
        )

        self.chat_worker.start()

    # ========================================================
    # Receive token
    # ========================================================

    def receive_token(
        self,
        text
    ):

        if self.assistant_message is None:

            return

        current = self.assistant_message.raw_text
        self.assistant_message.raw_text = current + text
        self.generated_characters += len(text)
        self.generated_chunks += 1

        self.assistant_message.content.setPlainText(
            self.assistant_message.raw_text
        )
        self._resize_message_content(self.assistant_message)

        self.scroll_to_bottom()

    # ========================================================
    # Receive thinking
    # ========================================================

    def receive_thinking(
        self,
        text
    ):

        self.current_thinking_text += text

    # ========================================================
    # Receive generation statistics
    # ========================================================

    def receive_generation_stats(
        self,
        stats
    ):

        self.generation_stats = stats

    # ========================================================
    # Equation rendering
    # ========================================================

    def render_message_equations(self, message_widget):
        """Render Qwen markdown/code/equations consistently after generation."""
        raw_text = getattr(message_widget, "raw_text", "")
        if not raw_text:
            return

        # ------------------------------------------------------------
        # Normalize Qwen display-math variants before tokenizing.
        #
        # Different Qwen sizes commonly emit all of these forms:
        #   $$E = mc^2$$
        #   $$\n        #   E = mc^2\n        #   $$
        #   $$\n        #   $$E = mc^2$$\n        #   $$
        # Normalize them to one canonical form so the renderer does not
        # depend on the model's exact whitespace/newline formatting.
        # ------------------------------------------------------------

        # Remove an empty $$ wrapper around an already-delimited equation.
        raw_text = re.sub(
            r"\$\$[ \t]*(?:\\?[ \t]*)?\r?\n[ \t]*(\$\$.*?\$\$)[ \t]*\r?\n[ \t]*\$\$",
            r"\1",
            raw_text,
            flags=re.S,
        )

        # Canonicalize a normal multiline $$ ... $$ block to one line.
        # This also prevents literal line-break commands from reaching
        # Matplotlib MathText when Qwen emits them as formatting noise.
        def normalize_display_block(match):
            expression = match.group(1).strip()
            expression = re.sub(r"\\(?:newline|linebreak)", " ", expression)
            expression = re.sub(r"[ \t\r\n]+", " ", expression).strip()
            return "$$" + expression + "$$"

        raw_text = re.sub(
            r"\$\$[ \t]*\r?\n(.*?)\r?\n[ \t]*\$\$",
            normalize_display_block,
            raw_text,
            flags=re.S,
        )

        # Also normalize a block whose contents are on several lines but the
        # delimiters are not isolated on their own lines.
        def normalize_any_display(match):
            expression = match.group(1).strip()
            expression = re.sub(r"\\(?:newline|linebreak)", " ", expression)
            expression = re.sub(r"[ \t\r\n]+", " ", expression).strip()
            return "$$" + expression + "$$"

        raw_text = re.sub(
            r"\$\$(.*?)\$\$",
            normalize_any_display,
            raw_text,
            flags=re.S,
        )

        from html import escape

        document = message_widget.content.document()
        document.clear()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        resource_index = 0

        def looks_like_equation(value):
            value = value.strip().strip("*").strip()
            if "=" not in value or len(value) > 220:
                return False
            # Avoid turning ordinary explanatory sentences into equations.
            if re.search(
                r"\b(is|are|was|were|means|where|because|therefore|this|that|which|if|then|for|with|from)\b",
                value,
                re.I,
            ):
                return False
            return bool(
                re.search(
                    r"[A-Za-zα-ωΑ-ΩθπλμΔΣΩ√^_*/]|\\frac|\\sqrt|\\sum|\\int",
                    value,
                )
            )

        # Normalize conservative bare equation lines outside fenced code.
        # Code blocks are protected first, so Python/C/etc. syntax is never
        # mistaken for an equation.
        protected_parts = re.split(r"(?s)(```.*?```|~~~.*?~~~)", raw_text)
        for part_index in range(0, len(protected_parts), 2):
            part = protected_parts[part_index]
            normalized_lines = []
            for line in part.splitlines(True):
                newline = "\n" if line.endswith("\n") else ""
                body = line[:-1] if newline else line
                if looks_like_equation(body.strip()) and not re.search(r"\$.*\$", body):
                    indent = body[:len(body) - len(body.lstrip())]
                    body = indent + "$$" + body.strip() + "$$"
                normalized_lines.append(body + newline)
            protected_parts[part_index] = "".join(normalized_lines)
        raw_text = "".join(protected_parts)

        # Parse fenced code before equations. This is important because code
        # often contains '$', '*', '=', or backslashes that must remain literal.
        token_re = re.compile(
            r"(?s)(```(?:[A-Za-z0-9_+.#-]+)?\r?\n.*?```|~~~(?:[A-Za-z0-9_+.#-]+)?\r?\n.*?~~~|\$\$.*?\$\$|\\\[.*?\\\]|\$[^$\n]+?\$|\\\([^\n]+?\\\))"
        )

        def insert_plain(value):
            if not value:
                return

            # Lightweight Markdown rendering for ordinary text. Escape first so
            # model text cannot accidentally become arbitrary HTML.
            #
            # Supported headings:
            #   # Heading
            #   ## Heading
            #   ### Heading
            #   #### Heading
            #
            # We intentionally keep this small rather than turning the message
            # widget into a full Markdown renderer. Headings are rendered as
            # compact bold blocks, while the original raw text is still kept
            # unchanged for saving/copying.
            lines = value.splitlines(True)
            rendered = []

            for line in lines:
                newline = line.endswith("\n")
                body = line[:-1] if newline else line
                if body.endswith("\r"):
                    body = body[:-1]

                heading = re.match(r"^(#{1,4})[ \t]+(.+?)\s*$", body)
                if heading:
                    level = len(heading.group(1))
                    title = escape(heading.group(2))
                    title = re.sub(r"\*\*([^*\n]+?)\*\*", r"<b>\1</b>", title)
                    title = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<b>\1</b>", title)

                    # Keep the hierarchy visually clear without introducing
                    # the large default margins of HTML <h1>/<h2>/... tags.
                    font_size = {1: 15, 2: 14, 3: 13, 4: 12}[level]
                    rendered.append(
                        f'<div style="font-size:{font_size}px; font-weight:600; '
                        f'margin-top:5px; margin-bottom:3px;">{title}</div>'
                    )
                else:
                    escaped = escape(body)
                    escaped = re.sub(r"\*\*([^*\n]+?)\*\*", r"<b>\1</b>", escaped)
                    escaped = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<b>\1</b>", escaped)
                    rendered.append(escaped)

                if newline:
                    rendered.append("<br>")

            cursor.insertHtml("".join(rendered))

        def insert_code(token):
            fence = "```" if token.startswith("```") else "~~~"
            header_match = re.match(
                rf"{re.escape(fence)}([A-Za-z0-9_+.#-]+)?\r?\n",
                token,
            )
            language = (header_match.group(1) or "") if header_match else ""
            body = token[len(fence):]
            if body.startswith("\r\n"):
                body = body[2:]
            elif body.startswith("\n"):
                body = body[1:]
            if language:
                body = body[body.find("\n") + 1:]

            code = body

            if code.endswith(fence):
                code = code[:-len(fence)]
            code = code.rstrip("\r\n")

            label = (
                f'<div style="font-size:9px; color:{MUTED_TEXT}; margin-bottom:3px;">'
                f"{escape(language)}</div>"
                if language else ""
            )
            html = (
                f'<table width="100%" cellspacing="0" cellpadding="0" '
                f'style="background:{BOLTU_BUBBLE}; border:1px solid {BUBBLE_BORDER};">'
                f'<tr><td style="padding:7px 9px;">{label}'
                f'<pre style="font-family:Consolas, &quot;Courier New&quot;, monospace; '
                f'font-size:11px; white-space:pre-wrap; margin:0; color:{TEXT_COLOR};">'
                f"{escape(code)}</pre></td></tr></table>"
            )
            cursor.insertHtml(html)

        def looks_like_math_block(token):
            """Reject $$ wrappers that Qwen used around ordinary prose/code."""
            if not (token.startswith("$$") and token.endswith("$$")):
                return True

            expression = token[2:-2].strip()

            # Qwen sometimes incorrectly wraps Markdown explanations/code in
            # $$ ... $$. These are not equations and should remain normal text.
            if "`" in expression:
                return False
            if re.match(r"^(?:[-*+]\s|\d+[.)]\s)", expression):
                return False

            # A prose sentence with no mathematical operators/symbols is not
            # worth sending to MathText. This keeps the renderer conservative.
            math_signal = re.search(
                r"(?:=|\\(?:frac|sqrt|sum|int|cdot|times)|[\^_]|[∑∫√∞≈≤≥±×÷])",
                expression,
            )
            prose_signal = re.search(
                r"\b(?:the|this|that|creates|creates|iterates|prints|variable|list|loop|number|code|example|where|because|which|is|are)\b",
                expression,
                re.I,
            )
            if prose_signal and not math_signal:
                return False

            return True

        def insert_equation(token):
            nonlocal resource_index

            if not looks_like_math_block(token):
                # Remove the accidental $$ wrapper but preserve the content.
                insert_plain(token[2:-2])
                return

            is_block = (
                (token.startswith("$$") and token.endswith("$$"))
                or (token.startswith(r"\[") and token.endswith(r"\]"))
            )
            pixmap = render_equation_pixmap(token, dpi=150 if is_block else 110)
            if pixmap is None:
                # If MathText cannot parse it, do not leave a confusing raw
                # $$...$$ wrapper on screen. Show the underlying text instead.
                if token.startswith("$$") and token.endswith("$$"):
                    insert_plain(token[2:-2])
                else:
                    insert_plain(token)
                return
            image = pixmap.toImage()
            url = QUrl(f"equation://boltu/{resource_index}")
            document.addResource(QTextDocument.ResourceType.ImageResource, url, image)
            image_format = QTextImageFormat()
            image_format.setName(url.toString())
            if not is_block:
                image_format.setWidth(image.width())
                image_format.setHeight(image.height())
            if is_block:
                cursor.insertBlock()
            cursor.insertImage(image_format)
            if is_block:
                cursor.insertBlock()
            resource_index += 1

        text_cursor = 0
        for match in token_re.finditer(raw_text):
            insert_plain(raw_text[text_cursor:match.start()])
            token = match.group(0)
            if token.startswith("```") or token.startswith("~~~"):
                insert_code(token)
            else:
                insert_equation(token)
            text_cursor = match.end()

        insert_plain(raw_text[text_cursor:])

        message_widget.content.setDocument(document)
        self._resize_message_content(message_widget)

    # ========================================================
    # Chat finished
    # ========================================================

    def chat_finished(self):

        if self.chat_finished_handled:

            return

        self.chat_finished_handled = True

        # ----------------------------------------------------
        # THIS is the timestamp we want:
        # when Boltu actually finished generating.
        # ----------------------------------------------------

        finished_time = self.timestamp()

        # Prefer exact llama.cpp server statistics. Fall back to the old
        # character-based estimate if statistics are unavailable.
        stats = self.generation_stats or {}
        completion_tokens = stats.get("completion_tokens")
        server_tps = stats.get("tokens_per_second")

        if completion_tokens is not None and server_tps is not None:
            performance_text = (
                f"{int(completion_tokens)} tokens · "
                f"{float(server_tps):.1f} tok/s"
            )
        else:
            elapsed = max(
                0.001,
                time.time() - (self.assistant_start_time or time.time())
            )
            estimated_tokens = max(
                0,
                round(self.generated_characters / 4.0)
            )
            estimated_tps = (
                estimated_tokens / elapsed
                if estimated_tokens
                else 0.0
            )
            performance_text = (
                f"~{estimated_tps:.1f} tok/s"
                if estimated_tokens
                else "— tok/s"
            )

        if self.assistant_message is not None:

            self.render_message_equations(
                self.assistant_message
            )

            self.assistant_message.time_label.setText(
                f"{finished_time} · {performance_text}"
            )

            self.assistant_message.time_label.setStyleSheet(
                f"""
                color: {MUTED_TEXT};
                font-size: 10px;
                """
            )

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        self.set_status(
            "Ready",
            "ready"
        )

        self.set_chat_controls(
            True
        )
        self.send_button.setText("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

        self.input.setFocus()

        self.assistant_message = None
        self.assistant_start_time = None
        self.generation_stats = None

        self.chat_worker = None

        self.scroll_to_bottom()

    def stop_generation(self):
        """Stop the active generation and keep the partial reply visible."""
        worker = self.chat_worker
        if worker is None or not worker.isRunning():
            return

        self.chat_finished_handled = True

        partial = ""
        if self.assistant_message is not None:
            partial = self.assistant_message.raw_text
            if partial:
                try:
                    boltu_core.add_assistant_message(partial)
                except Exception:
                    pass
            self.assistant_message.time_label.setText(
                self.timestamp() + " · stopped"
            )
            self._resize_message_content(self.assistant_message)

        # QThread.terminate() prevents the GUI worker from remaining blocked
        # in the streaming call.  llama-server also needs to be stopped so
        # the server-side generation is actually cancelled rather than
        # continuing to consume CPU after the GUI request is interrupted.
        try:
            worker.requestInterruption()
            worker.terminate()
            worker.wait(500)
        except Exception:
            pass

        self.chat_worker = None
        self.assistant_message = None
        self.assistant_start_time = None

        self.set_chat_controls(False)
        self.send_button.setText("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self.set_status("Stopping generation...", "busy")

        # Restart the same model after cancelling. This is intentionally a
        # fallback because the current boltu_core streaming API does not
        # expose the underlying HTTP connection for a graceful cancellation.
        model = boltu_core.get_current_model()
        try:
            boltu_core.stop_server()
        except Exception:
            pass

        self.server_worker = ServerWorker(model)
        self.server_worker.success.connect(self.generation_server_restarted)
        self.server_worker.error.connect(self.server_error)
        self.server_worker.start()
        self.scroll_to_bottom()

    def generation_server_restarted(self):
        """Restore the normal GUI state after a cancelled generation."""
        self.server_worker = None
        self.chat_finished_handled = False
        self.current_thinking_text = ""
        self.set_status("Ready", "ready")
        self.model_status.setText(boltu_core.get_current_model())
        self.set_chat_controls(True)
        self.input.setFocus()
        self.scroll_to_bottom()

    # ========================================================
    # Chat error
    # ========================================================

    def chat_error(
        self,
        error
    ):

        if self.chat_finished_handled:

            return

        self.chat_finished_handled = True

        if self.assistant_message is not None:

            self.assistant_message.content.setPlainText(
                "Sorry, an error occurred:\n\n"
                + error
            )

            self.assistant_message.time_label.setText(
                self.timestamp()
            )

        self.set_status(
            "Error",
            "error"
        )

        self.set_chat_controls(
            True
        )
        self.send_button.setText("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

        self.input.setFocus()

        self.assistant_message = None
        self.assistant_start_time = None

        self.chat_worker = None

    # ========================================================
    # New chat
    # ========================================================

    def new_chat(self):

        self._cancel_inline_panel_for_action()

        boltu_core.reset_conversation()

        while (
            self.chat_layout.count()
            > 1
        ):

            item = (
                self.chat_layout.takeAt(0)
            )

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        self.assistant_message = None
        self.assistant_start_time = None

        self.current_thinking_text = ""

        self.chat_finished_handled = False

        startup = self.add_message(
            "Boltu",
            "How can I help you?",
            ""
        )
        startup.is_startup = True

        self.scroll_to_bottom()

    def _conversation_records(self):
        records = []
        for i in range(self.chat_layout.count() - 1):
            row = self.chat_layout.itemAt(i).widget()
            if row is None:
                continue
            message = row.findChild(QFrame, "conversationMessage")
            if message is None or getattr(message, "is_startup", False):
                continue
            speaker = getattr(message, "speaker", "")
            if speaker not in ("You", "Boltu"):
                continue
            records.append({
                "speaker": speaker,
                "text": getattr(message, "raw_text", ""),
                "timestamp": message.time_label.text(),
            })
        return records

    def save_chat(self):
        records = self._conversation_records()
        if not records:
            QMessageBox.information(self, "Boltu", "There is no conversation to save yet.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Boltu",
            str(CHAT_DIR / "My Chat.json"),
            "Boltu Chat (*.json)",
        )
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"

        data = {
            "format": "boltu-chat",
            "version": 1,
            "model": boltu_core.get_current_model(),
            "saved_at": self.timestamp(),
            "messages": records,
        }
        try:
            Path(filename).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.set_status("Chat saved", "ready")
        except Exception as e:
            QMessageBox.critical(self, "Boltu", f"Could not save the chat.\n\n{e}")

    def open_chat(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Boltu",
            str(CHAT_DIR),
            "Boltu Chat (*.json)",
        )
        if not filename:
            return

        try:
            data = json.loads(Path(filename).read_text(encoding="utf-8"))
            records = data.get("messages", [])
            if not isinstance(records, list):
                raise ValueError("Invalid chat file.")
        except Exception as e:
            QMessageBox.critical(self, "Boltu", f"Could not open the chat.\n\n{e}")
            return

        boltu_core.reset_conversation()
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.assistant_message = None
        self.assistant_start_time = None
        self.current_thinking_text = ""
        self.chat_finished_handled = False

        for record in records:
            speaker = record.get("speaker")
            text = record.get("text", "")
            timestamp = record.get("timestamp", "")
            if speaker not in ("You", "Boltu"):
                continue
            message = self.add_message(speaker, text, timestamp)
            if speaker == "You":
                boltu_core.add_user_message(text)
            else:
                boltu_core.add_assistant_message(text)
                self.render_message_equations(message)

        self.set_status("Chat loaded", "ready")
        self.set_chat_controls(True)
        self.input.setFocus()
        self.scroll_to_bottom()

    def show_conversation_context_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: #22252b; color: {TEXT_COLOR}; "
            f"border: 1px solid {BORDER_COLOR}; padding: 4px; }} "
            "QMenu::item { padding: 6px 22px; } "
            "QMenu::item:selected { background: #303d55; }"
        )
        copy_action = menu.addAction("Copy message")
        select_action = menu.addAction("Select message text")
        copy_all_action = menu.addAction("Copy entire conversation")
        chosen = menu.exec(self.scroll_area.viewport().mapToGlobal(position))

        # Find the message QTextEdit beneath the pointer, rather than acting on
        # whichever widget happened to have keyboard focus (often the input box).
        target = self.scroll_area.viewport().childAt(position)
        while target is not None and not isinstance(target, QTextEdit):
            target = target.parentWidget()

        if chosen == copy_action and isinstance(target, QTextEdit):
            target.copy()
        elif chosen == select_action and isinstance(target, QTextEdit):
            target.selectAll()
        elif chosen == copy_all_action:
            messages = []
            for row_index in range(self.chat_layout.count()):
                item = self.chat_layout.itemAt(row_index)
                row = item.widget()
                if row is None:
                    continue
                for editor in row.findChildren(QTextEdit, "conversationContent"):
                    parent = editor.parentWidget()
                    # Header labels are found in the containing message bubble.
                    bubble = parent.parentWidget() if parent is not None else None
                    speaker = "Message"
                    timestamp = ""
                    if bubble is not None:
                        labels = bubble.findChildren(QLabel)
                        if labels:
                            speaker = labels[0].text() or speaker
                        if len(labels) > 1:
                            timestamp = labels[1].text()
                    prefix = f"{speaker} [{timestamp}]" if timestamp else speaker
                    messages.append(f"{prefix}:\n{editor.toPlainText()}")
            QApplication.clipboard().setText("\n\n".join(messages))

    # ========================================================
    # Switch model
    # ========================================================

    def model_selection_changed(self, index):
        if self._restoring_model_selection or index < 0:
            return

        selected = self.model_selector.itemText(index)
        current = boltu_core.get_current_model()
        if not selected or selected == current:
            return

        self.pending_model_selection = selected
        self._show_model_switch_panel(selected)

    def _show_model_switch_panel(self, selected):
        if getattr(self, "switch_panel", None) is not None:
            self.content_stack.removeWidget(self.switch_panel)
            self.switch_panel.deleteLater()

        self.switch_panel = QFrame()
        self.switch_panel.setObjectName("settingsPanel")
        layout = QVBoxLayout(self.switch_panel)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Switch Model")
        title.setObjectName("settingsTitle")
        message = QLabel(
            f"Switch to <b>{selected}</b>?<br><br>"
            "The current conversation will be cleared."
        )
        message.setObjectName("settingsDescription")
        message.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.hide_inline_panel)
        confirm_btn = QPushButton("Switch")
        confirm_btn.setObjectName("primaryButton")
        confirm_btn.clicked.connect(
            lambda: self.confirm_inline_model_switch(selected)
        )
        buttons.addWidget(cancel_btn)
        buttons.addWidget(confirm_btn)

        layout.addWidget(title)
        layout.addWidget(message)
        layout.addStretch()
        layout.addLayout(buttons)
        self.content_stack.addWidget(self.switch_panel)
        self.content_stack.setCurrentWidget(self.switch_panel)
        self.set_status("Switch Model", "ready")
        self.input.setEnabled(True)
        self.input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _set_top_controls_enabled(self, enabled):
        # Inline panels are intentionally non-modal: all normal controls remain
        # usable, and clicking another control cancels the panel first.
        return

    def hide_inline_panel(self):
        pending = self.pending_model_selection
        self.pending_model_selection = None
        self.content_stack.setCurrentWidget(self.conversation_page)
        if getattr(self, "switch_panel", None) is not None:
            self.content_stack.removeWidget(self.switch_panel)
            self.switch_panel.deleteLater()
            self.switch_panel = None
        if pending:
            # The running model is intentionally omitted from the dropdown.
            # When a switch is cancelled, return to the neutral placeholder
            # instead of leaving the un-applied model selected.
            self._restoring_model_selection = True
            self.model_selector.setCurrentIndex(-1)
            self._restoring_model_selection = False
        if self.chat_worker is None or not self.chat_worker.isRunning():
            self.input.setEnabled(True)
        self.set_status("Ready", "ready")

    def confirm_inline_model_switch(self, selected):
        self.pending_model_selection = None
        self.content_stack.setCurrentWidget(self.conversation_page)
        if getattr(self, "switch_panel", None) is not None:
            self.content_stack.removeWidget(self.switch_panel)
            self.switch_panel.deleteLater()
            self.switch_panel = None
        if not boltu_core.set_current_model(selected):
            self._set_top_controls_enabled(True)
            self.input.setEnabled(True)
            self.set_status("Could not select the requested model.", "error")
            return
        boltu_core.save_config()
        self.set_chat_controls(False)
        self.set_status("Switching model...", "busy")
        self.server_worker = ServerWorker(selected)
        self.server_worker.success.connect(self.model_switched)
        self.server_worker.error.connect(self.server_error)
        self.server_worker.start()

    # ========================================================
    # Model switched
    # ========================================================

    def model_switched(self):

        model_start_time = self.timestamp()

        boltu_core.reset_conversation()

        while (
            self.chat_layout.count()
            > 1
        ):

            item = (
                self.chat_layout.takeAt(0)
            )

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        self.assistant_message = None
        self.assistant_start_time = None

        self.set_status(
            "Ready",
            "ready"
        )

        self.model_status.setText(
            boltu_core.get_current_model()
        )

        self.show_startup_message(
            model_start_time
        )

        self.refresh_models()

        self.set_chat_controls(
            True
        )

        self.input.setFocus()

    # ========================================================
    # Settings
    # ========================================================

    def open_settings(self):
        # Clicking Settings while its panel is already visible is handled by
        # eventFilter() as a toggle. This method is therefore only reached when
        # opening Settings (or switching to it from another inline panel).
        self.settings_panel = getattr(self, "settings_panel", None) or SettingsPanel()
        self.content_stack.addWidget(self.settings_panel) if self.settings_panel.parent() is None else None
        self.content_stack.setCurrentWidget(self.settings_panel)
        self.input.setEnabled(True)
        self.input.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_status("Model Settings", "ready")

    def apply_settings_panel(self, cpu_threads, context_size, max_tokens, temperature, thinking):
        boltu_core.apply_settings(cpu_threads, context_size, max_tokens, temperature, thinking)
        boltu_core.save_config()
        self.hide_inline_panel()
        reply = QMessageBox.question(
            self, "Boltu",
            "Settings saved.\n\nRestart the model server now to apply them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.restart_model()

    # ========================================================
    # Restart model
    # ========================================================

    def restart_model(self):

        model = (
            boltu_core.get_current_model()
        )

        self.set_chat_controls(
            False
        )

        self.set_status(
            "Restarting model...",
            "busy"
        )

        self.server_worker = (
            ServerWorker(model)
        )

        self.server_worker.success.connect(
            self.model_restarted
        )

        self.server_worker.error.connect(
            self.server_error
        )

        self.server_worker.start()

    # ========================================================
    # Model restarted
    # ========================================================

    def model_restarted(self):

        model_start_time = self.timestamp()

        boltu_core.reset_conversation()

        while (
            self.chat_layout.count()
            > 1
        ):

            item = (
                self.chat_layout.takeAt(0)
            )

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

        self.assistant_message = None
        self.assistant_start_time = None

        self.set_status(
            "Ready",
            "ready"
        )

        self.model_status.setText(
            boltu_core.get_current_model()
        )

        self.show_startup_message(
            model_start_time
        )

        self.set_chat_controls(
            True
        )

        self.input.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_all_messages)

    # ========================================================
    # Close
    # ========================================================

    def closeEvent(
        self,
        event
    ):

        self.set_status(
            "Stopping...",
            "busy"
        )

        try:

            if (
                self.chat_worker is not None
                and self.chat_worker.isRunning()
            ):

                self.chat_worker.quit()
                self.chat_worker.wait(2000)

        except Exception:

            pass

        try:

            if (
                self.server_worker is not None
                and self.server_worker.isRunning()
            ):

                self.server_worker.quit()
                self.server_worker.wait(2000)

        except Exception:

            pass

        boltu_core.stop_server()

        event.accept()


# ============================================================
# Application
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "Boltu"
    )

    app.setApplicationDisplayName(
        "Boltu"
    )

    app.setFont(
        QFont(
            "Segoe UI",
            9
        )
    )

    # Dark native dialogs, with a single consistent window title: Boltu.
    app.setStyleSheet(app.styleSheet() + """
        QMessageBox {
            background: #202329;
            color: #e7e9ed;
        }
        QMessageBox QLabel {
            color: #e7e9ed;
            font-size: 12px;
        }
        QMessageBox QPushButton {
            background: #2a2f37;
            color: #e7e9ed;
            border: 1px solid #3a4049;
            border-radius: 6px;
            padding: 5px 14px;
            min-width: 60px;
        }
        QMessageBox QPushButton:hover {
            background: #343a44;
        }
        QMessageBox QPushButton:default {
            background: #4f8cff;
            border-color: #4f8cff;
            color: white;
        }
    """)

    dialog_filter = BoltuDialogThemeFilter()
    app.installEventFilter(dialog_filter)
    app._boltu_dialog_filter = dialog_filter

    window = BoltuWindow()

    window.show()
    apply_windows_dark_titlebar(window)
    QTimer.singleShot(100, lambda: apply_windows_dark_titlebar(window))
    QTimer.singleShot(500, lambda: apply_windows_dark_titlebar(window))
    QTimer.singleShot(1200, lambda: apply_windows_dark_titlebar(window))

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":

    main()