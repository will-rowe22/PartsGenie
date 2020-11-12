'''
PathwayGenie (c) GeneGenie Bioinformatics Ltd. 2018

PathwayGenie is licensed under the MIT License.

To view a copy of this license, visit <http://opensource.org/licenses/MIT/>.

@author:  neilswainston
'''
import unittest

from parts_genie.rbs_calculator import RbsCalculator
import parts_genie.vienna_utils as utils


class TestRbsCalculator(unittest.TestCase):
    '''Test class for RbsCalculator.'''

    def test_calc_kinetic_score(self):
        '''Tests calc_kinetic_score method.'''
        r_rna = 'acctcctta'
        calc = RbsCalculator(r_rna, utils)

        m_rna = 'TTCTAGAGGGGGGATCTCCCCCCAAAAAATAAGAGGTACACATGACTAAAACTTTCA' + \
            'AAGGCTCAGTATTCCCACTGAG'

        start_pos = 41
        self.assertAlmostEqual(calc.calc_kinetic_score(m_rna, start_pos),
                               0.528571428571428)

    def test_get_calc_dgs(self):
        '''Tests calc_dgs method.'''
        r_rna = 'acctcctta'
        calc = RbsCalculator(r_rna, utils)

        m_rna = 'TTCTAGAGGGGGGATCTCCCCCCAAAAAATAAGAGGTACACATGACTAAAACTTTCA' + \
            'AAGGCTCAGTATTCCCACTGAG'

        dgs = calc.calc_dgs(m_rna)
        self.assertEqual(list(dgs.keys()), [41, 74])
        self.assertAlmostEqual(dgs[41][0], -6.088674036389431)
        self.assertAlmostEqual(dgs[74][0], 5.793940143051147)

        dgs = calc.calc_dgs(m_rna)
        self.assertEqual(list(dgs.keys()), [41, 74])
        self.assertAlmostEqual(dgs[41][0], -6.088674036389431)
        self.assertAlmostEqual(dgs[74][0], 5.793940143051147)

    def test_mfe_fail(self):
        '''Tests mfe method.'''
        m_rna = 'GCGGGAATTACACATGGCATGGACGAACTTTATAAATGA'

        energies, bp_xs, bp_ys = utils.run('mfe', [m_rna], temp=37.0,
                                           dangles='none')

        self.assertEqual(energies, [0.0])
        self.assertEqual(bp_xs, [[]])
        self.assertEqual(bp_ys, [[]])

    def test_subopt(self):
        '''Tests subopt method.'''
        r_rna = 'ACCTCCTTA'
        m_rna = 'AACCTAATTGATAGCGGCCTAGGACCCCCATCAAC'

        _, _, bp_ys = utils.run('subopt', [m_rna, r_rna], temp=37.0,
                                dangles='all', energy_gap=3.0)

        nt_in_r_rna = False

        for bp_y in bp_ys:
            for nt_y in bp_y:
                if nt_y > len(m_rna):
                    nt_in_r_rna = True

        self.assertTrue(nt_in_r_rna)

    def test_subopt_fail(self):
        '''Tests subopt method.'''
        r_rna = 'CCC'
        m_rna = 'CCC'

        energies, bp_xs, bp_ys = utils.run('subopt', [m_rna, r_rna], temp=37.0,
                                           dangles='all', energy_gap=3.0)

        self.assertEqual(energies, [])
        self.assertEqual(bp_xs, [])
        self.assertEqual(bp_ys, [])


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
