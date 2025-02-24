from copy import deepcopy
from collections import deque

import gym

from x_mushroom_rl.environments import Environment, MDPInfo
from x_mushroom_rl.utils.spaces import *
from x_mushroom_rl.utils.frames import LazyFrames, preprocess_frame
try:
    from atariari.benchmark.wrapper import AtariARIWrapper, atari_dict
    ATARI_ARI_INSTALLED = True
except ImportError:
    from termcolor import colored
    print(colored("AtariARI Not found, please install it:", "red"))
    print(colored("https://github.com/mila-iqia/atari-representation-learning:", "blue"))
    ATARI_ARI_INSTALLED = False

class MaxAndSkip(gym.Wrapper):
    def __init__(self, env, skip, max_pooling=True):
        gym.Wrapper.__init__(self, env)
        self._obs_buffer = np.zeros((2,) + env.observation_space.shape,
                                    dtype=np.uint8)
        self._skip = skip
        self._max_pooling = max_pooling

    def reset(self):
        return self.env.reset()

    def step(self, action):
        total_reward = 0.
        for i in range(self._skip):
            obs, reward, absorbing, info = self.env.step(action)
            if i == self._skip - 2:
                self._obs_buffer[0] = obs
            if i == self._skip - 1:
                self._obs_buffer[1] = obs
            total_reward += reward
            if absorbing:
                break
        if self._max_pooling:
            frame = self._obs_buffer.max(axis=0)
        else:
            frame = self._obs_buffer.mean(axis=0)

        return frame, total_reward, absorbing, info

    def reset(self, **kwargs):
        return self.env.reset(**kwargs)


class Atari(Environment):
    """
    The Atari environment as presented in:
    "Human-level control through deep reinforcement learning". Mnih et. al..
    2015.

    """
    def __init__(self, name, width=84, height=84, ends_at_life=False,
                 max_pooling=True, history_length=4, max_no_op_actions=30):
        """
        Constructor.

        Args:
            name (str): id name of the Atari game in Gym;
            width (int, 84): width of the screen;
            height (int, 84): height of the screen;
            ends_at_life (bool, False): whether the episode ends when a life is
               lost or not;
            max_pooling (bool, True): whether to do max-pooling or
                average-pooling of the last two frames when using NoFrameskip;
            history_length (int, 4): number of frames to form a state;
            max_no_op_actions (int, 30): maximum number of no-op action to
                execute at the beginning of an episode.

        """
        # MPD creation
        if 'NoFrameskip' in name:
            self.env = MaxAndSkip(gym.make(name), history_length, max_pooling)
            self.augmented = False
        elif '-Augmented' in name and ATARI_ARI_INSTALLED:
            name = name.replace('-Augmented', '')
            if name.lower()[:4] in [name.lower()[:4] for name in atari_dict.keys()]:
                self.env = AtariARIWrapper(gym.make(name))
            else:
                self.env = gym.make(name)
            self.augmented = True
        else:
            self.env = gym.make(name)
            self.augmented = False

        if width is None and height is None:
            self.grey_and_rescale = False
            self._img_size = None
            observation_space = Box(
                low=0., high=255., shape=(history_length, 216, 160, 3))
        # MDP parameters
        else:
            self.grey_and_rescale = True
            self._img_size = (width, height)
            observation_space = Box(
                low=0., high=255., shape=(history_length, self._img_size[1], self._img_size[0]))
        self._episode_ends_at_life = ends_at_life
        self._max_lives = self.env.unwrapped.ale.lives()
        self._lives = self._max_lives
        self._force_fire = None
        self._real_reset = True
        self._max_no_op_actions = max_no_op_actions
        self._history_length = history_length
        self._current_no_op = None
        self.action_space = self.env.action_space

        assert self.env.unwrapped.get_action_meanings()[0] == 'NOOP'

        # MDP properties
        action_space = Discrete(self.env.action_space.n)
        horizon = np.inf  # the gym time limit is used.
        gamma = .99
        mdp_info = MDPInfo(observation_space, action_space, gamma, horizon)

        super().__init__(mdp_info)

    def reset(self, state=None):
        if self._real_reset:
            self._state = preprocess_frame(self.env.reset(), self._img_size,
                                           self.grey_and_rescale)
            self._state = deque([deepcopy(
                self._state) for _ in range(self._history_length)],
                maxlen=self._history_length
            )
            self._lives = self._max_lives

        self._force_fire = self.env.unwrapped.get_action_meanings()[1] == 'FIRE'

        self._current_no_op = np.random.randint(self._max_no_op_actions + 1)

        return LazyFrames(list(self._state), self._history_length)

    def step(self, action):
        # Force FIRE action to start episodes in games with lives
        if self._force_fire:
            obs, _, _, _ = self.env.env.step(1)
            self._force_fire = False
        while self._current_no_op > 0:
            obs, _, _, _ = self.env.env.step(0)
            self._current_no_op -= 1

        obs, reward, absorbing, info = self.env.step(action)
        self._real_reset = absorbing
        if info['ale.lives'] != self._lives:
            if self._episode_ends_at_life:
                absorbing = True
            self._lives = info['ale.lives']
            self._force_fire = self.env.unwrapped.get_action_meanings()[
                1] == 'FIRE'

        self._state.append(preprocess_frame(obs, self._img_size,
                                            self.grey_and_rescale))
        if self.augmented:
            return LazyFrames(list(self._state),
                              self._history_length), reward, absorbing, info, obs
        return LazyFrames(list(self._state),
                          self._history_length), reward, absorbing, info

    def render(self, mode='human'):
        return self.env.render(mode=mode)

    def stop(self):
        self.env.close()
        self._real_reset = True

    def set_episode_end(self, ends_at_life):
        """
        Setter.

        Args:
            ends_at_life (bool): whether the episode ends when a life is
                lost or not.

        """
        self._episode_ends_at_life = ends_at_life
