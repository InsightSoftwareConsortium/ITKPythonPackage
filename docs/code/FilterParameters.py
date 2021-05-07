#!/usr/bin/env python3

import itk
import sys

input_filename = sys.argv[1]

image = itk.imread(input_filename, itk.F)

# Pythonic snake case keyword arguments:
#
#   number_of_iterations
#
smoothed = itk.anti_alias_binary_image_filter(image, number_of_iterations=3)

# CamelCase keyword arguments:
#
#   NumberOfIterations
#
smoother = itk.AntiAliasBinaryImageFilter.New(image, NumberOfIterations=3)
smoother.Update()
smoothed = smoother.GetOutput()

# CamelCase Set method:
#
#   SetNumberOfIterations
#
smoother = itk.AntiAliasBinaryImageFilter.New(image)
smoother.SetNumberOfIterations(3)
smoother.Update()
smoothed = smoother.GetOutput()
