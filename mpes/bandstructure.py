#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
@author: R. Patrick Xian
"""

import numpy as np
import cv2
from copy import deepcopy
from xarray import DataArray
from mpes import fprocessing as fp, analysis as aly, utils as u
from collections import OrderedDict


class BandStructure(DataArray):
    """
    Data structure for storage and manipulation of a single band structure (1-3D) dataset.
    Instantiation of the BandStructure class can be done by specifying a (HDF5 or mat) file path
    or by separately specify the data, the axes values and their names.
    """

    keypair = {'X':'kx', 'Y':'ky', 't':'E'}

    def __init__(self, data=None, coords=None, dims=None, datakey='V', faddr=None, typ='float32', **kwds):

        self.faddr = faddr
        self.axesdict = OrderedDict()

        # Specify the symmetries of the band structure
        self.rot_sym_order = kwds.pop('rot_sym_order', 1) # Lowest rotational symmetry
        self.mir_sym_order = kwds.pop('mir_sym_order', 0) # No mirror symmetry

        # Initialization by loading data from an hdf5 file (details see mpes.fprocessing)
        if self.faddr is not None:
            hdfdict = fp.readBinnedhdf5(self.faddr, typ=typ)
            data = hdfdict.pop(datakey)

            for k, v in self.keypair.items():
                # When the file already contains the converted axes, read in directly
                try:
                    self.axesdict[v] = hdfdict[v]
                # When the file contains no converted axes, rename coordinates according to the keypair correspondence
                except:
                    self.axesdict[v] = hdfdict[k]

            super().__init__(data, coords=hdfdict, dims=hdfdict.keys(), **kwds)

        # Initialization by direct connection to existing data
        elif self.faddr is None:
            self.axesdict = coords
            super().__init__(data, coords=coords, dims=dims, **kwds)

        #setattr(self.data, 'datadim', self.data.ndim)
        #self['datadim'] = self.data.ndim

    def kcenter_estimate(self, threshold, dimname='E', method='centroid', view=False):
        """
        Estimate the momentum center (Gamma point) of the isoenergetic plane.
        """

        if dimname not in self.coords.keys():
            raise ValueError('Need to specify the name of the energy dimension if different from default (E)!')
        else:
            if method == 'centroid':
                pass
            elif method == 'peakfind':
                pass

            center = (0, 0)

            if view:
                pass

            return center

    def scale(self, axis, scale_array, update=True, ret=False):
        """
        Scaling and masking of band structure data.

        :Parameters:
            axis : str/tuple
                Axes along which to apply the intensity transform.
            scale_array : nD array
                Scale array to be applied to data.
            update : bool | True
                Options to update the existing array with the intensity-transformed version.
            ret : bool | False
                Options to return the intensity-transformed data.

        :Return:
            scdata : nD array
                Data after intensity scaling.
        """

        scdata = aly.apply_mask_along(self.data, mask=scale_array, axes=axis)

        if update:
            self.data = scdata

        if ret:
            return scdata

    def update_axis(self, axes=None, vals=None, axesdict=None):
        """
        Update the values of multiple axes.

        :Parameters:
            axes : list/tuple | None
                Collection of axis names.
            vals : list/tuple | None
                Collection of axis values.
            axesdict : dict | None
                Axis-value pair for update.
        """

        if axesdict:
            self.coords.update(axesdict)
        else:
            axesdict = dict(zip(axes, vals))
            self.coords.update(axesdict)

    @classmethod
    def resize(cls, data, axes, factor, method='mean', ret=True, **kwds):
        """
        Reduce the size (shape-changing operation) of the axis through rebinning.

        :Parameters:
            data : nD array
                Data to resize (e.g. self.data).
            axes : dict
                Axis values of the original data structure (e.g. self.coords).
            factor : list/tuple of int
                Resizing factor for each dimension (e.g. 2 means reduce by a factor of 2).
            method : str | 'mean'
                Numerical operation used for resizing ('mean' or 'sum').
            ret : bool | False
                Option to return the resized data array.

        :Return:
            binarr : nD array
                Resized n-dimensional array.
        """

        binarr = u.arraybin(data, factor, method=method)

        axesdict = OrderedDict()
        # DataArray sizes cannot be changed, need to create new class instance
        for i, (k, v) in enumerate(axes.items()):
            fac = factor[i]
            axesdict[k] = v[::fac]

        if ret:
            return cls(data=binarr, coords=axesdict, dims=axesdict.keys(), **kwds)

    def rotate(data, axis, update=True, ret=False):
        """
        Primary axis rotation.
        """

        # Slice out
        rdata = np.moveaxis(self.data, axis, 0)
        #data =
        rdata = np.moveaxis(self.data, 0, axis)

        if update:
            self.data = rdata
            # No change of axis values

        if ret:
            return rdata

    def orthogonalize(self, center, update=True, ret=False):
        """
        Align the high symmetry axes in the isoenergetic plane to the row and
        column directions of the image coordinate system.
        """

        pass

    def symmetrize(self, center, symtype, update=True, ret=False):
        """
        Symmetrize data within isoenergetic planes. Supports rotational and
        mirror symmetries.
        """

        if symtype == 'mirror':
            pass
        elif symtype == 'rotational':
            pass

        if update:
            pass

        if ret:
            return

    def _view_result(self):
        """
        2D visualization of temporary result.
        """

        pass

    def saveas(self, form='h5', save_addr='./'):

        pass


class MPESDataset(BandStructure):
    """
    Data structure for storage and manipulation of a multidimensional photoemission
    spectroscopy (MPES) dataset (4D and above).
    """

    def __init__(self, data=None, coords=None, dims=None, datakey='V', faddr=None, typ='float32', **kwds):

        self.faddr = faddr

        # Initialization by loading data from an hdf5 file
        if self.faddr is not None:
            hdfdict = fp.readBinnedhdf5(self.faddr, combined=True, typ=typ)
            data = hdfdict.pop(datakey)

            # Add other key pairs to the instance
            otherkp = kwds.pop('other_keypair', None)
            if otherkp:
                self.keypair = u.dictmerge(self.keypair, otherkp)

            for k, v in self.keypair.items():
                # When the file already contains the converted axes, read in directly
                try:
                    self.axesdict[v] = hdfdict[v]
                # When the file contains no converted axes, rename coordinates according to the keypair correspondence
                except:
                    self.axesdict[v] = hdfdict[k]

            super().__init__(data, coords=hdfdict, dims=hdfdict.keys(), **kwds)

        # Initialization by direct connection to existing data
        elif self.faddr is None:
            self.axesdict = coords
            super().__init__(data, coords=coords, dims=dims, **kwds)

    def gradient(self):

        pass

    def maxdiff(self):
        """
        Find the hyperslice with maximum difference from the specified one.
        """

        pass

    def subset(self, axis, axisrange):
        """
        Spawn an instance of the BandStructure class from axis slicing.

        :Parameters:
            axis : str/list
                Axes to subset from.
            axisrange : slice object/list
                The value range of axes to be sliced out.

        :Return:
            An instances of BandStructure, MPESDataset or DataArray class.
        """

        # Determine the remaining coordinate keys using set operations
        restaxes = set(self.coords.keys()) - set(axis)
        bsaxes = set(['kx', 'ky', 'E'])

        # Construct the subset data and the axes values
        axid = self.get_axis_num(axis)
        subdata = np.moveaxis(self.data, axid, 0)

        try:
            subdata = subdata[axisrange,...].mean(axis=0)
        except:
            subdata = subdata[axisrange,...]

        # Copy the correct axes values after slicing
        tempdict = deepcopy(self.axesdict)
        tempdict.pop(axis)

        # When the remaining axes are only a set of (kx, ky, E),
        # Create a BandStructure instance to contain it.
        if restaxes == bsaxes:
            bs = BandStructure(subdata, coords=tempdict, dims=tempdict.keys())

            return bs

        # When the remaining axes contain a set of (kx, ky, E) and other parameters,
        # Return an MPESDataset instance to contain it.
        elif bsaxes < restaxes:
            mpsd = MPESDataset(subdata, coords=tempdict, dims=tempdict.keys())

            return mpsd

        # When the remaining axes don't contain a full set of (kx, ky, E),
        # Create a normal DataArray instance to contain it.
        else:
            dray = DataArray(subdata, coords=tempdict, dims=tempdict.keys())

            return dray

    def saveas(self):

        pass
