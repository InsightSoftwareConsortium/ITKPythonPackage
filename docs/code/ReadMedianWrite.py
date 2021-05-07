#!/usr/bin/env python3

import itk
import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

image = itk.imread(input_filename)

median = itk.median_image_filter(image, radius=2)

itk.imwrite(median, output_filename)
