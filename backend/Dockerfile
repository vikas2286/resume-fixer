# Resume Fixer backend - Linux deployment image (Render / Railway / Fly).
# WeasyPrint on Linux needs Pango/Cairo system libraries; the app auto-falls
# back to pure-Python xhtml2pdf if WeasyPrint can't import (template_engine),
# so even a bare install still produces PDFs identical to local Windows output.
FROM python:3.11-slim

# System deps for WeasyPrint (pango/cairo/gdk-pixbuf) + fonts + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libcairo2 libffi-dev shared-mime-info curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application (templates + fonts ship with it)
COPY . .

# Never run with a committed .env - env comes from the host
RUN rm -f .env

ENV PYTHONUNBUFFERED=1

EXPOSE $PORT

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
