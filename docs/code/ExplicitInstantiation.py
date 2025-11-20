#!/usr/bin/env python3

import itk
import sys

input_filename = sys.argv[1]

# An apriori ImageType
PixelType = itk.F
ImageType = itk.Image[PixelType, 2]
image = itk.imread(input_filename, PixelType)

# An image type dynamically determined from the type on disk
image = itk.imread(input_filename)
ImageType = type(image)

# Functional interface
# The `ttype` keyword argument specifies the filter type.
smoothed = itk.median_image_filter(image, ttype=(ImageType, ImageType))

# Object-oriented interface
reader = itk.ImageFileReader[ImageType].New(file_name=input_filename)
median = itk.MedianImageFilter[ImageType, ImageType].New()
median.SetInput(reader.GetOutput())
median.Update()
smoothed = median.GetOutput()
