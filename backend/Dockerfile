FROM python:3.12-slim

WORKDIR /app

# ffmpeg/ffprobe：成片合成与时长探测必需
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# .dockerignore 挡住 .env / dev.db / storage / tests，只带走业务代码
COPY . .

EXPOSE 8000

# --proxy-headers：信任 nginx 转发的 X-Forwarded-*（拿真实客户端 IP）；
# forwarded-allow-ips 限定内网段（compose 网段），不信任外部直连伪造
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "172.16.0.0/12 192.168.0.0/16 10.0.0.0/8"]
