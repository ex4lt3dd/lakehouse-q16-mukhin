FROM apache/superset:4.1.2@sha256:15e110b8533d3cb6a0d529512ea71252b0ac62e3f72b1f7a5000f1361822ac26
USER root
RUN pip install --no-cache-dir "trino[sqlalchemy]==0.333.0"
USER superset
