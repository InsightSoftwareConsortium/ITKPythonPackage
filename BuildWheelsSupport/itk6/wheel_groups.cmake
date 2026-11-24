# Define below a reasonable dependency graph for ITK groups
set(ITK_GROUP_Core_DEPENDS)
set(ITK_GROUP_IO_DEPENDS Numerics)
set(ITK_GROUP_Numerics_DEPENDS Core)
set(ITK_GROUP_Filtering_DEPENDS Numerics)
set(ITK_GROUP_Filtering-extra_DEPENDS Filtering)
set(ITK_GROUP_Segmentation_DEPENDS Filtering)
set(ITK_GROUP_Registration_DEPENDS Filtering)
set(ITK_GROUP_Video_DEPENDS Core)

# Modules packaged in a wheel other than the one their group and dependees
# select. No wheel may exceed the 100 MB PyPI limit on any platform; move
# modules here to rebalance.
set(ITK_WHEEL_Core_MODULE_OVERRIDES ITKBridgeNumPy ITKVTK)
set(ITK_WHEEL_Filtering-extra_MODULE_OVERRIDES
    AdaptiveDenoising
    AnisotropicDiffusionLBR
    BoneEnhancement
    BoneMorphometry
    BSplineGradient
    Cuberille
    FastBilateral
    FixedPointInverseDisplacementField
    GenericLabelInterpolator
    HigherOrderAccurateGradient
    IsotropicWavelets
    LabelErodeDilate
    MeshNoise
    MeshToPolyData
    MinimalPathExtraction
    MorphologicalContourInterpolation
    ParabolicMorphology
    PhaseSymmetry
    PolarTransform
    RLEImage
    SmoothingRecursiveYvvGaussianFilter
    SplitComponents
    Strain
    SubdivisionQuadEdgeMeshFilter
    TextureFeatures
    Thickness3D
    TotalVariation
)
