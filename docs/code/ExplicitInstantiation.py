#!/usr/bin/env python

import itk
import sys

input_filename = sys.argv[1]

ImageType = itk.Image[itk.F,2]
reader = itk.ImageFileReader[ImageType].New(FileName = input_filename)
median = itk.MedianImageFilter[ImageType, ImageType].New()
median.SetInput(reader.GetOutput())

