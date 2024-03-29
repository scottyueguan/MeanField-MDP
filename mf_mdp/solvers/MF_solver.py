import numpy as np
from mf_mdp.solvers.MDP_solver import MDP_Solver
from mf_mdp.envs.mean_field_env import MeanFieldEnv
from mf_mdp.envs.MDP_env import MDPEnv
import copy
import pickle as pkl


class MF_Solver:
    def __init__(self, env: MeanFieldEnv, n_ittr=50, eps=0.01):
        self.mean_field_env = env
        self.n_ittr = n_ittr
        self.eps = eps
        self.soln = None
        np.random.seed(0)

    def solve(self, time_averaged=False, eta=None, entropy_regularized=False, prior=None, beta=None):

        if entropy_regularized:
            assert beta is not None
        if time_averaged:
            assert eta is not None
        if time_averaged and entropy_regularized:
            print("Both time averaged and entropy regularized!")

        diff1, diff2 = 1, 1

        # randomly initialize policy
        policy = self._init_policy()
        value = None

        # initialize mean field
        nu = [np.zeros(self.mean_field_env.dim_nu) for _ in range(self.mean_field_env.Tf + 1)]
        mu = [np.zeros(self.mean_field_env.n_states) for _ in range(self.mean_field_env.Tf + 1)]
        mdp_env = None

        for ittr in range(self.n_ittr):
            if diff1 < self.eps or diff2 < self.eps:
                break
            nu_, mu_ = self.propagate_mean_field(policy)  # propagate mean field

            mdp_env = self._generate_MDP_env(nu_)

            mdp_solver = MDP_Solver(env=mdp_env)

            if entropy_regularized:
                policy_, value_ = mdp_solver.solve_entropy(prior=prior, beta=beta)
            else:
                policy_, value_ = mdp_solver.solve()

            diff1 = sum(sum(abs(nu_[t] - nu[t])) for t in range(self.mean_field_env.Tf + 1))
            diff2 = sum(sum(abs(mu_[t] - mu[t])) for t in range(self.mean_field_env.Tf + 1))

            if not time_averaged:
                nu = copy.deepcopy(nu_)
                mu = copy.deepcopy(mu_)
                policy = copy.deepcopy(policy_)
                value = copy.deepcopy(value_)
            else:
                # perform a soft update
                nu = self._soft_update(x_old=nu, x_new=nu_, eta=eta)
                mu = self._soft_update(x_old=mu, x_new=mu_, eta=eta)
                # nu = copy.deepcopy(nu_)
                # mu = copy.deepcopy(mu_)
                policy = self._soft_update_policy(policy_old=policy, policy_new=policy_, eta=eta)
                value = self._soft_update(x_old=value, x_new=value_, eta=eta)

            print("Difference in mu is {}".format(diff2))

        self.soln = {"policy": policy, "value": value, "mu": mu, "nu": nu, "MDP_induced": mdp_env,
                     "mfg_env": self.mean_field_env}

    def propagate_mean_field(self, policy):
        mu = [np.zeros(self.mean_field_env.n_states) for _ in range(self.mean_field_env.Tf + 1)]
        mu[0] = self.mean_field_env.mu0

        nu = [np.zeros(self.mean_field_env.dim_nu) for _ in range(self.mean_field_env.Tf + 1)]
        nu[0] = self.mu2nu(mu_t=mu[0], pi_t=policy[0])

        for t in range(0, self.mean_field_env.Tf):
            mu_t = mu[t]
            T_c = self.controlled_trans(pi_t=policy[t], mu_t=mu_t)
            mu_next = np.matmul(mu_t, T_c)
            mu[t + 1] = mu_next

            nu_next = self.mu2nu(mu_t=mu_next, pi_t=policy[t + 1])
            nu[t + 1] = nu_next

        return nu, mu

    def mu2nu(self, mu_t, pi_t):
        '''
        Compute state action mean field from state mean field given a policy at time t
        :param mu_t: state mean field at t
        :param pi_t: policy at time t
        :return:
        '''
        nu_t = np.zeros(self.mean_field_env.dim_nu)
        pointer = 0
        for s in range(self.mean_field_env.n_states):
            for a in range(self.mean_field_env.n_actions[s]):
                nu_t[pointer] = mu_t[s] * pi_t[s][a]
                pointer += 1

        assert pointer == self.mean_field_env.dim_nu
        return nu_t

    def controlled_trans(self, pi_t, mu_t=None):
        T_c = np.zeros((self.mean_field_env.n_states, self.mean_field_env.n_states))
        for s in range(self.mean_field_env.n_states):
            for a in range(self.mean_field_env.n_actions[s]):
                T_c[s, :] += self.mean_field_env.get_transition(s, a, mu_t) * pi_t[s][a]

        assert all(abs(np.sum(T_c, axis=1) - 1) < 1e-5)

        return T_c

    def _init_policy(self):
        policy = []
        for t in range(self.mean_field_env.Tf + 1):
            policy_t = []
            for s in range(self.mean_field_env.n_states):
                tmp = np.random.random(self.mean_field_env.n_actions[s])
                tmp = tmp / sum(tmp)
                policy_t.append(list(tmp))
            policy.append(policy_t)
        return policy

    def _generate_MDP_env(self, nu):
        n_actions = max(self.mean_field_env.n_actions)

        reward_vec = [[] for t in range(self.mean_field_env.Tf + 1)]
        transitions = [[np.zeros((self.mean_field_env.n_states, self.mean_field_env.n_states))
                        for a in range(max(self.mean_field_env.n_actions))]
                       for t in range(self.mean_field_env.Tf + 1)]

        for t in range(self.mean_field_env.Tf + 1):
            mu_t = self.mean_field_env.nu2mu(nu_vec=nu[t])
            for s in range(self.mean_field_env.n_states):
                reward_s = []
                for a in range(self.mean_field_env.n_actions[s]):
                    reward_s.append(self.mean_field_env.individual_reward(s_t=s, a_t=a, nu_t=nu[t], t=t))
                    transitions[t][a][s, :] = self.mean_field_env.get_transition(s, a, mu=mu_t)

                reward_vec[t].append(reward_s)

        mdp_env = MDPEnv(n_states=self.mean_field_env.n_states, n_actions=self.mean_field_env.n_actions,
                         Tf=self.mean_field_env.Tf, gamma=self.mean_field_env.gamma)

        mdp_env.set_reward_vec(reward_vec)
        mdp_env.set_transitions(transitions)

        return mdp_env

    @staticmethod
    def _soft_update(x_old, x_new, eta):
        if x_old is None:
            return x_new
        x_ = (1 - eta) * np.array(x_old) + eta * np.array(x_new)
        return x_

    @staticmethod
    def _soft_update_policy(policy_old, policy_new, eta):
        if policy_old is None:
            return policy_new
        T, N = len(policy_old), len(policy_old[0])
        policy_ = [[list((1 - eta) * np.array(policy_old[t][s]) + eta * np.array(policy_new[t][s])) for s in range(N)]
                   for t in range(T)]
        return policy_

    def save(self, save_file_dir):
        with open(save_file_dir, "wb") as f:
            pkl.dump(self.soln, f)

    def load(self, save_file_dir):
        with open(save_file_dir, "rb") as f:
            self.soln = pkl.load(f)

        return self.soln
