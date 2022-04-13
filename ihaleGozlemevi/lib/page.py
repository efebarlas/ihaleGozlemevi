from .component import PDFComponent

class PDFPage():
    def __init__(self, page):
        self.page = page
    def getComponentsByType(self, componentType):
        return map(lambda c: PDFComponent(c), filter(lambda c: isinstance(c, componentType), self.page))