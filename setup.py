from setuptools import setup

setup(name='less-learn-mpi',
      version='0.1.3',
      description='Learning with Subset Stacking - MPI',
      url='https://github.com/sibirbil/LESS-MPI',
      maintainer='Kaya Gokalp',
      maintainer_email='kayagokalp@sabanciuniv.edu',
      license='MIT',
      packages=['lessmpi'],
      zip_safe=False,
      python_requires='>=3.6',
      install_requires=[
        'mpi4py>=3.0.0',
        'scikit-learn>=1.0.1',
        'numpy>=1.21.4'
      ])
