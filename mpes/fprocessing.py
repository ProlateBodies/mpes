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
from .igoribw import loadibw
from .base import FileCollection, MapParser
from . import utils as u, bandstructure as bs
import igor.igorpy as igor
import pandas as pd
import os
import re
import glob as g
import numpy as np
import numpy.fft as nft
import scipy.io as sio
import skimage.io as skio
from PIL import Image as pim
import warnings as wn
from h5py import File
import psutil as ps
import dask as d, dask.array as da, dask.dataframe as ddf
from dask.diagnostics import ProgressBar
from tqdm import tqdm
import natsort as nts
from functools import reduce
from funcy import project

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

    data = np.asarray(pd.read_table(fdir, delim_whitespace=True,
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
    Convert image to numpy ndarray.
    """

    mat = np.asarray(pim.open(fdir))
    return mat


class hdf5Reader(File):
    """ HDF5 reader class
    """

    def __init__(self, f_addr, ncores=None, **kwds):

        self.faddress = f_addr
        eventEstimator = kwds.pop('estimator', 'Stream_0')
        self.CHUNK_SIZE = int(kwds.pop('chunksz', 1e6))
        super().__init__(name=self.faddress, mode='r', **kwds)

        self.nEvents = self[eventEstimator].size
        self.groupNames = list(self)
        self.groupAliases = [self.readAttribute(self[gn], 'Name', nullval=gn) for gn in self.groupNames]
        # Initialize the look-up dictionary between group aliases and group names
        self.nameLookupDict = dict(zip(self.groupAliases, self.groupNames))
        self.attributeNames = list(self.attrs)

        if (ncores is None) or (ncores > N_CPU) or (ncores < 0):
            self.ncores = N_CPU
        else:
            self.ncores = int(ncores)

    def getGroupNames(self, wexpr=None, woexpr=None, use_alias=False):
        """ Retrieve group names from the loaded hdf5 file with string filtering.

        :Parameters:
            wexpr : str | None
                Expression in a name to leave in the group name list (w = with).
            woexpr : str | None
                Expression in a name to leave out of the group name list (wo = without).

        :Return:
            filteredGroupNames : list
                List of filtered group names.
        """

        # Gather group aliases, if specified
        if use_alias == True:
            groupNames = self.name2alias(self.groupNames)
        else:
            groupNames = self.groupNames

        # Filter the group names
        if (wexpr is None) and (woexpr is None):
            filteredGroupNames = groupNames
        if wexpr:
            filteredGroupNames = [i for i in groupNames if wexpr in i]
        elif woexpr:
            filteredGroupNames = [i for i in groupNames if woexpr not in i]

        return filteredGroupNames

    def getAttributeNames(self, wexpr=None, woexpr=None):
        """ Retrieve attribute names from the loaded hdf5 file with string filtering.

        :Parameters:
            wexpr : str | None
                Expression in a name to leave in the attribute name list (w = with).
            woexpr : str | None
                Expression in a name to leave out of the attribute name list (wo = without).

        :Return:
            filteredAttrbuteNames : list
                List of filtered attribute names.
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
        """ Retrieve the content of the group(s) in the loaded hdf5 file.

        :Parameter:
            group : list/tuple
                Collection of group names.

        :Return:
            groupContent : list/tuple
                Collection of values of the corresponding groups.
        """

        ngroup = len(group)
        amin, amax = u.intify(amin, amax)
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
        """ Retrieve the content of the attribute(s) in the loaded hdf5 file.

        :Parameter:
            attribute : list/tuple
                Collection of attribute names.

        :Return:
            attributeContent : list/tuple
                Collection of values of the corresponding attributes.
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

    def name2alias(self, names_to_convert):
        """ Find corresponding aliases of the named groups.

        :Parameter:
            names_to_convert : list/tuple
                Names to convert to aliases.

        :Return:
            aliases : list/tuple
                Aliases corresponding to the names.
        """

        aliases = [self.readAttribute(self[ntc], 'Name', nullval=ntc) for ntc in names_to_convert]

        return aliases

    def _assembleGroups(self, gnames, amin=None, amax=None, use_alias=True, dtyp='float32', ret='array'):
        """ Assemble the content values of the selected groups.
        """

        gdict = {}

        # Add groups to dictionary
        for ign, gn in enumerate(gnames):

            g_dataset = self.readGroup(self, gn, sliced=False)
            g_values = g_dataset[slice(amin, amax)]
            if bool(dtyp):
                g_values = g_values.astype(dtyp)

            # Use the group alias as the dictionary key
            if use_alias == True:
                g_name = self.readAttribute(g_dataset, 'Name', nullval=gn)
                gdict[g_name] = g_values
            # Use the group name as the dictionary key
            else:
                gdict[gn] = g_values

            # print('{}: {}'.format(g_name, g_values.dtype))
        if ret == 'array':
            return np.asarray(list(gdict.values()))
        elif ret == 'dict':
            return gdict

    def summarize(self, form='text', use_alias=True, ret=False, **kwds):
        """ Summarize the content of the hdf5 file (names of the groups,
        attributes and the selected contents. Output by print or as a dictionary.)

        :Parameters:
            form : str | 'text'
                Format to summarize the content of the file into.
                Options include 'text', 'dict' and 'dataframe'.
            use_alias : bool | True
                Specify whether to use the alias to rename the groups.
            ret : bool | False
                Specify whether function return is sought.
            **kwds : keyword arguments

        :Return:
            hdfdict : dict
                Dictionary including both the attributes and the groups,
                using their names as the keys.
            edf : dataframe
                Dataframe constructed using only the group values, and the column
                names are the corresponding group names (or aliases).
        """

        if form == 'text':
            # Output as printed text
            print('*** HDF5 file info ***\n',
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

        elif form == 'dict':
            # Summarize attributes and groups into a dictionary

            # Retrieve the range of acquired events
            amin = kwds.pop('amin', None)
            amax = kwds.pop('amax', None)
            amin, amax = u.intify(amin, amax)

            # Output as a dictionary
            # Attribute name stays, stream_x rename as their corresponding attribute name
            # Add groups to dictionary
            hdfdict = self._assembleGroups(self.groupNames, amin=amin, amax=amax, use_alias=use_alias, ret='dict')

            # Add attributes to dictionary
            for an in self.attributeNames:

                hdfdict[an] = self.readAttribute(self, an)

            if ret == True:
                return hdfdict

        elif form == 'dataframe':
            # Gather groups into columns of a dataframe

            self.CHUNK_SIZE = int(kwds.pop('chunksz', 1e6))

            dfParts = []
            chunkSize = min(self.CHUNK_SIZE, self.nEvents / self.ncores)
            nPartitions = int(self.nEvents // chunkSize) + 1
            # Determine the column names
            gNames = kwds.pop('groupnames', self.getGroupNames(wexpr='Stream'))
            colNames = self.name2alias(gNames)

            for p in range(nPartitions): # Generate partitioned dataframe

                # Calculate the starting and ending index of every chunk of events
                eventIDStart = int(p * chunkSize)
                eventIDEnd = int(min(eventIDStart + chunkSize, self.nEvents))
                dfParts.append(d.delayed(self._assembleGroups)(gNames, amin=eventIDStart, amax=eventIDEnd, **kwds))

            # Construct eda (event dask array) and edf (event dask dataframe)
            eda = da.from_array(np.concatenate(d.compute(*dfParts), axis=1).T, chunks=self.CHUNK_SIZE)
            self.edf = ddf.from_dask_array(eda, columns=colNames)

            if ret == True:
                return self.edf

    def convert(self, form, save_addr='./summary', pq_append=False, **kwds):
        """ Format conversion from hdf5 to mat (for Matlab/Python) or ibw (for Igor).

        :Parameters:
            form : str
                The format of the data to convert into.
            save_addr : str | './summary'
                File address to save to.
        """

        save_fname = u.appendformat(save_addr, form)

        if form == 'mat': # Save dictionary as mat file
            hdfdict = self.summarize(form='dict', ret=True, **kwds)
            sio.savemat(save_fname, hdfdict)

        elif form == 'parquet': # Save dataframe as parquet file
            compression = kwds.pop('compression', 'UNCOMPRESSED')
            engine = kwds.pop('engine', 'fastparquet')

            self.summarize(form='dataframe', **kwds)
            self.edf.to_parquet(save_addr, engine=engine, compression=compression,
                                append=pq_append, ignore_divisions=True)

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
            Class including all attributes.
        dictname : str
            Namestring of the dictionary to save (such as the attribute name in a class).
        form : str | 'h5'
            Save format, supporting 'mat', 'h5'/'hdf5', 'tiff' (need tifffile) or 'png' (need imageio).
        save_addr : str | './histogram'
            File path to save the binning result.
        **kwds : keyword arguments
            =========  ===========  ===========  ========================================
             keyword    data type     default     meaning
            =========  ===========  ===========  ========================================
              dtyp       string      'float32'    Data type of the histogram
             cutaxis      int            3        The axis to cut the 4D data in
            slicename    string         'V'       The shared namestring for the 3D slice
            otheraxes     dict         None       Values along other or converted axes
            =========  ===========  ===========  ========================================
    """

    dtyp = kwds.pop('dtyp', 'float32')
    sln = kwds.pop('slicename', 'V')
    save_addr = u.appendformat(save_addr, form)
    otheraxes = kwds.pop('otheraxes', None)

    histdict = getattr(processor, dictname)
    # Include other axes values in the binning dictionary
    if otheraxes:
        histdict = u.dictmerge(histdict, otheraxes)

    if form == 'mat': # Save as mat file (for Matlab)

        sio.savemat(save_addr, histdict)

    elif form in ('h5', 'hdf5'): # Save as hdf5 file

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
            raise NotImplementedError('The output format is undefined for data \
            with higher than three dimensions!')

    elif form == 'ibw': # Save as Igor wave

        from igorwriter import IgorWave
        wave = IgorWave(histdict['binned'], name='binned')
        wave.save(save_addr)

    else:
        raise NotImplementedError('Not implemented output format!')


class hdf5Processor(hdf5Reader):
    """ Class for generating multidimensional histogram from hdf5 files.
    """

    def __init__(self, f_addr, **kwds):

        self.faddress = f_addr
        self.ua = kwds.pop('use_alias', True)
        self.hdfdict = {}
        self.histdict = {}
        self.axesdict = {}

        super().__init__(f_addr=self.faddress, **kwds)

    def _addBinners(self, axes=None, nbins=None, ranges=None, binDict=None):
        """
        Construct the binning parameters within an instance.
        """

        # Use information specified in binDict, ignore others
        if binDict is not None:
            try:
                self.binaxes = binDict['axes']
                self.nbinaxes = len(self.binaxes)
                self.bincounts = binDict['nbins']
                self.binranges = binDict['ranges']
            except:
                pass # No action when binDict is not specified
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

    @d.delayed
    def _delayedBinning(self, data):
        """
        Lazily evaluated multidimensional binning.

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

    def distributedProcessBinning(self, axes=None, nbins=None, ranges=None,
                                binDict=None, chunksz=100000, pbar=True, ret=True, **kwds):
        """
        Compute the photoelectron intensity histogram using dask array.

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
            pbar : bool | True
                Option to display a progress bar.
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
        amin, amax = u.intify(amin, amax)

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
        if pbar:
            with ProgressBar():
                self.histdict['binned'], ax_vals = bintask.compute()
        else:
            self.histdict['binned'], ax_vals = bintask.compute()

        for iax, ax in enumerate(axes):
            self.histdict[ax] = ax_vals[iax]

        if ret:
            return self.histdict

    def distributedBinning(self, axes=None, nbins=None, ranges=None,
                            binDict=None, pbar=True, ret=True, **kwds):
        """
        :Parameters:
            see mpes.fprocessing.binDataframe()
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.
            **kwds : keyword arguments
        """

        # Retrieve the range of acquired events
        amin = kwds.pop('amin', None)
        amax = kwds.pop('amax', None)
        amin, amax = u.intify(amin, amax)

        # Set up the binning parameters
        self._addBinners(axes, nbins, ranges, binDict)
        self.summarize(form='dataframe')
        self.edf = self.edf[amin:amax] # Select event range for binning

        self.histdict = binDataframe(self.edf, ncores=self.ncores, axes=axes, nbins=nbins,
                        ranges=ranges, binDict=binDict, pbar=pbar)

        if ret:
            return self.histdict

    def localBinning(self, axes=None, nbins=None, ranges=None, binDict=None,
        jittered=False, histcoord='midpoint', ret='dict', **kwds):
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
                ================  ==============  ===========  ==========================================
                     keyword         data type      default     meaning
                ================  ==============  ===========  ==========================================
                     amin          numeric/None      None       minimum value of electron sequence
                     amax          numeric/None      None       maximum value of electron sequence
                  jitter_axes          list          axes       list of axes to jitter
                  jitter_bins          list          nbins      list of the number of bins
                jitter_amplitude   numeric/array     0.5        jitter amplitude (single number for all)
                 jitter_ranges         list         ranges      list of the binning ranges
                ================  ==============  ===========  ==========================================

        :Return:
            histdict : dict
                Dictionary containing binned data and the axes values (if `ret = True`).
        """

        # Retrieve the range of acquired events
        amin = kwds.pop('amin', None)
        amax = kwds.pop('amax', None)
        amin, amax = u.intify(amin, amax)

        # Assemble the data for binning, assuming they can be completely loaded into RAM
        self.hdfdict = self.summarize(form='dict', use_alias=self.ua, amin=amin, amax=amax, ret=True)

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

            # Add jitter to the specified dimensions of the data
            for jb, jax, jamp, jr in zip(jitter_bins, jitter_axes, jitter_amplitude, jitter_ranges):

                sz = self.hdfdict[jax].size
                # Calculate the bar size of the histogram in every dimension
                binsize = abs(jr[0] - jr[1])/jb
                self.hdfdict[jax] = self.hdfdict[jax].astype('float32')
                # Jitter as random uniformly distributed noise (W. S. Cleveland)
                self.hdfdict[jax] += jamp * binsize * np.random.uniform(low=-1,
                                        high=1, size=sz).astype('float32')

        # Stack up data from unbinned axes
        data_unbinned = np.stack((self.hdfdict[ax] for ax in axes), axis=1)
        self.hdfdict = {}

        # Compute binned data locally
        self.histdict['binned'], ax_vals = np.histogramdd(data_unbinned, bins=self.bincounts, range=self.binranges)
        del data_unbinned

        for iax, ax in enumerate(axes):
            if histcoord == 'midpoint':
                ax_edge = ax_vals[iax]
                ax_midpoint = (ax_edge[1:] + ax_edge[:-1])/2
                self.histdict[ax] = ax_midpoint
            elif histcoord == 'edge':
                self.histdict[ax] = ax_vals[iax]

        if ret == 'dict':
            return self.histdict
        elif ret == 'histogram':
            histogram = self.histdict.pop('binned')
            self.axesdict = self.histdict.copy()
            self.histdict = {}
            return histogram
        elif ret == False:
            return

    def updateHistogram(self, axes=None, sliceranges=None, ret=False):
        """
        Update the dimensional sizes of the binning results.
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

    def saveHistogram(self, dictname='histdict', form='h5', save_addr='./histogram', **kwds):
        """
        Save binned histogram and the axes.
        """

        try:
            saveDict(self, dictname, form, save_addr, **kwds)
        except:
            raise Exception('Saving histogram was unsuccessful!')

    def toSplitter(self):
        """
        Convert to an instance of hdf5Splitter.
        """

        return hdf5Splitter(f_addr=self.faddress)

    def toBandStructure(self):
        """
        Convert to an instance of BandStructure.
        """

        pass


def binPartition(partition, binaxes, nbins, binranges):
    """ Bin the data within a file partition (e.g. dask dataframe).

    :Parameters:
        partition : dataframe partition
            Partition of a dataframe.
        binaxes : list
            List of axes to bin.
        nbins : list
            Number of bins for each binning axis.
        binranges : list
            The range of each axis to bin.

    :Return:
        hist_partition : ndarray
            Histogram from the binning process.
    """

    cols = partition.columns
    binColumns = [cols.get_loc(binax) for binax in binaxes]
    vals = partition.values[:, binColumns]

    hist_partition, _ = np.histogramdd(vals, bins=nbins, range=binranges)

    return hist_partition


def binDataframe(df, ncores=N_CPU, axes=None, nbins=None, ranges=None,
                binDict=None, pbar=True):
    """
    Calculate multidimensional histogram from columns of a dask dataframe.
    Prof. Yves Acremann's method.

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
        pbar : bool | True
            Option to display a progress bar.

    :Return:
        histdict : dict
            Dictionary containing binned data and the axes values (if `ret = True`).
    """

    histdict = {}
    partitionResults = [] # Partition-level results
    for i in tqdm(range(0, df.npartitions, ncores), disable=not(pbar)):

        coreTasks = [] # Core-level jobs
        for j in range(0, ncores):

            ij = i + j
            if ij >= df.npartitions:
                break

            dfPartition = df.get_partition(ij) # Obtain dataframe partition
            coreTasks.append(d.delayed(binPartition)(dfPartition, axes, nbins, ranges))

        if len(coreTasks) > 0:
            coreResults = d.compute(*coreTasks)

            # Combine all core results for a dataframe partition
            partitionResult = np.zeros_like(coreResults[0])
            for coreResult in coreResults:
                partitionResult += coreResult

            partitionResults.append(partitionResult)
            # del partitionResult

        del coreTasks

    # Combine all partition results
    fullResult = np.zeros_like(partitionResults[0])
    for pr in partitionResults:
        fullResult += np.nan_to_num(pr)

    # Load into dictionary
    histdict['binned'] = fullResult.astype('float32')
    # Calculate axes values
    for iax, ax in enumerate(axes):
        axrange = ranges[iax]
        histdict[ax] = np.linspace(axrange[0], axrange[1], nbins[iax])

    return histdict


class hdf5Splitter(hdf5Reader):
    """
    Class to split large hdf5 files.
    """

    def __init__(self, f_addr, **kwds):

        self.faddress = f_addr
        self.splitFilepaths = []
        super().__init__(f_addr=self.faddress, **kwds)

    @d.delayed
    def _split_file(self, idx, save_addr, namestr):
        """ Split file generator
        """

        evmin, evmax = self.eventList[idx], self.eventList[idx+1]
        fpath = save_addr + namestr + str(idx+1) + '.h5'

        # Use context manager to open hdf5 file
        with File(fpath, 'w') as fsp:

            # Copy the attributes
            for attr, attrval in self.attrs.items():
                fsp.attrs[attr] = attrval

            # Copy the segmented groups and their attributes
            for gp in self.groupNames:
                #self.copy(gn, fsp[gn])
                fsp.create_dataset(gp, data=self.readGroup(self, gp, amin=evmin, amax=evmax))
                for gattr, gattrval in self[gp].attrs.items():
                    fsp[gp].attrs[gattr] = gattrval

        return(fpath)

    def split(self, nsplit, save_addr='./', namestr='split_',
                split_group='Stream_0', pbar=False):
        """
        Split and save an hdf5 file.

        :Parameters:
            nsplit : int
                Number of split files.
            save_addr : str | './'
                Directory to store the split files.
            namestr : str | 'split_'
                Additional namestring attached to the front of the filename.
            split_group : str | 'Stream_0'
                Name of the example group to split for file length reference.
            pbar : bool | False
                Enable (when True)/Disable (when False) the progress bar.
        """

        nsplit = int(nsplit)
        self.splitFilepaths = [] # Refresh the path when re-splitting
        self.eventLen = self[split_group].size
        self.eventList = np.linspace(0, self.eventLen, nsplit+1, dtype='int')
        tasks = []

        # Distributed file splitting
        for isp in range(nsplit):

            tasks.append(self._split_file(isp, save_addr, namestr))

        if pbar:
            with ProgressBar():
                self.splitFilepaths = d.compute(*tasks)
        else:
            self.splitFilepaths = d.compute(*tasks)

    def subset(self, file_id):
        """
        Spawn an instance of hdf5Processor from a specified split file.
        """

        if self.splitFilepaths:
            return hdf5Processor(f_addr=self.splitFilepaths[file_id])

        else:
            raise ValueError("No split files are present.")

    def toProcessor(self):
        """
        Change to an hdf5Processor instance.
        """

        return hdf5Processor(f_addr=self.faddress)


class parallelHDF5Processor(FileCollection):
    """
    Class for parallel processing of hdf5 files.
    """

    def __init__(self, files=[], file_sorting=True, folder=None):

        super().__init__(files=files, file_sorting=file_sorting, folder=folder)
        self.results = {}
        self.combinedresult = {}

    @staticmethod
    def _arraysum(arraya, arrayb):
        """ Sum of two arrays.
        """

        return arraya + arrayb

    def subset(self, file_id):
        """
        Spawn an instance of hdf5Processor from a specified substituent file.
        """

        if self.files:
            return hdf5Processor(f_addr=self.files[file_id])

        else:
            raise ValueError("No substituent file is present.")

    def parallelBinning(self, axes, nbins, ranges, scheduler='threads', combine=True,
    histcoord='midpoint', pbar=True, binning_kwds={}, compute_kwds={}, ret=False):
        """
        Parallel computation of the multidimensional histogram from file segments.

        :Parameters:
            axes : (list of) strings | None
                Names the axes to bin.
            nbins : (list of) int | None
                Number of bins along each axis.
            ranges : (list of) tuples | None
                Ranges of binning along every axis.
            scheduler : str | 'threads'
                Type of distributed scheduler ('threads', 'processes', 'synchronous')
            combine : bool | True
                Combine the results obtained from distributed binning.
            histcoord : string | 'midpoint'
                The coordinates of the histogram. Specify 'edge' to get the bar edges (every
                dimension has one value more), specify 'midpoint' to get the midpoint of the
                bars (same length as the histogram dimensions).
            pbar : Bool | true
                Whether to show the progress bar
            binning_kwds : dict | {}
                keyword arguments to be included in hdf5Processor.localBinning()
            compute_kwds : dict | {}
                keyword arguments to specify in dask.compute()
        """

        binTasks = []
        self.binaxes = axes
        self.nbinaxes = len(axes)
        self.bincounts = nbins
        self.binranges = ranges

        # Reset containers of results
        self.results = {}
        self.combinedresult = {}

        # Execute binning tasks
        if combine == True: # Combine results in the process of binning
            binning_kwds = u.dictmerge({'ret':'histogram'}, binning_kwds)
            # Construct binning tasks
            for f in self.files:
                binTasks.append(d.delayed(hdf5Processor(f).localBinning)
                                (axes=axes, nbins=nbins, ranges=ranges, **binning_kwds))
            if pbar:
                with ProgressBar():
                    self.combinedresult['binned'] = reduce(self._arraysum,
                    d.compute(*binTasks, scheduler=scheduler, **compute_kwds))
            else:
                self.combinedresult['binned'] = reduce(self._arraysum,
                d.compute(*binTasks, scheduler=scheduler, **compute_kwds))

            del binTasks

            # Calculate and store values of the axes
            for iax, ax in enumerate(self.binaxes):
                p_start, p_end = self.binranges[iax]
                self.combinedresult[ax] = u.calcax(p_start, p_end, self.bincounts[iax], ret=histcoord)

            if ret:
                return self.combinedresult

        else: # Return all task outcome of binning (not recommended due to the size)
            for f in self.files:
                binTasks.append(d.delayed(hdf5Processor(f).localBinning)
                                (axes=axes, nbins=nbins, ranges=ranges, **binning_kwds))
            if pbar:
                with ProgressBar():
                    self.results = d.compute(*binTasks, scheduler=scheduler, **compute_kwds)
            else:
                self.results = d.compute(*binTasks, scheduler=scheduler, **compute_kwds)

            del binTasks

            if ret:
                return self.results

    def combineResults(self, ret=True):
        """
        Combine the results from all segments (only when self.results is non-empty).

        :Parameters:
            ret : bool | True
                :True: returns the dictionary containing binned data explicitly
                :False: no explicit return of the binned data, the dictionary
                generated in the binning is still retained as an instance attribute.

        :Return:
            combinedresult : dict
                Return combined result dictionary (if `ret == True`).
        """

        try:
            binnedhist = np.stack([self.results[i]['binned'] for i in range(self.nfiles)], axis=0).sum(axis=0)

            # Transfer the results to combined result
            self.combinedresult = self.results[0].copy()
            self.combinedresult['binned'] = binnedhist
        except:
            pass

        if ret:
            return self.combinedresult

    def convert(self, form='parquet', save_addr='./summary', append_to_folder=False, pbar=True, **kwds):
        """
        Convert files to another format (e.g. parquet).
        """

        if os.path.exists(save_addr) and os.path.isdir(save_addr):
            # In an existing folder, clean up the files if specified
            existing_files = g.glob(save_addr + r'/*')
            n_existing_files = len(existing_files)

            # Remove existing files in the folder before writing into it
            if (n_existing_files > 0) and (append_to_folder == False):
                for f_exist in existing_files:
                    if '.h5' not in f_exist: # Keep the calibration files
                        os.remove(f_exist)

        for fi in tqdm(range(self.nfiles), disable=not(pbar)):
            subproc = self.subset(file_id=fi)
            subproc.convert(form=form, save_addr=save_addr, pq_append=True, **kwds)

    def updateHistogram(self, axes=None, sliceranges=None, ret=False):
        """
        Update the dimensional sizes of the binning results.
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
        """
        Save binned histogram and the axes.
        """

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


class parquetProcessor(MapParser):
    """
    Processs the parquet file converted from single events data.
    """

    def __init__(self, folder, ncores=None):

        self.folder = folder
        # Create the event dataframe
        self.edf = self.read(self.folder)
        self.npart = self.edf.npartitions
        self.histogram = None
        self.histdict = {}

        super().__init__(file_sorting=False, folder=folder)

        if (ncores is None) or (ncores > N_CPU) or (ncores < 0):
            self.ncores = N_CPU
        else:
            self.ncores = int(ncores)

    @property
    def nrow(self):
        """ Number of rows in the distributed dataframe.
        """

        return len(self.edf.index)

    @property
    def ncol(self):
        """ Number of columns in the distrbuted dataframe.
        """

        return len(self.edf.columns)

    @staticmethod
    def read(folder):
        """ Read parquet files from a folder.
        """

        return d.dataframe.read_parquet(folder)

    def _addBinners(self, axes=None, nbins=None, ranges=None, binDict=None):
        """ Construct the binning parameters within an instance.
        """

        # Use information specified in binDict, ignore others
        if binDict is not None:
            try:
                self.binaxes = binDict['axes']
                self.nbinaxes = len(self.binaxes)
                self.bincounts = binDict['nbins']
                self.binranges = binDict['ranges']
            except:
                pass # No action when binDict is not specified
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

    # Column operations
    def appendColumn(self, colnames, colvals):
        """ Append columns to dataframe.

        :Parameters:
            colnames : list/tuple
                New column names.
            colvals : numpy array/list
                Entries of the new columns.
        """

        colnames = list(colnames)
        colvals = [colvals]
        ncn = len(colnames)
        ncv = len(colvals)

        if ncn != ncv:
            errmsg = 'The names and values of the columns need to have the same dimensions.'
            raise ValueError(errmsg)

        else:
            for cn, cv in zip(colnames, colvals):
                self.edf = self.edf.assign(**{cn:ddf.from_array(cv)})

    def deleteColumn(self, colnames):
        """ Delete columns

        :Parameters:
            colnames : str/list/tuple
                List of column names to be dropped.
        """

        self.edf = self.edf.drop(colnames, axis=1)


    def applyFilter(self, colname, lb=-np.inf, ub=np.inf):
        """ Application of bound filters to a specified column (can be used consecutively).
        """

        self.edf = self.edf[(self.edf[self.colnam] > lb) & (self.edf[colname] < ub)]

    def transformColumn(self, oldcolname, mapping, newcolname='Transformed', args=(), update='append', **kwds):
        """ Apply function to an existing column and append to the dataframe.

        :Parameters:
            oldcolname : str
                Old column name.
            mapping : function
                Functional map to apply to the values of the old column.
            newcolname : str | 'Transformed'
                New column name.
            args : tuple | ()
                Additional arguments of the functional map.
            update : str | 'append'
                Updating option.
                'append' = append to the current dask dataframe as a new column with the new column name.
                'replace' = replace the values of the old column.
            **kwds : keyword arguments
                Additional arguments for the dask.dataframe.apply() function
        """

        if update == 'append':
            self.edf[newcolname] = self.edf[oldcolname].apply(mapping, args=args, meta=('x', 'f8'), **kwds)
        elif update == 'replace':
            self.edf[oldcolname] = self.edf[oldcolname].apply(mapping, args=args, meta=('x', 'f8'), **kwds)

    def transformColumn2D(self, map2D, X, Y, **kwds):
        """ Apply a mapping simultaneously to two dimensions.
        """

        newX = kwds.pop('newX', X)
        newY = kwds.pop('newY', Y)

        self.edf[newX], self.edf[newY] = map2D(self.edf[X], self.edf[Y], **kwds)

    def applyKCorrection(self, X='X', Y='Y', newX='Xm', newY='Ym', **kwds):
        """ Calculate and replace the X and Y values with their distortion-correction version.
        This method can be reused.
        """

        self.transformColumn2D(map2D=self.wMap, X=X, Y=Y, newX=newX, newY=newY, **kwds)

    def appendKAxis(self, x0, y0, X='X', Y='Y', newX='kx', newY='ky', **kwds):
        """ Calculate and append the k axes (kx, ky) to the events dataframe.
        This method can be reused.
        """

        self.transformColumn2D(map2D=self.kMap, X=X, Y=Y, newX=newX, newY=newY, r0=x0, c0=y0, **kwds)

    def appendEAxis(self, E0, **kwds):
        """ Calculate and append the E axis to the events dataframe.
        This method can be reused.
        """

        self.transformColumn('t', self.Emap, 'E', args=(E0, ), **kwds)

    # Row operation
    def appendRow(self, folder=None, df=None, type='parquet', **kwds):
        """ Append rows read from other parquet files to existing dataframe.
        """

        if type == 'parquet':
            return self.edf.append(self.read(folder), **kwds)
        elif type == 'dataframe':
            return self.edf.append(df, **kwds)
        else:
            raise NotImplementedError

    # Complex operation
    def distributedBinning(self, axes, nbins, ranges, binDict=None, pbar=True, ret=False, **kwds):
        """ Binning the dataframe to a multidimensional histogram.
        """

        # Set up the binning parameters
        self._addBinners(axes, nbins, ranges, binDict)
        #self.edf = self.edf[amin:amax] # Select event range for binning

        self.histdict = binDataframe(self.edf, ncores=self.ncores, axes=axes, nbins=nbins,
                        ranges=ranges, binDict=binDict, pbar=pbar)

        if ret:
            return self.histdict

    def convert(self, form='parquet', save_addr=None, namestr='/data', pq_append=False, **kwds):
        """ Update or convert to other file formats.
        """

        if form == 'parquet':
            compression = kwds.pop('compression', 'UNCOMPRESSED')
            engine = kwds.pop('engine', 'fastparquet')
            self.edf.to_parquet(save_addr, engine=engine, compression=compression,
                                append=pq_append, ignore_divisions=True, **kwds)

        elif form in ('h5', 'hdf5'):
            self.edf.to_hdf(save_addr, namestr, **kwds)

    def saveHistogram(self, form, save_addr, dictname='histdict', **kwds):
        """ Export binned histogram as other files.
        Refer to mpes.fprocessing.saveDict() for the description of arguments
        """

        try:
            saveDict(self, dictname, form, save_addr, **kwds)
        except:
            raise Exception('Saving histogram was unsuccessful!')

    def toDataStructure(self):
        """ Convert to the xarray data structure from existing binned data.
        """

        if bool(self.histdict):
            coords = project(self.histdict, self.binaxes)

            if self.nbinaxes == 3:
                return bs.BandStructure(data=self.histdict['binned'],
                        coords=coords, dims=self.binaxes, datakey='')
            elif self.nbinaxes > 3:
                return bs.MPESDataset(data=self.histdict['binned'],
                        coords=coords, dims=self.binaxes, datakey='')

        else:
            raise ValueError('No binning results are available!')


# =================== #
# Data transformation #
# =================== #

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
