from dataclasses import dataclass
from ekap_client import EKAPClient
from pdf_parser import Bulten
from datetime import datetime as dt
from datetime import timedelta, date
from faults import *
import utils
from functools import reduce

@dataclass
class LabeledBulten:
    """Class for bulten tests where the expected answer is known."""
    name: str
    ihale_tipi: str
    bulten: Bulten
    
    


def getRandomAnnuals(k=1):
    # returns: list of bulten objects (k per year)
    e = EKAPClient()
    year_now = date.today().year
    bultenler = []
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

def testGetRandomAnnuals(k=1):
    def tallyReduceFn(tally, year):
        tally[year] = 1 if year not in tally else tally[year] + 1
        return tally

    bultenler = getRandomAnnuals(k)
    cur_year = date.today().year
    assert len(bultenler) == k * (cur_year - 2010 + 1)

    years = list(map(lambda bulten: bulten.getYear(), bultenler))
    yearTally = reduce(tallyReduceFn, years, dict())
    
    expectedYears = [i//k for i in range(2010*k, cur_year*k + 1)]
    expectedTally = reduce(tallyReduceFn, expectedYears, dict())

    assert yearTally == expectedTally
if __name__ == "__main__":
    testGetRandomAnnuals()
#def getRandomLabeledAnnuals(k=1):
    # returns: list of labeled bulten objects (k per year)