import sys
from PyQt5.QtWidgets import QApplication
from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Search RPM")
    app.setOrganizationName("ziyiliunian")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    main()
