"""Create a view derivative; never modify the PDF used for extraction."""
import io
import os
from pathlib import Path
import tempfile
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth


def watermarked_pdf_bytes(source, document_id, version_number, identity=None):
    reader=PdfReader(source)
    writer=PdfWriter()
    for number,page in enumerate(reader.pages,1):
        page.transfer_rotation_to_content()
        width=float(page.mediabox.width);height=float(page.mediabox.height)
        overlay=io.BytesIO();canvas=Canvas(overlay,pagesize=(width,height),invariant=1)
        canvas.saveState();canvas.setFillAlpha(0.18);canvas.setFillColorRGB(0.15,0.25,0.4)
        canvas.translate(width/2,height/2);canvas.rotate(35)
        label=identity or "OHAYO - HOC LIEU BAO VE"
        font_size=min(34,max(10,width/18),width*0.9/max(stringWidth(label,"Helvetica-Bold",1),1))
        canvas.setFont("Helvetica-Bold",font_size)
        canvas.drawCentredString(0,0,label);canvas.restoreState()
        canvas.setFillColorRGB(0.35,0.4,0.5);canvas.setFont("Helvetica",max(5,min(8,width/70)))
        canvas.drawCentredString(width/2,12,f"{identity or 'OHAYO'} | {document_id} | v{version_number} | PDF {number}")
        canvas.save()
        page.merge_page(PdfReader(overlay).pages[0])
        writer.add_page(page)
    writer.add_metadata({"/Producer":"OHAYO protected view","/Subject":str(document_id)})
    result=io.BytesIO()
    writer.write(result)
    return result.getvalue()


def create_watermarked_pdf(source, destination, document_id, version_number):
    destination=Path(destination)
    if Path(source).resolve()==destination.resolve():
        raise ValueError("Watermark cannot replace original.")
    content=watermarked_pdf_bytes(source,document_id,version_number)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,suffix=".tmp",delete=False) as stream:
            temporary=stream.name;stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,destination)
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)
