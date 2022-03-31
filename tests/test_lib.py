from datetime import date
from functools import reduce
import unittest


from .context import data_driven_design as ddd  


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

        k = 3
        bultenler = ddd.getRandomAnnuals(k)
        # no cursor
        textSearchers = map(lambda bulten: bulten.textSearcher('temizlik'), bultenler)
        for searcher in textSearchers:
            print('\n\n\n\n\n\nNew bulten\n\n\n\n\n\n')
            for component in searcher:
                print(component)
class TestPdfParser(unittest.TestCase):
    def test_findKeyBBoxes(self):
        pass
