"""The wheel layout for the major version of the ITK source being built.

Each profile is a directory under ``BuildWheelsSupport`` holding
``WHEEL_NAMES.txt`` and ``wheel_groups.cmake``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BUILD_WHEELS_SUPPORT_DIR = Path(__file__).resolve().parent.parent / "BuildWheelsSupport"

# ITK modules ingested from remote modules. ITK excludes them from its default
# build; the wheels ship them. Override one with -DModule_<name>:BOOL=OFF.
ITK_INGESTED_REMOTE_MODULES: tuple[str, ...] = (
    "AdaptiveDenoising",
    "AnisotropicDiffusionLBR",
    "BoneEnhancement",
    "BoneMorphometry",
    "BSplineGradient",
    "Cuberille",
    "FastBilateral",
    "FixedPointInverseDisplacementField",
    "Fpfh",
    "GenericLabelInterpolator",
    "GrowCut",
    "HigherOrderAccurateGradient",
    "IOFDF",
    "IOMeshMZ3",
    "IOMeshSTL",
    "IOMeshSWC",
    "IOScanco",
    "IOTransformDCMTK",
    "IsotropicWavelets",
    "LabelErodeDilate",
    "MGHIO",
    "MeshNoise",
    "MeshToPolyData",
    "MinimalPathExtraction",
    "Montage",
    "MorphologicalContourInterpolation",
    "MultipleImageIterator",
    "ParabolicMorphology",
    "PhaseSymmetry",
    "PolarTransform",
    "PrincipalComponentsAnalysis",
    "RANSAC",
    "RLEImage",
    "SmoothingRecursiveYvvGaussianFilter",
    "SplitComponents",
    "Strain",
    "SubdivisionQuadEdgeMeshFilter",
    "TextureFeatures",
    "Thickness3D",
    "TotalVariation",
    "TwoProjectionRegistration",
    "VariationalRegistration",
)

_ITK_VERSION_MAJOR = re.compile(
    r'^\s*set\(\s*ITK_VERSION_MAJOR\s+"?(\d+)"?\s*\)', re.MULTILINE
)


@dataclass(frozen=True)
class WheelProfile:
    """Which wheels an ITK major version is packaged in, and what they ship."""

    name: str
    ingested_remote_modules: tuple[str, ...]

    @property
    def directory(self) -> Path:
        return BUILD_WHEELS_SUPPORT_DIR / self.name

    @property
    def wheel_groups_file(self) -> Path:
        return self.directory / "wheel_groups.cmake"

    def wheel_names(self) -> list[str]:
        """The wheel names, in build order."""
        with (self.directory / "WHEEL_NAMES.txt").open(encoding="utf-8") as content:
            return [wheel_name.strip() for wheel_name in content]


# In ITK 5 these are remote modules; enabling one fetches it.
ITK5_PROFILE = WheelProfile("itk5", ())
ITK6_PROFILE = WheelProfile("itk6", ITK_INGESTED_REMOTE_MODULES)


def itk_version_major(itk_source_dir: str | Path) -> int:
    """The ``ITK_VERSION_MAJOR`` of the ITK source tree at *itk_source_dir*."""
    version_file = Path(itk_source_dir) / "CMake" / "itkVersion.cmake"
    if not version_file.is_file():
        msg = f"Cannot tell the ITK version: {version_file} does not exist"
        raise FileNotFoundError(msg)
    match = _ITK_VERSION_MAJOR.search(version_file.read_text(encoding="utf-8"))
    if match is None:
        msg = f"No ITK_VERSION_MAJOR in {version_file}"
        raise ValueError(msg)
    return int(match.group(1))


def wheel_profile_for_major(major: int) -> WheelProfile:
    """The wheel profile for ITK major version *major*."""
    if major == 5:
        return ITK5_PROFILE
    if major >= 6:
        return ITK6_PROFILE
    msg = f"ITK {major} wheels are not supported; ITK 5 is the oldest"
    raise ValueError(msg)


def wheel_profile(itk_source_dir: str | Path) -> WheelProfile:
    """The wheel profile for the ITK source tree at *itk_source_dir*."""
    return wheel_profile_for_major(itk_version_major(itk_source_dir))
