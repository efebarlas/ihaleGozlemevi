from dataclasses import dataclass
from typing import List
from .ekap_client import EKAPClient
from .pdf_parser import Bulten
from datetime import datetime as dt
from datetime import timedelta, date
from .faults import IndexFault, Fault
from . import utils
from functools import reduce
from random import randrange
from .page import PDFPage

import logging
log = logging.getLogger(__name__)

@dataclass
class LabeledBulten:
    """Class for bulten tests where the expected answer is known."""
    name: str
    ihale_tipi: str
    bulten: Bulten
    
# TODO: make this lazy-evaluated, so that failing tests fail quicker
def getBultensByDates(dates: List[str], ihaleType="mal"):
    # returns: list of bulten objects at specified dates
    # dates: List[date strings]
    e = EKAPClient()
    bultenler = [e.getBulten(date, ihaleType) for date in dates]
    e.close()
    
    return bultenler
# TODO: make this lazy-evaluated, so that failing tests fail quicker
def getRandomPages(bulten: Bulten, pageCount=1, pageRange=(0,10)) -> List[PDFPage]:
    s = pageRange[0]
    e = pageRange[1]
    
    pages = []
    for _ in range(pageCount):
        page = bulten.getPage(randrange(s,e))
        while isinstance(page, IndexFault):
            page = bulten.getPage(randrange(s,e))
        pages.append(PDFPage(page))
    return pages

# TODO: make this lazy-evaluated, so that failing tests fail earlier
def getRandomAnnuals(k=1, **kwargs) -> List[Bulten]:
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

def inspectPageLayout(pageNum):
    bultenler = getRandomAnnuals(k=1)
    sayfalar = map(lambda x: x.getPage(pageNum), bultenler)

    # we're interested in: position, text color, text, pageid, width, height.
    # text: try except & c.get_text()
    # x0,x1,y0,y1: has direct properties
    # width, height: has direct properties
    for sayfa in sayfalar:
        for component in sayfa:
            print('hello')


#def getRandomLabeledAnnuals(k=1):
    # returns: list of labeled bulten objects (k per year)