"""
OCRサービス
Claude Vision APIを使用した請求書OCR処理
"""
import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import anthropic

from config.companies import is_group_company


class OcrService:
    """Claude Vision APIを使用したOCRサービス"""

    # 勘定科目判定用キーワードマッピング
    ACCOUNT_KEYWORDS = {
        'land_rent': {
            'keywords': ['賃料', '家賃', '地代', '共益費', '管理費'],
            'debit_account': '地代家賃',
            'description_prefix': '賃料'
        },
        'rent': {
            'keywords': ['リース', 'PCリース', 'レンタル'],
            'debit_account': '賃借料',
            'description_prefix': 'リース料'
        },
        'outsourcing_expense': {
            'keywords': ['業務支援', '業務委託', '外注', '人件費', '派遣'],
            'debit_account': '外注費',
            'description_prefix': ''
        },
        'travel_expense': {
            'keywords': ['出張', '精算', '旅費', '交通費', '新幹線', '宿泊'],
            'debit_account': '旅費交通費',
            'description_prefix': '出張精算'
        },
        'welfare_expense': {
            'keywords': ['慶祝金', '弔慰金', '見舞金', '祝金'],
            'debit_account': '福利厚生費',
            'description_prefix': ''
        },
        'miscellaneous': {
            'keywords': ['廃棄物', '清掃', '処理費'],
            'debit_account': '雑費',
            'description_prefix': ''
        },
        'utilities': {
            'keywords': ['電気', '水道', '光熱', 'ガス'],
            'debit_account': '水道光熱費',
            'description_prefix': ''
        },
        'advertising': {
            'keywords': ['パンフレット', '印刷', '広告', '看板', 'チラシ', 'ポスター'],
            'debit_account': '広告宣伝費',
            'description_prefix': ''
        },
        'consumables': {
            'keywords': ['備品', '消耗品', '文具', '事務用品'],
            'debit_account': '消耗品費',
            'description_prefix': ''
        },
        'sales_receivable': {
            'keywords': ['経営指導料', '指導料', 'コンサルティング'],
            'debit_account': '売掛金',
            'credit_account': '売上高',
            'description_prefix': ''
        }
    }

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def _extract_json(self, text: str) -> Dict:
        """
        テキストからJSONオブジェクトを安全に抽出
        複数のJSONがある場合は最初のものを返す
        """
        if not text:
            return {}

        # まず全体をJSONとしてパースを試みる
        text = text.strip()
        if text.startswith('{'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # バランスの取れたJSONオブジェクトを探す
        start_idx = text.find('{')
        if start_idx == -1:
            return {}

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start_idx:], start_idx):
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    json_str = text[start_idx:i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        # このJSONが不正なら次を探す
                        start_idx = text.find('{', i + 1)
                        if start_idx == -1:
                            return {}
                        depth = 0

        return {}

    def _encode_image(self, image_path: Path) -> Tuple[str, str]:
        """画像をBase64エンコード（様々な形式に対応）"""
        suffix = image_path.suffix.lower()

        # 直接対応可能な形式
        direct_media_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }

        # 変換が必要な形式
        convert_formats = ['.heic', '.heif', '.bmp', '.tiff', '.tif']

        if suffix in direct_media_type_map:
            media_type = direct_media_type_map[suffix]
            with open(image_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')
            return image_data, media_type

        elif suffix in convert_formats:
            # Pillowで変換してPNG形式で出力
            try:
                from PIL import Image
                import io

                # HEIC対応にはpillow-heifが必要
                if suffix in ['.heic', '.heif']:
                    try:
                        import pillow_heif
                        pillow_heif.register_heif_opener()
                    except ImportError:
                        pass

                img = Image.open(image_path)
                # RGBA→RGB変換（必要な場合）
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                image_data = base64.standard_b64encode(img_byte_arr.read()).decode('utf-8')
                return image_data, 'image/png'
            except Exception as e:
                # 変換失敗時はそのまま読み込み
                with open(image_path, 'rb') as f:
                    image_data = base64.standard_b64encode(f.read()).decode('utf-8')
                return image_data, 'image/png'

        else:
            # 未知の形式はそのまま読み込み
            with open(image_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')
            return image_data, 'image/png'

    def _encode_pdf_page(self, pdf_path: Path, page_num: int = 0) -> Tuple[Optional[str], str]:
        """PDFページをBase64エンコード（pdf2imageが必要）"""
        try:
            from pdf2image import convert_from_path
            import io

            # PDFをPIL Imageに変換
            images = convert_from_path(str(pdf_path), first_page=page_num + 1, last_page=page_num + 1)
            if not images:
                return None, ''

            # PNG形式でバイト列に変換
            img_byte_arr = io.BytesIO()
            images[0].save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)

            image_data = base64.standard_b64encode(img_byte_arr.read()).decode('utf-8')
            return image_data, 'image/png'
        except ImportError:
            # pdf2imageがない場合はPDFをそのまま読み込み
            with open(pdf_path, 'rb') as f:
                pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')
            return pdf_data, 'application/pdf'
        except Exception:
            return None, ''

    def _get_pdf_page_count(self, pdf_path: Path) -> int:
        """PDFのページ数を取得"""
        try:
            from pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(str(pdf_path))
            return info.get('Pages', 1)
        except Exception:
            return 1

    def extract_invoice_data(self, image_path: Path) -> Dict:
        """
        請求書画像からデータを抽出

        Returns:
            {
                'issuer': 発行元,
                'recipient': 宛先,
                'invoice_no': 請求書番号,
                'date': 請求日,
                'due_date': 支払期日,
                'amount': 金額,
                'tax_amount': 消費税額,
                'total_amount': 合計金額,
                'items': [{'name': 品目, 'quantity': 数量, 'unit_price': 単価, 'amount': 金額}],
                'invoice_type': 'sales' or 'purchase',
                'document_type': 'invoice', 'expense_report', 'celebration_application',
                'description': 摘要,
                'suggested_account': 推奨勘定科目
            }
        """
        suffix = image_path.suffix.lower()

        if suffix == '.pdf':
            image_data, media_type = self._encode_pdf_page(image_path, 0)
        else:
            image_data, media_type = self._encode_image(image_path)

        if not image_data:
            return {}

        prompt = """この書類画像から情報を抽出してJSON形式で返してください。

まず書類の種類を判定してください:
- invoice: 請求書
- expense_report: 出張精算書・経費精算書
- celebration_application: 慶祝金・弔慰金申請書
- other: その他

抽出項目:
- document_type: 書類の種類（上記のいずれか）
- issuer: 発行元（請求書を発行した会社名）
- recipient: 宛先（請求書の宛先会社名）
- invoice_no: 請求書番号
- date: 請求日/申請日（YYYY-MM-DD形式）
- due_date: 支払期日（YYYY-MM-DD形式、あれば）
- subtotal: 小計（税抜金額）
- tax_amount: 消費税額
- total_amount: 合計金額（税込）
- items: 明細行の配列 [{"name": "品目名", "quantity": 数量, "unit_price": 単価, "amount": 金額}]
- registration_no: インボイス登録番号（T+13桁の番号、あれば）
- description: 請求内容の要約（「○月分 ○○費」のような形式で）

出張精算書の場合は追加で:
- employee_name: 申請者名
- department: 所属（法人名や部署）
- destination: 行先
- travel_period: 出張期間
- transportation_cost: 交通費
- accommodation_cost: 宿泊費
- daily_allowance: 日当

慶祝金・弔慰金申請書の場合は追加で:
- applicant_name: 申請者名
- applicant_department: 申請者所属
- celebration_type: 種別（慶祝金 or 弔慰金）
- amount: 金額
- bank_info: 振込先口座情報

JSONのみを返してください。説明は不要です。
金額は数値のみ（カンマなし）で返してください。
日付が読み取れない場合は空文字を返してください。
"""

        content = [
            {
                "type": "image" if media_type != 'application/pdf' else "document",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        # JSONを抽出
        response_text = response.content[0].text
        invoice_data = self._extract_json(response_text)

        # 売上/仕入の判定
        invoice_data['invoice_type'] = self._determine_invoice_type(invoice_data)

        # 勘定科目の推定
        invoice_data['suggested_account'] = self._suggest_account(invoice_data)

        return invoice_data

    def extract_multi_page_invoice(self, pdf_path: Path) -> List[Dict]:
        """
        複数ページのPDFから各ページの請求書データを抽出

        Returns:
            List of invoice data dictionaries
        """
        page_count = self._get_pdf_page_count(pdf_path)
        results = []

        for page_num in range(page_count):
            image_data, media_type = self._encode_pdf_page(pdf_path, page_num)
            if not image_data:
                continue

            prompt = """このページは請求書ですか？請求書の場合のみ、以下の情報をJSON形式で返してください。
請求書でない場合は {"is_invoice": false} を返してください。

抽出項目:
- is_invoice: true（このページが請求書の場合）
- issuer: 発行元
- recipient: 宛先
- invoice_no: 請求書番号
- date: 請求日（YYYY-MM-DD形式）
- due_date: 支払期日
- subtotal: 小計
- tax_amount: 消費税額
- total_amount: 合計金額
- items: 明細行の配列
- registration_no: インボイス登録番号
- description: 請求内容の要約

JSONのみを返してください。金額は数値のみで返してください。
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            response_text = response.content[0].text
            page_data = self._extract_json(response_text)
            if page_data and page_data.get('is_invoice', True):
                page_data['page_number'] = page_num + 1
                page_data['invoice_type'] = self._determine_invoice_type(page_data)
                page_data['suggested_account'] = self._suggest_account(page_data)
                results.append(page_data)

        return results

    def extract_expense_report(self, image_path: Path) -> List[Dict]:
        """
        出張精算書から複数の精算データを抽出

        Returns:
            List of expense report data (each page/trip as separate entry)
        """
        suffix = image_path.suffix.lower()

        if suffix == '.pdf':
            page_count = self._get_pdf_page_count(image_path)
        else:
            page_count = 1

        results = []

        for page_num in range(page_count):
            if suffix == '.pdf':
                image_data, media_type = self._encode_pdf_page(image_path, page_num)
            else:
                image_data, media_type = self._encode_image(image_path)

            if not image_data:
                continue

            prompt = """この出張精算書から情報を抽出してJSON形式で返してください。

抽出項目:
- department: 所属（法人名）- ヘッダー部分に記載されている会社名
- employee_name: 氏名
- position: 役職
- destination: 行先
- purpose: 用件
- travel_start: 出張開始日（YYYY-MM-DD形式）
- travel_end: 出張終了日（YYYY-MM-DD形式）
- transportation_cost: 交通費合計
- accommodation_cost: 宿泊料
- daily_allowance: 宿泊日当
- total_amount: 総計
- advance_payment: 仮出金額
- settlement_amount: 追金または返納額

JSONのみを返してください。金額は数値のみで返してください。
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            response_text = response.content[0].text
            expense_data = self._extract_json(response_text)
            if expense_data:
                expense_data['document_type'] = 'expense_report'
                expense_data['page_number'] = page_num + 1
                expense_data['suggested_account'] = 'travel_expense'

                # 摘要を自動生成
                employee = expense_data.get('employee_name', '')
                dest = expense_data.get('destination', '')
                expense_data['description'] = f"出張精算 {employee} {dest}"

                results.append(expense_data)

        return results

    def extract_celebration_application(self, image_path: Path) -> Dict:
        """
        慶祝金・弔慰金申請書からデータを抽出

        Returns:
            Application data dictionary
        """
        suffix = image_path.suffix.lower()

        if suffix == '.pdf':
            image_data, media_type = self._encode_pdf_page(image_path, 0)
        else:
            image_data, media_type = self._encode_image(image_path)

        if not image_data:
            return {}

        prompt = """この慶祝金・弔慰金申請書から情報を抽出してJSON形式で返してください。

抽出項目:
- application_date: 申請日（YYYY-MM-DD形式）
- applicant_name: 申請者氏名
- applicant_department: 申請者所属
- application_type: 種別（"慶祝金" または "弔慰金"）
- amount: 金額
- bank_name: 銀行名
- branch_name: 支店名
- account_type: 口座種別（普通/当座）
- account_number: 口座番号
- account_holder: 口座名義

JSONのみを返してください。金額は数値のみで返してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        response_text = response.content[0].text
        app_data = self._extract_json(response_text)
        if app_data:
            app_data['document_type'] = 'celebration_application'
            app_data['suggested_account'] = 'welfare_expense'

            # 摘要を自動生成
            app_type = app_data.get('application_type', '慶祝金')
            applicant = app_data.get('applicant_name', '')
            app_data['description'] = f"{app_type} {applicant}"

            return app_data

        return {}

    def _determine_invoice_type(self, invoice_data: Dict) -> str:
        """
        請求書タイプを判定（売上 or 仕入）
        """
        issuer = invoice_data.get('issuer', '')
        recipient = invoice_data.get('recipient', '')

        # 発行元が自社グループ → 売上
        if is_group_company(issuer):
            return 'sales'

        # 宛先が自社グループ → 仕入
        if is_group_company(recipient):
            return 'purchase'

        # デフォルトは仕入（請求された側）
        return 'purchase'

    def _suggest_account(self, invoice_data: Dict) -> str:
        """
        請求内容から勘定科目を推定
        """
        # 書類タイプによる判定
        doc_type = invoice_data.get('document_type', 'invoice')
        if doc_type == 'expense_report':
            return 'travel_expense'
        if doc_type == 'celebration_application':
            return 'welfare_expense'

        # 明細行の品目を検索
        items = invoice_data.get('items', [])
        description = invoice_data.get('description', '')
        issuer = invoice_data.get('issuer', '')

        # 検索対象テキストを結合
        search_text = description
        for item in items:
            search_text += ' ' + str(item.get('name', ''))

        search_text = search_text + ' ' + issuer

        # キーワードマッチング
        for rule_id, rule in self.ACCOUNT_KEYWORDS.items():
            for keyword in rule['keywords']:
                if keyword in search_text:
                    return rule_id

        # デフォルト: 売上なら売上計上、仕入なら仕入計上
        invoice_type = invoice_data.get('invoice_type', 'purchase')
        if invoice_type == 'sales':
            return 'sales_receivable'
        else:
            return 'purchase'

    def extract_payment_info(self, image_path: Path) -> Dict:
        """
        入金通知・振込明細からデータを抽出

        Returns:
            {
                'date': 入金日,
                'payer': 振込人,
                'amount': 金額,
                'bank_account': 入金口座
            }
        """
        image_data, media_type = self._encode_image(image_path)

        prompt = """この入金通知または振込明細から以下の情報を抽出してJSON形式で返してください。

抽出項目:
- date: 入金日・振込日（YYYY-MM-DD形式）
- payer: 振込人・送金者名
- amount: 金額
- bank_account: 入金先口座（銀行名・支店名があれば）
- reference: 振込依頼人名義または参照番号

JSONのみを返してください。
金額は数値のみ（カンマなし）で返してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        response_text = response.content[0].text
        return self._extract_json(response_text)

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """日付文字列をパース"""
        if not date_str:
            return None

        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y年%m月%d日',
            '%Y.%m.%d'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def detect_document_type(self, image_path: Path) -> str:
        """
        書類の種類を検出

        Returns:
            'invoice', 'expense_report', 'celebration_application', 'payment_notice', 'other'
        """
        suffix = image_path.suffix.lower()

        if suffix == '.pdf':
            image_data, media_type = self._encode_pdf_page(image_path, 0)
        else:
            image_data, media_type = self._encode_image(image_path)

        if not image_data:
            return 'other'

        prompt = """この書類の種類を判定してください。以下のいずれかを返してください：
- invoice: 請求書
- expense_report: 出張精算書・経費精算書
- celebration_application: 慶祝金・弔慰金申請書
- payment_notice: 入金通知・振込明細
- other: その他

種類名のみを返してください。説明は不要です。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )

        response_text = response.content[0].text.strip().lower()

        valid_types = ['invoice', 'expense_report', 'celebration_application', 'payment_notice', 'other']
        for valid_type in valid_types:
            if valid_type in response_text:
                return valid_type

        return 'invoice'  # デフォルトは請求書
