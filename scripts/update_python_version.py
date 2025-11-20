#!/usr/bin/env python

"""Update the ITKPythonPackage version based off the ITK Git nightly-master
branch."""

import argparse
import sys
import os
import subprocess
from datetime import datetime

argparser = argparse.ArgumentParser(description=__doc__)
argparser.add_argument("itkSourceDir")

args = argparser.parse_args()
itkSourceDir = args.itkSourceDir
if not os.path.exists(os.path.join(itkSourceDir, ".git")):
    print("itkSourceDir does not appear to be a git repository!")
    sys.exit(1)

itkPythonPackageDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


os.chdir(itkSourceDir)
# "Wed Feb 8 15:21:09 2017"\n
commitDate = subprocess.check_output(
    ["git", "show", "-s", "--date=local", '--format="%cd"']
)
# Wed Feb 8 15:21:09 2017
commitDate = commitDate.strip()[1:-1]
# Wed Feb 08 15:21:09 2017
commitDate = commitDate.split(" ")
commitDate[2] = "{:02d}".format(int(commitDate[2]))
commitDate = " ".join(commitDate)
# 2017-02-08
commitDateDashes = datetime.strptime(commitDate, "%a %b %d %H:%M:%S %Y").strftime(
    "%Y-%m-%d"
)
# 20170208
commitDate = commitDateDashes.replace("-", "")

# v4.11.0-139-g922f2d9
#
revision = subprocess.check_output(["git", "describe", "--tags", "--long"])
revision.strip()
# 4.11.0-139-g922f2d9
revision = revision[1:]
version, numberOfCommits, gHash = revision.split("-")
version = version.strip()
numberOfCommits = numberOfCommits.strip()
gHash = gHash.strip()

pythonRevision = version
if int(numberOfCommits) > 0:
    pythonRevision += ".dev"
    pythonRevision += commitDate
    pythonRevision += "+"
    pythonRevision += numberOfCommits
    pythonRevision += "."
    pythonRevision += gHash

os.chdir(itkPythonPackageDir)
itkVersionPath = os.path.join(itkPythonPackageDir, "itkVersion.py")
if not os.path.exists(itkVersionPath):
    print("Expected file " + itkVersionPath + " not found!")
    sys.exit(1)
with open(itkVersionPath, "r") as fp:
    lines = fp.readlines()
with open(itkVersionPath, "w") as fp:
    for line in lines:
        if line.startswith("VERSION = "):
            fp.write("VERSION = '")
            fp.write(pythonRevision)
            fp.write("'\n")
        else:
            fp.write(line)


with open("CMakeLists.txt", "r") as fp:
    lines = fp.readlines()
with open("CMakeLists.txt", "w") as fp:
    for line in lines:
        if line.startswith("  # ITK nightly-master"):
            fp.write("  # ITK nightly-master ")
            fp.write(commitDateDashes)
            fp.write("\n")
        elif line.startswith("  set(ITK_GIT_TAG"):
            fp.write('  set(ITK_GIT_TAG "')
            fp.write(gHash[1:])
            fp.write('")\n')
        else:
            fp.write(line)
