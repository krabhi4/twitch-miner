FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

COPY ./requirements.txt ./

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -qq -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    zlib1g-dev \
    libjpeg-dev \
    libblas-dev \
    liblapack-dev \
  && pip install --upgrade pip \
  && pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    RUNNING_IN_DOCKER=1

WORKDIR /usr/src/app

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -qq -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/wheels /wheels
COPY ./requirements.txt ./

RUN pip install --upgrade pip \
  && pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
  && rm -rf /wheels

RUN mkdir -p /usr/src/app/analytics /usr/src/app/cookies /usr/src/app/logs

COPY ./TwitchChannelPointsMiner ./TwitchChannelPointsMiner
COPY ./assets ./assets

ENTRYPOINT [ "python", "run.py" ]
