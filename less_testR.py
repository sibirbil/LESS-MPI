#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan 19 08:41:43 2021

@author: sibirbil
"""
# %%
from typing import List, Callable
import time

import numpy as np
# from sklearn.preprocessing import StandardScaler
from pandas import DataFrame
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from less import LESSRegressor
import datasets as DS
from mpi4py import MPI

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
# %%

#problems: List[Callable[[str], DataFrame]] = [DS.abalone, DS.airfoil, DS.housing, 
#                                              DS.cadata, DS.ccpp, DS.energy,
#                                              DS.cpusmallscale, DS.superconduct]

problems: List[Callable[[str], DataFrame]] = [DS.abalone]
#problems: List[Callable[[str], DataFrame]] = [DS.msd]


# %%
for problem in problems:
	pname = problem.__name__.upper()
	if(rank == 0):
		print(pname)    

	df = np.array(problem('datasets/'))
	df_old = problem('datasets/')
	if(pname == "MSD"):
		X = df[:, 1:-1]
		y = df[:, 0]
	else:
		X = df[:, 0:-1]
		y = df[:, -1]
	split_size = 0.3
	X = StandardScaler().fit_transform(X)
	y = StandardScaler().fit_transform(np.expand_dims(y, -1))
	y = np.reshape(y, (len(y),))
	if(rank == 0):
		X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=split_size)
		
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
	LESS_mod = LESSRegressor(frac=0.01, n_replications=20)
	if (rank == 0):
		start_time = time.time()
	LESS_fit = LESS_mod.fit(X_train, y_train)
	if (rank == 0):
		end_time = time.time()
		print('Fit total time: ', end_time - start_time)
		print('Test error of LESS: ', mean_squared_error(LESS_fit.predict(X_test), y_test))     
		end_total_time = time.time()
		print('total time: ', end_total_time - start_time)
 
# %%
