from random import randrange

class PDFComponent():
    def __init__(self, component):
        self.component = component
    # there's a chance that the text has characters with
    # different colors. so we just look at three characters and
    # return 'mixed' if they aren't all the same.
    # we don't look at each and every character because
    # i suspect that is expensive to do for all text.
    # TODO: FIX THIS!
    def textColor(self):
        txtObj = self.component._objs[0]
        charColors = tuple(txtObj._objs[randrange(0, len(txtObj))]['stroking_color'] for _ in range(3))
        c = charColors[0]
        for i in charColors:
            if i != c:
                return "mixed"
        return c