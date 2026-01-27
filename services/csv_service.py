"""
CSV出力サービス
弥生会計インポート用CSV（CP932エンコーディング、25列形式）
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from io import StringIO

from .journal_service import JournalEntry


class CsvService:
    """弥生会計用CSV出力サービス"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self._slip_no_counter = 1

    def _format_date_yayoi(self, date_str: str) -> str:
        """
        日付を弥生会計形式に変換
        2025-12-01 → R.07/12/01
        """
        if not date_str:
            return ''

        try:
            if isinstance(date_str, datetime):
                dt = date_str
            else:
                dt = datetime.strptime(date_str, '%Y-%m-%d')

            # 令和に変換（令和元年 = 2019年）
            reiwa_year = dt.year - 2018
            return f"R.{reiwa_year:02d}/{dt.month:02d}/{dt.day:02d}"
        except:
            return date_str

    def _entry_to_yayoi_row(self, entry: Dict[str, Any], slip_no: int) -> List:
        """
        仕訳エントリを弥生会計25列形式に変換

        列の順序（添付CSVから解析）:
        0: 識別フラグ（2000固定）
        1: 伝票番号
        2: 決算（空白）
        3: 日付（R.07/12/01形式）
        4: 借方勘定科目
        5: 借方補助科目
        6: 借方部門（空白）
        7: 借方税区分
        8: 借方金額
        9: 借方消費税（0）
        10: 貸方勘定科目
        11: 貸方補助科目
        12: 貸方部門（空白）
        13: 貸方税区分
        14: 貸方金額
        15: 貸方消費税（0）
        16: 摘要
        17-19: 空白、0、空白
        20-22: 空白、0、0
        23: フラグ（no）
        """
        date_str = entry.get('date', '')
        yayoi_date = self._format_date_yayoi(date_str)

        return [
            '2000',                                      # 0: 識別フラグ
            str(slip_no),                                # 1: 伝票番号
            '',                                          # 2: 決算
            yayoi_date,                                  # 3: 日付
            entry.get('debit_account', ''),              # 4: 借方勘定科目
            entry.get('debit_sub_account', ''),          # 5: 借方補助科目
            '',                                          # 6: 借方部門
            entry.get('debit_tax_category', '対象外'),    # 7: 借方税区分
            str(entry.get('amount', 0)),                 # 8: 借方金額
            '0',                                         # 9: 借方消費税
            entry.get('credit_account', ''),             # 10: 貸方勘定科目
            entry.get('credit_sub_account', ''),         # 11: 貸方補助科目
            '',                                          # 12: 貸方部門
            entry.get('credit_tax_category', '対象外'),   # 13: 貸方税区分
            str(entry.get('amount', 0)),                 # 14: 貸方金額
            '0',                                         # 15: 貸方消費税
            entry.get('description', ''),                # 16: 摘要
            '',                                          # 17: 空白
            '',                                          # 18: 空白
            '0',                                         # 19: 調整額1
            '',                                          # 20: 空白
            '',                                          # 21: 空白
            '0',                                         # 22: 調整額2
            '0',                                         # 23: 調整額3
            'no'                                         # 24: フラグ
        ]

    def generate_yayoi_csv(
        self,
        entries: List[Dict[str, Any]],
        filename: Optional[str] = None,
        start_slip_no: int = 1
    ) -> Path:
        """
        仕訳エントリから弥生会計形式CSVファイルを生成（ヘッダーなし）

        Args:
            entries: 仕訳エントリのリスト
            filename: 出力ファイル名（指定なしの場合は日時で生成）
            start_slip_no: 開始伝票番号

        Returns:
            生成されたCSVファイルのパス
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'yayoi_{timestamp}.csv'

        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='cp932', newline='', errors='replace') as f:
            writer = csv.writer(f)

            # ヘッダーなしで直接データを出力
            for i, entry in enumerate(entries):
                slip_no = start_slip_no + i
                row = self._entry_to_yayoi_row(entry, slip_no)
                writer.writerow(row)

        return output_path

    def generate_yayoi_csv_bytes(
        self,
        entries: List[Dict[str, Any]],
        start_slip_no: int = 1
    ) -> bytes:
        """
        仕訳エントリから弥生会計形式CSVバイト列を生成（ダウンロード用）

        Args:
            entries: 仕訳エントリのリスト
            start_slip_no: 開始伝票番号

        Returns:
            CP932エンコードされたCSVバイト列
        """
        output = StringIO()
        writer = csv.writer(output)

        for i, entry in enumerate(entries):
            slip_no = start_slip_no + i
            row = self._entry_to_yayoi_row(entry, slip_no)
            writer.writerow(row)

        return output.getvalue().encode('cp932', errors='replace')

    # 以下は旧形式（互換性のため残す）

    # 弥生会計のCSVヘッダー（旧形式）
    HEADER_ROW1 = [
        '日付', '伝票No.', '決算', '調整', '付箋１', '付箋2', 'タイプ', '生成元',
        '', '', '', '', '借方', '', '', '',
        '', '', '', '', '貸方', '', '', '',
        '', '摘要', '請求書区分', '仕入税額控除', '期日', '番号', '仕訳メモ', '作業日付', '仕訳番号'
    ]

    HEADER_ROW2 = [
        '', '', '', '', '', '', '', '',
        '', '勘定科目', '補助科目', '部門', '税区分', '税計算区分', '金額', '消費税額',
        '', '勘定科目', '補助科目', '部門', '税区分', '税計算区分', '金額', '消費税額',
        '', '', '', '', '', '', '', '', ''
    ]

    def _format_date(self, dt: Optional[datetime]) -> str:
        """日付をフォーマット"""
        if dt is None:
            return ''
        return dt.strftime('%Y/%m/%d')

    def _entry_to_row(self, entry: JournalEntry) -> List:
        """仕訳エントリをCSV行に変換（旧形式）"""
        return [
            self._format_date(entry.date),
            entry.slip_no if entry.slip_no else '',
            entry.settlement,
            entry.adjustment,
            entry.label1,
            entry.label2,
            entry.entry_type,
            entry.source,
            '',  # 空欄
            entry.debit_account,
            entry.debit_sub_account,
            entry.debit_department,
            entry.debit_tax_category,
            entry.debit_tax_calc,
            entry.debit_amount if entry.debit_amount else '',
            entry.debit_tax_amount if entry.debit_tax_amount else '',
            '',  # 空欄
            entry.credit_account,
            entry.credit_sub_account,
            entry.credit_department,
            entry.credit_tax_category,
            entry.credit_tax_calc,
            entry.credit_amount if entry.credit_amount else '',
            entry.credit_tax_amount if entry.credit_tax_amount else '',
            '',  # 空欄
            entry.description,
            entry.invoice_category,
            entry.purchase_tax_deduction,
            self._format_date(entry.due_date) if entry.due_date else '',
            entry.number,
            entry.memo,
            self._format_date(entry.work_date),
            entry.journal_no if entry.journal_no else ''
        ]

    def generate_csv(
        self,
        entries: List[JournalEntry],
        filename: Optional[str] = None,
        include_header: bool = True
    ) -> Path:
        """
        仕訳エントリからCSVファイルを生成（旧形式）

        Args:
            entries: 仕訳エントリのリスト
            filename: 出力ファイル名（指定なしの場合は日時で生成）
            include_header: ヘッダー行を含めるか

        Returns:
            生成されたCSVファイルのパス
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'journal_{timestamp}.csv'

        output_path = self.output_dir / filename

        with open(output_path, 'w', encoding='cp932', newline='', errors='replace') as f:
            writer = csv.writer(f)

            if include_header:
                writer.writerow(self.HEADER_ROW1)
                writer.writerow(self.HEADER_ROW2)

            for entry in entries:
                row = self._entry_to_row(entry)
                writer.writerow(row)

        return output_path

    def generate_csv_string(
        self,
        entries: List[JournalEntry],
        include_header: bool = True
    ) -> str:
        """
        仕訳エントリからCSV文字列を生成（ダウンロード用）

        Args:
            entries: 仕訳エントリのリスト
            include_header: ヘッダー行を含めるか

        Returns:
            CSV形式の文字列
        """
        output = StringIO()
        writer = csv.writer(output)

        if include_header:
            writer.writerow(self.HEADER_ROW1)
            writer.writerow(self.HEADER_ROW2)

        for entry in entries:
            row = self._entry_to_row(entry)
            writer.writerow(row)

        return output.getvalue()

    def generate_csv_bytes(
        self,
        entries: List[JournalEntry],
        include_header: bool = True
    ) -> bytes:
        """
        仕訳エントリからCSVバイト列を生成（ダウンロード用、CP932エンコード）

        Args:
            entries: 仕訳エントリのリスト
            include_header: ヘッダー行を含めるか

        Returns:
            CP932エンコードされたCSVバイト列
        """
        csv_string = self.generate_csv_string(entries, include_header)
        return csv_string.encode('cp932', errors='replace')

    def validate_entry(self, entry: JournalEntry) -> List[str]:
        """
        仕訳エントリのバリデーション

        Returns:
            エラーメッセージのリスト（空なら問題なし）
        """
        errors = []

        if not entry.date:
            errors.append('日付が設定されていません')

        if not entry.debit_account:
            errors.append('借方勘定科目が設定されていません')

        if not entry.credit_account:
            errors.append('貸方勘定科目が設定されていません')

        if entry.debit_amount <= 0:
            errors.append('借方金額が不正です')

        if entry.credit_amount <= 0:
            errors.append('貸方金額が不正です')

        if entry.debit_amount != entry.credit_amount:
            errors.append('借方金額と貸方金額が一致しません')

        return errors
