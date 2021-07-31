from .qt_compatibility import QtCore, QtGui, QtWidgets, Qt
import re
import threading
import json
import logging
from typing import List, Tuple, Optional, Iterable
from concurrent.futures import Executor, ThreadPoolExecutor, wait, Future
from sys import modules as runtime_sys_modules, argv as sys_argv, platform as sys_platform, version_info as sys_version_info

import toolz as tz

import qtconsole.pygments_highlighter
from pygments.lexers import PythonLexer

from types import ModuleType
from pathlib import Path

#from . import wheel_fix
from .core import OrganizerNode as ONode, Node
from .config import get_user_config
from .cache import read_text_cached

from .core import UserScopeSettings, ScopeSettings, OrganizerNode, CodeElement
from .errors import BadArgsError, ModuleResolutionError, ScriptResolutionError
from .project_settings_module import Project

from . import serialize
from . import project_settings_module

logger = logging.getLogger(__name__)

COLUMN_WIDTH = 200

def make_module(name):
    module = ModuleType(name)
    runtime_sys_modules[name] = module
    return module

executors = make_module('call_map_executors')
Debug = make_module('call_map_debug')


def code_font():
    _code_font = QtGui.QFont('Monaco')
    _code_font.setStyleHint(QtGui.QFont.Monospace)
    _code_font.setPointSize(11)
    return _code_font


def maybe_first(iterable):
    for ii in iterable:
        return ii
    else:
        return None


def findParent(qobj, type_):
    while type(qobj) is not type_:
        qobj = qobj.parent()

    return qobj


class CallListItem(QtWidgets.QListWidgetItem):
    default_role_markers = {'child': ' ', 'definition': '.', 'parent': '<', 'signature': '-'}
    role_markers = default_role_markers.copy()
    type_markers = {'module': 'm:', 'class': 'c:', 'script': 's:'}
    type_background_colors = {
        #'class': QtGui.QColor(240, 220, 240),  # light purple
        #'module': QtGui.QColor(200, 240, 240),  # light blue
    }

    type_foreground_colors = {
        'class': QtGui.QColor(100, 20, 180),  # dark purple
        'module': QtGui.QColor(20, 100, 180),  # dark blue
        'script': QtGui.QColor(20, 100, 180),  # dark blue
    }

    role_foreground_colors = {
        'signature': QtGui.QColor('gray'),  # gray
    }

    def __init__(self, node: Node):
        """The parents call the node, children are called by the node.

        If not callable, the Node has no children

        :param relation: relation to the CallListItem on the left

        """
        super().__init__()

        self.node = node

        name = self.node.code_element.name

        self.setFont(code_font())

        fontMetrics = QtGui.QFontMetrics(self.font())

        icon = self.role_markers[self.node.code_element.role]

        try:
            color = self.type_background_colors[node.code_element.type]
        except KeyError:
            pass
        else:
            self.setBackground(QtGui.QBrush(color))

        try:
            color = self.type_foreground_colors[node.code_element.type]
        except KeyError:
            pass
        else:
            self.setForeground(QtGui.QBrush(color))

        try:
            color = self.role_foreground_colors[self.node.code_element.role]
        except KeyError:
            pass
        else:
            self.setForeground(QtGui.QBrush(color))

        if isinstance(icon, str):
            if self.node.code_element.role == 'signature':
                fullText = icon + ' ' + '[sig]'
            else:
                fullText = icon + ' ' + self.type_markers.get(node.code_element.type, '') + name
            elidedText = fontMetrics.elidedText(fullText, Qt.Qt.ElideRight, COLUMN_WIDTH - 25)
            self.setText(elidedText)
        else:
            raise NotImplementedError
            self.setText(name)
            self.setIcon(icon)

    @classmethod
    def configure_role_markers(cls, want_unicode_role_markers):
        if want_unicode_role_markers:
            cls.role_markers = tz.merge(cls.default_role_markers, {'definition': '・', 'parent': '⊲'})
        else:
            cls.role_markers = cls.default_role_markers

    def walk_left(self):
        for ll in self.listWidget().walk_left():
            yield ll.currentItem()

    def walk_right(self):
        for ll in self.listWidget().walk_right():
            yield ll.currentItem()

    def showSource(self, path) -> Tuple[bool, bool, str]:
        # returns success, reuse, text

        if path:
            _path = Path(path)

            main_widget = findParent(self.listWidget(), MainWidget)

            text_edit = main_widget.text_edit
            if _path == text_edit.current_path:
                return (True, True, '')

            text = read_text_cached(_path)

            # see http://www.qtcentre.org/archive/index.php/t-52574.html

            text_edit.current_path = _path

            return (True, False, text)
        else:
            return (False, True, '')

            #line = node.code_element.start_pos[0] - 1
            #scrollToLine(text_edit, line - 8)

    def highlight(self, cancel_event):
        if cancel_event.is_set():
            return

        text_edit = findParent(self.listWidget(), MainWidget).text_edit
        sig = Signaler()
        sig.setPlainText_highlight_and_scroll.connect(text_edit.setPlainText_highlight_and_scroll)

        #if (self.node.code_element.role == 'definition'
        #    and self.node.code_element.type == 'module'
        #    and self.listWidget().index > 0):
        #    text_edit.highlighter.reset()
        #else:
        success, reuse, text = self.showSource(self.node.code_element.call_pos[0])

        if cancel_event.is_set() or not success:
            text_edit.highlighter.reset()
            return
        else:
            call_pos = self.node.code_element.call_pos
            sig.setPlainText_highlight_and_scroll.emit(reuse, text, call_pos)


def next_nodes(node: Node, cancel_event: threading.Event) -> List[Node]:
    if node.code_element.role == 'signature':
        return []

    if (type(node) != ONode
        and node.code_element.path != None
        and node.code_element.type != 'module'):
        signatures = [node.with_new_role('signature')]
    else:
        signatures = []

    if cancel_event.is_set(): return ()

    try:
        children = list(node.children)
    except Exception as exc:
        children = []
        logger.error('{}; while finding outbound connections of {}.'.format(exc, node), exc_info=get_user_config()['EXC_INFO'])
    if cancel_event.is_set(): return ()

    try:
        parents = list(node.parents)
    except Exception as exc:
        parents = []
        logger.error('{}; while finding inbound connections of {}.'.format(exc, node), exc_info=get_user_config()['EXC_INFO'])
    if cancel_event.is_set(): return ()

    return signatures + children + parents


class UnthreadedExecutor:
    def submit(self, fn, *args, **kwargs) -> Future:
        result = fn(*args, **kwargs)
        future = Future()
        future.set_result(result)
        return future


class MuxExecutor(Executor):
    def __init__(self, max_workers=None, thread_name_prefix=''):
        self.unthreaded_executor = UnthreadedExecutor()
        if sys_version_info >= (3, 6):
            self.thread_pool_executor = ThreadPoolExecutor(max_workers=max_workers,
                                                           thread_name_prefix=thread_name_prefix)
        else:
            self.thread_pool_executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, **kwargs):
        if get_user_config()['MULTITHREADING']:
            executor = self.thread_pool_executor
        else:
            executor = self.unthreaded_executor

        return executor.submit(fn, *args, **kwargs)


executors.highlight_executor = MuxExecutor(max_workers=1, thread_name_prefix='highlight')
executors.main_executor = MuxExecutor(max_workers=1, thread_name_prefix='main')


class Signaler(QtCore.QObject):
    """Handles Qt Signals for multithreading

    Qt requires that objects in different threads pass information only through
    signals. Various signals are gathered in the `Signaler` class to make passing
    arguments more like using plain functions.

    """
    add_next = QtCore.Signal(int, Node, list)
    insertItem = QtCore.Signal(int, CallListItem)
    insertCallListItem = QtCore.Signal(int, object)
    focus = QtCore.Signal(CallListItem)
    setPlainText_highlight_and_scroll = QtCore.Signal(bool, str, tuple)
    progress = QtCore.Signal(int)
    setNode = QtCore.Signal(Node, list)


class CallList(QtWidgets.QListWidget):

    def __init__(self, map_widget, info_widget, index: int):
        super().__init__()

        self.map_widget = map_widget
        self.info_widget = info_widget
        self.index = index

        self.node = ONode('')
        self.nodes_to_items = {}

        self.currentItemChanged.connect(self.itemChangedSlot)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # appearance
        self.focused_palette = QtGui.QPalette()

        self.unfocused_palette = QtGui.QPalette()
        self.unfocused_palette.setColor(QtGui.QPalette.HighlightedText,
                                     QtGui.QColor('black'))
        self.unfocused_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor('lightgray'))

        self.setPalette(self.unfocused_palette)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.setMinimumWidth(COLUMN_WIDTH)
        self.setMaximumWidth(COLUMN_WIDTH)

        sizePolicy = QtWidgets.QSizePolicy()
        sizePolicy.setVerticalPolicy(Qt.QSizePolicy.Expanding)

        self.setSizePolicy(sizePolicy)
        self.setAttribute(QtCore.Qt.WA_MacShowFocusRect, False)

        #self.setAlternatingRowColors(True)

        self.populate_futures = []
        self.add_next_futures = []
        self.highlight_futures = []

        self.strict = False

    def setNode(self, node: Node, items: List[Node]):
        self.node = node
        self.clear()
        self.nodes_to_items.clear()

        for ii, item in enumerate(filter(tz.identity, items)):  # filter null items -- TODO: find better place for filter
            self.insertCallListItem(ii, item)

        # NOTE: previously `setNode` involved submitting a job to an Executor
        # and appending the future to self.populate_futures. Currently
        # self.populate_futures is always empty.

    def focus(self, current):
        self.info_widget.showInfo(current.node)
        if not self.map_widget.auto_highlight:
            return

        text = ', '.join(('< ' if node.code_element.role == 'parent' else '') + node.code_element.name
                         for node in self.map_widget.node_path())

        self.info_widget.setCallPath(text)

        cancel_event = threading.Event()
        fut = executors.highlight_executor.submit(current.highlight, cancel_event)
        fut.cancel_event = cancel_event
        self.highlight_futures.append(fut)

    def prepareToFocus(self):
        while self.highlight_futures:
            fut = self.highlight_futures.pop()
            fut.cancel()
            fut.cancel_event.set()

    def itemChangedSlot(self, current, previous):
        while self.add_next_futures:
            future = self.add_next_futures.pop()
            future.cancel()
            future.node.cancel_search()

            if not future.done() and not future.cancel_event.is_set():
                future.cancel_event.set()

        if current:
            try:
                node = current.node
            except AttributeError:
                return

            # clear immediately so user cannot issue commands on stale items
            self.map_widget.prepareToSetCallList(self.index + 1)

            self.prepareToFocus()

            wait(self.populate_futures + self.highlight_futures)

            self.focus(current)

            if self.strict:
                cancel_event = threading.Event()
                self.makeNextCallList(node, cancel_event)
            else:
                cancel_event = threading.Event()
                add_next_future = executors.main_executor.submit(self.makeNextCallList, node, cancel_event)
                add_next_future.node = node
                add_next_future.cancel_event = cancel_event
                self.add_next_futures.append(add_next_future)

    def _showCallPath(self):
        path = list(tz.cons(self.currentItem().node, (ll.currentItem().node for ll in self.walk_left())))
        path.reverse()

        text = ', '.join(('< ' if node.code_element.role == 'parent' else '')
                         + node.code_element.name
                         for node in path)

        self.info_widget.setCallPath(text)

    def remove_nodes(self, nodes: Iterable[Node]):
        for node in nodes:
            item = self.nodes_to_items.pop(node)
            self.takeItem(self.row(item))
            self.removeItemWidget(item)
            #assert 0
            #print(self.items())

    def add_nodes(self, nodes: Iterable[Node]):
        start = self.count()
        for ii, node in enumerate(nodes):
            self.insertCallListItem(start + ii, node)

    @QtCore.pyqtSlot(int, object)
    def insertCallListItem(self, ii, node: Node):
        self.nodes_to_items[node] = CallListItem(node)
        self.insertItem(ii, CallListItem(node))

    def makeNextCallList(self, node: Node, cancel_event: threading.Event):
        items = next_nodes(node, cancel_event)
        if not cancel_event.is_set():
            next_call_list = self.map_widget.callLists[self.index + 1]
            if self.strict:
                next_call_list.strict = True
                next_call_list.setNode(node, items)
                next_call_list.strict = False
            else:
                signaler = Signaler()
                signaler.setNode.connect(next_call_list.setNode)
                signaler.setNode.emit(node, items)

    def walk_right(self):
        return self.map_widget.callLists[self.index + 1:]

    def walk_left(self):
        if self.index > 0:
            return self.map_widget.callLists[self.index - 1: :-1]
        else:
            return ()

    def next_call_list(self):
        try:
            return self.map_widget.callLists[self.index + 1]
        except IndexError:
            return None

    def prev_call_list(self):
        if self.index > 0:
            return self.map_widget.callLists[self.index - 1]
        else:
            return None

    def focusInEvent(self, event):
        current = self.currentItem()
        if current:
            self.prepareToFocus()
            wait(self.populate_futures + self.highlight_futures)
            self.focus(current)
        self.setPalette(self.focused_palette)

    def focusOutEvent(self, event):
        if event.reason() != QtCore.Qt.ActiveWindowFocusReason:
            self.setPalette(self.unfocused_palette)

    def keyPressEvent(self, event):
        super().keyPressEvent(event) #ll.setFocus()

        if not event.isAccepted():
            if event.key() == Qt.Qt.Key_Right:
                _next = self.next_call_list()
                if _next and _next.count() > 0:
                    if all(future.done() for future in
                           tz.concatv(self.populate_futures, self.add_next_futures)):
                        _next.setFocus()
                        self.map_widget.ensureWidgetVisible(_next, 0, 0)
                        if self.next_call_list().currentItem() is None:
                            self.next_call_list().setCurrentRow(0)
                    else:
                        wait_item = _next.item(0)
                        wait_item.poked += 1
                        if wait_item.poked == 3:
                            wait_item.setText('QUIT POKING ME')
                event.accept()

            if event.key() == Qt.Qt.Key_Left:
                _prev = self.prev_call_list()
                if _prev:
                    _prev.setFocus()
                    (self.map_widget.ensureWidgetVisible(_prev, 0, 0))
                event.accept()

        if event.key() == Qt.Qt.Key_Space:
            pass

class MapLayout(QtWidgets.QHBoxLayout):
    def __init__(self, parent):
        super().__init__(parent)
        #self.addStretch(1)

    def sizeHint(self):
        size = super().sizeHint()
        width = self.count() * COLUMN_WIDTH
        return QtCore.QSize(width, self.parent().maximumHeight())

    def maximumSize(self):
        width = self.count() * COLUMN_WIDTH
        return QtCore.QSize(width, super().maximumSize().height())

    def minimumSize(self):
        width = self.count() * COLUMN_WIDTH
        return QtCore.QSize(width, super().minimumSize().height())


class MapWidget(QtWidgets.QScrollArea):
    def __init__(self, parent, info_widget, status_bar, node: Node):
        super().__init__(parent)

        self.info_widget = info_widget
        self.status_bar = status_bar

        self.callLists = []

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setWidget(QtWidgets.QWidget(self))

        layout = MapLayout(self.widget())
        #layout.setAlignment(QtCore.Qt.AlignRight)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        layout.setSizeConstraint(Qt.QLayout.SetMinAndMaxSize)

        self.currentIndex = -1
        self.prepareToSetCallList(0)

        self.root_list_items = {}  # type: Dict[Node, CallListItem]

        self.callLists[0].setNode(node, node.children)
        wait(self.callLists[0].populate_futures)

        for ii in range(self.callLists[0].count()):
            item = self.callLists[0].item(ii)
            child_node = item.node
            self.root_list_items[child_node] = item

        self.auto_highlight = True

    def prepareToSetCallList(self, index):
        oldIndex = self.currentIndex
        self.currentIndex = index

        try:
            ll = self.callLists[index]
        except IndexError:
            ll = CallList(self, self.info_widget, len(self.callLists))
            self.callLists.append(ll)

        self.widget().layout().insertWidget(ll.index, ll)

        while ll.populate_futures:
            fut = ll.populate_futures.pop()
            fut.cancel()
            fut.cancel_event.set()

        ll.clear()
        ll.nodes_to_items.clear()
        item = QtWidgets.QListWidgetItem('wait . . .')
        item.setFlags(QtCore.Qt.ItemNeverHasChildren)
        item.poked = 0
        ll.addItem(item)
        ll.show()
        self.ensureWidgetVisible(ll)

        if oldIndex != index:
            for ll in self.callLists[index+1:]:
                ll.hide()
                self.widget().layout().removeWidget(ll)

    def resizeEvent(self, event):
        # Note: must do super().resizeEvent before resizing the self.widget,
        # otherwise there will be minor graphical glitches.
        super().resizeEvent(event)
        self.widget().resize(self.widget().size().width(), event.size().height())

    def node_path(self):
        for ll in self.callLists:
            if ll.currentItem():
                yield ll.currentItem().node
            else:
                break

    def open_bookmark(self, bookmark_code_element_path: Iterable[CodeElement]):
        def same_except_location(aa: CodeElement, bb: CodeElement):
            return (aa.name == bb.name and
                    aa.module == bb.module and
                    aa.type == bb.type and
                    aa.role == bb.role)

        def same_except_name(aa: CodeElement, bb: CodeElement):
            return (aa.module == bb.module and
                    aa.type == bb.type and
                    aa.role == bb.role and
                    aa.call_pos == bb.call_pos)

        for ii, bookmark_code_element in enumerate(bookmark_code_element_path):
            ll = self.callLists[ii]  # type: CallList

            # TODO: use a with block to set strictness
            ll.strict = True

            wait(ll.populate_futures + ll.highlight_futures + ll.add_next_futures)

            near_misses = []

            for jj in range(ll.count()):
                ll_item = ll.item(jj)
                ll_code_element = ll_item.node.code_element
                if ll_code_element == bookmark_code_element:
                    ll.setCurrentItem(ll_item)
                    ll.setFocus()
                    wait(ll.add_next_futures)
                    break
                elif same_except_location(ll_code_element, bookmark_code_element):
                    near_misses.append((jj, 'Same except location.'))

                elif same_except_name(ll_code_element, bookmark_code_element):
                    near_misses.append((jj, 'Same except name.'))
            else:
                if near_misses:
                    idx, note = near_misses[0]
                    self.status_bar.showMessage(
                        'Exact bookmark not found. Nearest match followed. ({})'.format(note),
                        msecs=10000)
                    ll.setCurrentRow(idx)
                    ll.setFocus()
                else:
                    ll.setCurrentRow(0)
                    ll.setFocus()
                    ll.strict = False
                    return

            ll.strict = False

    def toggle_auto_highlight(self):
        self.auto_highlight = not self.auto_highlight
        self.status_bar.showMessage(
            'Auto highlight toggled {}'.format(
                'on' if self.auto_highlight else 'off'), msecs=3000)

        self.status_bar.update()

        if self.auto_highlight:
            current_callList = tz.first(cl for cl in self.callLists if cl.hasFocus())
            current = current_callList.currentItem()
            if current:
                current_callList.focus(current)


class InfoWidget(QtWidgets.QWidget):
    """Displays information about a node"""
    labels = ['code_path', 'name', 'type', 'module', 'position', 'defined at']
    auto_labels = ['name', 'type', 'module']

    def __init__(self, status_bar, parent=None):
        super().__init__(parent)

        self.status_bar = status_bar
        self.setLayout(QtWidgets.QGridLayout(self))
        self.current_code_element = None

        self.label_to_row = {label: ii for ii, label in enumerate(self.labels)}

        for ii, label in enumerate(self.labels):
            lineEdit = QtWidgets.QLineEdit(self)
            lineEdit.setFont(code_font())
            lineEdit.setReadOnly(True)
            qlabel = QtWidgets.QLabel('&' + label + ':', self)
            qlabel.setBuddy(lineEdit)
            qlabel.setAlignment(Qt.Qt.AlignLeft | Qt.Qt.AlignVCenter)

            self.layout().addWidget(qlabel, ii, 0)
            self.layout().addWidget(lineEdit, ii, 1)

        open_position_button = QtWidgets.QPushButton('Open')
        open_def_button = QtWidgets.QPushButton('Open')

        self.layout().addWidget(open_position_button, self.label_to_row['position'], 2)
        self.layout().addWidget(open_def_button, self.label_to_row['defined at'], 2)


        @open_position_button.clicked.connect
        def onclick():
            if self.current_code_element:
                self.open_in_editor_with_user_defined_function(
                    self.current_code_element.call_pos[0],
                    self.current_code_element.call_pos[1][0])


        @open_def_button.clicked.connect
        def onclick():
            if self.current_code_element and self.current_code_element.path:
                self.open_in_editor_with_user_defined_function(
                    self.current_code_element.path,
                    self.current_code_element.start_pos[0])


        self.layout().addItem(QtWidgets.QSpacerItem(0,0))
        self.layout().setRowStretch(self.layout().rowCount(), 1)


    def showInfo(self, node: Node):
        try:
            code_element = node.code_element
        except AttributeError:
            pass
        else:
            Debug.code_element = code_element
            Debug.node = node

            self.current_code_element = code_element

            for ii, label in enumerate(self.labels):
                lineEdit = self.layout().itemAtPosition(ii, 1).widget()

                if label == 'code_path':
                    continue
                elif label in self.auto_labels:
                    value = getattr(code_element, label)
                elif label == 'defined at':
                    if code_element.start_pos:
                        value = '{} : {}'.format(code_element.path, code_element.start_pos[0])
                    elif code_element.path:
                        value = code_element.path
                    else:
                        value = '[Unknown]'
                elif label == 'position':
                    value = '{} : {}'.format(code_element.call_pos[0], code_element.call_pos[1][0])

                lineEdit.setText(value if isinstance(value, str)
                                 else repr(value))

    def setCallPath(self, call_path):
        lineEdit = self.layout().itemAtPosition(0, 1).widget()
        lineEdit.setText(call_path)

    def open_in_editor_with_user_defined_function(self, path, line):
        user_defined_function = (get_user_config()['open_in_editor'])
        try:
            user_defined_function(path, line)
        except:
            message = 'Cannot open {} at line {}'.format(path, line)
            logger.exception(message)
            self.status_bar.showMessage(message, 10000)


class TargetHighlighter:
    def __init__(self, text_edit):
        self.text_edit = text_edit
        self.current_highlight_cursor = None

    def highlight(self, call_pos):
        self.reset()

        if call_pos[0] != None and call_pos[1] != (None, None):
            document = self.text_edit.document()
            self.call_pos = call_pos
            cursor = QtGui.QTextCursor(
                document.findBlockByLineNumber(call_pos[1][0] - 1))
            cursor.setPosition(cursor.block().position() + call_pos[1][1])

            anchor = cursor.position()
            cursor.movePosition(QtGui.QTextCursor.NextWord, anchor)

            self.current_highlight_cursor = cursor
            cursor.orig_format = cursor.charFormat()

            # WARNING: To be safe, make a new QTextCharFormat every time. If you
            # use the same one for more than one document, it will cause many
            # glitches. I do not know exactly when it is safe to share a format.
            # -- Andy Lee
            _fmt = QtGui.QTextCharFormat()
            _fmt.setBackground(QtGui.QColor('lightskyblue'))
            cursor.setCharFormat(_fmt)

    def reset(self):
        cc = self.current_highlight_cursor
        if cc:
            cc.setCharFormat(cc.orig_format)
            self.current_highlight_cursor = None


class PlainTextEdit(QtWidgets.QTextEdit):
    def setPlainText_highlight_and_scroll(self, reuse: bool, text: str, call_pos: tuple):
        if not reuse:
            self.setPlainText(text)

        self.highlighter.highlight(call_pos)
        if call_pos[1][0]:
            self.scrollToLine(call_pos[1][0] - 1 - 8)

    def scrollToLine(self, line):
        cursor = self.textCursor()
        block = self.document().findBlockByLineNumber(line)
        cursor.setPosition(block.position())

        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

        self.setTextCursor(cursor)

        #Widgets.text_edit.scrollBar().scrollContentsBy(0, 10)
        #Widgets.text_edit.horizontalScrollBar().setValue(10,10)


class SettingsWidget(QtWidgets.QTabWidget):
    def __init__(self, project: Project, map_widget: MapWidget, status_bar: QtWidgets.QStatusBar, parent=None):
        super().__init__(parent)

        self.project = project
        self.map_widget = map_widget
        self.status_bar = status_bar

        self.path_settings_widget = TextSettingsWidget(
            project, map_widget, status_bar, project_settings_module.sys_path, parent=self)

        self.module_settings_widget = TextSettingsWidget(
            project, map_widget, status_bar, project_settings_module.modules, parent=self)

        self.script_settings_widget = TextSettingsWidget(
            project, map_widget, status_bar, project_settings_module.scripts, parent=self)

        self.project_settings_widget = TextSettingsWidget(
            project, map_widget, status_bar, project_settings_module.project_settings, parent=self)

        self.bookmarks_json_widget = TextSettingsWidget(
            project, map_widget, status_bar, project_settings_module.bookmarks, parent=self)

        self.bookmarks_widget = BookmarksWidget(project, map_widget, parent=self)

        self.bookmarks_widget.bookmarks_changed.connect(self.bookmarks_json_widget.load_project_settings)
        self.bookmarks_json_widget.settings_changed.connect(self.bookmarks_widget.load_from_project_settings)

        self.addTab(self.bookmarks_widget, "bookmarks")
        self.addTab(self.path_settings_widget, "sys path")
        self.addTab(self.module_settings_widget, "modules")
        self.addTab(self.script_settings_widget, "scripts")
        self.addTab(self.project_settings_widget, "project settings")
        self.addTab(self.bookmarks_json_widget, "bookmarks (json)")

        if sys_platform == 'darwin':
            self.setStyleSheet('''
                QTabWidget::tab-bar {
                    left: 3px;
                }
            ''')

        #self.minimumSize = QtCore.QSize(200, 200)


class TextSettingsWidget(QtWidgets.QWidget):
    settings_changed = QtCore.Signal(list, list)

    def __init__(self, project: Project, map_widget: MapWidget, status_bar: QtWidgets.QStatusBar,
                 category: str, parent=None):
        super().__init__(parent)

        self.__init_gui_elements__()

        self.project = project
        self.map_widget = map_widget
        self.status_bar = status_bar
        self.category = category
        self.load_project_settings()
        self.textEdit.textChanged.connect(self.enableButtons)

    def __init_gui_elements__(self):
        self.setLayout(QtWidgets.QVBoxLayout(self))
        self.layout().setContentsMargins(3,3,3,3)
        self.layout().setSpacing(3)

        self.textEdit = QtWidgets.QTextEdit()
        self.textEdit.setFont(code_font())
        self.saveButton = QtWidgets.QPushButton('Commit')
        self.cancelButton = QtWidgets.QPushButton('Cancel')

        #self.buttonGroup = QtWidgets.QButtonGroup(self)
        #self.buttonGroup.addButton(self.saveButton)
        #self.buttonGroup.addButton(self.cancelButton)
        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.buttonLayout.addStretch(-1)
        self.buttonLayout.setContentsMargins(1,1,1,1)
        self.buttonLayout.setSpacing(15)

        self.saveButton.setMaximumWidth(200)
        self.saveButton.setMinimumWidth(100)
        self.cancelButton.setMaximumWidth(200)
        self.cancelButton.setMinimumWidth(100)

        self.layout().addWidget(self.textEdit)
        self.layout().addLayout(self.buttonLayout)

        self.buttonLayout.addWidget(self.saveButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.saveButton.pressed.connect(self.commit)
        self.cancelButton.pressed.connect(self.load_project_settings)

    def enableButtons(self):
        self.saveButton.setEnabled(True)
        self.cancelButton.setEnabled(True)

    def load_project_settings(self):
        text = json.dumps(self.project.encode(self.category, for_persistence=False), indent=True, sort_keys=True)
        self.textEdit.setPlainText(text)
        self.saveButton.setDisabled(True)
        self.cancelButton.setDisabled(True)

    def commit(self):
        type_ = project_settings_module.category_type[self.category]
        try:
            decoded = serialize.decode(type_, json.loads(self.textEdit.toPlainText()))
        except json.JSONDecodeError as err:
            message = 'Cannot decode JSON; {}'.format(err.args[0])
            logger.error(message)
            self.status_bar.showMessage(message, 10000)
            self.saveButton.setDisabled(True)
            return
        except serialize.DecodeError as err:
            message = '{}'.format(err.args[0])
            logger.error(message)
            self.status_bar.showMessage(message, 10000)
            self.saveButton.setDisabled(True)
            return

        try:
            has_changed, stale, additional = self.project.set_settings(self.category, decoded)
        except (ValueError, TypeError) as err:
            # TypeError -- raised by initial type validation in `set_settings`.
            # ModuleResolutionError -- raised by `module_nodes`
            # ScriptResolutionError -- raised by `script_nodes`

            message = 'Invalid settings; {}: {}'.format(type(err).__name__, err.args[0])
            logger.error(message)
            self.status_bar.showMessage(message, 10000)
            self.saveButton.setDisabled(True)
            return

        status_messages = []
        for key, err in tz.concatv(self.project.failures['python'][project_settings_module.modules].items(),
                                   self.project.failures['python'][project_settings_module.scripts].items()):
            message = '{}: {}'.format(type(err).__name__, err.args[0])
            logger.error(message)
            status_messages.append((logging.ERROR, message))

        if has_changed:
            if self.category in (project_settings_module.modules,
                                 project_settings_module.scripts):
                self.map_widget.callLists[0].remove_nodes(stale)
                self.map_widget.callLists[0].add_nodes(additional)

                # TODO: add/remove stale nodes in other callLists

            elif self.category == project_settings_module.files:
                print('TODO: implement settings update for {}'.format(self.category))
            elif self.category == project_settings_module.sys_path:
                # 1. Record code path
                # 2. regenerate root nodes and root list
                # 3. Follow previous code path

                old_code_element_path = list(node.code_element for node in self.map_widget.node_path())

                node = OrganizerNode('Root', [],
                                     list(tz.concatv(self.project.module_nodes['python'].values(),
                                                     self.project.script_nodes['python'].values())))

                try:
                    children = node.children
                except Exception as exc:
                    children = []
                    logger.error('{}; while finding inbound connections of {}.'.format(exc, node),
                                 exc_info=get_user_config()['EXC_INFO'])

                self.map_widget.callLists[0].setNode(node, children)

                self.map_widget.callLists[0].setFocus()

                self.map_widget.open_bookmark(old_code_element_path)

            elif self.category == project_settings_module.bookmarks:
                self.settings_changed.emit(stale, additional)

            elif self.category == 'project_settings':
                self.settings_changed.emit(stale, additional)

            else:
                print('TODO: implement settings update for {}'.format(self.category))

            try:
                self.project.update_persistent_storage()
            except Exception as err:
                message = 'Cannot save settings; {}'.format(err.args[0])
                logger.error(err, exc_info=get_user_config()['EXC_INFO'])
                status_messages.append((logging.ERROR, err.args[0]))
                self.load_project_settings()   # reload to reformat text
            else:
                status_messages.append((logging.INFO, 'Saved.'))
                self.load_project_settings()   # reload to reformat text

        else:
            status_messages.append((logging.INFO, 'Not saved (no change).'))
            self.load_project_settings()       # reload to reformat text

        self.status_bar.showMessage('. '.join(message for level, message in status_messages), 10000)


def bookmark_to_str(bookmark):
    return ', '.join(('< ' if code_element.role == 'parent' else '') + code_element.name
                     for code_element in bookmark)


class BookmarksWidget(QtWidgets.QWidget):
    bookmarks_changed = QtCore.Signal()

    def __init__(self, project: Project, map_widget: MapWidget, parent=None):
        super().__init__(parent)
        self.project = project
        self.map_widget = map_widget

        self.setLayout(QtWidgets.QVBoxLayout(self))
        self.layout().setContentsMargins(3,3,3,3)
        self.layout().setSpacing(3)

        self.buttonLayout = QtWidgets.QHBoxLayout()
        self.buttonLayout.setContentsMargins(1,1,1,1)
        self.buttonLayout.setSpacing(4)
        self.buttonLayout.addStretch(-1)

        self.visitButton = QtWidgets.QPushButton('Visit')
        self.visitButton.setMaximumWidth(200)
        self.visitButton.setMinimumWidth(100)
        self.addButton = QtWidgets.QPushButton('Add')
        self.addButton.setMaximumWidth(200)
        self.addButton.setMinimumWidth(100)
        self.deleteButton = QtWidgets.QPushButton('Delete')
        self.deleteButton.setMaximumWidth(200)
        self.deleteButton.setMinimumWidth(100)
        self.buttonLayout.addWidget(self.visitButton)
        self.buttonLayout.addWidget(self.addButton)
        self.buttonLayout.addWidget(self.deleteButton)
        self.buttonLayout.addStretch(-1)

        self.visitButton.pressed.connect(self.visitBookmark)
        self.addButton.pressed.connect(self.addBookmark)
        self.deleteButton.pressed.connect(self.deleteBookmark)

        self.listWidget = QtWidgets.QListWidget()

        self.layout().addWidget(self.listWidget)
        self.layout().addLayout(self.buttonLayout)

        self.load_from_project_settings()

    def load_from_project_settings(self):
        self.listWidget.clear()

        for ii, bookmark in enumerate(self.project.settings[project_settings_module.bookmarks]):
            item = QtWidgets.QListWidgetItem(bookmark_to_str(bookmark))
            item.setFont(code_font())
            item.setData(1, bookmark)
            self.listWidget.insertItem(ii, item)

    def visitBookmark(self):
        item = self.listWidget.currentItem()
        if item:
            bookmark = item.data(1)
            self.map_widget.open_bookmark(bookmark)

    def addBookmark(self):
        bookmark = list(node.code_element for node in self.map_widget.node_path())
        if bookmark:
            self.project.settings[project_settings_module.bookmarks].append(bookmark)
            item = QtWidgets.QListWidgetItem(bookmark_to_str(bookmark))
            item.setFont(code_font())
            item.setData(1, bookmark)
            self.listWidget.addItem(item)
            self.project.update_persistent_storage()

            self.bookmarks_changed.emit()
        else:
            logger.info('Empty bookmark ignored.')

    def deleteBookmark(self):
        item = self.listWidget.currentItem()
        if item:
            bookmark = item.data(1)
            self.listWidget.removeItemWidget(item)
            self.project.settings[project_settings_module.bookmarks].remove(bookmark)

            self.project.update_persistent_storage()
            self.load_from_project_settings()

            self.bookmarks_changed.emit()


def make_test_node():
    test_node = ONode('AAA',
                     parents=[ONode('BBB'), ONode('CCC')],
                     children=[ONode('DDD'), ONode('EEE')])

    for ii in range(100):
        test_node.children.append(ONode('X_' + repr(ii)))

    for child in test_node.children:
        child.children.append(ONode('Y' + child.code_element.name, [],
                                   [ONode('Z1' + child.code_element.name),
                                    ONode('Z2' + child.code_element.name)]))

    root_node = ONode('Root', [], [test_node])

    return root_node


class MyQApplication(QtWidgets.QApplication):

    def legacy_notify(self, obj: QtCore.QObject, event: QtCore.QEvent):
        """Fixes scrolling weirdness

        This is a legacy method for `notify` from before PyQt5. It doesn't work
        with PyQt5.

        """
        if (event.type() == QtCore.QEvent.Wheel):
            return wheel_fix.notify_wheel_event(self, obj, event)
        else:
            return super().notify(obj, event)


class MainWidget(QtWidgets.QSplitter):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setOrientation(QtCore.Qt.Horizontal)
        self.left_widget = QtWidgets.QWidget(self)
        self.right_widget = QtWidgets.QWidget(self)
        self.right_splitter = QtWidgets.QSplitter(self.right_widget)
        self.right_splitter.setOrientation(QtCore.Qt.Vertical)

        self.left_layout = QtWidgets.QVBoxLayout(self.left_widget)
        self.right_layout = QtWidgets.QVBoxLayout(self.right_widget)

        self.addWidget(self.left_widget)
        self.addWidget(self.right_widget)
        self.right_layout.addWidget(self.right_splitter)

        self.left_layout.setContentsMargins(0,0,0,0)
        self.right_layout.setContentsMargins(0,0,0,0)
        self.right_splitter.setContentsMargins(0,0,0,0)

        self.left_layout.setSpacing(0.0)
        self.right_layout.setSpacing(0.0)


    def finalize(self):
        self.setStretchFactor(0, 2)
        self.setStretchFactor(1, 1)
        self.right_splitter.setStretchFactor(0, 2)
        self.right_splitter.setStretchFactor(1, 1)

        self.setHandleWidth(1)
        self.setCollapsible(0, False)
        self.setCollapsible(1, False)

        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, True)


def make_app(user_scope_settings: UserScopeSettings, project_directory: Optional[str],
             enable_ipython_support: bool = False, show_gui: bool = True):
    from .jedi_dump import make_scope_settings

    ui_toplevel = ModuleType('call_map_ui_toplevel')

    project = project_settings_module.Project(project_directory)
    ui_toplevel.project = project

    stored_settings = project.load_from_persistent_storage()
    is_new_project = bool(stored_settings)
    project.update_settings(stored_settings)

    scope_settings = make_scope_settings(is_new_project, project.scope_settings, user_scope_settings)

    project.settings.update(
        {project_settings_module.modules: scope_settings.module_names,
         project_settings_module.scripts: scope_settings.scripts,
         project_settings_module.sys_path: scope_settings.effective_sys_path})

    project.update_module_resolution_path('python')
    project.make_platform_specific_nodes('python')

    errors = list(tz.concatv(project.failures['python'][project_settings_module.modules].values(),
                             project.failures['python'][project_settings_module.scripts].values()))
    # will also put in status bar later
    for error in errors:
        logger.error(error)

    try:
        ui_toplevel.project.update_persistent_storage()
    except FileNotFoundError as err:
        raise BadArgsError(err)

    node = OrganizerNode('Root', [],
                         list(tz.concatv(project.module_nodes['python'].values(),
                                         project.script_nodes['python'].values())))

    CallListItem.configure_role_markers(
        get_user_config()['UNICODE_ROLE_MARKERS'])

    app = QtCore.QCoreApplication.instance()
    if app is None:
        app = MyQApplication(sys_argv)
    ui_toplevel.app = app


    app.setQuitOnLastWindowClosed(True)

    main_window = QtWidgets.QMainWindow()
    main_window.layout().setSpacing(0)
    main_window.layout().setContentsMargins(0, 0, 0, 0)

    main_widget = MainWidget(main_window)
    main_window.setCentralWidget(main_widget)

    status_bar = main_window.statusBar()
    ui_toplevel.status_bar = status_bar
    status_bar.setSizeGripEnabled(False)

    info_widget = InfoWidget(main_widget, status_bar)
    ui_toplevel.info_widget = info_widget

    map_widget = MapWidget(main_widget, info_widget, status_bar, node)
    ui_toplevel.map_widget = map_widget

    text_edit_0 = PlainTextEdit()
    text_edit_0.current_path = None
    text_edit_0.highlighter = TargetHighlighter(text_edit_0)

    text_edit_0.setReadOnly(True)
    text_edit_0.setFont(code_font())

    ui_toplevel.pygments_highlighter = qtconsole.pygments_highlighter.PygmentsHighlighter(
        text_edit_0.document(), lexer=PythonLexer())


    text_edit_1 = QtWidgets.QTextEdit()
    text_edit_1.setFont(code_font())

    main_widget.text_edit = text_edit_0


    toggle_action = QtWidgets.QAction('&Turn Auto Highlight Off', main_window)
    view_menu = main_window.menuBar().addMenu('&View')
    view_menu.addAction(toggle_action)

    def _update_auto_highlight_menu_text():
        action_on_or_off = 'Off' if map_widget.auto_highlight else 'On'
        toggle_action.setText('&Turn Auto Highlight {}'.format(action_on_or_off))

    toggle_action.triggered.connect(map_widget.toggle_auto_highlight)
    toggle_action.triggered.connect(_update_auto_highlight_menu_text)

    ui_toplevel.settings_widget = SettingsWidget(ui_toplevel.project, map_widget, status_bar)

    def configure_sizes():
        main_widget.setSizes([4, 3])

        main_widget.right_splitter.setSizes([2,1])

        map_widget.setMinimumWidth(500)
        map_widget.setSizePolicy(QtWidgets.QSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding))

        info_widget.setSizePolicy(QtWidgets.QSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Maximum))

        text_edit_0.setMinimumWidth(400)
        text_edit_0.setMinimumHeight(300)
        text_edit_0.setSizePolicy(QtWidgets.QSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding))

        settings_widget = ui_toplevel.settings_widget
        settings_widget.setMinimumWidth(400)
        settings_widget.setSizePolicy(QtWidgets.QSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Minimum))

    configure_sizes()


    def fix_status_bar_shading(mesg):
        status_bar.show()

    status_bar.messageChanged.connect(fix_status_bar_shading)
    status_bar.showMessage('Starting', 1)
    status_bar.hide()
    if errors:
        status_bar.showMessage('. '.join(e.args[0] for e in errors), 10000)

    #ui_toplevel.right_layout = QtWidgets.QStackedLayout(main_widget.layout())
    main_widget.left_layout.addWidget(map_widget)
    main_widget.left_layout.addWidget(info_widget)
    #main_widget.left_layout.addWidget(status_bar)
    #main_widget.layout().addWidget(ui_toplevel.settings_widget, 2, 0)
    main_widget.right_splitter.addWidget(text_edit_0)
    main_widget.right_splitter.addWidget(ui_toplevel.settings_widget)
    main_widget.right_layout.addWidget(status_bar)
    #main_widget.layout().addWidget(text_edit_1, 1, 1)

    main_widget.resize(COLUMN_WIDTH * 4, 600)

    main_widget.finalize()

    ui_toplevel.main_widget = main_widget

    ui_toplevel.main_window = main_window
    if node.code_element.name != 'Root':
        ui_toplevel.main_window.setWindowTitle(node.code_element.name)
    else:
        ui_toplevel.main_window.setWindowTitle('Call Map')

    QtWidgets.qApp.setWindowIcon(QtGui.QIcon(
        str(Path(__file__).parent.joinpath('icons/cruciform-by-andylee.png'))))

    original_window_flags = ui_toplevel.main_window.windowFlags()

    if show_gui:
        MAXIMIZE_ON_START = True
        # the following is a workaround to fix window size when maximizing
        if MAXIMIZE_ON_START:
            ui_toplevel.main_window.setWindowFlags(Qt.Qt.FramelessWindowHint)
            ui_toplevel.main_window.setWindowState(Qt.Qt.WindowFullScreen)
            ui_toplevel.main_window.setVisible(True)

            ui_toplevel.main_window.setWindowFlags(original_window_flags)
            ui_toplevel.main_window.setWindowState(Qt.Qt.WindowMaximized)
            ui_toplevel.main_window.setVisible(True)
        else:
            ui_toplevel.main_window.resize(1800, 1000)
            ui_toplevel.main_window.show()

    map_widget.callLists[0].setFocus()

    def customFullScreen(self):
        # experimental
        self.setWindowFlags(Qt.Qt.FramelessWindowHint)
        self.setWindowState(Qt.Qt.WindowFullScreen)
        self.show()

    def cancelFullScreen(self):
        self.setWindowFlags(original_window_flags)
        self.show()

    ui_toplevel.main_window.customFullScreen = customFullScreen.__get__(ui_toplevel.main_window)
    ui_toplevel.main_window.cancelFullScreen = cancelFullScreen.__get__(ui_toplevel.main_window)

    return ui_toplevel


def _resolve_robustly(str_paths: List[str]):
    import os.path
    paths = []
    for ff in str_paths:
        try:
            pp = Path(ff).resolve()
        except FileNotFoundError as err:
            logger.error('Could not resolve {} from {}'.format(ff, os.path.realpath('.')))
        else:
            paths.append(pp)

    return paths


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Create root node from filename contents')
    parser.add_argument('-m', '--modules', metavar='M', type=str, nargs='+',
                        help='Modules (e.g. "os.path").',
                        default=[])
    parser.add_argument('-f', '--files', metavar='F', type=str, nargs='+',
                        help='Script or module file names.',
                        default=[])
    parser.add_argument('-p', '--add-to-sys-path', metavar='P', type=str,
                        nargs='+', help='''Directories to add to the analysis
                        Python module search path ("sys_path"), where modules
                        will be found during analysis. By default the Python
                        interpreter's `sys.path` is included. Note that the
                        module resolution order in Python is first match; earlier items in
                        `sys_path` have higher priority.''', default=[])
    parser.add_argument('-d', '--project-directory', metavar='PROJ_DIR', action='store', type=Path,
                        default=None,
                        help=('''Where to store `call_map` bookmarks, modules, sys_path, etc.
                              If not set, these will not be saved.'''))
    parser.add_argument('--no-interpreter-sys-path', action='store_true',
                        help='''Tells `call_map` not explicitly include the
                        `sys.path` from the interpreter in the Python module
                        search path. (Note that the analysis backend `jedi` as
                        of v0.10.0 will still fall back to the interpreter's
                        `sys.path` if it cannot resolve modules using the
                        `sys_path` that `call_map` passes to it.)
                        ''')
    parser.add_argument('--ipython', action='store_true', help='''Enables
                        IPython integration. See
                        `dev_helper_tools/shell_tools.zsh` in the `call_map`
                        source tree.''')
    parser.add_argument('-v', '--verbose', action='store_true', help='''Increase
                        logging verbosity.''')
    parser.add_argument('--version', action='store_true', help='''Print version and exit.''')

    args = parser.parse_args()

    if args.version:
        from . import version
        print(version)
        exit()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=get_user_config()['LOG_LEVEL'])

    module_names = args.modules

    file_names = _resolve_robustly(args.files)  # type: List[Path]

    additional_paths = _resolve_robustly(args.add_to_sys_path)  # type: List[Path]

    user_scope_settings = UserScopeSettings(
        module_names=module_names,
        file_names=file_names,
        include_runtime_sys_path=(not args.no_interpreter_sys_path),
        add_to_sys_path=additional_paths)

    try:
        ui_toplevel = make_app(user_scope_settings, project_directory=args.project_directory)
        runtime_sys_modules[ui_toplevel.__name__] = ui_toplevel
        enable_ipython_support = args.ipython

        if enable_ipython_support:
            # Previously this code was to stop segfault on exit.
            # It was tentatively removed around v0.2.0 due to improvements in ipython apparently obviating it.
            #import atexit
            #atexit.register(ui_toplevel.main_window.deleteLater)
            pass
        else:
            exit(ui_toplevel.app.exec_())

    except (BadArgsError, ModuleResolutionError) as err:
        if not args.ipython:
            logger.error(err)
            exit(1)
        else:
            raise
