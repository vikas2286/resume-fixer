"""Generate the test-fixture resume that reproduces the reported failure modes:

  * "ABOUT ME" used instead of "Summary"
  * a misspelled "EDUACTION" header
  * a letter-spaced "S K I L L S" header
  * "PROJECTS" inside a bold boxed header
  * standard PDF bullet characters for most list items
  * one marker-free INDERTED list (office-style) to exercise indent detection
  * a novel "HOBBIES" header with no known category (fallback path)

Usage: python make_harsh_sample.py [out_path]
"""
import sys

import fitz

BULLET = "\u2022"


def make(out_path="harsh_resume.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    x_left = 52
    x_title = 52
    x_bullet = 70
    x_indent = 96

    def txt(x, y, s, size=10.5, font="helv", bol=False):
        page.insert_text((x, y), s, fontname="hebo" if bol else "helv",
                         fontsize=size)
        return y + (size + 6)

    y = 42
    y = txt(x_left, y, "Harsh Sharma", 17, bol=True)
    y = txt(x_left, y, "harsh@email.com | +91 98765 12345", 9.5)

    # ABOUT ME (letter-spaced -> tests the squeezed matcher)
    y += 6
    y = txt(x_left, y, "A B O U T M E", 12, bol=True)

    # summary
    summary = ("I am a final-year Computer Science student focused on building "
                "production AI tools and backend systems. Interning at a fintech "
                "and shipping two open-source projects used by 200+ developers.")
    y = txt(x_left, y, summary, 10.5)

    # EDUACTION (typo)
    y += 6
    y = txt(x_left, y, "EDUACTION", 12, bol=True)
    y = txt(x_left, y, "B.Tech, Computer Science - NIT Delhi", 10.5, bol=False)
    y = txt(x_left, y, "Sep 2022 - May 2026", 10.5)
    y = txt(x_left, y, "CGPA: 8.9", 10.5)

    # S K I L L S (letter-spaced)
    y += 6
    y = txt(x_left, y, "S K I L L S", 12, bol=True)
    y = txt(x_left, y, "Languages: Python, JavaScript, TypeScript", 10.5)
    y = txt(x_left, y, "Frameworks: React, FastAPI, Node.js, Docker", 10.5)

    # PRO JECTS boxed header
    y += 8
    y0 = y - 4
    page.insert_text((x_left, y), "PROJECTS", fontname="hebo", fontsize=12)
    tw = fitz.get_text_length("PROJECTS", fontname="hebo", fontsize=12)
    page.draw_rect(fitz.Rect(x_left - 4, y0, x_left + tw + 4, y + 2),
                   color=(0.3, 0.3, 0.3), width=1.2)
    y = y + 24

    # project 1 with marker bullets
    y = txt(x_left, y, "AI Resume Parser", 11, bol=True)
    y = txt(x_bullet, y, "\u2022 Built a resume parser using PyMuPDF and FastAPI")
    y = txt(x_bullet, y, "\u2022 Integrated Gemini for bullet rewriting and JD matching")
    y = txt(x_bullet, y, "\u2022 Shipped as an open-source tool with 500+ stars")

    # project 2 with marker-free indented bullets
    y += 4
    y = txt(x_left, y, "Movie Recommender System", 11, bol=True)
    y = txt(x_indent, y, "Designed a hybrid graph + vector recommender over Neo4j")
    y = txt(x_indent, y, "Deployed on AWS ECS handling 1k requests per day")

    # HOBBIES (unknown -> fallback labeled section)
    y += 8
    y = txt(x_left, y, "HOBBIES", 12, bol=True)
    y = txt(x_bullet, y, "\u2022 Chess, running, reading tech blogs")

    doc.save(out_path)
    print("saved %s" % out_path)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "harsh_resume.pdf")