from collections import defaultdict

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch, cm
from reportlab.pdfbase.pdfform import textFieldRelative
from reportlab.platypus.flowables import Flowable
from reportlab.platypus import Image, Paragraph


class PageMarker(Flowable):
    def __init__(self, name, description):
        print(80 * '*')
        print(repr(description))
        self.name = name
        self.description = description

    def wrap(self, availWidth, availHeight):
        return Paragraph('test', getSampleStyleSheet()['Normal']).wrap(availWidth, availHeight)

    def draw(self):
        if not hasattr(self.canv, '_pdfgen_page_count'):
            self.canv._pdfgen_page_count = {}

        self.canv._pdfgen_page_count.setdefault(self.name, self.canv.getPageNumber())
        page = self.canv.getPageNumber() - self.canv._pdfgen_page_count[self.name] + 1
        formatted_description = self.description.format(page=page)
        p = Paragraph(formatted_description, getSampleStyleSheet()['Normal'])
        p.wrap(15 * cm, 1 * cm)
        p.drawOn(self.canv, 0 * cm, 0 * cm)


class TextField(Flowable):
    def __init__(self, name, width=100, height=20, value=None):
        self.name = name
        self.width = width
        self.height = height
        self.value = value

    def wrap(self, *args):
        return (self.width, self.height)

    def draw(self):
        self.canv.saveState()
        textFieldRelative(self.canv, self.name, 0, 0, self.width, self.height, value=self.value)
        self.canv.restoreState()


class BackgroundImage(Image):
    """
    A background image (digital picture). See base class Image.

    The background image can be aligned via the hAlign parameter - accepted
    values are 'CENTER', 'LEFT' or 'RIGHT' with 'CENTER' being the default and
    vertically - accepted values are 'CENTER', 'TOP' or 'BOTTOM' with 'CENTER'
    being the default.
    """
    def __init__(self, filename, width=None, height=None, kind='absolute',
                 mask='auto', lazy=1, hAlign='CENTER', vAlign='CENTER'):

        try:
            super(BackgroundImage, self).__init__(
                filename=filename,
                width=width,
                height=height,
                kind=kind,
                mask=mask,
                lazy=lazy,
                hAlign=hAlign)
        except TypeError:
            # old style calling of parent
            # this is still used by reportlab
            Image.__init__(
                self,
                filename=filename,
                width=width,
                height=height,
                kind=kind,
                mask=mask,
                lazy=lazy,
                hAlign=hAlign)

        self.vAlign = vAlign

    def draw(self, canvas, doc):
        lazy = self._lazy
        if lazy >= 2:
            self._lazy = 1

        #  nw   n   ne
        #   w   c    e
        #  sw   s   se
        anchor = ''

        if self.vAlign.upper() == 'TOP':
            anchor = 'n'
        elif self.vAlign.upper() == 'BOTTOM':
            anchor = 's'

        if self.hAlign.upper() == 'LEFT':
            anchor += 'w'
        elif self.hAlign.upper() == 'RIGHT':
            anchor += 'e'

        if anchor == '':
            anchor = 'c'

        # calculate bounding box
        if anchor == 'sw':
            x = 0
            y = 0
        elif anchor == 's':
            x = (doc.pagesize[0] / 2) - (self.drawWidth / 2)
            y = 0
        elif anchor == 'se':
            x = doc.pagesize[0] - self.drawWidth
        elif anchor == 'nw':
            x = 0
            y = doc.pagesize[1] - self.drawHeight
        elif anchor == 'n':
            x = (doc.pagesize[0] / 2) - (self.drawWidth / 2)
            y = doc.pagesize[1] - self.drawHeight
        elif anchor == 'ne':
            x = doc.pagesize[0] - self.drawWidth
            y = doc.pagesize[1] - self.drawHeight
        elif anchor == 'w':
            x = 0
            y = (doc.pagesize[1] / 2) - (self.drawHeight / 2)
        elif anchor == 'c':
            x = (doc.pagesize[0] / 2) - (self.drawHeight / 2)
            y = (doc.pagesize[1] / 2) - (self.drawHeight / 2)
        elif anchor == 's':
            x = doc.pagesize[0] - self.drawWidth
            y = (doc.pagesize[1] / 2) - (self.drawHeight / 2)
        else:
            x = getattr(self, '_offs_x', 0)
            y = getattr(self, '_offs_y', 0)

        canvas.drawImage(
            self._img or self.filename,
            x,
            y,
            self.drawWidth,
            self.drawHeight,
            mask=self._mask,
            anchor=anchor,
            preserveAspectRatio=True,
        )

        if lazy >= 2:
            self._img = self._file = None
            self._lazy = lazy
