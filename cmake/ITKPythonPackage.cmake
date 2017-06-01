
# ipp_ExternalProject_Add_Empty(<proj> <depends>)
#
# Add an empty external project
#
function(ipp_ExternalProject_Add_Empty proj depends)
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

# ipp_set_itk_groups()
#
# Set ``ITK_MODULE_*_GROUP`` variable for each modules.
#
macro(ipp_set_itk_groups)
  include("${}")
  foreach( group ${group_list} )
    set( _${group}_module_list )
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
endmacro()

# ipp_get_module_dependees(<itk-module> <output_var>)
#
# Collect all modules depending on ``<itk-module>``.
#
function(ipp_get_module_dependees itk-module output_var)
  set(dependees "")
  foreach(m_enabled IN LISTS ITK_MODULES_ENABLED)
    list(FIND ITK_MODULE_${m_enabled}_DEPENDS ${itk-module} _index)
    if(NOT _index EQUAL -1)
      list(APPEND dependees ${m_enabled})
    endif()
  endforeach()
  list(REMOVE_DUPLICATES dependees)
  set(${output_var} ${dependees} PARENT_SCOPE)
endfunction()

function(_recursive_deps item-type item-category itk-item output_var)
  set(_${itk-item}_deps )
  foreach(dep IN LISTS ITK_${item-type}_${itk-item}_${item-category})
    list(APPEND _${itk-item}_deps ${dep})
    _recursive_deps(${item-type} ${item-category} ${dep} _${itk-item}_deps)
  endforeach()
  list(APPEND ${output_var} ${_${itk-item}_deps})
  list(REMOVE_DUPLICATES ${output_var})
  set(${output_var} ${${output_var}} PARENT_SCOPE)
endfunction()

# ipp_recursive_module_dependees(<itk-module> <output_var>)
#
# Recursively collect all modules depending on ``<itk-module>``.
#
function(ipp_recursive_module_dependees itk-module output_var)
  set(_${itk-module}_deps )
  _recursive_deps("MODULE" "DEPENDEES" ${itk-module} ${output_var})
  set(${output_var} ${${output_var}} PARENT_SCOPE)
endfunction()

# ipp_is_module_leaf(<itk-module> <output_var>)
#
# If ``<itk-module>`` has no dependencies, set ``<output_var> to 1
# otherwise set ``<output_var> to 0.
#
function(ipp_is_module_leaf itk-module output_var)
  set(leaf 1)
  foreach(m_enabled IN LISTS ITK_MODULES_ENABLED)
    list(FIND ITK_MODULE_${m_enabled}_DEPENDS ${itk-module} _index)
    if(NOT _index EQUAL -1)
      set(leaf 0)
      break()
    endif()
  endforeach()
  set(${output_var} ${leaf} PARENT_SCOPE)
endfunction()

# ipp_is_module_python_wrapped(<itk-module> <output_var>)
#
# If ``<itk-module>`` is wrapped in python, set ``<output_var> to 1
# otherwise set ``<output_var> to 0.
#
function(ipp_is_module_python_wrapped itk-module output_var)
  set(wrapped 0)
  if(NOT DEFINED ITK_MODULE_${itk-module}_GROUP)
    message(AUTHOR_WARNING "Variable ITK_MODULE_${itk-module}_GROUP is not defined")
  else()
    set(group ${ITK_MODULE_${itk-module}_GROUP})
    set(module_folder ${itk-module})
    # if any, strip ITK prefix
    if(module_folder MATCHES "^ITK.+$")
      string(REGEX REPLACE "^ITK(.+)$" "\\1" module_folder ${module_folder})
    endif()
    if(EXISTS ${ITK_SOURCE_DIR}/Modules/${group}/${itk-module}/wrapping/CMakeLists.txt
        OR EXISTS ${ITK_SOURCE_DIR}/Modules/${group}/${module_folder}/wrapping/CMakeLists.txt)
      set(wrapped 1)
    endif()
  endif()
  set(${output_var} ${wrapped} PARENT_SCOPE)
endfunction()

# ipp_wheel_to_group(<wheel_name> <group_name_var>)
#
# Extract ITK group name from wheel name (e.g 'itk-core' -> 'Core').
#
# If the group name has less than 3 characters, take the uppercase
# value (e.g 'itk-io' -> 'IO').
#
function(ipp_wheel_to_group wheel_name group_name_var)
  string(REPLACE "itk-" "" _group ${wheel_name})
  string(SUBSTRING ${_group} 0 1 _first)
  string(TOUPPER ${_first} _first_uc)
  string(SUBSTRING ${_group} 1 -1 _remaining)
  set(group_name "${_first_uc}${_remaining}")
  # Convert to upper case if length <= 2
  string(LENGTH ${group_name} _length)
  if(_length LESS 3)
    string(TOUPPER ${group_name} group_name)
  endif()
  set(${group_name_var} ${group_name} PARENT_SCOPE)
endfunction()

# ipp_pad_text(<text> <text_right_jusitfy_length> <output_var>)
#
# Example:
#
#   set(row "Apple")
#   ipp_pad_text(${row} 20 row)
#
#   set(row "${row}Banana")
#   ipp_pad_text(${row} 40 row)
#
#   set(row "${row}Kiwi")
#   ipp_pad_text(${row} 60 row)
#
#   message(${row})
#
# Output:
#
#   Apple               Banana              Kiwi
#
function(ipp_pad_text text text_right_jusitfy_length output_var)
  set(fill_char " ")
  string(LENGTH "${text}" text_length)
  math(EXPR pad_length "${text_right_jusitfy_length} - ${text_length} - 1")
  if(pad_length GREATER 0)
    string(RANDOM LENGTH ${pad_length} ALPHABET ${fill_char} text_dots)
    set(${output_var} "${text} ${text_dots}" PARENT_SCOPE)
  else()
    set(${output_var} "${text}" PARENT_SCOPE)
  endif()
endfunction()

# ipp_display_table_row(<values> <widths>)
#
# Example:
#
#   ipp_display_table_row("Apple^^Banana^^Kiwi" "20;20;20")
#   ipp_display_table_row("Eiger^^Rainer^^Sajama" "20;20;20")
#
# Output:
#
#   Apple               Banana              Kiwi
#   Eiger               Rainer              Sajama
#
function(ipp_display_table_row values widths)
  list(LENGTH values length)
  set(text "")
  math(EXPR range "${length} - 1")
  foreach(index RANGE ${range})
    list(GET widths ${index} width)
    list(GET values ${index} value)
    string(REPLACE "^^" ";" value "${value}")
    ipp_pad_text("${value}" ${width} value)
    set(text "${text}${value}")
  endforeach()
  message(STATUS "${text}")
endfunction()

# ipp_list_to_string(<separator> <input_list> <output_string_var>)
#
# Example:
#
#   set(values Foo Bar Oof)
#   message("${values}")
#   ipp_list_to_string("^^" "${values}" values)
#   message("${values}")
#
# Output:
#
#   Foo;Bar;Oof
#   Foo^^Bar^^Oof
#
# Copied from Slicer/CMake/ListToString.cmake
#
function(ipp_list_to_string separator input_list output_string_var)
  set(_string "")
  # Get list length
  list(LENGTH input_list list_length)
  # If the list has 0 or 1 element, there is no need to loop over.
  if(list_length LESS 2)
    set(_string  "${input_list}")
  else()
    math(EXPR last_element_index "${list_length} - 1")
    foreach(index RANGE ${last_element_index})
      # Get current item_value
      list(GET input_list ${index} item_value)
      if(NOT item_value STREQUAL "")
        # .. and append non-empty value to output string
        set(_string  "${_string}${item_value}")
        # Append separator if current element is NOT the last one.
        if(NOT index EQUAL last_element_index)
          set(_string  "${_string}${separator}")
        endif()
      endif()
    endforeach()
  endif()
  set(${output_string_var} ${_string} PARENT_SCOPE)
endfunction()

# No-op function allowing to shut-up "Manually-specified variables were not used by the project"
# warnings.
function(ipp_unused_vars)
endfunction()

#
# Unused
#

function(recursive_module_deps itk-module output_var)
  set(_${itk-module}_deps )
  _recursive_deps("MODULE" "DEPENDS" ${itk-module} ${output_var})
  set(${output_var} ${${output_var}} PARENT_SCOPE)
endfunction()

function(recursive_group_deps itk-group output_var)
  set(_${itk-group}_deps )
  _recursive_deps("GROUP" "DEPENDS" ${itk-group} ${output_var})
  set(${output_var} ${${output_var}} PARENT_SCOPE)
endfunction()
