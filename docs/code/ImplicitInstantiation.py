#!/usr/bin/env python

import itk
import sys

input_filename = sys.argv[1]

# Use `ImageFileReader` instead of the wrapping function `imread` to illustrate this example.
reader = itk.ImageFileReader.New(FileName=input_filename)
# Here we specify the filter input explicitly
median = itk.MedianImageFilter.New(Input=reader.GetOutput())
# Same as above but shortened. `Input` does not have to be specified.
median = itk.MedianImageFilter.New(reader.GetOutput())
# Same as above. `.GetOutput()` does not have to be specified.
median = itk.MedianImageFilter.New(reader)

