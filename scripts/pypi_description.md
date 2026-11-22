![ITK: The Insight Toolkit](https://raw.githubusercontent.com/InsightSoftwareConsortium/ITK/801370c025c7d296783481779a41c6d559c992c5/Documentation/Art/itkBannerSmall.png)

# ITK: The Insight Toolkit

The Insight Toolkit (ITK) is an open-source, cross-platform toolkit for
N-dimensional scientific image processing, segmentation, and registration,
used widely in medical imaging research.

## Install

```bash
pip install itk
```

The `itk` package installs the whole toolkit through its parts, each of
which can also be installed alone: `itk-core`, `itk-numerics`, `itk-io`,
`itk-filtering`, `itk-filtering-extra`, `itk-registration`, and
`itk-segmentation`. ITK is also available from conda-forge
(`conda install -c conda-forge itk`).

Each wheel supports Python 3.11 and later (stable ABI) on Linux x86_64 and
aarch64 (manylinux_2_28), macOS arm64, and Windows x64.

## Quick start

```python
import itk

image = itk.imread("input.nrrd")
smoothed = itk.median_image_filter(image, radius=2)
itk.imwrite(smoothed, "output.nrrd")

array = itk.array_view_from_image(smoothed)  # NumPy view, no copy
```

## Links

- Documentation: https://docs.itk.org/
- Examples: https://examples.itk.org/
- Questions and discussion: https://discourse.itk.org/
- Source code: https://github.com/InsightSoftwareConsortium/ITK
- Issue tracker: https://github.com/InsightSoftwareConsortium/ITK/issues
- How these wheels are built:
  https://github.com/InsightSoftwareConsortium/ITKPythonPackage

## Citing ITK

> McCormick M, Liu X, Jomier J, Marion C, Ibanez L. ITK: enabling
> reproducible research and open science. Front Neuroinform. 2014;8:13.
> doi:10.3389/fninf.2014.00013

Citations for a specific release are on Zenodo:
https://doi.org/10.5281/zenodo.889843. More ways to cite ITK are listed at
https://github.com/InsightSoftwareConsortium/ITK#citation.

## License and support

ITK is distributed under the Apache 2.0 license. It is a fiscally sponsored
project of NumFOCUS (https://numfocus.org/); donations through
https://opencollective.com/itk support its development.
