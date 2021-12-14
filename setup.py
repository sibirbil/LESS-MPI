from setuptools import setup

setup(name='less-learn-mpi',
      version='0.1.0',
      description='Learning with Subset Stacking - MPI',
      url='git@github.com:sibirbil/LESS-MPI.git',
      maintainer='Kaya Gokalp',
      maintainer_email='kayagokalp@sabanciuniv.edu',
      license='MIT',
      packages=['less'],
      zip_safe=False,
      install_requires=[
        'mpi4py>=3.0.0',
        'scikit-learn>=1.0.1'
      ]),
