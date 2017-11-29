Welcome to ITKPythonPackage's documentation!
============================================

This project provides a ``setup.py`` script to build ITK Python wheels and
infrastructure to build ITK external module Python wheels.

`ITK <https://www.itk.org/>`_ is an open-source, cross-platform system that provides developers with an extensive suite of software tools for image analysis.

To install the stable ITK Python package::

  python -m pip install --upgrade pip
  python -m pip install itk

The Python packages are built daily. To install the latest build from the ITK
Git *master* branch::

  python -m pip install --upgrade pip
  python -m pip install itk --no-index \
    -f https://github.com/InsightSoftwareConsortium/ITKPythonPackage/releases/tag/latest


For more information on ITK's Python wrapping, see `an introduction in the ITK
Software Guide
<https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch3.html#x32-420003.7>`_.
There are also many `downloadable examples documented in Sphinx
<https://itk.org/ITKExamples/search.html?q=Python>`_.


.. toctree::
   :maxdepth: 2
   :caption: Contents

   Quick_start_guide.rst
   Build_ITK_Module_Python_packages.rst
   Build_ITK_Python_packages.rst
   Miscellaneous.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
