#!/usr/bin/env python3

import subprocess
import sys
import os
import tempfile

def add_test(cmd):
    cmd.insert(0, sys.executable)
    subprocess.check_call(cmd)

def cleanup(files):
    for f in files:
        if os.path.isdir(f):
            os.rmdir(f)
        else:
            os.remove(f)

# Create temporary folder to save output images
temp_folder = tempfile.mkdtemp()
# Change current working directory to find scripts
dir_ = os.path.dirname(sys.argv[0])
if len(dir_):
    os.chdir(dir_)

# Create input image for tests to avoid saving a binary file
# in the git repository of this project.
baseline_image = os.path.join(temp_folder, "baseline.png")
add_test(["CreateBaseline.py", baseline_image])

# Run test ReadMedianWrite.py
output_image = os.path.join(temp_folder, "filtered_image.png")
add_test(["ReadMedianWrite.py", baseline_image, output_image])
cleanup([output_image])

# Run test ImplicitInstantiation.py
add_test(["ImplicitInstantiation.py", baseline_image])

# Run test ExplicitInstantiation.py
add_test(["ExplicitInstantiation.py", baseline_image])

# Run test Cast.py
output_image = os.path.join(temp_folder, "filtered_image.png")
add_test(["Cast.py", baseline_image, output_image])
cleanup([output_image])

# Run test CompareITKTypes.py
add_test(["CompareITKTypes.py"])

# Run test InstantiateITKObjects.py
add_test(["InstantiateITKObjects.py"])

# Run test FilterParameters.py
add_test(["FilterParameters.py", baseline_image])

# Run test MixingITKAndNumPy.py
output_image = os.path.join(temp_folder, "filtered_image.png")
add_test(["MixingITKAndNumPy.py", baseline_image, output_image])
cleanup([output_image])

# Must be last
# Remove baseline image and temporary folder
cleanup([baseline_image, temp_folder])
