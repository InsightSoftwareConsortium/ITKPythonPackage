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

Basic example
..............

Here is a simple python script that reads an image, applies a median image filter (radius of 2 pixels), and writes the resulting image in a file.

.. literalinclude:: code/ReadMedianWrite.py

ITK and NumPy
.............

A common use case for using ITK in Python is to mingle NumPy and ITK operations on raster data. ITK provides a large number of I/O image formats and several sophisticated image processing algorithms not available in any other packages. The ability to intersperse that with the SciPy ecosystem provides a great tool for rapid prototyping.

The following script shows how to integrate NumPy and `itk.Image`:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 16-59

NumPy and `itk.Mesh`:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 62-76

NumPy and `itk.Transform`:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 96-115

NumPy and `itk.Matrix`, VNL vectors, and VNL matrices:

.. literalinclude:: code/MixingITKAndNumPy.py
   :lines: 118-

ITK and Xarray
..............

An `itk.Image` can be converted to and from an `xarray.DataArray
<https://xarray.pydata.org/en/stable/generated/xarray.DataArray.html>`_ while
preserving metadata::

  da = itk.xarray_from_image(image)

  image = itk.image_from_xarray(da)

ITK and VTK
............

An `itk.Image` can be converted to and from a `vtk.vtkImageData
<https://vtk.org/doc/nightly/html/classvtkImageData.html>`_ while
preserving metadata::

  vtk_image = itk.vtk_image_from_image(image)

  image = itk.image_from_vtk_image(vtk_image)

ITK and napari
..............

An `itk.Image` can be converted to and from a `napari.layers.Image
<https://napari.org/api/stable/napari.layers.Image.html#napari.layers.Image>`_ while
preserving metadata with the `itk-napari-conversion package
<https://github.com/InsightSoftwareConsortium/itk-napari-conversion>`_.

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

To cast the pixel type of an image, use `.astype`:

.. literalinclude:: code/Cast.py
   :lines: 10-18

Metadata dictionary
...................

An `itk.Image` has a metadata dict of `key: value` pairs.


The metadata dictionary can be retrieved with::

  meta_dict = dict(image)

For example::

  In [3]: dict(image)
  Out[3]:
  {'0008|0005': 'ISO IR 100',
   '0008|0008': 'ORIGINAL\\PRIMARY\\AXIAL',
   '0008|0016': '1.2.840.10008.5.1.4.1.1.2',
   '0008|0018': '1.3.12.2.1107.5.8.99.484849.834848.79844848.2001082217554549',
   '0008|0020': '20010822',

Individual dictionary items can be accessed or assigned::

  print(image['0008|0008'])

  image['origin'] = [4.0, 2.0, 2.0]

In the Python dictionary interface to image metadata, keys for the spatial
metadata, the *'origin'*, *'spacing'*, and *'direction'*, are reversed in
order from `image.GetOrigin()`, `image.GetSpacing()`, `image.GetDirection()`
to be consistent with the `NumPy array index order
<https://scikit-image.org/docs/dev/user_guide/numpy_images.html#notes-on-the-order-of-array-dimensions>`_
resulting from pixel buffer array views on the image.

Access pixel data with NumPy indexing
.....................................

Array views of an `itk.Image` provide a way to set and get pixel values with NumPy indexing syntax, e.g.::

  In [6]: image[0,:2,4] = [5,5]

  In [7]: image[0,:4,4:6]
  Out[7]:
  NDArrayITKBase([[    5,  -997],
                  [    5, -1003],
                  [ -993,  -999],
                  [ -996,  -994]], dtype=int16)

Input/Output (IO)
.................

Convenient functions are provided read and write from ITK's many supported
file formats::

  image = itk.imread('image.tif')

  # Read in with a specific pixel type.
  image = itk.imread('image.tif', itk.F)

  # Read in an image series.
  # Pass a sorted list of files.
  image = itk.imread(['image1.png', 'image2.png', 'image3.png'])

  # Read in a volume from a DICOM series.
  # Pass a directory.
  # Only a single series, sorted spatially, will be returned.
  image = itk.imread('/a/dicom/directory/')

  # Write an image.
  itk.imwrite(image, 'image.tif')


  # Read a mesh.
  mesh = itk.meshread('mesh.vtk')

  # Write a mesh.
  itk.meshwrite(mesh, 'mesh.vtk')


  # Read a spatial transform.
  transform = itk.transformread('transform.h5')

  # Write a spatial transform.
  itk.transformwrite(transform, 'transform.h5')

Image filters and Image-like inputs and outputs
...............................................

All `itk` functional image filters operate on an `itk.Image` but also:

- `xarray.DataArray <https://xarray.pydata.org/en/stable/generated/xarray.DataArray.html>`_ *
- `numpy.ndarray <https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html>`_
- `dask.array.Array <https://docs.dask.org/en/latest/array.html>`_

* Preserves image metadata

Filter parameters
.................

ITK filter parameters can be specified in the following ways:

.. literalinclude:: code/FilterParameters.py
   :lines: 10-

Filter types
............

In `itk`, filters are optimized at compile time for each image pixel type and
image dimension. There are two ways to instantiate these filters with the `itk`
Python wrapping:

- *Implicit (recommended)*: Type information is automatically detected from the data. Typed filter objects and images are implicitly created.

.. literalinclude:: code/ImplicitInstantiation.py
   :lines: 8-

- *Explicit*: This can be useful if an appropriate type cannot be determined implicitly or when a different filter type than the default is desired.

To specify the type of the filter, use the `ttype` keyword argument. Explicit instantiation of a median image filter:

.. literalinclude:: code/ExplicitInstantiation.py
   :lines: 8-

Instantiate an ITK object
.........................

There are two types of ITK objects. Most ITK objects, such as images, filters, or adapters, are instantiated the following way:

.. literalinclude:: code/InstantiateITKObjects.py
   :lines: 6-8

Some objects, like a Matrix, Vector, or RGBPixel, do not require the attribute `.New()` to be added to instantiate them:

.. literalinclude:: code/InstantiateITKObjects.py
   :lines: 11

In case of doubt, look at the attributes of the object you are trying to instantiate.

Examples
--------

Examples can be found in the `ITKSphinxExamples project <https://itk.org/ITKExamples/src/index.html>`_.
