"""
銀行取引サービス
銀行CSVの解析と自動仕分け
"""
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json


class BankService:
    """銀行取引の解析・自動仕分けサービス"""

    # 摘要キーワードからルールIDへのマッピング（過去データ分析に基づく）
    DESCRIPTION_RULES = {
        # 入金系
        'receivable_collection': {
            'keywords': ['売掛金', '売掛', '入金', 'さくら会', '口腔ケア', 'スマイル会', 'ハピネス', '浩蘭会', '仁鈴会'],
            'direction': 'deposit',
            'priority': 1
        },
        'temporary_received_deposit': {
            'keywords': ['不明入金', '仮受'],
            'direction': 'deposit',
            'priority': 2
        },
        'short_term_loan_receipt': {
            'keywords': ['貸付金回収', '短期貸付'],
            'direction': 'deposit',
            'priority': 3
        },
        'short_term_borrowing': {
            'keywords': ['借入', '融資'],
            'direction': 'deposit',
            'priority': 4
        },
        'miscellaneous_income': {
            'keywords': ['雑収入', '還付', '返金'],
            'direction': 'deposit',
            'priority': 5
        },
        'tax_refund': {
            'keywords': ['法人税還付', '国税還付', '還付金'],
            'direction': 'deposit',
            'priority': 6
        },

        # 出金系
        'bank_fee': {
            'keywords': ['振込手数料', '手数料', 'テスウリヨウ', 'ﾃｽｳﾘﾖｳ'],
            'direction': 'withdrawal',
            'priority': 10
        },
        'corporate_tax_payment': {
            'keywords': ['法人税', '住民税', '事業税', '国税', '地方税', '法人都道府県民税', '法人市民税'],
            'direction': 'withdrawal',
            'priority': 11
        },
        'consumption_tax_payment': {
            'keywords': ['消費税', '消費税等'],
            'direction': 'withdrawal',
            'priority': 12
        },
        'salary_payment': {
            'keywords': ['給与', '給料', '賃金', 'キュウヨ', 'ｷｭｳﾖ'],
            'direction': 'withdrawal',
            'priority': 13
        },
        'resident_tax_payment': {
            'keywords': ['住民税', '特別徴収'],
            'direction': 'withdrawal',
            'priority': 14
        },
        'social_insurance_payment': {
            'keywords': ['社会保険', '健康保険', '厚生年金', '年金', '社保', '労働保険', '雇用保険'],
            'direction': 'withdrawal',
            'priority': 15
        },
        'outsourcing_payment': {
            'keywords': ['外注', 'コーシ', 'ｺｰｼ', 'エディ', 'ﾕｰｽ', 'マツクボ'],
            'direction': 'withdrawal',
            'priority': 16
        },
        'lease_payment': {
            'keywords': ['リース', 'ﾘｰｽ', 'PCリース', 'コピー機'],
            'direction': 'withdrawal',
            'priority': 17
        },
        'land_rent_payment': {
            'keywords': ['家賃', '賃料', '地代', '共益費', '管理費'],
            'direction': 'withdrawal',
            'priority': 18
        },
        'utilities_payment': {
            'keywords': ['電気', '水道', 'ガス', '光熱', '中部電力', '東邦ガス'],
            'direction': 'withdrawal',
            'priority': 19
        },
        'communication_expense': {
            'keywords': ['電話', '通信', 'NTT', 'ドコモ', 'ソフトバンク', 'KDDI'],
            'direction': 'withdrawal',
            'priority': 20
        },
        'insurance': {
            'keywords': ['保険', '損保', '生保', '東京海上', '三井住友海上'],
            'direction': 'withdrawal',
            'priority': 21
        },
        'long_term_loan': {
            'keywords': ['借入返済', '長期借入', 'ローン', '元金', '返済'],
            'direction': 'withdrawal',
            'priority': 22
        },
        'interest_expense': {
            'keywords': ['利息', '金利'],
            'direction': 'withdrawal',
            'priority': 23
        },
        'purchase_payment': {
            'keywords': ['仕入', '買掛', '支払'],
            'direction': 'withdrawal',
            'priority': 24
        },
        'travel_expense_bank': {
            'keywords': ['出張', '旅費', '交通費'],
            'direction': 'withdrawal',
            'priority': 25
        },
        'welfare_expense': {
            'keywords': ['慶祝金', '弔慰金', '祝金', '見舞金', '福利'],
            'direction': 'withdrawal',
            'priority': 26
        },
        'consumables_payment': {
            'keywords': ['消耗品', '備品', '文具', 'アスクル', 'ASKUL'],
            'direction': 'withdrawal',
            'priority': 27
        },
        'advertising': {
            'keywords': ['広告', '宣伝', '印刷', 'パンフレット'],
            'direction': 'withdrawal',
            'priority': 28
        },
        'fixed_asset_purchase': {
            'keywords': ['固定資産', '工具', '器具', '備品購入', '設備'],
            'direction': 'withdrawal',
            'priority': 29
        },
        'vehicle_expense': {
            'keywords': ['車両', '自動車', 'ガソリン', '燃料', '駐車'],
            'direction': 'withdrawal',
            'priority': 30
        },
        'short_term_loan_payment': {
            'keywords': ['貸付', '短期貸付実行'],
            'direction': 'withdrawal',
            'priority': 31
        },
        'prepaid_expense_payment': {
            'keywords': ['前払', '前納'],
            'direction': 'withdrawal',
            'priority': 32
        },
        'bank_transfer': {
            'keywords': ['振替', '口座振替', '自振', 'ﾌﾘｺﾐ'],
            'direction': 'withdrawal',
            'priority': 33
        },
        'miscellaneous': {
            'keywords': [],  # デフォルト
            'direction': 'withdrawal',
            'priority': 99
        }
    }

    # グループ会社リスト（売掛金回収の判定用）
    GROUP_COMPANIES = [
        'SOKUTA', 'ソクタ', '白', 'ソーコー', '有馬', 'ケイ', 'KURUMI', 'クルミ',
        'カーリー', 'ヒロ', 'リクル', '医療白人', 'sakura', 'サクラ', 'ノーブ',
        'ヒーロ', '岩田', 'デンサポ', 'エナックス', 'モト', 'ユース', 'コーシ',
        'マツクボ', 'エディプラス', '日本水販売', 'ハピネスユウ',
        'サンポウ', 'コンゲン', 'M&A', 'トリプルウィン',
        'さくら会', '口腔ケア', 'スマイル会', 'ハピネス', '浩蘭会', '仁鈴会', 'MOO',
        '中京医療', 'VJCONSUL'
    ]

    def __init__(self, master_data_dir: Path):
        self.master_data_dir = master_data_dir
        self._load_rules()
        self._load_vendors()

    def _load_rules(self):
        """仕訳ルールを読み込み"""
        rules_path = self.master_data_dir / 'journal_rules.json'
        with open(rules_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.rules = {r['id']: r for r in data['rules']}

    def _load_vendors(self):
        """取引先マスタを読み込み"""
        vendors_path = self.master_data_dir / 'vendors.json'
        try:
            with open(vendors_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.vendors = {v['name']: v for v in data['vendors']}
        except FileNotFoundError:
            self.vendors = {}

    def parse_bank_csv(self, csv_path: Path, bank_type: str = 'aichi') -> List[Dict]:
        """
        銀行CSVを解析して取引リストに変換

        Args:
            csv_path: CSVファイルのパス
            bank_type: 銀行種別 ('aichi', 'mufg', 'smbc', etc.)

        Returns:
            [
                {
                    'date': '2024-01-15',
                    'description': '振込 サクラカイ',
                    'deposit': 100000,  # 入金
                    'withdrawal': 0,     # 出金
                    'balance': 1234567,
                    'direction': 'deposit' or 'withdrawal'
                }
            ]
        """
        transactions = []

        # 銀行種別に応じたパーサーを選択
        parser = self._get_parser(bank_type)

        with open(csv_path, 'r', encoding='cp932') as f:
            reader = csv.reader(f)

            # ヘッダー行をスキップ
            for _ in range(parser['skip_rows']):
                next(reader, None)

            for row in reader:
                if len(row) < parser['min_cols']:
                    continue

                try:
                    transaction = parser['parse_row'](row)
                    if transaction:
                        transactions.append(transaction)
                except (ValueError, IndexError):
                    continue

        return transactions

    def _get_parser(self, bank_type: str) -> Dict:
        """銀行種別に応じたパーサーを返す"""
        parsers = {
            'aichi': {
                'skip_rows': 1,
                'min_cols': 5,
                'parse_row': self._parse_aichi_row
            },
            'mufg': {
                'skip_rows': 1,
                'min_cols': 6,
                'parse_row': self._parse_mufg_row
            },
            'smbc': {
                'skip_rows': 1,
                'min_cols': 6,
                'parse_row': self._parse_smbc_row
            }
        }
        return parsers.get(bank_type, parsers['aichi'])

    def _parse_aichi_row(self, row: List[str]) -> Optional[Dict]:
        """愛知銀行CSVの行を解析"""
        # 想定フォーマット: 日付, 摘要, お預り金額, お支払金額, 残高
        date_str = row[0].strip()
        description = row[1].strip()
        deposit = self._parse_amount(row[2])
        withdrawal = self._parse_amount(row[3])
        balance = self._parse_amount(row[4]) if len(row) > 4 else 0

        if not date_str or (deposit == 0 and withdrawal == 0):
            return None

        return {
            'date': self._parse_date(date_str),
            'description': description,
            'deposit': deposit,
            'withdrawal': withdrawal,
            'balance': balance,
            'direction': 'deposit' if deposit > 0 else 'withdrawal'
        }

    def _parse_mufg_row(self, row: List[str]) -> Optional[Dict]:
        """三菱UFJ銀行CSVの行を解析"""
        # 想定フォーマット: 日付, お取引内容, お預り金額, お支払金額, 残高, メモ
        date_str = row[0].strip()
        description = row[1].strip()
        deposit = self._parse_amount(row[2])
        withdrawal = self._parse_amount(row[3])
        balance = self._parse_amount(row[4]) if len(row) > 4 else 0

        if not date_str or (deposit == 0 and withdrawal == 0):
            return None

        return {
            'date': self._parse_date(date_str),
            'description': description,
            'deposit': deposit,
            'withdrawal': withdrawal,
            'balance': balance,
            'direction': 'deposit' if deposit > 0 else 'withdrawal'
        }

    def _parse_smbc_row(self, row: List[str]) -> Optional[Dict]:
        """三井住友銀行CSVの行を解析"""
        # 想定フォーマット: 年月日, お取引内容, お預り金額, お引出し金額, 残高, メモ
        date_str = row[0].strip()
        description = row[1].strip()
        deposit = self._parse_amount(row[2])
        withdrawal = self._parse_amount(row[3])
        balance = self._parse_amount(row[4]) if len(row) > 4 else 0

        if not date_str or (deposit == 0 and withdrawal == 0):
            return None

        return {
            'date': self._parse_date(date_str),
            'description': description,
            'deposit': deposit,
            'withdrawal': withdrawal,
            'balance': balance,
            'direction': 'deposit' if deposit > 0 else 'withdrawal'
        }

    def _parse_amount(self, amount_str: str) -> int:
        """金額文字列を数値に変換"""
        if not amount_str:
            return 0
        # カンマ、円、スペースを除去
        cleaned = re.sub(r'[,\s円¥]', '', amount_str)
        try:
            return int(cleaned)
        except ValueError:
            return 0

    def _parse_date(self, date_str: str) -> str:
        """日付文字列をYYYY-MM-DD形式に変換"""
        formats = [
            '%Y/%m/%d',
            '%Y-%m-%d',
            '%Y年%m月%d日',
            '%Y.%m.%d',
            '%m/%d',  # 年なしの場合
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if fmt == '%m/%d':
                    dt = dt.replace(year=datetime.now().year)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return date_str

    def match_rule(self, transaction: Dict) -> Tuple[str, str, float]:
        """
        取引内容から仕訳ルールをマッチング

        Args:
            transaction: 取引データ

        Returns:
            (rule_id, vendor_name, confidence)
        """
        description = transaction.get('description', '')
        direction = transaction.get('direction', 'withdrawal')

        best_match = None
        best_priority = 999
        best_confidence = 0.0
        matched_vendor = ''

        # 摘要からルールをマッチング
        for rule_id, rule_config in self.DESCRIPTION_RULES.items():
            # 入金/出金の方向をチェック
            if rule_config['direction'] != direction:
                continue

            for keyword in rule_config['keywords']:
                if keyword in description or keyword.lower() in description.lower():
                    priority = rule_config['priority']
                    confidence = 0.9 - (priority * 0.01)  # 優先度が高いほど信頼度も高い

                    if priority < best_priority:
                        best_match = rule_id
                        best_priority = priority
                        best_confidence = confidence

        # グループ会社名のマッチング（売掛金回収の判定）
        if direction == 'deposit':
            for company in self.GROUP_COMPANIES:
                if company in description:
                    matched_vendor = company
                    if best_match is None:
                        best_match = 'receivable_collection'
                        best_confidence = 0.85
                    break

        # マッチしなかった場合のデフォルト
        if best_match is None:
            if direction == 'deposit':
                best_match = 'temporary_received_deposit'
                best_confidence = 0.5
            else:
                best_match = 'miscellaneous'
                best_confidence = 0.5

        return best_match, matched_vendor, best_confidence

    def process_transactions(self, transactions: List[Dict]) -> List[Dict]:
        """
        取引リストを処理して仕訳データを生成

        Args:
            transactions: 取引リスト

        Returns:
            仕訳データのリスト
        """
        journal_entries = []

        for tx in transactions:
            rule_id, vendor_name, confidence = self.match_rule(tx)
            rule = self.rules.get(rule_id, {})

            amount = tx.get('deposit', 0) or tx.get('withdrawal', 0)

            entry = {
                'date': tx.get('date', ''),
                'description': tx.get('description', ''),
                'amount': amount,
                'rule_id': rule_id,
                'rule_name': rule.get('name', ''),
                'debit_account': rule.get('debit_account', ''),
                'debit_tax_category': rule.get('debit_tax_category', '対象外'),
                'credit_account': rule.get('credit_account', ''),
                'credit_tax_category': rule.get('credit_tax_category', '対象外'),
                'vendor_name': vendor_name,
                'confidence': confidence,
                'direction': tx.get('direction', ''),
                'needs_review': confidence < 0.7
            }

            journal_entries.append(entry)

        return journal_entries

    def import_from_csv(self, csv_path: Path, bank_type: str = 'aichi') -> Dict:
        """
        銀行CSVをインポートして仕訳データを生成

        Args:
            csv_path: CSVファイルのパス
            bank_type: 銀行種別

        Returns:
            {
                'transactions': [...],  # 元の取引データ
                'journal_entries': [...],  # 仕訳データ
                'summary': {
                    'total_count': 件数,
                    'deposit_count': 入金件数,
                    'withdrawal_count': 出金件数,
                    'needs_review_count': 要確認件数
                }
            }
        """
        transactions = self.parse_bank_csv(csv_path, bank_type)
        journal_entries = self.process_transactions(transactions)

        deposit_count = sum(1 for e in journal_entries if e['direction'] == 'deposit')
        withdrawal_count = sum(1 for e in journal_entries if e['direction'] == 'withdrawal')
        needs_review_count = sum(1 for e in journal_entries if e['needs_review'])

        return {
            'transactions': transactions,
            'journal_entries': journal_entries,
            'summary': {
                'total_count': len(journal_entries),
                'deposit_count': deposit_count,
                'withdrawal_count': withdrawal_count,
                'needs_review_count': needs_review_count
            }
        }
