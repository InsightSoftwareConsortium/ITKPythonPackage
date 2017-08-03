#!/usr/bin/env python

import itk
import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

image = itk.imread(input_filename)
median = itk.MedianImageFilter.New(image, Radius = 2)
itk.imwrite(median, output_filename)
