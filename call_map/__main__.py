
from .gui import main

if __name__ == '__main__':
    main()

    try:
        __IPYTHON__
    except NameError:
        pass
    else:
        from .gui import Debug
        from sys import modules
        ui_toplevel = modules['call_map_ui_toplevel']
