"""
仕訳履歴管理サービス
仕訳の作成・出力履歴を記録し、トレーサビリティを提供
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class HistoryService:
    """仕訳履歴管理サービス"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.history_file = data_dir / 'journal_history.json'
        self._ensure_file()

    def _ensure_file(self):
        """履歴ファイルが存在しない場合は作成"""
        if not self.history_file.exists():
            self._save_data({
                'entries': [],
                'exports': []
            })

    def _load_data(self) -> Dict:
        """履歴データを読み込み"""
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {'entries': [], 'exports': []}

    def _save_data(self, data: Dict):
        """履歴データを保存"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_entry(
        self,
        entry: Dict[str, Any],
        source_file: Optional[str] = None,
        source_type: str = 'manual',
        learning_applied: bool = False
    ) -> str:
        """
        仕訳エントリを履歴に追加

        Args:
            entry: 仕訳データ
            source_file: 元ファイル名
            source_type: 'ocr_batch', 'ocr_single', 'manual', 'sales', 'purchase', 'payment'
            learning_applied: 学習データが適用されたか

        Returns:
            生成されたエントリID
        """
        data = self._load_data()

        entry_id = str(uuid.uuid4())
        history_entry = {
            'id': entry_id,
            'created_at': datetime.now().isoformat(),
            'source_file': source_file,
            'source_type': source_type,
            'entry': entry,
            'learning_applied': learning_applied,
            'exported': False,
            'exported_at': None,
            'export_id': None
        }

        data['entries'].append(history_entry)
        self._save_data(data)

        return entry_id

    def add_entries_batch(
        self,
        entries: List[Dict[str, Any]],
        source_files: Optional[List[str]] = None,
        source_type: str = 'ocr_batch',
        learning_applied_flags: Optional[List[bool]] = None
    ) -> List[str]:
        """
        複数の仕訳エントリを一括で履歴に追加

        Returns:
            生成されたエントリIDのリスト
        """
        data = self._load_data()
        entry_ids = []

        for i, entry in enumerate(entries):
            entry_id = str(uuid.uuid4())
            source_file = source_files[i] if source_files and i < len(source_files) else None
            learning_applied = learning_applied_flags[i] if learning_applied_flags and i < len(learning_applied_flags) else False

            history_entry = {
                'id': entry_id,
                'created_at': datetime.now().isoformat(),
                'source_file': source_file,
                'source_type': source_type,
                'entry': entry,
                'learning_applied': learning_applied,
                'exported': False,
                'exported_at': None,
                'export_id': None
            }

            data['entries'].append(history_entry)
            entry_ids.append(entry_id)

        self._save_data(data)
        return entry_ids

    def record_export(
        self,
        filename: str,
        entry_ids: List[str]
    ) -> str:
        """
        CSV出力を履歴に記録

        Args:
            filename: 出力ファイル名
            entry_ids: 出力した仕訳エントリのIDリスト

        Returns:
            出力履歴ID
        """
        data = self._load_data()

        export_id = str(uuid.uuid4())
        export_time = datetime.now().isoformat()

        export_record = {
            'id': export_id,
            'exported_at': export_time,
            'filename': filename,
            'entry_count': len(entry_ids),
            'entry_ids': entry_ids
        }

        data['exports'].append(export_record)

        # 各エントリの出力フラグを更新
        for entry in data['entries']:
            if entry['id'] in entry_ids:
                entry['exported'] = True
                entry['exported_at'] = export_time
                entry['export_id'] = export_id

        self._save_data(data)
        return export_id

    def get_entries(
        self,
        limit: int = 100,
        offset: int = 0,
        exported: Optional[bool] = None,
        source_type: Optional[str] = None
    ) -> List[Dict]:
        """
        仕訳履歴を取得

        Args:
            limit: 取得件数
            offset: オフセット
            exported: True=出力済みのみ, False=未出力のみ, None=全て
            source_type: フィルタするソースタイプ

        Returns:
            履歴エントリのリスト
        """
        data = self._load_data()
        entries = data['entries']

        # フィルタリング
        if exported is not None:
            entries = [e for e in entries if e['exported'] == exported]

        if source_type is not None:
            entries = [e for e in entries if e['source_type'] == source_type]

        # 新しい順にソート
        entries = sorted(entries, key=lambda x: x['created_at'], reverse=True)

        # ページネーション
        return entries[offset:offset + limit]

    def get_exports(self, limit: int = 50) -> List[Dict]:
        """
        CSV出力履歴を取得

        Returns:
            出力履歴のリスト（新しい順）
        """
        data = self._load_data()
        exports = data['exports']
        return sorted(exports, key=lambda x: x['exported_at'], reverse=True)[:limit]

    def get_entry_by_id(self, entry_id: str) -> Optional[Dict]:
        """IDで仕訳エントリを取得"""
        data = self._load_data()
        for entry in data['entries']:
            if entry['id'] == entry_id:
                return entry
        return None

    def get_export_by_id(self, export_id: str) -> Optional[Dict]:
        """IDで出力履歴を取得"""
        data = self._load_data()
        for export in data['exports']:
            if export['id'] == export_id:
                return export
        return None

    def get_entries_by_source_file(self, source_file: str) -> List[Dict]:
        """ソースファイル名で仕訳を検索"""
        data = self._load_data()
        return [e for e in data['entries'] if e['source_file'] == source_file]

    def get_stats(self) -> Dict:
        """
        履歴の統計情報を取得

        Returns:
            {
                'total_entries': 総仕訳数,
                'exported_entries': 出力済み仕訳数,
                'unexported_entries': 未出力仕訳数,
                'total_exports': 出力回数,
                'entries_by_source_type': {'ocr_batch': 10, 'manual': 5, ...}
            }
        """
        data = self._load_data()
        entries = data['entries']
        exports = data['exports']

        exported_count = sum(1 for e in entries if e['exported'])

        # ソースタイプ別集計
        by_source_type = {}
        for entry in entries:
            st = entry['source_type']
            by_source_type[st] = by_source_type.get(st, 0) + 1

        return {
            'total_entries': len(entries),
            'exported_entries': exported_count,
            'unexported_entries': len(entries) - exported_count,
            'total_exports': len(exports),
            'entries_by_source_type': by_source_type
        }

    def delete_entry(self, entry_id: str) -> bool:
        """仕訳エントリを削除"""
        data = self._load_data()
        original_len = len(data['entries'])
        data['entries'] = [e for e in data['entries'] if e['id'] != entry_id]

        if len(data['entries']) < original_len:
            self._save_data(data)
            return True
        return False

    def clear_unexported(self) -> int:
        """未出力の仕訳を全て削除"""
        data = self._load_data()
        original_len = len(data['entries'])
        data['entries'] = [e for e in data['entries'] if e['exported']]
        deleted_count = original_len - len(data['entries'])

        if deleted_count > 0:
            self._save_data(data)
        return deleted_count
