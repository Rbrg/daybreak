FROM python:3.12-slim

WORKDIR /app

# 先复制依赖声明利用层缓存；知识库与代码常变，放在后面
COPY pyproject.toml README.md ./
COPY agent/ ./agent/
COPY knowledge/ ./knowledge/
COPY evals/ ./evals/

RUN pip install --no-cache-dir .

# 交互式 REPL：docker run -it --env-file .env cli-agent
# 跑评估：     docker run --rm --env-file .env cli-agent python -m evals
ENTRYPOINT ["python", "-m", "agent"]
CMD []
