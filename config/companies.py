"""
グループ会社マスタ
OCRサービスとジャーナルサービスで共有
"""

# グループ会社リスト
# 正式名称とエイリアス（略称・別表記）を管理
GROUP_COMPANIES = [
    # 株式会社
    {'name': '株式会社ＳＯＫＵＴＡ', 'aliases': ['SOKUTA', 'ソクタ']},
    {'name': '株式会社白', 'aliases': []},
    {'name': '株式会社ソーコー', 'aliases': ['ソーコー']},
    {'name': '株式会社有馬', 'aliases': ['有馬']},
    {'name': '株式会社ケイ', 'aliases': []},
    {'name': '株式会社ＫＵＲＵＭＩ', 'aliases': ['KURUMI', 'クルミ']},
    {'name': '株式会社カーリー', 'aliases': ['カーリー']},
    {'name': '株式会社ヒロ', 'aliases': []},
    {'name': '株式会社リクル', 'aliases': ['リクル']},
    {'name': '株式会社医療白人', 'aliases': ['医療白人']},
    {'name': '株式会社sakura design', 'aliases': ['sakuradesign', 'サクラデザイン']},
    {'name': '株式会社ノーブ', 'aliases': ['ノーブ']},
    {'name': '株式会社ヒーロ', 'aliases': ['ヒーロ']},
    {'name': '株式会社岩田', 'aliases': ['岩田']},
    {'name': '株式会社デンサポ', 'aliases': ['デンサポ']},
    {'name': '株式会社エナックス', 'aliases': ['エナックス']},

    # 合同会社
    {'name': '合同会社モト', 'aliases': ['モト']},
    {'name': '合同会社ユース', 'aliases': ['ユース']},
    {'name': '合同会社コーシ', 'aliases': ['コーシ']},
    {'name': '合同会社マツクボ', 'aliases': ['マツクボ']},
    {'name': '合同会社エディプラス', 'aliases': ['エディプラス']},
    {'name': '合同会社日本水販売', 'aliases': ['日本水販売']},
    {'name': '合同会社ハピネスユウ', 'aliases': ['ハピネスユウ']},

    # ホールディングス・コンサル
    {'name': 'サンポウヨシホールディングス株式会社', 'aliases': ['サンポウヨシホールディングス', 'サンポウHD', 'サンポウ']},
    {'name': 'コンゲン人事株式会社', 'aliases': ['コンゲン人事']},
    {'name': 'M&Aプランナー株式会社', 'aliases': ['M&Aプランナー']},
    {'name': 'コンゲンデンタル株式会社', 'aliases': ['コンゲンデンタル', 'コンゲン']},

    # 不動産
    {'name': 'トリプルウィン不動産株式会社', 'aliases': ['トリプルウィン不動産', 'トリプルウィン']},

    # 医療法人
    {'name': '医療法人日本口腔ケア学会医療部門', 'aliases': ['日本口腔ケア学会', '口腔ケア']},
    {'name': '医療法人さくら会', 'aliases': ['さくら会']},
    {'name': '医療法人ハピネス', 'aliases': ['ハピネス']},
    {'name': '医療法人社団スマイル会', 'aliases': ['スマイル会']},
    {'name': '医療法人浩蘭会', 'aliases': ['浩蘭会']},
    {'name': '医療法人仁鈴会', 'aliases': ['仁鈴会']},
    {'name': '医療法人MOO', 'aliases': ['MOO']},

    # 一般社団法人・海外
    {'name': '一般社団法人中京医療情報発信センター', 'aliases': ['中京医療情報発信センター']},
    {'name': 'VJCONSUL CO LTD', 'aliases': ['VJCONSUL']},
]


def is_group_company(text: str) -> bool:
    """
    テキストがグループ会社かどうかを判定

    Args:
        text: 判定するテキスト（会社名）

    Returns:
        グループ会社ならTrue
    """
    if not text:
        return False

    text = text.strip()

    for company in GROUP_COMPANIES:
        # 正式名称との完全一致
        if company['name'] == text:
            return True

        # 正式名称が含まれている（部分一致）
        if company['name'] in text or text in company['name']:
            return True

        # エイリアスとの一致
        for alias in company['aliases']:
            if alias == text or alias in text or text in alias:
                return True

    return False


def get_group_company_list() -> list:
    """
    旧形式のグループ会社リストを取得（後方互換性のため）

    Returns:
        全ての会社名とエイリアスを含むフラットなリスト
    """
    result = []
    for company in GROUP_COMPANIES:
        result.append(company['name'])
        result.extend(company['aliases'])
    return result
