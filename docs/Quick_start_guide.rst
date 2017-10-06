===========================
Quick start guide
===========================

.. _quick-start:

Installation
------------

To install the ITK Python package::

    $ python -m pip install --upgrade pip
    $ python -m pip install itk

If a pre-compiled wheel package is not found for your Python distribution, then it will
attempt to build from source.

.. note::

  On Windows machines, the source path cannot be greater than 50 characters or
  issues will occur during build time due to filename truncation in Visual
  Studio. If you must compile from source, clone this repository in a short
  directory, like *C:/IPP*. Then, run `setup.py` within the repository via the
  command line.


Usage
-----

Basic examples
..............

Here is a simple python script that reads an image, applies a median image filter (radius of 2 pixels), and writes the resulting image in a file.

.. literalinclude:: code/ReadMedianWrite.py

There are two ways to instantiate filters with ITKPython:

- Implicit (recommended): ITK type information is automatically detected from the data. Typed filter objects and images are implicitly created.

.. literalinclude:: code/ImplicitInstantiation.py
   :lines: 8-

- Explicit: This can be useful if a filter cannot automatically select the type information (e.g. `CastImageFilter`), or to detect type mismatch errors which can lead to cryptic error messages.

Explicit instantiation of median image filter:

.. literalinclude:: code/ImplicitInstantiation.py
   :lines: 8-

Explicit instantiation of cast image filter:

.. literalinclude:: code/CastImageFilter.py
   :lines: 9-

ITK Python types
................

+---------------------+--------------------+
| C++ type            | Python type        |
+=====================+====================+
| float               | itk.F              |
+---------------------+--------------------+
| double              | itk.D              |
+---------------------+--------------------+
| unsigned char       | itk.UC             |
+---------------------+--------------------+
| std::complex<float> | itk.complex[itk.F] |
+---------------------+--------------------+

This list is not exhaustive and is only presented to illustrate the type names. The complete list of types can be found in the `ITK Software Guide <https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch9.html#x48-1530009.5>`_.

Types can also be obtained from their name in the C programming language:

.. literalinclude:: code/CompareITKTypes.py
   :lines: 5

Instantiate an ITK object
.........................

There are two types of ITK objects. Most ITK objects (images, filters, adapters, ...) are instantiated the following way:

.. literalinclude:: code/InstantiateITKObjects.py
   :lines: 6-8

Some objects (matrix, vector, RGBPixel, ...) do not require the attribute `.New()` to be added to instantiate them:

.. literalinclude:: code/InstantiateITKObjects.py
   :lines: 11

In case of doubt, look at the attributes of the object you are trying to instantiate.

Mixing ITK and NumPy
--------------------

A common use case for using ITK in Python is to mingle NumPy and ITK operations on raster data. ITK provides a large number of I/O image formats and several sophisticated image processing algorithms not available in any other packages. The ability to intersperse that with numpy special purpose hacking provides a great tool for rapid prototyping.

The following script shows how to integrate NumPy and ITK:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 8-32


Similar functions are available to work with VNL vector and matrices:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 34-


Examples
--------

Examples can be found in the `ITKExamples project <https://itk.org/ITKExamples/src/index.html>`_.
