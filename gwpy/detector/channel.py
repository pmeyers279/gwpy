# -*- coding: utf-8 -*-
# Copyright (C) Duncan Macleod (2013)
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

"""This module defines the `Channel` and `ChannelList` classes.
"""

from __future__ import print_function

import re
import numpy
import warnings
import subprocess
import sys
from math import log

from astropy import units

try:
    from ..io.nds import (NDS2_CHANNEL_TYPE, NDS2_CHANNEL_TYPESTR)
except ImportError:
    NDS2_CHANNEL_TYPESTR = {}
    NDS2_CHANNEL_TYPE = {}

from .. import version
from ..segments import (Segment, SegmentList, SegmentListDict)
from ..time import to_gps
from ..utils.deps import with_import

__author__ = 'Duncan Macleod <duncan.macleod@ligo.org>'
__version__ = version.version

re_quote = re.compile(r'^[\s\"\']+|[\s\"\']+$')


class Channel(object):
    """Representation of a laser-interferometer data channel.

    Parameters
    ----------
    ch : `str`, `Channel`
        name of this Channel (or another  Channel itself).
        If a `Channel` is given, all other parameters not set explicitly
        will be copied over.
    sample_rate : `float`, :class:`~astropy.units.quantity.Quantity`, optional
        number of samples per second
    unit : :class:`~astropy.units.core.Unit`, `str`, optional
        name of the unit for the data of this channel
    dtype : `numpy.dtype`, optional
        numeric type of data for this channel
    model : `str`, optional
        name of the SIMULINK front-end model that produces this `Channel`

    Notes
    -----
    The `Channel` structure implemented here is designed to match the
    data recorded in the LIGO Channel Information System
    (https://cis.ligo.org) for which a query interface is provided.
    """
    def __init__(self, ch, sample_rate=None, unit=None, dtype=None,
                 type=None, model=None, url=None):
        type_ = type
        # test for Channel input
        if isinstance(ch, Channel):
            sample_rate = sample_rate or ch.sample_rate
            unit = unit or ch.unit
            type_ = type_ or ch.type
            dtype = dtype or ch.dtype
            model = model or ch.model
            url = url or ch.url
            ch = ch.name
        # set attributes
        self.name = ch
        self.sample_rate = sample_rate
        self.unit = unit
        if type_ is not None:
            self.type = type_
        self.dtype = dtype
        self.model = model
        self.url = url

    # -------------------------------------------------------------------------
    # read-write properties

    @property
    def name(self):
        """Name of this `Channel`.

        This should follow the naming convention, with the following
        format: 'IFO:SYSTEM-SUBSYSTEM_SIGNAL'

        :type: `str`
        """
        return self._name

    @name.setter
    def name(self, n):
        try:
            self._name, self.type = str(n).rsplit(',', 1)
        except IndexError:
            pass
        except ValueError:
            self._name = str(n)
        self._ifo, self._system, self._subsystem, self._signal = (
            parse_channel_name(self._name))

    @property
    def sample_rate(self):
        """Rate of samples (Hertz) for this `Channel`.

        :type: :class:`~astropy.units.quantity.Quantity`
        """
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, rate):
        if isinstance(rate, units.Unit):
            self._sample_rate = rate
        elif rate is None:
            self._sample_rate = None
        elif isinstance(rate, units.Quantity):
            self._sample_rate = rate
        else:
            self._sample_rate = units.Quantity(float(rate), unit=units.Hertz)

    @property
    def unit(self):
        """Data unit for this `Channel`.

        :type: :class:`~astropy.units.core.Unit`
        """
        return self._unit

    @unit.setter
    def unit(self, u):
        if u is None:
            self._unit = None
        else:
            self._unit = units.Unit(u)

    @property
    def model(self):
        """Name of the SIMULINK front-end model that defines this `Channel`.

        :type: `str`
        """
        return self._model

    @model.setter
    def model(self, mdl):
        self._model = mdl and mdl.lower() or mdl

    @property
    def type(self):
        """DAQ data type for this channel.

        Valid values for this field are restricted to those understood
        by the NDS2 client sofware, namely:

        'm-trend', 'online', 'raw', 'reduced', 's-trend', 'static', 'test-pt'

        :type: `str`
        """
        try:
            return self._type
        except AttributeError:
            self._type = None
            return self.type

    @type.setter
    def type(self, type_):
        if type_ is None:
            self._type = None
        elif type_ in NDS2_CHANNEL_TYPESTR:
            self._type = NDS2_CHANNEL_TYPESTR[type_]
        elif type_.lower() in NDS2_CHANNEL_TYPE:
            self._type = type_.lower()
        else:
            raise ValueError("Channel type '%s' not understood." % type_)

    @property
    def ndstype(self):
        """NDS type integer for this `Channel`.

        This property is mapped to the `Channel.type` string.
        """
        return NDS2_CHANNEL_TYPE.get(self.type)

    @ndstype.setter
    def ndstype(self, type_):
        self.type = type_

    @property
    def dtype(self):
        """Numeric type for data in this `Channel`.

        :type: :class:`~numpy.dtype`
        """
        return self._dtype

    @dtype.setter
    def dtype(self, type_):
        if type_ is None:
            self._dtype = None
        else:
            self._dtype = numpy.dtype(type_)

    @property
    def url(self):
        """CIS browser url for this `Channel`.

        :type: `str`
        """
        return self._url

    @url.setter
    def url(self, href):
        self._url = href

    # -------------------------------------------------------------------------
    # read-only properties

    @property
    def ifo(self):
        """Interferometer prefix for this `Channel`.

        :type: `str`
        """
        return self._ifo

    @property
    def system(self):
        """Instrumental system for this `Channel`.

        :type: `str`
        """
        return self._system

    @property
    def subsystem(self):
        """Instrumental sub-system for this `Channel`.

        :type: `str`
        """
        return self._subsystem

    @property
    def signal(self):
        """Instrumental signal for this `Channel`.

        :type: `str`
        """
        return self._signal

    @property
    def texname(self):
        """Name of this `Channel` in LaTeX printable format.
        """
        return str(self).replace("_", r"\_")

    @property
    def ndsname(self):
        """Name of this `Channel` as stored in the NDS database
        """
        if self.type not in [None, 'raw', 'reduced']:
            return '%s,%s' % (self.name, self.type)
        return self.name

    # -------------------------------------------------------------------------
    # classsmethods

    @classmethod
    def query(cls, name, debug=False, timeout=None):
        """Query the LIGO Channel Information System for the `Channel`
        matching the given name

        Parameters
        ----------
        name : `str`
            name of channel
        debug : `bool`, optional
            print verbose HTTP connection status for debugging,
            default: `False`
        timeout : `float`, optional
            maximum time to wait for a response from the CIS

        Returns
        -------
        Channel
             a new `Channel` containing all of the attributes set from
             its entry in the CIS
        """
        channellist = ChannelList.query(name, debug=debug, timeout=timeout)
        if len(channellist) == 0:
            raise ValueError("No channels found matching '%s'." % name)
        if len(channellist) > 1:
            raise ValueError("%d channels found matching '%s', please refine "
                             "search, or use `ChannelList.query` to return "
                             "all results." % (len(channellist), name))
        return channellist[0]

    @classmethod
    @with_import('nds2')
    def query_nds2(cls, name, host=None, port=None, connection=None,
                   type=None):
        """Query an NDS server for channel information

        Parameters
        ----------
        name : `str`
            name of requested channel
        host : `str`, optional
            name of NDS2 server.
        port : `int`, optional
            port number for NDS2 connection
        connection : `nds2.connection`
            open connection to use for query
        type : `str`, `int`
            NDS2 channel type with which to restrict query

        Returns
        -------
        channel : `Channel`
            channel with metadata retrieved from NDS2 server

        Raises
        ------
        ValueError
            if multiple channels are found for a given name

        Notes
        -----
        .. warning::

           A `host` is required if an open `connection` is not given
        """
        return ChannelList.query_nds2([name], host=host, port=port,
                                      connection=connection, type=type,
                                      unique=True)[0]

    @classmethod
    def from_nds2(cls, nds2channel):
        """Generate a new channel using an existing nds2.channel object
        """
        # extract metadata
        name = nds2channel.name
        sample_rate = nds2channel.sample_rate
        unit = nds2channel.signal_units
        if not unit:
            unit = None
        ctype = nds2channel.channel_type_to_string(nds2channel.channel_type)
        # get dtype
        dtype = {nds2channel.DATA_TYPE_INT16: numpy.int16,
                 nds2channel.DATA_TYPE_INT32: numpy.int32,
                 nds2channel.DATA_TYPE_INT64: numpy.int64,
                 nds2channel.DATA_TYPE_FLOAT32: numpy.float32,
                 nds2channel.DATA_TYPE_FLOAT64: numpy.float64,
                 nds2channel.DATA_TYPE_COMPLEX32: numpy.complex64,
                }.get(nds2channel.data_type)
        return cls(name, sample_rate=sample_rate, unit=unit, dtype=dtype,
                   type=ctype)

    # -------------------------------------------------------------------------
    # methods

    def __str__(self):
        return self.name

    def __repr__(self):
        repr_ = '<Channel("%s"' % (str(self))
        if self.type:
            repr_ += ' [%s]' % self.type
        repr_ += ', %s' % self.sample_rate
        return repr_ + ') at %s>' % hex(id(self))

    def __eq__(self, other):
        for attr in ['name', 'sample_rate', 'unit', 'url', 'type', 'dtype']:
            try:
                if getattr(self, attr) != getattr(other, attr):
                    return False
            except TypeError:
                return False
        return True

    def __hash__(self):
        return hash((str(self), str(self.sample_rate), str(self.unit),
                    self.url, self.type, self.dtype))


_re_ifo = re.compile("[A-Z]\d:")
_re_cchar = re.compile("[-_]")


def parse_channel_name(name):
    """Decompose a channel name string into its components
    """
    if not name:
        return None, None, None, None
    # parse ifo
    if _re_ifo.match(name):
        ifo, name = name.split(":", 1)
    else:
        ifo = None
    # parse systems
    tags = _re_cchar.split(name, maxsplit=2)
    system = tags[0]
    if len(tags) > 1:
        subsystem = tags[1]
    else:
        subsystem = None
    if len(tags) > 2:
        signal = tags[2]
    else:
        signal = None
    return ifo, system, subsystem, signal


class ChannelList(list):
    """A `list` of `channels <Channel>`, with parsing utilities.
    """

    @property
    def ifos(self):
        """The `set` of interferometer prefixes used in this
        `ChannelList`.
        """
        return set([c.ifo for c in self])

    @classmethod
    def from_names(cls, *names):
        new = cls()
        for namestr in names:
            for name in new._split_names(namestr):
                new.append(Channel(name))
        return new

    @staticmethod
    def _split_names(namestr):
        """Split a comma-separated list of channel names.
        """
        out = []
        namestr = re_quote.sub('', namestr)
        while True:
            namestr = namestr.strip('\' \n')
            if ',' not in namestr:
                break
            for nds2type in NDS2_CHANNEL_TYPE.keys() + ['']:
                if nds2type and ',%s' % nds2type in namestr:
                    try:
                        channel, ctype, namestr = namestr.split(',', 2)
                    except ValueError:
                        channel, ctype = namestr.split(',')
                        namestr = ''
                    out.append('%s,%s' % (channel, ctype))
                    break
                elif nds2type == '' and ',' in namestr:
                    channel, namestr = namestr.split(',', 1)
                    out.append(channel)
                    break
        if namestr:
            out.append(namestr)
        return out

    def find(self, name):
        """Find the `Channel` with a specific name in this `ChannelList`.

        Parameters
        ----------
        name : `str`
            name of the `Channel` to find

        Returns
        -------
        index : `int`
            the position of the first `Channel` in this `ChannelList`
            whose `~Channel.name` matches the search key.

        Raises
        ------
        ValueError
            if no matching `Channel` is found.
        """
        for i, chan in enumerate(self):
            if name == chan.name:
                return i
        raise ValueError(name)

    def sieve(self, name=None, sample_rate=None, sample_range=None,
              exact_match=False, **others):
        """Find all `Channels <Channel>` in this list matching the
        specified criteria.

        Parameters
        ----------
        name : `str`, or regular expression
            any part of the channel name against which to match
            (or full name if `exact_match=False` is given)
        sample_rate : `float`
            rate (number of samples per second) to match exactly
        sample_range : 2-`tuple`
            `[low, high]` closed interval or rates to match within
        exact_match : `bool`
            return channels matching `name` exactly, default: `False`

        Returns
        -------
        new : `ChannelList`
            a new `ChannelList` containing the matching channels
        """
        # format name regex
        if isinstance(name, re._pattern_type):
            flags = name.flags
            name = name.pattern
        else:
            flags = 0
        if exact_match:
            name = name.startswith(r'\A') and name or r"\A%s" % name
            name = name.endswith(r'\Z') and name or r"%s\Z" % name
        name_regexp = re.compile(name, flags=flags)
        c = list(self)
        if name is not None:
            c = [entry for entry in c if
                 name_regexp.search(entry.name) is not None]
        if sample_rate is not None:
            sample_rate = (isinstance(sample_rate, units.Quantity) and
                           sample_rate.value or float(sample_rate))
            c = [entry for entry in c if entry.sample_rate and
                 entry.sample_rate.value == sample_rate]
        if sample_range is not None:
            c = [entry for entry in c if
                 sample_range[0] <= float(entry.sample_rate) <=
                 sample_range[1]]
        for attr, val in others.iteritems():
            if val is not None:
                c = [entry for entry in c if
                     (hasattr(entry, attr) and getattr(entry, attr) == val)]

        return self.__class__(c)

    @classmethod
    def query(cls, name, debug=False, timeout=None):
        """Query the LIGO Channel Information System a `ChannelList`.

        Parameters
        ----------
        name : `str`
            name of channel, or part of it.
        debug : `bool`, optional
            print verbose HTTP connection status for debugging,
            default: `False`
        timeout : `float`, optional
            maximum time to wait for a response from the CIS

        Returns
        -------
        `ChannelList`
            a new list containing all `Channels <Channel>` found.
        """
        from .io import cis
        return cis.query(name, debug=debug, timeout=timeout)

    @classmethod
    @with_import('nds2')
    def query_nds2(cls, names, host=None, port=None, connection=None,
                   type=None, unique=False):
        """Query an NDS server for channel information

        Parameters
        ----------
        name : `str`
            name of requested channel
        host : `str`, optional
            name of NDS2 server.
        port : `int`, optional
            port number for NDS2 connection
        connection : `nds2.connection`
            open connection to use for query
        type : `str`, `int`
            NDS2 channel type with which to restrict query
        unique : `bool`, optional
            require a unique query result for each name given, default `False`

        Returns
        -------
        channellist : `ChannelList`
            list of `Channels <Channel>` with metadata retrieved from
            NDS2 server

        Raises
        ------
        ValueError
            if multiple channels are found for a given name and `unique=True`
            is given

        Notes
        -----
        .. warning::

           A `host` is required if an open `connection` is not given
        """
        from ..io.nds import (auth_connect, NDSWarning)
        out = cls()
        # connect
        if connection is None:
            if host is None:
                raise ValueError("Please given either an open nds2.connection,"
                                 " or the name of the host to connect to")
            from ..io.nds import auth_connect
            connection = auth_connect(host, port)
        if isinstance(names, str):
            names = [names]
        for name in names:
            # format channel query
            if (type and (isinstance(type, (unicode, str)) or
                         (isinstance(type, int) and log(type, 2).is_integer()))):
                c = Channel(name, type=type)
            else:
                c = Channel(name)
            if c.ndstype is not None:
                found = connection.find_channels(c.ndsname, c.ndstype)
            elif type is not None:
                found = connection.find_channels(c.name, type)
            else:
                found = connection.find_channels(c.name)
            found = ChannelList(map(Channel.from_nds2, found))
            _names = set([c.ndsname for c in found])
            if unique and len(_names) == 0:
                raise ValueError("No match for channel %r in NDS database"
                                 % name)
            if unique and len(_names) > 1:
                raise ValueError(
                    "Multiple matches for channel '%s' in NDS database, "
                    "ambiguous request:\n    %s"
                     % (name, '\n    '.join(['%s (%s, %s)'
                        % (str(c), c.type, c.sample_rate) for c in found])))
            elif unique and len(found) > 1:
                warnings.warn('Multiple instances of %r found with different '
                              'sample rates, returning first.' % (name),
                              NDSWarning)
                out.append(found[0])
            else:
                out.extend(found)
        return out

    @classmethod
    @with_import('nds2')
    def query_nds2_availability(cls, channels, start, end,
                                host, port=None):
        """Query for when data are available for these channels in NDS2

        Parameters
        ----------
        channels : `list`
            list of `Channel` or `str` for which to search
        start : `int`
            GPS start time of search, or any acceptable input to
            :meth:`~gwpy.time.to_gps`
        end : `int`
            GPS end time of search, or any acceptable input to
            :meth:`~gwpy.time.to_gps`
        host : `str`
            name of NDS server
        port : `int`, optional
            port number for NDS connection

        Returns
        -------
        nested dict
            a `dict` of (channel, `dict`) pairs where the nested `dict`
            is over (frametype, SegmentList) segment-availability pairs
        """
        names = []
        for c in channels:
            name = str(c)
            if isinstance(c, Channel) and c.sample_rate:
                name += '%%%d' % c.sample_rate.value
            names.append(name)

        span = Segment(int(to_gps(start)), int(to_gps(end)))
        # build nds2_channel_source call
        cmd = ['nds2_channel_source', '-a',
               '-s', str(span[0]),
               '-n', host]
        if port is not None:
            cmd.extend(['-p', str(port)])
        cmd.extend(names)
        # call
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        out, err = proc.communicate()
        retcode = proc.poll()
        if retcode:
            print(err, file=sys.stderr)
            raise subprocess.CalledProcessError(retcode, ' '.join(cmd),
                                                output=out)

        # parse output
        re_seg = re.compile('\A(?P<obs>[A-Z])-(?P<type>\w+):'
                            '(?P<start>\d+)-(?P<end>\d+)\Z')
        segs = {}
        i = 0
        for line in out.splitlines():
            if line.startswith('Requested source list:'):
                continue
            elif line.startswith('Error in daq'):
                raise RuntimeError(line)
            elif not line.startswith(names[i].split('%')[0]):
                raise RuntimeError("Error parsing nds2_channel_source output")
            chan = channels[i]
            i += 1
            segs[chan] = SegmentListDict()
            for seg in line.split(' ', 1)[1].strip('{').rstrip('}').split(' '):
                try:
                    m = re_seg.search(seg).groupdict()
                except AttributeError:
                    if not seg:
                        continue
                    raise RuntimeError("Error parsing nds2_channel_source "
                                       "output:\n%s" % line)
                ftype = m['type']
                try:
                    seg = Segment(int(m['start']), int(m['end'])) & span
                except ValueError:
                    continue
                if ftype in segs[chan]:
                    segs[chan][ftype].append(seg)
                else:
                    segs[chan][ftype] = SegmentList([seg])
            segs[chan].coalesce()
        return segs
