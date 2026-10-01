# Third-party software

ModelCheck source is MIT licensed. Third-party libraries are distributed under their own terms. The project uses the open-source distribution of PySide6/Qt; it does not require a commercial Qt license for this open-source development setup.

Main dependencies:

| Component | Project | License family |
| --- | --- | --- |
| PySide6, Shiboken, Qt Core/Gui/Widgets | https://www.qt.io/qt-for-python | LGPLv3 / other offered Qt licenses; module-specific terms apply |
| pandas | https://pandas.pydata.org/ | BSD-3-Clause |
| NumPy | https://numpy.org/ | BSD-3-Clause, with bundled-library notices |
| scikit-learn | https://scikit-learn.org/ | BSD-3-Clause |
| SciPy | https://scipy.org/ | BSD-3-Clause, with bundled-library notices |
| joblib | https://joblib.readthedocs.io/ | BSD-3-Clause |
| threadpoolctl | https://github.com/joblib/threadpoolctl | BSD-3-Clause |

The development build is a folder, not a statically linked single binary. Qt libraries remain separate in `_internal` and can be replaced. There is no restriction on reverse engineering needed to debug modifications to LGPL-covered libraries. ModelCheck has not modified these libraries.

`tools/collect_licenses.py` copies installed distribution license files, package metadata and ModelCheck notices into `THIRD-PARTY-LICENSES` in the build. The repository's `licenses` folder includes the LGPLv3 and GPLv3 texts. For the Qt/PySide source corresponding to the installed versions, use the upstream source releases:

- Qt 6.11.2: https://download.qt.io/archive/qt/6.11/6.11.2/submodules/
- PySide 6.11.2: https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.11.2
- Qt license and component notices: https://doc.qt.io/qtforpython-6/licenses.html

Dependency updates can change license obligations. Preserve upstream notices and check the terms before redistributing a changed build. Development builds are not presented as a completed commercial distribution review.
