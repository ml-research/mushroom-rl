import numpy as np

from x_mushroom_rl.core import Core, Logger
from x_mushroom_rl.environments.segway import Segway
from x_mushroom_rl.algorithms.policy_search import *
from x_mushroom_rl.policy import DeterministicPolicy
from x_mushroom_rl.distributions import GaussianDiagonalDistribution
from x_mushroom_rl.approximators import Regressor
from x_mushroom_rl.approximators.parametric import LinearApproximator
from x_mushroom_rl.utils.dataset import compute_J
from x_mushroom_rl.utils.callbacks import CollectDataset
from x_mushroom_rl.utils.optimizers import AdaptiveOptimizer

from tqdm import tqdm, trange
tqdm.monitor_interval = 0


def experiment(alg, params, n_epochs, n_episodes, n_ep_per_fit):
    np.random.seed()

    logger = Logger(alg.__name__, results_dir=None)
    logger.strong_line()
    logger.info('Experiment Algorithm: ' + alg.__name__)

    # MDP
    mdp = Segway()

    # Policy
    approximator = Regressor(LinearApproximator,
                             input_shape=mdp.info.observation_space.shape,
                             output_shape=mdp.info.action_space.shape)

    n_weights = approximator.weights_size
    mu = np.zeros(n_weights)
    sigma = 2e-0 * np.ones(n_weights)
    policy = DeterministicPolicy(approximator)
    dist = GaussianDiagonalDistribution(mu, sigma)

    agent = alg(mdp.info, dist, policy, **params)

    # Train
    dataset_callback = CollectDataset()
    core = Core(agent, mdp, callbacks_fit=[dataset_callback])

    for i in trange(n_epochs, leave=False):
        core.learn(n_episodes=n_episodes,
                   n_episodes_per_fit=n_ep_per_fit, render=False)
        J = compute_J(dataset_callback.get(), gamma=mdp.info.gamma)
        dataset_callback.clean()

        p = dist.get_parameters()

        logger.epoch_info(i+1, J=np.mean(J), mu=p[:n_weights], sigma=p[n_weights:])

    logger.info('Press a button to visualize the segway...')
    input()
    core.evaluate(n_episodes=3, render=True)


if __name__ == '__main__':
    algs_params = [
        (REPS, {'eps': 0.05}),
        (RWR, {'beta': 0.01}),
        (PGPE, {'optimizer':  AdaptiveOptimizer(eps=0.3)}),
        ]
    for alg, params in algs_params:
        experiment(alg, params, n_epochs=20, n_episodes=100, n_ep_per_fit=25)
