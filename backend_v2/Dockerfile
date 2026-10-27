# Build from the REPO ROOT (it needs ai-engine/ai_engine.py):
#     docker build -f backend_v2/Dockerfile -t verify-backend .
#
# No torch, no sentence-transformers, no Chromium -> small image, fits in 512 MB.

FROM python:3.12-slim

WORKDIR /app

COPY backend_v2/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 verify

# Single source of truth for the two modules we reuse (never copied into backend_v2/)
COPY ai-engine/ai_engine.py ./ai_engine.py
COPY retrieval_demo_lite/search_retrieval_lite.py ./search_retrieval_lite.py
COPY backend_v2/app ./app

EXPOSE 8000
USER verify
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health',timeout=2)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-proxy-headers --no-access-log"]
