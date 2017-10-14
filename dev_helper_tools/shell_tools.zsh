
function ipy_call_map {
    QT_API=pyside2 ipython --gui=qt -im call_map -- --ipython $@
}
