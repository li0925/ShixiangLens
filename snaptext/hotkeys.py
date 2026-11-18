"""Windows hotkeys, dispatched on Qt's native event loop."""
import ctypes
import sys
from ctypes import wintypes
from PyQt5.QtCore import QAbstractNativeEventFilter
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, app, handlers):
        super().__init__()
        self.app = app
        self.handlers = {}
        self.failed = []
        if sys.platform != 'win32':
            self.failed = [name for _, name, _ in handlers]
            return
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        for index, (key, name, callback) in enumerate(handlers, 0x5310):
            sequence = name if '+' in name or name.startswith('F') else 'Ctrl+Alt+' + key
            code = int(QKeySequence(sequence)[0])
            modifiers = 0x4000
            if code & int(Qt.CTRL): modifiers |= 2
            if code & int(Qt.ALT): modifiers |= 1
            if code & int(Qt.SHIFT): modifiers |= 4
            if code & int(Qt.META): modifiers |= 8
            basic = code & 0x01ffffff
            virtual = 0x70 + basic-int(Qt.Key_F1) if int(Qt.Key_F1) <= basic <= int(Qt.Key_F24) else basic
            if self.user32.RegisterHotKey(None, index, modifiers, virtual):
                self.handlers[index] = callback
            else:
                self.failed.append(name)
        app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == 'win32' and event_type in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.handlers:
                self.handlers[msg.wParam]()
                return True, 0
        return False, 0

    def close(self):
        if sys.platform == 'win32':
            for index in self.handlers:
                self.user32.UnregisterHotKey(None, index)
        self.app.removeNativeEventFilter(self)
        self.handlers.clear()
