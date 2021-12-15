import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from mpi4py import MPI
import time
import datasets as DS
from lessmpi import LESSRegressor


comm = MPI.COMM_WORLD
rank = comm.Get_rank()

split_size = 0.1
random_state = 1234
df = np.array(DS.energy('./datasets/'))
X, y = df[:, 0:-1], df[:, -1]

if(rank == 0):
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=split_size,random_state=random_state)

else:
  len_x_test = int(len(X) * split_size)
  len_y_test = int(len(X) * split_size)
  len_x_train = int(len(X) * (1-split_size))
  len_y_train = int(len(y) * (1-split_size))
  X_train = np.empty((len_x_train,X[0].shape[0]))
  y_train = np.empty(len_y_train)
  X_test = np.empty((len_x_test,X[0].shape[0]))
  y_test = np.empty(len_y_test)


X_train = comm.bcast(X_train, root=0)
X_test = comm.bcast(X_test, root=0)
y_train = comm.bcast(y_train, root=0)
y_test = comm.bcast(y_test, root=0)

if(rank == 0):
  start_time = time.time()
LESS_fit = LESSRegressor(random_state=random_state).fit(X_train, y_train)

if(rank == 0):
  end_time = time.time()
  print('Test error of LESS: ', mean_squared_error(LESS_fit.predict(X_test), y_test), "and it took", end_time-start_time, "seconds")
