from xhtml2pdf import pisa
from flask import render_template
from io import BytesIO


def generate_invoice_pdf(order):
    html = render_template('user/invoice.html', order=order)

    pdf_file = BytesIO()

    pisa_status = pisa.CreatePDF(html, dest=pdf_file)

    if pisa_status.err:
        return None

    pdf_file.seek(0)
    return pdf_file