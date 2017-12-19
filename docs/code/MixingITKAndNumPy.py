#!/usr/bin/env python

import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

import itk
import numpy as np

# Read input image
itk_image = itk.imread(input_filename)

# Run filters on itk.Image

# View only of itk.Image, data is not copied
np_view = itk.GetArrayViewFromImage(itk_image)

# Copy of itk.Image, data is copied
np_copy = itk.GetArrayFromImage(itk_image)


# Do numpy stuff


# Convert back to itk, view only, data is not copied
itk_np_view = itk.GetImageViewFromArray(np_copy)

# Convert back to itk, data is copied
itk_np_copy = itk.GetImageFromArray(np_copy)

# Save result
itk.imwrite(itk_np_view, output_filename)

# Vnl matrix from array
arr = np.zeros([3,3], np.uint8)
matrix = itk.GetVnlMatrixFromArray(arr)

# Array from Vnl matrix
arr = itk.GetArrayFromVnlMatrix(matrix)

# Vnl vector from array
vec = np.zeros([3], np.uint8)
vnl_vector = itk.GetVnlVectorFromArray(vec)

# Array from Vnl vector
vec = itk.GetArrayFromVnlVector(vnl_vector)
