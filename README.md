# Learning with Subset Stacking (LESS) - MPI Version

LESS is a new supervised learning algorithm that is based on training many local estimators on subsets of a given dataset, and then passing their predictions to a global estimator. The current version supports regression, and we are working on classification. You can find the details about LESS in our [manuscript](https://arxiv.org/abs/2112.06251).

The serial version of LESS is given in our [main repository](https://github.com/sibirbil/LESS). This version of LESS relies on MPI for the parallelization of local models. To use this version, `mpi4py` is used. To use `less-learn-mpi`, you need to **install an mpi library**. We have used `openmpi` in our testing environments.

## Installation

`pip install less-learn-mpi`

## Example

In folder _example_, we also provide a simple script for testing. You can run this script for two threads by typing

`mpirun -n 2 python3 less-mpi-example.py`

Note that this example requires the package `pandas`.

## Citation

Our software can be cited as:
````
  @misc{LESS,
    author = "Ilker Birbil",
    title = "LESS: LEarning with Subset Stacking",
    year = 2021,
    url = "https://github.com/sibirbil/LESS/"
  }
````

