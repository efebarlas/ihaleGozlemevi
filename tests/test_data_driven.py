from datetime import date
from datetime import datetime as dt
from functools import reduce
import unittest
from context import utils
from context import data_driven_design as ddd
from pdfminer.layout import LTTextContainer

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)




class TestPdfParser(unittest.TestCase):
    # data-driven-testing of how many text components don't only have one color
    def test_textColorAmbiguous(self):
        bultenler = ddd.getRandomAnnuals(1)
        pages = utils.flatten(map(lambda x: ddd.getRandomPages(x, 2), bultenler))
        textComponents = utils.flatten(map(lambda page: page.getComponentsByType(LTTextContainer), pages))
        textColors = map(lambda tc: tc.textColor(), textComponents)
        
        ambiguous = 0
        total = 0

        for c in textColors:
            total += 1
            if c == "mixed":
                ambiguous += 1
        self.assertGreaterEqual(ambiguous / total, 0.99)