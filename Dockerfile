FROM python:3.11-alpine
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY gen.py .
# 这一步是为了确保权限，防止脚本无法在映射目录写入
RUN mkdir /output && chmod 777 /output
CMD ["python", "-u", "gen.py"]