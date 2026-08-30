"""Generate a deliberately MESSY sample resume PDF (multi-column, tables,
weird fonts, inconsistent sizes, passive voice, no metrics) for testing.

Usage: python make_sample_resume.py [out_path]
"""
import sys

import fitz


def main(out_path="messy_resume.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # --- header -----------------------------------------------------------
    page.insert_text((50, 40), "JOHN SMITH", fontname="Times-Bold", fontsize=20)
    page.insert_text((50, 58), "hard worker seeking growth oppurtunity",
                     fontname="Courier", fontsize=9)
    page.insert_text((50, 74), "john.smith@email.com | 555-234-8890",
                     fontname="Helvetica", fontsize=8)

    # --- two-column body ---------------------------------------------------
    left = [
        ("EXPERIENCE", "Helvetica-Bold", 13),
        ("Software Developer, Acme Corp 2019 - Present", "Times-Roman", 11),
        ("- was responsible for maintaining the backend systems",
         "Times-Roman", 10),
        ("- helped with the migration of old code to new framework",
         "Courier", 12),
        ("- duties included writing reports and attending meetings",
         "Times-Roman", 10),
        ("Junior Dev, StartupXYZ 2017 - 2019", "Times-Roman", 11),
        ("- tasked with fixing bugs reported by the QA team",
         "Times-Roman", 10),
        ("- was involved in database cleanup activities", "Times-Roman", 14),
    ]
    y = 110
    for text, font, size in left:
        page.insert_text((50, y), text, fontname=font, fontsize=size)
        y += size + 8

    right = [
        ("SKILLZ", "Helvetica-Bold", 13),
        ("Python, Java, SQL, HTML, CSS, JS, Git, Docker, AWS, Excel, "
         "Communication, Leadership", "Times-Roman", 9),
        ("EDUCATION", "Helvetica-Bold", 13),
        ("BSc Computer Science, State University, 2017", "Times-Roman", 11),
                ("I am a detail oriented self-starter and team player who thinks "
         "outside the box and is passionate about excellence.",
         "Times-Roman", 10),
    ]
    y = 110
    for text, font, size in right:
        page.insert_text((360, y), text, fontname="helv" if font == "Helvetica-Bold" else "tiro", fontsize=size)
        y += size + 8

    doc.save(out_path)
    print("saved %s" % out_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "messy_resume.pdf")
