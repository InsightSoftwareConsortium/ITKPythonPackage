# Define below a reasonable dependency graph for ITK groups
set(ITK_GROUP_Core_DEPENDS)
set(ITK_GROUP_IO_DEPENDS Numerics)
set(ITK_GROUP_Numerics_DEPENDS Core)
set(ITK_GROUP_Filtering_DEPENDS Numerics)
set(ITK_GROUP_Segmentation_DEPENDS Filtering)
set(ITK_GROUP_Registration_DEPENDS Filtering)
set(ITK_GROUP_Video_DEPENDS Core)

# Modules packaged in a wheel other than the one their group and dependees
# select.
set(ITK_WHEEL_Core_MODULE_OVERRIDES ITKBridgeNumPy ITKVTK)
