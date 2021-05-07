#!/usr/bin/env python3

import numpy as np
import itk
import sys

input_filename = sys.argv[1]
output_filename = sys.argv[2]

image = itk.imread(input_filename)

# Cast to an unsigned char pixel type
cast_image = image.astype(itk.UC)

# Equivalent
cast_image = image.astype(np.uint8)

itk.imwrite(cast_image, output_filename)
