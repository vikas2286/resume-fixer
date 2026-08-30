"""Generate 5 synthetic stress-test resumes the pipeline has never seen.
Deliberately different structures from Vikas/Kanish/Harsh."""
import os

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
BULLET = "\u2022"


def txt(page, x, y, s, size=10, bold=False):
    page.insert_text((x, y), s, fontname="hebo" if bold else "helv",
                     fontsize=size)
    return y + size + 5


# ------------------------------------------------------------------ 1. two-col
def make_twocol(path):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    LX, RX = 52, 356           # left main column / right sidebar
    y = txt(pg, 52, 46, "Ananya Krishnan", 17, bold=True)
    y = txt(pg, 52, y + 2, "Senior Backend Engineer", 11)
    y = txt(pg, 52, y + 2, "ananya.krishnan@mailbox.org | +91 98450 11223",
            9.5)
    sy = 50
    sy = txt(pg, RX, sy, "CONTACT", 11, bold=True)
    sy = txt(pg, RX, sy, "linkedin.com/in/ananya-krishnan", 9)
    sy = txt(pg, RX, sy, "github.com/ananya-krishnan", 9)
    sy = txt(pg, RX, sy, "ananya.dev/portfolio", 9)
    sy += 8
    sy = txt(pg, RX, sy, "TECHNICAL SKILLS", 11, bold=True)
    for s in ("Python, Go, Java, TypeScript",
              "Django, FastAPI, Spring Boot",
              "PostgreSQL, MongoDB, Redis",
              "Kafka, RabbitMQ, Celery",
              "AWS ECS, Terraform, Datadog",
              "Docker, Kubernetes, Helm"):
        sy = txt(pg, RX, sy, s, 9)
    sy += 8
    sy = txt(pg, RX, sy, "LANGUAGES", 11, bold=True)
    sy = txt(pg, RX, sy, "English (fluent), Hindi (native)", 9)
    sy = txt(pg, RX, sy, "German (conversational)", 9)
    sy += 8
    sy = txt(pg, RX, sy, "SPEAKING", 11, bold=True)
    sy = txt(pg, RX, sy, "PyCon India 2024 - speaker", 9)
    sy = txt(pg, RX, sy, "AWS Community Day - panelist", 9)
    my = 130
    my = txt(pg, LX, my, "EXPERIENCE", 12, bold=True)
    jobs = [
        ("Nimbus Payments - Senior Backend Engineer", [
            "Led the ledger service rewrite serving 4M daily transactions,",
            "cutting p99 latency from 340ms to 95ms.",
            "Designed an idempotent payout pipeline handling 20k TPS at peak,",
            "eliminating duplicate settlements (previously ~15/week).",
            "Introduced contract tests across 9 services, reducing",
            "cross-team integration incidents by 60%.",
        ]),
        ("Cobalt Labs - Backend Engineer", [
            "Built multi-tenant billing with usage-based metering for 300+",
            "B2B customers; invoicing errors dropped from 2.1% to 0.1%.",
            "Sharded the events store, sustaining 8x traffic growth with",
            "zero downtime migrations.",
        ]),
        ("Fieldstone Analytics - Junior Developer", [
            "Automated ETL for 40+ client data feeds in Airflow, saving",
            "~25 analyst hours per week.",
        ]),
    ]
    for title, bullets in jobs:
        my = txt(pg, LX, my, title, 10.5, bold=True)
        for b in bullets:
            my = txt(pg, LX + 14, my, BULLET + " " + b, 9.5)
        my += 4
    my += 2
    my = txt(pg, LX, my, "EDUCATION", 12, bold=True)
    my = txt(pg, LX, my, "B.Tech Computer Science, RV College of Engineering",
             9.5)
    my = txt(pg, LX, my, "2013 - 2017 | CGPA 9.1", 9.5)
    doc.save(path)
    doc.close()


# ------------------------------------------------------------------ 2. photo
def make_photo(path):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = txt(pg, 52, 48, "Rohan Deshpande", 16, bold=True)
    y = txt(pg, 52, y + 2, "Data Engineer | rohan.desh@datalane.io | "
                            "+91 90040 55221", 9.5)
    y = txt(pg, 52, y + 2, "linkedin.com/in/rohan-desh | "
                            "github.com/rohandesh", 9.5)
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 140))
    pm.set_rect(pm.irect, (90, 110, 160))
    pg.insert_image(fitz.Rect(452, 40, 566, 168), pixmap=pm)
    y += 8
    y = txt(pg, 52, y, "SUMMARY", 12, bold=True)
    y = txt(pg, 52, y, "Data engineer with 4 years building batch and"
                       " streaming pipelines on GCP; cut warehouse spend", 10)
    y = txt(pg, 52, y, "by 38% while doubling pipeline reliability.", 10)
    y += 4
    y = txt(pg, 52, y, "EXPERIENCE", 12, bold=True)
    y = txt(pg, 52, y, "DataLane Systems - Data Engineer (2021 - Present)",
            10.5, bold=True)
    for b in ("Migrated 60+ nightly jobs to Dataflow, shrinking window from"
              " 5h to 40min.",
              "Built CDC ingestion from Postgres to BigQuery for 12 product"
              " teams.",
              "Added data contracts with Soda checks, catching 95% of schema"
              " breaks pre-prod."):
        y = txt(pg, 66, y, BULLET + " " + b, 9.5)
    y = txt(pg, 52, y, "Bluepeak Retail - Junior Data Engineer"
                       " (2019 - 2021)", 10.5, bold=True)
    for b in ("Automated daily sales loads; eliminated 3 manual spreadsheet"
              " handoffs.",
              "Modeled the returns mart used by finance for monthly close."):
        y = txt(pg, 66, y, BULLET + " " + b, 9.5)
    y += 4
    y = txt(pg, 52, y, "SKILLS", 12, bold=True)
    y = txt(pg, 52, y, "Python, SQL, Airflow, dbt, Spark, BigQuery,"
                       " Dataflow, GCP, Terraform", 9.5)
    y += 4
    y = txt(pg, 52, y, "EDUCATION", 12, bold=True)
    y = txt(pg, 52, y, "B.E. Information Technology, Pune Institute of"
                       " Computer Technology", 9.5)
    doc.save(path)
    doc.close()


# ------------------------------------------------------- 3. nonstandard names
def make_headers(path):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = txt(pg, 52, 46, "Meera Iyer", 16, bold=True)
    y = txt(pg, 52, y + 2, "meera.iyer@devmail.com | +91 99870 41230", 9.5)
    y = txt(pg, 52, y + 2, "github.com/meera-iyer | "
                            "linkedin.com/in/meera-iyer", 9.5)
    y += 6
    y = txt(pg, 52, y, "CAREER OBJECTIVE", 12, bold=True)
    y = txt(pg, 52, y, "Frontend engineer seeking to build accessible,"
                       " fast product interfaces; shipped design-system", 10)
    y = txt(pg, 52, y, "components used by 40+ engineers across 6 teams.", 10)
    y += 4
    y = txt(pg, 52, y, "TECH STACK", 12, bold=True)
    y = txt(pg, 52, y, "React, TypeScript, Redux, Tailwind, Vite, Jest,"
                       " Playwright, Node.js", 9.5)
    y += 4
    y = txt(pg, 52, y, "WORK HISTORY", 12, bold=True)
    y = txt(pg, 52, y, "Sproutly Health - Frontend Engineer"
                       " (2022 - Present)", 10.5, bold=True)
    for b in ("Rebuilt the patient intake flow; completion rate rose from"
              " 61% to 89%.",
              "Cut bundle size 45% via route-level code splitting and"
              " dependency audit.",
              "Drove WCAG 2.1 AA audit remediation - 87 open issues closed"
              " in one quarter."):
        y = txt(pg, 66, y, BULLET + " " + b, 9.5)
    y = txt(pg, 52, y, "Vistar Media - Associate Frontend Engineer"
                       " (2020 - 2022)", 10.5, bold=True)
    for b in ("Shipped the campaign builder used to launch 3,000+ monthly"
              " campaigns.",
              "Introduced Playwright e2e suites, cutting release smoke time"
              " from 2h to 12min."):
        y = txt(pg, 66, y, BULLET + " " + b, 9.5)
    y += 4
    y = txt(pg, 52, y, "ACADEMIC BACKGROUND", 12, bold=True)
    y = txt(pg, 52, y, "M.Sc Computer Science, Anna University - 2020", 9.5)
    y += 4
    y = txt(pg, 52, y, "KEY PROJECTS", 12, bold=True)
    y = txt(pg, 52, y, "A11y Lens - browser extension auditing color"
                       " contrast (400+ users)", 9.5)
    y = txt(pg, 66, y, BULLET + " Built with React + Vite; scored 100 on"
                                " Lighthouse a11y.", 9.5)
    doc.save(path)
    doc.close()


# ------------------------------------------------------------------ 4. 2-page
def make_twopage(path):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)

    def job(y, title, bullets):
        y = txt(pg, 52, y, title, 10.5, bold=True)
        for b in bullets:
            y = txt(pg, 66, y, BULLET + " " + b, 9.5)
        return y + 3

    y = txt(pg, 52, 46, "Vikram Raghavan", 16, bold=True)
    y = txt(pg, 52, y + 2, "vikram.raghavan@engmail.com | +91 98201 33440 |"
                            " linkedin.com/in/vikram-raghavan", 9.5)
    y += 6
    y = txt(pg, 52, y, "EXPERIENCE", 12, bold=True)
    y = job(y, "Meridian Cloud - Principal Engineer (2018 - Present)", [
        "Own the multi-region control plane for a platform running 12,000+"
        " compute nodes across 3 continents (99.99% availability SLA).",
        "Led the service-mesh migration for 80 microservices; tail latency"
        " fell 42% and cross-region failover went from 45min to 90s.",
        "Authored the capacity-planning model that deferred a $2.1M hardware"
        " purchase by 18 months while absorbing 2.4x traffic growth.",
        "Mentored 11 engineers; 4 promoted to senior within two years.",
        "Drove the incident-review program: repeat incidents fell 70%"
        " across two quarters (MTTR 38min to 11min).",
        "Cut the CI bill 55% ($380k/yr) by moving 70% of builds to a"
        " self-hosted fleet with elastic burst capacity.",
        "Designed the config-service replacing 40+ static YAML repos,"
        " eliminating an entire class of deploy rollbacks.",
        "Ran the on-call redesign (follow-the-sun), cutting pages/engineer"
        " from 14 to 3 per month with no SLA regression.",
        "Published the internal 'platform golden path' adopted by 23 teams.",
    ])
    y = job(y, "Halcyon Systems - Senior Engineer (2014 - 2018)", [
        "Built the telemetry ingestion lake (2TB/day) on Kafka + Spark;"
        " replaced 6 bespoke pipelines.",
        "Led Kubernetes adoption from zero to production for the flagship"
        " product (40 services).",
        "Introduced schema-registry governance, ending a year of consumer"
        " breakages.",
        "Automated DR drills; recovery time validated at 17 minutes against"
        " a 30-minute objective.",
        "Reduced the fleet's memory footprint 33% via GC tuning and"
        " container right-sizing.",
    ])
    y = job(y, "Cirrus Apps - Software Engineer (2011 - 2014)", [
        "Shipped the mobile sync engine powering 3 flagship apps.",
        "Cut cold-start time 61% through lazy init and asset trimming.",
    ])
    y += 2
    y = txt(pg, 52, y, "PATENTS & PUBLICATIONS", 12, bold=True)
    y = txt(pg, 66, y, BULLET + " US Patent 11,204,556 - adaptive regional"
                                " request routing (2021)", 9.5)
    y = txt(pg, 66, y, BULLET + " 'Failure Modes at Scale', ACM Queue"
                                " contributor (2022)", 9.5)
    pg2 = doc.new_page(width=612, height=792)
    y2 = txt(pg2, 52, 52, "OPEN SOURCE & COMMUNITY", 12, bold=True)
    for b in ("Maintainer, 'routezen' - traffic-shaping library, 1.8k GitHub"
              " stars, 300k monthly downloads.",
              "Organizer, Distributed Systems Meetup (Bengaluru) - 2,400"
              " members, monthly talks.",
              "Core contributor to 'kvbench'; benchmark suite cited by 3"
              " database papers."):
        y2 = txt(pg2, 66, y2, BULLET + " " + b, 9.5)
    y2 += 4
    y2 = txt(pg2, 52, y2, "PROJECTS", 12, bold=True)
    y2 = txt(pg2, 52, y2, "Chaos Lantern - fault-injection harness used by"
                          " 5 companies", 10.5, bold=True)
    for b in ("Simulates zone loss, clock skew, and partition storms against"
              " staging clusters.",
              "Adopted as a release gate by the payments group after catching"
              " a quorum bug pre-launch."):
        y2 = txt(pg2, 66, y2, BULLET + " " + b, 9.5)
    y2 = txt(pg2, 52, y2, "Tracepaint - distributed trace visualizer", 10.5,
             bold=True)
    for b in ("Renders 1M-span traces interactively via WebGL sampling.",
              "Integrated with Jaeger and Tempo backends."):
        y2 = txt(pg2, 66, y2, BULLET + " " + b, 9.5)
    y2 += 4
    y2 = txt(pg2, 52, y2, "EDUCATION", 12, bold=True)
    y2 = txt(pg2, 52, y2, "M.Tech Computer Science, IIT Madras - 2011", 9.5)
    y2 = txt(pg2, 52, y2, "B.E. Computer Science, College of Engineering"
                          " Guindy - 2009", 9.5)
    y2 += 4
    y2 = txt(pg2, 52, y2, "CERTIFICATIONS", 12, bold=True)
    y2 = txt(pg2, 66, y2, BULLET + " AWS Solutions Architect - Professional"
                                   " (2023)", 9.5)
    y2 = txt(pg2, 66, y2, BULLET + " CKA - Certified Kubernetes Administrator"
                                   " (2022)", 9.5)
    doc.save(path)
    doc.close()


# ------------------------------------------------------------------ 5. sparse
def make_fresher(path):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = txt(pg, 52, 48, "Tara Menon", 15, bold=True)
    y = txt(pg, 52, y + 2, "tara.menon21@unimail.edu | +91 99010 77452", 9.5)
    y += 8
    y = txt(pg, 52, y, "EDUCATION", 12, bold=True)
    y = txt(pg, 52, y, "B.Sc Computer Science, St. Xavier's College - 2026"
                       " (expected)", 9.5)
    y += 6
    y = txt(pg, 52, y, "SKILLS", 12, bold=True)
    y = txt(pg, 52, y, "Python, HTML, CSS, JavaScript", 9.5)
    y += 6
    y = txt(pg, 52, y, "PROJECT", 12, bold=True)
    y = txt(pg, 52, y, "Campus Canteen Menu Site", 10.5, bold=True)
    y = txt(pg, 66, y, BULLET + " Static website listing the daily mess"
                                " menu.", 9.5)
    y = txt(pg, 66, y, BULLET + " Deployed on GitHub Pages.", 9.5)
    doc.save(path)
    doc.close()


def _main():
    outs = {
        "stress_twocol.pdf": make_twocol,
        "stress_photo.pdf": make_photo,
        "stress_headers.pdf": make_headers,
        "stress_twopage.pdf": make_twopage,
        "stress_fresher.pdf": make_fresher,
    }
    for name, fn in outs.items():
        p = os.path.join(HERE, name)
        fn(p)
        d = fitz.open(p)
        print("generated %-22s pages=%d" % (name, len(d)))
        d.close()


if __name__ == "__main__":
    _main()


if __name__ == "__main__":
    _main()
