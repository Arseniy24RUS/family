#!/usr/bin/env python3
"""Assemble the Personnel expertise without rewriting the supplied report."""
from pathlib import Path
import argparse, csv, hashlib, json, re, shutil, subprocess, sys

DEFAULT_APP=Path(__file__).resolve().parents[1]
def span(a,b):return list(range(a,b+1))
def norm(s):return re.sub(r'\W+','',s.lower().replace('ё','е'))

def build(app,src,render=None):
    cache=app/'.cache/personnel_expertise';cache.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(app/'scripts/extract_personnel_report.py'),'--docx',str(src),'--output',str(cache)],check=True,stdout=subprocess.DEVNULL)
    report=json.loads((cache/'extraction.json').read_text());blocks={b['index']:b for b in report['blocks']}
    base='downloads/projects/personnel/report/';dest=app/'public'/base;dest.mkdir(parents=True,exist_ok=True)
    locator_path=app/'inputs/personnel/report/report_page_locations.json'
    locators=json.loads(locator_path.read_text()) if locator_path.exists() else {}
    if locators.get('source_docx_sha256')!=report['sha256']:locators={}
    page_text=[]
    if render:
        try:
            import fitz
            with fitz.open(next(render.glob('*.pdf'))) as doc:page_text=[norm(p.get_text()) for p in doc]
        except (ImportError,StopIteration):pass
    def locate(txt):
        q=norm(txt)[:95]
        if len(q)<15:return None
        if page_text:return next((i+1 for i,p in enumerate(page_text) if i>=3 and q in p),None)
        return locators.get('locations',{}).get(norm(txt))
    sources=[{'id':'report','title':'Экспертиза национального проекта «Кадры», 2026','text':'Предоставленный авторский отчёт. Нормативный срез – 27 октября 2026 года, статистический – 15 октября, документальный – 19 октября.','url':base+'expertise_personnel_2026.docx','kind':'author_report','sha256':report['sha256']}]
    for f in report['footnotes']:
        urls=[x.rstrip('.,;') for x in f['urls']]
        sources.append({'id':f"fn_{f['id']:03d}",'title':f['paragraphs'][0].strip(),'text':f['text'],'url':urls[0] if urls else sources[0]['url'],'urls':urls,'paragraphs':f['paragraphs'],'note_number':f['id'],'kind':'source_note','source_blocks':[f'b{i}' for i in f['referenced_by']]})
    def nearby_ids(a,b):return list(dict.fromkeys(['report']+[f'fn_{n:03d}' for i in range(a,b+1) for n in blocks.get(i,{}).get('footnotes',[])]))
    tables=[]
    for t in report['tables']:
        i,n=t['index'],t['number'];title=blocks.get(i-1,{}).get('text',f'Таблица {n}');note=blocks.get(i+1,{}).get('text','')
        if not note.startswith('Примечание.'):note=''
        columns=[{'key':f'c{k}','label':v,'title':v} for k,v in enumerate(t['rows'][0])]
        tables.append({'id':f'table_{n:02d}','number':n,'type':'table','sourceBlock':f'b{i}','title':title,'columns':columns,'rows':[{f'c{k}':v for k,v in enumerate(r)} for r in t['rows'][1:]],'note':note,'sourceIds':nearby_ids(i-2,i+1),'page':locate(title)})
    tm={t['sourceBlock']:t for t in tables};figures=[]
    implementations=['observation_calendar','plan_participation','training_employment','disability_workplace_targets','quarterly_prestige','finance_allocation','finance_year_matrix','finance_horizons','regional_unemployment_context','shared_task_routes','reviewed_direct_links','domain_matrix','same_genre_tfidf_matrix','stemming_sensitivity']
    for n,f in enumerate(report['figures'],1):
        i=f['block'];title=blocks[i+1]['text'];note=blocks[i+2].get('text','');filename=f'figure_{n:02d}'+Path(f['path']).suffix
        shutil.copy2(cache/f['path'],dest/filename)
        figures.append({'id':f'figure_{n:02d}','number':n,'title':title,'caption':title,'note':note,'url':base+filename,'sourceBlock':f'b{i}','page':locate(title),'sourceIds':nearby_ids(i-1,i+2),'implementation':implementations[n-1],'original_sha256':f['sha256'],'role':'faithful_source_illustration','interactive_data':'documentary.json or analytics.json; source images do not substitute numeric inputs'})
    fm={f['sourceBlock']:f for f in figures}
    formula_by_paragraph={
      159:('КЗₜ = ЗФₜ / ЗБₜ × 100%',r'\text{КЗ}_t=\frac{\text{ЗФ}_t}{\text{ЗБ}_t}\times100\%'),
      161:('ЗБₜ = Σⱼ₌₁¹¹ Нⱼₜ × УЗБⱼ / 100%',r'\text{ЗБ}_t=\sum_{j=1}^{11}\text{Н}_{jt}\frac{\text{УЗБ}_j}{100\%}'),
      169:('Pₜ = Nфакт,ₜ / Nплан,ₜ × 100%',r'P_t=\frac{N_{\text{факт},t}}{N_{\text{план},t}}\times100\%'),
      220:('HHI = Σᵢ₌₁⁴ sᵢ²; sᵢ = Bᵢ / Σⱼ₌₁⁴ Bⱼ',r'HHI=\sum_{i=1}^{4}s_i^2,\quad s_i=\frac{B_i}{\sum_{j=1}^{4}B_j}'),
      349:('ATT = E[Y(1) − Y(0) | D = 1]',r'ATT=E[Y(1)-Y(0)\mid D=1]'),
      363:('Cдоп = Cпрограмма / (N × ATT)',r'C_{\text{доп}}=\frac{C_{\text{программа}}}{N\times ATT}')}
    def convert(i):
        b=blocks[i];common={'id':f'b{i}','sourceBlock':i,'sourceIds':nearby_ids(i,i),'page':locate(b.get('text',''))}
        if f'b{i}' in tm:return {**tm[f'b{i}'],**common,'id':tm[f'b{i}']['id'],'sourceIds':tm[f'b{i}']['sourceIds'],'page':tm[f'b{i}']['page']}
        if f'b{i}' in fm:
            f=fm[f'b{i}'];return {**common,'type':'figure_ref','figureId':f['id'],'title':f['title'],'note':f['note'],'url':f['url'],'page':f['page'],'sourceIds':f['sourceIds']}
        p=b.get('paragraph_index')
        if p in formula_by_paragraph:return {**common,'type':'formula','text':formula_by_paragraph[p][0],'latex':formula_by_paragraph[p][1],'number':int(re.sub(r'\D','',b['text']))}
        txt=b.get('text','')
        if not txt or b.get('images') or b.get('style')=='Caption':return None
        if (f'b{i-1}' in tm or f'b{i-2}' in fm) and txt.startswith('Примечание.'):return None
        level=re.search(r'Heading(\d)',b.get('style',''))
        return {**common,'type':'heading','level':min(int(level.group(1))+1,4),'text':txt} if level else {**common,'type':'paragraph','text':txt}
    para_routes={
      'overview':span(53,61)+span(368,374),'framework':span(62,87),'structure':span(88,100),'logic':span(101,138),
      'audit':span(139,155)+span(375,378),'targets':span(156,207),'projections':span(208,211),
      'finance':span(212,239)+span(379,382),'map':span(240,251),'population':span(252,260),
      'network':span(261,299),'domains':span(300,314),'texts':span(315,329),'proposals':span(330,345),
      'causal':span(346,367),'methods':span(383,391),'regions':[],'lab':[],'explorer':[],'library':[],'updates':[]}
    par_to_route={p:k for k,v in para_routes.items() for p in v};mapping={k:[] for k in para_routes}
    for b in report['blocks']:
        p=b.get('paragraph_index')
        if b['type']=='table':p=blocks[b['index']-1].get('paragraph_index')
        if p in par_to_route:mapping[par_to_route[p]].append(b['index'])
    titles={'overview':'Обзор и основные выводы','framework':'Предмет и теоретическая рамка','structure':'Стратегическая архитектура','logic':'Механизмы четырёх федеральных проектов','audit':'Аудит системы показателей','targets':'Показатели и целевые ориентиры','map':'Территориальный контекст рынка труда','regions':'Региональные условия и доступность','finance':'Плановое финансирование','network':'Документальные связи','texts':'Текстовый анализ','domains':'Тематические сферы','causal':'Оценка дополнительного результата','proposals':'Предложения по совершенствованию','lab':'Лаборатория расчётов','explorer':'Данные ЕМИСС','library':'Источники и код','updates':'Обновление данных','projections':'Траектории к целям','population':'Трудовые траектории и целевые группы','methods':'Методы и воспроизводимость'}
    summaries={
      'overview':'Проект соединяет кадровое прогнозирование, развитие службы занятости, переход от образования к работе, адресную поддержку и повышение общественной значимости труда. Основной резерв – прослеживаемая связь меры, трудовой траектории человека и результата работодателя.',
      'framework':'Экспертиза различает кадровую потребность, квалификационное несоответствие, издержки поиска и барьеры участия в труде. Наблюдение результата требует совместного рассмотрения положения человека, работодателя и территории.',
      'structure':'Четыре федеральных проекта охватывают инфраструктуру управления, образование, адресные меры и общественное восприятие труда. Сопряжение с молодёжной, семейной, территориальной политикой и производительностью проверяется на уровне переходов получателей.',
      'logic':'Л1 развивает кадровый прогноз и службу занятости, Л2 соединяет образование с применением квалификации, Л3 обеспечивает обучение, найм, адаптацию и мобильность, Л4 воздействует на информированность и отношение к профессиям. Для каждого механизма нужны собственные проверяемые исходы.',
      'audit':'Реестр включает два национальных и девять федеральных показателей. В статистическом срезе экспертизы доступны пять показателей с числовыми данными и 60 общероссийских наблюдений. Причины отсутствия остальных рядов различаются и показаны отдельно.',
      'targets':'Пять сопоставлений за 2025 год используют два самостоятельных годовых факта и три методически обоснованных годовых эквивалента. Сравнения относятся к выбранным редакциям целей октября 2026 года. Индекс, отношение к плану и доли сохраняют собственный смысл.',
      'map':'Безработица 2024 года характеризует исходные условия до начала национального проекта. Карта содержит 85 региональных наблюдений и отдельный общероссийский агрегат. Контекстный показатель не измеряет территориальный результат мероприятий «Кадров».',
      'regions':'Региональная диагностика сопоставляет уровень безработицы с условиями поиска и доступности работы. Выбор мер требует сведений о вакансиях, квалификации, оплате, транспортной связанности и составе участников. Рейтинг эффективности проекта по одному контекстному показателю не рассчитывается.',
      'finance':'На активные меры приходится 54,48% суммы планов четырёх федеральных проектов за 2025–2030 годы. Федеральный итог составляет 178,80095131 млрд руб., национальный – 177,33160971 млрд руб. Разница 1,46934160 млрд руб. полностью относится к 2025 году.',
      'network':'Сеть содержит 32 карточки результатов, 11 показателей и 67 пар через общую задачу. Полный паспорт Л1 отдельно подтверждает десять прямых связей с сокращением времени трудоустройства. Паспортные веса распределяют заявленное влияние и не являются причинными коэффициентами.',
      'texts':'Косинусная близость рассчитывается по очищенным профилям документов. Внутрипроектное сравнение использует четыре федеральных HTML-паспорта одного жанра. Устойчивость ближайших национальных проектов проверяется русским стеммингом.',
      'domains':'Словарные частоты нормированы на объём профиля, а тематические категории пересекаются. Общий словарь не включает МРОТ и оплату труда в доходную категорию, поэтому словарный ноль в Л1 требует содержательного уточнения.',
      'causal':'Наблюдаемая занятость после программы не определяет дополнительный вклад поддержки. Оценка требует исходного статуса, прослеживаемой когорты, пригодного сравнения и заранее определённых трудовых результатов.',
      'proposals':'Приоритетны единый журнал трудового перехода, версионный учёт целей и прогнозов, наблюдение выпускных когорт, разделение исходной занятости и сочетаний мер, проверка устойчивости работы и пилоты оценки дополнительности.',
      'lab':'Изменение параметров показывает арифметику отношения к плану, возрастной стандартизации, концентрации финансирования и стоимости дополнительного результата. Пользовательский сценарий сохраняет статус условного расчёта.',
      'explorer':'В источниках сохранены период, частота, единица и режим накопления. Допустимое отношение к плановой численности может превышать 100%. Нули, пропуски и самостоятельные годовые итоги различаются.',
      'library':'Авторская экспертиза, исходные таблицы и иллюстрации, паспортные редакции, статистические ответы, документальные расчёты и код доступны вместе с контрольными суммами и происхождением.',
      'updates':'Новые ответы ЕМИСС проходят проверку источника, единицы, периода и структуры. Дата попытки получения отделена от даты последнего пригодного набора. При ошибке сохраняются последние проверенные наблюдения.',
      'projections':'Короткая история допускает расчёт расстояния до цели и условного требуемого изменения. Она не обеспечивает надёжной вероятностной оценки достижения целей к 2030 году. Плановая траектория отображается как документальный ориентир.',
      'population':'Первый вход, возвращение к работе, сохранение занятости, профессиональное продвижение, формализация и перемещение между территориями образуют разные трудовые результаты. Семейные обязанности, возраст, здоровье и локальные условия влияют на доступность маршрута.',
      'methods':'Сопоставимость определяется методом расчёта, совокупностью, частотой и редакцией. Финансы сверяются в исходной десятичной точности. Статистические, документальные и причинные выводы имеют разные основания.'}
    pages={}
    for route,ids in mapping.items():
        bb=[convert(i) for i in ids];bb=[b for b in bb if b]
        pages[route]={'id':route,'title':titles[route],'summary':summaries[route],'blocks':bb,'sources':list(dict.fromkeys(s for b in bb for s in b['sourceIds'])) or ['report'],'source_blocks':ids}
    extra={
      'regions':[
        'Региональное значение безработицы относится к населению в возрасте 15 лет и старше и к одному календарному году. Общероссийские 2,5% берутся из опубликованного агрегата. Среднее региональных процентов его не заменяет.',
        'Архангельская и Тюменская области сопоставляются без автономных округов. Территории без наблюдения сохраняются на карте с отдельным обозначением. Отсутствие значения не заменяется нулём.',
        'Сравнение регионов в интерфейсе характеризует различия исходного рынка труда. Для оценки результатов проекта нужны сведения об участниках, составе поддержки, завершении мер и последующей занятости в соответствующей территории.'],
      'lab':[
        'Отношение числа участников к плану равно фактической численности, делённой на плановую, и умноженной на 100. При положительном плане значение выше 100 допустимо. Нулевой знаменатель означает неопределённый расчёт, а не нулевой результат.',
        'Возрастной стандарт занятости строится суммированием населения текущего года, взвешенного по возрастным уровням занятости базового 2024 года. Отношение фактической занятости к стандарту разделяет часть демографических изменений и интенсивности участия в труде, но не идентифицирует влияние проекта.',
        'HHI равен сумме квадратов долей четырёх федеральных проектов в их общем плане. Индекс описывает концентрацию портфеля. Изменение долей в условном расчёте не устанавливает оптимальный бюджет.',
        'Стоимость дополнительного результата определяется как расходы программы, делённые на число участников и оценку дополнительности ATT. Для положительного причинного эффекта требуется самостоятельное оценочное исследование. При нулевом либо отрицательном эффекте стоимость положительного дополнительного результата по этой формуле не определяется.'],
      'explorer':[
        'Два самостоятельных годовых факта сохраняют приоритет перед оперативными записями. В частности, занятость завершивших обучение за 2025 год равна 81,3%, тогда как декабрьская оперативная запись составляет 80,2%.',
        'Декабрьские значения участия в активных мерах и оборудования рабочих мест, а также IV квартал престижа профессий имеют годовой статус по соответствующим методикам. Их использование в годовом сопоставлении не добавляет независимых наблюдений.',
        'По оборудованию рабочих мест накопление ведётся с начала мероприятия. Опубликованное снижение с 0,1766% в декабре 2025 года до 0,1699% в январе 2026 года сохраняется с пояснением о необходимости проверки пересмотра. Оно не исправляется сглаживанием.'],
      'library':[
        'Полный авторский отчёт сохранён без изменения. Текст распределён по тематическим страницам, включая 13 таблиц, 14 иллюстраций, 112 сносок и шесть формул. Исходные иллюстрации доступны как материалы источника, интерактивные графики используют палитру «Кадров».',
        'Документальный корпус включает пять электронных представлений паспортов, четыре правовые републикации, полный паспорт «Управления рынком труда» и презентацию. Электронная публикация DataBudget сопровождается датой и версией и не приравнивается к подписанному акту утверждения.'],
      'updates':[
        'Авторская экспертиза использует нормативные сведения по состоянию на 27 октября 2026 года, статистический срез на 15 октября и документальный корпус на 19 октября. Последующие пригодные загрузки меняют текущую статистику и вычисляемые панели. Авторский текст сохраняет собственную дату.',
        'Повторная публикация того же периода учитывается как пересмотр существующей записи. Ошибки загрузки и отсутствие числового ответа не изменяют дату последнего проверенного числового набора.']}
    extra_sources={'regions':['report','fn_077','fn_078','fn_079'],'lab':['report','fn_047','fn_052'],'explorer':['report','fn_057','fn_061','fn_071'],'library':['report'],'updates':['report']}
    for route,tt in extra.items():
        for n,txt in enumerate(tt,1):pages[route]['blocks'].append({'id':f'{route}_explanation_{n}','type':'paragraph','text':txt,'sourceIds':extra_sources[route],'origin':'platform_explanation_based_on_report'})
        pages[route]['sources']=extra_sources[route]
    short=[('Л1','Управление рынком труда','Кадровый прогноз и служба занятости','Прогноз, модернизация, цифровой подбор','Решение кадровой потребности и устойчивое трудоустройство','Полный клиентский маршрут, качество прогноза и его использование',102,110,[334,335]),('Л2','Образование для рынка труда','Переход к применению квалификации','Маршрутизация, центры карьеры, профессиональные стандарты','Устойчивая занятость выпускной когорты','Сопоставимые знаменатели, один и два года после выпуска, соответствие работы подготовке',111,119,[336]),('Л3','Активные меры содействия занятости','Обучение, найм, адаптация и мобильность','Программы подготовки и адресная поддержка','Дополнительный вход, сохранение работы и устойчивое использование адаптированного места','Исходный статус, сочетание мер, завершение и наблюдение после поддержки',120,131,[337,338]),('Л4','Человек труда','Информированность и профессиональный выбор','Коммуникации, конкурс, ярмарки трудоустройства','Переход от отношения к подтверждённому трудовому действию','Дизайн опроса, профессиональный выбор, контакт, собеседование и начало работы',132,138,[339])]
    byp={b.get('paragraph_index'):b for b in report['blocks'] if b['type']=='paragraph'}
    federal=[]
    for n,(code,name,focus,output,transition,verification,a,z,proposals) in enumerate(short,1):
        ids=[byp[p]['index'] for p in range(a+1,z+1)]
        federal.append({'id':f'l{n}','code':code,'name':name,'focus':focus,'output':output,'expectedTransition':transition,'verification':verification,'mechanismBlocks':[f'b{i}' for i in ids],'proposalBlocks':[f"b{byp[p]['index']}" for p in proposals],'sourceIds':nearby_ids(min(ids),max(ids))})
    registry=[]
    for row in report['tables'][10]['rows'][1:]:registry.append({'code':row[0],'name':row[1],'availability':row[2],'observations':int(row[3]),'sourceIds':['report','fn_110']})
    derived={'registry':registry,'federalProjects':federal,'populationGroups':[
      {'id':'entrants','name':'Первый вход и возвращение в занятость','age':'По статусу получателя','basis':'Выпускники, незанятые и возвращающиеся после перерыва','caveat':'Различать исходную незанятость, поиск работы и состояние вне рабочей силы.'},
      {'id':'workers','name':'Работающие участники обучения','age':'По условиям программы','basis':'Действующие работники и лица под риском увольнения','caveat':'Сохранение работы и повышение квалификации учитываются отдельно от нового входа.'},
      {'id':'older','name':'Люди старших возрастов','age':'Возрастная группа и статус указываются в конкретной мере','basis':'Добровольное продолжение или возвращение к работе','caveat':'Нужны условия труда, здоровье, адаптация рабочего места и качество занятости.'},
      {'id':'care','name':'Родители и лица с обязанностями ухода','age':'Универсальный возрастной диапазон не устанавливается','basis':'Согласование графика, пространственной доступности и условий семьи','caveat':'Обязанности ухода не означают отсутствия трудовой мотивации.'},
      {'id':'disability','name':'Получатели поддержки адаптации рабочего места','age':'По установленным условиям меры','basis':'Инвалидность, установленная квота и фактическое трудоустройство','caveat':'Показатель оборудованных мест не равен уровню занятости всех инвалидов.'},
      {'id':'mobility','name':'Участники трудовой мобильности','age':'По условиям программы','basis':'Исходная и принимающая территория, гражданство и статус занятости','caveat':'Прирост работников принимающей территории не тождественен приросту национальной занятости.'}],
      'proposalStages':[{'id':'definitions','order':1,'title':'Унификация определений и первичных записей','horizon':'До изменения количественных целей','result':'Проверены единицы, редакции и наблюдаемые события.'},{'id':'pilot','order':2,'title':'Пилот связанного наблюдения когорт','horizon':'После согласования данных и ресурсов','result':'В разных типах территорий проверены полнота данных и нагрузка исполнителей.'},{'id':'evaluation','order':3,'title':'Оценка результата и расширение','horizon':'По готовности сопоставимых данных','result':'Результаты пилота обосновывают корректировку мониторинга и масштаба поддержки.'}],
      'limits':[{'id':'regional','text':'Региональные ряды показателей проекта отсутствуют; безработица 2024 описывает отдельный контекст.'},{'id':'annual','text':'Два прямых годовых факта и три годовых эквивалента не образуют длинную историю для прогноза.'},{'id':'ratio','text':'Отношение к плановой численности допускает превышение 100%.'},{'id':'finance','text':'Паспортные суммы являются номинальными планами, не кассовым исполнением.'},{'id':'causal','text':'Причинные коэффициенты не оценены; паспортные веса отражают заявленное распределение.'},{'id':'dictionary','text':'Словарный ноль по доходам в Л1 не означает отсутствия МРОТ и оплаты труда.'}]}
    meta={'project_id':'personnel','title':'Экспертиза национального проекта «Кадры»','edition_date':'2026-10-27','statistical_snapshot':'2026-10-15','documentary_snapshot':'2026-10-19','source_docx_sha256':report['sha256'],'source_pages':len(page_text) or locators.get('source_pages'),'report_url':base+'expertise_personnel_2026.docx','download_url':base+'expertise_personnel_2026.docx','markdown_url':base+'expertise_personnel_2026.md','extract_url':base+'report_extraction.json','content_policy':'author_report_preserved; current_statistical_panels_update_separately','tables':len(tables),'figures':len(figures),'footnotes':len(report['footnotes']),'formulas':6,'report_sources_are_not_automatically_revised':True}
    out={'meta':meta,'pages':pages,'tables':tables,'figures':figures,'sources':sources,'derived':derived}
    target=app/'public/data/projects/personnel/expertise.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if src.resolve()!=(dest/'expertise_personnel_2026.docx').resolve():shutil.copy2(src,dest/'expertise_personnel_2026.docx')
    shutil.copy2(cache/'extraction.json',dest/'report_extraction.json')
    (dest/'expertise_personnel_2026.md').write_text((cache/'full_text.md').read_text()+'\n# Сноски и источники\n\n'+'\n\n'.join(f"[{f['id']}] {f['text']}" for f in report['footnotes'])+'\n',encoding='utf-8')
    for t in tables:
        with (dest/(t['id']+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.writer(f);wr.writerow([c['label'] for c in t['columns']]);wr.writerows([[r[c['key']] for c in t['columns']] for r in t['rows']])
    assigned=[i for vv in mapping.values() for i in vv]
    substantive=[b['index'] for b in report['blocks'] if (b.get('paragraph_index',53)>=53) and b['index']>=53 and (b.get('text') or b.get('images') or b['type']=='table')]
    missing=sorted(set(substantive)-set(assigned));duplicates=[i for i in set(assigned) if assigned.count(i)>1]
    assert not missing and not duplicates,(missing,duplicates)
    assert len(pages)==21 and len(tables)==13 and len(figures)==14 and len(report['footnotes'])==112
    summary={'report_pages':meta['source_pages'],'routes':len(pages),'substantive_blocks':len(substantive),'assigned_blocks':len(assigned),'unmapped_substantive_blocks':missing,'duplicate_assignments':duplicates,'tables':13,'figures':14,'footnotes':112,'formulas':6,'verified_page_locators':sum(b.get('page') is not None for p in pages.values() for b in p['blocks']),'blocks_by_page':{k:len(v['blocks']) for k,v in pages.items()}}
    coverage=[]
    for b in report['blocks']:
        i=b['index'];route=next((k for k,v in mapping.items() if i in v),None);item={'sourceBlock':i,'sourceType':b['type'],'sourceStyle':b.get('style'),'route':route}
        if i<53:item.update(status='original_docx_only',reason='Title, approval template and table of contents are preserved in the original DOCX and Markdown.')
        elif convert(i):item.update(status='rendered_block',target=convert(i)['id'])
        elif b.get('style')=='Caption':item.update(status='embedded_in_rendered_block',target=tm[f'b{i+1}']['id'] if f'b{i+1}' in tm else fm[f'b{i-1}']['id'],field='title')
        elif f'b{i-1}' in tm:item.update(status='embedded_in_rendered_block',target=tm[f'b{i-1}']['id'],field='note')
        elif f'b{i-2}' in fm:item.update(status='embedded_in_rendered_block',target=fm[f'b{i-2}']['id'],field='note')
        else:item.update(status='original_docx_only',reason='Blank formatting paragraph.')
        coverage.append(item)
    (dest/'coverage_manifest.json').write_text(json.dumps({'meta':meta,'summary':summary,'blocks':coverage},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if page_text:
        locator_path.parent.mkdir(parents=True,exist_ok=True)
        locations={norm(b.get('text','')):locate(b.get('text','')) for b in report['blocks'] if locate(b.get('text','')) is not None}
        locator_path.write_text(json.dumps({'source_docx_sha256':report['sha256'],'source_pages':len(page_text),'locations':locations},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2));return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=DEFAULT_APP);parser.add_argument('--docx',type=Path);parser.add_argument('--render-dir',type=Path);args=parser.parse_args()
    root=args.root.resolve();build(root,(args.docx or root/'public/downloads/projects/personnel/report/expertise_personnel_2026.docx').resolve(),args.render_dir)
