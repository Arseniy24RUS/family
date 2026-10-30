#!/usr/bin/env python3
"""Build reproducible Longlife finance, targets, document links and text analysis.

The default build is offline and uses the standard library. --verify-text also
recalculates the fixed TF-IDF model and Russian Snowball sensitivity.
"""
from pathlib import Path
from decimal import Decimal
import argparse, collections, csv, gzip, hashlib, json, re
from build_youth_documentary import numrows, verify_text

PROJECT = 'long_active_life'
REL = f'downloads/projects/{PROJECT}/documentary/'
YEARS = range(2025, 2031)
MILLION = Decimal(1000000)


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def csv_rows(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def decimal(value):
    return Decimal(str(value))


def target_version_key(row):
    return row['source_sha256'], row['source_version'], row.get('target_series_id', '')


def build_targets(inputs, registry):
    all_rows = inputs['tables']['targets']
    documents = {d['source_sha256']: d for d in inputs['source_documents']}
    items, selected_records = [], []
    for indicator in registry['items']:
        code = indicator['indicator_code']
        candidates = [r for r in all_rows if r['indicator_code'] == code and r['target_period_kind'] == 'annual' and r['mapping_status'] in {'approved', 'conditional'}]
        assert candidates, code
        national = bool(re.search(r'\.Д\.', code))

        def priority(row):
            html = row['source_kind'] == 'secondary_epbs_rendering'
            level_match = row['document_level'] == ('national' if national else 'federal')
            return (0 if row['mapping_status'] == 'approved' else 1, 0 if html else 1, 0 if level_match else 1, 0 if row['source_kind'] == 'pdf_national_passport' else 1, target_version_key(row))

        chosen = min(candidates, key=priority)
        selected_key = target_version_key(chosen)
        selected = sorted([r for r in candidates if target_version_key(r) == selected_key], key=lambda r: int(r['target_year']))
        selected_records.extend(selected)
        years = {str(y): None for y in YEARS}
        for row in selected:
            year = row['target_year']
            if year not in years:
                continue
            number = float(row['target_value'])
            assert years[year] is None or years[year] == number, (code, year, 'Conflicting values in selected source series')
            years[year] = number
        variants = []
        for key in sorted({target_version_key(r) for r in candidates}):
            records = [r for r in candidates if target_version_key(r) == key]
            first = records[0]
            values = {}
            for row in records:
                assert row['target_year'] not in values or values[row['target_year']] == float(row['target_value'])
                values[row['target_year']] = float(row['target_value'])
            variants.append({'source_url': first['source_url'], 'source_version': first['source_version'], 'source_sha256': first['source_sha256'], 'source_file': documents[first['source_sha256']]['download_path'], 'target_series_id': first.get('target_series_id'), 'source_locator': first['source_locator'], 'years': values, 'unit': first['unit'], 'mapping_status': first['mapping_status'], 'selected': key == selected_key, 'document_level': first['document_level'], 'source_kind': first['source_kind']})
        source_ids = indicator.get('source_ids', [])
        unit = '%' if chosen['unit'].lower() == 'процент' else chosen['unit']
        display_unit = 'человек на 10 тыс. населения' if code in {'2.14.Д.19', '2.14.ДБ.1', '2.14.ДБ.3'} else 'лет' if unit.lower() in {'год', 'лет'} else unit
        proxy = chosen.get('target_is_proxy') == '1'
        selected_html = chosen['source_kind'] == 'secondary_epbs_rendering'
        item = {'code': code, 'indicator_code': code, 'emiss_id': int(source_ids[0]) if source_ids else None, 'source_ids': source_ids, 'name': indicator['indicator_name'], 'target_name': chosen.get('target_indicator_name') or chosen['indicator_name'], 'unit': unit, 'display_unit': display_unit, 'direction': chosen['direction'], 'years': years, 'yearStatus': {year: 'documented_target' if value is not None else 'not_published' for year, value in years.items()}, 'baseline': {'year': int(chosen['baseline_year']) if chosen['baseline_year'].isdigit() else None, 'value': float(chosen['baseline_value']) if chosen['baseline_value'] else None, 'status': 'source_value_with_year' if chosen['baseline_year'] else 'source_value_without_confirmed_year'}, 'source_url': chosen['source_url'], 'source_sha256': chosen['source_sha256'], 'source_locator': chosen['source_locator'], 'source_version': chosen['source_version'], 'source_file': documents[chosen['source_sha256']]['download_path'], 'source_kind': chosen['source_kind'], 'document_level': chosen['document_level'], 'publisher_updated_label': chosen['publisher_updated_label'], 'measure_type': chosen['measure_type'], 'gap_unit': chosen['gap_unit'], 'records': [{k: row.get(k) for k in ['target_id', 'target_year', 'target_value', 'source_locator', 'source_sha256', 'mapping_status']} for row in selected], 'versions': variants, 'mapping_status': chosen['mapping_status'], 'formal_comparison_eligible': chosen['mapping_status'] == 'approved' and bool(source_ids), 'target_is_proxy': proxy, 'proxy_only': proxy, 'edition_note': 'Выбранная электронная редакция от 16.10.2026. Сопоставление не является проверкой первоначально утверждённого обязательства 2025 года.' if selected_html else 'Выбрана доступная документальная PDF-редакция. Значения не приписываются отсутствующей актуальной электронной публикации.'}
        if display_unit != unit:
            item['denominator_note'] = 'Официальная единица сохранена; при отображении раскрыт знаменатель либо языковое обозначение величины.'
        for year, value in years.items():
            if value is None and any(year in variant['years'] for variant in variants):
                item['yearStatus'][year] = 'not_published_in_selected_source_series'
        if code == '2.14.Д.16':
            item['clarification'] = 'Выбранный национальный PDF-паспорт содержит извлечённый ориентир только за 2025 год. Будущие значения другой PDF-редакции сохранены в перечне версий и не объединяются с выбранной серией.'
        if proxy:
            item['clarification'] = 'Абсолютный прокси-показатель П02851-Д8: число пациентов, а не доля пользователей или цифрового охвата. Сопоставим только со своим абсолютным планом 2025 года; последующие годы не опубликованы.'
        if code in {'2.14.Д.13', '2.14.ДА.6'}:
            item['clarification'] = 'Паспортный ориентир 2030 года — 14,6%; в информационном материале Правительства указан 13,6%. Основания и редакции сохраняются раздельно; прежний ориентир не заменяет выбранную паспортную цель.'
        items.append(item)
    assert len(items) == 65
    numeric = sum(value is not None for item in items for value in item['years'].values())
    result = {'project_id': PROJECT, 'documentary_snapshot': inputs['documentary_snapshot'], 'basis': 'selected_source_editions_with_explicit_priority_and_preserved_alternatives', 'items': items, 'target_cells': len(items) * 6, 'numeric_targets': numeric, 'missing_targets': len(items) * 6 - numeric, 'version_policy': 'Choose a complete source series: approved mapping, then HTML, then matching governance level; preserve every alternative source series without averaging. Federal HTML is preferred for federal registry codes. National entries without linked statistics retain no invented EMISS source.', 'extracted_records_all_editions': len(all_rows), 'selected_record_count': len(selected_records), 'clarifications': [{'indicator_codes': ['2.14.Д.13', '2.14.ДА.6'], 'year': 2030, 'selected_value': 14.6, 'other_published_value': 13.6, 'source_url': 'https://government.ru/info/54305/', 'sourceIds': ['report', 'fn_016'], 'status': 'different_documentary_bases_not_interchangeable'}, {'indicator_code': '2.14.Д8.3', 'status': 'absolute_proxy_only', 'source_id': '63151', 'unit': 'человек', 'published_years': [2025]}], 'strategicGoals': [{'name': 'Ожидаемая продолжительность жизни при рождении', 'year': 2030, 'value': 78, 'unit': 'лет', 'source_url': 'https://government.ru/info/54305/', 'sourceIds': ['report', 'fn_016']}, {'name': 'Ожидаемая продолжительность жизни при рождении', 'year': 2036, 'value': 81, 'unit': 'лет', 'source_url': 'https://government.ru/info/54305/', 'sourceIds': ['report', 'fn_016']}]}
    return result, selected_records


def build_finance(inputs, names):
    cashflows = inputs['tables']['f_cashflows']
    headers = [r for r in cashflows if r['row_type'] == 'document_header' and r['source_name'] == 'all_sources_declared']
    federal = [r for r in headers if r['document_level'] == 'federal' and int(r['year']) in YEARS]
    national = [r for r in headers if r['document_level'] == 'national' and int(r['year']) in YEARS]
    assert (len(federal), len(national)) == (66, 6)
    projects, horizons = [], []
    for title in sorted({r['document_title'] for r in federal}):
        common = sorted([r for r in federal if r['document_title'] == title], key=lambda r: int(r['year']))
        full = sorted([r for r in headers if r['document_level'] == 'federal' and r['document_title'] == title], key=lambda r: int(r['year']))
        first = common[0]
        code = re.search(r'\[(Д[1-9АБ])\]', title).group(1)
        total = sum(decimal(r['amount_thousand_rub']) for r in common)
        full_total = sum(decimal(r['amount_thousand_rub']) for r in full)
        later_rows = [r for r in full if int(r['year']) > 2030]
        later = sum((decimal(r['amount_thousand_rub']) for r in later_rows), Decimal(0)) if later_rows else None
        point = lambda r: {'year': int(r['year']), 'amountThousandRub': r['amount_thousand_rub'], 'amountBillionRub': float(decimal(r['amount_thousand_rub']) / MILLION), 'record_id': r['record_id'], 'source_xpath': r['source_xpath']}
        late_share = sum(decimal(r['amount_thousand_rub']) for r in common if int(r['year']) in {2029, 2030}) / total * 100
        project = {'id': 'd' + code[1:].replace('А', 'a').replace('Б', 'b'), 'code': code, 'name': names[code], 'title': title, 'totalThousandRub': str(total), 'totalBillionRub': float(total / MILLION), 'years': [point(r) for r in common], 'fullYears': [point(r) for r in full], 'laterThousandRub': str(later) if later is not None else None, 'laterBillionRub': float(later / MILLION) if later is not None else None, 'laterPublished': bool(later_rows), 'fullHorizonThousandRub': str(full_total), 'fullHorizonBillionRub': float(full_total / MILLION), 'source_url': first['source_url'], 'source_sha256': first['source_sha256'], 'edition': first['edition_label'], 'publisher_updated_label': first['publisher_updated_label'], 'retrieved_at': first['retrieved_at'], 'lastTwoYearsSharePercent': float(late_share)}
        projects.append(project)
        horizons.append({'code': code, 'name': project['name'], 'commonStart': 2025, 'commonEnd': 2030, 'commonThousandRub': str(total), 'commonBillionRub': float(total / MILLION), 'fullStart': min(int(r['year']) for r in full), 'fullEnd': max(int(r['year']) for r in full), 'fullThousandRub': str(full_total), 'fullBillionRub': float(full_total / MILLION), 'laterStart': min(int(r['year']) for r in later_rows) if later_rows else None, 'laterEnd': max(int(r['year']) for r in later_rows) if later_rows else None, 'laterThousandRub': project['laterThousandRub'], 'laterBillionRub': project['laterBillionRub'], 'laterPublished': bool(later_rows)})
    total = sum(decimal(p['totalThousandRub']) for p in projects)
    nat_total = sum(decimal(r['amount_thousand_rub']) for r in national)
    full_total = sum(decimal(p['fullHorizonThousandRub']) for p in projects)
    for project in projects:
        share = decimal(project['totalThousandRub']) / total
        project.update(share=float(share * 100), sharePercent=float(share * 100), shareFraction=float(share))

    def reconciliation_row(year, nat, fed):
        return {'year': year, 'nationalThousandRub': str(nat), 'federalThousandRub': str(fed), 'differenceThousandRub': str(fed - nat), 'nationalMinusFederalThousandRub': str(nat - fed), 'nationalBillionRub': float(nat / MILLION), 'federalBillionRub': float(fed / MILLION), 'differenceBillionRub': float((fed - nat) / MILLION), 'nationalMinusFederalBillionRub': float((nat - fed) / MILLION)}

    reconciliation = [reconciliation_row(year, sum(decimal(r['amount_thousand_rub']) for r in national if int(r['year']) == year), sum(decimal(r['amount_thousand_rub']) for r in federal if int(r['year']) == year)) for year in YEARS]
    source_rows = [r for r in cashflows if r['row_type'] == 'document_source' and int(r['year']) in YEARS]
    source_categories = [('Федеральный бюджет, всего', 'federal_budget', 'Федеральный бюджет'), ('Консолидированные бюджеты субъектов Российской Федерации, всего', 'regional_budgets', 'Консолидированные бюджеты субъектов РФ'), ('Бюджеты государственных внебюджетных фондов Российской Федерации, всего', 'state_extra_budgetary_funds', 'Государственные внебюджетные фонды')]
    source_summaries, source_years = [], []
    for source_name, code, name in source_categories:
        national_sum = sum((decimal(r['amount_thousand_rub']) for r in source_rows if r['source_name'] == source_name and r['document_level'] == 'national'), Decimal(0))
        federal_sum = sum((decimal(r['amount_thousand_rub']) for r in source_rows if r['source_name'] == source_name and r['document_level'] == 'federal'), Decimal(0))
        source_summaries.append({**reconciliation_row('2025–2030', national_sum, federal_sum), 'code': code, 'name': name, 'source_name': source_name, 'nationalSharePercent': float(national_sum / nat_total * 100)})
        for year in YEARS:
            n = sum((decimal(r['amount_thousand_rub']) for r in source_rows if r['source_name'] == source_name and r['document_level'] == 'national' and int(r['year']) == year), Decimal(0))
            f = sum((decimal(r['amount_thousand_rub']) for r in source_rows if r['source_name'] == source_name and r['document_level'] == 'federal' and int(r['year']) == year), Decimal(0))
            source_years.append({**reconciliation_row(year, n, f), 'code': code, 'name': name, 'source_name': source_name})
    assert sum(decimal(r['nationalThousandRub']) for r in source_summaries) == nat_total
    assert sum(decimal(r['federalThousandRub']) for r in source_summaries) == total
    assert all(decimal(r['difference_thousand_rub']) == 0 for r in inputs['tables']['f_source_reconciliation'])
    hhi = sum((decimal(p['totalThousandRub']) / total) ** 2 for p in projects)
    assert len(projects) == 11 and sum(len(p['fullYears']) for p in projects) == 120
    assert {p['code'] for p in projects if not p['laterPublished']} == {'Д9', 'ДА'}
    assert all(decimal(r['nationalMinusFederalThousandRub']) > 0 for r in reconciliation)
    return {'projects': projects, 'reconciliation': reconciliation, 'horizonSummaries': horizons, 'sourceSummaries': source_summaries, 'sourceYears': source_years, 'sourceReconciliation': inputs['tables']['f_source_reconciliation'], 'totalThousandRub': str(total), 'totalBillionRub': float(total / MILLION), 'nationalThousandRub': str(nat_total), 'nationalBillionRub': float(nat_total / MILLION), 'differenceThousandRub': str(total - nat_total), 'differenceBillionRub': float((total - nat_total) / MILLION), 'nationalMinusFederalThousandRub': str(nat_total - total), 'nationalMinusFederalBillionRub': float((nat_total - total) / MILLION), 'differenceConvention': 'federal_minus_national', 'authorDifferenceConvention': 'national_minus_federal', 'differenceLabel': 'Сумма ФП − национальный паспорт', 'authorDifferenceLabel': 'Национальный паспорт − сумма ФП', 'laterThousandRub': str(full_total - total), 'fullHorizonThousandRub': str(full_total), 'fullHorizonNote': 'Сумма опубликованных горизонтов: девять ФП до 2036 года, Д9 и ДА до 2030 года. Отсутствующие последующие годы не заменяются нулём.', 'hhi': float(hhi), 'hhiDecimal': str(hhi), 'effectiveEqualProjects': float(1 / hhi), 'top2SharePercent': sum(p['sharePercent'] for p in sorted(projects, key=lambda p: decimal(p['totalThousandRub']), reverse=True)[:2]), 'nationalLastTwoYearsSharePercent': float(sum(decimal(r['amount_thousand_rub']) for r in national if int(r['year']) in {2029, 2030}) / nat_total * 100), 'unit': 'тыс. руб.', 'basis': 'Номинальные плановые назначения по всем источникам, 2025–2030', 'notExecution': True, 'differentEditions': True, 'cashflows': cashflows, 'limitations': ['Паспортный план не является кассовым исполнением.', 'Вложенные межбюджетные перечисления не суммируются повторно.', 'Суммы после 2030 года показаны отдельно; у Д9 и ДА такие строки отсутствуют.', 'Малая доля профилактики или кадров в паспортах не характеризует все расходы здравоохранения на эти функции.', 'Расхождение агрегатов не доказывает недофинансирование, избыточные расходы или нарушение.']}


def reviewed_links(inputs):
    rows = inputs['manual_reviewed_links']
    provenance = inputs['manual_review_provenance']
    source = next(d for d in inputs['source_documents'] if d['source_sha256'] == provenance['source_pdf_sha256'])
    nodes, edges = {}, []
    refs = ['report', 'fn_005', 'fn_116', 'fn_119', 'fn_121']
    for row in rows:
        rid, iid = 'reviewed_Д2_r' + row['result_number'], 'reviewed_Д2_i' + row['indicator_number']
        common = {'code': 'Д2', 'sourceIds': refs, 'source_url': source['source_url'], 'source_file': source['download_path']}
        nodes[rid] = {**common, 'id': rid, 'kind': 'result', 'title': row['result_short'], 'full_title': row['result_title'], 'result_number': row['result_number']}
        nodes[iid] = {**common, 'id': iid, 'kind': 'indicator', 'title': row['indicator_short'], 'full_title': row['indicator'], 'indicator_code': row['indicator_code'], 'indicator_number': row['indicator_number'], 'source_indicator_level': row['source_indicator_level']}
        edges.append({**common, 'id': rid + '_' + iid, 'source_node_id': rid, 'target_node_id': iid, 'evidence_class': 'reviewed_direct_passport_link', 'relation': 'direct_passport_assignment', 'weight': 1, 'documentary_weight_percent': int(row['documentary_weight_percent']), 'weight_meaning': 'passport_declared_distribution_not_estimated_causal_effect', 'figureId': 'figure_14', 'pdf_page': int(row['pdf_page']), 'printed_page': int(row['printed_page']), 'source_sha256': source['source_sha256'], 'edition_note': 'Полный паспорт с планом реализации 2025 года. Сохранение весов в электронной редакции 2026 года не подтверждено.', 'causal_effect': False})
    column_sums = {str(i): sum(edge['documentary_weight_percent'] for edge in edges if edge['target_node_id'] == f'reviewed_Д2_i{i}') for i in range(1, 7)}
    row_sums = {str(i): sum(edge['documentary_weight_percent'] for edge in edges if edge['source_node_id'] == f'reviewed_Д2_r{i}') for i in range(1, 5)}
    assert len(nodes) == 10 and len(edges) == 24 and set(column_sums.values()) == {100}
    assert list(row_sums.values()) == [155, 90, 190, 165]
    return {'nodes': list(nodes.values()), 'edges': edges, 'scope': 'Полная весовая матрица Д2: четыре мероприятия и шесть показателей', 'source': 'Полный паспорт борьбы с сердечно-сосудистыми заболеваниями, PDF, с. 182–183; печатные страницы дополнительных материалов 1–2.', 'columnSums': column_sums, 'rowSums': row_sums, 'resultCount': 4, 'indicatorCount': 6, 'edgeCount': 24, 'bipartiteDensity': 1, 'unweightedResultDegree': 6, 'unweightedIndicatorDegree': 4, 'rowSumInterpretation': 'Сумма весов по шести разным показателям не является рейтингом общественной полезности.', 'causal_effect': False}


def build_text(inputs):
    tables = inputs['tables']
    documents = numrows(tables['documents'])
    same_genre = {d['document_id'] for d in documents if d['genre'] == 'html_passport'}
    federal = {d['document_id'] for d in documents if d['genre'] == 'html_passport' and d['document_level'] == 'federal'}
    primary = next(d['document_id'] for d in documents if d['genre'] == 'html_passport' and d['document_level'] == 'national')
    pairs = [r for r in tables['document_similarity'] if r['document_a'] in same_genre and r['document_b'] in same_genre]
    assert (len(documents), len(same_genre), len(federal), len(pairs)) == (15, 12, 11, 66)
    token_count = sum(int(d['profile_token_count']) for d in documents if d['document_id'] in same_genre)
    assert token_count == 9094
    frames = [{'id': key, 'name': value['name'], 'patterns': value['patterns']} for key, value in inputs['profiles']['dictionary']['frames'].items()]
    totals = []
    for frame in frames:
        count = sum(int(r['count']) for r in tables['frame_scores'] if r['document_id'] in same_genre and r['frame_id'] == frame['id'])
        totals.append({'frame_id': frame['id'], 'frame_name': frame['name'], 'count': count, 'n_tokens': token_count, 'per_1000_tokens': count / token_count * 1000, 'scope': '12_same_genre_structured_html_passports'})
    comparable = lambda row: row.get('family_genre_mismatch') != '1' and row.get('project_a') != 'family' and row.get('project_b') != 'family'
    similarity = [r for r in tables['project_similarity'] if comparable(r)]
    stemming = [r for r in tables['stemming_project_sensitivity'] if comparable(r)]
    assert len(similarity) == len(stemming) == 9
    rank = lambda rows, field: [r['project_b'] if r['project_a'] == PROJECT else r['project_a'] for r in sorted(rows, key=lambda r: float(r[field]), reverse=True)]
    primary_order, stem_order = rank(similarity, 'cosine_similarity'), rank(stemming, 'russian_snowball_cosine')
    assert primary_order == stem_order
    return {'documents': documents, 'federalDocumentIds': sorted(federal), 'sameGenreDocumentIds': sorted(same_genre), 'primaryDocumentId': primary, 'sameGenreTokenCount': token_count, 'frames': frames, 'frameScores': numrows(tables['frame_scores']), 'frameTotals': totals, 'projectFrameScores': numrows(tables['project_frame_scores']), 'topTerms': numrows(tables['tfidf_top_terms']), 'documentSimilarity': numrows(pairs), 'projectSimilarity': numrows(similarity), 'stemmingSensitivity': numrows(stemming), 'crossGenreProjectSimilarity': numrows([r for r in tables['project_similarity'] if not comparable(r)]), 'crossGenreStemmingSensitivity': numrows([r for r in tables['stemming_project_sensitivity'] if not comparable(r)]), 'stability': {'same_top_three': primary_order[:3] == stem_order[:3], 'top_three_jaccard': 1, 'same_all_nine_order': primary_order == stem_order, 'primary_order': primary_order, 'stemmed_order': stem_order}, 'kwic': numrows(tables['kwic']), 'units': numrows(tables['units']), 'lexicalFrequencies': numrows(tables['lexical_frequencies']), 'domainEvidence': numrows(tables['domain_evidence']), 'conceptCooccurrence': numrows(tables['concept_cooccurrence']), 'parameters': inputs['profiles']['parameters'], 'corpusDocuments': len(inputs['profiles']['documents']), 'dictionaryVersion': inputs['profiles']['dictionary']['version'], 'limitations': ['Категории словаря пересекаются и не складываются до 100%.', 'Матрица сходства охватывает 12 однотипных HTML-паспортов: национальный и 11 федеральных.', 'Межпроектное сопоставление исключает архивный жанр «Семьи»; отдельные коэффициенты сохранены только как несовместимые по жанру данные.', 'Семейная медицина не означает семейную политику; школы пациентов не определяют молодёжную направленность; слово «образования» может обозначать территориальные образования.', 'Здоровье в названии цифровой платформы не равнозначно мероприятию по здоровому образу жизни.', 'Стемминг не является лемматизацией. Сходство лексики не измеряет причинную связь или качество управления.']}


def build(root, verify=False):
    root = Path(root)
    download = root / 'public' / REL
    with gzip.open(root / 'inputs/longlife/documentary_inputs.json.gz', 'rt', encoding='utf-8') as stream:
        inputs = json.load(stream)
    for source in inputs['source_documents']:
        path = (root / 'public' / source['download_path']).resolve()
        assert path.is_relative_to((root / 'public').resolve())
        assert path.stat().st_size == source['size_bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == source['source_sha256']
    assert hashlib.sha256((download / 'manual_direct_links.csv').read_bytes()).hexdigest() == inputs['manual_review_provenance']['sha256']
    registry = json.loads((root / f'public/data/projects/{PROJECT}/indicators.json').read_text())
    config = json.loads((root / 'inputs/longlife/report/editorial_config.json').read_text())
    targets, selected_targets = build_targets(inputs, registry)
    finance = build_finance(inputs, {p['code']: p['name'] for p in config['federalProjects']})
    text = build_text(inputs)
    tables = inputs['tables']
    coverage = numrows(tables['link_coverage'])[0]
    coverage.update(federal_indicator_cards=43, national_indicator_cards=10, unique_statistical_series=42, direct_reviewed_results=4, direct_reviewed_indicators=6, direct_reviewed_edges=24)
    network = {'nodes': numrows(tables['nodes']), 'edges': numrows(tables['edges']), 'sharedTaskLinks': numrows(tables['result_indicator_shared_task']), 'semanticCandidates': numrows(tables['semantic_candidates']), 'coverage': coverage, 'metrics': numrows(tables['network_node_metrics']), 'summary': numrows(tables['network_summary']), 'unresolvedClaims': numrows(tables['link_claims']), 'indicatorRegistryLinks': numrows(tables['indicator_registry_links']), 'directReviewed': reviewed_links(inputs), 'limitations': ['Карточки результатов не устанавливают исполнение; 53 карточки показателей не являются 53 независимыми статистическими величинами.', '282 пары через общую задачу имеют структурное основание.', '160 лексических кандидатов не утверждены как прямые связи.', 'Проверенные 24 прямые связи охватывают только полную матрицу Д2 редакции с планом 2025 года.', 'Полная двудольная сеть не позволяет ранжировать мероприятия по невзвешенной степени.']}
    assert (len(network['nodes']), len(network['edges']), len(network['sharedTaskLinks']), len(network['semanticCandidates'])) == (184, 313, 282, 160)
    metadata = {'project_id': PROJECT, 'source_release': inputs['source_release'], 'documentary_snapshot': inputs['documentary_snapshot'], 'source_documents': len(inputs['source_documents']), 'source_document_bytes_verified': True, 'source_input_sha256': hashlib.sha256((root / 'inputs/longlife/documentary_inputs.json.gz').read_bytes()).hexdigest(), 'source_provenance': inputs['source_provenance'], 'source_kind': 'documentary_plans_and_profiles', 'notExecution': True, 'notCausal': True}
    doc = {'meta': metadata, 'finance': finance, 'network': network, 'text': text, 'targets': targets, 'demographicContext': config['demographicContext'], 'sources': inputs['source_documents'], 'downloads': {'sources': REL + 'documentary_sources.zip', 'inputs': REL + 'documentary_inputs.json.gz', 'sources_index': REL + 'source_manifest.json', 'text_methods': REL + 'text_methods.md', 'finance_methods': REL + 'finance_methods.md', 'full_documentary': REL + 'documentary_full.json', 'direct_links': REL + 'manual_direct_links.csv', 'finance_years': REL + 'finance_fp_years.csv', 'finance_sources': REL + 'finance_source_years.csv', 'targets_all_editions': REL + 'targets_all_editions.csv', 'demographic_context': REL + 'rosstat_life_expectancy_2023.csv', 'code': 'downloads/code/platform/build_longlife_documentary.py'}}
    validation = {'passed': True, 'source_documents': len(inputs['source_documents']), 'finance_total_thousand_rub': finance['totalThousandRub'], 'national_total_thousand_rub': finance['nationalThousandRub'], 'national_minus_federal_thousand_rub': finance['nationalMinusFederalThousandRub'], 'finance_common_cells': 66, 'finance_full_cells': 120, 'finance_horizons_without_later_years': ['Д9', 'ДА'], 'source_reconciliation_cells': len(finance['sourceReconciliation']), 'hhi': finance['hhi'], 'target_cells': targets['target_cells'], 'numeric_targets': targets['numeric_targets'], 'target_records_all_editions': len(tables['targets']), 'same_genre_cosine_pairs': len(text['documentSimilarity']), 'same_genre_profile_tokens': text['sameGenreTokenCount'], 'thematic_cells': len(text['frameScores']), 'comparable_projects': len(text['projectSimilarity']), 'direct_reviewed_edges': 24, 'direct_reviewed_results': 4, 'direct_reviewed_indicators': 6, 'shared_task_pairs': 282, 'semantic_candidates': 160, 'node_types': dict(collections.Counter(node['kind'] for node in network['nodes'])), 'demographic_ages': len(config['demographicContext']['ageSex'])}
    if verify:
        replication = verify_text(inputs, doc)
        dump(download / 'text_replication_validation.json', replication)
        validation['text_replication'] = replication
    dump(download / 'documentary_full.json', doc)
    text['documentFiles'] = []
    for source in text['documents']:
        did = source['document_id']
        units = [r for r in text['units'] if r['document_id'] == did]
        kwic = [r for r in text['kwic'] if r['document_id'] == did]
        name = hashlib.sha256(did.encode()).hexdigest()[:20] + '.json'
        path = f'data/projects/{PROJECT}/text/' + name
        dump(root / 'public' / path, {'document_id': did, 'units': units, 'kwic': kwic})
        text['documentFiles'].append({'document_id': did, 'path': path, 'units': len(units), 'kwic': len(kwic)})
    text['unitCount'], text['kwicCount'] = len(text['units']), len(text['kwic'])
    text['units'], text['kwic'], text['lazyText'] = [], [], True
    finance['cashflowCount'], finance['cashflows'] = len(finance['cashflows']), []
    dump(root / f'public/data/projects/{PROJECT}/documentary.json', doc)
    dump(root / f'public/data/projects/{PROJECT}/targets.json', targets)
    csv_rows(download / 'finance_projects.csv', [{k: v for k, v in p.items() if k not in {'years', 'fullYears'}} for p in finance['projects']])
    for name, rows in [('finance_reconciliation', finance['reconciliation']), ('finance_cashflows', tables['f_cashflows']), ('finance_horizons', finance['horizonSummaries']), ('finance_source_years', finance['sourceYears']), ('finance_source_summaries', finance['sourceSummaries']), ('targets_all_editions', tables['targets']), ('targets_selected', selected_targets), ('network_shared_task', tables['result_indicator_shared_task']), ('network_semantic_candidates', tables['semantic_candidates']), ('document_similarity', text['documentSimilarity']), ('stemming_sensitivity', tables['stemming_project_sensitivity']), ('frame_scores', tables['frame_scores']), ('frame_totals_same_genre', text['frameTotals'])]:
        csv_rows(download / (name + '.csv'), rows)
    csv_rows(download / 'finance_fp_years.csv', [{'code': p['code'], 'name': p['name'], **r} for p in finance['projects'] for r in p['fullYears']])
    validation.update(runtime_json_bytes=(root / f'public/data/projects/{PROJECT}/documentary.json').stat().st_size, lazy_document_files=len(text['documentFiles']), all_text_units=text['unitCount'], all_kwic_contexts=text['kwicCount'])
    assert validation['runtime_json_bytes'] < 6_000_000
    dump(download / 'documentary_validation.json', validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return doc


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--verify-text', action='store_true')
    args = parser.parse_args()
    build(args.root.resolve(), args.verify_text)
