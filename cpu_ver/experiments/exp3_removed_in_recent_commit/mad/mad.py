import sys, os
sys.path.append(os.path.abspath('../../../'))



"""Runs for paper"""
import matplotlib as mpl
mpl.use('Agg')
"""Runs for paper"""
import numpy as np
import pickle
from collections import defaultdict
from funkyyak import grad, kylist, getval

import hypergrad.mnist as mnist
from hypergrad.mnist import random_partition
from hypergrad.nn_utils import make_nn_funs, VectorParser
from hypergrad.optimizers import sgd_meta_only_mad as sgd
from hypergrad.util import RandomState, dictslice, dictmap
from hypergrad.odyssey import omap

layer_sizes = [784, 1000, 1000, 10]
N_layers = len(layer_sizes) - 1
batch_size = 200
N_iters = 300
N_train = 10**4 * 2
N_valid = 10**4
N_tests = 10**4
N_thin = 50

all_N_meta_iter = [0, 0, 5]
alpha = 0.3
meta_alpha = 0.2
beta = 0.9
seed = 0
N_thin = 10
N_meta_thin = 1
log_L2 = -5.0
log_init_scale = -3.0

def run():
    RS = RandomState((seed, "top_rs"))
    all_data = mnist.load_data_as_dict()
    train_data, tests_data = random_partition(all_data, RS, [N_train, N_tests])
    w_parser, pred_fun, loss_fun, frac_err = make_nn_funs(layer_sizes)
    N_weights = w_parser.vect.size

    def transform_weights(z_vect, transform):
        return z_vect * transform

    def regularization(z_vect):
        return np.dot(z_vect, z_vect) * np.exp(log_L2)

    def constrain_transform(t_vect, name):
        all_t = w_parser.new_vect(t_vect)
        for i in range(N_layers):
            all_t[('biases', i)] = 0.0
        if name == 'universal':
            t_mean = np.mean([np.mean(all_t[('weights', i)])
                              for i in range(N_layers)])
            for i in range(N_layers):
                all_t[('weights', i)] = t_mean
        elif name == 'layers':
            for i in range(N_layers):
                all_t[('weights', i)] = np.mean(all_t[('weights', i)])
        elif name == 'units':
            for i in range(N_layers):
                all_t[('weights', i)] = np.mean(all_t[('weights', i)], axis=1, keepdims=True)
        else:
            raise Exception
        return all_t.vect

    def process_transform(t_vect):
        # Remove the redundancy due to sharing transformations within units
        all_t = w_parser.new_vect(t_vect)
        new_t = np.zeros((0,))
        for i in range(N_layers):
            layer = all_t[('weights', i)]
            assert np.all(layer[:, 0] == layer[:, 1])
            cur_t = np.exp(log_L2) / layer[:, 0]**2
            new_t = np.concatenate((new_t, cur_t))
        return new_t

    def train_z(data, z_vect_0, transform):
        N_data = data['X'].shape[0]
        def primal_loss(z_vect, transform, i_primal, record_results=False):
            RS = RandomState((seed, i_primal, "primal"))
            idxs = RS.randint(N_data, size=batch_size)
            minibatch = dictslice(data, idxs)
            w_vect = transform_weights(z_vect, transform)
            loss = loss_fun(w_vect, **minibatch)
            reg = regularization(z_vect)
            if record_results and i_primal % N_thin == 0:
                print "Iter {0}: train: {1}".format(i_primal, getval(loss))
            return loss + reg
        return sgd(grad(primal_loss), transform, z_vect_0, alpha, beta, N_iters)

    all_transforms, all_tests_loss = [], []
    def train_reg(transform_0, constraint, N_meta_iter, i_top):
        def hyperloss(transform, i_hyper, cur_train_data, cur_valid_data):
            RS = RandomState((seed, i_top, i_hyper, "hyperloss"))
            z_vect_0 = RS.randn(N_weights) * np.exp(log_init_scale)
            z_vect_final = train_z(cur_train_data, z_vect_0, transform)
            w_vect_final = transform_weights(z_vect_final, transform)
            return loss_fun(w_vect_final, **cur_valid_data)
        hypergrad = grad(hyperloss)
        cur_transform = transform_0
        for i_hyper in range(N_meta_iter):
            if i_hyper % N_meta_thin == 0:
                tests_loss = hyperloss(cur_transform, i_hyper, train_data, tests_data)
                all_tests_loss.append(tests_loss)
                all_transforms.append(cur_transform.copy())
                print "Hyper iter {0}, test loss {1}".format(i_hyper, all_tests_loss[-1])
                print "Cur_transform", np.mean(cur_transform)
            RS = RandomState((seed, i_top, i_hyper, "hyperloss"))
            cur_split = random_partition(train_data, RS, [N_train - N_valid, N_valid])
            raw_grad = hypergrad(cur_transform, i_hyper, *cur_split)
            constrained_grad = constrain_transform(raw_grad, constraint)
            cur_transform -= constrained_grad * meta_alpha
        return cur_transform

    transform = np.ones(N_weights)
    constraints = ['universal', 'layers', 'units']
    for i_top, (N_meta_iter, constraint) in enumerate(zip(all_N_meta_iter, constraints)):
        transform = train_reg(transform, constraint, N_meta_iter, i_top)

    all_L2_regs = np.array(zip(*map(process_transform, all_transforms)))
    return all_L2_regs, all_tests_loss

def plot():
    import matplotlib.pyplot as plt
    mpl.rcParams['font.family'] = 'serif'
    mpl.rcParams['image.interpolation'] = 'none'
    with open('results.pkl') as f:
        all_L2_regs, all_tests_loss = pickle.load(f)

    fig = plt.figure(0)
    fig.clf()

    ax = fig.add_subplot(211)
    for L2_reg_curve in all_L2_regs:
        ax.plot(L2_reg_curve)
    ax.set_ylabel('L2 regularization')

    ax = fig.add_subplot(212)
    ax.plot(all_tests_loss)
    ax.set_ylabel('Test loss')
    ax.set_xlabel('Meta iterations')

    plt.savefig("reg_learning_curve.png")

if __name__ == '__main__':
    # results = run()
    # with open('results.pkl', 'rb') as f:
    #     results = pickle.load(f)
    # print('...')
    plot()
