FROM python:3.12-slim AS builder

WORKDIR /build
COPY packages/common/requirements.txt /build/common-requirements.txt
COPY services/worker/requirements.txt /build/worker-requirements.txt
RUN sed -i '/civicproof-common/d' /build/worker-requirements.txt && \
    pip install --no-cache-dir --prefix=/install \
    -r /build/common-requirements.txt \
    -r /build/worker-requirements.txt

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local

COPY packages/common/src/civicproof_common /app/civicproof_common
COPY services/worker/src /app/src

ENV PYTHONPATH=/app:/app/src
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "src.main"]
