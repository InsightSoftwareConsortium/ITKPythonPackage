===========================
Quick start guide
===========================

.. _quick-start:

Installation
------------

To install the ITK Python package::

    $ pip install itk


Usage
-----

Basic examples
..............

Here is a simple python script that reads an image, applies a median image filter (radius of 2 pixels), and writes the resulting image in a file.

.. literalinclude:: code/ReadMedianWrite.py

In `itk`, filters are optimized at compile time for each image pixel type and
image dimension. There are two ways to instantiate these filters with the `itk`
Python wrapping:

- *Implicit (recommended)*: Type information is automatically detected from the data. Typed filter objects and images are implicitly created.

.. literalinclude:: code/ImplicitInstantiation.py
   :lines: 8-

- *Explicit*: This can be useful if an appropriate type cannot be determined implicitly, e.g. with the `CastImageFilter`, and when a different filter type than the default is desired.

Explicit instantiation of a median image filter:

.. literalinclude:: code/ExplicitInstantiation.py
   :lines: 8-

Explicit instantiation of cast image filter:

.. literalinclude:: code/Cast.py
   :lines: 10-18

ITK Python types
................

+---------------------+--------------------+--------------------+
| C++ type            | Python type        | NumPy dtype        |
+=====================+====================+====================+
| float               | itk.F              | np.float32         |
+---------------------+--------------------+--------------------+
| double              | itk.D              | np.float64         |
+---------------------+--------------------+--------------------+
| unsigned char       | itk.UC             | np.uint8           |
+---------------------+--------------------+--------------------+
| std::complex<float> | itk.complex[itk.F] | np.complex64       |
+---------------------+--------------------+--------------------+

This list is not exhaustive and is only presented to illustrate the type names. The complete list of types can be found in the `ITK Software Guide <https://itk.org/ItkSoftwareGuide.pdf>`_.

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

Filter Parameters
.................

ITK filter parameters can be specified in the following ways:

.. literalinclude:: code/FilterParameters.py
   :lines: 10-


Mixing ITK and NumPy
--------------------

A common use case for using ITK in Python is to mingle NumPy and ITK operations on raster data. ITK provides a large number of I/O image formats and several sophisticated image processing algorithms not available in any other packages. The ability to intersperse that with the SciPy ecosystem provides a great tool for rapid prototyping.

The following script shows how to integrate NumPy and ITK:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 8-33


Similar functions are available to work with `itk.Matrix`, VNL vectors and matrices:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 35-


Examples
--------

Examples can be found in the `ITKSphinxExamples project <https://itk.org/ITKExamples/src/index.html>`_.
