import numpy as np
from mf_mdp.envs.MDP_env import MDPEnv
from mf_mdp.envs.mean_field_env import MeanFieldEnv
from utils import empirical_dist


class FinitePopMDPEnv(MDPEnv):
    def __init__(self, n_agents, mean_field_env: MeanFieldEnv, mean_field_policy):
        self.mean_field_env = mean_field_env
        self.mu = None
        super(FinitePopMDPEnv, self).__init__(self.mean_field_env.n_states, self.mean_field_env.n_actions,
                                              self.mean_field_env.Tf, self.mean_field_env.gamma)
        self.mu_0 = self.mean_field_env.mu0
        self.n_agents = n_agents
        self.mean_field_policy = mean_field_policy
        self._init_transitions()
        self.emp_dist_flow = self.compute_emp_dist_flow()
        self._init_reward_vec()

    def _init_transitions(self):
        self.T = [self.mean_field_env.T for _ in range(self.Tf)]

    def _init_reward_vec(self):
        reward_vec = [[] for _ in range(self.Tf + 1)]
        for t in range(self.Tf + 1):
            for s in range(self.n_states):
                reward_s = []
                for a in range(self.n_actions[s]):
                    reward_s.append(self._deviated_reward(s, a, t))
                reward_vec[t].append(reward_s)
        self.set_reward_vec(reward_vec)

    def _deviated_reward(self, s, a, t):
        r = 0
        emp_dist = self.emp_dist_flow[t]
        if emp_dist is None:
            return 0
        for case in emp_dist:
            n_list = case.n_list
            p = case.prob
            l = self._pair_wise_emp_dist(s, a, t, n_list)
            r += p * self.mean_field_env.theta(l, t)
        return r

    def _pair_wise_emp_dist(self, s, a, t, n_list):
        l = 0
        for state in range(self.n_states):
            if s != state:
                state_count = n_list[state]
            else:
                state_count = n_list[state] + 1

            state_fraction = state_count / self.n_agents

            l += self.mean_field_env.pairwise_reward(s, a, state, t) * state_fraction

        return l

    def compute_emp_dist_flow(self):
        emp_dist_flow = []
        mean_field_flow = self.compute_mean_field_flow()
        for t in range(len(mean_field_flow)):
            if self.mean_field_env.terminal_reward_only and t < self.mean_field_env.Tf:
                # If only terminal reward is assigned, no need to worry about non-terminal emp dist
                emp_dist_flow.append(None)
            else:
                mu_t = mean_field_flow[t]
                emp_dist_flow.append(empirical_dist(N=self.n_agents - 1, p=mu_t))
        print("Total {} nodes expanded for empirical distribution".format(len(emp_dist_flow[-1])))
        return emp_dist_flow

    def compute_mean_field_flow(self):
        mu = [self.mu_0]
        for t in range(self.Tf):
            pi_t = self.mean_field_policy[t]
            controlled_trans = self.mean_field_controlled_trans(pi_t, t)
            mu.append(np.matmul(mu[t], controlled_trans))
        self.mu = mu
        return mu

    def mean_field_controlled_trans(self, pi_t, t):
        T_c = np.zeros((self.n_states, self.n_states))
        for s in range(self.n_states):
            for a in range(self.n_actions[s]):
                T_c[s, :] += self.T[t][a][s] * pi_t[s][a]

        assert all(abs(np.sum(T_c, axis=1) - 1) < 1e-5)

        return T_c
