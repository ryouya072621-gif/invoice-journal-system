"""
学習サービス
OCR結果の修正を学習し、次回から自動適用
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class LearningService:
    """OCR修正の学習サービス"""

    def __init__(self, master_data_dir: Path):
        self.master_data_dir = master_data_dir
        self.corrections_path = master_data_dir / 'corrections.json'
        self._load_corrections()

    def _load_corrections(self):
        """学習データを読み込み"""
        if self.corrections_path.exists():
            with open(self.corrections_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.corrections = data.get('corrections', [])
        else:
            self.corrections = []

    def _save_corrections(self):
        """学習データを保存"""
        data = {
            'corrections': self.corrections,
            'updated_at': datetime.now().isoformat()
        }
        with open(self.corrections_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_correction(self, original: Dict, corrected: Dict) -> bool:
        """
        修正内容を学習データとして保存

        Args:
            original: OCRの元データ
            corrected: ユーザーが修正したデータ

        Returns:
            保存成功かどうか
        """
        # パターンを生成
        pattern = self._create_pattern(original)

        # 修正内容を抽出
        correction = {
            'debit_account': corrected.get('debit_account', ''),
            'debit_sub_account': corrected.get('debit_sub_account', ''),
            'debit_tax_category': corrected.get('debit_tax_category', '対象外'),
            'credit_account': corrected.get('credit_account', ''),
            'credit_sub_account': corrected.get('credit_sub_account', ''),
            'credit_tax_category': corrected.get('credit_tax_category', '対象外'),
            'invoice_type': corrected.get('invoice_type', 'purchase')
        }

        # 既存のパターンを検索
        existing_idx = self._find_matching_pattern_index(pattern)

        if existing_idx is not None:
            # 既存パターンを更新
            self.corrections[existing_idx]['correction'] = correction
            self.corrections[existing_idx]['count'] += 1
            self.corrections[existing_idx]['updated_at'] = datetime.now().isoformat()
        else:
            # 新規パターンを追加
            self.corrections.append({
                'pattern': pattern,
                'correction': correction,
                'count': 1,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            })

        self._save_corrections()
        return True

    def _create_pattern(self, ocr_data: Dict) -> Dict:
        """OCRデータからマッチングパターンを生成"""
        pattern = {}

        # 発行元（最優先）
        issuer = ocr_data.get('issuer', '').strip()
        if issuer:
            pattern['issuer'] = issuer

        # 宛先
        recipient = ocr_data.get('recipient', '').strip()
        if recipient:
            pattern['recipient'] = recipient

        # 摘要のキーワード
        description = ocr_data.get('description', '').strip()
        if description:
            pattern['description_contains'] = description

        return pattern

    def _find_matching_pattern_index(self, pattern: Dict) -> Optional[int]:
        """パターンが既存データに存在するか検索"""
        for idx, item in enumerate(self.corrections):
            existing_pattern = item['pattern']

            # 発行元が一致
            if pattern.get('issuer') and existing_pattern.get('issuer'):
                if pattern['issuer'] == existing_pattern['issuer']:
                    return idx

        return None

    def find_matching_correction(self, ocr_data: Dict) -> Optional[Dict]:
        """
        OCRデータに適用可能な学習データを検索

        Args:
            ocr_data: OCR結果

        Returns:
            マッチした修正データ、なければNone
        """
        issuer = ocr_data.get('issuer', '').strip()
        recipient = ocr_data.get('recipient', '').strip()
        description = ocr_data.get('description', '').strip()

        best_match = None
        best_score = 0

        for item in self.corrections:
            pattern = item['pattern']
            score = 0

            # 発行元完全一致（最高優先度）
            if pattern.get('issuer') and issuer:
                if pattern['issuer'] == issuer:
                    score += 100
                elif pattern['issuer'] in issuer or issuer in pattern['issuer']:
                    score += 50

            # 宛先一致
            if pattern.get('recipient') and recipient:
                if pattern['recipient'] == recipient:
                    score += 30
                elif pattern['recipient'] in recipient or recipient in pattern['recipient']:
                    score += 15

            # 摘要キーワード一致
            if pattern.get('description_contains') and description:
                if pattern['description_contains'] in description:
                    score += 20

            # 使用回数ボーナス（よく使われるパターンを優先）
            score += min(item.get('count', 0), 10)

            if score > best_score:
                best_score = score
                best_match = item

        # スコアが50以上の場合のみマッチとみなす
        if best_score >= 50:
            return best_match

        return None

    def apply_correction(self, ocr_data: Dict, correction: Dict) -> Dict:
        """
        学習データをOCR結果に適用

        Args:
            ocr_data: OCR結果
            correction: 適用する修正データ

        Returns:
            修正適用後のデータ
        """
        result = ocr_data.copy()

        # 修正を適用
        corr = correction.get('correction', {})

        if corr.get('debit_account'):
            result['suggested_debit_account'] = corr['debit_account']
        if corr.get('debit_sub_account'):
            result['suggested_debit_sub_account'] = corr['debit_sub_account']
        if corr.get('debit_tax_category'):
            result['suggested_debit_tax_category'] = corr['debit_tax_category']
        if corr.get('credit_account'):
            result['suggested_credit_account'] = corr['credit_account']
        if corr.get('credit_sub_account'):
            result['suggested_credit_sub_account'] = corr['credit_sub_account']
        if corr.get('credit_tax_category'):
            result['suggested_credit_tax_category'] = corr['credit_tax_category']
        if corr.get('invoice_type'):
            result['invoice_type'] = corr['invoice_type']

        result['learning_applied'] = True
        result['learning_pattern'] = correction.get('pattern', {})
        result['learning_count'] = correction.get('count', 0)

        return result

    def get_all_corrections(self) -> List[Dict]:
        """全ての学習データを取得"""
        return self.corrections

    def delete_correction(self, index: int) -> bool:
        """学習データを削除"""
        if 0 <= index < len(self.corrections):
            del self.corrections[index]
            self._save_corrections()
            return True
        return False

    def clear_all_corrections(self) -> bool:
        """全ての学習データをクリア"""
        self.corrections = []
        self._save_corrections()
        return True
