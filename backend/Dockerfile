FROM python:3.12-slim

# 国内构建加速:debian apt + pip 换腾讯云源(海外/CI 用 --build-arg APT_MIRROR= PIP_INDEX= 置空即关闭)
ARG APT_MIRROR=mirrors.tencentyun.com
ARG PIP_INDEX=https://mirrors.tencentyun.com/pypi/simple
RUN if [ -n "$APT_MIRROR" ]; then \
      for f in /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list; do \
        [ -f "$f" ] && sed -i "s|deb.debian.org|$APT_MIRROR|g; s|security.debian.org|$APT_MIRROR|g" "$f"; \
      done; \
    fi

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
RUN pip install --no-cache-dir ${PIP_INDEX:+-i $PIP_INDEX} .

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
