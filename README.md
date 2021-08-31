ITK Python Package
==================

This project provides a `setup.py` script to build ITK Python binary
packages and infrastructure to build ITK external module Python
packages.

ITK is an open-source, cross-platform system that provides developers
with an extensive suite of software tools for image analysis.

Installation
------------

To install the ITK Python package:

```
    $ pip install itk
```

Usage
-----

### Simple example script

```
    import itk
    import sys

    input_filename = sys.argv[1]
    output_filename = sys.argv[2]

    image = itk.imread(input_filename)

    median = itk.median_image_filter(image, radius=2)

    itk.imwrite(median, output_filename)
```

See also the [ITK Python Quick Start
Guide](https://itkpythonpackage.readthedocs.io/en/master/Quick_start_guide.html).
There are also many [downloadable examples documented in
Sphinx](https://itk.org/ITKExamples/search.html?q=Python).

For more information on ITK's Python wrapping, [an introduction is
provided in the ITK Software
Guide](https://itk.org/ITKSoftwareGuide/html/Book1/ITKSoftwareGuide-Book1ch3.html#x32-420003.7).

-   Free software: Apache Software license
-   Documentation: <http://itkpythonpackage.readthedocs.org>
-   Source code: <https://github.com/InsightSoftwareConsortium/ITKPythonPackage>
