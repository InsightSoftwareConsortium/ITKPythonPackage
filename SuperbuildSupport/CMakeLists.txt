cmake_minimum_required(VERSION 3.26.6 FATAL_ERROR)
# NOTE: 3.26.6 is the first cmake version to support Development.SABIModule

project(ITKPythonPackageSuperbuild CXX)

include(${CMAKE_CURRENT_SOURCE_DIR}/../cmake/ITKPythonPackage_Utils.cmake)
include(${CMAKE_CURRENT_SOURCE_DIR}/../cmake/ITKPythonPackage_SuperBuild.cmake)
