
function ipy_call_map {
    QT_API=pyqt5 ipython --gui=qt -im call_map -- --ipython $@
}
