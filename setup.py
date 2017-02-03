from skbuild import setup

setup(
    name='ITK',
    version='0.11.0',
    author='Insight Software Consortium',
    author_email='insight-users@itk.org',
    packages=['itk'],
    package_dir={'itk':'itk'},
    download_url=r'https://itk.org/ITK/resources/software.html',
    description=r'TK is an open-source software toolkit for performing '
                r'registration and segmentation.',
    long_description='ITK is an open-source, cross-platform system that '
                     'provides developers with an extensive suite of software '
                     'tools for image analysis. Developed through extreme '
                     'programming methodologies, ITK employs leading-edge '
                     'algorithms for registering and segmenting '
                     'multidimensional data..',
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering"
        ],
    license='Apache',
    keywords='ITK InsightToolkit segmentation registration image',
    url=r'http://itk.org/',
    install_requires=[
    ]
    )
