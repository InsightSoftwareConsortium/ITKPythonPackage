
# Generated using: python setup_py_configure.py 'itk'

from __future__ import print_function
from os import sys, path

try:
    from skbuild import setup
except ImportError:
    print('scikit-build is required to build from source.', file=sys.stderr)
    print('Please run:', file=sys.stderr)
    print('', file=sys.stderr)
    print('  python -m pip install scikit-build')
    sys.exit(1)

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from itkVersion import get_versions

this_directory = path.abspath(path.dirname(__file__))
itk_readme_path = path.join(this_directory, 'ITK-source', 'ITK', 'README.md')
if path.exists(itk_readme_path):
    with open(itk_readme_path, encoding='utf-8') as f:
        long_description = f.read()
else:
    with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()

setup(
    name='itk',
    version=get_versions()['package-version'],
    author='Insight Software Consortium',
    author_email='community@itk.org',
    packages=['itk'],
    package_dir={'itk': 'itk'},
    cmake_args=[],
    py_modules=[
        'itkBase',
        'itkConfig',
        'itkExtras',
        'itkLazy',
        'itkTemplate',
        'itkTypes',
        'itkVersion',
        'itkBuildOptions'
    ],
    download_url=r'https://itk.org/ITK/resources/software.html',
    description=r'ITK is an open-source toolkit for multidimensional image analysis',
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: C++",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: Healthcare Industry",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Software Development :: Libraries",
        "Operating System :: Android",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Operating System :: MacOS"
        ],
    license='Apache',
    keywords='ITK InsightToolkit segmentation registration image imaging',
    url=r'https://itk.org/',
    install_requires=[
        r'numpy',
    ]
    )
