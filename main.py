"""
請求書自動仕訳システム
Flask APIサーバー
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename

from config.settings import Config, MASTER_DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, ANTHROPIC_API_KEY, BATCH_MAX_FILES, BATCH_CONCURRENT
from services.journal_service import JournalService
from services.csv_service import CsvService
from services.ocr_service import OcrService
from services.master_service import MasterService
from services.bank_service import BankService
from services.learning_service import LearningService
from services.history_service import HistoryService

app = Flask(__name__)
app.config.from_object(Config)

# サービスの初期化
journal_service = JournalService(MASTER_DATA_DIR)
csv_service = CsvService(OUTPUT_DIR)
master_service = MasterService(MASTER_DATA_DIR)
learning_service = LearningService(MASTER_DATA_DIR)
history_service = HistoryService(MASTER_DATA_DIR)

# OCRサービスはAPI keyがある場合のみ初期化
ocr_service = None
if ANTHROPIC_API_KEY:
    ocr_service = OcrService(ANTHROPIC_API_KEY)

# 銀行サービスの初期化
bank_service = BankService(MASTER_DATA_DIR)


def allowed_file(filename: str) -> bool:
    """許可されたファイル形式かチェック"""
    return '.' in filename and \
           ('.' + filename.rsplit('.', 1)[1].lower()) in app.config.get('UPLOAD_EXTENSIONS', [])


def safe_int(value, default=0) -> int:
    """安全に整数変換（カンマ、円、¥などを除去）"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    # 文字列から数値以外を除去
    import re
    cleaned = re.sub(r'[^\d.-]', '', str(value))
    if not cleaned or cleaned == '-' or cleaned == '.':
        return default
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return default


@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """ヘルスチェック"""
    return jsonify({
        'status': 'ok',
        'ocr_available': ocr_service is not None
    })


# ====== 請求書処理 ======

@app.route('/api/invoice/upload', methods=['POST'])
def upload_invoice():
    """請求書をアップロードしてOCR処理（編集画面用にデータを返す）"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '許可されていないファイル形式です'}), 400

    if ocr_service is None:
        return jsonify({'error': 'OCRサービスが利用できません。ANTHROPIC_API_KEYを設定してください'}), 500

    # ファイル保存
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOAD_DIR / unique_filename
    file.save(str(filepath))

    try:
        # OCR処理
        invoice_data = ocr_service.extract_invoice_data(filepath)
        invoice_data['file_path'] = str(filepath)

        # 学習データを適用
        correction = learning_service.find_matching_correction(invoice_data)
        if correction:
            invoice_data = learning_service.apply_correction(invoice_data, correction)

        # デフォルトの仕訳データを生成
        invoice_type = invoice_data.get('invoice_type', 'purchase')
        date_str = invoice_data.get('date', '')

        # 日付パース
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                date = datetime.now()
        else:
            date = datetime.now()

        # 取引先名の決定
        if invoice_type == 'sales':
            vendor_name = invoice_data.get('recipient', '')
        else:
            vendor_name = invoice_data.get('issuer', '')

        amount = safe_int(invoice_data.get('total_amount', 0))
        description = invoice_data.get('description', '')
        if not description:
            month = date.month if date else ''
            description = f"{vendor_name}　{month}月分" if month else vendor_name

        # デフォルトの勘定科目を決定
        if invoice_data.get('suggested_debit_account'):
            debit_account = invoice_data['suggested_debit_account']
            credit_account = invoice_data.get('suggested_credit_account', '普通預金')
            debit_tax = invoice_data.get('suggested_debit_tax_category', '対象外')
            credit_tax = invoice_data.get('suggested_credit_tax_category', '対象外')
        elif invoice_type == 'sales':
            debit_account = '売掛金'
            credit_account = '売上高'
            debit_tax = '対象外'
            credit_tax = '簡売五10%'
        else:
            debit_account = '仕入高'
            credit_account = '買掛金'
            debit_tax = '課対仕入10%'
            credit_tax = '対象外'

        # 編集用データを返す（自動で仕訳一覧に追加しない）
        suggested_entry = {
            'date': date.strftime('%Y-%m-%d'),
            'debit_account': debit_account,
            'debit_sub_account': vendor_name if invoice_type == 'sales' else '',
            'debit_tax_category': debit_tax,
            'debit_amount': amount,
            'credit_account': credit_account,
            'credit_sub_account': vendor_name if invoice_type != 'sales' else '',
            'credit_tax_category': credit_tax,
            'credit_amount': amount,
            'description': description,
            'invoice_type': invoice_type
        }

        return jsonify({
            'success': True,
            'data': invoice_data,
            'suggested_entry': suggested_entry,
            'learning_applied': invoice_data.get('learning_applied', False),
            'auto_created': False  # 編集画面を表示するため
        })
    except Exception as e:
        return jsonify({'error': f'OCR処理に失敗しました: {str(e)}'}), 500


@app.route('/api/invoice/process', methods=['POST'])
def process_invoice():
    """請求書データから仕訳を生成"""
    data = request.json

    if not data:
        return jsonify({'error': 'データが指定されていません'}), 400

    try:
        entries = journal_service.generate_from_invoice(data)

        # 仕訳データをレスポンス用に変換
        result = []
        for entry in entries:
            result.append({
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_amount': entry.credit_amount,
                'description': entry.description
            })

        return jsonify({
            'success': True,
            'entries': result
        })
    except Exception as e:
        return jsonify({'error': f'仕訳生成に失敗しました: {str(e)}'}), 500


# ====== 売上・入金処理 ======

@app.route('/api/sales/create', methods=['POST'])
def create_sales():
    """売上計上の仕訳を生成"""
    data = request.json

    required = ['date', 'vendor_name', 'amount', 'description']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        entry = journal_service.create_sales_entry(
            date=date,
            vendor_name=data['vendor_name'],
            amount=safe_int(data['amount']),
            description=data['description'],
            sales_type=data.get('sales_type', 'sales_receivable')
        )

        return jsonify({
            'success': True,
            'entry': {
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_amount': entry.credit_amount,
                'description': entry.description
            }
        })
    except Exception as e:
        return jsonify({'error': f'仕訳生成に失敗しました: {str(e)}'}), 500


@app.route('/api/payment/receive', methods=['POST'])
def receive_payment():
    """入金処理の仕訳を生成"""
    data = request.json

    required = ['date', 'vendor_name', 'amount', 'description']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        entry = journal_service.create_payment_received_entry(
            date=date,
            vendor_name=data['vendor_name'],
            amount=safe_int(data['amount']),
            description=data['description'],
            bank_id=data.get('bank_id')
        )

        return jsonify({
            'success': True,
            'entry': {
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_amount': entry.credit_amount,
                'description': entry.description
            }
        })
    except Exception as e:
        return jsonify({'error': f'仕訳生成に失敗しました: {str(e)}'}), 500


# ====== 仕入・支払処理 ======

@app.route('/api/purchase/create', methods=['POST'])
def create_purchase():
    """仕入計上の仕訳を生成"""
    data = request.json

    required = ['date', 'vendor_name', 'amount', 'description']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        entry = journal_service.create_purchase_entry(
            date=date,
            vendor_name=data['vendor_name'],
            amount=safe_int(data['amount']),
            description=data['description']
        )

        return jsonify({
            'success': True,
            'entry': {
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_amount': entry.credit_amount,
                'description': entry.description
            }
        })
    except Exception as e:
        return jsonify({'error': f'仕訳生成に失敗しました: {str(e)}'}), 500


@app.route('/api/payment/make', methods=['POST'])
def make_payment():
    """買掛金支払の仕訳を生成"""
    data = request.json

    required = ['date', 'vendor_name', 'amount', 'description']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
        entry = journal_service.create_purchase_payment_entry(
            date=date,
            vendor_name=data['vendor_name'],
            amount=safe_int(data['amount']),
            description=data['description'],
            bank_id=data.get('bank_id')
        )

        return jsonify({
            'success': True,
            'entry': {
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_amount': entry.credit_amount,
                'description': entry.description
            }
        })
    except Exception as e:
        return jsonify({'error': f'仕訳生成に失敗しました: {str(e)}'}), 500


# ====== CSV出力 ======

@app.route('/api/csv/generate', methods=['POST'])
def generate_csv():
    """仕訳データから弥生会計形式CSVを生成"""
    data = request.json

    if not data or 'entries' not in data:
        return jsonify({'error': '仕訳データが指定されていません'}), 400

    try:
        # 開始伝票番号（指定があれば使用）
        start_slip_no = data.get('start_slip_no', 1)

        # 弥生会計形式でCSV生成
        csv_path = csv_service.generate_yayoi_csv(
            entries=data['entries'],
            start_slip_no=start_slip_no
        )

        return jsonify({
            'success': True,
            'file_path': str(csv_path),
            'filename': csv_path.name,
            'count': len(data['entries'])
        })
    except Exception as e:
        return jsonify({'error': f'CSV生成に失敗しました: {str(e)}'}), 500


@app.route('/api/csv/download/<filename>', methods=['GET'])
def download_csv(filename):
    """CSVファイルをダウンロード"""
    filepath = OUTPUT_DIR / secure_filename(filename)
    if not filepath.exists():
        return jsonify({'error': 'ファイルが見つかりません'}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )


# ====== バッチ処理 ======

# スレッドセーフなロック
_batch_lock = threading.Lock()


def _process_single_file(filepath, original_filename, ocr_svc):
    """単一ファイルを処理するヘルパー関数（並列処理用）"""
    try:
        # ドキュメントタイプを検出
        doc_type = ocr_svc.detect_document_type(filepath)

        if doc_type == 'expense_report':
            invoice_data = ocr_svc.extract_expense_report(filepath)
        elif doc_type == 'celebration_application':
            invoice_data = ocr_svc.extract_celebration_application(filepath)
        elif str(filepath).lower().endswith('.pdf'):
            invoice_data = ocr_svc.extract_multi_page_invoice(filepath)
        else:
            invoice_data = ocr_svc.extract_invoice_data(filepath)

        invoice_data['file_path'] = str(filepath)
        invoice_data['document_type'] = doc_type

        # 仕訳生成
        entries = _generate_entries_from_invoice_data(invoice_data)

        return {
            'filename': original_filename,
            'data': invoice_data,
            'entries': entries,
            'success': True
        }
    except Exception as e:
        return {
            'filename': original_filename,
            'error': str(e),
            'success': False
        }


@app.route('/api/invoice/batch', methods=['POST'])
def batch_process_invoices():
    """複数の請求書を一括処理（並列処理対応、最大200ファイル）"""
    if 'files' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if len(files) > BATCH_MAX_FILES:
        return jsonify({'error': f'ファイル数が多すぎます（最大{BATCH_MAX_FILES}件）'}), 400

    if ocr_service is None:
        return jsonify({'error': 'OCRサービスが利用できません'}), 500

    # ファイルを先に全て保存
    file_tasks = []
    invalid_files = []

    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            invalid_files.append({'filename': file.filename, 'error': '不正なファイル形式'})
            continue

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = UPLOAD_DIR / unique_filename
        file.save(str(filepath))
        file_tasks.append((filepath, file.filename))

    # 並列処理で OCR 実行
    results = []
    errors = list(invalid_files)

    with ThreadPoolExecutor(max_workers=BATCH_CONCURRENT) as executor:
        futures = {
            executor.submit(_process_single_file, fp, orig, ocr_service): orig
            for fp, orig in file_tasks
        }

        for future in as_completed(futures):
            result = future.result()
            if result.get('success'):
                results.append(result)
            else:
                errors.append({'filename': result['filename'], 'error': result.get('error', '不明なエラー')})

    return jsonify({
        'success': True,
        'processed': len(results),
        'failed': len(errors),
        'total': len(files),
        'results': results,
        'errors': errors
    })


@app.route('/api/invoice/multipage', methods=['POST'])
def process_multipage_invoice():
    """複数ページPDFを処理（1ページ=1請求書）"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'PDFファイルのみ対応しています'}), 400

    if ocr_service is None:
        return jsonify({'error': 'OCRサービスが利用できません'}), 500

    # ファイル保存
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOAD_DIR / unique_filename
    file.save(str(filepath))

    try:
        # 複数ページPDF処理
        invoice_data = ocr_service.extract_multi_page_invoice(filepath)

        # 各請求書データから仕訳生成
        all_entries = []
        if isinstance(invoice_data, list):
            for data in invoice_data:
                entries = _generate_entries_from_invoice_data(data)
                all_entries.extend(entries)
        else:
            all_entries = _generate_entries_from_invoice_data(invoice_data)

        return jsonify({
            'success': True,
            'data': invoice_data,
            'entries': all_entries,
            'page_count': len(invoice_data) if isinstance(invoice_data, list) else 1
        })
    except Exception as e:
        return jsonify({'error': f'処理に失敗しました: {str(e)}'}), 500


# ====== 出張精算書処理 ======

@app.route('/api/expense-report/upload', methods=['POST'])
def upload_expense_report():
    """出張精算書をアップロードして処理"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '許可されていないファイル形式です'}), 400

    if ocr_service is None:
        return jsonify({'error': 'OCRサービスが利用できません'}), 500

    # ファイル保存
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOAD_DIR / unique_filename
    file.save(str(filepath))

    try:
        # 出張精算書処理
        expense_data = ocr_service.extract_expense_report(filepath)
        expense_data['file_path'] = str(filepath)

        # 仕訳生成
        entries = []
        if 'expenses' in expense_data:
            for expense in expense_data['expenses']:
                date_str = expense.get('date', expense_data.get('date', ''))
                if date_str:
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        date = datetime.now()
                else:
                    date = datetime.now()

                amount = safe_int(expense.get('amount', 0))
                description = expense.get('description', '')
                company = expense.get('company', expense_data.get('applicant', ''))

                entry = journal_service.create_custom_entry(
                    date=date,
                    debit_account='旅費交通費',
                    debit_sub_account=company,
                    credit_account='普通預金',
                    credit_sub_account='',
                    amount=amount,
                    description=description,
                    debit_tax_category='課対仕入10%',
                    credit_tax_category='対象外'
                )
                entries.append({
                    'date': entry.date.strftime('%Y-%m-%d'),
                    'slip_no': entry.slip_no,
                    'debit_account': entry.debit_account,
                    'debit_sub_account': entry.debit_sub_account,
                    'debit_tax_category': entry.debit_tax_category,
                    'debit_amount': entry.debit_amount,
                    'credit_account': entry.credit_account,
                    'credit_sub_account': entry.credit_sub_account,
                    'credit_tax_category': entry.credit_tax_category,
                    'credit_amount': entry.credit_amount,
                    'description': entry.description
                })

        return jsonify({
            'success': True,
            'data': expense_data,
            'entries': entries
        })
    except Exception as e:
        return jsonify({'error': f'処理に失敗しました: {str(e)}'}), 500


# ====== 慶祝金・弔慰金処理 ======

@app.route('/api/celebration/upload', methods=['POST'])
def upload_celebration():
    """慶祝金・弔慰金申請書をアップロードして処理"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '許可されていないファイル形式です'}), 400

    if ocr_service is None:
        return jsonify({'error': 'OCRサービスが利用できません'}), 500

    # ファイル保存
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOAD_DIR / unique_filename
    file.save(str(filepath))

    try:
        # 慶祝金申請書処理
        celebration_data = ocr_service.extract_celebration_application(filepath)
        celebration_data['file_path'] = str(filepath)

        # 仕訳生成
        date_str = celebration_data.get('date', '')
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                date = datetime.now()
        else:
            date = datetime.now()

        amount = safe_int(celebration_data.get('amount', 0))
        applicant = celebration_data.get('applicant', '')
        event_type = celebration_data.get('event_type', '')
        description = f"{applicant} {event_type}"

        entry = journal_service.create_custom_entry(
            date=date,
            debit_account='福利厚生費',
            debit_sub_account='',
            credit_account='普通預金',
            credit_sub_account='',
            amount=amount,
            description=description,
            debit_tax_category='対象外',
            credit_tax_category='対象外'
        )

        entry_data = {
            'date': entry.date.strftime('%Y-%m-%d'),
            'slip_no': entry.slip_no,
            'debit_account': entry.debit_account,
            'debit_sub_account': entry.debit_sub_account,
            'debit_tax_category': entry.debit_tax_category,
            'debit_amount': entry.debit_amount,
            'credit_account': entry.credit_account,
            'credit_sub_account': entry.credit_sub_account,
            'credit_tax_category': entry.credit_tax_category,
            'credit_amount': entry.credit_amount,
            'description': entry.description
        }

        return jsonify({
            'success': True,
            'data': celebration_data,
            'entry': entry_data
        })
    except Exception as e:
        return jsonify({'error': f'処理に失敗しました: {str(e)}'}), 500


def _generate_entries_from_invoice_data(invoice_data):
    """請求書データから仕訳エントリを生成するヘルパー関数"""
    entries = []

    # リスト（複数請求書）の場合
    if isinstance(invoice_data, list):
        for data in invoice_data:
            entries.extend(_generate_entries_from_invoice_data(data))
        return entries

    invoice_type = invoice_data.get('invoice_type', 'purchase')
    date_str = invoice_data.get('date', '')

    if date_str:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            date = datetime.now()
    else:
        date = datetime.now()

    # 取引先名の決定
    if invoice_type == 'sales':
        vendor_name = invoice_data.get('recipient', '')
    else:
        vendor_name = invoice_data.get('issuer', '')

    amount = safe_int(invoice_data.get('total_amount', 0))
    description = invoice_data.get('description', '')
    if not description:
        month = date.month if date else ''
        description = f"{vendor_name}　{month}月分" if month else vendor_name

    # 推定勘定科目
    # suggested_accountは文字列ID（'land_rent', 'travel_expense'等）または辞書
    suggested_account = invoice_data.get('suggested_account', '')

    # 勘定科目キーワードマッピング（OCRサービスと同じ定義）
    ACCOUNT_KEYWORDS = {
        'land_rent': {'debit_account': '地代家賃', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'rent': {'debit_account': '賃借料', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'outsourcing_expense': {'debit_account': '外注費', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'travel_expense': {'debit_account': '旅費交通費', 'credit_account': '普通預金', 'debit_tax_category': '課対仕入10%'},
        'welfare_expense': {'debit_account': '福利厚生費', 'credit_account': '普通預金', 'debit_tax_category': '対象外'},
        'miscellaneous': {'debit_account': '雑費', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'utilities': {'debit_account': '水道光熱費', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'advertising': {'debit_account': '広告宣伝費', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'consumables': {'debit_account': '消耗品費', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'},
        'sales_receivable': {'debit_account': '売掛金', 'credit_account': '売上高', 'debit_tax_category': '対象外', 'credit_tax_category': '簡売五10%'},
        'purchase': {'debit_account': '仕入高', 'credit_account': '買掛金', 'debit_tax_category': '課対仕入10%'}
    }

    # 文字列IDの場合は辞書に変換
    if isinstance(suggested_account, str) and suggested_account in ACCOUNT_KEYWORDS:
        account_info = ACCOUNT_KEYWORDS[suggested_account]
        debit_account = account_info.get('debit_account', '')
        credit_account = account_info.get('credit_account', '')
        debit_tax = account_info.get('debit_tax_category', '対象外')
        credit_tax = account_info.get('credit_tax_category', '対象外')
    elif isinstance(suggested_account, dict):
        debit_account = suggested_account.get('debit_account', '')
        credit_account = suggested_account.get('credit_account', '')
        debit_tax = suggested_account.get('debit_tax_category', '対象外')
        credit_tax = suggested_account.get('credit_tax_category', '対象外')
    else:
        debit_account = ''
        credit_account = ''
        debit_tax = '対象外'
        credit_tax = '対象外'

    if debit_account and credit_account:

        entry = journal_service.create_custom_entry(
            date=date,
            debit_account=debit_account,
            debit_sub_account=vendor_name,
            credit_account=credit_account,
            credit_sub_account='',
            amount=amount,
            description=description,
            debit_tax_category=debit_tax,
            credit_tax_category=credit_tax
        )
    elif invoice_type == 'sales':
        entry = journal_service.create_sales_entry(
            date=date,
            vendor_name=vendor_name,
            amount=amount,
            description=description
        )
    else:
        entry = journal_service.create_purchase_entry(
            date=date,
            vendor_name=vendor_name,
            amount=amount,
            description=description
        )

    entries.append({
        'date': entry.date.strftime('%Y-%m-%d'),
        'slip_no': entry.slip_no,
        'debit_account': entry.debit_account,
        'debit_sub_account': entry.debit_sub_account,
        'debit_tax_category': entry.debit_tax_category,
        'debit_amount': entry.debit_amount,
        'credit_account': entry.credit_account,
        'credit_sub_account': entry.credit_sub_account,
        'credit_tax_category': entry.credit_tax_category,
        'credit_amount': entry.credit_amount,
        'description': entry.description
    })

    return entries


# ====== 銀行取引インポート ======

@app.route('/api/bank/import', methods=['POST'])
def import_bank_transactions():
    """銀行CSVをインポートして自動仕分け"""
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルが指定されていません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'CSVファイルのみ対応しています'}), 400

    # 銀行種別（デフォルト: aichi）
    bank_type = request.form.get('bank_type', 'aichi')

    # ファイル保存
    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    filepath = UPLOAD_DIR / unique_filename
    file.save(str(filepath))

    try:
        # 銀行CSVインポート
        result = bank_service.import_from_csv(filepath, bank_type)

        # 仕訳エントリをJournalEntry形式で生成
        entries = []
        for je in result['journal_entries']:
            if je['amount'] <= 0:
                continue

            date_str = je.get('date', '')
            if date_str:
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    date = datetime.now()
            else:
                date = datetime.now()

            entry = journal_service.create_custom_entry(
                date=date,
                debit_account=je['debit_account'],
                debit_sub_account=je.get('vendor_name', ''),
                credit_account=je['credit_account'],
                credit_sub_account='',
                amount=je['amount'],
                description=je['description'],
                debit_tax_category=je['debit_tax_category'],
                credit_tax_category=je['credit_tax_category']
            )

            entries.append({
                'date': entry.date.strftime('%Y-%m-%d'),
                'slip_no': entry.slip_no,
                'debit_account': entry.debit_account,
                'debit_sub_account': entry.debit_sub_account,
                'debit_tax_category': entry.debit_tax_category,
                'debit_amount': entry.debit_amount,
                'credit_account': entry.credit_account,
                'credit_sub_account': entry.credit_sub_account,
                'credit_tax_category': entry.credit_tax_category,
                'credit_amount': entry.credit_amount,
                'description': entry.description,
                'rule_id': je['rule_id'],
                'rule_name': je['rule_name'],
                'confidence': je['confidence'],
                'needs_review': je['needs_review']
            })

        return jsonify({
            'success': True,
            'summary': result['summary'],
            'entries': entries,
            'transactions': result['transactions']
        })
    except Exception as e:
        return jsonify({'error': f'インポートに失敗しました: {str(e)}'}), 500


@app.route('/api/bank/match', methods=['POST'])
def match_bank_transaction():
    """銀行取引データから仕訳ルールをマッチング（単一取引）"""
    data = request.json

    if not data:
        return jsonify({'error': 'データが指定されていません'}), 400

    required = ['description']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        transaction = {
            'description': data['description'],
            'deposit': data.get('deposit', 0),
            'withdrawal': data.get('withdrawal', 0),
            'direction': 'deposit' if data.get('deposit', 0) > 0 else 'withdrawal'
        }

        rule_id, vendor_name, confidence = bank_service.match_rule(transaction)
        rule = bank_service.rules.get(rule_id, {})

        return jsonify({
            'success': True,
            'rule_id': rule_id,
            'rule_name': rule.get('name', ''),
            'vendor_name': vendor_name,
            'confidence': confidence,
            'debit_account': rule.get('debit_account', ''),
            'credit_account': rule.get('credit_account', ''),
            'debit_tax_category': rule.get('debit_tax_category', '対象外'),
            'credit_tax_category': rule.get('credit_tax_category', '対象外')
        })
    except Exception as e:
        return jsonify({'error': f'マッチングに失敗しました: {str(e)}'}), 500


# ====== 学習機能 ======

@app.route('/api/learn/save', methods=['POST'])
def save_correction():
    """修正内容を学習データとして保存"""
    data = request.json

    if not data:
        return jsonify({'error': 'データが指定されていません'}), 400

    required = ['original', 'corrected']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        success = learning_service.save_correction(
            original=data['original'],
            corrected=data['corrected']
        )

        if success:
            return jsonify({
                'success': True,
                'message': '学習データを保存しました'
            })
        else:
            return jsonify({'error': '保存に失敗しました'}), 500
    except Exception as e:
        return jsonify({'error': f'保存に失敗しました: {str(e)}'}), 500


@app.route('/api/learn/list', methods=['GET'])
def list_corrections():
    """学習データ一覧を取得"""
    try:
        corrections = learning_service.get_all_corrections()
        return jsonify({
            'success': True,
            'corrections': corrections,
            'count': len(corrections)
        })
    except Exception as e:
        return jsonify({'error': f'取得に失敗しました: {str(e)}'}), 500


@app.route('/api/learn/delete/<int:index>', methods=['DELETE'])
def delete_correction(index):
    """学習データを削除"""
    try:
        success = learning_service.delete_correction(index)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': '削除に失敗しました'}), 400
    except Exception as e:
        return jsonify({'error': f'削除に失敗しました: {str(e)}'}), 500


@app.route('/api/learn/clear', methods=['DELETE'])
def clear_corrections():
    """全ての学習データをクリア"""
    try:
        learning_service.clear_all_corrections()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': f'クリアに失敗しました: {str(e)}'}), 500


# ====== マスタデータ ======

@app.route('/api/master/vendors', methods=['GET'])
def get_vendors():
    """取引先一覧を取得"""
    vendor_type = request.args.get('type')
    vendors = master_service.get_vendors(vendor_type)
    return jsonify({'vendors': vendors})


@app.route('/api/master/vendors', methods=['POST'])
def add_vendor():
    """取引先を追加"""
    data = request.json
    if master_service.add_vendor(data):
        return jsonify({'success': True})
    return jsonify({'error': '追加に失敗しました'}), 400


@app.route('/api/master/banks', methods=['GET'])
def get_banks():
    """銀行一覧を取得"""
    banks = master_service.get_banks()
    return jsonify({
        'banks': banks,
        'default_bank': master_service.default_bank
    })


@app.route('/api/master/rules', methods=['GET'])
def get_rules():
    """仕訳ルール一覧を取得"""
    rules = master_service.get_rules()
    return jsonify({'rules': rules})


@app.route('/api/master/sub_accounts', methods=['GET'])
def get_sub_accounts():
    """補助科目一覧を取得"""
    sub_accounts = master_service.get_all_sub_accounts()
    return jsonify({'sub_accounts': sub_accounts})


# ====== 履歴管理 ======

@app.route('/api/history/entries', methods=['GET'])
def get_history_entries():
    """仕訳履歴を取得"""
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        exported = request.args.get('exported')
        source_type = request.args.get('source_type')

        # 文字列をboolに変換
        if exported == 'true':
            exported = True
        elif exported == 'false':
            exported = False
        else:
            exported = None

        entries = history_service.get_entries(
            limit=limit,
            offset=offset,
            exported=exported,
            source_type=source_type
        )

        return jsonify({
            'success': True,
            'entries': entries,
            'count': len(entries)
        })
    except Exception as e:
        return jsonify({'error': f'取得に失敗しました: {str(e)}'}), 500


@app.route('/api/history/entries', methods=['POST'])
def add_history_entry():
    """仕訳を履歴に追加"""
    data = request.json

    if not data or 'entry' not in data:
        return jsonify({'error': 'エントリデータが指定されていません'}), 400

    try:
        entry_id = history_service.add_entry(
            entry=data['entry'],
            source_file=data.get('source_file'),
            source_type=data.get('source_type', 'manual'),
            learning_applied=data.get('learning_applied', False)
        )

        return jsonify({
            'success': True,
            'entry_id': entry_id
        })
    except Exception as e:
        return jsonify({'error': f'追加に失敗しました: {str(e)}'}), 500


@app.route('/api/history/entries/batch', methods=['POST'])
def add_history_entries_batch():
    """複数の仕訳を一括で履歴に追加"""
    data = request.json

    if not data or 'entries' not in data:
        return jsonify({'error': 'エントリデータが指定されていません'}), 400

    try:
        entry_ids = history_service.add_entries_batch(
            entries=data['entries'],
            source_files=data.get('source_files'),
            source_type=data.get('source_type', 'ocr_batch'),
            learning_applied_flags=data.get('learning_applied_flags')
        )

        return jsonify({
            'success': True,
            'entry_ids': entry_ids,
            'count': len(entry_ids)
        })
    except Exception as e:
        return jsonify({'error': f'追加に失敗しました: {str(e)}'}), 500


@app.route('/api/history/exports', methods=['GET'])
def get_history_exports():
    """CSV出力履歴を取得"""
    try:
        limit = int(request.args.get('limit', 50))
        exports = history_service.get_exports(limit=limit)

        return jsonify({
            'success': True,
            'exports': exports,
            'count': len(exports)
        })
    except Exception as e:
        return jsonify({'error': f'取得に失敗しました: {str(e)}'}), 500


@app.route('/api/history/exports', methods=['POST'])
def record_history_export():
    """CSV出力を履歴に記録"""
    data = request.json

    if not data:
        return jsonify({'error': 'データが指定されていません'}), 400

    required = ['filename', 'entry_ids']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field}が指定されていません'}), 400

    try:
        export_id = history_service.record_export(
            filename=data['filename'],
            entry_ids=data['entry_ids']
        )

        return jsonify({
            'success': True,
            'export_id': export_id
        })
    except Exception as e:
        return jsonify({'error': f'記録に失敗しました: {str(e)}'}), 500


@app.route('/api/history/stats', methods=['GET'])
def get_history_stats():
    """履歴の統計情報を取得"""
    try:
        stats = history_service.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': f'取得に失敗しました: {str(e)}'}), 500


@app.route('/api/history/entries/<entry_id>', methods=['DELETE'])
def delete_history_entry(entry_id):
    """仕訳履歴を削除"""
    try:
        success = history_service.delete_entry(entry_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': '削除に失敗しました'}), 400
    except Exception as e:
        return jsonify({'error': f'削除に失敗しました: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
