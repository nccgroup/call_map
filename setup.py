import setuptools
import glob
import os.path as osp
import json as _json
from pathlib import Path as _Path

requirements = [
        #'jedi>=0.10.0, <=0.10.2',
        'jedi==0.10.2',
        'toolz', 'pygments', 'qtconsole']

# If PyQt5 was installed using conda, pip will not recognize it
# Therefore import it to see if it is installed.
try:
    import PyQt5
except ImportError:
    requirements += ['PyQt5']

_package_info = (
    _json.loads(_Path(__file__).parent.joinpath('call_map', 'package_info.json').read_text()))

setuptools.setup(
    name='call_map',
    version=_package_info['version'],
    description='A GUI for viewing call graphs in Python',
    author='Andy Lee',
    license='MIT',
    classifiers=[
        'Programming Language :: Python :: 3.5',
    ],

    install_requires=requirements,

    entry_points={
        'console_scripts': ['call_map=call_map.gui:main'],
    },

    package_data={
        '': ['*.png']
    },

    packages=setuptools.find_packages(exclude=['contrib', 'docs', 'tests*', 'scratch'])
)
