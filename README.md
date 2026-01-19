# 請求書自動仕訳システム

請求書PDF/画像からOCRでデータを抽出し、弥生会計インポート用の仕訳CSV（CP932、25列）を自動生成するシステム。

## 機能

- Claude Vision APIによる請求書OCR
- 売掛/買掛の自動判別
- 弥生会計インポート用CSV出力（CP932エンコーディング）
- 「優良な電子帳簿」対応（訂正履歴・検索機能・相互関連性）

## プロジェクト構造

```
invoice-journal-system/
├── main.py                      # Flask APIサーバー
├── requirements.txt             # 依存パッケージ
├── config/
│   └── settings.py              # 設定管理
├── master_data/                 # マスタデータ（JSON）
│   ├── vendors.json             # 発行元マスタ
│   ├── journal_rules.json       # 仕訳ルールマスタ
│   └── clients.json             # クライアント企業マスタ
├── services/
│   ├── ocr_service.py           # Claude Vision API OCR処理
│   ├── journal_service.py       # 仕訳生成ロジック
│   ├── csv_service.py           # CSV出力処理
│   └── master_service.py        # マスタデータ管理
├── templates/
│   └── index.html               # フロントエンド
├── static/
│   ├── css/style.css
│   └── js/app.js
└── docs/
    └── 経理確認事項_仕訳ルール.docx  # 経理担当者確認用
```

## セットアップ

```bash
pip install -r requirements.txt
```

## 環境変数

```
ANTHROPIC_API_KEY=your_api_key
```

## 実行

```bash
python main.py
```

## ドキュメント

- [経理確認事項_仕訳ルール.docx](docs/経理確認事項_仕訳ルール.docx) - 経理担当者への仕訳ルール確認書
