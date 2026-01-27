"""
仕訳生成サービス
過去データから抽出した全仕訳パターンに対応
"""
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path

from config.companies import is_group_company


@dataclass
class JournalEntry:
    """仕訳エントリ"""
    date: datetime
    slip_no: int = 0
    settlement: str = ''
    adjustment: str = 'NO'
    label1: str = ''
    label2: str = ''
    entry_type: str = ''
    source: str = ''

    # 借方
    debit_account: str = ''
    debit_sub_account: str = ''
    debit_department: str = ''
    debit_tax_category: str = '対象外'
    debit_tax_calc: str = ''
    debit_amount: int = 0
    debit_tax_amount: int = 0

    # 貸方
    credit_account: str = ''
    credit_sub_account: str = ''
    credit_department: str = ''
    credit_tax_category: str = '対象外'
    credit_tax_calc: str = ''
    credit_amount: int = 0
    credit_tax_amount: int = 0

    # その他
    description: str = ''
    invoice_category: str = ''
    purchase_tax_deduction: str = ''
    due_date: Optional[datetime] = None
    number: str = ''
    memo: str = ''
    work_date: Optional[datetime] = None
    journal_no: int = 0


class JournalService:
    """仕訳生成サービス"""

    def __init__(self, master_data_dir: Path):
        self.master_data_dir = master_data_dir
        self._load_rules()
        self._load_vendors()
        self._load_banks()
        self._slip_counter = 1
        self._journal_counter = 1

    def _load_rules(self):
        """仕訳ルールを読み込み"""
        rules_path = self.master_data_dir / 'journal_rules.json'
        with open(rules_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.rules = {r['id']: r for r in data['rules']}

    def _load_vendors(self):
        """取引先マスタを読み込み"""
        vendors_path = self.master_data_dir / 'vendors.json'
        with open(vendors_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.vendors = {v['name']: v for v in data['vendors']}

    def _load_banks(self):
        """銀行マスタを読み込み"""
        banks_path = self.master_data_dir / 'banks.json'
        with open(banks_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.banks = {b['id']: b for b in data['banks']}
        self.default_bank = data.get('default_bank', 'aichi_kasugai')

    def get_next_slip_no(self) -> int:
        """次の伝票番号を取得"""
        no = self._slip_counter
        self._slip_counter += 1
        return no

    def get_next_journal_no(self) -> int:
        """次の仕訳番号を取得"""
        no = self._journal_counter
        self._journal_counter += 1
        return no

    def create_sales_entry(
        self,
        date: datetime,
        vendor_name: str,
        amount: int,
        description: str,
        sales_type: str = 'sales_receivable'
    ) -> JournalEntry:
        """
        売上計上の仕訳を生成
        借方: 売掛金（対象外） / 貸方: 売上高（簡売五10%または課税売上10%）
        """
        rule = self.rules.get(sales_type, self.rules['sales_receivable'])
        vendor = self.vendors.get(vendor_name, {'sub_account': vendor_name})

        # 借方税区分: 対象外
        debit_tax = rule.get('debit_tax_category', '対象外')
        # 貸方税区分: 取引先のsales_tax_typeを優先、なければルールのcredit_tax_category
        credit_tax = vendor.get('sales_tax_type', rule.get('credit_tax_category', '簡売五10%'))

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account=vendor.get('sub_account', vendor_name),
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account=vendor.get('sub_account', vendor_name),
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_payment_received_entry(
        self,
        date: datetime,
        vendor_name: str,
        amount: int,
        description: str,
        bank_id: Optional[str] = None
    ) -> JournalEntry:
        """
        入金処理の仕訳を生成
        借方: 普通預金（対象外） / 貸方: 売掛金（対象外）
        """
        rule = self.rules['payment_received']
        vendor = self.vendors.get(vendor_name, {'sub_account': vendor_name})
        bank = self.banks.get(bank_id or self.default_bank, {})

        # 借方/貸方とも対象外
        debit_tax = rule.get('debit_tax_category', '対象外')
        credit_tax = rule.get('credit_tax_category', '対象外')

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account=bank.get('sub_account', ''),
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account=vendor.get('sub_account', vendor_name),
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_purchase_entry(
        self,
        date: datetime,
        vendor_name: str,
        amount: int,
        description: str,
        purchase_type: str = 'purchase'
    ) -> JournalEntry:
        """
        仕入計上の仕訳を生成
        借方: 仕入高（課対仕入10%） / 貸方: 買掛金（対象外）
        """
        rule = self.rules.get(purchase_type, self.rules['purchase'])
        vendor = self.vendors.get(vendor_name, {'sub_account': vendor_name})

        # 借方: 課対仕入10%、貸方: 対象外
        debit_tax = rule.get('debit_tax_category', '課対仕入10%')
        credit_tax = rule.get('credit_tax_category', '対象外')

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account='',
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account=vendor.get('sub_account', vendor_name),
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_purchase_payment_entry(
        self,
        date: datetime,
        vendor_name: str,
        amount: int,
        description: str,
        bank_id: Optional[str] = None
    ) -> JournalEntry:
        """
        買掛金支払の仕訳を生成
        借方: 買掛金（対象外） / 貸方: 普通預金（対象外）
        """
        rule = self.rules['purchase_payment']
        vendor = self.vendors.get(vendor_name, {'sub_account': vendor_name})
        bank = self.banks.get(bank_id or self.default_bank, {})

        # 借方/貸方とも対象外
        debit_tax = rule.get('debit_tax_category', '対象外')
        credit_tax = rule.get('credit_tax_category', '対象外')

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account=vendor.get('sub_account', vendor_name),
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account=bank.get('sub_account', ''),
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_expense_entry(
        self,
        date: datetime,
        expense_type: str,
        amount: int,
        description: str,
        vendor_name: str = '',
        bank_id: Optional[str] = None,
        payment_method: str = 'bank'  # 'bank', 'cash', 'unpaid'
    ) -> JournalEntry:
        """
        経費の仕訳を生成
        借方: 経費科目（課対仕入10%） / 貸方: 現金/普通預金/未払金（対象外）
        """
        rule = self.rules.get(expense_type, self.rules['miscellaneous'])

        # 借方税区分: ルールから取得（課対仕入10%など）
        debit_tax = rule.get('debit_tax_category', '課対仕入10%')

        # 貸方の決定
        if payment_method == 'cash':
            credit_account = '現金'
            credit_sub = ''
        elif payment_method == 'unpaid':
            credit_account = '未払金'
            credit_sub = vendor_name
        else:
            credit_account = '普通預金'
            bank = self.banks.get(bank_id or self.default_bank, {})
            credit_sub = bank.get('sub_account', '')

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account='',
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=credit_account,
            credit_sub_account=credit_sub,
            credit_tax_category='対象外',
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_advance_received_entry(
        self,
        date: datetime,
        vendor_name: str,
        amount: int,
        description: str
    ) -> JournalEntry:
        """
        前受金振替の仕訳を生成
        借方: 前受収益（対象外） / 貸方: 売上高（簡売五10%）
        """
        rule = self.rules['advance_received_transfer']
        vendor = self.vendors.get(vendor_name, {})

        # 借方: 対象外、貸方: 取引先のsales_tax_typeまたはルールのcredit_tax_category
        debit_tax = rule.get('debit_tax_category', '対象外')
        credit_tax = vendor.get('sales_tax_type', rule.get('credit_tax_category', '簡売五10%'))

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account='',
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account='',
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_temporary_received_entry(
        self,
        date: datetime,
        amount: int,
        description: str,
        bank_id: Optional[str] = None
    ) -> JournalEntry:
        """
        仮受金計上の仕訳を生成
        借方: 普通預金（対象外） / 貸方: 仮受金（対象外）
        """
        rule = self.rules['temporary_received']
        bank = self.banks.get(bank_id or self.default_bank, {})

        # 借方/貸方とも対象外
        debit_tax = rule.get('debit_tax_category', '対象外')
        credit_tax = rule.get('credit_tax_category', '対象外')

        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=rule['debit_account'],
            debit_sub_account=bank.get('sub_account', ''),
            debit_tax_category=debit_tax,
            debit_amount=amount,
            credit_account=rule['credit_account'],
            credit_sub_account='',
            credit_tax_category=credit_tax,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    def create_custom_entry(
        self,
        date: datetime,
        debit_account: str,
        debit_sub_account: str,
        credit_account: str,
        credit_sub_account: str,
        amount: int,
        description: str,
        debit_tax_category: str = '対象外',
        credit_tax_category: str = '対象外'
    ) -> JournalEntry:
        """
        カスタム仕訳を生成
        """
        entry = JournalEntry(
            date=date,
            slip_no=self.get_next_slip_no(),
            adjustment='NO',
            debit_account=debit_account,
            debit_sub_account=debit_sub_account,
            debit_tax_category=debit_tax_category,
            debit_amount=amount,
            credit_account=credit_account,
            credit_sub_account=credit_sub_account,
            credit_tax_category=credit_tax_category,
            credit_amount=amount,
            description=description,
            work_date=datetime.now(),
            journal_no=self.get_next_journal_no()
        )
        return entry

    # 摘要キーワードからルールIDへのマッピング
    DESCRIPTION_KEYWORDS = {
        # 経費系
        'rent': ['リース', 'PCリース', 'レンタル', 'コピー機'],
        'land_rent': ['賃料', '家賃', '地代', '共益費', '管理費'],
        'outsourcing_expense': ['業務支援', '業務委託', '外注', '人件費', '派遣'],
        'travel_expense': ['出張', '精算', '旅費', '交通費', '新幹線', '宿泊'],
        'welfare_expense': ['慶祝金', '弔慰金', '見舞金', '祝金', '福利'],
        'miscellaneous': ['廃棄物', '清掃', '処理費'],
        'utilities': ['電気', '水道', '光熱', 'ガス'],
        'advertising': ['パンフレット', '印刷', '広告', '看板', 'チラシ', 'ポスター'],
        'consumables': ['備品', '消耗品', '文具', '事務用品'],
        'communication_expense': ['電話', '通信', 'NTT', 'ドコモ'],
        'insurance': ['保険', '損保', '生保'],
        'vehicle_expense': ['車両', '自動車', 'ガソリン', '燃料', '駐車'],
        # 銀行取引系
        'bank_fee': ['振込手数料', '手数料', 'テスウリヨウ'],
        'corporate_tax_payment': ['法人税', '住民税', '事業税', '国税', '地方税'],
        'consumption_tax_payment': ['消費税'],
        'salary_payment': ['給与', '給料', '賃金'],
        'social_insurance_payment': ['社会保険', '健康保険', '厚生年金', '年金', '労働保険'],
        'long_term_loan': ['借入返済', '長期借入', 'ローン返済'],
        'interest_expense': ['利息', '金利'],
        # 売上系
        'sales_receivable': ['経営指導料', '指導料', 'コンサルティング', '業務委託料'],
    }

    def match_rule_by_description(self, description: str, invoice_type: str = 'purchase') -> str:
        """
        摘要から仕訳ルールをマッチング

        Args:
            description: 摘要テキスト
            invoice_type: 'sales' or 'purchase'

        Returns:
            rule_id
        """
        description_lower = description.lower() if description else ''

        # キーワードマッチング
        for rule_id, keywords in self.DESCRIPTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in description or keyword.lower() in description_lower:
                    return rule_id

        # デフォルト
        if invoice_type == 'sales':
            return 'sales_receivable'
        else:
            return 'purchase'

    def determine_journal_type(self, invoice_data: Dict) -> str:
        """
        請求書データから仕訳タイプを判定
        """
        issuer = invoice_data.get('issuer', '')
        recipient = invoice_data.get('recipient', '')

        # 発行元が自社グループ → 売上（売掛金計上）
        if is_group_company(issuer):
            return 'sales'

        # 宛先が自社グループ → 仕入（買掛金計上）
        if is_group_company(recipient):
            return 'purchase'

        # デフォルトは買掛金
        return 'purchase'

    def generate_from_invoice(self, invoice_data: Dict) -> List[JournalEntry]:
        """
        請求書データから仕訳を生成
        """
        entries = []

        journal_type = self.determine_journal_type(invoice_data)
        date = invoice_data.get('date', datetime.now())
        if isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d')

        vendor_name = invoice_data.get('vendor_name', '')
        amount = invoice_data.get('amount', 0)
        description = invoice_data.get('description', '')

        if journal_type == 'sales':
            entry = self.create_sales_entry(
                date=date,
                vendor_name=vendor_name,
                amount=amount,
                description=description
            )
        else:
            entry = self.create_purchase_entry(
                date=date,
                vendor_name=vendor_name,
                amount=amount,
                description=description
            )

        entries.append(entry)
        return entries
