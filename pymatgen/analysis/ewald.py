#!/usr/bin/env python

"""
This module provides classes for calculating the ewald sum of a structure.
"""

from __future__ import division

__author__ = "Shyue Ping Ong, William Davidson Richard"
__copyright__ = "Copyright 2011, The Materials Project"
__credits__ = "Christopher Fischer"
__version__ = "1.0"
__maintainer__ = "Shyue Ping Ong"
__email__ = "shyue@mit.edu"
__status__ = "Production"
__date__ = "$Sep 23, 2011M$"

from math import pi, sqrt, log, exp, cos, sin, erfc, factorial
from datetime import datetime
from copy import deepcopy, copy
import bisect

import numpy as np

from pymatgen.core.physical_constants import ELECTRON_CHARGE, EPSILON_0
from pymatgen.core.structure import Structure


class EwaldSummation(object):
    """
    Calculates the electrostatic energy of a periodic array of charges using
    the Ewald technique.
    Ref: http://www.ee.duke.edu/~ayt/ewaldpaper/ewaldpaper.html

    This matrix can be used to do fast calculations of ewald sums after species
    removal.

    E = E_recip + E_real + E_point

    Atomic units used in the code, then converted to eV.
    """

    # Converts unit of q*q/r into eV
    CONV_FACT = 1e10 * ELECTRON_CHARGE / (4 * pi * EPSILON_0)

    def __init__(self, structure, real_space_cut=None, recip_space_cut=None,
                 eta=None, acc_factor=8.0):
        """
        Initializes and calculates the Ewald sum. Default convergence
        parameters have been specified, but you can override them if you wish.

        Args:
            structure:
                input structure that must have proper Specie on all sites, i.e.
                Element with oxidation state. Use OxidationStateDecorator in
                pymatgen.core.structure_modifier for example.
            real_space_cut:
                Real space cutoff radius dictating how many terms are used in
                the real space sum. Defaults to None, which means determine
                automagically using the formula given in gulp 3.1
                documentation.
            recip_space_cut:
                Reciprocal space cutoff radius. Defaults to None, which means
                determine automagically using the formula given in gulp 3.1
                documentation.
            eta:
                The screening parameter. Defaults to None, which means
                determine automatically.
            acc_factor:
                No. of significant figures each sum is converged to.
        """
        self._s = structure
        self._vol = structure.volume

        self._acc_factor = acc_factor

        # set screening length
        self._eta = eta if eta \
            else (len(structure) * 0.01 / self._vol) ** (1 / 3) * pi
        self._sqrt_eta = sqrt(self._eta)

        # acc factor used to automatically determine the optimal real and
        # reciprocal space cutoff radii
        self._accf = sqrt(log(10 ** acc_factor))

        self._rmax = real_space_cut if real_space_cut \
            else self._accf / self._sqrt_eta
        self._gmax = recip_space_cut if recip_space_cut \
            else 2 * self._sqrt_eta * self._accf

        """
        The next few lines pre-compute certain quantities and store them. Ewald
        summation is rather expensive, and these shortcuts are necessary to
        obtain several factors of improvement in speedup.
        """
        self._oxi_states = [compute_average_oxidation_state(site)
                            for site in structure]
        self._coords = np.array(self._s.cart_coords)
        self._forces = np.zeros((len(structure), 3))

        """
        Now we call the relevant private methods to calculate the reciprocal
        and real space terms.
        """
        (self._recip, recip_forces) = self._calc_recip()
        (self._real, self._point, real_point_forces) = \
            self._calc_real_and_point()
        self._forces = recip_forces + real_point_forces

    def compute_partial_energy(self, removed_indices):
        """
        Gives total ewald energy for certain sites being removed, i.e. zeroed
        out.
        """
        total_energy_matrix = self.total_energy_matrix.copy()
        for i in removed_indices:
            total_energy_matrix[i, :] = 0
            total_energy_matrix[:, i] = 0
        return sum(sum(total_energy_matrix))

    def compute_sub_structure(self, structure):
        """
        Gives total ewald energy for an sub structure in the same
        lattice. The sub structure must be a subset of the original
        structure, with possible different charges.
        """
        total_energy_matrix = self.total_energy_matrix.copy()

        def find_match(site):
            for test_site in structure:
                frac_diff = abs(np.array(site.frac_coords)
                                - np.array(test_site.frac_coords)) % 1
                frac_diff = [abs(a) < 1e-5 or abs(a) > 1 - 1e-5 \
                     for a in frac_diff]
                if all(frac_diff):
                    return test_site
            return None

        matches = []
        for i, site in enumerate(self._s):
            matching_site = find_match(site)
            if matching_site:
                new_charge = compute_average_oxidation_state(matching_site)
                old_charge = self._oxi_states[i]
                scaling_factor = new_charge / old_charge
                matches.append(matching_site)
            else:
                scaling_factor = 0
            total_energy_matrix[i, :] *= scaling_factor
            total_energy_matrix[:, i] *= scaling_factor

        if len(matches) != len(structure):
            print "Missing sites."
            print len(matches)
            print len(structure)
            print "unmatched = {}".format([site for site in structure
                                           if site not in matches])

        return sum(sum(total_energy_matrix))

    @property
    def reciprocal_space_energy(self):
        """
        The reciprocal space energy.
        """
        return sum(sum(self._recip))

    @property
    def reciprocal_space_energy_matrix(self):
        """
        The reciprocal space energy matrix. Each matrix element (i, j)
        corresponds to the interaction energy between site i and site j in
        reciprocal space.
        """
        return self._recip

    @property
    def real_space_energy(self):
        """
        The real space space energy.
        """
        return sum(sum(self._real))

    @property
    def real_space_energy_matrix(self):
        """
        The real space energy matrix. Each matrix element (i, j) corresponds to
        the interaction energy between site i and site j in real space.
        """
        return self._real

    @property
    def point_energy(self):
        """
        The point energy.
        """
        return sum(self._point)

    @property
    def point_energy_matrix(self):
        """
        The point space matrix. A diagonal matrix with the point terms for each
        site in the diagonal elements.
        """
        return self._point

    @property
    def total_energy(self):
        """
        The total energy.
        """
        return sum(sum(self._recip)) + sum(sum(self._real)) + sum(self._point)

    @property
    def total_energy_matrix(self):
        """
        The total energy matrix. Each matrix element (i, j) corresponds to the
        total interaction energy between site i and site j.
        """
        totalenergy = self._recip + self._real
        for i in range(len(self._point)):
            totalenergy[i, i] += self._point[i]
        return totalenergy

    @property
    def forces(self):
        """
        The forces on each site as a Nx3 matrix. Each row corresponds to a
        site.
        """
        return self._forces

    def _calc_recip(self):
        """
        Perform the reciprocal space summation. Calculates the quantity
        E_recip = 1/(2PiV) sum_{G < Gmax} exp(-(G.G/4/eta))/(G.G) S(G)S(-G)
        where
        S(G) = sum_{k=1,N} q_k exp(-i G.r_k)
        S(G)S(-G) = |S(G)|**2

        This method is heavily vectorized to utilize numpy's C backend for
        speed.
        """
        numsites = self._s.num_sites
        prefactor = 2 * pi / self._vol
        erecip = np.zeros((numsites, numsites))
        forces = np.zeros((numsites, 3))
        coords = self._coords
        recip = Structure(self._s.lattice.reciprocal_lattice, ["H"],
                          [np.array([0, 0, 0])])
        recip_nn = recip.get_neighbors(recip[0], self._gmax)

        for (n, dist) in recip_nn:
            gvect = n.coords
            gsquare = np.linalg.norm(gvect) ** 2

            expval = exp(-1.0 * gsquare / (4.0 * self._eta))

            gvect_tile = np.tile(gvect, (numsites, 1))
            gvectdot = np.sum(gvect_tile * coords, 1)
            #calculate the structure factor
            sfactor = np.zeros((numsites, numsites))
            sreal = 0.0
            simag = 0.0
            for i in xrange(numsites):
                qi = self._oxi_states[i]
                g_dot_i = gvectdot[i]
                sfactor[i, i] = qi * qi
                sreal += qi * cos(g_dot_i)
                simag += qi * sin(g_dot_i)

                for j in xrange(i + 1, numsites):
                    qj = self._oxi_states[j]
                    exparg = g_dot_i - gvectdot[j]
                    cosa = cos(exparg)
                    sina = sin(exparg)
                    sfactor[i, j] = qi * qj * (cosa + sina)
                    """
                    Uses the property that when site i and site j are switched,
                    exparg' == - exparg. This implies
                    cos (exparg') = cos (exparg) and
                    sin (exparg') = - sin (exparg)

                    Halves all computations.
                    """
                    sfactor[j, i] = qi * qj * (cosa - sina)

            erecip += expval / gsquare * sfactor
            pref = 2 * expval / gsquare * np.array(self._oxi_states)
            factor = prefactor * pref * \
                (sreal * np.sin(gvectdot)
                 - simag * np.cos(gvectdot)) * EwaldSummation.CONV_FACT
            forces += np.tile(factor, (3, 1)).transpose() * gvect_tile

        return (erecip * prefactor * EwaldSummation.CONV_FACT, forces)

    def _calc_real_and_point(self):
        """
        Determines the self energy -(eta/pi)**(1/2) * sum_{i=1}^{N} q_i**2

        If cell is charged a compensating background is added (i.e. a G=0 term)
        """
        all_nn = self._s.get_all_neighbors(self._rmax, True)

        forcepf = 2.0 * self._sqrt_eta / sqrt(pi)
        coords = self._coords
        numsites = self._s.num_sites
        ereal = np.zeros((numsites, numsites))
        epoint = np.zeros((numsites))
        forces = np.zeros((numsites, 3))
        for i in xrange(numsites):
            nn = all_nn[i]  # self._s.get_neighbors(site, self._rmax)
            qi = self._oxi_states[i]
            epoint[i] = qi * qi
            epoint[i] *= -1.0 * sqrt(self._eta / pi)
            # add jellium term
            epoint[i] += qi * pi / (2.0 * self._vol * self._eta)
            for j in range(len(nn)):
                nsite = nn[j][0]
                rij = nn[j][1]
                qj = compute_average_oxidation_state(nsite)
                erfcval = erfc(self._sqrt_eta * rij)
                ereal[nn[j][2], i] += erfcval * qi * qj / rij
                fijpf = qj / pow(rij, 3) * (erfcval + forcepf * rij *
                                            exp(-self._eta * pow(rij, 2)))
                forces[i] += fijpf * (coords[i] - nsite.coords) * \
                    qi * EwaldSummation.CONV_FACT

        ereal = ereal * 0.5 * EwaldSummation.CONV_FACT
        epoint = epoint * EwaldSummation.CONV_FACT
        return (ereal, epoint, forces)

    @property
    def eta(self):
        return self._eta

    def __str__(self):
        output = ["Real = " + str(self.real_space_energy)]
        output.append("Reciprocal = " + str(self.reciprocal_space_energy))
        output.append("Point = " + str(self.point_energy))
        output.append("Total = " + str(self.total_energy))
        output.append("Forces:\n" + str(self.forces))
        return "\n".join(output)


class EwaldMinimizer:
    '''
    This class determines the manipulations that will minimize an ewald matrix,
    given a list of possible manipulations. This class does not perform the
    manipulations on a structure, but will return the list of manipulations
    that should be done on one to produce the minimal structure. It returns the
    manipulations for the n lowest energy orderings. This class should be used
    to perform fractional species substitution or fractional species removal to
    produce a new structure. These manipulations create large numbers of
    candidate structures, and this class can be used to pick out those with the
    lowest ewald sum.

    An alternative (possibly more intuitive) interface to this class is the
    order disordered structure transformation.

    Author - Will Richards
    '''

    ALGO_FAST = 0
    ALGO_COMPLETE = 1
    ALGO_BEST_FIRST = 2

    '''
    ALGO_TIME_LIMIT: Slowly increases the speed (with the cost of decreasing
    accuracy) as the minimizer runs. Attempts to limit the run time to
    approximately 30 minutes.
    '''
    ALGO_TIME_LIMIT = 3

    def __init__(self, matrix, m_list, num_to_return=1, algo=ALGO_FAST):
        '''
        Args:
            matrix:
                a matrix of the ewald sum interaction energies. This is stored
                in the class as a diagonally symmetric array and so
                self._matrix will not be the same as the input matrix.
            m_list:
                list of manipulations. each item is of the form
                (multiplication fraction, number_of_indices, indices, species)
                These are sorted such that the first manipulation contains the
                most permutations. this is actually evaluated last in the
                recursion since I'm using pop.
            num_to_return:
                The minimizer will find the number_returned lowest energy
                structures. This is likely to return a number of duplicate
                structures so it may be necessary to overestimate and then
                remove the duplicates later. (duplicate checking in this
                process is extremely expensive)
        '''
        # Setup and checking of inputs
        self._matrix = copy(matrix)
        # Make the matrix diagonally symmetric (so matrix[i,:] == matrix[:,j])
        for i in range(len(self._matrix)):
            for j in range(i, len(self._matrix)):
                value = (self._matrix[i, j] + self._matrix[j, i]) / 2
                self._matrix[i, j] = value
                self._matrix[j, i] = value

        def comb(n, k):
            return factorial(n) / factorial(k) / factorial(n - k)

        # sort the m_list based on number of permutations
        self._m_list = sorted(m_list, key=lambda x: comb(len(x[2]), x[1]),
                              reverse=True)

        for mlist in self._m_list:
            if mlist[0] > 1:
                raise ValueError('multiplication fractions must be <= 1')
        self._current_minimum = float('inf')
        self._num_to_return = num_to_return
        self._algo = algo
        if algo == EwaldMinimizer.ALGO_COMPLETE:
            raise NotImplementedError('Complete algo not yet implemented for '
                                      'EwaldMinimizer')

        self._output_lists = []
        # Tag that the recurse function looks at at each level. If a method
        # sets this to true it breaks the recursion and stops the search.
        self._finished = False

        self._start_time = datetime.utcnow()

        self.minimize_matrix()

        self._best_m_list = self._output_lists[0][1]
        self._minimized_sum = self._output_lists[0][0]

    def minimize_matrix(self):
        '''
        This method finds and returns the permutations that produce the lowest
        ewald sum calls recursive function to iterate through permutations
        '''
        if self._algo == EwaldMinimizer.ALGO_FAST or \
            self._algo == EwaldMinimizer.ALGO_BEST_FIRST:
            return self._recurse(self._matrix, self._m_list,
                                 set(range(len(self._matrix))))

    def add_m_list(self, matrix_sum, m_list):
        '''
        This adds an m_list to the output_lists and updates the current
        minimum if the list is full.
        '''
        if self._output_lists is None:
            self._output_lists = [[matrix_sum, m_list]]
        else:
            bisect.insort(self._output_lists, [matrix_sum, m_list])
        if self._algo == EwaldMinimizer.ALGO_BEST_FIRST and \
            len(self._output_lists) == self._num_to_return:
            self._finished = True
        if len(self._output_lists) > self._num_to_return:
            self._output_lists.pop()
        if len(self._output_lists) == self._num_to_return:
            self._current_minimum = self._output_lists[-1][0]

    def best_case(self, matrix, m_list, indices_left):
        '''
        Computes a best case given a matrix and manipulation list.

        Args:
            matrix:
                the current matrix (with some permutations already performed
            m_list:
                [(multiplication fraction, number_of_indices, indices,
                species)] describing the manipulation
            indices:
                Set of indices which haven't had a permutation performed on
                them.
        '''

        m_indices = []
        fraction_list = []
        for m in m_list:
            m_indices.extend(m[2])
            fraction_list.extend([m[0]] * m[1])

        indices = list(indices_left.intersection(m_indices))

        interaction_matrix = matrix[indices, :][:, indices]

        fractions = np.zeros(len(interaction_matrix)) + 1
        fractions[:len(fraction_list)] = fraction_list
        fractions = np.sort(fractions)

        # Sum associated with each index (disregarding interactions between
        # indices)
        sums = 2 * np.sum(matrix[indices], axis=1)
        sums = np.sort(sums)

        # Interaction corrections. Can be reduced to (1-x)(1-y) for x,y in
        # fractions each element in a column gets multiplied by (1-x), and then
        # the sum of the columns gets multiplied by (1-y) since fractions are
        # less than 1, there is no effect of one choice on the other
        step1 = np.sort(interaction_matrix) * (1 - fractions)
        step2 = np.sort(np.sum(step1, axis=1))
        step3 = step2 * (1 - fractions)
        interaction_correction = np.sum(step3)

        if self._algo == self.ALGO_TIME_LIMIT:
            elapsed_time = datetime.utcnow() - self._start_time
            speedup_parameter = elapsed_time.total_seconds() / 1800
            avg_int = np.sum(interaction_matrix, axis=None)
            avg_frac = np.average(np.outer(1 - fractions, 1 - fractions))
            average_correction = avg_int * avg_frac

            interaction_correction = average_correction * speedup_parameter \
                + interaction_correction * (1 - speedup_parameter)

        best_case = np.sum(matrix) + np.inner(sums[::-1], fractions - 1) \
            + interaction_correction

        return best_case

    def get_next_index(self, matrix, manipulation, indices_left):
        """
        Returns an index that should have the most negative effect on the
        matrix sum
        """
        f = manipulation[0]
        indices = list(indices_left.intersection(manipulation[2]))
        sums = np.sum(matrix[indices], axis=1)
        if f < 1:
            next_index = indices[sums.argmax(axis=0)]
        else:
            next_index = indices[sums.argmin(axis=0)]

        return next_index

    def _recurse(self, matrix, m_list, indices, output_m_list=[]):
        '''
        This method recursively finds the minimal permutations using a binary
        tree search strategy.

        Args:
            matrix:
                The current matrix (with some permutations already performed
            m_list:
                The list of permutations still to be performed
            indices:
                Set of indices which haven't had a permutation performed on
                them.
        '''
        #check to see if we've found all the solutions that we need
        if self._finished:
            return

        #if we're done with the current manipulation, pop it off.
        while m_list[-1][1] == 0:
            m_list = copy(m_list)
            m_list.pop()
            #if there are no more manipulations left to do check the value
            if not m_list:
                matrix_sum = np.sum(matrix)
                if matrix_sum < self._current_minimum:
                    self.add_m_list(matrix_sum, output_m_list)
                return

        #if we wont have enough indices left, return
        if m_list[-1][1] > len(indices.intersection(m_list[-1][2])):
            return

        if len(m_list) == 1 or m_list[-1][1] > 1:
            if self.best_case(matrix, m_list, indices) > self._current_minimum:
                return

        index = self.get_next_index(matrix, m_list[-1], indices)

        m_list[-1][2].remove(index)

        # Make the matrix and new m_list where we do the manipulation to the
        # index that we just got
        matrix2 = np.copy(matrix)
        m_list2 = deepcopy(m_list)
        output_m_list2 = copy(output_m_list)

        matrix2[index, :] *= m_list[-1][0]
        matrix2[:, index] *= m_list[-1][0]
        output_m_list2.append([index, m_list[-1][3]])
        indices2 = copy(indices)
        indices2.remove(index)
        m_list2[-1][1] -= 1

        #recurse through both the modified and unmodified matrices

        self._recurse(matrix2, m_list2, indices2, output_m_list2)
        self._recurse(matrix, m_list, indices, output_m_list)

    @property
    def best_m_list(self):
        return self._best_m_list

    @property
    def minimized_sum(self):
        return self._minimized_sum

    @property
    def output_lists(self):
        return self._output_lists


def compute_average_oxidation_state(site):
    """
    Calculates the average oxidation state of a site

    Args:
        site:
            Site to compute average oxidation state

    Returns:
        Average oxidation state of site.
    """
    try:
        avg_oxi = sum([sp.oxi_state * occu
                       for sp, occu in site.species_and_occu.items()
                       if sp != None])
        return avg_oxi
    except:
        pass
    try:
        return site.charge
    except AttributeError:
        raise ValueError("Ewald summation can only be performed on structures "
                         "that are either oxidation state decorated or have "
                         "site charges.")