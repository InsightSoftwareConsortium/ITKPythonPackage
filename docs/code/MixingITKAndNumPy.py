#!/usr/bin/env python3

import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

import itk
import numpy as np

# Read input image
itk_image = itk.imread(input_filename)

# Run filters on itk.Image

# View only of itk.Image, pixel data is not copied
np_view = itk.array_view_from_image(itk_image)

# Copy of itk.Image, pixel data is copied
np_copy = itk.array_from_image(itk_image)
# Equivalent
np_copy = np.asarray(itk_image)


# Do NumPy stuff...


# Convert back to ITK, view only, data is not copied
itk_np_view = itk.image_view_from_array(np_copy)

# Convert back to ITK, data is copied
itk_np_copy = itk.image_from_array(np_copy)

# Save result
itk.imwrite(itk_np_view, output_filename)

# VNL matrix from np.ndarray
arr = np.zeros([3,3], np.uint8)
matrix = itk.vnl_matrix_from_array(arr)

# Array from VNL matrix
arr = itk.array_from_vnl_matrix(matrix)

# VNL vector from np.ndarray
vec = np.zeros([3], np.uint8)
vnl_vector = itk.vnl_vector_from_array(vec)

# Array from VNL vector
vec = itk.array_from_vnl_vector(vnl_vector)

# itk.Matrix from np.ndarray
mat = itk.matrix_from_array(np.eye(3))

# np.ndarray from itk.Matrix
arr = itk.array_from_matrix(mat)
