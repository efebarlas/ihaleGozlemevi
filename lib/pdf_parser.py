from pdfminer.high_level import extract_pages as pdf_extract_pages
from pdfminer.layout import LTTextContainer
# from more_itertools import seekable
from ihaleGozlemevi.lib import utils
from dataclasses import dataclass
import re
from ihaleGozlemevi.lib.faults import *
from datetime import datetime as dt
from pathlib import Path


import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


# generic pdf stuff
def getPdfTree(pdfFilePath):
    # returns generator[PDF pages]
    return pdf_extract_pages(pdfFilePath)

# def safeSeek(seekbl, idx):
#     seekbl.seek(idx)
#     try:
#         return next(seekbl)
#     except StopIteration:
#         return IndexFault(seekbl, idx)

# TODO: consider using a different pdfminer.six api, because random seeking with extract_pages is very slow

def safeSeek(seekbl, idx):
    seekbl.seek(idx)
    try:
        return next(seekbl)
    except StopIteration:
        return IndexFault(seekbl, idx)

@dataclass
# TODO: upgrade Python to 3.10 and use slots=True for performance improvements
class BBox:
    """Class for bulten tests where the expected answer is known."""
    x0: float
    x1: float
    y0: float
    y1: float

class PDFCursor():
    #__slots__ = ("pageNum","pdfComponent")
    def __init__(self, LTPage, LTComponent=None):
        self.pageNum = LTPage.pageid
        #self.LTComponent = LTComponent
        if LTComponent == None:
            self.bbox = BBox(0,0,LTPage.y1,LTPage.y1)
        else:
            self.bbox = BBox(LTComponent.x0, LTComponent.x1, LTComponent.y0, LTComponent.y1)
        self.pageBBox = BBox(LTPage.x0, LTPage.x1, LTPage.y0, LTPage.y1)
    def getBBox(self):
        return self.bbox
    def getPageBelow(self):
        # returns bbox that cuts out the part above and including the cursor's bbox
        return BBox(self.pageBBox.x0, self.pageBBox.x1, self.pageBBox.y0, self.bbox.y0)
    def isAbove(self, bbox):
        pageBelow = self.getPageBelow()
        return isWithinBBox(pageBelow, bbox)
# ihale specific stuff
class Bulten():
    def __init__(self, pdfFilePath):
        self.pageCursor = getPdfTree(pdfFilePath)
        self.pdfFilePath = pdfFilePath
        self.documentName = Path(pdfFilePath).name
        self._date = None
        self._currPageNum = -1

    def getPage(self,pageNum):
        if pageNum < self._currPageNum:
            self.pageCursor = getPdfTree(self.pdfFilePath)
            self._currPageNum = -1
            return self.getPage(pageNum)
        try:
            for _ in range(pageNum - self._currPageNum - 1):
                next(self.pageCursor)
            page = next(self.pageCursor)
        except StopIteration:
            return IndexFault(self.pageCursor, pageNum)
        
        self._currPageNum = pageNum  
        log.debug(f'New page fetched: {self.documentName}:{pageNum}')
        return page

    def getIhaleTipi(self):
        for i in self.getPage(0):
            if isinstance(i, LTTextContainer):
                print(i.get_text())
    def printBultenText(self):
        for i in self.pageCursor:
            print(f'\n\n***PAGE {i}***\n\n')
            for j in i:
                if isinstance(j, LTTextContainer):
                    print(utils.asciify(j.get_text()))
    def getIhaleList(self):
        # returns: seekable generator which looks through pdf and parses ihale's
        # TODO: hello
        def ihaleGenerator():
            ihale = "lol"
            yield ihale
        return ihaleGenerator
    def getDate(self):
        if self._date != None:
            return self._date

        
        second_page = self.getPage(1)
        dateBBox = BBox(300, 600, 750, 842.04)
        for i in second_page:
            if isinstance(i, LTTextContainer) and isWithinBBox(dateBBox, i):
                dateStr = utils.asciify(i.get_text().lower())
                break
                        
        regex = re.compile('(\\d{,2}) (ocak|subat|mart|nisan|mayıs|mayis|haziran|temmuz|agustos|eylul|ekim|kasım|kasim|aralık|aralik) (\\d{4})')
        try:
            day, month, year = regex.search(dateStr).groups()
        except:
            return DocumentFault('bulten tarihi', self.documentName)
        monthNum = utils.monthNameToNum(month)
        date = dt.strptime(f'{day}/{monthNum}/{year}', '%d/%m/%Y')

        self._date = date
        return date
    def getYear(self):
        date = self.getDate()
        if isinstance(date, Fault):
            return date
        return date.year
    def textSearcher(self, text, cursor=None):
        # returns generator which yields PDFCursors to components with the specified text 
        # NOTE: search queries are case-insensitive and asciified!!

        # TODO: we may only care about visible text (i.e., black text on white bg). there should be an arg about this!
        textQuery = utils.asciify(text.lower())
        if textQuery != text:
            log.warning(f'PDF is searched for text {text}, which isn\'t in lower case OR has non-ASCII characters!')

        if cursor is None:
            cursor = PDFCursor(self.getPage(0))
        startPage = self.getPage(cursor.pageNum)
        cpn = cursor.pageNum
        # TODO: could be more functional with maps and all
        for component in startPage:
            if isinstance(component, LTTextContainer) and \
                cursor.isAbove(component):
                componentText = utils.asciify(component.get_text().lower())
                if componentText.find(textQuery) != -1:
                    log.debug(f'text found in page num: {cpn}')
                    yield component
        
        pageNum = cursor.pageNum + 1
        page = self.getPage(pageNum)
        while not isinstance(page, Fault):
            for component in page:
                if isinstance(component, LTTextContainer):
                    componentText = utils.asciify(component.get_text().lower())
                    if componentText.find(textQuery) != -1:
                        log.debug(f'text found in page num: {pageNum}')
                        yield component
            pageNum += 1
            page = self.getPage(pageNum)

        if not isinstance(page, IndexFault):
            log.warning('Page retrieval failed unexpectedly')
            log.warning(page)
def isWithinBBox(capturingBBox, capturedBBox):
    # this function supports both LTComponents and BBox objects

    a = capturingBBox
    b = capturedBBox

    return (a.x0 <= b.x0 and a.x1 >= b.x1 and a.y0 <=b.y0 and a.y1 >= b.y1)
def findKeyBBoxes(cursor: PDFCursor):

    # returns a partitioning of the document space to capture value bboxes into keys
    # TODO: must be aware of page breaks!!
    # ne olabilir: key onceki sayfada kalir ama yazi page break'e gider, header
    # ve footer yaziyi ortadan boler.
    # bir element'in header'in onunde oldugunu header cizgisinden anlayabiliriz.
    # hatta, sanki header ve footer hep ayni absolut konumda gibi.
    # in that case, sonraki sayfadaki value yazisini onceki sayfayla birlestirmek icin 
    

    # looks below provided cursor
    # REASONING:
    # Ihale bultenlerindeki ilanlardaki metadata,
    # sola dayali key ve saga dayali degerlerden olusuyor.
    #
    # Key X'in degeri ardisik key'in yatay pozisyonuna dusmuyor.
    # Ardisik key'lerin yatay pozisyonlari alinarak o key'e
    # karsilik sonuc bu sekilde bulunabilir.

    # Tek istisna: Merkez-aligned degerler key'in ustune gecebiliyor.
    # data-driven-design: En cok yatay deger overlap'e sahip key o value ile eslestirilir.
    #textQuery = utils.asciify(text.lower())
    #if textQuery != text:
    #   log.warning(f'PDF is searched for text {text}, which isn\'t in lower case OR has non-ASCII characters!')

    if cursor is None:
        cursor = PDFCursor(self.getPage(0))
    startPage = self.getPage(cursor.pageNum)

    # TODO: could be more functional with maps and all
    for component in startPage:
        if isinstance(component, LTTextContainer) and \
            cursor.isAbove(component):
            componentText = utils.asciify(component.get_text().lower())
            if componentText.find(textQuery) != -1:
                yield component
    
    pageNum = cursor.pageNum + 1
    page = self.getPage(pageNum)
    while not isinstance(page, Fault):
        for component in page:
            if isinstance(component, LTTextContainer):
                componentText = utils.asciify(component.get_text().lower())
                if componentText.find(textQuery) != -1:
                    yield component
        pageNum += 1
        page = self.getPage(pageNum)

    if not isinstance(page, IndexFault):
        log.warning('Page retrieval failed unexpectedly')
        log.warning(page)
    pass
def findValueBBoxes():
    # returns all bboxes that are likely to be values
    pass
def BBoxToDict():
    # given the key partitioning and value bboxes, will return a dictionary of key-value pairs
    pass
        
        

# if __name__ == "__main__":
#     #testIndexFault()
#     bulten = Bulten("./BULTEN_28032022_MAL_SONUC.pdf")
#     #bulten.getIhaleTipi()
#     #print('h')
#     bulten.printBultenText()

