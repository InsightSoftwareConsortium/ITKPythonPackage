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
# reusing existing resources.
#
#  ITK_SOURCE_DIR: Path to an existing source directory
#

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
elseif(NOT "$ENV{CXX}" STREQUAL "")
    list(APPEND ep_common_cmake_cache_args -DCMAKE_CXX_COMPILER:PATH=$ENV{CXX})
endif()

if(CMAKE_C_COMPILER)
    list(
        APPEND ep_common_cmake_cache_args
        -DCMAKE_C_COMPILER:PATH=${CMAKE_C_COMPILER}
    )
elseif(NOT "$ENV{CC}" STREQUAL "")
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

if(NOT ITK_SOURCE_DIR AND NOT "$ENV{ITK_SOURCE_DIR}" STREQUAL "")
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
