#!/usr/bin/env python3
"""Build Health Technologies views from source packets without a network or SQLite.

The routine build does not overwrite the verified source snapshot. A copied
candidate needs scripts, published data and downloads only, not inputs/.
"""
from __future__ import annotations

import argparse
import collections
import json
from decimal import Decimal
from pathlib import Path

from healthtech_data import ROOT, PROJECT, DATA, DOWNLOADS, REPORT_DATE, load, atomic, sha256, csv_write, CSV_FIELDS


def latest(rows, valid=False):
    pool = [r for r in rows if r.get('analytical_value' if valid else 'value') is not None]
    return max(pool,key=lambda r:(r['period_end'],r['frequency']=='annual')) if pool else None


def make_source(config, packet, status):
    sid = config['indicator_id']
    rows = packet['observations']
    source = {key:value for key,value in config.items() if key not in {'field_overrides','dimension_defaults','titles','first_year','min_regional_count','export_format'}}
    good = latest(rows,True)
    interpretable_period = latest([r for r in rows if not any(f['code']=='monthly_cell_for_annual_indicator' for f in r['quality_flags'])])
    source.update(id=sid,available=any(r['value'] is not None for r in rows),
                  origin_kind=packet['origin_kind'],direct_emiss_verified=packet.get('direct_emiss_verified',False),
                  published_at=packet['published_at'],acquired_at=packet.get('acquired_at'),verified_at=packet.get('verified_at'),
                  published_at_semantics=packet.get('published_at_semantics','source_update_date_in_republished_workbook'),last_success=status.get('last_success'),
                  last_checked_at=status.get('checked_at'),refresh_state=status.get('state'),snapshot_id=packet['snapshot_id'],
                  observation_count=len(rows),numeric_count=sum(r['value'] is not None for r in rows),
                  missing_count=sum(r['value'] is None for r in rows),usable_count=sum(r['analytical_value'] is not None for r in rows),
                  excluded_numeric_count=sum(r['value'] is not None and r['excluded'] for r in rows),
                  national=rows,annual=[r for r in rows if r['frequency']=='annual'],annual_equivalents=[],
                  latest_national=good or interpretable_period or latest(rows),latest_published=latest(rows),latest_analytically_usable=good,
                  latest_national_selection='latest_analytically_usable_else_reviewable_period_else_latest_published',
                  regional_latest=[],regional_history=[],regional_periods=[],regional_slices=[],other_territories=[],
                  geography_scope='national_only',geography_note='Все восстановленные наблюдения относятся к Российской Федерации. Региональные различия по этим данным не рассчитываются.',
                  downloads={'observations':f'data/projects/{PROJECT}/series/{sid}.json',
                             'provenance':f'data/projects/{PROJECT}/provenance/{sid}.json',
                             'csv':f'downloads/projects/{PROJECT}/statistics/series/{sid}.csv'})
    if packet['snapshot_id'] and packet['snapshot_id'].startswith('nsedc:'):
        source['downloads']['source_input'] = f'downloads/projects/{PROJECT}/statistics/inputs/{sid}.zip'
    elif packet.get('source_input'):
        source['downloads']['source_input'] = packet['source_input']
    codes = {}
    for row in rows:
        for flag in row['quality_flags']:
            group = codes.setdefault(flag['code'],{**flag,'cells':0,'numeric_cells':0})
            group['cells'] += 1
            group['numeric_cells'] += row['value'] is not None
    source['quality_flags'] = list(codes.values())
    source['gaps'] = []
    if sid == '62988' and rows:
        periods = {r['period'] for r in rows}
        if '2026-06' not in periods and {'2026-05','2026-07'} <= periods:
            source['gaps'].append({'period':'2026-06','frequency':'monthly','kind':'absent_source_row',
                                   'message':'Июньская строка отсутствует в исходной таблице; наблюдение не создано и значение не интерполировано.'})
    return source


def coverage(cards, sources):
    result = {'registry_indicators':len(cards),'confirmed_sources':len(sources),'available_sources':sum(s['available'] for s in sources),
              'observations':sum(s['observation_count'] for s in sources),'numeric_observations':sum(s['numeric_count'] for s in sources),
              'missing_observations':sum(s['missing_count'] for s in sources),'usable_observations':sum(s['usable_count'] for s in sources),
              'excluded_numeric_observations':sum(s['excluded_numeric_count'] for s in sources),
              'annual_facts':sum(r['value'] is not None and not r['excluded'] for s in sources for r in s['annual']),
              'regional_sources':0,'territories':1,'regions':0,'by_federal_project':[]}
    for code in [None,'С1','С2','С3','С4','С5']:
        group = [c for c in cards if c['federal_project_code']==code]
        sourceids = {sid for c in group for sid in c['source_ids']}
        relevant = [s for s in sources if s['id'] in sourceids]
        result['by_federal_project'].append({'code':code or 'С','title':'Национальный проект' if code is None else group[0]['federal_project_name'],
                                            'registry_indicators':len(group),'confirmed_sources':len(relevant),
                                            'available_sources':sum(s['available'] for s in relevant),
                                            'numeric_observations':sum(s['numeric_count'] for s in relevant),
                                            'missing_observations':sum(s['missing_count'] for s in relevant)})
    return result


def read_targets(root):
    path = root / DATA / 'targets.json'
    if not path.exists():
        return []
    data = load(path)
    return data if isinstance(data,list) else data.get('items',[])


def canonical_unit(value):
    return {'%':'процент','проценты':'процент','ед.':'единица','единиц':'единица','млн руб.':'миллион рублей'}.get(str(value).casefold().strip(),str(value).casefold().strip())


def target_comparisons(sources, targets):
    by_id = {s['id']:s for s in sources}
    result = []
    for target in targets:
        sid = str(target.get('source_id') or '')
        source = by_id.get(sid)
        if not source or not source['target_comparison_allowed'] or target.get('mapping_status')=='conditional':
            continue
        if canonical_unit(target.get('unit')) != canonical_unit(source['unit']):
            continue
        for year, target_value in target.get('years',{}).items():
            if target_value is None:
                continue
            annual = [r for r in source['annual'] if r['year']==int(year) and r['analytical_value'] is not None]
            if len(annual)!=1:
                continue
            row = annual[0]
            difference = float(Decimal(str(row['value']))-Decimal(str(target_value)))
            ratio = float(Decimal(str(row['value']))/Decimal(str(target_value))*100) if target_value else None
            result.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'target_year':int(year),
                           'target_value':target_value,'fact_value':row['value'],'fact_period':row['period'],'fact_frequency':'annual',
                           'difference':difference,'difference_unit':'п.п.' if source['unit']=='процент' else source['display_unit'],
                           'unit':source['unit'],'display_unit':source['display_unit'],'ratio_percent':ratio,
                           'comparison_kind':'annual_fact_vs_annual_plan','annual_comparison_eligible':True,'formal_attainment_eligible':False,
                           'direct_emiss_verified':row['origin_kind']=='live_emiss','reference_observation_id':row['id'],
                           'target_source':target,'interpretation':'Арифметическое сопоставление одного опубликованного годового значения с выбранной редакцией плана. Не является интегральной оценкой проекта или причинного эффекта.'})
    return result


def changes(sources):
    matched, within = [], []
    eligible = {'63130','63132','62988','63445','63446','63447','63062'}
    for source in sources:
        if source['id'] not in eligible:
            continue
        good = [r for r in source['national'] if r['analytical_value'] is not None]
        for row in good:
            prior = [r for r in good if r['year']==row['year']-1 and r['frequency']==row['frequency'] and r['month']==row['month'] and r['quarter']==row['quarter']]
            if len(prior)==1:
                old = prior[0]
                delta = float(Decimal(str(row['value']))-Decimal(str(old['value'])))
                matched.append({'source_id':source['id'],'title':source['short_title'],'from_period':old['period'],'to_period':row['period'],
                                'from_value':old['value'],'to_value':row['value'],'difference':delta,
                                'relative_change_percent':float(Decimal(str(delta))/Decimal(str(old['value']))*100) if old['value'] else None,
                                'unit':source['unit'],'difference_unit':'п.п.' if source['unit']=='процент' else source['display_unit'],
                                'reference_observation_ids':[old['id'],row['id']], 'comparison_kind':'same_calendar_slice',
                                'interpretation':source['period_note']})
        grouped = collections.defaultdict(list)
        for row in good:
            grouped[(row['year'],row['frequency'])].append(row)
        for (_,frequency), rows in grouped.items():
            rows.sort(key=lambda r:r['period_end'])
            if len(rows)<2 or rows[-1]['period']==rows[0]['period']:
                continue
            first,last = rows[0],rows[-1]
            delta = float(Decimal(str(last['value']))-Decimal(str(first['value'])))
            within.append({'source_id':source['id'],'title':source['short_title'],'from_period':first['period'],'to_period':last['period'],
                           'from_value':first['value'],'to_value':last['value'],'difference':delta,
                           'unit':source['unit'],'difference_unit':'п.п.' if source['unit']=='процент' else source['display_unit'],
                           'reference_observation_ids':[first['id'],last['id']], 'comparison_kind':'within_calendar_year',
                           'interpretation':source['period_note']})
    return matched,within


def annual_december(sources):
    result = []
    for source in sources:
        for row in source['annual']:
            if row['value'] is None:
                continue
            december = next((r for r in source['national'] if r['year']==row['year'] and r['frequency']=='monthly' and r['month']==12),None)
            if december:
                result.append({'source_id':source['id'],'year':row['year'],'annual_value':row['value'],'december_value':december['value'],
                               'annual_observation_id':row['id'],'december_observation_id':december['id'],
                               'same_value':row['value']==december['value'],'interpretation':'Тип периода сохранён. Декабрьская ячейка не заменяет самостоятельную годовую запись.'})
    return result


def reconciliation(sources):
    by_id = {s['id']:s for s in sources}
    def dec(sid):
        return next((r for r in by_id[sid]['national'] if r['period']=='2025-12' and r['value'] is not None),None)
    amount,growth = dec('63132'),dec('62987')
    if not amount or not growth:
        return None
    baseline = Decimal('91')
    implied = (Decimal(str(amount['value']))/baseline-1)*100
    return {'published_amount':amount['value'],'amount_unit':'млн руб.','published_growth':growth['value'],'growth_unit':'%',
            'assumed_baseline_2023':91,'baseline_unit':'млн руб.','baseline_status':'author_report_transcription',
            'baseline_source':'Авторская экспертиза, раздел 3.5, абзац о согласовании денежного прокси и прироста к 2023 году.',
            'mechanical_implied_growth':float(implied),'difference_from_published_growth':float(implied-Decimal(str(growth['value']))),
            'reference_observation_ids':[amount['id'],growth['id']],
            'interpretation':'Условная арифметическая проверка доступных агрегатов. Несовпадение не доказывает ошибку ведомства: состав учреждений, база, компоненты и редакции не согласованы. Показатели не исправляются и не подменяются друг другом.'}


def methods(coverage_data):
    specs = [
      ('source_quality','Проверка исходных ячеек','computed','Исходные ячейки сохранённой републикации CSV сверены с оригинальным XLS. Числа, пропуски и единицы сохранены; прямые обновления проходят отдельную проверку контракта.'),
      ('observability','Наблюдаемость показателей','computed',f"{coverage_data['available_sources']} публикаций содержат {coverage_data['numeric_observations']} числовых ячеек. Все наблюдения относятся к Российской Федерации."),
      ('time_dynamics','Сопоставимые временные изменения','computed_with_period_contracts','Сравниваются одинаковые календарные срезы и отдельно изменения внутри года. Перекрывающиеся окна, месячные нули годовых показателей и разрывы методик ограничивают выводы.'),
      ('target_comparison','Годовой факт и план','annual_only_comparison',f"Найдено самостоятельных пригодных годовых фактов: {coverage_data['annual_facts']}. Декабрьские и квартальные записи не объявляются годовыми."),
      ('forecasting','Прогноз достижения целей','insufficient_independent_annual_history','Вероятностный прогноз и экстраполяция не рассчитаны. Нужны независимая сопоставимая история, состав портфеля и проверенные переходы между стадиями.'),
      ('regional_comparison','Сравнение регионов','ineligible_no_regional_observations','Наблюдения по субъектам России отсутствуют в восстановленных публикациях. Значение РФ не копируется в регионы.'),
      ('regional_pca','Главные компоненты и региональные профили','ineligible_no_regional_matrix','Нет региональной матрицы объектов и признаков; PCA и кластеризация не применяются.'),
      ('spatial_autocorrelation','Пространственная автокорреляция','ineligible_no_regional_observations','Индексы Морана и локальные кластеры не вычисляются без сопоставимых территориальных наблюдений.'),
      ('causal_evaluation','Оценка причинного эффекта','ineligible_no_counterfactual_design','Агрегаты РФ не содержат контрольной группы, даты внедрения и результатов сопоставимых объектов; DiD, RDD и причинный ATT не оцениваются.'),
      ('clinical_effectiveness','Клиническая доказательность','requires_patient_level_design','Регистрационные допуски и счётчики технологий не измеряют сравнительный клинический эффект. Нужны дизайн, компаратор, исходы и сроки наблюдения.'),
      ('cost_effectiveness','Экономическая оценка технологий','requires_cost_and_outcome_components','ICER и QALY не рассчитываются из финансового плана и агрегатов коммерциализации без сопоставимых затрат и исходов.'),
      ('portfolio_scenarios','Сценарии технологического портфеля','user_assumptions_only','Условные сценарии задаются пользователем. Вероятности прохождения стадий не оценены по открытым данным.'),
      ('publication_semantics','Проверка периода и редакции','computed','В исходной републикации годовой факт 4,55% отделён от декабрьского нуля. Квартальная ВДС с неоднозначной редакцией заблокирована для сравнения с целью.'),
      ('commercialization_check','Согласование показателей коммерциализации','conditional_arithmetic_check','Проверка суммы и прироста к базе показывает необходимость раскрытия компонентов. Условная база 91 млн руб. имеет статус транскрипции авторского отчёта.')]
    return [{'project_id':PROJECT,'method_id':mid,'method_name':name,'section_number':i+1,'current_status':status,'status':status,
             'current_limitations':note,'evidence_scope':'health_technologies_project_specific','numeric_indicators':coverage_data['available_sources'],
             'regional_indicators':0,'multivariate_input_status':'no_regional_matrix'} for i,(mid,name,status,note) in enumerate(specs)]


def build(root=ROOT):
    root = Path(root)
    configs = load(root/'scripts/healthtech_emiss_sources.json')['sources']
    cards = load(root/DATA/'indicators.json')['items']
    status = load(root/DATA/'refresh-status.json')
    states = {s['source_id']:s for s in status['sources']}
    sources, all_rows = [], []
    for config in configs:
        sid = config['indicator_id']
        packet = load(root/DATA/'series'/(sid+'.json'))
        if packet['source_id']!=sid or packet['project_id']!=PROJECT or packet['unit']!=config['unit']:
            raise ValueError('Source packet identity mismatch')
        provenance = load(root/DATA/'provenance'/(sid+'.json'))
        if provenance['published_sha256'] != sha256(root/DATA/'series'/(sid+'.json')):
            raise ValueError('Source packet does not match verified provenance: ' + sid)
        sources.append(make_source(config,packet,states.get(sid,{})))
        all_rows.extend(packet['observations'])
        csv_write(root/DOWNLOADS/'series'/(sid+'.csv'),packet['observations'],CSV_FIELDS)
    cover = coverage(cards,sources)
    numeric_rows = [r for r in all_rows if r['value'] is not None]
    meta = {'project_id':PROJECT,'report_as_of':REPORT_DATE,
            'statistical_as_of':max([s['published_at'] for s in sources if s['published_at']],default=None),
            'acquired_at':max([s['acquired_at'] for s in sources if s['acquired_at']],default=None),
            'latest_observation_period':max([r['period'] for r in numeric_rows],default=None),
            'origin_kind':'mixed_verified_sources' if any(s['direct_emiss_verified'] for s in sources) else 'secondary_emiss_republication',
            'direct_emiss_verified':bool(sources) and all(s['direct_emiss_verified'] for s in sources if s['available']),
            'origin_note':'Статистические публикации ЕМИСС сохранены в открытом репозитории НЦСЭД. Дата получения, дата обновления данных во встроенном паспорте и отчётный период различаются. Прямая актуальность оригинала подтверждается только отдельным успешным обновлением.',
            'geography_scope':'national_only','missing_policy':'preserved_without_zero_fill_or_interpolation',
            'latest_selection_note':'Последнее пригодное наблюдение выбирается с учётом типа периода и флагов. Все более поздние исходные ячейки доступны в полной таблице.'}
    statistics = {'schema_version':1,'project_id':PROJECT,'meta':meta,'summary':cover,'registry':cards,'sources':sources}
    targets = read_targets(root)
    matched,within = changes(sources)
    method_rows = methods(cover)
    analytics = {'schema_version':1,'project_id':PROJECT,'meta':meta,'coverage':cover,
                 'target_comparisons':target_comparisons(sources,targets),'annual_december_audit':annual_december(sources),
                 'matched_period_changes':matched,'within_year_changes':within,'commercialization_reconciliation':reconciliation(sources),
                 'quality_summary':dict(collections.Counter(flag['code'] for r in all_rows for flag in r['quality_flags'])),
                 'forecast_eligibility':[{'source_id':s['id'],'title':s['short_title'],'annual_observations':sum(r['analytical_value'] is not None for r in s['annual']),
                                          'eligible':False,'status':'insufficient_independent_annual_history' if s['id']!='63059' else 'methodology_break_unresolved',
                                          'reason':'Проверенная прогнозная модель отсутствует; частые оперативные клетки не заменяют независимые сопоставимые годовые наблюдения.'} for s in sources],
                 'territorial_readiness':{'eligible':False,'available_regions':0,'status':'national_only','reason':'Нет региональных наблюдений. Для территориальной оценки нужны место проживания, маршрутизация и сведения об организациях.'},
                 'clinical_readiness':{'eligible':False,'status':'administrative_outputs_only','reason':'Счётчики продуктов и доли пациентов не содержат сравнения клинических исходов.'},
                 'diagnostics':{'pca':{'eligible':False,'reason':'Нет региональной матрицы'},'clustering':{'eligible':False,'reason':'Нет сопоставимых объектов'},
                                'moran':{'eligible':False,'reason':'Нет региональных наблюдений'},'causal':{'eligible':False,'reason':'Нет контрфактического дизайна'}},
                 'methods':method_rows}
    atomic(root/DATA/'statistics.json',statistics)
    atomic(root/DATA/'analytics.json',analytics)
    atomic(root/DATA/'methods.json',{'schema_version':1,'project_id':PROJECT,'items':method_rows})
    csv_write(root/DOWNLOADS/'observations.csv',all_rows,CSV_FIELDS)
    csv_write(root/DOWNLOADS/'target_comparisons.csv',analytics['target_comparisons'],['source_id','indicator_code','target_year','target_value','fact_value','fact_period','fact_frequency','difference','difference_unit','ratio_percent','comparison_kind','reference_observation_id'])
    csv_write(root/DOWNLOADS/'matched_period_changes.csv',matched,['source_id','title','from_period','to_period','from_value','to_value','difference','difference_unit','relative_change_percent','reference_observation_ids'])
    csv_write(root/DOWNLOADS/'within_year_changes.csv',within,['source_id','title','from_period','to_period','from_value','to_value','difference','difference_unit','reference_observation_ids'])
    csv_write(root/DOWNLOADS/'method_eligibility.csv',method_rows,['method_id','method_name','current_status','current_limitations'])
    atomic(root/DOWNLOADS/'annual_december_audit.json',analytics['annual_december_audit'])
    atomic(root/DOWNLOADS/'commercialization_reconciliation.json',analytics['commercialization_reconciliation'])
    return {'project_id':PROJECT,**cover,'target_comparisons':len(analytics['target_comparisons'])}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.root),ensure_ascii=False))
