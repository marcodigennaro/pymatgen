# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

from __future__ import unicode_literals

import unittest2 as unittest
import os
from pymatgen.electronic_structure.boltztrap import BoltztrapAnalyzer
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import Spin, OrbitalType
from pymatgen.core.structure import Structure
from monty.serialization import loadfn


try:
    from ase.io.cube import read_cube
except ImportError:
    read_cube = None

test_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        'test_files')


@unittest.skipIf(read_cube is None, "No ase.io.read_cube.")
class BoltztrapAnalyzerTest(unittest.TestCase):

    def setUp(self):
        self.bz = BoltztrapAnalyzer.from_files(os.path.join(test_dir, "boltztrap/transp/"))
        self.bz_bands = BoltztrapAnalyzer.from_files(os.path.join(test_dir, "boltztrap/bands/"))
        self.bz_up = BoltztrapAnalyzer.from_files(os.path.join(test_dir, "boltztrap/dos_up/"),dos_spin=1)
        self.bz_dw = BoltztrapAnalyzer.from_files(os.path.join(test_dir, "boltztrap/dos_dw/"),dos_spin=-1)
        self.bz_fermi = BoltztrapAnalyzer.from_files(os.path.join(test_dir, "boltztrap/fermi/"))
        
    def test_properties(self):
        self.assertAlmostEqual(self.bz.gap, 1.6644932121620404, 4)
        array = self.bz._cond[300][102]
        self.assertAlmostEqual(array[0][0]/1e19, 7.5756518, 4)
        self.assertAlmostEqual(array[0][2], -11.14679)
        self.assertAlmostEqual(array[1][0], -88.203286)
        self.assertAlmostEqual(array[2][2], 1.7133249e+19)
        array = self.bz._seebeck[300][22]
        self.assertAlmostEqual(array[0][1], 6.4546074e-22)
        self.assertAlmostEqual(array[1][1], -0.00032073711)
        self.assertAlmostEqual(array[1][2], -2.9868424e-24)
        self.assertAlmostEqual(array[2][2], -0.0003126543)
        array = self.bz._kappa[500][300]
        self.assertAlmostEqual(array[0][1], 0.00014524309)
        self.assertAlmostEqual(array[1][1], 328834400000000.0)
        self.assertAlmostEqual(array[1][2], 3.7758069e-05)
        self.assertAlmostEqual(array[2][2], 193943750000000.0)
        self.assertAlmostEqual(self.bz._hall[400][800][1][0][0], 9.5623749e-28)
        self.assertAlmostEqual(self.bz._hall[400][68][1][2][2], 6.5106975e-10)
        self.assertAlmostEqual(self.bz.doping['p'][3], 1e18)
        self.assertAlmostEqual(self.bz.mu_doping['p'][300][2], 0.1553770018406)
        self.assertAlmostEqual(self.bz.mu_doping['n'][300][-1],
                               1.6486017632924719, 4)
        self.assertAlmostEqual(self.bz._cond_doping['n'][800][3][1][1]/1e16,
                               1.5564085, 4)
        self.assertAlmostEqual(self.bz._seebeck_doping['p'][600][2][0][
                                   1]/1e-23, 3.2860613, 4)
        self.assertAlmostEqual(self.bz._carrier_conc[500][67], 38.22832002)
        self.assertAlmostEqual(self.bz.vol, 612.97557323964838, 4)
        self.assertAlmostEqual(self.bz._hall_doping['n'][700][-1][2][2][2], 5.0136483e-26)
        self.assertAlmostEqual(self.bz.dos.efermi, -0.0300005507057)
        self.assertAlmostEqual(self.bz.dos.energies[0], -2.4497049391830448, 4)
        self.assertAlmostEqual(self.bz.dos.energies[345],
                               -0.72708823447130944, 4)
        self.assertAlmostEqual(self.bz.dos.energies[-1], 3.7569398770153524, 4)
        self.assertAlmostEqual(self.bz.dos.densities[Spin.up][400], 118.70171)
        self.assertAlmostEqual(self.bz.dos.densities[Spin.up][200], 179.58562)
        self.assertAlmostEqual(self.bz.dos.densities[Spin.up][300], 289.43945)
        
        self.assertAlmostEqual(self.bz_bands._bz_bands.shape, (1316, 20))
        self.assertAlmostEqual(self.bz_bands._bz_kpoints.shape, (1316, 3))
        self.assertAlmostEqual(self.bz_up._dos_partial['0']['pz'][2562],0.023862958)
        self.assertAlmostEqual(self.bz_dw._dos_partial['1']['px'][3120],5.0192891)
        self.assertAlmostEqual(self.bz_fermi.fermi_surface_data[0].shape,
                               (121,121, 65))
        self.assertAlmostEqual(self.bz_fermi.fermi_surface_data[0][21][79][19],-0.138412)

    def test_get_seebeck(self):
        ref = [-768.99078999999995, -724.43919999999991, -686.84682999999973]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_seebeck()['n'][800][3][i], ref[i])
        self.assertAlmostEqual(self.bz.get_seebeck(output='average')['p'][800][3], 697.608936667)
        self.assertAlmostEqual(self.bz.get_seebeck(output='average', doping_levels=False)[500][520], 1266.7056)
        self.assertAlmostEqual(self.bz.get_seebeck(output='eigs', doping_levels=False)[300][65], -36.2459389333)

    def test_get_conductivity(self):
        ref = [5.9043185000000022, 17.855599000000002, 26.462935000000002]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_conductivity()['p'][600][2][i], ref[i])
        self.assertAlmostEqual(self.bz.get_conductivity(output='average')['n'][700][1], 1.58736609667)
        self.assertAlmostEqual(self.bz.get_conductivity(output='average', doping_levels=False)[300][457], 2.87163566667)
        self.assertAlmostEqual(self.bz.get_conductivity(output='eigs', doping_levels=False,
                                                        relaxation_time=1e-15)[200][63], 16573.0536667)

    def test_get_power_factor(self):
        ref = [6.2736602345523362, 17.900184232304138, 26.158282220458144]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_power_factor()['p'][200][2][i], ref[i])
        self.assertAlmostEqual(self.bz.get_power_factor(output='average')['n'][600][4], 411.230962976)
        self.assertAlmostEqual(self.bz.get_power_factor(output='average', doping_levels=False,
                                                        relaxation_time=1e-15)[500][459], 6.59277148467)
        self.assertAlmostEqual(self.bz.get_power_factor(output='eigs', doping_levels=False)[800][61], 2022.67064134)

    def test_get_thermal_conductivity(self):
        ref = [2.7719565628862623e-05, 0.00010048046886793946, 0.00015874549392499391]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_thermal_conductivity()['p'][300][2][i], ref[i])
        self.assertAlmostEqual(self.bz.get_thermal_conductivity(output='average', relaxation_time=1e-15)['n'][500][0],
                               1.74466575612e-07)
        self.assertAlmostEqual(self.bz.get_thermal_conductivity(output='average', doping_levels=False)[800][874],
                               8.08066254813)
        self.assertAlmostEqual(self.bz.get_thermal_conductivity(output='eigs', doping_levels=False)[200][32],
                               0.0738961845832)

    def test_get_zt(self):
        ref = [0.0002228294548133532, 0.00081441896388844142, 0.00085232847622913053]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_zt()['n'][400][0][i], ref[i])
        self.assertAlmostEqual(self.bz.get_zt(output='average', kl=0.5)['p'][700][2], 0.0170001879916)
        self.assertAlmostEqual(self.bz.get_zt(output='average', doping_levels=False, relaxation_time=1e-15)[300][240],
                               0.00953842615332)
        self.assertAlmostEqual(self.bz.get_zt(output='eigs', doping_levels=False)[700][65], 0.335990406091)

    def test_get_average_eff_mass(self):
        ref = [0.76045816788363574, 0.96181142990667101, 2.9428428773308628]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_average_eff_mass()['p'][300][2][i], ref[i])
        ref = [1.1295783824744523, 1.3898454041924351, 5.2459984671977935]
        for i in range(0, 3):
            self.assertAlmostEqual(self.bz.get_average_eff_mass()['n'][600][1][i], ref[i])
        ref = [[9.61811430e-01, -8.25159596e-19, -4.70319444e-19],
               [-8.25159596e-19, 2.94284288e+00, 3.00368916e-18],
               [-4.70319444e-19, 3.00368916e-18, 7.60458168e-01]]
        for i in range(0, 3):
            for j in range(0, 3):
                self.assertAlmostEqual(self.bz.get_average_eff_mass(output='tensor')['p'][300][2][i][j], ref[i][j])
        self.assertAlmostEqual(self.bz.get_average_eff_mass(output='average')['n'][300][2], 1.53769093989)

    def test_get_carrier_concentration(self):
        self.assertAlmostEqual(self.bz.get_carrier_concentration()[300][39] /
                               1e22, 6.4805156617179151, 4)
        self.assertAlmostEqual(self.bz.get_carrier_concentration()[300][
                                   693]/1e15, -6.590800965604750, 4)

    def test_get_hall_carrier_concentration(self):
        self.assertAlmostEqual(self.bz.get_hall_carrier_concentration()[600][
                                   120]/1e21, 6.773394626767555, 4)
        self.assertAlmostEqual(self.bz.get_hall_carrier_concentration()[500][
                                   892]/1e21, -9.136803845741777, 4)
    
    def test_get_symm_bands(self):
        structure = loadfn(os.path.join(test_dir,'boltztrap/structure_mp-12103.json'))
        sbs_bzt = self.bz_bands.get_symm_bands(structure,-5.25204548)
        self.assertAlmostEqual(len(sbs_bzt.bands[Spin.up]),20)
        self.assertAlmostEqual(len(sbs_bzt.bands[Spin.up][1]),143)
    
    def test_check_acc_bzt_bands(self):
        structure = loadfn(os.path.join(test_dir,'boltztrap/structure_mp-12103.json'))
        sbs = loadfn(os.path.join(test_dir,'boltztrap/dft_bs_sym_line.json'))
        sbs_bzt = self.bz_bands.get_symm_bands(structure,-5.25204548)
        corr,werr_vbm,werr_cbm,warn = self.bz_bands.check_acc_bzt_bands(sbs_bzt,sbs)
        self.assertAlmostEqual(corr[2],9.16851750e-05)
        self.assertAlmostEqual(werr_vbm['K-H'],0.18260273521047862)
        self.assertAlmostEqual(werr_cbm['M-K'],0.071552669981356981)
        self.assertFalse(warn)
        
    def test_get_comlete_dos(self):
        structure = loadfn(os.path.join(test_dir,'boltztrap/structure_mp-12103.json'))
        cdos = self.bz_up.get_complete_dos(structure,self.bz_dw)
        self.assertIs(cdos.densities.keys()[0],Spin.down)
        self.assertIs(cdos.densities.keys()[1],Spin.up)
        self.assertAlmostEqual(cdos.get_spd_dos()[OrbitalType.p].densities[Spin.up][3134],43.839230100999991)
        self.assertAlmostEqual(cdos.get_spd_dos()[OrbitalType.s].densities[Spin.down][716],6.5383268000000001)
        
if __name__ == '__main__':
    unittest.main()
