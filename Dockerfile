FROM python:3.7 AS builder
COPY ./requirements.txt .

RUN pip install -r requirements.txt

FROM daskdev/dask

RUN apt-get update && apt-get install -y libmariadb3

RUN mkdir /app
WORKDIR /app
ENV PYTHONPATH=.

COPY --from=builder /usr/local/lib/python3.7/site-packages /opt/conda/lib/python3.7/site-packages