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
castFilter = itk.CastImageFilter[InputType, OutputType].New()
castFilter.SetInput(image)
itk.imwrite(castFilter, output_filename)
