FROM python:3.12-slim

# libpq5: psycopg 运行时;libreoffice-writer(含 soffice):旧版 .doc→PDF 转换(真题批量解析);
# fonts-noto-cjk:中文字体(转换/渲染中文卷面用)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    libreoffice-writer \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# soffice 首次运行需可写 HOME 放用户配置
ENV HOME=/root

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
