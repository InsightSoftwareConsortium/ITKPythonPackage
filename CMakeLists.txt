cmake_minimum_required(VERSION 3.26.6 FATAL_ERROR)
# NOTE: 3.26.6 is the first cmake version to support Development.SABIModule

project(ITKPythonPackage CXX)

if(NOT DEFINED ITKPythonPackage_SUPERBUILD)
  set(ITKPythonPackage_SUPERBUILD ON)
endif()

include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/ITKPythonPackage_Utils.cmake)

if(ITKPythonPackage_SUPERBUILD)
    include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/ITKPythonPackage_SuperBuild.cmake)
else()
    include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/ITKPythonPackage_BuildWheels.cmake)
endif()
