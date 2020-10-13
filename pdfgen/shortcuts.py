import io

from reportlab.platypus.flowables import PageBreak

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import translation

from pdfgen.parser import XmlParser, find
from itertools import repeat

try:
    from PyPDF2 import PdfFileMerger, PdfFileReader  # noqa
    USE_PYPDF2 = True
except ImportError:
    # Use old version as fallback
    USE_PYPDF2 = False


def get_parser(template_name):
    """
    Get the correct parser based on the file extension
    """

    parser = XmlParser()
    # set the barcode file
    parser.barcode_library = find('common/pdf_img/barcode.ps')
    return parser


def render_to_pdf_data(template_name, context, context_instance=None):
    """
    Parse the template into binary PDF data
    """
    input = render_to_string(template_name, context, context_instance)
    parser = get_parser(template_name)

    return parser.parse(input)


def render_to_pdf_download(template_name, context, context_instance=None, filename=None):
    """
    Parse the template into a download
    """
    response = HttpResponse(content_type='application/pdf')
    if filename:
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

    xml = render_to_string(template_name, context)
    parser = get_parser(template_name)
    output = parser.parse(xml)

    response.write(output)

    return response


def multiple_templates_to_pdf_download(template_names, context, context_instance=None, filename=None):
    """
    Render multiple templates with the same context into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        zip(repeat(context, len(template_names)), template_names),
        context_instance=context_instance,
        filename=filename
    )


def multiple_contexts_to_pdf_download(template_name, contexts, context_instance=None, filename=None):
    """
    Render a single template with multiple contexts into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        zip(contexts, repeat(template_name, len(contexts))),
        context_instance=context_instance,
        filename=filename
    )


def multiple_contexts_to_pdf_data(template_name, contexts, context_instance=None, filename=None):
    return multiple_contexts_and_templates_to_pdf_data(
        zip(contexts, repeat(template_name, len(contexts))),
        context_instance=context_instance,
        filename=filename
    )


def multiple_contexts_and_templates_to_pdf_data(contexts_templates, context_instance=None, filename=None):
    if USE_PYPDF2:
        merger = PdfFileMerger()
    else:
        all_parts = []

    old_lang = translation.get_language()

    for context, template_name in contexts_templates:
        parser = get_parser(template_name)
        if 'language' in context:
            translation.activate(context['language'])
        xml = render_to_string(template_name, context, context_instance)
        if USE_PYPDF2:
            outstream = io.BytesIO()
            outstream.write(parser.parse(xml))
            reader = PdfFileReader(outstream)
            merger.append(reader)
        else:
            parts = parser.parse_parts(xml)
            all_parts += parts
            all_parts.append(PageBreak())

    translation.activate(old_lang)

    if USE_PYPDF2:
        output = io.BytesIO()
        merger.write(output)
        output = output.getvalue()
    else:
        output = parser.merge_parts(all_parts)

    return output


def multiple_contexts_and_templates_to_pdf_download(contexts_templates, context_instance=None, filename=None):
    """
    Render multiple templates with multiple contexts into a single download
    """
    response = HttpResponse()
    response['Content-Type'] = 'application/pdf'
    response['Content-Disposition'] = u'attachment; filename=%s' % (filename or u'document.pdf')

    output = multiple_contexts_and_templates_to_pdf_data(
                    contexts_templates=contexts_templates,
                    context_instance=context_instance,
                    filename=filename)

    response.write(output)
    return response
