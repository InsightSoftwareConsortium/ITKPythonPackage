#-----------------------------------------------------------------------------
#------------------------------------------------------
#----------------------------------
# ITKPythonPackage_SUPERBUILD: ON
#----------------------------------
#------------------------------------------------------
#-----------------------------------------------------------------------------

option(
    ITKPythonPackage_USE_TBB
    "Build and use oneTBB in the ITK python package"
    ON
)

# Avoid "Manually-specified variables were not used by the project" warnings.
ipp_unused_vars(${PYTHON_VERSION_STRING} ${SKBUILD})

set(ep_download_extract_timestamp_arg)
if(CMAKE_VERSION VERSION_EQUAL "3.24" OR CMAKE_VERSION VERSION_GREATER "3.24")
    # See https://cmake.org/cmake/help/latest/policy/CMP0135.html
    set(ep_download_extract_timestamp_arg DOWNLOAD_EXTRACT_TIMESTAMP 1)
endif()

#-----------------------------------------------------------------------------
# Options

# When building different "flavor" of ITK python packages on a given platform,
# explicitly setting the following options allow to speed up package generation by
# re-using existing resources.
#
#  ITK_SOURCE_DIR: Path to an existing source directory
#

option(ITKPythonPackage_BUILD_PYTHON "Build ITK python module" ON)
mark_as_advanced(ITKPythonPackage_BUILD_PYTHON)

set(ep_common_cmake_cache_args)
if(NOT CMAKE_CONFIGURATION_TYPES)
    if(NOT CMAKE_BUILD_TYPE)
        set(CMAKE_BUILD_TYPE "Release")
    endif()
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
    )
endif()

if(CMAKE_OSX_DEPLOYMENT_TARGET)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=${CMAKE_OSX_DEPLOYMENT_TARGET}
    )
endif()
if(CMAKE_OSX_ARCHITECTURES)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_OSX_ARCHITECTURES:STRING=${CMAKE_OSX_ARCHITECTURES}
    )
endif()

if(CMAKE_MAKE_PROGRAM)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_MAKE_PROGRAM:FILEPATH=${CMAKE_MAKE_PROGRAM}
    )
endif()

if(CMAKE_CXX_COMPILER)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_CXX_COMPILER:PATH=${CMAKE_CXX_COMPILER}
    )
elseif(ENV{CXX})
    list(APPEND ep_common_cmake_cache_args -DCMAKE_CXX_COMPILER:PATH=$ENV{CXX})
endif()

if(CMAKE_C_COMPILER)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_C_COMPILER:PATH=${CMAKE_C_COMPILER}
    )
elseif(ENV{CC})
    list(APPEND ep_common_cmake_cache_args -DCMAKE_C_COMPILER:PATH=$ENV{CC})
endif()

#-----------------------------------------------------------------------------
# compile with multiple processors
include(ProcessorCount)
ProcessorCount(NPROC)
if(NOT NPROC EQUAL 0)
    set(ENV{MAKEFLAGS} "-j${NPROC}")
endif()

#-----------------------------------------------------------------------------
include(ExternalProject)

#-----------------------------------------------------------------------------
# A separate project is used to download ITK, so that it can reused
# when building different "flavor" of ITK python packages

message(STATUS "SuperBuild -")
message(STATUS "SuperBuild - ITK-source-download")

if(NOT ITK_SOURCE_DIR AND ENV{ITK_SOURCE_DIR})
    set(ITK_SOURCE_DIR "$ENV{ITK_SOURCE_DIR}")
endif()

set(tbb_depends "")
set(tbb_args -DModule_ITKTBB:BOOL=OFF)
if(ITKPythonPackage_USE_TBB)
    set(TBB_INSTALL_PREFIX "${CMAKE_BINARY_DIR}/../oneTBB-prefix")
    set(TBB_DIR "${TBB_INSTALL_PREFIX}/lib/cmake/TBB")
    set(tbb_args -DModule_ITKTBB:BOOL=ON -DTBB_DIR:PATH=${TBB_DIR})

    set(tbb_cmake_cache_args)
    if(CMAKE_OSX_DEPLOYMENT_TARGET)
        list(
            APPEND tbb_cmake_cache_args
            -DCMAKE_CXX_OSX_DEPLOYMENT_TARGET_FLAG:STRING="-mmacosx-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET}"
            -DCMAKE_C_OSX_DEPLOYMENT_TARGET_FLAG:STRING="-mmacosx-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET}"
        )
    endif()

    ExternalProject_Add(
        oneTBB
        URL
            https://github.com/oneapi-src/oneTBB/archive/refs/tags/v2022.2.0.tar.gz
        URL_HASH
            SHA256=f0f78001c8c8edb4bddc3d4c5ee7428d56ae313254158ad1eec49eced57f6a5b
        CMAKE_ARGS
            -DTBB_TEST:BOOL=OFF
            -DCMAKE_INSTALL_PREFIX:PATH=${TBB_INSTALL_PREFIX}
            -DCMAKE_INSTALL_LIBDIR:STRING=lib # Skip default initialization by GNUInstallDirs CMake module
            ${ep_common_cmake_cache_args} ${tbb_cmake_cache_args}
            ${ep_download_extract_timestamp_arg}
        BUILD_BYPRODUCTS "${TBB_DIR}/TBBConfig.cmake"
        USES_TERMINAL_DOWNLOAD 1
        USES_TERMINAL_UPDATE 1
        USES_TERMINAL_CONFIGURE 1
        USES_TERMINAL_BUILD 1
    )
    message(STATUS "SuperBuild -   TBB: Enabled")
    message(STATUS "SuperBuild -   TBB_DIR: ${TBB_DIR}")
    set(tbb_depends oneTBB)
endif()

# Only add ITK-source-download ExternalProject if directory does not
# already exist
if(NOT EXISTS ${ITK_SOURCE_DIR})
    set(ITK_REPOSITORY "https://github.com/InsightSoftwareConsortium/ITK.git")

    if(NOT DEFINED ITK_GIT_TAG AND DEFINED ENV{ITK_GIT_TAG})
        set(ITK_GIT_TAG "$ENV{ITK_GIT_TAG}")
    endif()

    if(NOT DEFINED ITK_GIT_TAG)
        message(
            FATAL_ERROR
            "ITK_GIT_TAG must be defined when configuring cmake"
        )
    endif()
    ExternalProject_Add(
        ITK-source-download
        SOURCE_DIR ${ITK_SOURCE_DIR}
        GIT_REPOSITORY ${ITK_REPOSITORY}
        GIT_TAG ${ITK_GIT_TAG}
        USES_TERMINAL_DOWNLOAD 1
        CONFIGURE_COMMAND ""
        BUILD_COMMAND ""
        INSTALL_COMMAND ""
        DEPENDS "${tbb_depends}"
    )
    set(proj_status "")
else()
    # Suppress unused variable warning
    set(_unused "${ITK_GIT_TAG}")
    ipp_externalproject_add_empty(
      ITK-source-download
      ""
    )
    set(proj_status " (REUSE)")
endif()

message(STATUS "SuperBuild -   ITK_SOURCE_DIR: ${ITK_SOURCE_DIR}")
message(STATUS "SuperBuild - ITK-source-download[OK]${proj_status}")

#-----------------------------------------------------------------------------
if(NOT ITKPythonPackage_BUILD_PYTHON)
    return()
endif()

#-----------------------------------------------------------------------------
# Search for python interpreter and libraries

message(STATUS "SuperBuild -")
message(STATUS "SuperBuild - Searching for python")

# Sanity checks
if(DEFINED Python3_INCLUDE_DIR AND NOT EXISTS ${Python3_INCLUDE_DIR})
    message(
        FATAL_ERROR
        "Python3_INCLUDE_DIR=${Python3_INCLUDE_DIR}: variable is defined but corresponds to nonexistent directory"
    )
endif()
if(DEFINED Python3_LIBRARY AND NOT EXISTS ${Python3_LIBRARY})
    message(
        FATAL_ERROR
        "Python3_LIBRARY=${Python3_LIBRARY}: variable is defined but corresponds to nonexistent file"
    )
endif()
if(DEFINED Python3_EXECUTABLE AND NOT EXISTS ${Python3_EXECUTABLE})
    message(
        FATAL_ERROR
        "Python3_EXECUTABLE=${Python3_EXECUTABLE}: variable is defined but corresponds to nonexistent file"
    )
endif()
if(DEFINED DOXYGEN_EXECUTABLE AND NOT EXISTS ${DOXYGEN_EXECUTABLE})
    message(
        FATAL_ERROR
        "DOXYGEN_EXECUTABLE=${DOXYGEN_EXECUTABLE}: variable is defined but corresponds to nonexistent file"
    )
endif()

if(
    NOT DEFINED Python3_INCLUDE_DIR
    OR NOT DEFINED Python3_LIBRARY
    OR NOT DEFINED Python3_EXECUTABLE
)
    find_package(Python3 COMPONENTS Interpreter Development)
    if(NOT Python3_EXECUTABLE AND _Python3_EXECUTABLE)
        set(Python3_EXECUTABLE
            ${_Python3_EXECUTABLE}
            CACHE INTERNAL
            "Path to the Python interpreter"
            FORCE
        )
    endif()
endif()
if(NOT DEFINED DOXYGEN_EXECUTABLE)
    find_package(Doxygen REQUIRED)
endif()

message(STATUS "SuperBuild -   Python3_INCLUDE_DIR: ${Python3_INCLUDE_DIR}")
message(STATUS "SuperBuild -   Python3_INCLUDE_DIRS: ${Python3_INCLUDE_DIRS}")
message(STATUS "SuperBuild -   Python3_LIBRARY: ${Python3_LIBRARY}")
message(STATUS "SuperBuild -   Python3_EXECUTABLE: ${Python3_EXECUTABLE}")
message(STATUS "SuperBuild - Searching for python[OK]")
message(STATUS "SuperBuild -   DOXYGEN_EXECUTABLE: ${DOXYGEN_EXECUTABLE}")

# CMake configuration variables to pass to ITK's build
set(ep_itk_cmake_cache_args "")
foreach(var BUILD_SHARED_LIBS ITK_BUILD_DEFAULT_MODULES)
    if(DEFINED ${var})
        list(APPEND ep_itk_cmake_cache_args "-D${var}=${${var}}")
    endif()
endforeach()
function(cached_variables RESULTVAR PATTERN)
    get_cmake_property(variables CACHE_VARIABLES)
    set(result)
    foreach(variable ${variables})
        if(${variable} AND variable MATCHES "${PATTERN}")
            list(APPEND result "-D${variable}=${${variable}}")
        endif()
    endforeach()
    set(${RESULTVAR} ${result} PARENT_SCOPE)
endfunction()
cached_variables(itk_pattern_cached_vars "^(ITK_WRAP_)|(ITKGroup_)|(Module_)")
list(APPEND ep_itk_cmake_cache_args ${itk_pattern_cached_vars})
# Todo, also pass all Module_* variables
message(STATUS "ITK CMake Cache Args -   ${ep_itk_cmake_cache_args}")
#-----------------------------------------------------------------------------
# ITK: This project builds ITK and associated Python modules

option(
    ITKPythonPackage_ITK_BINARY_REUSE
    "Reuse provided ITK_BINARY_DIR without configuring or building ITK"
    OFF
)

set(ITK_BINARY_DIR "${CMAKE_BINARY_DIR}/ITKb" CACHE PATH "ITK build directory")

message(STATUS "SuperBuild -")
message(STATUS "SuperBuild - ITK => Requires ITK-source-download")
message(STATUS "SuperBuild -   ITK_BINARY_DIR: ${ITK_BINARY_DIR}")

if(NOT ITKPythonPackage_ITK_BINARY_REUSE)
    set(_stamp "${CMAKE_BINARY_DIR}/ITK-prefix/src/ITK-stamp/ITK-configure")
    if(EXISTS ${_stamp})
        execute_process(COMMAND ${CMAKE_COMMAND} -E remove ${_stamp})
        message(STATUS "SuperBuild -   Force re-configure removing ${_stamp}")
    endif()

    ExternalProject_Add(
        ITK
        DOWNLOAD_COMMAND ""
        SOURCE_DIR ${ITK_SOURCE_DIR}
        BINARY_DIR ${ITK_BINARY_DIR}
        PREFIX "ITKp"
        CMAKE_ARGS
            -DBUILD_TESTING:BOOL=OFF
            -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_INSTALL_PREFIX}
            -DPY_SITE_PACKAGES_PATH:PATH=${CMAKE_INSTALL_PREFIX}
            -DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel
            -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON
            -DITK_LEGACY_SILENT:BOOL=ON -DITK_WRAP_PYTHON:BOOL=ON
            -DDOXYGEN_EXECUTABLE:FILEPATH=${DOXYGEN_EXECUTABLE}
            -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR}
            -DPython3_LIBRARY:FILEPATH=${Python3_LIBRARY}
            -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE}
            ${ep_common_cmake_cache_args} ${tbb_args} ${ep_itk_cmake_cache_args}
            ${ep_download_extract_timestamp_arg}
        USES_TERMINAL_DOWNLOAD 1
        USES_TERMINAL_UPDATE 1
        USES_TERMINAL_CONFIGURE 1
        USES_TERMINAL_BUILD 1
        INSTALL_COMMAND ""
    )
    set(proj_status "")
else()
    # Sanity checks
    if(NOT EXISTS "${ITK_BINARY_DIR}/CMakeCache.txt")
        message(
            FATAL_ERROR
            "ITKPythonPackage_ITK_BINARY_REUSE is ON but ITK_BINARY_DIR variable is not associated with an ITK build directory. [ITK_BINARY_DIR:${ITK_BINARY_DIR}]"
        )
    endif()

    ipp_externalproject_add_empty(
      ITK
      ""
    )
    set(proj_status " (REUSE)")
endif()
ExternalProject_Add_StepDependencies(ITK download ITK-source-download)

message(STATUS "SuperBuild - ITK[OK]${proj_status}")

#-----------------------------------------------------------------------------
# ITKPythonPackage: This project adds install rules for the "RuntimeLibraries"
# components associated with the ITK project.

message(STATUS "SuperBuild -")
message(STATUS "SuperBuild - ${PROJECT_NAME} => Requires ITK")

ExternalProject_Add(
    ${PROJECT_NAME}
    SOURCE_DIR ${CMAKE_SOURCE_DIR}
    BINARY_DIR ${CMAKE_BINARY_DIR}/${PROJECT_NAME}-build
    DOWNLOAD_COMMAND ""
    UPDATE_COMMAND ""
    CMAKE_CACHE_ARGS
        -DITKPythonPackage_SUPERBUILD:BOOL=0
        -DITK_BINARY_DIR:PATH=${ITK_BINARY_DIR}
        -DITK_SOURCE_DIR:PATH=${ITK_SOURCE_DIR}
        -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_INSTALL_PREFIX}
        -DITKPythonPackage_WHEEL_NAME:STRING=${ITKPythonPackage_WHEEL_NAME}
        -DITKPythonPackage_USE_TBB:BOOL=${ITKPythonPackage_USE_TBB}
        ${ep_common_cmake_cache_args}
    USES_TERMINAL_CONFIGURE 1
    INSTALL_COMMAND ""
    DEPENDS ITK
)

install(SCRIPT ${CMAKE_BINARY_DIR}/${PROJECT_NAME}-build/cmake_install.cmake)

message(STATUS "SuperBuild - ${PROJECT_NAME}[OK]")
