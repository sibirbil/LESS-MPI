#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Ilker Birbil @ UvA
"""
from typing import List, Optional, Callable, NamedTuple
import warnings
import numpy as np
from sklearn.base import RegressorMixin, BaseEstimator
from sklearn.neighbors import KDTree
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted
from mpi4py import MPI
import time

comm = MPI.COMM_WORLD
number_of_workers=comm.Get_size()
rank = comm.Get_rank()


############################
# Supporting classes

class SklearnEstimator:
    '''
    This base class is dummy. It is used just for guideline. 
    '''
    def fit(self, X: np.array, y: np.array):
        raise NotImplementedError('Needs to implement fit(X, y)')

    def predict(self, X0: np.array):
        raise NotImplementedError('Needs to implement predict(X, y)')

class LocalModelR(NamedTuple):
    estimator: SklearnEstimator
    center: np.array

class ReplicationR(NamedTuple):
    global_estimator: SklearnEstimator
    local_estimators: List[LocalModelR]

############################    


############################
def rbf(data, center, coeff=1.0):
    '''
    RBF kernel - L2 norm
    This is is used by the default distance function in LESS 
    '''
    return np.exp(-coeff * np.linalg.norm(np.array(data - center, dtype=float), ord=2, axis=1))

############################


class LESSRegressor(RegressorMixin, BaseEstimator, SklearnEstimator):
    '''
    Parameters
    ----------
        frac: fraction of total samples used for number of neighbors (default is 0.05)
        n_neighbors : number of neighbors (default is None)
        n_subsets : number of subsets (default is None)
        n_replications : number of replications (default is 50)
        d_normalize : distance normalization (default is True)
        val_size: percentage of samples used for validation (default is None - no validation)
        random_state: initialization of the random seed (default is None)
        tree_method : method used for constructing the nearest neighbor tree,
                e.g., sklearn.neighbors.KDTree (default) or sklearn.neighbors.BallTree
        cluster_method : method used for clustering the subsets,
                e.g., sklearn.cluster.KMeans, sklearn.cluster.SpectralClustering (default is None)
        local_estimator : estimator for training the local models (default is LinearRegression)
        global_estimator : estimator for training the global model (default is LinearRegression)
        distance_function : distance function evaluating the distance from a subset to a sample,
                e.g., df(subset, sample) which returns a vector of distances
                (default is RBF(subset, sample, 1.0/n_subsets^2))
    '''
    def __init__(self, frac=None, n_neighbors=None, n_subsets=None, 
                 n_replications=20, d_normalize=True, val_size=None, random_state=None,
                 tree_method=lambda data, n_subsets: KDTree(data, n_subsets),
                 cluster_method=None,
                 local_estimator=lambda: LinearRegression(),
                 global_estimator=lambda: LinearRegression(),
                 distance_function: Callable[[np.array, np.array], np.array]=None):
        
        self.local_estimator = local_estimator
        self.global_estimator = global_estimator
        self.tree_method = tree_method
        self.cluster_method = cluster_method
        self.distance_function = distance_function
        self.frac = frac
        self.n_neighbors = n_neighbors
        self.n_subsets = n_subsets
        self.n_replications = n_replications
        self.d_normalize = d_normalize
        self.val_size = val_size
        self.random_state = random_state

        self._set_local_attributes()
    
    def _set_local_attributes(self):
        '''
        Storing the local variables and
        checking the given parameters
        '''
        
  
        self.local_estimator_ = self.local_estimator
        self.global_estimator_ = self.global_estimator
        self.tree_method_ = self.tree_method
        self.cluster_method_ = self.cluster_method
        self.distance_function_ = self.distance_function
        self.frac_ = self.frac
        self.n_neighbors_ = self.n_neighbors
        self.n_subsets_ = self.n_subsets
        self.n_replications_ = self.n_replications
        self.d_normalize_ = self.d_normalize
        self.val_size_ = self.val_size
        self.random_state_ = self.random_state
        self.rng_ = np.random.default_rng(self.random_state_)
        self.replications_: Optional[List[ReplicationR]] = None
        self._isfitted = False
        
        if(self.local_estimator_ == None):
            raise ValueError('LESS does not work without a local estimator.')
            
        if (self.val_size_ != None):            
            if(self.val_size_ <= 0.0 or self.val_size_ >= 1.0):
                raise ValueError('Parameter val_size should be in the interval (0, 1).')
        
        if(self.frac_ != None):
            if(self.frac_ <= 0.0 or self.frac_ > 1.0):
                raise ValueError('Parameter frac should be in the interval (0, 1].')

        if (self.n_replications_ < 1):
            raise ValueError('The number of replications should greater than equal to one.')
                        
        if (self.cluster_method_ != None):
            if (self.frac_ != None):
                warnings.warn('Both frac and cluster_method parameters are provided. \
                              Proceeding with clustering...')
                self.frac_ = None
                
            if ('n_clusters' in self.cluster_method_().get_params().keys()):
                if (self.cluster_method_().get_params()['n_clusters'] == 1):
                    warnings.warn('There is only one cluster, so the \
                                  global estimator is set to none.')
                    # If no global estimator is defined, then we output
                    # the average of the local estimators by assigning 
                    # the weight (1/self.n_subsets) to each local estimator
                    self.global_estimator_ = None
                    self.d_normalize_ = True
                    # If there is also no validation step, then there is 
                    # no randomness. So, no need for replications.
                    if (self.val_size_ == None):
                        warnings.warn('Since validation set is not used, \
                            there is no randomness, and hence, \
                                no need for replications.')                        
                        self.n_replications_ = 1
        elif(self.frac_ == None and 
             self.n_neighbors_== None and
             self.n_subsets_ == None):
            self.frac_ = 0.05
                    
    def _check_input(self, len_X: int):
        '''
        Checks whether the input is valid,
        where len_X is the length of input data
        '''
        if (self.cluster_method_ == None):
            
            if (self.frac_ != None):
                self.n_neighbors_ = int(np.ceil(self.frac_ * len_X))
                self.n_subsets_ = int(len_X/self.n_neighbors_)
                self.n_neighbors_ = int(len_X/self.n_subsets_)
                
            if (self.n_subsets_ == None):
                self.n_subsets_ = int(len_X/self.n_neighbors_)
            
            if (self.n_neighbors_ == None):
                self.n_neighbors_ = int(len_X/self.n_subsets_)
            
            if (self.n_neighbors_ >= len_X):
                warnings.warn('The number of neighbors is larger than \
                    the number of samples. Setting number of subsets to one.')
                self.n_neighbors_ = len_X
                self.n_subsets_ = 1
                
            if (self.n_subsets_ >= len_X):
                warnings.warn('The number of subsets is larger than \
                    the number of samples. Setting number of neighbors to one.')            
                self.n_neighbors_ = 1
                self.n_subsets_ = len_X 
            
            if (self.n_subsets_ == 1):
                warnings.warn('There is only one subset, so the \
                    global estimator is set to none.')
                self.global_estimator_ = None
                self.d_normalize_ = True
        else:
                # When we use clustering, the number of 
                # subsets may differ in each replication
                self.frac_ = None
                self.n_neighbors_=None
                self.n_subsets_ = []


    def fit(self, X: np.array, y: np.array):
        '''
        Dummy fit function that calls the proper method
        according to validation and clustering parameters.
        Options are:
        - Default fitting (no validation set, no clustering)
        - Fitting with validation set (no clustering)
        - Fitting with clustering (no) validation set)
        - Fitting with validation set and clustering
        '''
        
        # Check that X and y have correct shape
        X, y = check_X_y(X, y)
        if (self.val_size_ != None):
            # Validation set is not used for
            # global estimation
            if (self.cluster_method_ == None):
                self._fitval(X, y)
            else:
                self._fitvalc(X, y)
        else:
            # Validation set is used for
            # global estimation
            if (self.cluster_method_ == None):
                self._fitnoval(X, y)
            else:
                self._fitnovalc(X, y)
        
        self._isfitted = True
        
        return self

    def _fit_helper(self,X,y,neighbor_indices_list, Xval = None):
        if rank < ((self.n_subsets_) % number_of_workers):
            start = rank * (int((self.n_subsets_/number_of_workers))+1)
            stop = start + int((self.n_subsets_/number_of_workers))
        else:
            start = (rank * int((self.n_subsets_/number_of_workers))) + (self.n_subsets_ % number_of_workers)
            stop = start + int((self.n_subsets_/number_of_workers)) - 1
        my_chunk_len = stop-start+1
        if Xval is None:
            predicts = np.zeros((len(X),my_chunk_len))
            dists = np.zeros((len(X),my_chunk_len))
        else:
            predicts = np.zeros((len(Xval),my_chunk_len))
            dists = np.zeros((len(Xval),my_chunk_len))
            

        local_models: List[LocalModelR] = [None for i in range(my_chunk_len)]
        
        for job_index in range(start,stop+1):
            neighbor_i = job_index
            neighbor_indices = neighbor_indices_list[job_index]
            Xneighbors, yneighbors = X[neighbor_indices], y[neighbor_indices]
            local_center = np.mean(Xneighbors, axis=0)
            if ('random_state' in self.local_estimator_().get_params().keys()):
                local_model = self.local_estimator_().\
                    set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                        fit(Xneighbors, yneighbors)
            else:
                local_model = self.local_estimator_().fit(Xneighbors, yneighbors)
            local_models[job_index - start] = (LocalModelR(estimator=local_model, center=local_center))
            if Xval is None:
                predicts[:, job_index - start] = local_model.predict(X)
            else:
                predicts[:, job_index - start] = local_model.predict(Xval)
                
            if(self.distance_function_ == None):
                if(Xval is None):
                    dists[:, job_index - start] = rbf(X, local_center, \
                        coeff=1.0/np.power(self.n_subsets_, 2.0))
                else:
                    dists[:, job_index - start] = rbf(Xval, local_center, \
                        coeff=1.0/np.power(self.n_subsets_, 2.0))
            else:
                if(Xval is None):
                    dists[:, job_index - start] = self.distance_function(X, local_center)
                else:
                    dists[:, job_index - start] = self.distance_function(Xval, local_center)
                  

        local_models_gathered = comm.gather(local_models, root=0)
        dists_gathered = comm.gather(dists, root=0)
        predicts_gathered = comm.gather(predicts, root=0)
        if(rank == 0):
            dists_gathered = (np.concatenate(dists_gathered, axis=1))
            local_models_gathered = [localmodel for localmodels in local_models_gathered for localmodel in localmodels]
            predicts_gathered = np.concatenate(predicts_gathered, axis=1)
        return [predicts_gathered, dists_gathered, local_models_gathered]

    def _fit_helperc(self,X,y,cluster_fit_labels,cluster_fit_centers,use_cluster_centers,i, Xval = None):
        if rank < ((self.n_subsets_[i]) % number_of_workers):
            start = rank * (int(((self.n_subsets_[i])/number_of_workers))+1)
            stop = start + int(((self.n_subsets_[i])/number_of_workers))
        else:
            start = (rank * int(((self.n_subsets_[i])/number_of_workers))) + ((self.n_subsets_[i]) % number_of_workers)
            stop = start + int(((self.n_subsets_[i])/number_of_workers)) - 1
        my_chunk_len = stop-start+1
        if Xval is None:
            predicts = np.zeros((len(X),my_chunk_len))
            dists = np.zeros((len(X),my_chunk_len))
        else:
            predicts = np.zeros((len(Xval),my_chunk_len))
            dists = np.zeros((len(Xval),my_chunk_len))
        

        local_models: List[LocalModelR] = [None for i in range(my_chunk_len)]
        
        for job_index in range(start,stop+1):
            neighbor_indices = cluster_fit_labels == np.unique(cluster_fit_labels)[job_index]
            Xneighbors, yneighbors = X[neighbor_indices], y[neighbor_indices]
            if(use_cluster_centers):
                local_center = cluster_fit_centers[job_index]
            else:
                local_center = np.mean(Xneighbors, axis=0)
            if ('random_state' in self.local_estimator_().get_params().keys()):
                local_model = self.local_estimator_().\
                    set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                        fit(Xneighbors, yneighbors)
            else:
                local_model = self.local_estimator_().fit(Xneighbors, yneighbors)
            local_models[job_index - start] = (LocalModelR(estimator=local_model, center=local_center))
            if Xval is None:
                predicts[:, job_index - start] = local_model.predict(X)
            else:
                predicts[:, job_index - start] = local_model.predict(Xval)
                
            if(self.distance_function_ == None):
                if(Xval is None):
                    dists[:, job_index - start] = rbf(X, local_center, \
                        coeff=1.0/np.power(self.n_subsets_[i], 2.0))
                else:
                    dists[:, job_index - start] = rbf(Xval, local_center, \
                        coeff=1.0/np.power(self.n_subsets_[i], 2.0))
            else:
                if(Xval is None):
                    dists[:, job_index - start] = self.distance_function(X, local_center)
                else:
                    dists[:, job_index - start] = self.distance_function(Xval, local_center)
                  

        local_models_gathered = comm.gather(local_models, root=0)
        dists_gathered = comm.gather(dists, root=0)
        predicts_gathered = comm.gather(predicts, root=0)
        if(rank == 0):
            dists_gathered = (np.concatenate(dists_gathered, axis=1))
            local_models_gathered = [localmodel for localmodels in local_models_gathered for localmodel in localmodels]
            predicts_gathered = np.concatenate(predicts_gathered, axis=1)
        return [predicts_gathered, dists_gathered, local_models_gathered]
    def _fitnoval(self, X: np.array, y: np.array):
        '''
        Fit function: All data is used for global estimator (no validation)
        Tree method is used (no clustering)
        '''

        len_X: int = len(X)
        # Check the validity of the input
        self._check_input(len_X)
        # A nearest neighbor tree is grown for querying
        tree = self.tree_method_(X, self.n_subsets_)
        self.replications_ = []
        for i in range(self.n_replications_):
            if rank == 0:
                # Select n_subsets many samples to construct the local sample sets
                sample_indices = self.rng_.choice(len_X, size=self.n_subsets_)
                # Construct the local sample sets
                _, neighbor_indices_list = np.array(tree.query(X[sample_indices], k=self.n_neighbors_), dtype = 'i')
            else:
                neighbor_indices_list = np.zeros([self.n_subsets_, self.n_neighbors_],dtype='i')
            comm.Bcast(neighbor_indices_list, root=0)
            local_models: List[LocalModelR] = []
            dists = np.zeros((len_X, self.n_subsets_))            
            predicts = np.zeros((len_X, self.n_subsets_))
            [predicts,dists,local_models] = self._fit_helper(X,y,neighbor_indices_list)
            if rank == 0:
                # Normalize the distances from each sample to the local subsets
                if (self.d_normalize_):
                    dists = (dists.T/np.sum(dists, axis=1)).T
            
                if (self.global_estimator_ != None):
                    if ('random_state' in self.global_estimator_().get_params().keys()):
                        global_model = self.global_estimator_().\
                            set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                                fit(dists * predicts, y)
                    else:
                        global_model = self.global_estimator_().fit(dists * predicts, y)
                else:
                    global_model = None

                self.replications_.append(ReplicationR(global_model, local_models))

        return self


    def _fitval(self, X: np.array, y: np.array):
        '''
        Fit function: (val_size x data) is used for global estimator (validation)
        Tree method is used (no clustering)
        '''

        self.replications_ = []
        for i in range(self.n_replications_):
            if rank ==0:
                # Split for global estimation
                X_train, X_val, y_train, y_val = train_test_split(X, y,
                    test_size=self.val_size_,
                    random_state=self.rng_.integers(np.iinfo(np.int16).max))
            else:
                len_x_val = int(len(X) * self.val_size_)
                len_y_val = int(len(y) * self.val_size_)
                len_x_train = int(len(X) * (1-self.val_size_))
                len_y_train = int(len(y) * (1-self.val_size_))
                X_train = np.empty((len_x_train,X[0].shape[0]))
                y_train = np.empty(len_y_train)
                X_val = np.empty((len_x_val,X[0].shape[0]))
                y_val = np.empty(len_y_val)
            
            X_train = comm.bcast(X_train, root=0)
            X_val = comm.bcast(X_val, root=0)
            y_train = comm.bcast(y_train, root=0)
            y_val = comm.bcast(y_val,root=0)  
            len_X_val: int = len(X_val)
            len_X_train: int = len(X_train)
            # Check the validity of the input
            if (i==0):
                self._check_input(len_X_train)
            if rank == 0: 
                # A nearest neighbor tree is grown for querying
                tree = self.tree_method_(X_train, self.n_subsets_)
            
                # Select n_subsets many samples to construct the local sample sets
                sample_indices = self.rng_.choice(len_X_train, size=self.n_subsets_)
                # Construct the local sample sets
                _, neighbor_indices_list = np.array(tree.query(X_train[sample_indices], k=self.n_neighbors_), dtype='i')
            else:
                neighbor_indices_list = np.zeros([self.n_subsets_, self.n_neighbors_], dtype = 'i')
            comm.Bcast(neighbor_indices_list, root=0)
            local_models: List[LocalModelR] = []
            dists = np.zeros((len_X_val, self.n_subsets_))            
            predicts = np.zeros((len_X_val, self.n_subsets_))
            [predicts,dists,local_models] = self._fit_helper(X_train,y_train,neighbor_indices_list,X_val)
            if rank == 0:
                # Normalize the distances from each sample to the local subsets
                if (self.d_normalize_):
                    dists = (dists.T/np.sum(dists, axis=1)).T
            
                if (self.global_estimator_ != None):
                    if ('random_state' in self.global_estimator_().get_params().keys()):
                        global_model = self.global_estimator_().\
                            set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                                fit(dists * predicts, y_val)
                    else:
                        global_model = self.global_estimator_().fit(dists * predicts, y_val)
                else:
                     global_model = None

                self.replications_.append(ReplicationR(global_model, local_models))

        return self

    def _fitnovalc(self, X: np.array, y: np.array):
        '''
        Fit function: All data is used for global estimator (no validation)
        Clustering is used (no tree method)
        '''

        len_X: int = len(X)
        # Check the validity of the input
        self._check_input(len_X)
        
        if ('random_state' not in self.cluster_method_().get_params().keys()): 
                warnings.warn('Clustering method is not random, so there is \
                    no need for replications, unless validaton set is used. \
                    Note that lack of replications may increase the variance.') 
                if(rank == 0):
                     cluster_fit = self.cluster_method().fit(X)
                     self.n_replications_ = 1
                     cluster_fit_labels = cluster_fit.labels_
                     cluster_fit_centers = cluster_fit.cluster_centers_
                     n_clusters = cluster_fit_labels.shape[0]
                     n_features = cluster_fit_labels.shape[1]
                else:
                     n_clusters = comm.bcast(n_clusters, root=0)
                     n_features = comm.bcast(n_features, root=0)
                     self.n_replications_ = 1
                     cluster_fit_labels = np.zeros([n_clusters, n_features], dtype = 'i')
                     cluster_fit_centers = np.zeros([n_clusters, n_features], dtype = 'd')
                cluster_fit_labels = comm.bcast(cluster_fit_labels, root=0) 
                cluster_fit_centers = comm.bcast(cluster_fit_centers, root=0) 
        self.replications_ = []
        for i in range(self.n_replications_):
            if (self.n_replications_ > 1):
                if (rank == 0):
                    cluster_fit = self.cluster_method(n_jobs=1).\
                        set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                             fit(X)
                    cluster_fit_labels = cluster_fit.labels_
                    cluster_fit_centers = cluster_fit.cluster_centers_
                    n_clusters = cluster_fit_centers.shape[0]
                    n_features = cluster_fit_centers.shape[1]
                else:
                     n_clusters = 0
                     n_features = 0
                     use_cluster_centers = False
                     cluster_fit_labels = np.zeros([n_clusters, n_features], dtype = 'i')
                     cluster_fit_centers = np.zeros([n_clusters, n_features], dtype = 'd')
                    
                n_clusters = comm.bcast(n_clusters, root=0)
                n_features = comm.bcast(n_features, root=0)
                cluster_fit_labels = comm.bcast(cluster_fit_labels, root=0) 
                cluster_fit_centers = comm.bcast(cluster_fit_centers, root=0) 
            # Some clustering methods may find less number of
            # clusters than requested 'n_clusters'
            self.n_subsets_.append(len(np.unique(cluster_fit_labels)))
            n_subsets = self.n_subsets_[i]
            
            local_models: List[LocalModelR] = []
            dists = np.zeros((len_X, n_subsets))            
            predicts = np.zeros((len_X, n_subsets))
            if rank == 0:            
                if (hasattr(cluster_fit, 'cluster_centers_')):
                     use_cluster_centers = True
                else:
                     use_cluster_centers = False
            use_cluster_centers = comm.bcast(use_cluster_centers, root=0)
                

            [predicts,dists,local_models] = self._fit_helperc(X,y,cluster_fit_labels,cluster_fit_centers,use_cluster_centers,i)
            if rank == 0:
                # Normalize the distances from each sample to the local subsets
                if (self.d_normalize_):
                    dists = (dists.T/np.sum(dists, axis=1)).T
            
                if (self.global_estimator_ != None):
                    if ('random_state' in self.global_estimator_().get_params().keys()):
                        global_model = self.global_estimator_().\
                            set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                            fit(dists * predicts, y)
                    else:
                        global_model = self.global_estimator_().fit(dists * predicts, y)
                else:
                    global_model = None

                self.replications_.append(ReplicationR(global_model, local_models))

        return self

    def _fitvalc(self, X: np.array, y: np.array):
        '''
        Fit function: (val_size x data) is used for global estimator (validation)
        Clustering is used (no tree method)
        '''

        self.replications_ = []
        for i in range(self.n_replications_):
            if rank ==0:
                # Split for global estimation
                X_train, X_val, y_train, y_val = train_test_split(X, y,
                    test_size=self.val_size_,
                    random_state=self.rng_.integers(np.iinfo(np.int16).max))
            else:
                len_x_val = int(len(X) * self.val_size_)
                len_y_val = int(len(y) * self.val_size_)
                len_x_train = int(len(X) * (1-self.val_size_))
                len_y_train = int(len(y) * (1-self.val_size_))
                X_train = np.empty((len_x_train,X[0].shape[0]))
                y_train = np.empty(len_y_train)
                X_val = np.empty((len_x_val,X[0].shape[0]))
                y_val = np.empty(len_y_val)
            
            X_train = comm.bcast(X_train, root=0)
            X_val = comm.bcast(X_val, root=0)
            y_train = comm.bcast(y_train, root=0)
            y_val = comm.bcast(y_val,root=0)  
            len_X_val: int = len(X_val)
            len_X_train: int = len(X_train)
            # Check the validity of the input
            if (i == 0):
                use_cluster_centers = False
                self._check_input(len_X_train)

 
            if(rank == 0):
                 if 'random_state' not in self.cluster_method().get_params().keys():
                     cluster_fit = self.cluster_method().fit(X_train)
                 else:
                     cluster_fit = self.cluster_method().\
                         set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                             fit(X_train)
                 cluster_fit_labels = cluster_fit.labels_
                 cluster_fit_centers = cluster_fit.cluster_centers_
                 n_clusters = cluster_fit_centers.shape[0]
                 n_features = cluster_fit_centers.shape[1]
            else:
                 n_clusters = 0
                 n_features = 0
                 cluster_fit_labels = np.zeros([n_clusters, n_features], dtype = 'i')
                 cluster_fit_centers = np.zeros([n_clusters, n_features], dtype = 'd')
            n_clusters = comm.bcast(n_clusters, root=0)
            n_features = comm.bcast(n_features, root=0)
            cluster_fit_labels = comm.bcast(cluster_fit_labels, root=0) 
            cluster_fit_centers = comm.bcast(cluster_fit_centers, root=0) 
            if (rank == 0):
                if (i==1):
                    if (hasattr(cluster_fit, 'cluster_centers_')):
                        use_cluster_centers = True
                    else:
                        use_cluster_centers = False
            use_cluster_centers = comm.bcast(use_cluster_centers, root=0)  
            # Since each replication returns
            self.n_subsets_.append(len(np.unique(cluster_fit_labels)))
            n_subsets = self.n_subsets_[i]
            
            local_models: List[LocalModelR] = []
            dists = np.zeros((len_X_val, n_subsets))            
            predicts = np.zeros((len_X_val, n_subsets))
                
            [predicts,dists,local_models] = self._fit_helperc(X_train,y_train,cluster_fit_labels,cluster_fit_centers,use_cluster_centers,i,X_val)
            if (rank == 0):
                # Normalize the distances from each sample to the local subsets
                if (self.d_normalize_):
                    dists = (dists.T/np.sum(dists, axis=1)).T
            
                if (self.global_estimator_ != None):
                    if ('random_state' in self.global_estimator_().get_params().keys()):
                        global_model = self.global_estimator_().\
                            set_params(random_state=self.rng_.integers(np.iinfo(np.int16).max)).\
                                fit(dists * predicts, y_val)
                    else:
                        global_model = self.global_estimator_().fit(dists * predicts, y_val)
                else:
                    global_model = None

                self.replications_.append(ReplicationR(global_model, local_models))

        return self


    def predict(self, X0: np.array):
        '''
        Predictions are evaluated for the test samples in X0
        '''
        
        check_is_fitted(self, attributes='_isfitted')
        # Input validation
        X0 = check_array(X0)

        len_X0: int = len(X0)
        yhat = np.zeros(len_X0)
        for i in range(self.n_replications_):
            # Get the fitted global and local estimators
            global_model = self.replications_[i].global_estimator
            local_models = self.replications_[i].local_estimators
            if (self.cluster_method_ == None):
                n_subsets = self.n_subsets_
            else:
                n_subsets = self.n_subsets_[i]
            predicts = np.zeros((len_X0, n_subsets))
            dists = np.zeros((len_X0, n_subsets))
            for j in range(n_subsets):
                local_center = local_models[j].center
                local_model = local_models[j].estimator
                predicts[:, j] = local_model.predict(X0)
                
                if (self.distance_function_ == None):
                    dists[:, j] = rbf(X0, local_center, \
                        coeff=1.0/np.power(n_subsets, 2.0))
                else:
                    dists[:, j] = self.distance_function_(X0, local_center)

            # Normalize the distances from each sample to the local subsets
            if (self.d_normalize_):
                dists = (dists.T/np.sum(dists, axis=1)).T

            if (global_model != None):
                yhat += global_model.predict(dists * predicts)
            else:
                yhat += np.sum(dists * predicts, axis=1)

        yhat = yhat/self.n_replications
                    
        return yhat
    
    # AUXILIARY FUNCTIONS
    
    def get_n_subsets(self):
        
        if (self._isfitted == False):
            warnings.warn('You need to fit LESS first.')

        return self.n_subsets_
    
    def get_n_neighbors(self):
        
        if (self.cluster_method_ != None):
            warnings.warn('Number of neighbors is not fixed when clustering is used.')
        elif (self._isfitted == False):
            warnings.warn('You need to fit LESS first.')
            
        return self.n_neighbors_
    
    def get_frac(self):
        
        # Fraction is set to None only if clustering method is given
        if (self.cluster_method_ != None):
            warnings.warn('Parameter frac is not set when clustering is used.')

        return self.frac_
    
    def get_n_replications(self):
        
        return self.n_replications_
    
    def get_d_normalize(self):
        
        return self.d_normalize_
    
    def get_val_size(self):
        
        return self.val_size_
    
    def get_random_state(self):
        
        return self.random_state_
