#!/usr/bin/env python3

import sys
from pathlib import Path

data_dir = Path(__file__).parent.resolve() / '..' / 'data'

input_image_filename = sys.argv[1]
temp_dir = Path(input_image_filename).parent
output_image_filename = sys.argv[2]
input_mesh_filename = data_dir / 'cow.vtk'
output_mesh_filename = temp_dir / 'cow.vtk'
input_transform_filename = data_dir / 'rigid.tfm'
output_transform_filename = temp_dir / 'rigid.tfm'

import itk
import numpy as np

# Read input image
itk_image = itk.imread(input_image_filename)

# Run filters on itk.Image

# View only of itk.Image, pixel data is not copied
array_view = itk.array_view_from_image(itk_image)

# Copy of itk.Image, pixel data is copied
array_copy = itk.array_from_image(itk_image)
# Equivalent
array_copy = np.asarray(itk_image)

# Image metadata
# Sequences, e.g. spacing, are in zyx (NumPy) indexing order
metadata = dict(itk_image)

# Pixel array and image metadata together
# in standard Python data types + NumPy array
# Sequences, e.g. spacing, are in xyz (ITK) indexing order
image_dict = itk.dict_from_image(itk_image)


# Do interesting things...


# Convert back to ITK, view only, data is not copied
itk_image_view = itk.image_view_from_array(array_copy)

# Convert back to ITK, data is copied
itk_image_copy = itk.image_from_array(array_copy)

# Add the metadata
for k, v in metadata.items():
    itk_image_view[k] = v

# Save result
itk.imwrite(itk_image_view, output_image_filename)

# Convert back to itk image data structure
itk_image = itk.image_from_dict(image_dict)


# Read input mesh
itk_mesh = itk.meshread(input_mesh_filename)

# Convert to standard Python data types + NumPy arrays
mesh_dict = itk.dict_from_mesh(itk_mesh)


# Do interesting things...


# Convert back to itk mesh data structure
itk_mesh = itk.mesh_from_dict(mesh_dict)

# Save result
itk.meshwrite(itk_mesh, output_mesh_filename)


# itk.Mesh inherits from itk.PointSet,
# create a PointSet from the Mesh
itk_pointset = itk.PointSet[itk.F, 3].New()
itk_pointset.SetPoints(itk_mesh.GetPoints())
itk_pointset.SetPointData(itk_mesh.GetPointData())

# Convert to standard Python data types + NumPy arrays
pointset_dict = itk.pointset_from_dict(itk_pointset)


# Do interesting things...


# Convert back to itk pointset instance
itk_pointset = itk.pointset_from_dict(pointset_dict)


# Read input transforms
#
# This is a Python list
#
# When there is more than one transformation
# the list defines a transformation chain
itk_transforms = itk.transformread(input_transform_filename)

# Convert to standard Python data types + NumPy arrays
transform_dicts = [itk.dict_from_transform(t) for t in itk_transforms]


# Do interesting things...


# Convert back to itk transform instance
itk_transforms = [itk.transform_from_dict(t) for t in transform_dicts]

# Save result
itk.transformwrite(itk_transforms, output_transform_filename)


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
# Equivalent
arr = np.asarray(mat)
