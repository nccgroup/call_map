'''
The qt_compatibility module is to make it easy to switch between different Qt/Python bridge implementations.

'''

QT_API = 'PySide2'

if QT_API == 'PySide2':
    from PySide2 import QtCore, QtGui, QtWidgets

    Qt = QtWidgets
    Qt.Qt = QtCore.Qt
