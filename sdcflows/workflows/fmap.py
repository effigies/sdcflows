#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Direct B0 mapping sequences
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the fieldmap is directly measured with a prescribed sequence (such as
:abbr:`SE (spiral echo)`), we only need to calculate the corresponding B-Spline
coefficients to adapt the fieldmap to the TOPUP tool.
This procedure is described with more detail `here <https://cni.stanford.edu/\
wiki/GE_Processing#Fieldmaps>`_.

This corresponds to the section 8.9.3 --fieldmap image (and one magnitude image)--
of the BIDS specification.

"""
from __future__ import print_function, division, absolute_import, unicode_literals

from nipype.pipeline import engine as pe
from nipype.interfaces import utility as niu
from nipype.interfaces import ants

from nipype.interfaces import fsl
from niworkflows.interfaces.masks import BETRPT
from nipype.workflows.dmri.fsl.utils import demean_image, cleanup_edge_pipeline
from fmriprep.interfaces import IntraModalMerge, CopyHeader
from fmriprep.interfaces.bids import DerivativesDataSink
from fmriprep.interfaces.fmap import FieldEnhance
from fmriprep.interfaces.utils import ApplyMask


def init_fmap_wf(reportlets_dir, ants_nthreads, fmap_bspline, name='fmap_wf'):
    """
    Fieldmap workflow - when we have a sequence that directly measures the fieldmap
    we just need to mask it (using the corresponding magnitude image) to remove the
    noise in the surrounding air region, and ensure that units are Hz.

    .. workflow ::

        from fmriprep.workflows.fieldmap.fmap import init_fmap_wf
        wf = init_fmap_wf(reportlets_dir='.', ants_nthreads=6, 
                          fmap_bspline=False)

    """

    workflow = pe.Workflow(name=name)
    inputnode = pe.Node(niu.IdentityInterface(
        fields=['magnitude', 'fieldmap']), name='inputnode')
    outputnode = pe.Node(niu.IdentityInterface(fields=['fmap', 'fmap_ref', 'fmap_mask']),
                         name='outputnode')

    # Merge input magnitude images
    magmrg = pe.Node(IntraModalMerge(), name='magmrg')
    # Merge input fieldmap images
    fmapmrg = pe.Node(IntraModalMerge(zero_based_avg=False, hmc=False),
                      name='fmapmrg')

    # de-gradient the fields ("bias/illumination artifact")
    mag_inu = pe.Node(ants.N4BiasFieldCorrection(dimension=3), name='mag_inu')
    cphdr = pe.Node(CopyHeader(), name='cphdr')
    bet = pe.Node(BETRPT(generate_report=True, frac=0.6, mask=True),
                  name='bet')
    ds_fmap_mask = pe.Node(
        DerivativesDataSink(base_directory=reportlets_dir,
                            suffix='fmap_mask'), name='ds_fmap_mask')

    workflow.connect([
        (inputnode, magmrg, [('magnitude', 'in_files')]),
        (inputnode, fmapmrg, [('fieldmap', 'in_files')]),
        (magmrg, mag_inu, [('out_file', 'input_image')]),
        (mag_inu, cphdr, [('output_image', 'in_file')]),
        (magmrg, cphdr, [('out_file', 'hdr_file')]),
        (cphdr, bet, [('out_file', 'in_file')]),
        (bet, outputnode, [('mask_file', 'fmap_mask'),
                           ('out_file', 'fmap_ref')]),
        (inputnode, ds_fmap_mask, [('fieldmap', 'source_file')]),
        (bet, ds_fmap_mask, [('out_report', 'in_file')]),
    ])

    if fmap_bspline:
        # despike_threshold=1.0, mask_erode=1),
        fmapenh = pe.Node(FieldEnhance(
            unwrap=False, despike=False, njobs=ants_nthreads),
            name='fmapenh')
        fmapenh.interface.num_threads = ants_nthreads
        fmapenh.interface.estimated_memory_gb = 4

        workflow.connect([
            (bet, fmapenh, [('mask_file', 'in_mask'),
                            ('out_file', 'in_magnitude')]),
            (fmapmrg, fmapenh, [('out_file', 'in_file')]),
            (fmapenh, outputnode, [('out_file', 'fmap')]),
        ])

    else:
        torads = pe.Node(niu.Function(output_names=['out_file', 'cutoff_hz'],
                                      function=_torads), name='torads')
        prelude = pe.Node(fsl.PRELUDE(), name='prelude')
        tohz = pe.Node(niu.Function(function=_tohz), name='tohz')

        denoise = pe.Node(fsl.SpatialFilter(operation='median', kernel_shape='sphere',
                                            kernel_size=3), name='denoise')
        demean = pe.Node(niu.Function(function=demean_image), name='demean')
        cleanup = cleanup_edge_pipeline(name='cleanup')

        applymsk = pe.Node(ApplyMask(), name='applymsk')

        workflow.connect([
            (bet, prelude, [('mask_file', 'mask_file'),
                            ('out_file', 'magnitude_file')]),
            (fmapmrg, torads, [('out_file', 'in_file')]),
            (torads, tohz, [('cutoff_hz', 'cutoff_hz')]),
            (torads, prelude, [('out_file', 'phase_file')]),
            (prelude, tohz, [('unwrapped_phase_file', 'in_file')]),
            (tohz, denoise, [('out', 'in_file')]),
            (denoise, demean, [('out_file', 'in_file')]),
            (demean, cleanup, [('out', 'inputnode.in_file')]),
            (bet, cleanup, [('mask_file', 'inputnode.in_mask')]),
            (cleanup, applymsk, [('outputnode.out_file', 'in_file')]),
            (bet, applymsk, [('mask_file', 'in_mask')]),
            (applymsk, outputnode, [('out_file', 'fmap')]),
        ])

    return workflow


def _torads(in_file, out_file=None):
    from math import pi
    import nibabel as nb
    import numpy as np
    from fmriprep.utils.misc import genfname

    if out_file is None:
        out_file = genfname(in_file, suffix='rad')

    fmapnii = nb.load(in_file)
    fmapdata = fmapnii.get_data()
    cutoff = max(abs(fmapdata.min()), fmapdata.max())
    fmapdata *= (pi / cutoff)
    nb.Nifti1Image(fmapdata, fmapnii.affine, fmapnii.header).to_filename(
        out_file)
    return out_file, cutoff


def _tohz(in_file, cutoff_hz, out_file=None):
    from math import pi
    import nibabel as nb
    from fmriprep.utils.misc import genfname
    if out_file is None:
        out_file = genfname(in_file, suffix='hz')

    fmapnii = nb.load(in_file)
    fmapdata = fmapnii.get_data()
    fmapdata *= (cutoff_hz / pi)
    nb.Nifti1Image(fmapdata, fmapnii.affine, fmapnii.header).to_filename(
        out_file)
    return out_file