#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Miscellaneous utilities
"""


def split_and_deoblique_func(in_file):
    import os
    from nilearn.image import iter_img
    import nibabel as nb
    import numpy as np
    out_files = []
    for i, img in enumerate(iter_img(in_file)):
        out_file = os.path.abspath('vol%04d.nii.gz'%i)
        affine = img.affine
        affine[:3,:3] = np.diag(np.diag(affine[:3, :3]))
        nb.Nifti1Image(np.asanyarray(img.dataobj), affine, img.header).to_filename(out_file)
        out_files.append(out_file)
    return out_files


def afni2itk_func(in_file):
    import os
    from scipy.io import loadmat, savemat
    from numpy import loadtxt, around, hstack, vstack, zeros, float64

    def read_afni_affine(input_file, debug=False):
        orig_afni_mat = loadtxt(input_file)
        if debug:
            print(orig_afni_mat)

        output = []
        for i in range(orig_afni_mat.shape[0]):
            output.append(vstack((orig_afni_mat[i,:].reshape(3, 4, order='C'), [0, 0, 0, 1])))
        return output

    def get_ants_dict(affine, debug=False):
        out_dict = {}
        out_dict['AffineTransform_double_3_3'] = hstack(
            (affine[:3, :3].reshape(1, -1), affine[:3, 3].reshape(1, -1))).reshape(-1, 1).astype(float64)
        out_dict['fixed'] = zeros((3, 1))
        if debug:
            print(out_dict)

        return out_dict

    out_file = os.path.abspath('mc4d.txt')
    with open(out_file, 'w') as fp:
        fp.write("#Insight Transform File V1.0\n")
        for i, affine in enumerate(read_afni_affine(in_file)):
            fp.write("#Transform %d\n"%i)
            fp.write("Transform: AffineTransform_double_3_3\n")
            trans_dict = get_ants_dict(affine)
            fp.write("Parameters: " + ' '.join(["%g"%i for i in list(trans_dict['AffineTransform_double_3_3'])]) + "\n")
            fp.write("FixedParameters: " + ' '.join(["%g"%i for i in list(trans_dict['fixed'])]) + "\n")
    return out_file


def fix_multi_T1w_source_name(in_files):
    """
    Make up a generic source name when there are multiple T1s

    >>> fix_multi_T1w_source_name([
    ...     '/path/to/sub-045_ses-test_T1w.nii.gz',
    ...     '/path/to/sub-045_ses-retest_T1w.nii.gz'])
    '/path/to/sub-045_T1w.nii.gz'

    """
    import os
    from nipype.utils.filemanip import filename_to_list
    base, in_file = os.path.split(filename_to_list(in_files)[0])
    subject_label = in_file.split("_", 1)[0].split("-")[1]
    return os.path.join(base, "sub-%s_T1w.nii.gz" % subject_label)


def add_suffix(in_files, suffix):
    """
    Wrap nipype's fname_presuffix to conveniently just add a prefix

    >>> add_suffix([
    ...     '/path/to/sub-045_ses-test_T1w.nii.gz',
    ...     '/path/to/sub-045_ses-retest_T1w.nii.gz'], '_test')
    'sub-045_ses-test_T1w_test.nii.gz'

    """
    import os.path as op
    from nipype.utils.filemanip import fname_presuffix, filename_to_list
    return op.basename(fname_presuffix(filename_to_list(in_files)[0],
                                       suffix=suffix))


if __name__ == '__main__':
    pass
