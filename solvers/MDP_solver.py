import numpy as np
from envs.base_env import MeanFieldEnv


class MDP_Solver:
    def __init__(self, env: MeanFieldEnv, n_ittr=20, eps=0.01):
        self.env = env
        self.n_ittr = n_ittr
        self.eps = eps
        self.Tf = self.env.Tf
        self.V = [np.zeros(self.env.n_states) for _ in range(self.Tf + 1)]  # Value Function
        self.V_ = [np.zeros(self.env.n_states) for _ in range(self.Tf + 1)]  # Temp storage
        self.policy = [[np.zeros(self.env.n_actions[s]) for s in range(self.env.n_states)] for _ in range(self.Tf + 1)]

    def solve(self, nu):
        diff = 1
        for _ in range(self.n_ittr):  # TODO:Check if need to iterate. Finite Horizon probably not.
            if diff < self.eps:
                break

            self._resetTemp()
            for t in reversed(range(self.env.Tf + 1)):
                nu_t = nu[t]

                for s in range(self.env.n_states):
                    if t == self.env.Tf:  # terminal time step
                        Q_s = np.zeros(self.env.n_actions[s])
                        for a in range(self.env.n_actions[s]):
                            Q_s[a] = self.env.individual_reward(s_t=s, a_t=a, nu_t=nu_t, t=t)
                    else:
                        Q_s = self.computeQs(s, t, nu_t)

                    self.V_[t][s] = max(Q_s)
                    a_max = np.argmax(Q_s)
                    self.policy[t][s][a_max] = 1

            diff = sum(sum(abs(self.V[t] - self.V_[t])) for t in range(self.Tf + 1))
            self._updateNew()

        return self.policy

    def computeQs(self, s, t, nu_t):
        n_actions = self.env.n_actions[s]
        Q_s = np.zeros(n_actions)
        V_next = self.V_[t + 1]
        for a in range(n_actions):
            Q_s[a] += self.env.individual_reward(s_t=s, nu_t=nu_t, t=t, a_t=a)
            T_sa = self.env.T[a][s]
            assert len(T_sa) > 0
            for s_prime in range(self.env.n_states):
                Q_s[a] += self.env.gamma * T_sa[s_prime] * V_next[s_prime]
        return Q_s

    def _resetTemp(self):
        self.V_ = [np.zeros(self.env.n_states) for _ in range(self.Tf + 1)]
        self.policy = [[np.zeros(self.env.n_actions[s]) for s in range(self.env.n_states)] for _ in range(self.Tf + 1)]

    def _updateNew(self):
        self.V = np.copy(self.V_)