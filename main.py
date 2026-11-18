import os
import sys

# PyQt must use its own plugins even when launched from an Anaconda shell.
if not getattr(sys, 'frozen', False):
    for name in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        os.environ.pop(name, None)

from PyQt5.QtCore import Qt
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication
from snaptext.desktop import DesktopApp


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setApplicationName('SnapText')
    # Retain the existing AppLocalDataLocation so settings and pins survive.
    app.setApplicationDisplayName('拾像 Lens')
    from snaptext.brand import icon
    app.setWindowIcon(icon())
    app.setQuitOnLastWindowClosed(False)
    if len(sys.argv) == 3 and sys.argv[1] == '--verify':
        from snaptext.diagnostics import verify
        return verify(app, sys.argv[2])
    socket = QLocalSocket()
    socket.connectToServer('ShixiangLens-local-v1')
    if socket.waitForConnected(500):
        socket.write(b'show')
        socket.waitForBytesWritten(500)
        return 0
    server = QLocalServer(app)
    QLocalServer.removeServer('ShixiangLens-local-v1')
    server.listen('ShixiangLens-local-v1')
    controller = DesktopApp(app, preload=True, persist=True)
    def activate():
        connection = server.nextPendingConnection()
        if connection:
            connection.close()
            connection.deleteLater()
        controller.show_home()
    server.newConnection.connect(activate)
    if len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
        from PyQt5.QtGui import QImage
        controller.add_pin(QImage(sys.argv[1]))
    else:
        controller.show_home()
    app.aboutToQuit.connect(controller.shutdown)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
