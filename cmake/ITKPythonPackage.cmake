

# Add an empty external project
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
