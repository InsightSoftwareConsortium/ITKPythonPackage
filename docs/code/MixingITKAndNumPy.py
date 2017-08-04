#!/usr/bin/env python

import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

import itk
import numpy as np

# Read input image
itk_image = itk.imread(input_filename)

#run filters on itkImage

#view only of itkImage, data is not copied
np_view = itk.GetArrayViewFromImage( itk_image )

#copy of itkImage, data is copied
np_copy = itk.GetArrayFromImage( itk_image )


#do numpy stuff

#convert back to itk, view only, data is not copied
itk_np_view = itk.GetImageViewFromArray( np_copy)

#convert back to itk, data is not copied
itk_np_copy = itk.GetImageFromArray( np_copy)

# Save result
itk.imwrite(itk_np_view, output_filename)

# Vnl matrix[View] from array
arr = np.zeros([3,3], np.uint8)
matrix_view = itk.GetVnlMatrixViewFromArray(arr)
matrix = itk.GetVnlMatrixFromArray(arr)

# Array[View] from Vnl matrix
arr_view = itk.GetArrayViewFromVnlMatrix(matrix)
arr = itk.GetArrayFromVnlMatrix(matrix)

# Vnl vector[View] from array
vec = np.zeros([3], np.uint8)
vnl_vector_view = itk.GetVnlVectorViewFromArray(vec)
vnl_vector = itk.GetVnlVectorFromArray(vec)

# Array[View] from Vnl vector
vec_view = itk.GetArrayViewFromVnlVector(vnl_vector)
vec = itk.GetArrayFromVnlVector(vnl_vector)

