from pdfminer.psparser import PSKeyword
import pdfplumber

from ihaleGozlemevi.lib import utils
from dataclasses import dataclass
import re
from ihaleGozlemevi.lib.faults import *
from datetime import datetime as dt
from pathlib import Path

from thefuzz import fuzz, process

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)



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
def isWithinBBox(capturingBBox, capturedBBox):
    # this function supports both LTComponents and BBox objects

    a = capturingBBox
    b = capturedBBox

    return (a.x0 <= b.x0 and a.x1 >= b.x1 and a.y0 <=b.y0 and a.y1 >= b.y1)

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
        self.pdf = pdfplumber.open(pdfFilePath)
        self.pdfFilePath = pdfFilePath
        self.documentName = Path(pdfFilePath).name
        self._date = None
        self._currPageNum = -1
    def getPage(self,pageNum):
        pass
    def getIhaleTipi(self):
        pass
    def printBultenText(self):
        pass
    def isSonuc(self):
        pg = self.pdf.pages[1]
                
        line0 = pg.lines[0]
        line1 = pg.lines[1]
        headerBBox = (0, 0, pg.width, min(line0['top'], line1['top']))
        pg = pg.crop(headerBBox)
        txt = pg.extract_text()
        if 'sonuc' in utils.asciify(txt.lower()):
            return True
        return False
    def getIhaleList(self):
        
        CUTOFF=95

        # data-driven assumption: documents have > 2 pages
        pg = self.pdf.pages[1]
        # data-driven assumption: the header and footer will always have a line indicating where they end / begin.
        line0 = pg.lines[0]
        line1 = pg.lines[1]
        headerFooterBBox = (0, min(line0['top'], line1['top']), pg.width, max(line0['top'], line1['top'])) #x0,top,x1,bottom
        ts = {"vertical_strategy": "text", 
        "horizontal_strategy": "text",
        "keep_blank_chars": 'true',
        "explicit_vertical_lines": [0, 243], # so that the entire keys and values are captured. 242 represents the line between the key and value cells 
        "text_x_tolerance": 1, # data-driven decision: spaces take ~4 'pixels' and key-value text never gets horizontally closer than 5 pixels
        "text_y_tolerance": 3
        }


        
        ikn_tokens={'ikn': 'ikn', 'ihale kayit numarasi': 'ikn'}
        tablo_tokens=[{'ikn': 'ikn', 'ihale kayit numarasi': 'ikn'},
        {
            'adi': 'idare adi', 
            'adresi': 'idare adresi', 
            'telefon ve faks numarasi': 'idare telefon ve faks numarasi', 
            'elektronik posta adresi': 'idare e-posta adresi',
            'ihale dokumaninin gorulebilecegi ve e-imza kullanilarak indirilebilecegi internet sayfasi': 'kaynak',
            'ihale dokumaninin gorulebilecegi ve': 'kaynak',
            # sonuc bultenleri
            'tarihi': 'ihale tarihi',
            'turu': 'ihale turu',
            'usulu': 'ihale usulu',
            'yaklasik maliyeti': 'ihale yaklasik maliyeti',
            'sozlesmeye esas kisimlarinin yaklasik maliyeti': 'esas kisimlarin yaklasik maliyeti',
        },{
            'adi': 'mal adi',
            'niteligi, turu ve miktari': 'mal niteligi',
            'yapilacagi/teslim edilecegi yer': 'mal teslim yeri',
            'suresi/teslim tarihi': 'mal teslim tarihi',
            'ise baslama tarihi': 'ise baslama tarihi',
            'teslim yerleri': 'mal teslim yeri',
            'teslim tarihi': 'mal teslim tarihi'
        },{
            'ihale (son teklif verme) tarih ve saati': 'son teklif tarih ve saati',
            'ihale komisyonunun toplanti yeri (e-tekliflerin acilacagi adres)': 'komisyon toplanti yeri',
            'ihale komisyonunun toplanti yeri': 'komisyon toplanti yeri',
            'dokuman satin alan sayisi': 'dokuman satin alan sayisi',
            'dokuman ekap uzerinden e-imza kullanarak indiren sayisi': 'e-imza indiren sayisi',
            'toplam teklif sayisi': 'toplam teklif sayisi',
            'toplam gecerli teklif sayisi': 'toplam gecerli teklif sayisi',
            'yerli mali teklif eden istekli lehine fiyat avantaji uygulamasi': 'yerli mal fiyat avantaji',
            'tarihi ve saati': 'son teklif tarih ve saati',
            'yapilacagi yer': 'ihale yeri'
        },{
            'tarihi': 'sozlesme tarihi',
            'bedeli': 'sozlesme bedeli',
            'suresi': 'sozlesme suresi',
            'yuklenicisi': 'yuklenici',
            'yuklenicinin uyrugu': 'yuklenici uyrugu',
            'yuklenicinin adresi': 'yuklenici adresi',
        }]
        delimiters = [('idarenin',),('ihale konusu mal alimin','ihale konusu malin'), ('ihalenin',), ('ikn', 'ihale kayit numarasi')]
        sonuc_delimiters = [('ihalenin',), ('ihale konusu malin',), ('teklifler',), ('sozlesmenin',), ('ikn', 'ihale kayit numarasi')]
        if self.isSonuc():
            delimiters = sonuc_delimiters
        # fsm: ikn -> idarenin -> ihale konusu mal aliminin -> ihalenin (end of table) ikn->...
        tableCounter = 0
        tablesPerIhale = 5 if self.isSonuc() else 4
        ihaleBreak = False
        keys = tablo_tokens[tableCounter].keys()
        ihale = {}
        for pg in self.pdf.pages[6:]: #[6:] ,TEMPORARY for faster testing
            pg = pg.crop(headerFooterBBox)
            tables = pg.extract_tables(ts)
            for table in tables:
                for line in table:
                    if len(line) < 3:
                        continue
                    if len(line) > 3:
                        print('what?')
                    k, _, v = line
                    
                    k = utils.asciify(k.lower())
                    if k in ('ikn', 'ihale kayit numarasi'):
                        if ihaleBreak:
                            yield ihale
                            ihale = {}
                        ihaleBreak = True
                    if not ihaleBreak:
                        continue
                    k = k.split(')',maxsplit=1)[-1] # a), b), c)'yi gecmek adina
                    if process.extractOne(k.split('-',maxsplit=1)[-1], delimiters[tableCounter], score_cutoff=CUTOFF): # 1-, 2-, 3-'u gecmek adina
                        tableCounter += 1
                        tableCounter %= tablesPerIhale
                        keys = tablo_tokens[tableCounter].keys()
                        if tableCounter != 0:
                            continue
                    res = process.extractOne(k, keys, score_cutoff=CUTOFF)
                    #if res is None:
                        # # if next table has the answers, advance pointer
                        # res = process.extractOne(k, tablo_tokens[(tableCounter + 1) % tablesPerIhale].keys(), score_cutoff=CUTOFF)
                        # if res is not None:
                        #     tableCounter = (tableCounter + 1) % tablesPerIhale
                        #     keys = tablo_tokens[tableCounter].keys()
                        #     if tableCounter == 0: # loop back but segment wasn't ikn
                        #         log.debug('ihale table parsing fault')
                    if res is not None and tablo_tokens[tableCounter][res[0]] not in ihale:
                        ihale[tablo_tokens[tableCounter][res[0]]] = v
            print(tables)
    def getDate(self):
        if self._date != None:
            return self._date
        pass
    def getYear(self):
        date = self.getDate()
        if isinstance(date, Fault):
            return date
        return date.year
    def textSearcher(self, text, cursor=None):
        pass
def isWithinBBox(capturingBBox, capturedBBox):
    # this function supports both LTComponents and BBox objects

    a = capturingBBox
    b = capturedBBox

    return (a.x0 <= b.x0 and a.x1 >= b.x1 and a.y0 <=b.y0 and a.y1 >= b.y1)
