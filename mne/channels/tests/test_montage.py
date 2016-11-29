# Author: Teon Brooks <teon.brooks@gmail.com>
#
# License: BSD (3-clause)

import os.path as op
import warnings

from nose.tools import assert_equal, assert_true, assert_raises

import numpy as np
from scipy.io import savemat

from numpy.testing import (assert_array_equal, assert_almost_equal,
                           assert_allclose, assert_array_almost_equal,
                           assert_array_less)
from mne.tests.common import assert_dig_allclose
from mne.channels.montage import read_montage, _set_montage, read_dig_montage
from mne.utils import _TempDir, run_tests_if_main
from mne import create_info, EvokedArray, read_evokeds
from mne.coreg import fit_matched_points
from mne.transforms import apply_trans, get_ras_to_neuromag_trans
from mne.io.constants import FIFF
from mne.io.meas_info import _read_dig_points
from mne.io.kit import read_mrk
from mne.io import read_raw_brainvision

from mne.datasets import testing

data_path = testing.data_path(download=False)
fif_dig_montage_fname = op.join(data_path, 'montage', 'eeganes07.fif')
locs_montage_fname = op.join(data_path, 'EEGLAB', 'test_chans.locs')
evoked_fname = op.join(data_path, 'montage', 'level2_raw-ave.fif')

io_dir = op.join(op.dirname(__file__), '..', '..', 'io')
kit_dir = op.join(io_dir, 'kit', 'tests', 'data')
elp = op.join(kit_dir, 'test_elp.txt')
hsp = op.join(kit_dir, 'test_hsp.txt')
hpi = op.join(kit_dir, 'test_mrk.sqd')
bv_fname = op.join(io_dir, 'brainvision', 'tests', 'data', 'test.vhdr')


def test_montage():
    """Test making montages."""
    tempdir = _TempDir()
    # no pep8
    input_str = [
        'FidNz 0.00000 10.56381 -2.05108\nFidT9 -7.82694 0.45386 -3.76056\n'
        'very_very_very_long_name 7.82694 0.45386 -3.76056\nDmy 7.0 0.0 1.0',
        '// MatLab   Sphere coordinates [degrees]         Cartesian coordinates\n'  # noqa: E501
        '// Label       Theta       Phi    Radius         X         Y         Z       off sphere surface\n'  # noqa: E501
        'E1      37.700     -14.000       1.000    0.7677    0.5934   -0.2419  -0.00000000000000011\n'  # noqa: E501
        'E2      44.600      -0.880       1.000    0.7119    0.7021   -0.0154   0.00000000000000000\n'  # noqa: E501
        'E3      51.700      11.000       1.000    0.6084    0.7704    0.1908   0.00000000000000000\n'  # noqa: E501
        'E4      52.700      12.000       1.000    0.7084    0.7504    0.1508   0.00000000000000000',  # noqa: E501; dummy line
        '# ASA electrode file\nReferenceLabel  avg\nUnitPosition    mm\n'
        'NumberPositions=    68\nPositions\n-86.0761 -19.9897 -47.9860\n'
        '85.7939 -20.0093 -48.0310\n0.0083 86.8110 -39.9830\n'
        '85 -20 -48\n'
        'Labels\nLPA\nRPA\nNz\nDummy\n',
        '# ASA electrode file\nReferenceLabel  avg\nUnitPosition    m\n'
        'NumberPositions=    68\nPositions\n-.0860761 -.0199897 -.0479860\n'
        '.0857939 -.0200093 -.0480310\n.0000083 .00868110 -.0399830\n'
        '.08 -.02 -.04\n'
        'Labels\nLPA\nRPA\nNz\nDummy\n',
        'Site  Theta  Phi\nFp1  -92    -72\nFp2   92     72\n'
        'very_very_very_long_name   -60    -51\n'
        'dummy -60 -52\n',
        '346\n'
        'EEG\t      F3\t -62.027\t -50.053\t      85\n'
        'EEG\t      Fz\t  45.608\t      90\t      85\n'
        'EEG\t      F4\t   62.01\t  50.103\t      85\n'
        'EEG\t      FCz\t   68.01\t  58.103\t      85\n',
        'eeg Fp1 -95.0 -3. -3.\neeg AF7 -1 -1 -3\neeg A3 -2 -2 2\neeg A 0 0 0'
    ]

    kinds = ['test.sfp', 'test.csd', 'test_mm.elc', 'test_m.elc', 'test.txt',
             'test.elp', 'test.hpts']
    for kind, text in zip(kinds, input_str):
        fname = op.join(tempdir, kind)
        with open(fname, 'w') as fid:
            fid.write(text)
        montage = read_montage(fname)
        if ".sfp" in kind or ".txt" in kind:
            assert_true('very_very_very_long_name' in montage.ch_names)
        assert_equal(len(montage.ch_names), 4)
        assert_equal(len(montage.ch_names), len(montage.pos))
        assert_equal(montage.pos.shape, (4, 3))
        assert_equal(montage.kind, op.splitext(kind)[0])
        if kind.endswith('csd'):
            dtype = [('label', 'S4'), ('theta', 'f8'), ('phi', 'f8'),
                     ('radius', 'f8'), ('x', 'f8'), ('y', 'f8'), ('z', 'f8'),
                     ('off_sph', 'f8')]
            try:
                table = np.loadtxt(fname, skip_header=2, dtype=dtype)
            except TypeError:
                table = np.loadtxt(fname, skiprows=2, dtype=dtype)
            pos2 = np.c_[table['x'], table['y'], table['z']]
            assert_array_almost_equal(pos2[:-1, :], montage.pos[:-1, :], 4)
        if kind.endswith('elc'):
            # Make sure points are reasonable distance from geometric centroid
            centroid = np.sum(montage.pos, axis=0) / montage.pos.shape[0]
            distance_from_centroid = np.apply_along_axis(
                np.linalg.norm, 1,
                montage.pos - centroid)
            assert_array_less(distance_from_centroid, 0.2)
            assert_array_less(0.01, distance_from_centroid)

    # Test reading in different letter case.
    ch_names = ["F3", "FZ", "F4", "FC3", "FCz", "FC4", "C3", "CZ", "C4", "CP3",
                "CPZ", "CP4", "P3", "PZ", "P4", "O1", "OZ", "O2"]
    montage = read_montage('standard_1020', ch_names=ch_names)
    assert_array_equal(ch_names, montage.ch_names)

    # test transform
    input_str = """
    eeg Fp1 -95.0 -31.0 -3.0
    eeg AF7 -81 -59 -3
    eeg AF3 -87 -41 28
    cardinal 2 -91 0 -42
    cardinal 1 0 -91 -42
    cardinal 3 0 91 -42
    """
    kind = 'test_fid.hpts'
    fname = op.join(tempdir, kind)
    with open(fname, 'w') as fid:
        fid.write(input_str)
    montage = read_montage(op.join(tempdir, 'test_fid.hpts'), transform=True)
    # check coordinate transformation
    pos = np.array([-95.0, -31.0, -3.0])
    nasion = np.array([-91, 0, -42])
    lpa = np.array([0, -91, -42])
    rpa = np.array([0, 91, -42])
    fids = np.vstack((nasion, lpa, rpa))
    trans = get_ras_to_neuromag_trans(fids[0], fids[1], fids[2])
    pos = apply_trans(trans, pos)
    assert_array_equal(montage.pos[0], pos)
    idx = montage.ch_names.index('2')
    assert_array_equal(montage.pos[idx, [0, 2]], [0, 0])
    idx = montage.ch_names.index('1')
    assert_array_equal(montage.pos[idx, [1, 2]], [0, 0])
    idx = montage.ch_names.index('3')
    assert_array_equal(montage.pos[idx, [1, 2]], [0, 0])
    pos = np.array([-95.0, -31.0, -3.0])
    montage_fname = op.join(tempdir, 'test_fid.hpts')
    montage = read_montage(montage_fname, unit='mm')
    assert_array_equal(montage.pos[0], pos * 1e-3)

    # test with last
    info = create_info(montage.ch_names, 1e3, ['eeg'] * len(montage.ch_names))
    _set_montage(info, montage)
    pos2 = np.array([c['loc'][:3] for c in info['chs']])
    assert_array_equal(pos2, montage.pos)
    assert_equal(montage.ch_names, info['ch_names'])

    info = create_info(
        montage.ch_names, 1e3, ['eeg'] * len(montage.ch_names))

    evoked = EvokedArray(
        data=np.zeros((len(montage.ch_names), 1)), info=info, tmin=0)
    evoked.set_montage(montage)
    pos3 = np.array([c['loc'][:3] for c in evoked.info['chs']])
    assert_array_equal(pos3, montage.pos)
    assert_equal(montage.ch_names, evoked.info['ch_names'])

    # Warning should be raised when some EEG are not specified in the montage
    with warnings.catch_warnings(record=True) as w:
        info = create_info(montage.ch_names + ['foo', 'bar'], 1e3,
                           ['eeg'] * (len(montage.ch_names) + 2))
        _set_montage(info, montage)
        assert_true(len(w) == 1)


@testing.requires_testing_data
def test_read_locs():
    """Test reading EEGLAB locs."""
    pos = read_montage(locs_montage_fname).pos
    expected = [[0., 9.99779165e-01, -2.10157875e-02],
                [3.08738197e-01, 7.27341573e-01, -6.12907052e-01],
                [-5.67059636e-01, 6.77066318e-01, 4.69067752e-01],
                [0., 7.14575231e-01, 6.99558616e-01]]
    assert_allclose(pos[:4], expected, atol=1e-7)


def test_read_dig_montage():
    """Test read_dig_montage"""
    names = ['nasion', 'lpa', 'rpa', '1', '2', '3', '4', '5']
    montage = read_dig_montage(hsp, hpi, elp, names, transform=False)
    elp_points = _read_dig_points(elp)
    hsp_points = _read_dig_points(hsp)
    hpi_points = read_mrk(hpi)
    assert_equal(montage.point_names, names)
    assert_array_equal(montage.elp, elp_points)
    assert_array_equal(montage.hsp, hsp_points)
    assert_array_equal(montage.hpi, hpi_points)
    assert_true(montage.dev_head_t is None)
    montage = read_dig_montage(hsp, hpi, elp, names,
                               transform=True, dev_head_t=True)
    # check coordinate transformation
    # nasion
    assert_almost_equal(montage.nasion[0], 0)
    assert_almost_equal(montage.nasion[2], 0)
    # lpa and rpa
    assert_allclose(montage.lpa[1:], 0, atol=1e-16)
    assert_allclose(montage.rpa[1:], 0, atol=1e-16)
    # device head transform
    dev_head_t = fit_matched_points(tgt_pts=montage.elp,
                                    src_pts=montage.hpi, out='trans')
    assert_array_equal(montage.dev_head_t, dev_head_t)

    # Digitizer as array
    m2 = read_dig_montage(hsp_points, hpi_points, elp_points, names, unit='m')
    assert_array_equal(m2.hsp, montage.hsp)
    m3 = read_dig_montage(hsp_points * 1000, hpi_points, elp_points * 1000,
                          names)
    assert_allclose(m3.hsp, montage.hsp)

    # test unit parameter and .mat support
    tempdir = _TempDir()
    mat_hsp = op.join(tempdir, 'test.mat')
    savemat(mat_hsp, dict(Points=(1000 * hsp_points).T))
    montage_cm = read_dig_montage(mat_hsp, hpi, elp, names, unit='cm')
    assert_allclose(montage_cm.hsp, montage.hsp * 10.)
    assert_allclose(montage_cm.elp, montage.elp * 10.)
    assert_array_equal(montage_cm.hpi, montage.hpi)
    assert_raises(ValueError, read_dig_montage, hsp, hpi, elp, names,
                  unit='km')


def test_set_dig_montage():
    """Test applying DigMontage to inst."""
    # Extensive testing of applying `dig` to info is done in test_meas_info
    # with `test_make_dig_points`.
    names = ['nasion', 'lpa', 'rpa', '1', '2', '3', '4', '5']
    hsp_points = _read_dig_points(hsp)
    elp_points = _read_dig_points(elp)
    nasion, lpa, rpa = elp_points[:3]
    nm_trans = get_ras_to_neuromag_trans(nasion, lpa, rpa)
    elp_points = apply_trans(nm_trans, elp_points)
    nasion, lpa, rpa = elp_points[:3]
    hsp_points = apply_trans(nm_trans, hsp_points)

    montage = read_dig_montage(hsp, hpi, elp, names, transform=True,
                               dev_head_t=True)
    temp_dir = _TempDir()
    fname_temp = op.join(temp_dir, 'test.fif')
    montage.save(fname_temp)
    montage_read = read_dig_montage(fif=fname_temp)
    for use_mon in (montage, montage_read):
        info = create_info(['Test Ch'], 1e3, ['eeg'])
        with warnings.catch_warnings(record=True) as w:  # test ch pos not set
            _set_montage(info, use_mon)
        assert_true(all('not set' in str(ww.message) for ww in w))
        hs = np.array([p['r'] for i, p in enumerate(info['dig'])
                       if p['kind'] == FIFF.FIFFV_POINT_EXTRA])
        nasion_dig = np.array([p['r'] for p in info['dig']
                               if all([p['ident'] == FIFF.FIFFV_POINT_NASION,
                                       p['kind'] == FIFF.FIFFV_POINT_CARDINAL])
                               ])
        lpa_dig = np.array([p['r'] for p in info['dig']
                            if all([p['ident'] == FIFF.FIFFV_POINT_LPA,
                                    p['kind'] == FIFF.FIFFV_POINT_CARDINAL])])
        rpa_dig = np.array([p['r'] for p in info['dig']
                            if all([p['ident'] == FIFF.FIFFV_POINT_RPA,
                                    p['kind'] == FIFF.FIFFV_POINT_CARDINAL])])
        hpi_dig = np.array([p['r'] for p in info['dig']
                            if p['kind'] == FIFF.FIFFV_POINT_HPI])
        assert_allclose(hs, hsp_points, atol=1e-7)
        assert_allclose(nasion_dig.ravel(), nasion, atol=1e-7)
        assert_allclose(lpa_dig.ravel(), lpa, atol=1e-7)
        assert_allclose(rpa_dig.ravel(), rpa, atol=1e-7)
        assert_allclose(hpi_dig, elp_points[3:], atol=1e-7)


@testing.requires_testing_data
def test_fif_dig_montage():
    """Test FIF dig montage support."""
    dig_montage = read_dig_montage(fif=fif_dig_montage_fname)

    # test round-trip IO
    temp_dir = _TempDir()
    fname_temp = op.join(temp_dir, 'test.fif')
    _check_roundtrip(dig_montage, fname_temp)

    # Make a BrainVision file like the one the user would have had
    with warnings.catch_warnings(record=True) as w:
        raw_bv = read_raw_brainvision(bv_fname, preload=True)
    assert_true(any('will be dropped' in str(ww.message) for ww in w))
    raw_bv_2 = raw_bv.copy()
    mapping = dict()
    for ii, ch_name in enumerate(raw_bv.ch_names[:-1]):
        mapping[ch_name] = 'EEG%03d' % (ii + 1,)
    raw_bv.rename_channels(mapping)
    for ii, ch_name in enumerate(raw_bv_2.ch_names[:-1]):
        mapping[ch_name] = 'EEG%03d' % (ii + 33,)
    raw_bv_2.rename_channels(mapping)
    raw_bv.drop_channels(['STI 014'])
    raw_bv.add_channels([raw_bv_2])

    for ii in range(2):
        if ii == 1:
            dig_montage.transform_to_head()  # should have no meaningful effect

        # Set the montage
        raw_bv.set_montage(dig_montage)

        # Check the result
        evoked = read_evokeds(evoked_fname)[0]

        assert_equal(len(raw_bv.ch_names), len(evoked.ch_names))
        for ch_py, ch_c in zip(raw_bv.info['chs'], evoked.info['chs']):
            assert_equal(ch_py['ch_name'],
                         ch_c['ch_name'].replace('EEG ', 'EEG'))
            # C actually says it's unknown, but it's not (?):
            # assert_equal(ch_py['coord_frame'], ch_c['coord_frame'])
            assert_equal(ch_py['coord_frame'], FIFF.FIFFV_COORD_HEAD)
            assert_allclose(ch_py['loc'], ch_c['loc'], atol=1e-7)
        assert_dig_allclose(raw_bv.info, evoked.info)

    # Roundtrip of non-FIF start
    names = ['nasion', 'lpa', 'rpa', '1', '2', '3', '4', '5']
    montage = read_dig_montage(hsp, hpi, elp, names, transform=False)
    assert_raises(RuntimeError, montage.save, fname_temp)  # must be head coord
    montage = read_dig_montage(hsp, hpi, elp, names)
    _check_roundtrip(montage, fname_temp)


def _check_roundtrip(montage, fname):
    """Check roundtrip writing."""
    assert_equal(montage.coord_frame, 'head')
    montage.save(fname)
    montage_read = read_dig_montage(fif=fname)
    assert_equal(str(montage), str(montage_read))
    for kind in ('elp', 'hsp', 'nasion', 'lpa', 'rpa'):
        assert_allclose(getattr(montage, kind),
                        getattr(montage_read, kind), err_msg=kind)
    assert_equal(montage_read.coord_frame, 'head')

run_tests_if_main()
