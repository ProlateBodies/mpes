#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
@author: R. Patrick Xian
"""
# =========================
# Sections:
# 1.  Utility functions
# 2.  File I/O and parsing
# 3.  Data transformation
# =========================

from __future__ import print_function, division
import numpy as np
import pandas as pd
import re, glob2 as g
import numpy.fft as nft
from scipy.interpolate import interp1d
from numpy import polyval as poly
from scipy.signal import savgol_filter
import igor.igorpy as igor
from .igoribw  import loadibw
from PIL import Image as pim
import skimage.io as skio
import scipy.io as sio
from h5py import File
import psutil as ps
import dask as d, dask.array as da
from dask.diagnostics import ProgressBar
import warnings as wn
from tqdm import tqdm
import natsort as nts

N_CPU = ps.cpu_count()

# ================= #
# Utility functions #
# ================= #

def find_nearest(val, narray):
    """
    Find the value closest to a given one in a 1D array

    **Parameters**

    val : float
        Value of interest
    narray : 1D numeric array
        array to look for the nearest value

    **Return**

    ind : int
        index of the value nearest to the sepcified
    """

    return np.argmin(np.abs(narray - val))


def sgfltr2d(datamat, span, order, axis=0):
    """
    Savitzky-Golay filter for two dimensional data
    Operated in a line-by-line fashion along one axis
    Return filtered data
    """

    dmat = np.rollaxis(datamat, axis)
    r, c = np.shape(datamat)
    dmatfltr = np.copy(datamat)
    for rnum in range(r):
        dmatfltr[rnum, :] = savgol_filter(datamat[rnum, :], span, order)

    return np.rollaxis(dmatfltr, axis)


def sortNamesBy(namelist, pattern, gp=0, slicerange=(None, None)):
    """
    Sort a list of names according to a particular sequence of numbers
    (specified by a regular expression search pattern)

    Parameters

    namelist : str
        List of name strings
    pattern : str
        Regular expression of the pattern
    gp : int
        Grouping number

    Returns

    orderedseq : array
        Ordered sequence from sorting
    sortednamelist : str
        Sorted list of name strings
    """

    gp = int(gp)
    sa, sb = slicerange

    # Extract a sequence of numbers from the names in the list
    seqnum = np.array([re.search(pattern, namelist[i][sa:sb]).group(gp)
                       for i in range(len(namelist))])
    seqnum = seqnum.astype(np.float)

    # Sorted index
    idx_sorted = np.argsort(seqnum)

    # Sort the name list according to the specific number of interest
    sortednamelist = [namelist[i] for i in idx_sorted]

    # Return the sorted number sequence and name list
    return seqnum[idx_sorted], sortednamelist


def rot2d(th, angle_unit):
    """
    construct 2D rotation matrix
    """

    if angle_unit == 'deg':
        thr = np.deg2rad(th)
        return np.array([[np.cos(thr), -np.sin(thr)],
                         [np.sin(thr), np.cos(thr)]])

    elif angle_unit == 'rad':
        return np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])


def binarysearch(arr, val):
    """
    Equivalent to BinarySearch(waveName, val) in Igor Pro, the sorting order is determined automatically
    """

    sortedarr = np.sort(arr)
    if np.array_equal(arr, sortedarr):
        return np.searchsorted(arr, val, side='left') - 1
    elif np.array_equal(arr, sortedarr[::-1]):
        return np.size(arr) - np.searchsorted(arr[::-1], val, side='left') - 1


def searchinterp(arr, val):
    """
    Equivalent to BinarySearchInterp(waveName, val) in Igor Pro, the sorting order is determined automatically
    """

    indstart = binarysearch(arr, val)
    indstop = indstart + 1
    indarray = np.array([indstart, indstop])
    finterp = interp1d(arr[indstart:indstop + 1], indarray, kind='linear')

    return finterp(val) + 0  # +0 because of data type conversion


def linterp(xind, yarr, frac):
    """
    Linear interpolation
    """

    return yarr[xind] * (1 - frac) + yarr[xind + 1] * frac


# ====================== #
#  File I/O and parsing  #
# ====================== #

def readimg(f_addr):
    """
    Read images (jpg, png, 2D/3D tiff)
    """

    return skio.imread(f_addr)


def readtsv(fdir, header=None, dtype='float', **kwds):
    """
    Read tsv file from hemispherical detector

    **Parameters**

    fdir : str
        file directory
    header : int | None
        number of header lines
    dtype : str | 'float'
        data type of the return numpy.ndarray
    **kwds : keyword arguments
        other keyword arguments for pandas.read_table()

    **Return**

    data : numpy ndarray
        read and type-converted data
    """

    data = np.asarray(pd.read_table(fdir, delim_whitespace=True, \
                      header=None, **kwds), dtype=dtype)
    return data


def readIgorBinFile(fdir, **kwds):
    """
    Read Igor binary formats (pxp and ibw)
    """

    ftype = kwds.pop('ftype', fdir[-3:])
    errmsg = "Error in file loading, please check the file format."

    if ftype == 'pxp':

        try:
            igfile = igor.load(fdir)
        except IOError:
            print(errmsg)

    elif ftype == 'ibw':

        try:
            igfile = loadibw(fdir)
        except IOError:
            print(errmsg)

    else:

        raise IOError(errmsg)

    return igfile


def readARPEStxt(fdir, withCoords=True):
    """
    Read and convert Igor-generated ARPES .txt files into numpy arrays
    The withCoords option specify whether the energy and angle information is given
    """

    if withCoords:

        # Retrieve the number of columns in the txt file
        dataidx = pd.read_table(fdir, skiprows=1, header=None).columns
        # Read all data with the specified columns
        datamat = pd.read_table(fdir, skiprows=0, header=None, names=dataidx)
        # Shift the first row by one value (align the angle axis)
        #datamat.iloc[0] = datamat.iloc[0].shift(1)

        ARPESData = datamat.loc[1::, 1::].values
        EnergyData = datamat.loc[1::, 0].values
        AngleData = datamat.loc[0, 1::].values

        return ARPESData, EnergyData, AngleData

    else:

        ARPESData = np.asarray(pd.read_table(fdir, skiprows=1, header=None))

        return ARPESData


def txtlocate(ffolder, keytext):
    """
    Locate specific txt files containing experimental parameters
    """

    txtfiles = g.glob(ffolder + r'\*.txt')
    for ind, fname in enumerate(txtfiles):
        if keytext in fname:
            txtfile = txtfiles[ind]

    return txtfile


def appendformat(filepath, form):
    """
    Append a format string to the end of a file path

    :Parameters:
        filepath : str
            File path of interest
        form : str
            File format of interest
    """

    format_string = '.'+form
    if filepath:
        if not filepath.endswith(format_string):
            filepath += format_string

    return filepath


def parsenum(
        NumberPattern,
        strings,
        CollectorList,
        linenumber,
        offset=0,
        Range='all'):
    """
    Number parser for reading calibration file
    """

    # Specify Range as 'all' to take all numbers, specify number limits to
    # pick certain number
    numlist = re.findall(NumberPattern, strings[linenumber + offset])
    if Range == 'all':
        CollectorList.append(numlist)
    else:
        Rmin, Rmax = re.split(':', Range)
        # One-sided slicing with max value specified in number
        if Rmin == 'min':
            CollectorList.append(numlist[:int(Rmax)])
        # One-sided slicing with min value specified in number
        elif Rmax == 'max':
            CollectorList.append(numlist[int(Rmin):])
        # Two-sided slicing with bothe min and max specified in number
        else:
            CollectorList.append(numlist[int(Rmin):int(Rmax)])

    return CollectorList


def readLensModeParameters(calibfiledir, lensmode='WideAngleMode'):
    """
    Retrieve the calibrated lens correction parameters
    """

    # For wide angle mode
    if lensmode == 'WideAngleMode':

        LensModeDefaults, LensParamLines = [], []
        with open(calibfiledir, 'r') as fc:

            # Read the full file as a line-split string block
            calib = fc.read().splitlines()
            # Move read cursor back to the beginning
            fc.seek(0)
            # Scan through calibration file, find and append line indices
            # (lind) to specific lens settings
            for lind, line in enumerate(fc):
                if '[WideAngleMode defaults' in line:
                    LensModeDefaults.append(lind)
                elif '[WideAngleMode@' in line:
                    LensParamLines.append(lind)

        # Specify regular expression pattern for retrieving numbers
        numpattern = r'[-+]?\d*\.\d+|[-+]?\d+'

        # Read detector settings at specific lens mode
        aRange, eShift = [], []
        for linum in LensModeDefaults:

            # Collect the angular range
            aRange = parsenum(
                numpattern,
                calib,
                aRange,
                linenumber=linum,
                offset=2,
                Range='all')
            # Collect the eShift
            eShift = parsenum(
                numpattern,
                calib,
                eShift,
                linenumber=linum,
                offset=3,
                Range='all')

        # Read list calibrated Da coefficients at all retardation ratios
        rr, aInner, Da1, Da3, Da5, Da7 = [], [], [], [], [], []
        for linum in LensParamLines:

            # Collect the retardation ratio (rr)
            rr = parsenum(
                numpattern,
                calib,
                rr,
                linenumber=linum,
                offset=0,
                Range='all')
            # Collect the aInner coefficient
            aInner = parsenum(
                numpattern,
                calib,
                aInner,
                linenumber=linum,
                offset=1,
                Range='all')
            # Collect Da1 coefficients
            Da1 = parsenum(
                numpattern,
                calib,
                Da1,
                linenumber=linum,
                offset=2,
                Range='1:4')
            # Collect Da3 coefficients
            Da3 = parsenum(
                numpattern,
                calib,
                Da3,
                linenumber=linum,
                offset=3,
                Range='1:4')
            # Collect Da5 coefficients
            Da5 = parsenum(
                numpattern,
                calib,
                Da5,
                linenumber=linum,
                offset=4,
                Range='1:4')
            # Collect Da7 coefficients
            Da7 = parsenum(
                numpattern,
                calib,
                Da7,
                linenumber=linum,
                offset=5,
                Range='1:4')

        aRange, eShift, rr, aInner = list(map(lambda x: np.asarray(
            x, dtype='float').ravel(), [aRange, eShift, rr, aInner]))
        Da1, Da3, Da5, Da7 = list(
            map(lambda x: np.asarray(x, dtype='float'), [Da1, Da3, Da5, Da7]))

        return aRange, eShift, rr, aInner, Da1, Da3, Da5, Da7

    else:
        print('This mode is currently not supported!')


def mat2im(datamat, dtype='uint8', scaling=['normal'], savename=None):
    """
    Convert data matrix to image
    """

    dataconv = np.abs(np.asarray(datamat))
    for scstr in scaling:
        if 'gamma' in scstr:
            gfactors = re.split('gamma|-', scstr)[1:]
            gfactors = u.numFormatConversion(gfactors, form='float', length=2)
            dataconv = gfactors[0]*(dataconv**gfactors[1])

    if 'normal' in scaling:
        dataconv = (255 / dataconv.max()) * (dataconv - dataconv.min())
    elif 'inv' in scaling and 'normal' not in scaling:
        dataconv = 255 - (255 / dataconv.max()) * (dataconv - dataconv.min())

    if dtype == 'uint8':
        imrsc = dataconv.astype(np.uint8)
    im = pim.fromarray(imrsc)

    if savename:
        im.save(savename)
    return im


def im2mat(fdir):
    """
    Convert image to numpy ndarray
    """

    mat = np.asarray(pim.open(fdir))
    return mat


class hdf5Reader(File):
    """ HDF5 reader class
    """

    def __init__(self, f_addr, **kwds):

        self.faddress = f_addr
        super().__init__(name=self.faddress, mode='r', **kwds)

        self.groupNames = list(self)
        self.groupAliases = [self.readAttribute(self[gn], 'Name', nullval=gn) for gn in self.groupNames]
        # Initialize the look-up dictionary between group aliases and group names
        self.nameLookupDict = dict(zip(self.groupAliases, self.groupNames))
        self.attributeNames = list(self.attrs)

    def getGroupNames(self, wexpr=None, woexpr=None):
        """ Retrieve group names from the loaded hdf5 file with string filtering

        :Parameters:
            wexpr : str | None
                Expression in a name to leave in the group name list (w = with).
            woexpr : str | None
                Expression in a name to leave out of the group name list (wo = without).

        :Return:
            filteredGroupNames : list
                List of filtered group names
        """

        if (wexpr is None) and (woexpr is None):
            filteredGroupNames = self.groupNames
        elif wexpr:
            filteredGroupNames = [i for i in self.groupNames if wexpr in i]
        elif woexpr:
            filteredGroupNames = [i for i in self.groupNames if woexpr not in i]

        return filteredGroupNames

    def getAttributeNames(self, wexpr=None, woexpr=None):
        """ Retrieve attribute names from the loaded hdf5 file with string filtering

        :Parameters:
            wexpr : str | None
                Expression in a name to leave in the attribute name list (w = with).
            woexpr : str | None
                Expression in a name to leave out of the attribute name list (wo = without).

        :Return:
            filteredAttrbuteNames : list
                List of filtered attribute names
        """

        if (wexpr is None) and (woexpr is None):
            filteredAttributeNames = self.attributeNames
        elif wexpr:
            filteredAttributeNames = [i for i in self.attributeNames if wexpr in i]
        elif woexpr:
            filteredAttributeNames = [i for i in self.attributeNames if woexpr not in i]

        return filteredAttributeNames

    @staticmethod
    def readGroup(element, *group, amin=None, amax=None, sliced=True):
        """ Retrieve the content of the group(s) in the loaded hdf5 file

        :Parameter:
            group : list/tuple
                Collection of group names

        :Return:
            groupContent : list/tuple
                Collection of values of the corresponding groups
        """

        ngroup = len(group)
        groupContent = []
        for g in group:
            try:
                if sliced:
                    groupContent.append(element.get(g)[slice(amin, amax)])
                else:
                    groupContent.append(element.get(g))
            except:
                raise ValueError("Group '"+g+"' doesn't have sufficient length for slicing!")

        if ngroup == 1: # Singleton case
            groupContent = groupContent[0]

        return groupContent

    @staticmethod
    def readAttribute(element, *attribute, nullval='None'):
        """ Retrieve the content of the attribute(s) in the loaded hdf5 file

        :Parameter:
            attribute : list/tuple
                Collection of attribute names

        :Return:
            attributeContent : list/tuple
                Collection of values of the corresponding attributes
        """

        nattr = len(attribute)
        attributeContent = []
        for ab in attribute:
            try:
                attributeContent.append(element.attrs[ab].decode('utf-8'))
            except AttributeError: # No need to decode
                attributeContent.append(element.attrs[ab])
            except KeyError: # No such an attribute
                attributeContent.append(nullval)

        if nattr == 1:
            attributeContent = attributeContent[0]

        return attributeContent

    def summarize(self, output='text', use_alias=True, **kwds):
        """ Summarize the content of the hdf5 file (names of the groups,
        attributes and the selected contents. Output by print or as a dictionary.)

        :Parameters:
            output : str | 'text'
                Output format, available options are 'text' and 'dict'.
            use_alias : bool | True
                Specify if to use the alias to rename the groups

        :Return:
            hdfdict : dict
                Dictionary constructed if output format is set to 'dict'.
        """

        if output == 'text':
            # Output as printed text
            print('*** HDF5 file info ***\n', \
                  'File address = ' + self.faddress + '\n')

            # Output info on attributes
            print('\n>>> Attributes <<<\n')
            for an in self.attributeNames:
                print(an + ' = {}'.format(self.readAttribute(self, an)))

            # Output info on groups
            print('\n>>> Groups <<<\n')
            for gn in self.groupNames:

                g_dataset = self.readGroup(self, gn, sliced=False)
                g_shape = g_dataset.shape
                g_alias = self.readAttribute(g_dataset, 'Name')

                print(gn + ', Shape = {}, Alias = {}'.format(g_shape, g_alias))

        elif output == 'dict':

            # Retrieve the range of acquired events
            amin = kwds.pop('amin', None)
            amax = kwds.pop('amax', None)

            # Output as a dictionary
            # Attribute name stays, stream_x rename as their corresponding attribute name
            hdfdict = {}

            # Add attributes to dictionary
            for an in self.attributeNames:

                hdfdict[an] = self.readAttribute(self, an)

            # Add groups to dictionary
            for gn in self.groupNames:

                g_dataset = self.readGroup(self, gn, sliced=False)
                g_values = g_dataset[slice(amin, amax)]

                # Use the group alias as the dictionary key
                if use_alias == True:
                    g_name = self.readAttribute(g_dataset, 'Name', nullval=gn)
                    hdfdict[g_name] = g_values
                # Use the group name as the dictionary key
                else:
                    hdfdict[gn] = g_values

            return hdfdict

    def convert(self, form, save_addr='./summary', **kwds):
        """ Format conversion from hdf5 to mat (for Matlab/Python) or ibw (for Igor)

        :Parameters:
            form : str
                The format of the data to convert into.
            save_addr : str | './summary'
                File address to save to.
        """

        save_addr = appendformat(save_addr, form)

        if form == 'mat': # Save as mat file
            hdfdict = self.summarize(output='dict', **kwds)
            sio.savemat(save_addr, hdfdict)

        elif form == 'ibw':
        # TODO: Save in igor ibw format
            raise NotImplementedError

        else:
            raise NotImplementedError


def saveDict(processor, dictname, form='h5', save_addr='./histogram', **kwds):
    """ Save the binning result dictionary, including the histogram and the
    axes values (edges or midpoints).

    :Parameters:
        processor : class
            Class including all attributes
        dictname : str
            Namestring of the dictionary to save (such as the attribute name in a class)
        form : str | 'h5'
            Save format, supporting 'mat', 'h5', 'tiff' (need tifffile) or 'png' (need imageio)
        save_addr : str | './histogram'
            File path to save the binning result
        **kwds : keyword arguments
            =========  ===========  ===========  ========================================
             keyword    data type     default     meaning
            =========  ===========  ===========  ========================================
              dtyp       string      'float32'    data type of the histogram
             cutaxis      int            3        the axis to cut the 4D data in
            slicename    string         'V'       the shared namestring for the 3D slice
            =========  ===========  ===========  ========================================
    """

    histdict = getattr(processor, dictname)
    dtyp = kwds.pop('dtyp', 'float32')
    sln = kwds.pop('slicename', 'V')
    save_addr = appendformat(save_addr, form)

    if form == 'mat': # Save as mat file (for Matlab)

        sio.savemat(save_addr, histdict)

    elif form == 'h5': # Save as hdf5 file

        cutaxis = kwds.pop('cutaxis', 3)

        # Save the binned data
        # Save 1-3D data as single datasets
        try:
            hdf = File(save_addr, 'w')
            if processor.nbinaxes < 4:
                hdf.create_dataset('binned/'+sln, data=histdict['binned'])
            # Save 4D data as a list of separated 3D datasets
            elif processor.nbinaxes == 4:
                nddata = np.rollaxis(histdict['binned'], cutaxis)
                n = nddata.shape[0]
                for i in range(n):
                    hdf.create_dataset('binned/'+sln+str(i), data=nddata[i,...])
            else:
                raise NotImplementedError('The output format is undefined for data\
                with higher than four dimensions!')

            # Save the axes in the same group
            for k in processor.binaxes:
                hdf.create_dataset('axes/'+k, data=histdict[k])

        finally:
            hdf.close()

    elif form == 'tiff': # Save as tiff stack

        try:
            import tifffile as ti
            ti.imsave(save_addr, data=histdict['binned'].astype(dtyp))
        except ImportError:
            raise ImportError('tifffile package is not installed locally!')

    elif form == 'png': # Save as png for slices

        import imageio as imio
        cutaxis = kwds.pop('cutaxis', 2)

        if processor.nbaxes == 2:
            imio.imwrite(save_addr[:-3]+'.png', histdict['binned'], format='png')
        if processor.nbinaxes == 3:
            nddata = np.rollaxis(histdict['binned'], cutaxis)
            n = nddata.shape[0]
            for i in range(n):
                wn.simplefilter('ignore', UserWarning)
                imio.imwrite(save_addr[:-3]+'_'+str(i)+'.png', nddata[i,...], format='png')

        elif processor.nbinaxes >= 4:
            raise NotImplementedError('The output format is undefined for data\
            with higher than three dimensions!')

    elif form == 'ibw': # Save as Igor wave

        from igorwriter import IgorWave
        wave = IgorWave(histdict['binned'], name='binned')
        wave.save(save_addr)

    else:
        raise NotImplementedError('Not implemented output format!')


class hdf5Processor(hdf5Reader):
    """ Class for generating multidimensional histogram from hdf5 files
    """

    def __init__(self, f_addr, ncores=None, **kwds):

        self.faddress = f_addr
        self.ua = kwds.pop('use_alias', True)
        self.hdfdict = {}
        self.histdict = {}
        super().__init__(f_addr=self.faddress, **kwds)

        if (ncores is None) or (ncores > N_CPU) or (ncores < 0):
            self.ncores = N_CPU
        else:
            self.ncores = int(ncores)

    def _addBinners(self, axes=None, nbins=None, ranges=None, binDict=None):
        """
        Construct the binning parameters within an instance
        """

        # Use information specified in binDict, ignore others
        if binDict is not None:
            try:
                self.binaxes = binDict['axes']
                self.nbinaxes = len(self.binaxes)
                self.bincounts = binDict['nbins']
                self.binranges = binDict['ranges']
            except:
                pass
        # Use information from other specified parameters if binDict is not given
        else:
            self.binaxes = axes
            self.nbinaxes = len(self.binaxes)

            # Collect the number of bins
            try: # To have the same number of bins on all axes
                self.bincounts = int(nbins)
            except: # To have different number of bins on each axis
                self.bincounts = list(map(int, nbins))

            self.binranges = ranges

    @staticmethod
    def _int(*nums):
        """ Safely convert to integer (avoiding None)
        """

        intnums = list(nums) # Make a copy of the to-be-converted list
        for i, num in enumerate(nums):
            try:
                intnums[i] = int(num)
            except TypeError:
                pass

        return intnums

    @d.delayed
    def _delayedBinning(self, data):
        """
        Lazily evaluated multidimensional binning

        :Parameters:
            data : numpy array
                Data to bin.

        :Returns:
            hist : numpy array
                Binned histogram.
            edges : list of numpy array
                Bins along each axis of the histogram.
        """

        hist, edges = np.histogramdd(data, bins=self.bincounts, range=self.binranges)

        return hist, edges

    def distributedBinning(self, axes=None, nbins=None, ranges=None, \
                           binDict=None, chunksz=100000, ret=True, **kwds):
        """
        Compute the photoelectron intensity histogram in the distributed way.

        :Paramters:
            axes : (list of) strings | None
                Names the axes to bin.
            nbins : (list of) int | None
                Number of bins along each axis.
            ranges : (list of) tuples | None
                Ranges of binning along every axis.
            binDict : dict | None
                Dictionary with specifications of axes, nbins and ranges. If binDict
                is not None. It will override the specifications from other arguments.
            chunksz : numeric (single numeric or tuple)
                Size of the chunk to distribute.
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.

        :Return:
            histdict : dict
                Dictionary containing binned data and the axes values (if `ret = True`).

        """

        # Retrieve the range of acquired events
        amin = kwds.pop('amin', None)
        amax = kwds.pop('amax', None)
        amin, amax = self._int(amin, amax)

        # Set up the binning parameters
        self._addBinners(axes, nbins, ranges, binDict)

        # Assemble the data to bin in a distributed way
        if (amin is None) and (amax is None):
            dsets = [self[self.nameLookupDict[ax]] for ax in axes]
        else:
            dsets = [self[self.nameLookupDict[ax]][slice(amin, amax)] for ax in axes]
        dsets_distributed = [da.from_array(ds, chunks=(chunksz)) for ds in dsets]
        data_unbinned = da.stack(dsets_distributed, axis=1)
        # if rechunk:
        #     data_unbineed = data_unbinned.rechunk('auto')

        # Compute binned data
        bintask = self._delayedBinning(self, data_unbinned)
        with ProgressBar():
            self.histdict['binned'], ax_vals = bintask.compute()

        for iax, ax in enumerate(axes):
            self.histdict[ax] = ax_vals[iax]

        if ret:
            return self.histdict

    def localBinning(self, axes=None, nbins=None, ranges=None, binDict=None, \
                     jittered=False, histcoord='midpoint', ret=True, **kwds):
        """
        Compute the photoelectron intensity histogram locally after loading all data into RAM.

        :Paramters:
            axes : (list of) strings | None
                Names the axes to bin.
            nbins : (list of) int | None
                Number of bins along each axis.
            ranges : (list of) tuples | None
                Ranges of binning along every axis.
            binDict : dict | None
                Dictionary with specifications of axes, nbins and ranges. If binDict
                is not None. It will override the specifications from other arguments.
            jittered : bool | False
                Determines whether to add jitter to the data to avoid rebinning artefact.
            histcoord : string | 'midpoint'
                The coordinates of the histogram. Specify 'edge' to get the bar edges (every
                dimension has one value more), specify 'midpoint' to get the midpoint of the
                bars (same length as the histogram dimensions).
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.
            **kwds : keyword argument
                ================  ==============  ===========  ========================================
                     keyword         data type      default     meaning
                ================  ==============  ===========  ========================================
                     amin          numeric/None      None       minimum value of electron sequence
                     amax          numeric/None      None       maximum value of electron sequence
                  jitter_axes          list          axes       list of axes to jitter
                  jitter_bins          list          nbins      list of the number of bins
                jitter_amplitude       list       [0.5, ...]    list of the jitter amplitude
                 jitter_ranges         list         ranges      list of the binning ranges
                ================  ==============  ===========  ========================================

        :Return:
            histdict : dict
                Dictionary containing binned data and the axes values (if `ret = True`).
        """

        # Retrieve the range of acquired events
        amin = kwds.pop('amin', None)
        amax = kwds.pop('amax', None)
        amin, amax = self._int(amin, amax)

        # Assemble the data for binning, assuming they can be completely loaded into RAM
        self.hdfdict = self.summarize(output='dict', use_alias=self.ua, amin=amin, amax=amax)

        # Set up binning parameters
        self._addBinners(axes, nbins, ranges, binDict)

        # Add jitter to the data streams before binning
        if jittered:

            # Retrieve parameters for histogram jittering, the ordering of the jittering
            # parameters is the same as that for the binning
            jitter_axes = kwds.pop('jitter_axes', axes)
            jitter_bins = kwds.pop('jitter_bins', nbins)
            jitter_amplitude = kwds.pop('jitter_amplitude', 0.5*np.ones(self.nbinaxes))
            jitter_ranges = kwds.pop('jitter_ranges', ranges)

            # Add jitter to every dimension of the data
            for jb, jax, jamp, jr in zip(jitter_bins, jitter_axes, jitter_amplitude, jitter_ranges):

                sz = self.hdfdict[jax].size
                # Calculate the bar size of the histogram in every dimension
                binsize = abs(jr[0] - jr[1])/jb

                self.hdfdict[jax] = self.hdfdict[jax].astype('float32')
                self.hdfdict[jax] += jamp * binsize * np.random.\
                uniform(low=-1, high=1, size=sz).astype('float32')

        # Stack up data from unbinned axes
        data_unbinned = np.stack((self.hdfdict[ax] for ax in axes), axis=1)

        # Compute binned data locally
        self.histdict['binned'], ax_vals = \
        np.histogramdd(data_unbinned, bins=self.bincounts, range=self.binranges)

        for iax, ax in enumerate(axes):
            if histcoord == 'midpoint':
                ax_edge = ax_vals[iax]
                ax_midpoint = (ax_edge[1:] + ax_edge[:-1])/2
                self.histdict[ax] = ax_midpoint
            elif histcoord == 'edge':
                self.histdict[ax] = ax_vals[iax]

        if ret:
            return self.histdict

    def updateHistogram(self, axes=None, sliceranges=None, ret=False):
        """
        Update the size of the binning results
        """

        # Input axis order to binning axes order
        binaxes = np.asarray(self.binaxes)
        seqs = [np.where(ax == binaxes)[0][0] for ax in axes]

        for seq, ax, rg in zip(seqs, axes, sliceranges):
            # Update the lengths of binning axes
            seq = np.where(ax == binaxes)[0][0]
            self.histdict[ax] = self.histdict[ax][rg[0]:rg[1]]

            # Update the binned histogram
            tempmat = np.moveaxis(self.histdict['binned'], seq, 0)[rg[0]:rg[1],...]
            self.histdict['binned'] = np.moveaxis(tempmat, 0, seq)

        if ret:
            return self.histdict

    def saveHistogram(self, form='h5', save_addr='./histogram', **kwds):

        try:
            saveDict(self, dictname='histdict', form=form, save_addr=save_addr, **kwds)
        except:
            raise Exception('Saving histogram was unsuccessful!')


class hdf5Splitter(hdf5Reader):
    """
    Class to split large hdf5 files
    """

    def __init__(self, f_addr, **kwds):

        self.faddress = f_addr
        self.splitFilepaths = []
        super().__init__(f_addr=self.faddress, **kwds)

    def split(self, nsplit, save_addr='./', namestr='split_', \
    split_group='Stream_0', pbar=False):
        """
        Split and save an hdf5 file

        :Parameters:
            nsplit : int
                Number of split files
            save_addr : str | './'
                Directory to store the split files
            namestr : str | 'split_'
                Additional namestring attached to the front of the filename
            split_group : str | 'Stream_0'
                Name of the example group to split for file length reference
            pbar : bool | False
                Enable (when True)/Disable (when False) the progress bar
        """

        nsplit = int(nsplit)
        self.splitFilepaths = []
        self.eventLen = self[split_group].size
        self.eventList = np.linspace(0, self.eventLen, nsplit+1, dtype='int')

        for i in tqdm(range(nsplit), disable=not(pbar)):

            evmin, evmax = self.eventList[i], self.eventList[i+1]
            fpath = save_addr + namestr + str(i+1) + '.h5'
            self.splitFilepaths.append(fpath)

            try:
                fsp = File(fpath, 'w')

                # Copy the attributes
                for attr, attrval in self.attrs.items():
                    fsp.attrs[attr] = attrval

                # Copy the segmented groups and their attributes
                for gp in self.groupNames:
                    #self.copy(gn, fsp[gn])
                    fsp.create_dataset(gp, data=self.readGroup(self, gp, amin=evmin, amax=evmax))
                    for gattr, gattrval in self[gp].attrs.items():
                        fsp[gp].attrs[gattr] = gattrval

            except Exception as e:
                print(e)

            # Save and close the file
            finally:
                fsp.close()


class parallelHDF5Processor(object):
    """
    Class for parallel processing of hdf5 files
    """

    def __init__(self, files):

        self.files = files
        self.nfiles = len(self.files)
        self.results = {}
        self.combinedresult = {}

    def parallelBinning(self, axes, nbins, ranges, scheduler='threads',\
    pbar=True, ret=True, binning_kwds={}, compute_kwds={}):
        """
        Parallel computation of the multidimensional histogram from file segments

        :Parameters:
            axes : (list of) strings | None
                Names the axes to bin.
            nbins : (list of) int | None
                Number of bins along each axis.
            ranges : (list of) tuples | None
                Ranges of binning along every axis.
            scheduler : str | 'threads'
                Type of distributed scheduler ('threads', 'processes', 'synchronous')
            pbar : Bool | true
                Whether to show the progress bar
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.
            binning_kwds : dict | {}
                keyword arguments to be included in hdf5Processor.localBinning()
            compute_kwds : dict | {}
                keyword arguments to specify in dask.computer()

        """

        binTasks = []
        self.binaxes = axes
        self.nbinaxes = len(axes)
        self.bincounts = nbins
        self.binranges = ranges

        for f in self.files:
            binTasks.append(d.delayed(hdf5Processor(f).localBinning)\
                           (axes=axes, nbins=nbins, ranges=ranges, **binning_kwds))
        if len(binTasks) > 0:
            if pbar:
                with ProgressBar():
                    self.results = d.compute(*binTasks, scheduler=scheduler, **compute_kwds)
            else:
                self.results = d.compute(*binTasks, scheduler=scheduler, **compute_kwds)

        if ret:
            return self.results

    def combineResults(self, bin_accumulated=True, ret=True):
        """
        Combine the results from all segments

        :Parameters:
            bin_accumulated : bool | True
                Accumulate the bins.
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.

        :Return:
            combinedresult : dict
                Return combined result dictionary (if `ret == True`).
        """

        binnedhist = np.stack([self.results[i]['binned'] for i in range(self.nfiles)], axis=0)

        if bin_accumulated:
            binnedhist = np.sum(binnedhist, axis=0)

        # Transfer the results to combined result
        self.combinedresult = self.results[0]
        self.combinedresult['binned'] = binnedhist

        if ret:
            return self.combinedresult

    def updateHistogram(self, axes=None, sliceranges=None, ret=False):
        """
        Update the size of the binning results
        """

        # Input axis order to binning axes order
        binaxes = np.asarray(self.binaxes)
        seqs = [np.where(ax == binaxes)[0][0] for ax in axes]

        for seq, ax, rg in zip(seqs, axes, sliceranges):
            # Update the lengths of binning axes
            self.combinedresult[ax] = self.combinedresult[ax][rg[0]:rg[1]]

            # Update the binned histogram
            tempmat = np.moveaxis(self.combinedresult['binned'], seq, 0)[rg[0]:rg[1],...]
            self.combinedresult['binned'] = np.moveaxis(tempmat, 0, seq)

        if ret:
            return self.combinedresult

    def saveHistogram(self, dictname='combinedresult', form='h5', save_addr='./histogram', **kwds):

        try:
            saveDict(self, dictname, form, save_addr, **kwds)
        except:
            raise Exception('Saving histogram was unsuccessful!')


def readBinnedhdf5(fpath, combined=True, typ='float32'):
    """
    Read binned hdf5 file (3D/4D data) into a dictionary.

    :Parameters:
        fpath : str
            File path
        combined : bool | True
            Specify if the volume slices are combined.
        typ : str | 'float32'
            Data type of the numerical values in the output dictionary

    :Return:
        out : dict
            Dictionary with keys being the axes and the volume (slices).
    """

    f = File(fpath, 'r')
    out = {}

    # Read the axes group
    for ax, axval in f['axes'].items():
        out[ax] = axval[...]

    # Read the binned group
    group = f['binned']
    itemkeys = group.keys()
    nbinned = len(itemkeys)

    # Binned 3D matrix
    if (nbinned == 1) or (combined == False):
        for ik in itemkeys:
            out[ik] = np.asarray(group[ik], dtype=typ)

    # Binned 4D matrix
    elif (nbinned > 1) or (combined == True):
        val = []
        itemkeys_sorted = nts.natsorted(itemkeys)
        for ik in itemkeys_sorted:
            val.append(group[ik])
        out['V'] = np.asarray(val, dtype=typ)

    return out


# =================== #
# Data transformation #
# =================== #

def MCP_Position_mm(Ek, Ang, aInner, Da):
    """
    In the region [-aInner, aInner], calculate the corrected isoline positions using
    the given formula in the SPECS HSA manual (p47 of SpecsLab, Juggler and CCDAcquire).
    In the region beyond aInner on both sides, use Taylor expansion and approximate
    the isoline position up to the first order, i.e.

    n = zInner + dAng*zInner'

    The np.sign() and abs() take care of the sign on each side and reduce the
    conditional branching to one line.
    """

    if abs(Ang) <= aInner:

        return zInner(Ek, Ang, Da)
    else:
        dA = abs(Ang) - aInner
        return np.sign(Ang) * (zInner(Ek, aInner, Da) +
                               dA * zInner_Diff(Ek, aInner, Da))


def zInner(Ek, Ang, Da):
    """
    Calculate the isoline position by interpolated polynomial at a certain kinetic energy
    (Ek) and photoemission angle (Ang).
    """
    D1, D3, D5, D7 = Da

    return poly(D1, Ek) * (Ang) + 10**(-2) * poly(D3, Ek) * (Ang)**3 + \
        10**(-4) * poly(D5, Ek) * (Ang)**5 + 10**(-6) * poly(D7, Ek) * (Ang)**7


def zInner_Diff(Ek, Ang, Da):
    """
    Calculate the derivative of the isoline position by interpolated polynomial at a
    certain kinetic energy (Ek) and photoemission angle (Ang).
    """

    D1, D3, D5, D7 = Da

    return poly(D1, Ek) + 3*10**(-2)*poly(D3, Ek)*(Ang)**2 + \
        5*10**(-4)*poly(D5, Ek)*(Ang)**4 + 7*10**(-6)*poly(D7,Ek)*(Ang)**6


def slice2d(datamat, xaxis, yaxis, xmin, xmax, ymin, ymax):
    """
    Slice ARPES matrix (E,k) according to specified energy and angular ranges
    """

    axes = [xaxis, xaxis, yaxis, yaxis]
    bounds = [xmin, xmax, ymin, ymax]
    lims = list(map(lambda x, y: find_nearest(x, y), bounds, axes))
    slicedmat = datamat[lims[0]:lims[1], lims[2]:lims[3]]

    return slicedmat, xaxis[lims[0]:lims[1]], yaxis[lims[2]:lims[3]]


def slice3d(datamat, xaxis, yaxis, zaxis, xmin, xmax, ymin, ymax, zmin, zmax):
    """
    Slice trARPES matrix (E,k,t) according to specified energy and angular ranges
    """

    axes = [xaxis, xaxis, yaxis, yaxis, zaxis, zaxis]
    bounds = [xmin, xmax, ymin, ymax, zmin, zmax]
    lims = list(map(lambda x, y: find_nearest(x, y), bounds, axes))
    slicedmat = datamat[lims[0]:lims[1], lims[2]:lims[3], lims[4]:lims[5]]

    return slicedmat, xaxis[lims[0]:lims[1]
                            ], yaxis[lims[2]:lims[3]], zaxis[lims[4]:lims[5]]


def fftfilter2d(datamat):

    r, c = datamat.shape
    x, y = np.meshgrid(np.arange(-r / 2, r / 2), np.arange(-c / 2, c / 2))
    zm = np.zeros_like(datamat.T)

    ftmat = (nft.fftshift(nft.fft2(datamat))).T

    # Construct peak center coordinates array using rotation
    x0, y0 = -80, -108
    # Conversion factor for radius (half-width half-maximum) of Gaussian
    rgaus = 2 * np.log(2)
    sx, sy = 10 / rgaus, 10 * (c / r) / rgaus
    alf, bet = np.arctan(r / c), np.arctan(c / r)
    rotarray = np.array([0, 2 * alf, 2 * (alf + bet), -2 * bet])
    xy = [np.dot(rot2d(roth, 'rad'), np.array([x0, y0])) for roth in rotarray]

    # Generate intermediate positions and append to peak center coordinates
    # array
    for everynumber in range(4):
        n = everynumber % 4
        xy.append((xy[n] + xy[n - 1]) / 2)

    # Construct the complement of mask matrix
    for currpair in range(len(xy)):
        xc, yc = xy[currpair]
        zm += np.exp(-((x - xc)**2) / (2 * sx**2) -
                     ((y - yc)**2) / (2 * sy**2))

    fltrmat = np.abs(nft.ifft2((1 - zm) * ftmat))

    return fltrmat


def normspec(*specs, smooth=False, aligned=False, span=13, order=1):
    """
    Normalize a series of 1D spectra
    """

    nspec = len(specs)
    specnorm = []

    for i in range(nspec):

        spec = specs[i]

        if smooth:
            spec = savgol_filter(spec, span, order)

        if type(spec) in (list, tuple):
            nsp = spec / max(spec)
        else:
            nsp = spec / spec.max()
        specnorm.append(nsp)

        # Align 1D spectrum
        normalized_specs = np.asarray(specnorm)

    return normalized_specs
