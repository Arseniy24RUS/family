"""Faithful DOCX-to-platform content assembly, Youth and Children, 2026.

This script preserves the source report text and its source notes. It does not
refresh statistics, infer missing values, or turn proposals into proven effects.
"""
from pathlib import Path
from decimal import Decimal
import json, re, shutil, hashlib, csv, subprocess, sys, argparse

DEFAULT_APP=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=DEFAULT_APP);ap.add_argument('--docx',type=Path);ap.add_argument('--render-dir',type=Path);args=ap.parse_args()
APP=args.root.resolve();ROOT=APP/'.cache/youth_expertise';ROOT.mkdir(parents=True,exist_ok=True)
SRC=(args.docx or APP/'public/downloads/projects/youth_children/report/expertise_youth_children_2026.docx').resolve()
RENDER=args.render_dir or ROOT/'render'
subprocess.run([sys.executable,str(APP/'scripts/extract_youth_report.py'),'--docx',str(SRC),'--output',str(ROOT)],check=True,stdout=subprocess.DEVNULL)
BASE='downloads/projects/youth_children/report/'
DEST=APP/'public'/BASE
DEST.mkdir(parents=True,exist_ok=True)
R=json.loads((ROOT/'extraction.json').read_text())
LOCATOR_PATH=APP/'inputs/youth/report/report_page_locations.json'
LOCATORS=json.loads(LOCATOR_PATH.read_text()) if LOCATOR_PATH.exists() else {}
if LOCATORS.get('source_docx_sha256')!=R['sha256']:LOCATORS={}
B={b['index']:b for b in R['blocks']}

def norm(s):return re.sub(r'\W+','',s.lower().replace('ё','е'))

# Rendered page locations are optional evidence metadata, never guessed.
page_text=[]
try:
    import fitz
    pdf=fitz.open(next(RENDER.glob('*.pdf')))
    page_text=[norm(p.get_text()) for p in pdf]
except (ImportError,StopIteration):pass

def locate(text,after=3):
    if not page_text:return LOCATORS.get('locations',{}).get(norm(text))
    q=norm(text)[:95]
    if len(q)<15:return None
    return next((i+1 for i,p in enumerate(page_text) if i>=after and q in p),None)

sources=[{'id':'report','title':'Экспертиза национального проекта «Молодёжь и дети», 2026',
          'text':'Предоставленный авторский отчёт. Анализ охватывает сведения по состоянию на 27 октября 2026 года; статистический срез – 15 октября, документальный – 19 октября.',
          'url':BASE+'expertise_youth_children_2026.docx','kind':'author_report','sha256':R['sha256']}]
for f in R['footnotes']:
    urls=[u.rstrip('.,;)') for u in f['urls']]
    sources.append({'id':f"fn_{f['id']:03d}",'title':f['paragraphs'][0].strip(),
                    'text':f['text'],'url':urls[0] if urls else sources[0]['url'],
                    'urls':urls,'paragraphs':f['paragraphs'],'note_number':f['id'],
                    'kind':'source_note','source_blocks':[f'b{i}' for i in f['referenced_by']]})
source_by_id={s['id']:s for s in sources}

formula={153:('Sгод = max(SI, SII, SIII, SIV)',r'S_{\text{год}}=\max(S_I,S_{II},S_{III},S_{IV})'),
178:('Δтреб = (T2030 − Y2025) / 5',r'\Delta_{\text{треб}}=(T_{2030}-Y_{2025})/5'),
197:('HHI = Σᵢ sᵢ²; sᵢ = Bᵢ / Σⱼ Bⱼ, i = 1,…,9',r'HHI=\sum_{i=1}^{9}s_i^2,\quad s_i=\frac{B_i}{\sum_j B_j}'),
354:('cos(a,b) = (vₐ · vᵦ) / (‖vₐ‖ ‖vᵦ‖)',r'\cos(a,b)=\frac{v_a\cdot v_b}{\lVert v_a\rVert\lVert v_b\rVert}')}

tables=[]
for raw in R['tables']:
    i=raw['index']; n=raw['number']; cap=B.get(i-1,{}).get('text',f'Таблица {n}')
    note=B.get(i+1,{}).get('text','')
    if not note.startswith('Примечание.'):note=''
    ids=['report']+[f'fn_{n:03d}' for n in B.get(i+1,{}).get('footnotes',[])]
    if n==1:ids+=['fn_001','fn_002','fn_003']
    if n==2:ids+=['fn_011','fn_012']
    if n==5:ids+=['fn_046','fn_047','fn_048']
    if n==6:ids+=['fn_055','fn_056']
    if n==7:ids+=['fn_060','fn_061','fn_062']
    if n==10:ids+=['fn_081']
    if n==11:ids+=['fn_049','fn_050']
    if n==12:ids+=['fn_052','fn_082']
    cols=[{'key':f'c{k}','label':t,'title':t} for k,t in enumerate(raw['rows'][0])]
    rows=[{f'c{k}':v for k,v in enumerate(r)} for r in raw['rows'][1:]]
    tables.append({'id':f'table_{n:02d}','number':n,'type':'table','sourceBlock':f'b{i}',
                   'title':cap,'columns':cols,'rows':rows,'note':note,'sourceIds':list(dict.fromkeys(ids)),
                   'page':locate(cap)})
table_map={t['sourceBlock']:t for t in tables}

figure_sources={1:[11,12],2:[27,28],3:[32,33],4:[40,41,45],5:[46,47,48],6:[49,50],7:[49,50],8:[52,53,54],9:[55,56],10:[57],11:[58],12:[63],13:[64],14:[65],15:[],16:[],17:[81]}
figure_implementations={1:'functional_grouping',2:'observation_availability',3:'same_month_participation',4:'teacher_and_school_timeseries',5:'annual_facts_and_targets',6:'federal_finance_totals',7:'federal_finance_year_matrix',8:'finance_reconciliation',9:'independent_regional_distributions',10:'teacher_map',11:'talents_map',12:'reviewed_direct_links_yu1',13:'reviewed_direct_links_yu4_yu9',14:'domain_matrix',15:'same_genre_tfidf_matrix',16:'stemming_sensitivity',17:'indicator_availability'}
figures=[]
for f in R['figures']:
    n=int(Path(f['path']).stem[5:]);i=f['block']
    cap=B[i+1]['text'];note=B[i+2]['text']
    dst=f'figure_{n:02d}.png';shutil.copy2(ROOT/f['path'],DEST/dst)
    figures.append({'id':f'figure_{n:02d}','number':n,'title':cap,'caption':cap,'note':note,
                    'url':BASE+dst,'sourceBlock':f'b{i}','page':locate(cap),
                    'sourceIds':['report']+[f'fn_{x:03d}' for x in figure_sources[n]],
                    'implementation':figure_implementations[n],'original_sha256':f['sha256'],
                    'role':'faithful_source_illustration','interactive_data':'documentary.json or analytics.json; original raster is not a numeric dataset'})
figure_map={f['sourceBlock']:f for f in figures}

def convert(i):
    b=B[i];ids=['report']+[f'fn_{x:03d}' for x in b.get('footnotes',[])]
    common={'id':f'b{i}','sourceBlock':i,'sourceIds':ids,'page':locate(b.get('text',''))}
    if f'b{i}' in table_map:return {**table_map[f'b{i}'],**common,'id':table_map[f'b{i}']['id'],'sourceIds':table_map[f'b{i}']['sourceIds']}
    if f'b{i}' in figure_map:
        f=figure_map[f'b{i}'];return {**common,'type':'figure_ref','figureId':f['id'],'title':f['title'],'note':f['note'],'url':f['url'],'page':f['page'],'sourceIds':f['sourceIds']}
    if i in formula:
        return {**common,'type':'formula','text':formula[i][0],'latex':formula[i][1],'number':int(b['text'].strip('()'))}
    if b.get('images'):return None
    txt=b.get('text','')
    if not txt:return None
    # Captions and notes are retained on their table/figure object, not repeated as prose.
    if b.get('style')=='Caption':return None
    if (f'b{i-1}' in table_map or f'b{i-2}' in figure_map) and txt.startswith('Примечание.'):return None
    level=re.search(r'Heading(\d)',b.get('style',''))
    if level:return {**common,'type':'heading','level':min(int(level.group(1))+1,4),'text':txt}
    return {**common,'type':'paragraph','text':txt}

def span(a,b):return list(range(a,b+1))
mapping={
 'overview':span(54,62)+span(327,333),
 'framework':span(63,72)+span(76,81),
 'structure':span(82,97),
 'logic':span(98,128),
 'audit':span(129,138)+[140]+span(334,341),
 'targets':[139]+span(141,169),
 'map':span(212,230),
 'regions':span(231,236),
 'finance':span(184,211)+span(342,349),
 'network':span(237,254),
 'texts':[255,256,257]+span(263,272)+span(277,279),
 'domains':span(258,262)+span(273,276),
 'causal':span(317,326),
 'proposals':span(280,316),
 'lab':[], 'explorer':[], 'library':[], 'updates':[],
 'projections':span(170,183),
 'population':span(73,75),
 'methods':span(350,356),
}
titles={
 'overview':'Обзор и основные выводы','framework':'Предмет и теоретическая рамка','structure':'Стратегическая архитектура',
 'logic':'Механизмы девяти федеральных проектов','audit':'Аудит системы показателей','targets':'Показатели и целевые ориентиры',
 'map':'Карта территориальных различий','regions':'Региональные профили и доступность','finance':'Плановое финансирование',
 'network':'Документальные связи','texts':'Текстовый анализ','domains':'Тематические сферы','causal':'Оценка дополнительного результата',
 'proposals':'Предложения по совершенствованию','lab':'Лаборатория расчётов','explorer':'Данные ЕМИСС','library':'Источники и код',
 'updates':'Обновление данных','projections':'Траектории к целям','population':'Целевые группы','methods':'Методы и воспроизводимость'}
summaries={
 'overview':'Проект объединяет молодёжные программы, школьную среду, педагогические кадры, профессиональное образование и университетскую инфраструктуру. Основной резерв совершенствования – проверка того, как созданные возможности используются и превращаются в устойчивые результаты для получателей.',
 'framework':'Экспертиза различает документальный факт, описательное статистическое наблюдение и экспертное предложение. Связь ресурсов с общественным результатом проверяется через образовательные, профессиональные и социальные переходы человека.',
 'structure':'Девять федеральных проектов образуют последовательность образовательных и жизненных возможностей. Общая принадлежность к национальному проекту создаёт организационную предпосылку преемственности; переход между исполнителями требует самостоятельной проверки.',
 'logic':'Для каждой меры различаются ресурс, непосредственный продукт, использование возможности, изменение положения получателя и общественный результат. Уже предусмотренные сопровождение, опросы и распространение практик нуждаются в определённой единице наблюдения и правиле принятия решения.',
 'audit':'Реестр содержит 37 кодов: 9 национальных и 28 федеральных. В срезе экспертизы числовые наблюдения доступны по 10 кодам, ещё для 19 установлен источник, для 8 соответствие источнику не подтверждено. Эти количества описывают доступность данных анализа и не измеряют долю общественного эффекта.',
 'targets':'Одинаковая процентная форма скрывает разные совокупности, периоды накопления и способы агрегирования. Оперативные точки сопоставляются с соответствующими периодами, а подтверждённые годовые факты – с годовой целью той же редакции паспорта.',
 'map':'Два самостоятельных региональных распределения описывают зарегистрированный охват педагогов обучением и школьников системой развития способностей. Даты срезов и знаменатели различаются; единый рейтинг регионов по ним не рассчитывается.',
 'regions':'Неоднородность зарегистрированного охвата требует проверки предложения, информированности, условий обращения, отбора и завершения программы. Крайнее значение само по себе не устанавливает качество управления или причину ограничения доступа.',
 'finance':'План девяти федеральных паспортов за 2025–2030 годы составляет 6 181,32050553 млрд руб. На педагогическое и школьное направления приходится 62,44%. Суммы номинальные, по всем источникам, из разных редакций; они не характеризуют кассовое исполнение.',
 'network':'Сеть различает прямую паспортную привязку, связь через общую задачу и непроверенный лексический кандидат. Формальное ребро не объясняет причинный механизм. Неразрешённые связи электронной публикации не доказывают их отсутствия в полном паспорте.',
 'texts':'TF-IDF и косинусная близость показывают сходство словоупотребления. Внутрипроектное сравнение использует девять федеральных паспортов одного жанра; межпроектная чувствительность проверена русским стеммингом. Коэффициенты не измеряют качество политики.',
 'domains':'Частоты 18 словарных тематик нормированы на длину текста; категории пересекаются. Низкая частота слова не означает отсутствия соответствующей меры. Контекстная проверка уточняет значение инфраструктуры проживания, безопасности и инклюзии.',
 'causal':'Доступная статистика описывает процесс, но не идентифицирует дополнительное воздействие проекта. Предлагается оценивать конкретные меры при наличии исходных данных, прослеживаемых получателей и пригодной группы сравнения.',
 'proposals':'Предложения развивают существующие инструменты проекта: согласование определений и редакций, наблюдение использования возможностей и переходов, затем оценочные исследования. Сроки отсчитываются от принятия решения и являются экспертными предложениями.',
 'lab':'Расчёты показывают свойства официальных формул и чувствительность выводов к заданным предпосылкам. Входные параметры можно менять; результат сценария не становится наблюдаемым фактом или статистическим прогнозом.',
 'explorer':'Выберите показатель, территорию и период. Годовые, оперативные и накопительные наблюдения сохраняют собственную частоту и смысл. Пропуски и отмеченные аномалии представлены явно, без подстановки нулей.',
 'library':'Полный авторский отчёт, исходные таблицы и иллюстрации, официальные статистические источники, извлечённые документы и воспроизводимый код доступны вместе с датами, редакциями и происхождением.',
 'updates':'Статистическое обновление выполняется отдельной проверяемой процедурой. Дата попытки загрузки, дата последнего успешного получения и период наблюдения различаются. При ошибке источника сохраняются последние проверенные значения.',
 'projections':'Два самостоятельных годовых факта позволяют вычислить расстояние до целей 2030 года. Среднее требуемое изменение – арифметический ориентир масштаба задачи. Короткая история не даёт основания для надёжного вероятностного прогноза.',
 'population':'Молодёжь 14–35 лет, учащиеся начальной школы, педагоги, студенты и иностранные граждане образуют разные целевые совокупности. Возраст, статус, гражданство при применимости, территория и дата знаменателя должны соответствовать назначению меры.',
 'methods':'Расчёты сохраняют единицы, периоды, редакции документов и границы доказательности. Денежные суммы сверяются десятичной арифметикой; региональные квартили не взвешены; тематические профили и TF-IDF воспроизводятся из фиксированного корпуса.'}

pages={}
for route,indices in mapping.items():
    blocks=[convert(i) for i in indices];blocks=[b for b in blocks if b]
    ids=list(dict.fromkeys(s for b in blocks for s in b['sourceIds'])) or ['report']
    pages[route]={'id':route,'title':titles[route],'summary':summaries[route],'blocks':blocks,'sources':ids,'source_blocks':indices}

additional={
 'lab':[
  ('heading','Максимум двух долей участия'),
  ('paragraph','Региональный показатель участия в программах определяется максимумом двух долей – профессионального и личностного развития и патриотического воспитания. Это значение не равно доле уникальных лиц в объединении двух аудиторий. Для расчёта объединения необходима величина пересечения участников.'),
  ('formula','Доля объединения = A + B − пересечение; max(A, B) ≤ объединение ≤ min(100, A + B).'),
  ('heading','Средний требуемый прирост'),
  ('paragraph','От годового факта 2025 года до цели 2030 года остаётся пять лет. Деление расстояния до цели на пять задаёт условную линейную траекторию и сохраняет исходную единицу в расчёте на год. Для долей используется изменение в процентных пунктах.'),
  ('formula','Среднее требуемое изменение = (цель 2030 − годовой факт 2025) / 5.'),
  ('heading','Концентрация плановых средств'),
  ('paragraph','HHI равен сумме квадратов долей девяти федеральных проектов в их совокупном плане. Изменение пользовательского распределения показывает арифметику концентрации, а не оптимальность финансирования. Расходы на единицу эффекта требуют самостоятельных сведений об исполнении и причинном результате.')],
 'explorer':[
  ('paragraph','Национальная величина берётся из национального ряда источника. Среднее региональных процентов не заменяет её. Разные частоты, категории и единицы измерения не соединяются в один ряд.'),
  ('paragraph','Значение ЕМИСС 62968 за декабрь 2025 года, 6,31%, присутствует в первичном источнике и сохраняется в таблице с отметкой. Для содержательной динамики и автоматического выбора последнего пригодного наблюдения оно исключается до разъяснения производителя данных.')],
 'library':[
  ('paragraph','Авторский отчёт сохранён целиком, включая 12 таблиц, 17 иллюстраций, 83 сноски и четыре формулы. Тексты сайта разнесены по тематическим страницам; исходные иллюстрации доступны как материалы отчёта, а интерактивные визуализации используют общую палитру проекта.'),
  ('paragraph','Электронные публикации DataBudget являются вторичным представлением паспортов. Прямые паспортные связи, статистика ЕМИСС и авторские интерпретации имеют отдельное происхождение. Совпадение слов и административная привязка не объявляются доказательством воздействия.')],
 'updates':[
  ('paragraph','Экспертиза подготовлена по сведениям, доступным на 27 октября 2026 года. Её статистический срез относится к 15 октября, документальный – к 19 октября. Последующие успешные загрузки обновляют наблюдения и вычисляемые показатели; авторский текст сохраняет собственную дату и не переписывается автоматически.'),
  ('paragraph','Новая публикация той же величины не считается новым независимым наблюдением. Источник, единица, частота, территория, категория, период и статус качества сопровождают каждую запись. Пропуски и отказы загрузки сохраняются в журнале.')]
}
additional_sources={'lab':['report','fn_034','fn_046','fn_047','fn_049','fn_050'],'explorer':['report','fn_055','fn_056','fn_083'],'library':['report'],'updates':['report','fn_027','fn_028']}
for route,items in additional.items():
    for n,(typ,txt) in enumerate(items,1):
        block={'id':f'{route}_editorial_{n}','type':typ,'text':txt,'sourceIds':additional_sources[route],'origin':'platform_explanation_based_on_report'}
        if typ=='heading':block['level']=2
        pages[route]['blocks'].append(block)
    pages[route]['sources']=additional_sources[route]

correction={'id':'qualification_targets_precision','type':'note','kind':'source_clarification',
 'text':'Уточнение по первичному источнику. В авторском абзаце значения целей на 2028 и 2029 годы приведены как 15% и 21%. В выбранном официальном паспорте Минобрнауки, с. 5, указаны 14,9% и 21,1%. Интерактивная траектория и расчёты используют точные паспортные значения; текст исходного отчёта сохранён.',
 'sourceIds':['report','fn_048'],'source_page':5,'origin':'platform_source_check'}
pb=pages['projections']['blocks'];pos=next(i for i,b in enumerate(pb) if b['id']=='b174')+1;pb.insert(pos,correction)

def number(x):return Decimal(re.sub(r'\s+','',x).replace(',','.'))
reg=[]
for row in B[340]['rows'][1:]:
    reg.append({'code':row[0],'name':row[1],'availability':row[2],'emiss_id':int(row[3]) if row[3].isdigit() else None,'level':'national' if re.fullmatch(r'2\.14\.Ю\.\d+',row[0]) else 'federal'})
target_ids=[62932,62931,62935,62936,62934,62969,62968,62895,62898]
targets=[]
for idx,row in enumerate(B[142]['rows'][1:]):
    targets.append({'code':f'2.14.Ю.{idx+1}','emiss_id':target_ids[idx],'name':row[0],'unit':row[1],
                    'values':{str(y):float(number(v)) for y,v in zip([2024,2025,2026,2030],row[2:])},
                    'sourceIds':['report','fn_031'],'sourcePage':locate(B[141]['text']),
                    'basis':'passport_minobrnauki','yearsMissingFromReportTable':[2027,2028,2029]})

mechanism_short=[
 ('y1','Молодёжные программы и инфраструктура','Участие и сопровождение','Применение опыта, продолжение образования, доступность регионального центра','Уникальные и повторные участники; интенсивность; повторный контакт через 6 и 12 месяцев.'),
 ('y2','Воспитание и общественное участие','Педагогически сопровождаемая деятельность','Устойчивый опыт сотрудничества и добровольчества','Возраст участников; продолжительность; обратная связь семей и педагогов; конфиденциальные опросы.'),
 ('y3','Международные образовательные связи','Поступление и сопровождение','Продолжение и завершение обучения','Когорты приёма; переходы этапов; причины выбытия; условия проживания.'),
 ('y4','Школьная среда и способности','Ремонт, оборудование, доступные занятия','Фактическое использование обновлённой среды','Возобновление занятий; доступность помещений; число учащихся; эксплуатационная готовность.'),
 ('y5','Передовые школы','Новые организации и методические центры','Применение практик другими школами','Исходный отбор; апробация; устойчивое использование; условия переноса.'),
 ('y6','Педагогические кадры','Выплаты, замещение вакансий, обучение','Закрепление специалиста и применение компетенций','Предметная вакансия; нагрузка; удержание через 12 и 24 месяца; профессиональный дефицит.'),
 ('y7','Современные кампусы','Строительство и обновление инфраструктуры','Доступная действующая образовательная и жилая среда','Ввод и начало услуги отдельно; загрузка; стоимость проживания; неохваченная потребность; эксплуатация.'),
 ('y8','Университетская подготовка','Инженерные школы, практики и дополнительные квалификации','Применение подготовки в профессиональной деятельности','Выполненная задача; оценка наставника; применение квалификации; занятость по направлению.'),
 ('y9','Профессиональное образование','Кластеры, демонстрационный экзамен, поддержка инклюзии','Завершение обучения и переход к работе','Когортный маршрут; работа по профессии; сохранение занятости; использование сертификатов.')]
federal=[]
logic_ranges=[(99,102),(103,106),(107,109),(110,112),(113,115),(116,118),(119,121),(122,124),(125,128)]
proposal_ranges=[(290,292),(293,295),(296,298),(299,301),(302,304),(305,307),(308,310),(311,313),(314,316)]
for idx,short in enumerate(mechanism_short):
    a,z=logic_ranges[idx];pa,pz=proposal_ranges[idx]
    federal.append({'id':short[0],'code':f'Ю{idx+1}','name':B[a]['text'],'focus':short[1],'output':short[2],'expectedTransition':short[3],'verification':short[4],
                    'mechanismBlocks':[f'b{i}' for i in range(a+1,z+1)],'proposalBlocks':[f'b{i}' for i in range(pa+1,pz+1)],
                    'sourceIds':list(dict.fromkeys(s for i in range(a+1,z+1) for s in (['report']+[f'fn_{x:03d}' for x in B[i].get('footnotes',[])])))})
finance_rows=[]
for row in B[345]['rows'][1:-1]:
    code=re.search(r'\[(Ю\d+)\]',row[0]).group(1)
    finance_rows.append({'code':code,'name':row[0].split('] ',1)[1],'totalThousandRub':str(number(row[1])),'totalBillionRub':float(number(row[1])/Decimal(10**6)),
                         'reportedSharePercent':float(number(row[2])),'edition':row[3],'sourceIds':['report','fn_049','fn_050']})
reconciliation=[]
for row in B[348]['rows'][1:-1]:
    reconciliation.append({'year':int(row[0]),'nationalThousandRub':str(number(row[1])),'federalThousandRub':str(number(row[2])),'differenceThousandRub':str(number(row[3]))})

derived={
 'registry':reg,'targets':targets,'federalProjects':federal,
 'finance':{'projects':finance_rows,'reconciliation':reconciliation,'unit':'thousand_rub','basis':'nominal_all_sources_passport_plan','notExecution':True,'differentEditions':True},
 'annualAnchors':[
  {'emiss_id':62895,'name':'Иностранные обучающиеся','unit':'тыс. человек','year':2025,'fact':414.647,'target2025':410,'target2030':500,'gap2030':85.353,'requiredAnnualChange':17.0706,'sourceIds':['report','fn_046']},
  {'emiss_id':62898,'name':'Несколько квалификаций','unit':'%','year':2025,'fact':5.6,'target2025':5.6,'target2030':30,'gap2030':24.4,'requiredAnnualChange':4.88,'sourceIds':['report','fn_047','fn_048']}],
 'regionalReference':[
  {'emiss_id':62969,'period':'2026-07','n':85,'min':1.68,'q1':5.26,'median':8.21,'q3':12.63,'max':35.67,'national':10.35,'sourceIds':['report','fn_055']},
  {'emiss_id':62968,'period':'2026-09','n':89,'min':67.46,'q1':89.92,'median':97.58,'q3':100,'max':100,'national':93.76,'equal100':27,'below80':8,'sourceIds':['report','fn_056']}],
 'proposalStages':[
  {'id':'reconcile','title':'Согласование основы','horizon':'До 3 месяцев','months':[0,3],'result':B[287]['rows'][1][2]},
  {'id':'monitor','title':'Настройка мониторинга','horizon':'3–6 месяцев','months':[3,6],'result':B[287]['rows'][2][2]},
  {'id':'transitions','title':'Первое наблюдение переходов','horizon':'6–12 месяцев после участия или ввода','months':[6,12],'result':B[287]['rows'][3][2]},
  {'id':'evaluation','title':'Проверка устойчивости и вклада','horizon':'12–24 месяца; по готовности дизайна','months':[12,24],'result':B[287]['rows'][4][2]}],
 'populationGroups':[
  {'id':'youth','name':'Молодёжь','age':'14–35 лет включительно','basis':'Определение ФЗ № 489-ФЗ с предусмотренными законом оговорками','caveat':'Не является универсальным знаменателем всех показателей проекта.'},
  {'id':'confidence','name':'Респонденты уверенности в самореализации','age':'18–35 лет','basis':'Методика ЕМИСС 62936','caveat':'Максимум квартальных долей, не среднегодовая доля.'},
  {'id':'children','name':'Школьники и дети младшего возраста','age':'По назначению конкретной программы','basis':'Образовательный статус и методика показателя','caveat':'«Орлята России» адресованы начальной школе и не входят автоматически в совокупность 14–35 лет.'},
  {'id':'teachers','name':'Педагогические работники','age':'Возрастной диапазон молодёжи не применяется','basis':'Работники дошкольного, общего, СПО и высшего образования','caveat':'Накопление обучения с начала проекта; уровень образования и профессиональная функция учитываются отдельно.'},
  {'id':'students','name':'Получатели нескольких квалификаций','age':'Обучающиеся по программам бакалавриата, специалитета и магистратуры','basis':'Методика ЕМИСС 62898','caveat':'Не переносится автоматически на студентов СПО или на оценку трудоустройства.'},
  {'id':'foreign','name':'Иностранные обучающиеся','age':'Возраст не служит единственным критерием','basis':'Образовательный статус, квота/договоры/платное обучение с исключением пересечений','caveat':'Численность контингента на конец периода не равна новому приёму.'}],
 'limits':[
  {'id':'annual','text':'Два самостоятельных годовых факта относятся к разным показателям и не образуют временной ряд для регрессионного прогноза.'},
  {'id':'regional','text':'Два разновременных региональных показателя не используются для общего рейтинга, PCA, кластеризации или интегральной оценки всей политики.'},
  {'id':'causal','text':'Причинные эффекты не оценены; для них нужны исходные данные, сравнение и проверка предпосылок дизайна.'},
  {'id':'finance','text':'Паспортный план не является кассовым исполнением; HHI не измеряет эффективность; расхождение редакций не доказывает перерасход.'},
  {'id':'text','text':'Лексическое сходство не измеряет согласованность действий; словарный ноль не доказывает отсутствия меры.'},
  {'id':'zero','text':'Нулевые проектные базы не доказывают отсутствия деятельности до начала проекта; сомнительные статистические нули требуют проверки статуса.'},
  {'id':'anomaly','text':'ЕМИСС 62968: декабрь 2025 = 6,31% сохраняется как первичная запись с предупреждением и исключается из содержательной динамики.'}],
}

full_sources='\n\n'.join(f"[{f['id']}] {f['text']}" for f in R['footnotes'])
fulltext=(ROOT/'full_text.md').read_text()+'\n\n# Сноски и источники\n\n'+full_sources+'\n'
(DEST/'expertise_youth_children_2026.md').write_text(fulltext)
if SRC.resolve()!=(DEST/'expertise_youth_children_2026.docx').resolve():shutil.copy2(SRC,DEST/'expertise_youth_children_2026.docx')
shutil.copy2(ROOT/'extraction.json',DEST/'report_extraction.json')
for t in tables:
    with (DEST/(t['id']+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow([c['label'] for c in t['columns']]);w.writerows([[r[c['key']] for c in t['columns']] for r in t['rows']])

meta={'project_id':'youth_children','title':'Экспертиза национального проекта «Молодёжь и дети»','edition_date':'2026-10-27','statistical_snapshot':'2026-10-15','documentary_snapshot':'2026-10-19','source_docx_sha256':R['sha256'],
      'source_pages':len(page_text) or LOCATORS.get('source_pages'),'report_url':BASE+'expertise_youth_children_2026.docx','download_url':BASE+'expertise_youth_children_2026.docx','markdown_url':BASE+'expertise_youth_children_2026.md','extract_url':BASE+'report_extraction.json','content_policy':'author_report_preserved; current_statistical_panels_update_separately',
      'tables':len(tables),'figures':len(figures),'footnotes':len(R['footnotes']),'formulas':4,'report_sources_are_not_automatically_revised':True,
      'source_clarifications':[{'id':correction['id'],'route':'projections','source_block':'b174','emiss_id':62898,'values':{'2028':14.9,'2029':21.1},'source_url':'https://minobrnauki.gov.ru/upload/2026/06/N_Molodezh_i_deti_.pdf','source_page':5}]}
out={'meta':meta,'pages':pages,'tables':tables,'figures':figures,'sources':sources,'derived':derived}
dest=APP/'public/data/projects/youth_children/expertise.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')

assigned=[i for rows in mapping.values() for i in rows]
substantive=[b['index'] for b in R['blocks'] if b['index']>=54 and (b.get('text') or b.get('images') or b['type']=='table')]
missing=set(substantive)-set(assigned); duplicates=[i for i in set(assigned) if assigned.count(i)>1]
assert not missing,missing
assert not duplicates,duplicates
assert len(pages)==21 and len(tables)==12 and len(figures)==17 and len(R['footnotes'])==83
report={'report_pages':meta['source_pages'],'routes':len(pages),'substantive_blocks':len(substantive),'assigned_blocks':len(assigned),'unmapped_substantive_blocks':sorted(missing),'duplicate_assignments':duplicates,'tables':len(tables),'figures':len(figures),'footnotes':len(R['footnotes']),'formulas':4,'verified_page_locators':sum(b.get('page') is not None for p in pages.values() for b in p['blocks']),'blocks_by_page':{k:len(v['blocks']) for k,v in pages.items()}}
(ROOT/'content_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
coverage=[]
for raw in R['blocks']:
    i=raw['index'];route=next((k for k,v in mapping.items() if i in v),None)
    item={'sourceBlock':i,'sourceType':raw['type'],'sourceStyle':raw.get('style'),'route':route}
    if i<54:item.update(status='original_docx_only',reason='Title, approval template and duplicated table of contents; preserved in original DOCX and full Markdown.')
    elif convert(i):item.update(status='rendered_block',target=convert(i)['id'])
    elif raw.get('style')=='Caption':
        if B.get(i+1,{}).get('type')=='table':target=table_map[f'b{i+1}']['id'];field='title'
        else:target=figure_map[f'b{i-1}']['id'];field='title'
        item.update(status='embedded_in_rendered_block',target=target,field=field)
    elif f'b{i-1}' in table_map:item.update(status='embedded_in_rendered_block',target=table_map[f'b{i-1}']['id'],field='note')
    elif f'b{i-2}' in figure_map:item.update(status='embedded_in_rendered_block',target=figure_map[f'b{i-2}']['id'],field='note')
    else:item.update(status='original_docx_only',reason='Blank formatting paragraph.')
    coverage.append(item)
(DEST/'coverage_manifest.json').write_text(json.dumps({'meta':meta,'summary':report,'blocks':coverage},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
