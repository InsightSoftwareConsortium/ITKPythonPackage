.. ITKPythonPackage documentation master file, created by
   sphinx-quickstart on Mon May 29 14:09:52 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ITKPythonPackage's documentation!
============================================

This project provides a ``setup.py`` script that build ITK Python wheels.

ITK is an open-source, cross-platform system that provides developers with an extensive suite of software tools for image analysis.

The Python packages are built daily. To install the ITK Python package::

	$ python -m pip install --upgrade pip
	$ python -m pip install itk -f https://github.com/InsightSoftwareConsortium/ITKPythonPackage/releases/tag/latest

For more information on ITK's Python wrapping, see an introduction in the ITK Software Guide. There are also many downloadable examples documented in Sphinx.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   Automated_wheels_building_with_scripts.rst
   Prerequisites.rst
   Detailed_build_instructions.rst
   Miscellaneous.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
