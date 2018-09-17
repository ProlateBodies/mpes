#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
@author: R. Patrick Xian
"""

from __future__ import print_function, division
from . import utils as u
import numpy as np
import glob as g
import natsort as nts
import cv2
from silx.io import dictdump


class FileCollection(object):
    """ File collecting and sorting class.
    """

    def __init__(self, files=[], file_sorting=True, folder=None):

        self.sorting = file_sorting
        self.files = self._sort_terms(files, self.sorting)
        self.folder = folder

    def __add__(self, other):
        """ Append two FileCollection instances by combining the file names.
        """

        self.files = list(set(self.files) | set(other.files))
        self.folder = None

    def __iter__(self):

        for file in self.files:
            yield file

    @property
    def nfiles(self):
        """ Total number of loaded files.
        """

        return len(self.files)

    @property
    def fileID(self):
        """ The sequence IDs of the files.
        """

        return list(range(self.nfiles))

    @staticmethod
    def _sort_terms(terms, parameter):
        """
        Sort terms according to parameter value.

        :Parameters:
            terms : list
                List of terms (e.g. strings).
            parameter : bool
                Decision parameter for sorting.

        :Return:
            Sorted or unsorted terms.
        """

        if parameter == True:
            return nts.natsorted(terms)
        else:
            return terms

    def gather(self, identifier=r'/*.h5', f_start=None, f_end=None, f_step=1, file_sorting=True):
        """
        Gather files from a folder (specified at instantiation).

        :Parameters:
            identifier : str | r'/*.h5'
                File identifier used for glob.glob().
            f_start, f_end, f_step : int, int, int | None, None, 1
                Starting, ending file id and the step. Used to construct a file selector.
            file_sorting : bool | True
                Option to sort the files by their names.
        """

        f_start, f_end, f_step = u.intify(f_start, f_end, f_step)

        if self.folder is not None:
            self.files = g.glob(self.folder + identifier)

            if file_sorting == True:
                self.files = self._sort_terms(self.files, file_sorting)

            self.files = self.files[slice(f_start, f_end, f_step)]

        else:
            raise ValueError('No folder is specified!')

    def filter(self, wexpr=None, woexpr=None, str_start=None, str_end=None):
        """ Filter filenames by keywords.

        :Parameters:
            wexpr : str | None
                Expression in a name to leave in the filename list (w = with).
            woexpr : str | None
                Expression in a name to leave out of the filename list (wo = without).

        :Return:
            filteredFiles : list
                List of filtered filenames.
        """

        if (wexpr is None) and (woexpr is None):
            filteredFiles = self.files
        elif wexpr:
            filteredFiles = [i for i in self.files if wexpr in i[str_start:str_end]]
        elif woexpr:
            filteredFiles = [i for i in self.files if woexpr not in i[str_start:str_end]]

        return filteredFiles

    def select(self, ids=[], update='', ret='selected'):
        """ Select files by the filename id.

        :Parameters:
            ids : 1D array | []
                File IDs for selection.
            update : str | ''
                File address list update condition,
                'remove' = remove the selected files
                'keep' = keep the selected files and remove the rest
                others strings or no action = do nothing
            ret : str | 'selected'
                Return option,
                'selected' = return selected files
                'rest' = return the rest of the files (not selected)
        """

        if self.files:
            selectedFiles = list(map(self.files.__getitem__, ids))
            selectedFiles = self._sort_terms(selectedFiles, self.sorting)

            if update == 'remove':
                difflist = list(set(self.files) - set(selectedFiles))
                self.files = self._sort_terms(difflist, self.sorting)
            elif update == 'keep':
                self.files = selectedFiles

            if ret == 'selected':
                return selectedFiles
            elif ret == 'rest':
                return self.files

        else:
            raise ValueError('No files addresses are gathered!')


class MapParser(FileCollection):
    """ Parser of recorded parameters and turn into functional maps.
    """

    def __init__(self, files=[], file_sorting=True, folder=None, **kwds):

        super().__init__(files=files, file_sorting=file_sorting, folder=folder)

    @property
    def kfile(self, **kwds):
        """ File containing the momentum correction and calibration information.
        """

        fstr_k = kwds.pop('filestring_momentum', 'momentum.')
        return self.filter(wexpr=fstr_k)

    @property
    def Efile(self, **kwds):
        """ File containing the energy calibration information.
        """

        fstr_E = kwds.pop('filestring_energy', 'energy.')
        return self.filter(wexpr=fstr_E)

    def parse_kmap(self):
        """ Retrieve the parameters to construct the momentum conversion function.
        """

        self.fr, self.fc = dictdump.load(self.kfile)['calibration']['coeffs']

    def parse_Emap(self):
        """ Retrieve the parameters to construct the energy conversion function.
        """

        self.coeffs = dictdump.load(self.Efile)['coeffs']

    def parse_wmap(self):
        """ Retrieve the parameters to construct the distortion correction function
        """

        self.warping = dictdump.load(self.kfile)['warping']

    @staticmethod
    def parse(parse_map):
        """ Parse map parameters stored in files.
        """

        try:
            parse_map()
            return 1 # Retrieved mapping parameters successfully
        except:
            return 0 # Failed to retrieve parameters

    @staticmethod
    def mapConstruct(mapfunc, **kwds):
        """ Construct mapping function.
        """

        return partial(mapfunc, **kwds)

    @property
    def kMap(self, **kwds):
        """ The (row, column) to momentum coordinate transform function.
        """

        ret = self.parse(self.parse_kmap)
        if ret == 1:

            kmap = kwds.pop('map', kmap_rc)
            if kwds: # Parse other remaining keyword arguments
                return self.mapConstruct(kmap, **kwds)
            else:
                return self.mapConstruct(kmap, fr=self.fr, fc=self.fc)

        else:
            return None

    @property
    def Emap(self, **kwds):
        """ The ToF to energy coordinate transform function.
        """

        ret = self.parse(self.parse_Emap)
        if ret == 1:

            Emap = kwds.pop('map', tof2evpoly)
            if kwds: # Parse other remaining keyword arguments
                return self.mapConstruct(Emap, **kwds)
            else:
                return self.mapConstruct(Emap, a=self.poly_a)

        else:
            return None

    @property
    def wmap(self, **kwds):
        """ The distortion correction transform function.
        """

        ret = self.parse(self.parse_wmap)
        if ret == 1:

            wmap = kwds.pop('map', correctnd)
            if kwds: # Parse other remaining keyword arguments
                return self.mapConstruct(wmap, **kwds)
            else:
                return self.mapConstruct(wmap, warping=self.warping)

        else:
            return None


def tof2evpoly(a, E0, t):
    """
    Polynomial approximation of the time-of-flight to electron volt
    conversion formula.

    :Parameters:
        a : 1D array
            Polynomial coefficients.
        E0 : float
            Energy offset.
        t : numeric array
            Drift time of electron.

    :Return:
        E : numeric array
            Converted energy
    """

    odr = len(a) # Polynomial order
    a = a[::-1]
    E = 0

    for i, d in enumerate(range(1, odr+1)):
        E += a[i]*t**d
    E += E0

    return E


def kmap_xy(x, y, x0, y0, fx, fy):
    """
    Conversion from Cartesian coordinate (x, y) to momentum coordinate.
    """

    kx = fx * (x - x0)
    ky = fy * (y - y0)

    return (kx, ky)


def kmap_rc(r, c, r0, c0, fr, fc):
    """
    Conversion from image coordinate (row, column) to momentum coordinate.
    """

    kr = fr * (r - r0)
    kc = fc * (c - c0)

    return (kr, kc)


def reshape2d(data, apply_axis):
    """ Reshape matrix to apply 2D function to.
    """

    nax = len(apply_axis)
    dshape = data.shape
    dim_rest = tuple(set(range(data.ndim)) - set(apply_axis))
    shapedict = dict(enumerate(dshape))

    # Calculate the matrix dimension to reshape original data into
    reshapedict = {}
    for ax in apply_axis:
        reshapedict[ax] = dshape[ax]

    squeezed_dim = 1
    for dr in dim_rest:
        squeezed_dim *= shapedict[dr]
    reshapedict[nax+1] = squeezed_dim

    reshape_dims = tuple(reshapedict.values())
    data = data.reshape(reshape_dims)

    return data


def mapping(data, f, **kwds):
    """ Mapping a generic function to multidimensional data with
    the possibility to supply keyword arguments.
    """

    result = np.asarray(list(map(lambda x:f(x, **kwds), data)))

    return result


def correctnd(data, warping, func=cv2.warpPerspective, **kwds):
    """ Apply a 2D transform to 2D in n-dimensional data.
    """

    apply_axis = kwds.pop('apply_axis', (0, 1))
    dshape = data.shape
    dsize = kwds.pop('dsize', op.itemgetter(*apply_axis)(dshape))

    # Reshape data
    redata = reshape2d(data, apply_axis)
    redata = np.moveaxis(redata, 2, 0)
    redata = mapping(redata, func, M=warping, dsize=dsize, **kwds)
    redata = np.moveaxis(redata, 0, 2).reshape(dshape)

    return redata
