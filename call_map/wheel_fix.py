"""
Utilities for locking scroll orientation

Normally you can scroll in any direction you want, but sometimes that is
not desirable.

The only function you should be using from this module is
:func:`notify_wheel_event`. Use it from your custom notify method,
for example::

    class MyQApplication(QtGui.QApplication):
        def notify(self, obj: QtCore.QObject, event: QtCore.QEvent):
            if (event.type() == QtCore.QEvent.Wheel):
                return wheel_fix.notify_wheel_event(self, obj, event)
            else:
                return super().notify(obj, event)

"""

from PyQt5 import QtCore, QtGui, Qt, QtWidgets

HORIZONTAL = 1
VERTICAL = 2

LOCK_INTERVAL = 200

locked_orientation = None

timer = QtCore.QTimer()
timer.setInterval(LOCK_INTERVAL)


def unlock():
    global locked_orientation
    locked_orientation = None
    timer.stop()

timer.timeout.connect(unlock)


def update_lock_orientation(event):
    global locked_orientation

    if locked_orientation is None:
        locked_orientation = event.orientation()
    else:
        timer.stop()

    timer.start()


def notify_wheel_event(app: QtWidgets.QApplication,
                       obj: QtCore.QObject,
                       event: QtCore.QEvent):
    """Notify obj or obj.parent() based on orientation lock state"""

    update_lock_orientation(event)

    if (event.orientation() == locked_orientation
        and (type(obj) is not QtGui.QScrollBar
             or obj.orientation() == locked_orientation)):

        return super(type(app), app).notify(obj, event)
    else:
        return super(type(app), app).notify(obj.parent(), event)
