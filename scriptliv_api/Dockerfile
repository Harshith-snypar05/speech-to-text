FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SCRIPTLIV_ENV=production
WORKDIR /srv
COPY requirements.txt .
# pytest and mongomock are test-only; keep the image to runtime packages
RUN grep -vE '^(pytest|mongomock)' requirements.txt > runtime.txt && pip install --no-cache-dir -r runtime.txt
COPY app ./app
RUN useradd --system --uid 10001 scriptliv
USER scriptliv
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8790/healthz', timeout=4).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790", "--proxy-headers", "--forwarded-allow-ips", "*"]
