# -*- coding: utf-8 -*-
import openpyxl
import os

# Analyze all xlsx files
files = [f for f in os.listdir(r'C:\Users\houmo\Downloads\仕訳日記帳_temp') if f.endswith('.xlsx')]

all_debit = {}
all_credit = {}
bank_patterns = []

for filename in files:
    filepath = os.path.join(r'C:\Users\houmo\Downloads\仕訳日記帳_temp', filename)
    wb = openpyxl.load_workbook(filepath)
    sheet = wb.active

    for i, row in enumerate(sheet.iter_rows(values_only=True)):
        if i < 10:
            continue
        row_list = list(row)
        if len(row_list) < 25:
            continue

        debit_acc = str(row_list[9]) if row_list[9] else ''
        debit_sub = str(row_list[10]) if row_list[10] else ''
        credit_acc = str(row_list[17]) if row_list[17] else ''
        credit_sub = str(row_list[18]) if row_list[18] else ''
        amount = row_list[14] if row_list[14] else 0
        desc = str(row_list[25]) if len(row_list) > 25 and row_list[25] else ''

        if debit_acc:
            all_debit[debit_acc] = all_debit.get(debit_acc, 0) + 1
        if credit_acc:
            all_credit[credit_acc] = all_credit.get(credit_acc, 0) + 1

        # Bank transactions
        if '普通預金' in debit_acc or '普通預金' in credit_acc:
            bank_patterns.append({
                'debit': debit_acc,
                'debit_sub': debit_sub,
                'credit': credit_acc,
                'credit_sub': credit_sub,
                'amount': amount,
                'desc': desc[:50]
            })

with open(r'C:\Users\houmo\invoice-journal-system\output\full_analysis.txt', 'w', encoding='utf-8') as f:
    f.write('=== 全社 借方勘定科目 TOP30 ===\n')
    for k, v in sorted(all_debit.items(), key=lambda x: -x[1])[:30]:
        f.write(f'{v}: {k}\n')

    f.write('\n=== 全社 貸方勘定科目 TOP30 ===\n')
    for k, v in sorted(all_credit.items(), key=lambda x: -x[1])[:30]:
        f.write(f'{v}: {k}\n')

    # Analyze bank transaction patterns
    bank_debit_patterns = {}  # 借方=普通預金 (入金)
    bank_credit_patterns = {}  # 貸方=普通預金 (出金)

    for p in bank_patterns:
        if '普通預金' in p['debit']:
            key = f"{p['credit']}|{p['credit_sub']}"
            bank_debit_patterns[key] = bank_debit_patterns.get(key, 0) + 1
        if '普通預金' in p['credit']:
            key = f"{p['debit']}|{p['debit_sub']}"
            bank_credit_patterns[key] = bank_credit_patterns.get(key, 0) + 1

    f.write(f'\n=== 入金パターン（借方=普通預金）TOP30 ===\n')
    f.write('件数: 貸方科目|補助科目\n')
    for k, v in sorted(bank_debit_patterns.items(), key=lambda x: -x[1])[:30]:
        f.write(f'{v}: {k}\n')

    f.write(f'\n=== 出金パターン（貸方=普通預金）TOP30 ===\n')
    f.write('件数: 借方科目|補助科目\n')
    for k, v in sorted(bank_credit_patterns.items(), key=lambda x: -x[1])[:30]:
        f.write(f'{v}: {k}\n')

    f.write(f'\n=== 銀行取引サンプル 最初の30件 ===\n')
    for p in bank_patterns[:30]:
        line = f"{p['debit']}|{p['debit_sub']} -> {p['credit']}|{p['credit_sub']} : {p['amount']} : {p['desc']}\n"
        f.write(line)

print(f'Analyzed {len(files)} files, {len(bank_patterns)} bank transactions')
