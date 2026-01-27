"""
マスタデータ管理サービス
取引先、銀行口座、仕訳ルールのCRUD操作
"""
import json
from pathlib import Path
from typing import Dict, List, Optional


class MasterService:
    """マスタデータ管理サービス"""

    def __init__(self, master_data_dir: Path):
        self.master_data_dir = master_data_dir
        self._load_all()

    def _load_all(self):
        """全マスタデータを読み込み"""
        self._load_vendors()
        self._load_banks()
        self._load_rules()
        self._load_clients()

    def _load_vendors(self):
        """取引先マスタを読み込み"""
        path = self.master_data_dir / 'vendors.json'
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.vendors = data.get('vendors', [])

    def _load_banks(self):
        """銀行マスタを読み込み"""
        path = self.master_data_dir / 'banks.json'
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.banks = data.get('banks', [])
        self.default_bank = data.get('default_bank', '')

    def _load_rules(self):
        """仕訳ルールを読み込み"""
        path = self.master_data_dir / 'journal_rules.json'
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.rules = data.get('rules', [])

    def _load_clients(self):
        """クライアント設定を読み込み"""
        path = self.master_data_dir / 'clients.json'
        with open(path, 'r', encoding='utf-8') as f:
            self.clients = json.load(f)

    def _save_vendors(self):
        """取引先マスタを保存"""
        path = self.master_data_dir / 'vendors.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'vendors': self.vendors}, f, ensure_ascii=False, indent=2)

    def _save_banks(self):
        """銀行マスタを保存"""
        path = self.master_data_dir / 'banks.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'banks': self.banks,
                'default_bank': self.default_bank
            }, f, ensure_ascii=False, indent=2)

    # ====== 取引先マスタ操作 ======

    def get_vendors(self, vendor_type: Optional[str] = None) -> List[Dict]:
        """取引先一覧を取得"""
        if vendor_type:
            return [v for v in self.vendors if v.get('type') == vendor_type]
        return self.vendors

    def get_vendor(self, vendor_id: str) -> Optional[Dict]:
        """取引先を取得"""
        for v in self.vendors:
            if v.get('id') == vendor_id:
                return v
        return None

    def get_vendor_by_name(self, name: str) -> Optional[Dict]:
        """取引先を名前で取得"""
        for v in self.vendors:
            if v.get('name') == name:
                return v
        return None

    def add_vendor(self, vendor: Dict) -> bool:
        """取引先を追加"""
        if self.get_vendor(vendor.get('id', '')):
            return False
        self.vendors.append(vendor)
        self._save_vendors()
        return True

    def update_vendor(self, vendor_id: str, data: Dict) -> bool:
        """取引先を更新"""
        for i, v in enumerate(self.vendors):
            if v.get('id') == vendor_id:
                self.vendors[i].update(data)
                self._save_vendors()
                return True
        return False

    def delete_vendor(self, vendor_id: str) -> bool:
        """取引先を削除"""
        for i, v in enumerate(self.vendors):
            if v.get('id') == vendor_id:
                del self.vendors[i]
                self._save_vendors()
                return True
        return False

    # ====== 銀行マスタ操作 ======

    def get_banks(self) -> List[Dict]:
        """銀行一覧を取得"""
        return self.banks

    def get_bank(self, bank_id: str) -> Optional[Dict]:
        """銀行を取得"""
        for b in self.banks:
            if b.get('id') == bank_id:
                return b
        return None

    def add_bank(self, bank: Dict) -> bool:
        """銀行を追加"""
        if self.get_bank(bank.get('id', '')):
            return False
        self.banks.append(bank)
        self._save_banks()
        return True

    def set_default_bank(self, bank_id: str) -> bool:
        """デフォルト銀行を設定"""
        if self.get_bank(bank_id):
            self.default_bank = bank_id
            self._save_banks()
            return True
        return False

    # ====== 仕訳ルール操作 ======

    def get_rules(self) -> List[Dict]:
        """仕訳ルール一覧を取得"""
        return self.rules

    def get_rule(self, rule_id: str) -> Optional[Dict]:
        """仕訳ルールを取得"""
        for r in self.rules:
            if r.get('id') == rule_id:
                return r
        return None

    # ====== クライアント設定 ======

    def get_group_companies(self) -> List[str]:
        """グループ会社一覧を取得"""
        return self.clients.get('company_info', {}).get('group_companies', [])

    def is_group_company(self, company_name: str) -> bool:
        """グループ会社かどうか判定"""
        group_companies = self.get_group_companies()
        for gc in group_companies:
            if gc in company_name:
                return True
        return False

    # ====== 検索・マッチング ======

    def find_vendor_by_partial_name(self, partial_name: str) -> Optional[Dict]:
        """部分一致で取引先を検索"""
        for v in self.vendors:
            if partial_name in v.get('name', ''):
                return v
            if partial_name in v.get('sub_account', ''):
                return v
        return None

    def suggest_journal_rule(self, vendor_name: str, description: str = '') -> Optional[str]:
        """
        取引先名と摘要から仕訳ルールを推測
        """
        vendor = self.get_vendor_by_name(vendor_name)
        if vendor:
            return vendor.get('default_rule')

        # 摘要からの推測
        keywords_rules = {
            '外注': 'outsourcing_expense',
            '家賃': 'land_rent',
            '賃料': 'rent',
            '保険': 'insurance',
            '通信': 'communication',
            '旅費': 'travel_expense',
            '交通': 'travel_expense',
            '消耗品': 'consumables',
            '仕入': 'purchase',
            '売上': 'sales_receivable',
            '入金': 'payment_received'
        }

        for keyword, rule_id in keywords_rules.items():
            if keyword in description:
                return rule_id

        return None

    def get_all_sub_accounts(self) -> Dict[str, List[str]]:
        """全ての補助科目を勘定科目別に取得"""
        result = {
            '売掛金': [],
            '買掛金': [],
            '普通預金': [],
            '売上高': [],
            '仕入高': []
        }

        # 取引先から売掛金・買掛金の補助科目
        for v in self.vendors:
            sub = v.get('sub_account', '')
            if v.get('type') == 'client':
                if sub not in result['売掛金']:
                    result['売掛金'].append(sub)
                if sub not in result['売上高']:
                    result['売上高'].append(sub)
            elif v.get('type') == 'supplier':
                if sub not in result['買掛金']:
                    result['買掛金'].append(sub)
                if sub not in result['仕入高']:
                    result['仕入高'].append(sub)

        # 銀行から普通預金の補助科目
        for b in self.banks:
            sub = b.get('sub_account', '')
            if sub not in result['普通預金']:
                result['普通預金'].append(sub)

        return result
