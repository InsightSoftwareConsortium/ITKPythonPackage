===========================
Detailed build instructions
===========================

Building ITK Python wheels
--------------------------

Build the ITK Python wheel with the following command::

	mkvirtualenv build-itk
	pip install -r requirements-dev.txt
	python setup.py bdist_wheel

Efficiently building wheels for different version of python
-----------------------------------------------------------

If on a given platform you would like to build wheels for different version of python, you can download and build the ITK components independent from python first and reuse them when building each wheel.

Here are the steps:

- Build ITKPythonPackage with ITKPythonPackage_BUILD_PYTHON set to OFF

- Build "flavor" of package using::

	python setup.py bdist_wheel -- \
	  -DITK_SOURCE_DIR:PATH=/path/to/ITKPythonPackage-core-build/ITK-source
