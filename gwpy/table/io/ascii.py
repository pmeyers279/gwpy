# -*- coding: utf-8 -*-
# Copyright (C) Duncan Macleod (2014)
#
# This file is part of GWpy.
#
# GWpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GWpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GWpy.  If not, see <http://www.gnu.org/licenses/>.

"""Read event tables from ASCII files.

This module only defines a function factory for reading lines of ASCII
into a particular LIGO_LW table object.

Each specific ASCII table format should define their own line parser
(that generates each row of the table) and pass it to the factory method.
"""

from numpy import loadtxt

from .. import lsctables
from ... import version
from ...io.cache import file_list

__author__ = 'Duncan Macleod <duncan.macleod@ligo.org>'
__version__ = version.version


def ascii_table_factory(table, format, trig_func, cols=None, comments='#',
                        delimiter=None):
    """Build a table reader for the given format

    Parameters
    ----------
    table : `type`
        table class for which this format is relevant
    format : `str`
        name of the format
    trig_func : `callable`
        method to convert one row of data (from `numpy.loadtxt`) into an event
    cols : `list` of `str`
        list of columns that can be read by default for this format
    """
    def table_from_ascii(f, format=None, columns=cols, filt=None, nproc=1):
        """Build a `~{0}` from events in an ASCII file.

        Parameters
        ----------
        f : `file`, `str`, `CacheEntry`, `list`, `Cache`
            object representing one or more files. One of

            - an open `file`
            - a `str` pointing to a file path on disk
            - a formatted :class:`~glue.lal.CacheEntry` representing one file
            - a `list` of `str` file paths
            - a formatted :class:`~glue.lal.Cache` representing many files

        columns : `list`, optional
            list of column name strings to read, default all.
        filt : `function`, optional
            function by which to filt events. The callable must accept as
            input a `SnglBurst` event and return `True`/`False`.
        nproc : `int`, optional, default: 1
            number of parallel processes with which to distribute file I/O,
            default: serial process

        Returns
        -------
        table : `~{0}`
            a new `~{0}` filled with yummy data
        """.format(table.__name__)
        # allow multiprocessing
        if nproc != 1:
            from .cache import read_cache
            return read_cache(f, table.tableName,
                              columns=columns, nproc=nproc, format=format)

        # format list of files
        files = file_list(f)

        # generate output
        if columns is None:
            columns = cols

        out = lsctables.New(table, columns=columns)
        append = out.append

        # iterate over events
        for fp in files:
            dat = loadtxt(fp, comments=comments, delimiter=delimiter)
            for line in dat:
                row = trig_func(line, columns=columns)
                row.event_id = out.get_next_id()
                if filt is None or filt(row):
                    append(row)
        return out
    return table_from_ascii
