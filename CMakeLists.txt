cmake_minimum_required(VERSION 3.3)

project(ITKPythonPackage NONE)

set(CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake ${CMAKE_MODULE_PATH})
include(ITKPythonPackage)

if(NOT DEFINED ITKPythonPackage_SUPERBUILD)
  set(ITKPythonPackage_SUPERBUILD 1)
endif()

if(ITKPythonPackage_SUPERBUILD)

  #-----------------------------------------------------------------------------
  #------------------------------------------------------
  #----------------------------------
  # ITKPythonPackage_SUPERBUILD: ON
  #----------------------------------
  #------------------------------------------------------
  #-----------------------------------------------------------------------------

  # Avoid "Manually-specified variables were not used by the project" warnings.
  ipp_unused_vars(${PYTHON_VERSION_STRING} ${SKBUILD})

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

  if(CMAKE_MAKE_PROGRAM)
    list(APPEND ep_common_cmake_cache_args
      -DCMAKE_MAKE_PROGRAM:FILEPATH=${CMAKE_MAKE_PROGRAM})
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
  # ITK nightly-master 2017-06-13
  set(ITK_GIT_TAG "c5c879a")

  #-----------------------------------------------------------------------------
  # A separate project is used to download ITK, so that it can reused
  # when building different "flavor" of ITK python packages

  message(STATUS "SuperBuild -")
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
    set(proj_status "")

  else()

    ipp_ExternalProject_Add_Empty(
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

  option(ITKPythonPackage_ITK_BINARY_REUSE "Reuse provided ITK_BINARY_DIR without configuring or building ITK" OFF)

  set(ITK_BINARY_DIR "${CMAKE_BINARY_DIR}/ITK-build" CACHE PATH "ITK build directory")

  message(STATUS "SuperBuild -")
  message(STATUS "SuperBuild - ITK => Requires ITK-source-download")
  message(STATUS "SuperBuild -   ITK_BINARY_DIR: ${ITK_BINARY_DIR}")

  if(NOT ITKPythonPackage_ITK_BINARY_REUSE)

    set(_stamp "${CMAKE_BINARY_DIR}/ITK-prefix/src/ITK-stamp/ITK-configure")
    if(EXISTS ${_stamp})
      execute_process(COMMAND ${CMAKE_COMMAND} -E remove ${_stamp})
      message(STATUS "SuperBuild -   Force re-configure removing ${_stamp}")
    endif()

    set(install_component_per_module OFF)
    if(NOT ITKPythonPackage_WHEEL_NAME STREQUAL "itk")
      set(install_component_per_module ON)
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
        -DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=${install_component_per_module}
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
    set(proj_status "")

  else()

    # Sanity checks
    if(NOT EXISTS "${ITK_BINARY_DIR}/CMakeCache.txt")
      message(FATAL_ERROR "ITKPythonPackage_ITK_BINARY_REUSE is ON but ITK_BINARY_DIR variable is not associated with an ITK build directory. [ITK_BINARY_DIR:${ITK_BINARY_DIR}]")
    endif()

    ipp_ExternalProject_Add_Empty(
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

  if(NOT DEFINED ITKPythonPackage_WHEEL_NAME)
    set(ITKPythonPackage_WHEEL_NAME "itk")
  endif()
  message(STATUS "SuperBuild -   ITKPythonPackage_WHEEL_NAME:${ITKPythonPackage_WHEEL_NAME}")

  ExternalProject_add(${PROJECT_NAME}
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
      ${ep_common_cmake_cache_args}
    USES_TERMINAL_CONFIGURE 1
    INSTALL_COMMAND ""
    DEPENDS ITK
    )

  install(SCRIPT ${CMAKE_BINARY_DIR}/${PROJECT_NAME}-build/cmake_install.cmake)

  message(STATUS "SuperBuild - ${PROJECT_NAME}[OK]")

else()

  #-----------------------------------------------------------------------------
  #------------------------------------------------------
  #----------------------------------
  # ITKPythonPackage_SUPERBUILD: OFF
  #----------------------------------
  #------------------------------------------------------
  #-----------------------------------------------------------------------------

  set(components "PythonWheelRuntimeLibraries")
  if(NOT ITKPythonPackage_WHEEL_NAME STREQUAL "itk")

    message(STATUS "ITKPythonPackage_WHEEL_NAME: ${ITKPythonPackage_WHEEL_NAME}")

    # Extract ITK group name from wheel name
    message(STATUS "")
    set(msg "Extracting ITK_WHEEL_GROUP")
    message(STATUS ${msg})
    ipp_wheel_to_group(${ITKPythonPackage_WHEEL_NAME} ITK_WHEEL_GROUP)
    message(STATUS "${msg} - done [${ITK_WHEEL_GROUP}]")

    #
    # Considering that
    #
    # * Every ITK module is associated with exactly on ITK group.
    # * ITK module dependencies are specified independently of ITK groups
    #
    # we semi-arbitrarily defined a collection of wheels (see ``ITK_WHEEL_GROUPS``)
    # that will roughly bundle the modules associated with each group.
    #
    # Based on the module dependency graph, the code below will determine which module
    # should be packaged in which wheel.
    #

    # List of ITK wheel groups
    set(ITK_WHEEL_GROUPS "")
    file(STRINGS "${CMAKE_SOURCE_DIR}/scripts/WHEEL_NAMES.txt" ITK_WHEELS  REGEX "^itk-.+")
    foreach(wheel_name IN LISTS ITK_WHEELS)
      ipp_wheel_to_group(${wheel_name} group)
      list(APPEND ITK_WHEEL_GROUPS ${group})
    endforeach()

    # Define below a reasonable dependency graph for ITK groups
    set(ITK_GROUP_Core_DEPENDS)
    set(ITK_GROUP_IO_DEPENDS Core)
    set(ITK_GROUP_Numerics_DEPENDS Core)
    set(ITK_GROUP_Filtering_DEPENDS Numerics)
    set(ITK_GROUP_Segmentation_DEPENDS Filtering)
    set(ITK_GROUP_Registration_DEPENDS Filtering)
    set(ITK_GROUP_Video_DEPENDS Core)

    # ITK is needed to retrieve ITK module information
    set(ITK_DIR ${ITK_BINARY_DIR})
    find_package(ITK REQUIRED)
    set(CMAKE_MODULE_PATH ${ITK_CMAKE_DIR} ${CMAKE_MODULE_PATH})

    # Sort wheel groups
    include(TopologicalSort)
    topological_sort(ITK_WHEEL_GROUPS ITK_GROUP_ _DEPENDS)

    # Set ``ITK_MODULE_<modulename>_DEPENDS`` variables
    #
    # Notes:
    #
    #  * ``<modulename>_DEPENDS`` variables are set after calling ``find_package(ITK REQUIRED)``
    #
    #  * This naming convention corresponds to what is used internally in ITK and allow
    #    to differentiate with variable like ``ITK_GROUP_<groupname>_DEPENDS`` set above.
    #
    foreach(module IN LISTS ITK_MODULES_ENABLED)
      set(ITK_MODULE_${module}_DEPENDS "${${module}_DEPENDS}")
    endforeach()

    # Set ``ITK_MODULE_<modulename>_DEPENDEES`` variables
    foreach(module IN LISTS ITK_MODULES_ENABLED)
      ipp_get_module_dependees(${module} ITK_MODULE_${module}_DEPENDEES)
    endforeach()

    # Set ``ITK_GROUPS`` variable
    file(GLOB group_dirs "${ITK_SOURCE_DIR}/Modules/*")
    set(ITK_GROUPS )
    foreach(dir IN LISTS group_dirs)
      file(RELATIVE_PATH group "${ITK_SOURCE_DIR}/Modules" "${dir}")
      if(NOT IS_DIRECTORY "${dir}" OR "${group}" MATCHES "^External$")
        continue()
      endif()
      list(APPEND ITK_GROUPS ${group})
    endforeach()
    message(STATUS "")
    message(STATUS "ITK_GROUPS:${ITK_GROUPS}")

    # Set ``ITK_MODULE_<modulename>_GROUP`` variables
    foreach(group IN LISTS ITK_GROUPS)
      file( GLOB_RECURSE _${group}_module_files ${ITK_SOURCE_DIR}/Modules/${group}/itk-module.cmake )
      foreach( _module_file ${_${group}_module_files} )
        file( STRINGS ${_module_file} _module_line REGEX "itk_module[ \n]*\\([ \n]*[A-Za-z0-9]*" )
        string( REGEX MATCH "(\\([ \n]*)([A-Za-z0-9]*)" _module_name ${_module_line} )
        set( _module_name ${CMAKE_MATCH_2} )
        set( _${_module_name}_module_line ${_module_line} )
        list( APPEND _${group}_module_list ${_module_name} )
        set(ITK_MODULE_${_module_name}_GROUP ${group})
      endforeach()
    endforeach()

    # Initialize ``ITK_WHEEL_<wheelgroup>_MODULES`` variables that will contain list of modules
    # to package in each wheel.
    foreach(group IN LISTS ITK_WHEEL_GROUPS)
      set(ITK_WHEEL_${group}_MODULES "")
    endforeach()

    # Configure table display
    set(row_widths 40 20 20 10 90 12)
    set(row_headers MODULE_NAME MODULE_GROUP WHEEL_GROUP IS_LEAF MODULE_DEPENDEES_GROUPS IS_WRAPPED)
    message(STATUS "")
    ipp_display_table_row("${row_headers}" "${row_widths}")

    # Update ``ITK_WHEEL_<wheelgroup>_MODULES`` variables
    foreach(module IN LISTS ITK_MODULES_ENABLED)

      ipp_is_module_leaf(${module} leaf)
      set(dependees_groups)
      if(NOT leaf)
        set(dependees "")
        ipp_recursive_module_dependees(${module} dependees)
        foreach(dep IN LISTS dependees)
          list(APPEND dependees_groups ${ITK_MODULE_${dep}_GROUP})
        endforeach()
        if(dependees_groups)
          list(REMOVE_DUPLICATES dependees_groups)
        endif()
      endif()

      # Filter out group not associated with a wheel
      set(dependees_wheel_groups)
      foreach(group IN LISTS dependees_groups)
        list(FIND ITK_WHEEL_GROUPS ${group} _index)
        if(_index EQUAL -1)
          continue()
        endif()
        list(APPEND dependees_wheel_groups ${group})
      endforeach()

      set(wheel_group)
      list(LENGTH dependees_wheel_groups _length)

      # Sanity check
      if(leaf AND _length GREATER 0)
        message(FATAL_ERROR "leaf module should not module depending on them !")
      endif()

      if(_length EQUAL 0)
        set(wheel_group "${ITK_MODULE_${module}_GROUP}")
      elseif(_length EQUAL 1)
        # Since packages depending on this module belong to one group, also package this module
        set(wheel_group "${dependees_wheel_groups}")
      elseif(_length GREATER 1)
        # If more than one group is associated with the dependees, package the module in the
        # "common ancestor" group.
        set(common_ancestor_index 999999)
        foreach(g IN LISTS dependees_wheel_groups)
          list(FIND ITK_WHEEL_GROUPS ${g} _index)
          if(NOT _index EQUAL -1 AND _index LESS common_ancestor_index)
            set(common_ancestor_index ${_index})
          endif()
        endforeach()
        list(GET ITK_WHEEL_GROUPS ${common_ancestor_index} wheel_group)
      endif()

      set(wheel_group_display ${wheel_group})

      # XXX Hard-coded dispatch
      if(module STREQUAL "BridgeNumPy")
        set(new_wheel_group "Core")
        set(wheel_group_display "${new_wheel_group} (was ${wheel_group})")
        set(wheel_group ${new_wheel_group})
      endif()
      if(module STREQUAL "ITKVTK")
        set(new_wheel_group "Core")
        set(wheel_group_display "${new_wheel_group} (was ${wheel_group})")
        set(wheel_group ${new_wheel_group})
      endif()

      # Associate module with a wheel
      list(APPEND ITK_WHEEL_${wheel_group}_MODULES ${module})

      # Display module info
      ipp_is_module_python_wrapped(${module} is_wrapped)
      ipp_list_to_string("^^" "${dependees_groups}" dependees_groups_str)
      set(row_values "${module};${ITK_MODULE_${module}_GROUP};${wheel_group_display};${leaf};${dependees_groups_str};${is_wrapped}")
      ipp_display_table_row("${row_values}" "${row_widths}")

    endforeach()

    # Set list of components to install
    set(components "")
    foreach(module IN LISTS ITK_WHEEL_${ITK_WHEEL_GROUP}_MODULES)
      list(APPEND components ${module}PythonWheelRuntimeLibraries)
    endforeach()

  endif()

  #-----------------------------------------------------------------------------
  # Install ITK components
  message(STATUS "Adding install rules for components:")
  foreach(component IN LISTS components)
    message(STATUS "  ${component}")
    install(CODE "
unset(CMAKE_INSTALL_COMPONENT)
set(COMPONENT \"${component}\")
set(CMAKE_INSTALL_DO_STRIP 1)
include\(\"${ITK_BINARY_DIR}/cmake_install.cmake\")
unset(CMAKE_INSTALL_COMPONENT)
")
  endforeach()

endif()
