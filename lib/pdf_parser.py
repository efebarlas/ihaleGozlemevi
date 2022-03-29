from pdfminer.high_level import extract_pages as pdf_extract_pages
from pdfminer.layout import LTTextContainer
from more_itertools import seekable
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

class IndexFault():
    def __init__(self, obj, idx):
        self.obj = obj
        self.idx = idx
    def __str__(self):
        return f'IndexFault: object {self.obj} with length {len(self.obj)} cannot be indexed at {self.idx}'

def testIndexFault():
    a = [1,2,3,4]
    d = IndexFault(a,5)
    assert d.__str__() == f'IndexFault: object {a} with length 4 cannot be indexed at 5' 

# ihale specific stuff
class Bulten():
    def __init__(self, pdfFilePath):
        self.bulten_tree = seekable(getPdfTree(pdfFilePath))
    def getPage(self,pageNum):
        return safeSeek(self.bulten_tree, pageNum)
    def getIhaleTipi(self):
        self.first_page = self.getPage(0)
        for i in self.first_page:
            if isinstance(i, LTTextContainer):
                print(i.get_text())

if __name__ == "__main__":
    testIndexFault()
    bulten = Bulten("./BULTEN_28032022_MAL_SONUC.pdf")
    bulten.getIhaleTipi()
    print('h')

