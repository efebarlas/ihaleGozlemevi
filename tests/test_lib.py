from datetime import date
from datetime import datetime as dt
from functools import reduce
import unittest
from ihaleGozlemevi.lib import utils
from ihaleGozlemevi.lib import data_driven_design as ddd
import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
#from .context import data_driven_design as ddd  


class TestDataDrivenDesign(unittest.TestCase):
    def test_getRandomAnnuals(self):

        def tallyReduceFn(tally, year):
            tally[year] = 1 if year not in tally else tally[year] + 1
            return tally
        k = 3
        bultenler = ddd.getRandomAnnuals(k)
        cur_year = date.today().year
        self.assertEqual(len(bultenler), k * (cur_year - 2010 + 1))

        years = list(map(lambda bulten: bulten.getYear(), bultenler))
        yearTally = reduce(tallyReduceFn, years, dict())
        
        expectedYears = [i//k for i in range(2010*k, k*(cur_year + 1))]
        expectedTally = reduce(tallyReduceFn, expectedYears, dict())

        self.assertEqual(yearTally,expectedTally)
    def test_textSearcher(self):

        # 10 dates
        dates = ["31.01.2017","30.06.2016","29.03.2013"]
        
        #dates = ["31.01.2017","30.06.2016","29.03.2013","28.11.2014","26.06.2013","24.04.2015","01.07.2019","01.04.2021","04.11.2020", "05.07.2018"]
        expectedTally = {"31.01.2017": 36, "30.06.2016": 23, "29.03.2013": 39, "28.11.2014": 10, "26.06.2013": 10, "24.04.2015": 21, "01.07.2019": 14,"01.04.2021":36,"04.11.2020":16, "05.07.2018":36}
        
        bultenler = ddd.getBultensByDates(dates)
        # no cursor
        textSearchers = map(lambda bulten: (dt.strftime(bulten.getDate(), "%d.%m.%Y"), bulten.textSearcher('temizlik')), bultenler)
        
        actualTally = {}
        for dateStr, searcher in textSearchers:
            for find in searcher:
                foundTxt = utils.asciify(find.get_text().lower())
                count = foundTxt.count('temizlik')
                log.debug(f'There are {count} counts of the text search query within this component')
                actualTally[dateStr] = count if dateStr not in actualTally else actualTally[dateStr] + count
            self.assertEqual(expectedTally[dateStr], actualTally[dateStr])
class TestPdfParser(unittest.TestCase):
    def test_getPage(self):
        dates = ["31.01.2017"]

        bultenler = ddd.getBultensByDates(dates)

        for i in bultenler:
            expectedPageId = 5
            page = i.getPage(expectedPageId)
            # pageid is one-indexed
            self.assertEqual(page.pageid - 1, expectedPageId)
       
        for i in bultenler:
            expectedPageId = 2
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)

        for i in bultenler:
            expectedPageId = 20
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)

        for i in bultenler:
            expectedPageId = 10
            page = i.getPage(expectedPageId)
            self.assertEqual(page.pageid - 1, expectedPageId)