# Learning with Subset Stacking (LESS) MPI Version

LESS is a new supervised learning algorithm that is based on training many local estimators on subsets of a given dataset, and then passing their predictions to a global estimator. You can find the details about LESS in our [manuscript](https://arxiv.org/abs/2112.06251).

The serial version of LESS is given our [main repository](https://github.com/sibirbil/LESS). This version of LESS relies on MPI for the parallelization of local models. To use this version, `mpi4py` is used. To use `less-learn-mpi`, you need to **install an mpi library**. We have used `openmpi` in our testing environments.

## Installation

`pip install less-learn-mpi`

## Example

In the example folder there is less-mpi-example.py where a simple example can be found. 

To run the example you can use 

`mpirun -n 2 python3 less-mpi-example.py`

whicih will run the script with two threads.

Note that this example requires pandas which can be installed with `pip install pandas`

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

