import sys
from .watermark import create_watermarked_pdf

if __name__=="__main__":
    source,destination,document_id,version=sys.argv[1:]
    create_watermarked_pdf(source,destination,document_id,int(version))
