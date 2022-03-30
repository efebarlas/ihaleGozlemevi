from pdfminer.high_level import extract_pages as pdf_extract_pages
from pdfminer.layout import LTTextContainer
from more_itertools import seekable
import utils
from dataclasses import dataclass
import re
from faults import *
from datetime import datetime as dt
from pathlib import Path


# generic pdf stuff
def getPdfTree(pdfFilePath):
    # returns generator[PDF pages]
    return pdf_extract_pages(pdfFilePath)

def safeSeek(seekbl, idx):
    seekbl.seek(idx)
    try:
        return next(seekbl)
    except StopIteration:
        return IndexFault(seekbl, idx)



@dataclass
class BBox:
    """Class for bulten tests where the expected answer is known."""
    x0: float
    x1: float
    y0: float
    y1: float

# ihale specific stuff
class Bulten():
    def __init__(self, pdfFilePath):
        self.bultenTree = seekable(getPdfTree(pdfFilePath))
        self.documentName = Path(pdfFilePath).name
        self._date = None
    def getPage(self,pageNum):
        return safeSeek(self.bultenTree, pageNum)
    def getIhaleTipi(self):
        for i in self.getPage(0):
            if isinstance(i, LTTextContainer):
                print(i.get_text())
    def printBultenText(self):
        for i in self.bultenTree:
            print(f'\n\n***PAGE {i}***\n\n')
            for j in i:
                if isinstance(j, LTTextContainer):
                    print(utils.asciify(j.get_text()))
    def getIhaleList(self):
        # returns: seekable generator which looks through pdf and parses ihale's
        def ihaleGenerator():
            ihale = "lol"
            yield ihale
        return seekable(ihaleGenerator)
    def getDate(self):
        if self._date != None:
            return self._date

        
        second_page = self.getPage(1)
        dateBBox = BBox(300, 600, 750, 842.04)
        for i in second_page:
            if isinstance(i, LTTextContainer) and isWithinBBox(dateBBox, i):
                dateStr = utils.asciify(i.get_text().lower())
                break
                        
        regex = re.compile('(\d{,2}) (ocak|subat|mart|nisan|mayıs|mayis|haziran|temmuz|agustos|eylul|ekim|kasım|kasim|aralık|aralik) (\d{4})')
        try:
            day, month, year = regex.search(dateStr).groups()
        except:
            return DocumentFault('bulten tarihi', self.documentName)
        monthNum = utils.monthNameToNum(month)
        date = dt.strptime(f'{day}/{monthNum}/{year}', '%d/%m/%Y')

        self._date = date
        return date
    def getYear(self):
        date = self.getDate().year
        return date
def isWithinBBox(capturingBBox, capturedBBox):
    # you were here, to help with parsing of date & year!!!
    # you can test this using testGetRandomAnnuals

    a = capturingBBox
    b = capturedBBox

    return (a.x0 <= b.x0 and a.x1 >= b.x1 and a.y0 <=b.y0 and a.y1 >= b.y1)
        
        
        

if __name__ == "__main__":
    #testIndexFault()
    bulten = Bulten("./BULTEN_28032022_MAL_SONUC.pdf")
    #bulten.getIhaleTipi()
    #print('h')
    bulten.printBultenText()

