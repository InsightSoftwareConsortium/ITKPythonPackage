#!/usr/bin/env python

import itk
import sys

input_filename = sys.argv[1]

PixelType = itk.F
ImageType = itk.Image[PixelType,2]

# Functional interface
image = itk.imread(input_filename, PixelType)
smoothed = itk.median_image_filter(image, ttype=(ImageType, ImageType))

# Object-oriented interface
reader = itk.ImageFileReader[ImageType].New(FileName=input_filename)
median = itk.MedianImageFilter[ImageType, ImageType].New()
median.SetInput(reader.GetOutput())
median.Update()
smoothed = median.GetOutput()
