"""
設定管理モジュール
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ベースディレクトリ
BASE_DIR = Path(__file__).resolve().parent.parent

# API設定
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# ファイルパス
MASTER_DATA_DIR = BASE_DIR / 'master_data'
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'output'

# ディレクトリ作成
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# 弥生会計CSV設定
YAYOI_CSV_ENCODING = 'cp932'
YAYOI_CSV_COLUMNS = [
    '日付', '伝票No.', '決算', '調整', '付箋１', '付箋2', 'タイプ', '生成元',
    '', '勘定科目', '補助科目', '部門', '税区分', '税計算区分', '金額', '消費税額',
    '', '勘定科目', '補助科目', '部門', '税区分', '税計算区分', '金額', '消費税額',
    '', '摘要', '請求書区分', '仕入税額控除', '期日', '番号', '仕訳メモ', '作業日付', '仕訳番号'
]

# 税区分マッピング
TAX_CATEGORIES = {
    '対象外': '対象外',
    '課対仕入10%': '課対仕入10%',
    '課税売上10%': '課税売上10%',
    '課対仕入8%': '課対仕入8%',
    '非課税': '非課税',
    '不課税': '不課税'
}

# Flaskアプリ設定
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB (100枚対応)
    UPLOAD_EXTENSIONS = [
        '.pdf',
        # 一般的な画像形式
        '.png', '.jpg', '.jpeg', '.gif', '.webp',
        # 追加画像形式
        '.bmp', '.tiff', '.tif',
        # iPhone/iOS
        '.heic', '.heif',
    ]

# バッチ処理設定
BATCH_MAX_FILES = 200  # 最大ファイル数
BATCH_CONCURRENT = 5   # 同時処理数
