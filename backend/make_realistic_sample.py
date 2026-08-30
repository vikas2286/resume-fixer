"""Generate a REALISTIC resume PDF that reproduces the reported data bugs:

  1. a double-drawn bullet (design tools often paint text twice) -> dupes
  2. PROJECTS with two titled sub-projects and NO dates           -> merge
  3. EDUCATION where "CGPA: x.xx" and the date share one line     -> glue

Usage: python make_realistic_sample.py [out_path]
"""
import sys

import fitz

BULLET = "\u2022 "


def main(out_path="realistic_resume.pdf"):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    def line(x, y, text, size=10.5, font="helv", color=(0, 0, 0)):
        # Design tools often paint each glyph run twice (fill pass + overlay
        # pass) ~0.4pt apart. Duplicate both so the parser MUST dedupe them,
        # otherwise every bullet would appear twice in the output PDF.
        page.insert_text((x, y), text, fontname=font, fontsize=size, color=color)
        page.insert_text((x, y + 0.4), text, fontname=font, fontsize=size,
                         color=color)
        return y + size + 6

    y = 50
    y = line(60, y, "ARJUN MEHTA", 20, "hebo")
    y = line(60, y, "arjun.mehta@email.com | +91 98765 43210 | linkedin.com/in/arjunmehta", 9.5)
    y += 8

    y = line(60, y, "EXPERIENCE", 12, "hebo")
    y = line(60, y, "Software Engineer, TechCorp    Jul 2024 - Present", 11, "hebo")
    y = line(72, y, BULLET + "Built multi-agent AI workflow automation platform serving 50k users")
    y = line(72, y, BULLET + "Implemented agent orchestration with LangGraph cutting latency by 40%")
    y = line(72, y, BULLET + "Designed RAG pipelines reducing hallucination rate to 2%")
    y = line(60, y, "Software Intern, StartupHub    Jan 2024 - Jun 2024", 11)
    y = line(72, y, BULLET + "Shipped billing dashboard used by 200+ internal teams")
    y = line(72, y, BULLET + "Automated invoice reconciliation saving 15 hours weekly")
    y += 8

    y = line(60, y, "PROJECTS", 12, "hebo")
    y = line(60, y, "AgentFlow", 11, "hebo")
    y = line(72, y, BULLET + "Built multi-agent AI workflow orchestration tool with drag-and-drop UI")
    y = line(72, y, BULLET + "Integrated 12+ LLM providers behind one unified interface")
    y = line(60, y, "ResumeRanker", 11, "hebo")
    y = line(72, y, BULLET + "Implemented agent-based resume scoring engine with ATS simulation")
    y = line(72, y, BULLET + "Deployed on AWS Lambda handling 1k scans per day")
    y += 8

    y = line(60, y, "EDUCATION", 12, "hebo")
    y = line(60, y, "B.Tech, Computer Science - National Institute of Technology", 11)
    y = line(60, y, "CGPA: 7.82 \u00b7 1 Sep 2023 \u2013 Sep 2027", 10.5)
    y += 8

    y = line(60, y, "SKILLS", 12, "hebo")
    y = line(60, y, "Python, TypeScript, React, FastAPI, Docker, AWS, LangChain, PostgreSQL")

    doc.save(out_path)
    print("saved %s" % out_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "realistic_resume.pdf")
