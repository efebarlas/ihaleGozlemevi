from dataclasses import dataclass
from ihaleGozlemevi.lib.ekap_client import EKAPClient
from ihaleGozlemevi.lib.pdf_parser import Bulten
from datetime import datetime as dt
from datetime import timedelta, date
from ihaleGozlemevi.lib.faults import *
from ihaleGozlemevi.lib import utils
from functools import reduce
import logging
log = logging.getLogger(__name__)

@dataclass
class LabeledBulten:
    """Class for bulten tests where the expected answer is known."""
    name: str
    ihale_tipi: str
    bulten: Bulten
    
    


def getRandomAnnuals(k=1, **kwargs):
    # returns: list of bulten objects (k per year)
    e = EKAPClient()
    year_now = date.today().year
    bultenler = []
    # TODO: implement getting sonuc bultenleri from this fn too
    for y in range(2010, int(year_now) + 1):
        offset = y - 2010
        while len(bultenler) < (offset + 1) * k:
            d = utils.randomDate(year=str(y))
            while d.weekday() >= 5:
                d = utils.randomDate(year=str(y))
            d = dt.combine(d, dt.min.time())
            dateStr = dt.strftime(d, "%d.%m.%Y")

            b = e.getBulten(dateStr, "mal", noDownload=True) # read-through cache
            if isinstance(b, Fault):
                continue
            bultenler.append(b)
    e.close()
    return bultenler

#def getRandomLabeledAnnuals(k=1):
    # returns: list of labeled bulten objects (k per year)