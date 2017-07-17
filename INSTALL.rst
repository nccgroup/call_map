============
Installation
============

.. default-role:: code


Standard Installation with Pip
-------------------------------

Call Map is distributed as a Python package. It requires `Python 3.5`,
`pip>=8.1.2`, and `jedi==0.10.0` [*]_. Other requirements can be installed
automatically once you have the correct versions of `pip` and `jedi`.
(If you don't have `Python 3.5`, see `Getting Python 3.5`_.)

Before installing for the first time, consider `Using Virtualenv`_.
To install `call_map`, from the top level directory of `call_map`, run::

  pip3 install --upgrade pip              # make sure pip is >=8.1.2
  pip3 install --no-cache-dir -e .        # caching sometimes breaks

Note that some Python 3 distributions call the package manager `pip`, and some
call it `pip3`.

I have included instructions using `conda`, `apt`, and `brew` if you prefer
obtaining as many depencencies as possible using those package managers. I also
include instructions for obtaining `Python 3.5` with `apt` and `brew`.

More details about `PyQt5` specifically can be found at `the Riverbank download
page`__ (Riverbank is the developer of `PyQt5`).

__ https://www.riverbankcomputing.com/software/pyqt/download5

.. [*] A small part of `call_map` relies on internal structures of `jedi`, which
       may change in future releases. I plan to make `call_map` rely less on
       `jedi` internals in future `call_map` releases.


Using Virtualenv
-----------------

Setting up virtual environment is optional but recommended. Virtualenv makes it
easy to start over if things break, by deleting the virtualenv directory. To
set it up, run::

  python -m venv --system-site-packages $HOME/py3env
  export PATH=$HOME/py3env/bin:$PATH

  # update command hash table in bash/zsh
  hash pip3
  hash python


Getting Python 3.5
-------------------

You can obtain the `official release`__ or use a package manager. Specific
instructions for Mac OS and Ubuntu are included below.

__ https://www.python.org/downloads/release/python-352/

Mac OS
~~~~~~~

You can use `brew`::

  brew install python3

You can also use `brew` to compile PyQt5::

  brew install --with-python3 pyqt5


Ubuntu
~~~~~~~

You can use `apt` to install `Python 3.5` and `PyQt5`::

  sudo apt install python3-pyqt5 virtualenv


Using Conda
------------

You can use `conda` to install `pyqt` and `qtconsole`, then `pip` to install
`jedi` and `call_map`::

  pip install conda
  hash conda
  conda install pygments
  conda install pyqt
  conda install qtconsole
  conda install toolz

Now follow the `pip` installation instructions in `Standard Installation with
Pip`_. `pip` will not reinstall the packages you installed with conda.
