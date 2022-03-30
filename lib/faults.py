class Fault():
    def __init__(self):
        pass
    def __str__(self):
        pass
class DeprecationFault(Fault):
    def __init__(self):
        pass
    def __str__(self):
        return "The EKAP client may be deprecated. Please update the EKAP client to compatibilize with the current EKAP UI"
class ValidationFault(Fault):
    def __init__(self, validatedObj, schemaType):
        self.validatedObject = validatedObj
        self.schemaType = schemaType
    def __str__(self):
        return f"ValidationFault: object '{self.validatedObject}' could not be validated against the '{self.schemaType}' schema"
class ResmiTatilFault(Fault):
    def __init__(self):
        pass
    def __str__(self):
        return f"ResmiTatilFault: EKAP girilen tarihin resmi tatil oldugunu soyluyor."
class DiskCacheFault(Fault):
    def __init__(self, data_type, filePath):
        self.data_type = data_type
        self.filePath = filePath
        pass
    def __str__(self):
        return f"CacheFault: {self.filePath} of type {self.data_type} could not be found on disk"

class DocumentFault(Fault):
    def __init__(self, field, documentName):
        self.field = field
        self.documentName = documentName 
        pass
    def __str__(self):
        return f"DocumentFault: document '{self.documentName}' could not be parsed for field '{self.field}'."

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