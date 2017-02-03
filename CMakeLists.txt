cmake_minimum_required(VERSION 3.3)

project(ITKPythonPackage NONE)

if(NOT DEFINED ITKPythonPackage_SUPERBUILD)
  set(ITKPythonPackage_SUPERBUILD 1)
endif()

if(ITKPythonPackage_SUPERBUILD)


  # compile with multiple processors
  include(ProcessorCount)
  ProcessorCount(NPROC)
  if(NOT NPROC EQUAL 0)
    set( ENV{MAKEFLAGS} "-j${NPROC}" )
  endif()

  #-----------------------------------------------------------------------------
  # Search for python interpreter and libraries

  message(STATUS "SuperBuild - Searching for python")

  # Sanity checks
  if(DEFINED PYTHON_INCLUDE_DIR AND NOT EXISTS ${PYTHON_INCLUDE_DIR})
    message(FATAL_ERROR "PYTHON_INCLUDE_DIR variable is defined but corresponds to nonexistent directory")
  endif()
  if(DEFINED PYTHON_LIBRARY AND NOT EXISTS ${PYTHON_LIBRARY})
    message(FATAL_ERROR "PYTHON_LIBRARY variable is defined but corresponds to nonexistent file")
  endif()
  if(DEFINED PYTHON_EXECUTABLE AND NOT EXISTS ${PYTHON_EXECUTABLE})
    message(FATAL_ERROR "PYTHON_EXECUTABLE variable is defined but corresponds to nonexistent file")
  endif()

  if(NOT DEFINED PYTHON_INCLUDE_DIR
     OR NOT DEFINED PYTHON_LIBRARY
     OR NOT DEFINED PYTHON_EXECUTABLE)

    find_package ( PythonLibs REQUIRED )
    find_package ( PythonInterp REQUIRED )

  endif()

  message(STATUS "SuperBuild -   PYTHON_INCLUDE_DIR: ${PYTHON_INCLUDE_DIR}")
  message(STATUS "SuperBuild -   PYTHON_LIBRARY: ${PYTHON_LIBRARY}")
  message(STATUS "SuperBuild -   PYTHON_EXECUTABLE: ${PYTHON_EXECUTABLE}")
  message(STATUS "SuperBuild - Searching for python[OK]")

  #-----------------------------------------------------------------------------
  # ITK: This project builds ITK and associated Python modules
  include(ExternalProject)

  set(ITK_REPOSITORY "git://github.com/InsightSoftwareConsortium/ITK.git")
  set(ITK_GIT_TAG "origin/master")

  set(ITK_SOURCE_DIR ${CMAKE_BINARY_DIR}/ITK)
  set(ITK_BINARY_DIR ${CMAKE_BINARY_DIR}/ITK-build)

  message(STATUS "SuperBuild - ITK")
  message(STATUS "SuperBuild -   ITK_SOURCE_DIR: ${ITK_SOURCE_DIR}")
  message(STATUS "SuperBuild -   ITK_BINARY_DIR: ${ITK_BINARY_DIR}")

  ExternalProject_add(ITK
    GIT_REPOSITORY ${ITK_REPOSITORY}
    GIT_TAG ${ITK_GIT_TAG}
    SOURCE_DIR ${ITK_SOURCE_DIR}
    BINARY_DIR ${ITK_BINARY_DIR}
    CMAKE_CACHE_ARGS
      -DBUILD_TESTING:BOOL=OFF
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_INSTALL_PREFIX}
      -DITK_LEGACY_SILENT:BOOL=ON
      -DITK_WRAP_PYTHON:BOOL=ON
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR}
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE}
    USES_TERMINAL_DOWNLOAD 1
    USES_TERMINAL_UPDATE 1
    USES_TERMINAL_CONFIGURE 1
    USES_TERMINAL_BUILD 1
    INSTALL_COMMAND ""
    )
  set(ITK_DIR ${CMAKE_BINARY_DIR}/ITK-build)

  message(STATUS "SuperBuild -   ITK_DIR: ${ITK_DIR}")
  message(STATUS "SuperBuild - ITK[OK]")

  #-----------------------------------------------------------------------------
  # ITKPythonPackage: This project adds install rules for the "Runtime"
  # component associated with ITK project.

  message(STATUS "SuperBuild - ${PROJECT_NAME} => Requires ITK")

  ExternalProject_add(${PROJECT_NAME}
    SOURCE_DIR ${CMAKE_SOURCE_DIR}
    BINARY_DIR ${CMAKE_BINARY_DIR}/${PROJECT_NAME}-build
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    CMAKE_CACHE_ARGS
      -DITKPythonPackage_SUPERBUILD:BOOL=0
      -DITK_DIR:PATH=${ITK_DIR}
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_INSTALL_PREFIX}
    USES_TERMINAL_CONFIGURE 1
    INSTALL_COMMAND ""
    DEPENDS ITK
    )

  install(SCRIPT ${CMAKE_BINARY_DIR}/${PROJECT_NAME}-build/cmake_install.cmake)

  message(STATUS "SuperBuild - ${PROJECT_NAME}[OK]")

else()
  message(STATUS "Package here")
endif()
