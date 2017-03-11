cmake_minimum_required(VERSION 3.3)

project(ITKPythonPackage NONE)

if(NOT DEFINED ITKPythonPackage_SUPERBUILD)
  set(ITKPythonPackage_SUPERBUILD 1)
endif()

if(ITKPythonPackage_SUPERBUILD)

  set(ep_common_cmake_cache_args)
  if(NOT CMAKE_CONFIGURATION_TYPES)
    list(APPEND ep_common_cmake_cache_args
      -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
      )
  endif()
  #-----------------------------------------------------------------------------
  # Options

  # When building different "flavor" of ITK python packages on a given platform,
  # explicitly setting the following options allow to speed up package generation by
  # re-using existing resources.
  #
  #  ITK_SOURCE_DIR: Path to an existing source directory
  #

  option ( ITKPythonPackage_BUILD_PYTHON "Build ITK python module" ON )
  mark_as_advanced( ITKPythonPackage_BUILD_PYTHON )

  if(CMAKE_OSX_DEPLOYMENT_TARGET)
    list(APPEND ep_common_cmake_cache_args
      -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${CMAKE_OSX_DEPLOYMENT_TARGET})
  endif()
  if(CMAKE_OSX_ARCHITECTURES)
    list(APPEND ep_common_cmake_cache_args
      -DCMAKE_OSX_ARCHITECTURES:STRING=${CMAKE_OSX_ARCHITECTURES})
  endif()

  #-----------------------------------------------------------------------------
  # compile with multiple processors
  include(ProcessorCount)
  ProcessorCount(NPROC)
  if(NOT NPROC EQUAL 0)
    set( ENV{MAKEFLAGS} "-j${NPROC}" )
  endif()

  #-----------------------------------------------------------------------------
  include(ExternalProject)

  set(ITK_REPOSITORY "https://github.com/InsightSoftwareConsortium/ITK.git")
  # ITK nightly-master 2017-03-10
  set(ITK_GIT_TAG "56d722a")

  # Add an empty external project
  function(itk_ExternalProject_Add_Empty proj depends)
    set(depends_args)
    if(NOT depends STREQUAL "")
      set(depends_args DEPENDS ${depends})
    endif()
    ExternalProject_add(${proj}
      SOURCE_DIR ${CMAKE_BINARY_DIR}/${proj}
      DOWNLOAD_COMMAND ""
      UPDATE_COMMAND ""
      CONFIGURE_COMMAND ""
      BUILD_COMMAND ""
      BUILD_IN_SOURCE 1
      BUILD_ALWAYS 1
      INSTALL_COMMAND ""
      ${depends_args}
      )
  endfunction()

  #-----------------------------------------------------------------------------
  # A separate project is used to download ITK, so that it can reused
  # when building different "flavor" of ITK python packages

  message(STATUS "SuperBuild - ITK-source-download")

  # Sanity checks
  if(DEFINED ITK_SOURCE_DIR AND NOT EXISTS ${ITK_SOURCE_DIR})
    message(FATAL_ERROR "ITK_SOURCE_DIR variable is defined but corresponds to nonexistent directory")
  endif()

  if(NOT DEFINED ITK_SOURCE_DIR)

    set(ITK_SOURCE_DIR ${CMAKE_BINARY_DIR}/ITK-source)

    ExternalProject_add(ITK-source-download
      SOURCE_DIR ${ITK_SOURCE_DIR}
      GIT_REPOSITORY ${ITK_REPOSITORY}
      GIT_TAG ${ITK_GIT_TAG}
      USES_TERMINAL_DOWNLOAD 1
      CONFIGURE_COMMAND ""
      BUILD_COMMAND ""
      INSTALL_COMMAND ""
      )

  else()

    itk_ExternalProject_Add_Empty(
      ITK-source-download
      ""
      )

  endif()

  message(STATUS "SuperBuild -   ITK_SOURCE_DIR: ${ITK_SOURCE_DIR}")
  message(STATUS "SuperBuild - ITK-source-download[OK]")

  #-----------------------------------------------------------------------------
  if(NOT ITKPythonPackage_BUILD_PYTHON)
    return()
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

  set(ITK_BINARY_DIR ${CMAKE_BINARY_DIR}/ITK-build)

  message(STATUS "SuperBuild - ITK => Requires ITK-source-download")
  message(STATUS "SuperBuild -   ITK_BINARY_DIR: ${ITK_BINARY_DIR}")

  set(_stamp "${CMAKE_BINARY_DIR}/ITK-prefix/src/ITK-stamp/ITK-configure")
  if(EXISTS ${_stamp})
    execute_process(COMMAND ${CMAKE_COMMAND} -E remove ${_stamp})
    message(STATUS "SuperBuild -   Force re-configure removing ${_stamp}")
  endif()

  ExternalProject_add(ITK
    DOWNLOAD_COMMAND ""
    SOURCE_DIR ${ITK_SOURCE_DIR}
    BINARY_DIR ${ITK_BINARY_DIR}
    CMAKE_CACHE_ARGS
      -DBUILD_TESTING:BOOL=OFF
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_INSTALL_PREFIX}
      -DPY_SITE_PACKAGES_PATH:PATH=${CMAKE_INSTALL_PREFIX}
      -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel
      -DITK_LEGACY_SILENT:BOOL=ON
      -DITK_WRAP_PYTHON:BOOL=ON
      -DITK_WRAP_PYTHON_LEGACY:BOOL=OFF
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR}
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE}
      ${ep_common_cmake_cache_args}
    USES_TERMINAL_DOWNLOAD 1
    USES_TERMINAL_UPDATE 1
    USES_TERMINAL_CONFIGURE 1
    USES_TERMINAL_BUILD 1
    INSTALL_COMMAND ""
    )
  ExternalProject_Add_StepDependencies(ITK download ITK-source-download)

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

  #-----------------------------------------------------------------------------
  # Install ITK "PythonWheelRuntimeLibraries" components
  install(CODE "
unset(CMAKE_INSTALL_COMPONENT)
set(COMPONENT \"PythonWheelRuntimeLibraries\")
include\(\"${ITK_DIR}/cmake_install.cmake\")
unset(CMAKE_INSTALL_COMPONENT)
")

endif()
