#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
@author: R. Patrick Xian
"""

def numFormatConversion(seq, form='int', **kwds):
    """
    When length keyword is not specified as an argument, the function
    returns a format-converted sequence of numbers
    
    The function returns nothing when the conversion fails due to errors
    
    **Parameters**
    
    seq : 1D numeric array
        the numeric array to be converted
    form : str | 'int'
        the converted format
    
    **Return**
    
    numseq : converted numeric type
        the format-converted array
    """
    
    try:
        lseq = len(seq)
    except:
        raise
    
    l = kwds.pop('length', lseq)
    if lseq == l:
        # Case of numeric array of the right length but may not be
        # the right type
        try:
            numseq = eval('list(map(' + form + ', seq))')
            return numseq
        except:
            raise 
    else:
        # Case of numeric array of the right type but wrong length
        return seq

        
def replist(entry, row, column):
    """
    Generator of nested lists with identical entries.
    Generated values are independent of one another.
    
    ***Parameters***
    
    entry : numeric/str
        repeated item in nested list
    row : int
        number of rows in nested list
    column : int
        number of columns in nested list
    
    ***Return***
    
    nested list
    """

    return [[entry]*column for _ in range(row)]