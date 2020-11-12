'''
PathwayGenie (c) GeneGenie Bioinformatics Ltd. 2018

PathwayGenie is licensed under the MIT License.

To view a copy of this license, visit <http://opensource.org/licenses/MIT/>.

@author:  neilswainston
'''
# pylint: disable=too-many-arguments
# pylint: disable=too-many-branches
# pylint: disable=too-many-locals
# pylint: disable=too-many-statements
# pylint: disable=wrong-import-order
import math
import random
import re

from Bio.Seq import Seq
from synbiochem.utils import seq_utils

from parts_genie.nucl_acid_utils import NuclAcidCalcRunner


_START_CODON_PATT = r'(?=([ACGT]TG))'
_RT_EFF = 2.222
_K = 2500.0

_START_CODON_ENERGIES = {'ATG': -1.194, 'GTG': -0.0748, 'TTG': -0.0435,
                         'CTG': -0.03406}

_MEAN_SYART_CODON_ENERGY = \
    sum(_START_CODON_ENERGIES.values()) / len(_START_CODON_ENERGIES)


class RbsCalculator():
    '''Class for calculating RBS.'''

    def __init__(self, r_rna, calc, temp=37.0):
        self.__r_rna = r_rna.upper()
        self.__runner = NuclAcidCalcRunner(calc, temp)
        self.__optimal_spacing = 5
        self.__cutoff = 35

    def calc_dgs(self, m_rna, cds_start=float('NaN'), limit=float('inf')):
        ''''Calculates each dg term in the free energy model and sums them to
        create dg_total.'''
        m_rna = m_rna.upper()

        start_positions = []
        dgs_tirs = []
        count = 0

        # Ensure CDS start position is added (not all CDS start with a
        # _START_CODON_PATT):
        all_start_pos = {match.start()
                         for match in re.finditer(_START_CODON_PATT, m_rna)}

        if math.isfinite(cds_start):
            all_start_pos.add(cds_start)

        for start_pos in all_start_pos:
            try:
                d_g = self.__calc_dg(m_rna, start_pos)

                if not math.isinf(d_g):
                    start_positions.append(start_pos)
                    dgs_tirs.append((d_g, get_tir(d_g)))
                    count += 1
            except ValueError:
                # Occurs when start codon appears at start of sequence, and is
                # therefore leaderless. Take no action, as safe to ignore.
                continue

            if count == limit:
                break

        return dict(zip(start_positions, dgs_tirs))

    def calc_kinetic_score(self, m_rna, start_pos, dangles='none'):
        '''Gets kinetic score.'''
        sub_m_rna = \
            m_rna[max(0, start_pos - self.__cutoff):min(len(m_rna),
                                                        start_pos +
                                                        self.__cutoff)]

        _, bp_xs, bp_ys = self.__runner.mfe([sub_m_rna], dangles=dangles)

        largest_range_helix = 0

        for (nt_x, nt_y) in zip(bp_xs[0], bp_ys[0]):
            if nt_x <= len(sub_m_rna) and nt_y <= len(sub_m_rna):
                val = nt_y - nt_x
                largest_range_helix = max(val, largest_range_helix)

        return float(largest_range_helix) / float(len(sub_m_rna))

    def get_initial_rbs(self, rbs_len, cds, tir_target_rel):
        '''Generates random initial condition for designing a synthetic rbs
        sequence.'''
        dg_target_rel = get_dg(tir_target_rel)
        cds = cds.upper()

        dg_range_high = 25.0
        dg_range_low = -18.0

        dg_target_rel = (dg_target_rel - dg_range_high) / \
            (dg_range_low - dg_range_high)
        # 0.0: Low expression
        # 1.0: High expression

        if dg_target_rel < 0.125:
            prob_shine_delgano = 0.50
            core_length = 4
            max_nonoptimal_spacing = 10
        elif dg_target_rel < 0.250:
            prob_shine_delgano = 0.50
            core_length = 4
            max_nonoptimal_spacing = 10
        elif dg_target_rel < 0.5:
            prob_shine_delgano = 0.75
            core_length = 4
            max_nonoptimal_spacing = 10
        elif dg_target_rel < 0.7:
            prob_shine_delgano = 0.75
            core_length = 4
            max_nonoptimal_spacing = 5
        elif dg_target_rel < 0.8:
            prob_shine_delgano = 0.75
            core_length = 6
            max_nonoptimal_spacing = 5
        elif dg_target_rel < 0.9:
            prob_shine_delgano = 0.90
            core_length = 6
            max_nonoptimal_spacing = 5
        elif dg_target_rel < 0.95:
            prob_shine_delgano = 0.90
            core_length = 8
            max_nonoptimal_spacing = 3
        else:
            prob_shine_delgano = 1.0
            core_length = 9
            max_nonoptimal_spacing = 2

        shine_delgano = Seq(self.__r_rna).reverse_complement()

        return self.__get_random_rbs(rbs_len, shine_delgano,
                                     prob_shine_delgano, core_length,
                                     max_nonoptimal_spacing)

    def __calc_dg(self, m_rna, start_pos):
        '''Calculates dG.'''
        # Set dangles based on length between 5' end of m_rna and start codon:
        max_rbs_len = 35

        if start_pos > max_rbs_len:
            dangles = 'none'
        else:
            dangles = 'all'

        # Start codon energy:

        dg_start = _START_CODON_ENERGIES.get(m_rna[start_pos:start_pos + 3],
                                             _MEAN_SYART_CODON_ENERGY)

        # Energy of m_rna folding:
        [dg_m_rna, _, _] = \
            self.__calc_dg_m_rna(m_rna, start_pos, dangles)

        # Energy of m_rna:r_rna hybridization and folding:
        [dg_m_rna_r_rna, m_rna_subseq, bp_x, bp_y, energy_before] = \
            self.__calc_dg_m_rna_r_rna(m_rna, start_pos, dangles)

        # Standby site correction:
        dg_standby = self.__calc_dg_standby_site(m_rna_subseq, bp_x,
                                                 bp_y, energy_before,
                                                 dangles)

        # Total energy is m_rna:r_rna + start - r_rna - m_rna - standby_site:
        return dg_m_rna_r_rna + dg_start - dg_m_rna - dg_standby

    def __calc_dg_m_rna(self, m_rna, start_pos, dangles='all'):
        '''Calculates the dg_m_rna given the m_rna sequence.'''

        m_rna_subseq = \
            m_rna[max(0, start_pos - self.__cutoff):min(len(m_rna),
                                                        start_pos +
                                                        self.__cutoff)]

        energies, bp_xs, bp_ys = self.__runner.mfe([m_rna_subseq],
                                                   dangles=dangles)
        return energies[0], bp_xs[0], bp_ys[0]

    def __calc_dg_m_rna_r_rna(self, m_rna, start_pos, dangles):
        '''Calculates the dg_m_rna_r_rna from the m_rna and r_rna sequence.
        Considers all feasible 16S r_rna binding sites and includes the effects
        of non-optimal spacing.'''
        energy_cutoff = 3.0

        # Footprint of the 30S complex that prevents formation of secondary
        # structures downstream of the start codon. Here, we assume that the
        # entire post-start RNA sequence does not form secondary structures
        # once the 30S complex has bound.
        footprint = 1000

        begin = max(0, start_pos - self.__cutoff)
        m_rna_len = min(len(m_rna), start_pos + self.__cutoff)
        start_pos_in_subsequence = min(start_pos, self.__cutoff)
        startpos_to_end_len = m_rna_len - start_pos_in_subsequence - begin

        # 1. identify a list of r_rna-binding sites. Binding sites are
        # hybridizations between the m_rna and r_rna and can include
        # mismatches, bulges, etc. Intra-molecular folding is also allowed
        # within the m_rna.
        # The subopt program is used to generate a list of optimal & suboptimal
        # binding sites.
        # Constraints: the entire r_rna-binding site must be upstream of the
        # start codon
        m_rna_subseq = m_rna[begin:start_pos]

        if not m_rna_subseq:
            raise ValueError('Warning: There is a leaderless start codon, ' +
                             'which is being ignored.')

        energies, bp_xs, bp_ys = self.__runner.subopt([m_rna_subseq,
                                                       self.__r_rna],
                                                      energy_cutoff,
                                                      dangles=dangles)

        if not bp_xs:
            raise ValueError(
                'Warning: The 16S r_rna has no predicted binding site. ' +
                'Start codon is considered as leaderless and ignored.')

        # 2. Calculate dg_spacing for each 16S r_rna binding site

        # Calculate the aligned spacing for each binding site in the list
        aligned_spacing = []
        for (bp_x, bp_y) in zip(bp_xs,
                                bp_ys):
            aligned_spacing.append(
                self.__calc_aligned_spacing(m_rna_subseq,
                                            start_pos_in_subsequence,
                                            bp_x, bp_y))

        dg_spacing_list = []
        dg_m_rna_r_rna = []
        dg_m_rna_r_rna_spacing = []

        # Calculate dg_spacing using aligned spacing value. Add it to
        # dg_m_rna_r_rna.
        for counter in range(len(bp_xs)):
            dg_m_rna_r_rna.append(energies[counter])
            val = self.__calc_dg_spacing(aligned_spacing[counter])
            dg_spacing_list.append(val)
            dg_m_rna_r_rna_spacing.append(
                val + energies[counter])

        # 3. Find 16S r_rna binding site that minimizes
        # dg_spacing+dg_m_rna_r_rna.
        index = dg_m_rna_r_rna_spacing.index(min(dg_m_rna_r_rna_spacing))
        dg_spacing_final = dg_spacing_list[index]

        # Check: Is the dg spacing large compared to the energy gap? If so,
        # this means the list of suboptimal 16S r_rna binding sites generated
        # by subopt is too short.
        # if dg_spacing_final > energy_cutoff:
        # print 'Warning: The spacing penalty is greater than the ' + \
        #    'energy gap. dg (spacing) = ', dg_spacing_final

        # 4. Identify the 5' and 3' ends of the identified 16S r_rna binding
        # site. Create a base pair list.

        most_5p_m_rna = float('inf')
        most_3p_m_rna = -float('inf')

        # Generate a list of r_rna-m_rna base paired nucleotides
        bp_x_target = []
        bp_y_target = []

        bp_x = bp_xs[index]
        bp_y = bp_ys[index]
        for (nt_x, nt_y) in zip(bp_x, bp_y):
            if nt_y > len(m_rna_subseq):  # nt is r_rna
                most_5p_m_rna = min(most_5p_m_rna, bp_x[bp_y.index(nt_y)])
                most_3p_m_rna = max(most_3p_m_rna, bp_x[bp_y.index(nt_y)])
                bp_x_target.append(nt_x)
                bp_y_target.append(nt_y)

        if most_5p_m_rna == float('inf'):
            raise ValueError(
                'Warning: The 16S r_rna has no predicted binding site. ' +
                'Start codon is considered as leaderless and ignored.')

        # The r_rna-binding site is between the nucleotides at positions
        # most_5p_m_rna and most_3p_m_rna
        # Now, fold the pre-sequence, r_rna-binding-sequence and post-sequence
        # separately. Take their base pairings and combine them together.
        # Calculate the total energy. For secondary structures, this splitting
        # operation is allowed.

        # We postulate that not all of the post-sequence can form secondary
        # structures. Once the 30S complex binds to the m_rna, it prevents the
        # formation of secondary structures that are mutually exclusive with
        # ribosome binding. We define self.footprint to be the length of the
        # 30S complex footprint. Here, we assume that the entire m_rna sequence
        # downstream of the 16S r_rna binding site can not form secondary
        # structures.

        m_rna_pre = m_rna[begin:begin + most_5p_m_rna - 1]
        post_window_end = m_rna_len + 1
        post_window_begin = min(
            start_pos + footprint, post_window_end)  # Footprint
        post_window_end = m_rna_len + 1
        m_rna_post = m_rna[post_window_begin:post_window_end]

        total_bp_x = []
        total_bp_y = []

        # Calculate pre-sequence folding
        if m_rna_pre:
            _, bp_xs, bp_ys = self.__runner.mfe([m_rna_pre], dangles=dangles)
            bp_x_pre = bp_xs[0]
            bp_y_pre = bp_ys[0]

        else:
            bp_x_pre = []
            bp_y_pre = []

        # Add pre-sequence base pairings to total base pairings
        offset = 0  # Begins at 0
        for (nt_x, nt_y) in zip(bp_x_pre, bp_y_pre):
            total_bp_x.append(nt_x + offset)
            total_bp_y.append(nt_y + offset)

        # Add r_rna-binding site base pairings to total base pairings
        offset = 0  # Begins at zero
        if startpos_to_end_len < self.__cutoff:
            r_rna_offset = startpos_to_end_len
        else:
            r_rna_offset = startpos_to_end_len

        for (nt_x, nt_y) in zip(bp_x_target, bp_y_target):
            total_bp_x.append(nt_x + offset)
            total_bp_y.append(nt_y + r_rna_offset)

        # Calculate post-sequence folding
        if m_rna_post:
            _, bp_xs, bp_ys = self.__runner.mfe([m_rna_post], dangles=dangles)
            bp_x_post = bp_xs[0]
            bp_y_post = bp_ys[0]
        else:
            bp_x_post = []
            bp_y_post = []

        offset = post_window_begin - begin
        for (nt_x, nt_y) in zip(bp_x_post, bp_y_post):
            total_bp_x.append(nt_x + offset)
            total_bp_y.append(nt_y + offset)

        m_rna_subseq = m_rna[begin:m_rna_len]

        total_energy = self.__runner.energy([m_rna_subseq, self.__r_rna],
                                            total_bp_x, total_bp_y,
                                            dangles=dangles)

        total_energy_withspacing = total_energy + dg_spacing_final

        return (total_energy_withspacing, m_rna_subseq, total_bp_x, total_bp_y,
                total_energy)

    def __calc_dg_spacing(self, aligned_spacing):
        '''Calculates the dG_spacing according to the value of the aligned
        spacing. This relationship was determined through experiments.'''
        d_s = aligned_spacing - self.__optimal_spacing

        if aligned_spacing < self.__optimal_spacing:
            dg_spacing_penalty = 12.2 / \
                (1.0 + math.exp(2.5 * (d_s + 2.0))) ** 3.0
        else:
            dg_spacing_penalty = 0.048 * d_s * d_s + 0.24 * d_s

        return dg_spacing_penalty

    def __calc_dg_standby_site(self, m_rna, bp_x, bp_y, energy_before,
                               dangles):
        '''Calculates the dg of standby given the structure of the m_rna:r_rna
        complex.'''

        # To calculate the mfe structure while disallowing base pairing at the
        # standby site, we split the folded m_rna sequence into three parts:
        # (i) a pre-sequence (before the standby site) that can fold; (ii) the
        # standby site, which can not fold; (iii) the 16S r_rna binding site
        # and downstream sequence, which has been previously folded.
        standby_site_length = 4

        # Identify the most 5p m_rna nt that is bound to r_rna
        for (nt_x, nt_y) in zip(bp_x, bp_y):
                # nt_x is m_rna, nt_y is r_rna, they are bound.
            if nt_x <= len(m_rna) and nt_y > len(m_rna):
                most_5p_m_rna = nt_x  # starts counting from 0
                break

        # Extract the base pairings that are 3' of the most_5p_m_rna base
        # pairing
        bp_x_3p = []
        bp_y_3p = []
        for (nt_x, nt_y) in zip(bp_x, bp_y):
            if nt_x >= most_5p_m_rna:
                bp_x_3p.append(nt_x)
                bp_y_3p.append(nt_y)

        # Create the m_rna subsequence
        m_rna_subsequence = m_rna[
            0:max(0, most_5p_m_rna - standby_site_length - 1)]

        # Fold it and extract the base pairings
        if m_rna_subsequence:
            _, bp_xs, bp_ys = self.__runner.mfe(
                [m_rna_subsequence], dangles=dangles)
            bp_x_5p = bp_xs[0]  # [0] added 12/13/07
            bp_y_5p = bp_ys[0]
        else:
            bp_x_5p = []
            bp_y_5p = []

        # Put the sets of base pairings together
        bp_x_after = []
        bp_y_after = []

        for (nt_x, nt_y) in zip(bp_x_5p, bp_y_5p):
            bp_x_after.append(nt_x)
            bp_y_after.append(nt_y)

        for (nt_x, nt_y) in zip(bp_x_3p, bp_y_3p):
            bp_x_after.append(nt_x)
            bp_y_after.append(nt_y)

        # Calculate its energy
        energy_after = self.__runner.energy([m_rna, self.__r_rna],
                                            bp_x_after, bp_y_after,
                                            dangles=dangles)

        d_g = energy_before - energy_after

        if d_g > 0.0:
            d_g = 0.0

        return d_g

    def __get_random_rbs(self, rbs_len, shine_delgano, prob_shine_delgano,
                         core_length, max_nonoptimal_spacing):
        '''Generates a random rbs sequence tailored towards the target
        translation  initiation rate.'''
        rbs = []

        # Choose core_length nucleotides.
        # Choose from the SD sequence with probability prob_shine_delgano
        # Choose from non-SD sequence with probability
        # (1 - prob_shine_delgano) / 3
        # The beginning/end of the core_length wrt to the SD sequence is
        # uniformly randomly determined.

        # core_length can't be greater then shine_delgano length:
        core_length = min(len(shine_delgano), core_length)
        diff = len(shine_delgano) - core_length
        begin = int(random.random() * diff)

        for i in range(core_length):
            if random.random() < prob_shine_delgano:
                rbs.append(shine_delgano[begin + i])
            else:
                choices = list(seq_utils.NUCLEOTIDES)
                choices.remove(shine_delgano[begin + i])
                rbs.append(random.choice(choices))

        offset = diff - begin

        spacing = random.choice(range(max(
            0, offset + self.__optimal_spacing - max_nonoptimal_spacing),
            offset + self.__optimal_spacing + max_nonoptimal_spacing))

        rbs.extend([random.choice(seq_utils.NUCLEOTIDES)
                    for _ in range(spacing)])

        # if len(rbs) > MAX_RBS_LENGTH:
        #    rbs = rbs[len(rbs) - MAX_RBS_LENGTH:len(rbs) + 1]

        return ''.join([random.choice(seq_utils.NUCLEOTIDES)
                        for _ in range(rbs_len - len(rbs))] + rbs)

    def __calc_aligned_spacing(self, m_rna, start_pos, bp_x, bp_y):
        '''Calculates the aligned spacing between the 16S r_rna binding site and
        the start codon.'''

        # r_rna is the concatenated at the end of the sequence in 5' to 3'
        # direction first: identify the farthest 3' nt in the r_rna that binds
        # to the mRNA and return its mRNA base pairer
        seq_len = len(m_rna) + len(self.__r_rna)

        for r_rna_nt in range(seq_len, seq_len - len(self.__r_rna), -1):
            if r_rna_nt in bp_y:
                r_rna_pos = bp_y.index(r_rna_nt)
                if bp_x[r_rna_pos] < start_pos:
                    farthest_3_prime_r_rna = r_rna_nt - len(m_rna)
                    m_rna_nt = bp_x[r_rna_pos]

                    # start_pos is counting starting from 0 (python)
                    distance_to_start = start_pos - m_rna_nt + 1
                    return distance_to_start - farthest_3_prime_r_rna
                # else:
                break

        return float('inf')


def get_dg(tir):
    '''Gets dg from translation initiation rate.'''
    return _RT_EFF * (math.log(_K) - math.log(tir))


def get_tir(d_g):
    '''Gets translation initiation rate from dg.'''
    return _K * math.exp(-d_g / _RT_EFF)


def _calc_longest_loop_bulge(m_rna, bp_x, bp_y, rbs=None):
    ''''Calculate the longest helical loop and bulge structure
    (longest contiguous list of un-base paired nucleotides starting and
    ending with a helix (loop -> same helix, bulge -> different helix)
    in the secondary structure.'''
    loop_length = 0
    begin_helix = 1

    bulge_loop_list = []
    helical_loop_list = []
    bulge_loop_start_end = []
    helical_loop_start_end = []

    if rbs is not None:
        rbs_begin = m_rna.find(rbs)
        rbs_end = rbs_begin + len(rbs)
        nucleotide_range = range(rbs_begin, rbs_end + 1)
    else:
        nucleotide_range = range(1, len(m_rna) + 1)

    # Find loops. Find bulges.
    for nuc in nucleotide_range:
        # nth nucleotide is not base-paired.
        if bp_x.count(nuc) == 0 and bp_y.count(nuc) == 0:

            # Determine if nearest neighbor nucleotides are base-paired
            (x_1, x_2, y_1, y_2) = (bp_x.count(nuc - 1),
                                    bp_x.count(nuc + 1),
                                    bp_y.count(nuc - 1),
                                    bp_y.count(nuc + 1))

            # middle unpaired nt
            if (x_1, x_2, y_1, y_2) == (0, 0, 0, 0):
                loop_length += 1

            # single mismatch -- loop
            elif (x_1, x_2, y_1, y_2) == (1, 0, 0, 1) or \
                    (x_1, x_2, y_1, y_2) == (0, 1, 1, 0):
                loop_length += 1
                begin_helix = nuc - 1
                end_helix = nuc + 1

            # single mismatch -- bulge
            elif (x_1, x_2, y_1, y_2) == (1, 1, 0, 0) or \
                    (x_1, x_2, y_1, y_2) == (0, 0, 1, 1):
                loop_length += 1
                begin_helix = nuc - 1
                end_helix = nuc + 1

            # starting unpaired nt
            elif (x_1, x_2, y_1, y_2) == (1, 0, 0, 0) or \
                    (x_1, x_2, y_1, y_2) == (0, 0, 1, 0):
                loop_length += 1
                begin_helix = nuc - 1

            # ending unpaired nt
            elif (x_1, x_2, y_1, y_2) == (0, 1, 0, 0) or \
                    (x_1, x_2, y_1, y_2) == (0, 0, 0, 1):
                loop_length += 1
                end_helix = nuc + 1

            # 1,0,1,0 is impossible w/o psuedoknots
            # 0,1,0,1 is impossible w/o psuedoknots
            # Also, all binary combinations with 3 or 4 true are impossible
            # (nuc-1 or nuc+1 can not be in both bp_x and bp_y)

        elif loop_length > 0:
            # Bulge or loop?
            # loop

            if bp_x.count(begin_helix) > 0 and bp_y.count(end_helix) > 0 \
                    and bp_x.index(begin_helix) == bp_y.index(end_helix):
                helical_loop_list.append(loop_length)
                loop_length = 0
                helical_loop_start_end.append((begin_helix, end_helix))
            else:
                bp_end = 0
                bp_begin = 0

                if bp_x.count(end_helix) > 0:
                    bp_begin = bp_y[bp_x.index(end_helix)]
                if bp_y.count(end_helix) > 0:
                    bp_end = bp_x[bp_y.index(end_helix)]

                if bp_x.count(begin_helix) > 0:
                    bp_end = bp_y[bp_x.index(begin_helix)]
                if bp_y.count(begin_helix) > 0:
                    bp_begin = bp_x[bp_y.index(begin_helix)]

                if bp_end > bp_begin:
                    bulge_loop_list.append(loop_length)
                    loop_length = 0
                    bulge_loop_start_end.append((begin_helix, end_helix))
                else:
                    loop_length = 0

    return helical_loop_list, bulge_loop_list, helical_loop_start_end, \
        bulge_loop_start_end
