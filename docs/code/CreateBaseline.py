#!/usr/bin/env python3

import itk
import sys

image = itk.Image[itk.UC,2].New()
image.SetRegions([10,10])
image.SetOrigin([0,0])
image.SetSpacing([0.5,0.5])
image.Allocate()
image.FillBuffer(1)
itk.imwrite(image, sys.argv[1])
