#!/usr/bin/env python3

import itk

# Instantiate SmartPointer objects
InputType = itk.Image[itk.F,3]
OutputType = itk.Image[itk.F,3]
median = itk.MedianImageFilter[InputType, OutputType].New()

# Instantiate non-SmartPointer objects
pixel = itk.RGBPixel[itk.UC]()
