ITKPythonPackage
================

Build infrastructure for ITK Python wheels and ITK external module Python
wheels.

`ITK <https://www.itk.org/>`_ is an open-source, cross-platform system that
provides developers with an extensive suite of software tools for image
analysis.

.. code-block:: bash

   pip install itk

For more information on ITK's Python wrapping, see `an introduction in the
Book 1, Chapter 3 of the ITK Software Guide <https://itk.org/ItkSoftwareGuide.pdf>`_.
There are also many `downloadable examples documented in Sphinx
<https://itk.org/ITKExamples/search.html?q=Python>`_.

----

Quick Links
-----------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: Prerequisites
      :link: Prerequisites
      :link-type: doc

      Platform requirements and tooling setup for building ITK wheels.

   .. grid-item-card:: Build ITK Python Packages
      :link: Build_ITK_Python_packages
      :link-type: doc

      Build core ITK wheels (``itk-core``, ``itk-numerics``, ``itk-io``, etc.)
      from source.

   .. grid-item-card:: Build ITK Module Packages
      :link: Build_ITK_Module_Python_packages
      :link-type: doc

      Create, build, and publish Python packages for ITK remote and external
      modules.

   .. grid-item-card:: Miscellaneous
      :link: Miscellaneous
      :link-type: doc

      License, authors, and additional resources.

----

.. toctree::
   :maxdepth: 3

   Prerequisites
   Build_ITK_Python_packages
   Build_ITK_Module_Python_packages
   Miscellaneous
