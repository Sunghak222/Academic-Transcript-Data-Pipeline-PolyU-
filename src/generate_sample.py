from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

input_txt = "./data/sample_transcript.txt"
output_pdf = "./data/sample_transcript.pdf"

c = canvas.Canvas(output_pdf, pagesize=A4)
width, height = A4

y = height - 40

with open(input_txt, "r", encoding="utf-8") as f:
    for line in f:
        if y < 40:
            c.showPage()
            y = height - 40
        c.drawString(40, y, line.rstrip())
        y -= 14

c.save()

print("Generated:", output_pdf)