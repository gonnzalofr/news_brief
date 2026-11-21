# syntax=docker/dockerfile:1
FROM python:3.13-slim-trixie AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt \
 && groupadd --system --gid 10001 brief \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin brief

FROM base AS test
COPY . .
# The unit suite is a build step: an image whose tests fail does not exist.
RUN python -m unittest discover -s tests -t .

FROM base AS runtime
# Copying from the test stage is what makes it run.
COPY --from=test /app/brief /app/brief
COPY --from=test /app/samples /app/samples
COPY --from=test /app/VERSION /app/VERSION
RUN mkdir /data && chown 10001:10001 /data
ENV DATA_DIR=/data HOST=0.0.0.0 PORT=4960
VOLUME /data
USER 10001:10001
EXPOSE 4960
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4960/healthz', timeout=4)"]
CMD ["python", "-m", "brief", "serve"]
