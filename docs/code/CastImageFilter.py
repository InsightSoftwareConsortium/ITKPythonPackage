#!/usr/bin/env python

import itk
import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

image = itk.imread(input_filename)
InputType = type(image)
# Find input image dimension
input_dimension = image.GetImageDimension()
# Select float as output pixel type
OutputType = itk.Image[itk.UC, input_dimension]

# Functional interface
casted = itk.cast_image_filter(image, ttype=(InputType, OutputType))

# Object-oriented interface
cast_filter = itk.CastImageFilter[InputType, OutputType].New()
cast_filter.SetInput(image)
cast_filter.Update()
casted = cast_filter.GetOutput()

# imwrite calls .Update()
itk.imwrite(cast_filter, output_filename)
