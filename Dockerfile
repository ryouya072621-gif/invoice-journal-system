# Python 3.11をベースイメージとして使用
FROM python:3.11-slim

# 作業ディレクトリを設定
WORKDIR /app

# requirements.txtをコピーして依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 環境変数
ENV PORT=8080
ENV FLASK_ENV=production

# ポートを公開
EXPOSE 8080

# gunicornでアプリを起動
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
