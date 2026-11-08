FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/qwen/requirements.txt
RUN pip install --no-cache-dir -r /opt/qwen/requirements.txt
RUN groupadd --gid 10001 qwen && useradd --uid 10001 --gid 10001 --no-create-home qwen && mkdir -p /work /outputs /attachments /runtime && chown 10001:10001 /work /outputs /runtime
COPY kernel_runner.py /opt/qwen/kernel_runner.py
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg PLOTLY_RENDERER=plotly_mimetype HOME=/tmp/qwen JUPYTER_RUNTIME_DIR=/runtime IPYTHONDIR=/runtime/ipython OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["python", "-I", "-u", "/opt/qwen/kernel_runner.py"]
