#-----------------------------------------------------------------------------
#------------------------------------------------------
#----------------------------------
# ITKPythonPackage_SUPERBUILD: OFF
#----------------------------------
#------------------------------------------------------
#-----------------------------------------------------------------------------
if(NOT DEFINED ITKPythonPackage_WHEEL_NAME)
  message(FATAL_ERROR "ITKPythonPackage_WHEEL_NAME must be defined")
endif()

message(STATUS "SuperBuild - ITKPythonPackage_WHEEL_NAME:${ITKPythonPackage_WHEEL_NAME}")

set(components "PythonWheelRuntimeLibraries")

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
# * Every ITK module is associated with exactly one ITK group.
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
    file(READ ${_module_file} _module_file_content)
    string( REGEX MATCH "itk_module[ \n]*(\\([ \n]*)([A-Za-z0-9]*)" _module_name ${_module_file_content} )
    set(_module_name ${CMAKE_MATCH_2})
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
  if(module STREQUAL "ITKBridgeNumPy")
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

if(MSVC AND ITKPythonPackage_WHEEL_NAME STREQUAL "itk-core")
message(STATUS "Adding install rules for compiler runtime libraries")
# Put the runtime libraries next to the "itk/_*.pyd" C-extensions so they
# are found.
set(CMAKE_INSTALL_SYSTEM_RUNTIME_DESTINATION "itk")
include(InstallRequiredSystemLibraries)
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
include(\"${ITK_BINARY_DIR}/cmake_install.cmake\")
unset(CMAKE_INSTALL_COMPONENT)
")
endforeach()
