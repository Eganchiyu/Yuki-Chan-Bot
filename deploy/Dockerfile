# Yuki 运行镜像：只装依赖，不 COPY 代码。
#
# 为什么代码不进镜像：自进化需要「改完重启即生效」。代码以 :ro 挂载进容器，
# 换代码只需重启容器（秒级），不必重新构建镜像；同时容器内代码物理不可写，
# 小女仆无法直接改坏正在运行的生产代码。
#
# 构建：docker build -f deploy/Dockerfile -t yuki:base .
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai

# libgomp1: onnxruntime/torch 运行期依赖；libgl1+libglib2.0-0: opencv；curl: HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libgl1 libglib2.0-0 curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# 与宿主路径保持一致：容器内代码挂到同一绝对路径，file:// 引用才通
WORKDIR /app

# 只把依赖声明带进来，改代码不会让依赖层失效
COPY pyproject.toml /app/pyproject.toml
RUN python -c "import tomllib;d=tomllib.load(open('/app/pyproject.toml','rb'));open('/tmp/req.txt','w').write('\n'.join(d['project']['dependencies']))" \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/req.txt

# 运行期工作目录由 deploy/run.sh 的 -w "$ROOT" 指定（与宿主同路径），不依赖本镜像 WORKDIR
ENV YUKI_HEALTH_PORT=8778 \
    YUKI_HEALTH_HOST=127.0.0.1 \
    YUKI_DESKTOP_PET=0 \
    NO_PROXY=127.0.0.1,localhost

EXPOSE 8778

HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8778/health || exit 1

CMD ["python", "main.py"]
