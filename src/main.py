import sys
from pathlib import Path

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from .main_window import MainWindow

APP_NAME = "银河麒麟服务器多架构包下载工具"
ICON_NAME = "kylin-server-rpm-search"


def _application_icon():
    icon = QIcon.fromTheme(ICON_NAME)
    if not icon.isNull():
        return icon
    project_icon = (
        Path(__file__).resolve().parent.parent
        / "packaging/usr/share/icons/hicolor/scalable/apps"
        / f"{ICON_NAME}.svg"
    )
    return QIcon(str(project_icon))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("ziyiliunian")
    app.setWindowIcon(_application_icon())
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
