FROM python:3.12-slim AS builder

WORKDIR /build
COPY packages/common/requirements.txt /build/common-requirements.txt
COPY services/api/requirements.txt /build/api-requirements.txt
RUN sed -i '/civicproof-common/d' /build/api-requirements.txt && \
    pip install --no-cache-dir --prefix=/install \
    -r /build/common-requirements.txt \
    -r /build/api-requirements.txt

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local

COPY packages/common/src/civicproof_common /app/civicproof_common
COPY services/api/src /app/src

ENV PYTHONPATH=/app:/app/src
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
