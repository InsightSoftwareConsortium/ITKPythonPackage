from skbuild import setup

setup(
    name='itk',
    version='4.12.0.dev0',
    author='Insight Software Consortium',
    author_email='community@itk.org',
    packages=['itk'],
    package_dir={'itk': 'itk'},
    py_modules=[
        'itkBase',
        'itkConfig',
        'itkExtras',
        'itkLazy',
        'itkTemplate',
        'itkTypes',
        'WrapITKBuildOptionsPython'
    ],
    download_url=r'https://itk.org/ITK/resources/software.html',
    description=r'ITK is an open-source toolkit for multidimensional image '
                r'analysis.',
    long_description='ITK is an open-source, cross-platform library that '
                     'provides developers with an extensive suite of software '
                     'tools for image analysis. Developed through extreme '
                     'programming methodologies, ITK employs leading-edge '
                     'algorithms for registering and segmenting '
                     'multidimensional scientific images.',
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
        "Topic :: Software Development :: Libraries"
        ],
    license='Apache',
    keywords='ITK Insight Toolkit segmentation registration image',
    url=r'https://itk.org/',
    install_requires=[
    ]
    )
