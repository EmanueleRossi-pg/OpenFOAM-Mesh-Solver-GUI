#!/usr/bin/env python3
# Reusable Fusion-dark theme

import os
from PyQt5.QtWidgets import QApplication, QWidget # type: ignore
from PyQt5.QtGui import QPalette, QColor # type: ignore

def set_qt_env():
    
    
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

    
    if os.environ.get("QT_XCB_GL_INTEGRATION", "").strip().lower() == "none":
        
        del os.environ["QT_XCB_GL_INTEGRATION"]
        # If you explicitly want to force GLX instead, uncomment the next line:
        # os.environ["QT_XCB_GL_INTEGRATION"] = "glx"

def apply_fusion_dark(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    bg      = QColor(45, 45, 48)
    base    = QColor(37, 37, 38)
    altBase = QColor(51, 51, 55)
    text    = QColor(235, 235, 235)
    dim     = QColor(180, 180, 180)
    btn     = QColor(63, 63, 70)
    hi      = QColor(90, 140, 230)

    # Active
    pal.setColor(QPalette.Active, QPalette.Window, bg)
    pal.setColor(QPalette.Active, QPalette.Base, base)
    pal.setColor(QPalette.Active, QPalette.AlternateBase, altBase)
    pal.setColor(QPalette.Active, QPalette.Text, text)
    pal.setColor(QPalette.Active, QPalette.WindowText, text)
    pal.setColor(QPalette.Active, QPalette.Button, btn)
    pal.setColor(QPalette.Active, QPalette.ButtonText, text)
    pal.setColor(QPalette.Active, QPalette.ToolTipBase, text)
    pal.setColor(QPalette.Active, QPalette.ToolTipText, QColor(30, 30, 30))
    pal.setColor(QPalette.Active, QPalette.Highlight, hi)
    pal.setColor(QPalette.Active, QPalette.HighlightedText, QColor(255, 255, 255))

    # Inactive = same as Active
    for role in (
        QPalette.Window, QPalette.Base, QPalette.AlternateBase, QPalette.Text,
        QPalette.WindowText, QPalette.Button, QPalette.ButtonText,
        QPalette.ToolTipBase, QPalette.ToolTipText, QPalette.Highlight,
        QPalette.HighlightedText
    ):
        pal.setColor(QPalette.Inactive, role, pal.color(QPalette.Active, role))

    # Disabled (slightly dim)
    pal.setColor(QPalette.Disabled, QPalette.Window, bg)
    pal.setColor(QPalette.Disabled, QPalette.Base, base)
    pal.setColor(QPalette.Disabled, QPalette.AlternateBase, altBase)
    pal.setColor(QPalette.Disabled, QPalette.Text, dim)
    pal.setColor(QPalette.Disabled, QPalette.WindowText, dim)
    pal.setColor(QPalette.Disabled, QPalette.Button, btn)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, dim)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, hi.darker(130))
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(230, 230, 230))

    app.setPalette(pal)
    app.setStyleSheet("""
        QWidget { font-size: 14px; }
        QGroupBox {
            font-weight: 600;
            border: 1px solid #707070;
            border-radius: 8px;
            margin-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            top: -4px;
            padding: 0 4px;
        }
        QLabel.hint { color: #cfcfcf; }
        QPushButton { padding: 6px 14px; border-radius: 8px; }
        QPushButton:hover { border: 1px solid #6699ff; }
        QCheckBox { padding: 4px 0; }
    """)

def center_on_screen(w: QWidget):
    geo = w.frameGeometry()
    center = w.screen().availableGeometry().center()
    geo.moveCenter(center)
    w.move(geo.topLeft())
