# Licensed under a 3-clause BSD style license - see LICENSE.rst

"""Package to do gravitational wave astrophysics with python
"""

# import core astropy modules
from astropy import table
from astropy.units.quantity import WARN_IMPLICIT_NUMERIC_CONVERSION
WARN_IMPLICIT_NUMERIC_CONVERSION.set(False)

import warnings
warnings.filterwarnings("ignore", "Module (.*) was already import from")

# set metadata
from . import version
__author__ = "Duncan Macleod <duncan.macleod@ligo.org>"
__version__ = version.version