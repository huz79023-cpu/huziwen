FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# 安装系统依赖（ffmpeg 用于音频处理）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制服务代码
COPY app.py .

# 阿里云 FC 自定义容器标准端口
EXPOSE 9000

CMD ["python", "-u", "app.py"]
