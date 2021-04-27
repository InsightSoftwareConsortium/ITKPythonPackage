
# Generated using: python setup_py_configure.py 'itk-meta'

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

long_description = 'itk\n'
long_description += '====================================\n\n'
long_description += 'ITK is an open-source, cross-platform library that provides developers with an extensive suite of software tools for image analysis. Developed through extreme programming methodologies, ITK employs leading-edge algorithms for registering and segmenting multidimensional scientific images.\n\n'

this_directory = path.abspath(path.dirname(__file__))
itk_readme_path = path.join(this_directory, 'ITK-source', 'ITK', 'README.md')
if path.exists(itk_readme_path):
    with open(itk_readme_path, encoding='utf-8') as f:
        long_description += f.read()
else:
    with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
        long_description += f.read()


setup(
    name='itk',
    version=get_versions()['package-version'],
    author='Insight Software Consortium',
    author_email='community@itk.org',
    packages=['itk'],
    package_dir={'itk': 'itk'},
    cmake_args=['-DITKPythonPackage_WHEEL_NAME:STRING=itk-meta'],
    py_modules=[],
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
        'itk-core==5.2.0.post1',
        'itk-numerics==5.2.0.post1',
        'itk-io==5.2.0.post1',
        'itk-filtering==5.2.0.post1',
        'itk-registration==5.2.0.post1',
        'itk-segmentation==5.2.0.post1',
        'numpy'
    ]
    )
