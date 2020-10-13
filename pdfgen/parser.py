import logging
from io import BytesIO
from reportlab.lib import pagesizes, colors
from reportlab.lib.units import mm, toLength
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfform import resetPdfForm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, Spacer, Image, PageBreak
from reportlab.platypus.doctemplate import SimpleDocTemplate
from svglib.svglib import SvgRenderer

from pdfgen.flowables import TextField, BackgroundImage, PageMarker

import xml.dom.minidom

from django.conf import settings


from pdfgen.barcode import Barcode
from .compat import find, etree


logger = logging.getLogger(__name__)


CSS_DICT = {
    'padding-left': 'LEFTPADDING',
    'padding-right': 'RIGHTPADDING',
    'padding-top': 'TOPPADDING',
    'padding-bottom': 'BOTTOMPADDING',
    'border-left': 'LINEBEFORE',
    'border-right': 'LINEAFTER',
    'border-top': 'LINEABOVE',
    'border-bottom': 'LINEBELOW',
    'text-align': 'alignment',
    'font-family': 'fontName',
    'font-size': 'fontSize',
    'color': 'textColor',
    'left': TA_LEFT,
    'right': TA_RIGHT,
    'center': TA_CENTER,
    'justify': TA_JUSTIFY,
}


def _new_draw(self):
    self.canv.setLineWidth(0.2*mm)
    self.drawPara(self.debug)


def patch_reportlab():
    setattr(Paragraph, 'draw', _new_draw)


patch_reportlab()


def debug_print(text):
    if settings.DEBUG:
        logger.debug(text)


def split_ignore(haystack, needle, ignore_start=None, ignore_end=None):
    parts = []
    ignore_start = ignore_start or '<![CDATA['
    ignore_end = ignore_end or ']]>'
    haystack_len, needle_len, ignore_start_len, ignore_end_len = \
        len(haystack), len(needle), len(ignore_start), len(ignore_end)
    ignore = False
    i = 0
    pi = -1
    while i < haystack_len:
        unignored = False
        if ignore and i+ignore_end_len <= haystack_len and haystack[i:i+ignore_end_len] == ignore_end:
            ignore = False
            unignored = True
        if not ignore and i+needle_len <= haystack_len and haystack[i:i+needle_len] == needle:
            part = haystack[pi+1:i].replace(ignore_start, '').replace(ignore_end, '')
            i += needle_len-1
            pi = i
            parts.append(part)
        if not ignore and not unignored and i+ignore_start_len <= haystack_len and \
                haystack[i:i+ignore_start_len] == ignore_start:
            ignore = True
        i += 1
    parts.append(haystack[pi+1:].replace(ignore_start, '').replace(ignore_end, ''))
    return parts


def inner_xml(e):
    return etree.tostring(e).strip()[len(e.tag)+2:-len(e.tag)-3]


def content(e):
    return e.text + ''.join(etree.tostring(c) for c in e)


class XmlParser(object):
    document = None
    styles = None
    out_buffer = None
    style_stack = None
    barcode_library = ''
    fonts = {}
    #: the Django MEDIA_URL
    media_url = ''
    #: the Django STATIC_URL
    static_url = ''
    background = None
    footer_flowable = None
    footer_on_first_page = False

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.out_buffer = BytesIO()
        self.style_stack = []
        self.media_url = getattr(settings, 'MEDIA_URL', '')
        self.static_url = getattr(settings, 'STATIC_URL', '')

    def get_from_url(self, url):
        """
        For a given URL, return the matching path to the directory.

        Support MEDIA_URL and STATIC_URL
        """
        if self.static_url and url.startswith(self.static_url):
            url = url.replace(self.static_url, '', 1)
        elif self.media_url and url.startswith(self.media_url):
            url = url.replace(self.media_url, '', 1)

        return find(url)

    def set_background_image(self, canvas, doc):
        canvas.saveState()

        if self.background:
            self.background.draw(canvas, doc)

        # Header
        # header = Paragraph('This is a multi-line header.  It goes on every page.   ' * 5, self.styles['Normal'])
        # w, h = header.wrap(doc.width, doc.topMargin)
        # header.drawOn(canvas, doc.leftMargin, doc.height + doc.topMargin - h)

        canvas.restoreState()

    def handle_first_page(self, canvas, doc):
        self.set_background_image(canvas, doc)
        if self.footer_on_first_page:
            self.draw_footer(canvas, doc)

    def handle_later_pages(self, canvas, doc):
        self.set_background_image(canvas, doc)
        self.draw_footer(canvas, doc)

    def draw_footer(self, canvas, doc):
        print('-' * 80)
        print('Trying to draw footer...', repr(self.footer_flowable))

        if self.footer_flowable is None:
            return
        canvas.saveState()
        w, h = self.footer_flowable.wrap(doc.width, doc.bottomMargin)
        self.footer_flowable.drawOn(canvas, doc.leftMargin, doc.bottomMargin - h)
        canvas.restoreState()

    def merge_parts(self, parts):
        if self.document is not None:
            self.document.build(
                parts,
                onFirstPage=self.handle_first_page,
                onLaterPages=self.handle_later_pages
            )
            output_data = self.out_buffer.getvalue()
            self.out_buffer.close()

            return output_data
        else:
            return None

    def parse(self, buffer):
        resetPdfForm()  # work around for stupid global state in reportlab
        parts = self.parse_parts(buffer)
        return self.merge_parts(parts)

    def parse_parts(self, buffer):
        xdoc = etree.fromstring(buffer)
        return list(self.parse_element(xdoc))

    def parse_element(self, e):
        try:
            method = getattr(self, e.tag, self.parse_children)
            for i in method(e):
                if isinstance(i, BackgroundImage):
                    # save the background image, don't add it to render list
                    self.background = i
                    continue
                else:
                    yield i
        except TypeError:
            # some elements are not strings, like Comment
            pass

    def parse_children(self, e):
        for c in e:
            for i in self.parse_element(c):
                yield i

    PAGE_SIZES_MAPPING = {
        'A0': pagesizes.A0,
        'A1': pagesizes.A1,
        'A2': pagesizes.A2,
        'A3': pagesizes.A3,
        'A4': pagesizes.A4,
        'A5': pagesizes.A5,
        'A6': pagesizes.A6,

        'B0': pagesizes.B0,
        'B1': pagesizes.B1,
        'B2': pagesizes.B2,
        'B3': pagesizes.B3,
        'B4': pagesizes.B4,
        'B5': pagesizes.B5,
        'B6': pagesizes.B6,

        'LETTER': pagesizes.LETTER,
        'LEGAL': pagesizes.LEGAL,
        'ELEVENSEVENTEEN': pagesizes.ELEVENSEVENTEEN,
    }

    def doc(self, e):
        fmt = e.get('format', 'A4')
        raw_margins = e.get('margin', '2cm, 2cm, 2cm, 2cm')
        title = e.get('title')

        if ',' in fmt:
            w, h = (toLength(i.strip()) for i in fmt.split(','))
            fmt = (w, h)
        else:
            fmt = self.PAGE_SIZES_MAPPING.get(fmt.upper(), pagesizes.A4)

        top_margin, right_margin, bottom_margin, left_margin = (toLength(i.strip()) for i in raw_margins.split(','))

        def make_canvas(*args, **kwargs):
            canvas = Canvas(*args, **kwargs)
            canvas.setLineWidth(0.25)
            return canvas

        if self.document is None:
            self.document = SimpleDocTemplate(self.out_buffer,
                                              pagesize=fmt,
                                              title=title,
                                              topMargin=top_margin,
                                              leftMargin=left_margin,
                                              rightMargin=right_margin,
                                              bottomMargin=bottom_margin,
                                              canvasmaker=make_canvas)

        for i in self.parse_children(e):
            yield i

    def style(self, e):
        name = e.get('name')
        source_name = e.get('base', None)
        def_dict = dict(e.attrib)

        del def_dict['name']
        if 'base' in def_dict:
            del def_dict['base']

        new_dict = {}
        for k in def_dict.keys():
            v = def_dict[k]
            nk = CSS_DICT.get(k, k)
            # translate v
            v = CSS_DICT.get(v, v)
            if nk == 'fontSize' or nk == 'leading':
                v = toLength(v)
            elif nk == 'color':
                v = colors.HexColor(int('0x' + v[1:], 0))
            new_dict[nk] = v

        if 'leading' not in new_dict and 'fontSize' in new_dict:
            new_dict['leading'] = new_dict['fontSize'] * 1.5  # + 2.0

        if source_name is not None:
            source_dict = self.styles[source_name].__dict__.copy()
            source_dict.update(new_dict)
            new_dict = source_dict

        new_dict.update({'name': name})

        if name in self.styles:
            self.styles[name].__dict__.update(new_dict)
        else:
            self.styles.add(ParagraphStyle(**new_dict))

        # make this function an empty generator
        if False:
            yield  # noqa

    def font(self, e):
        name = e.get('name')
        path = e.get('src')
        self.import_pdf_font(path, name)

        if False:
            yield  # noqa

    def div(self, e):
        style = e.get('style', None)

        if style is not None:
            self.style_stack.append(self.styles[style])

        parts = list(self.parse_children(e))

        if style is not None:
            self.style_stack.pop()

        for i in parts:
            yield i

    def p(self, e):
        data = inner_xml(e)
        para = Paragraph(data, self.style_stack[-1] if len(self.style_stack) > 0 else self.styles['Normal'])
        yield para

    def textfield(self, e):  # noqa
        name = e.get('name')
        value = e.get('value')
        width = int(e.get('width', "100"))
        height = int(e.get('height', "20"))
        yield TextField(name, width, height, value)

    def tstyle(self, e):  # noqa
        area = e.get('area', '0:-1')

        top_left, bottom_right = (list(int(q) for q in p.split(',')) for p in area.split(':'))
        top = top_left[0]
        left = top_left[-1]
        bottom = bottom_right[0]
        right = bottom_right[-1]
        cells = [(top, left), (bottom, right)]

        tstyle_dict = dict(e.attrib)
        if 'area' in tstyle_dict:
            del tstyle_dict['area']

        if 'border' in tstyle_dict:
            border = tstyle_dict['border']
            tstyle_dict.update({'border-left': border,
                                'border-right': border,
                                'border-top': border,
                                'border-bottom': border
                                })
            del tstyle_dict['border']

        if 'padding' in tstyle_dict:
            padding = tstyle_dict['padding']
            tstyle_dict.update({'padding-left': padding,
                                'padding-right': padding,
                                'padding-top': padding,
                                'padding-bottom': padding
                                })
            del tstyle_dict['padding']

        for key in tstyle_dict.keys():
            value = tstyle_dict[key]
            desc = CSS_DICT.get(key, key.upper())
            params = value.split(',')

            for i in range(len(params)):
                param = params[i].strip()
                if param[0] == '#':
                    params[i] = colors.HexColor(int('0x' + param[1:], 0))
                else:
                    try:
                        floatval = toLength(param)
                        params[i] = floatval
                    except ValueError:
                        params[i] = param.upper()

            yield [desc] + cells + params

    def tr(self, e):
        for c in e:
            if c.tag == 'td':
                yield list(self.parse_children(c)) if len(c) else None

    def table(self, e):
        cols = [toLength(i.strip()) for i in e.get('cols').split(',')]
        align = e.get('align', 'left').upper()
        repeatrows = int(e.get('repeatrows', '0'))

        tstyles = []
        rows = []

        for c in e:
            if c.tag == 'tstyle':
                tstyles += list(self.tstyle(c))
            else:
                rows.append(list(self.parse_element(c)))

        table_obj = Table(rows, cols, hAlign=align, style=tstyles, repeatRows=repeatrows)
        yield table_obj

    def pagebreak(self, e):  # noqa
        yield PageBreak()

    def pagemarker(self, e):  # noqa
        yield PageMarker(name=e.get('name'), description=content(e))

    def footer(self, e):
        self.footer_flowable = list(self.parse_children(e))[0]
        self.footer_on_first_page = e.get('firstpage', 'false').lower() in ('true', '1')
        if False:
            yield  # noqa

    def spacer(self, e):  # noqa
        width = toLength(e.get('width', '1pt'))
        height = toLength(e.get('height'))
        yield Spacer(width, height)

    def vector(self, e):
        scale = float(e.get('scale', '1.0'))
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        path = e.get('src')
        search = e.get('search', None)
        replace = e.get('replace', None)

        fh = open(self.get_from_url(path), 'rb')
        data = fh.read()
        fh.close()

        if search is not None:
            data = data.replace(search, replace)

        svg = xml.dom.minidom.parseString(data).documentElement

        svg_renderer = SvgRenderer('')
        svg_obj = svg_renderer.render(svg)

        svg_obj.scale(scale, scale)
        svg_obj.asDrawing(width, height)

        yield svg_obj

    def img(self, e):
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        path = e.get('src')
        align = e.get('align', 'left').upper()
        background = e.get('background', 'False') == 'True'
        v_align = e.get('vertical-align', 'BOTTOM').upper()

        if background:
            img_obj = BackgroundImage(
                filename=self.get_from_url(path),
                width=width,
                height=height,
                hAlign=align,
                vAlign=v_align)
        else:
            img_obj = Image(filename=self.get_from_url(path), width=width, height=height)
            img_obj.hAlign = align

        yield img_obj

    def barcode(self, e):
        scale = float(e.get('scale', '1.0'))
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        value = e.get('value')
        align = e.get('align', 'left').upper()
        barcode_type = e.get('type', 'datamatrix')

        barcode_obj = Barcode(library=self.barcode_library,
                              width=width,
                              height=height,
                              data=value,
                              scale=scale,
                              type=barcode_type,
                              align=align.lower())

        barcode_obj.hAlign = align

        yield barcode_obj

    def import_pdf_font(self, base_name, face_name):
        if self.fonts.get(face_name, None) is None:
            afm = find(base_name + '.afm')
            pfb = find(base_name + '.pfb')
            ttf = find(base_name + '.ttf')

            if afm:
                try:
                    face = pdfmetrics.EmbeddedType1Face(afm, pfb)

                    pdfmetrics.registerTypeFace(face)
                    font = pdfmetrics.Font(face_name, face_name, 'WinAnsiEncoding')
                    pdfmetrics.registerFont(font)
                except:  # noqa
                    pass
            elif ttf:
                pdfmetrics.registerFont(TTFont(face_name, ttf))
            else:
                raise Exception('Cannot find font %s (tried .afm, .pfb and .ttf)' % base_name)
        else:
            self.fonts[face_name] = True
