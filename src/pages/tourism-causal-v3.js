import {h, svg, para, button, download, fmt} from '../core/dom.js';
import {heading, panel} from '../components/ui.js';
import {projectHref} from '../platform/projects.js';
import {normalizeTourismRows, tourismPeriods, TOURISM_RESEARCH_VERSION} from '../core/tourism-research.js';
import {researchNav} from './tourism-v3.js';

const REVIEWED_ON = '2026-10-31';
const PROTOCOL_ID = 'tourism-modular-accommodation-2025-2027';
const PROTOCOL_VERSION = '1.0.0';

const SOURCES = [
  {
    id: 'measure',
    title: 'Поддержка модульных средств размещения',
    publisher: 'Минтранс России, 14 июля 2025 года',
    url: 'https://www.mintrans.gov.ru/press-center/branch-news/7286',
    evidence: 'Официальное сообщение о поддержке на 2025–2027 годы. В нём также отмечены предыдущие раунды финансирования.',
    verification: 'Страница прочитана. Финансирование по отдельным получателям в базу не внесено.',
    limitation: 'Публикация описывает программу в целом. Для анализа отдельных проектов необходим реестр получателей.'
  },
  {
    id: 'selection',
    title: 'Документы отбора инвестиционных проектов',
    publisher: 'Государственный комитет Республики Татарстан по туризму',
    url: 'https://tourism.tatarstan.ru/subsidii-na-sozdanie-modulnih-nekapitalnih-7710869.htm',
    evidence: 'Опубликованы ссылки на федеральный перечень отобранных проектов и региональные документы отбора.',
    verification: 'Наличие документов подтверждено поиском. Содержимое PDF и состав получателей требуют проверки.',
    limitation: 'Реестр получателей ещё не подключён. Необходимо сверить состав проектов, даты и редакции решений.'
  },
  {
    id: 'trips',
    title: 'Количество туристических поездок',
    publisher: 'ЕМИСС, показатель 62900',
    url: 'https://www.fedstat.ru/indicator/62900',
    evidence: 'В платформу включены региональные накопительные оценки поездок. Они служат описательным контекстом исследования.',
    verification: 'Используется сохранённый статистический срез. Обновление первоисточника при открытии страницы не выполняется.',
    limitation: 'Накопительные поездки используются для описания регионального распределения. Связь с получателями субсидий не установлена.'
  },
  {
    id: 'methodology',
    title: 'Методики показателей нацпроекта',
    publisher: 'Росстат',
    url: 'https://rosstat.gov.ru/storage/mediabank/NP10_N.htm',
    evidence: 'В официальном перечне для поездок указан приказ Минэкономразвития России от 30 сентября 2026 года № 684.',
    verification: 'Реквизиты подтверждены поиском по официальному перечню. Соответствие каждой записи конкретной редакции ещё не установлено.',
    limitation: 'Редакция методики и статус первой либо уточнённой оценки для каждого наблюдения ещё не установлены.'
  },
  {
    id: 'irts',
    title: 'International Recommendations for Tourism Statistics 2008',
    publisher: 'ООН, 2010',
    url: 'https://unstats.un.org/unsd/publication/Seriesm/SeriesM_83rev1e.pdf',
    evidence: 'Различает поездки, посетителей, ночёвки, мощности размещения и их использование. Основа для определения исследуемого исхода.',
    verification: 'Документ прочитан. Определение российского показателя проверяется отдельно.',
    limitation: 'Международные определения помогают выбрать исход. Состав российского показателя требует самостоятельной сверки.'
  },
  {
    id: 'did',
    title: 'Introduction to DiD with Multiple Time Periods',
    publisher: 'Б. Каллауэй и П. Сант’Анна, авторская документация did',
    url: 'https://bcallaway11.github.io/did/articles/multi-period-did.html',
    evidence: 'Групповые и временные эффекты при неодновременном начале воздействия. Условия применения включают параллельную динамику и отсутствие опережающей реакции.',
    verification: 'Документация прочитана. Выбор метода для данного исследования пока условный.',
    limitation: 'Метод применим после обоснования сравнения и предпосылок. Его наличие не обеспечивает причинную идентификацию.'
  }
];

const externalLink = (label, url) => h('a', {
  href: url, target: '_blank', rel: 'noopener noreferrer', class: 'text-link'
}, label);
const internalLink = (label, page, params = {}) => h('a', {
  href: projectHref('tourism', page, params), class: 'text-link'
}, label);
const status = (label, kind = 'pending') => h('span', {
  class: `v3-status v3-status-${kind}`
}, label);

function protocol(ctx) {
  const packet = ctx?.tourism || {};
  const statistics = packet.statistics || {};
  const series = (statistics.sources || []).find(item => String(item.source_id || item.id) === '62900');
  const rows = Array.isArray(packet.observations) ? normalizeTourismRows(packet) : [];
  const periods = tourismPeriods(rows);
  const compactSource = String(packet.source_id) === '62900' && periods.length > 0;
  const coverage = compactSource || series ? {
    source_id: '62900',
    first_period: compactSource ? periods[0] : series.first_period || null,
    last_period: compactSource ? periods.at(-1) : series.last_period || null,
    regional_count: compactSource ? new Set(rows.filter(row => !row.isNational && row.eligible).map(row => row.regionId)).size : series.regional_count ?? null,
    observations_count: compactSource ? rows.length : series.observations_count ?? null,
    unit: packet.unit || series?.unit || null,
    temporal_type: 'cumulative_ytd',
    use: 'descriptive_context_only'
  } : null;
  const readiness = [
    {
      id: 'measure', name: 'Мера и правила отбора', state: 'located', label: 'Основание найдено',
      evidence: 'Поддержка модульных средств размещения в 2025–2027 годах подтверждена официальными публикациями.',
      requirement: 'Сохранить действующие и исторические редакции правил, критерии оценки заявок и изменения условий.',
      source_ids: ['measure', 'selection']
    },
    {
      id: 'recipients', name: 'Получатели и заявители', state: 'located', label: 'Документы найдены',
      evidence: 'На официальном региональном сайте опубликованы ссылки на перечень отобранных проектов. Реестр в платформу ещё не включён.',
      requirement: 'Связать проекты, получателей, муниципалитеты, суммы, оценки заявок и результаты отбора, включая отклонённые заявки.',
      source_ids: ['selection']
    },
    {
      id: 'dates', name: 'Начало и интенсивность воздействия', state: 'pending', label: 'Данные не подключены',
      evidence: 'В статистическом пакете отсутствуют даты соглашений, перечислений, строительства и начала работы отдельных объектов.',
      requirement: 'Различить назначение поддержки, выплату и ввод. Разделить финансовое обеспечение будущих затрат и их возмещение.',
      source_ids: ['selection']
    },
    {
      id: 'outcome', name: 'Исход и доступная мощность', state: 'partial', label: 'Есть описательный ряд',
      evidence: coverage ? 'Доступен региональный ряд поездок, ЕМИСС 62900. Муниципальные ночёвки и открытые номеро-сутки по поддержанным объектам не подключены.' : 'Региональный ряд поездок не загружен. Муниципальные ночёвки и открытые номеро-сутки не подключены.',
      requirement: 'Получить сопоставимые ночёвки за календарный месяц и фактические дни работы. Сохранить версии исходных публикаций.',
      source_ids: ['trips', 'irts']
    },
    {
      id: 'prehistory', name: 'История до назначения поддержки', state: 'pending', label: 'Недостаточно для оценки',
      evidence: coverage?.first_period ? `Первое наблюдение подключённого ряда поездок: ${dateLabel(coverage.first_period)} Ряд не покрывает полноценную предысторию мер, назначенных в начале 2025 года.` : 'Предыстория целевого исхода до назначения поддержки в исследование не включена.',
      requirement: 'Собрать несколько полных сезонных циклов до воздействия, историю прежней поддержки и сопоставимый период после.',
      source_ids: ['trips', 'measure']
    },
    {
      id: 'comparison', name: 'Группа сравнения', state: 'pending', label: 'Не сформирована',
      evidence: 'Поддержка предоставлялась и до 2025 года. Отсутствие новой субсидии не подтверждает отсутствие прежнего воздействия.',
      requirement: 'Проверить историю всех кандидатов, состав заявителей и пересечение мер. Обосновать доступное сравнение до выбора оценивателя.',
      source_ids: ['measure', 'did']
    },
    {
      id: 'comparability', name: 'Сопоставимость измерения', state: 'pending', label: 'Требует проверки',
      evidence: 'В официальном перечне Росстата указана новая методика поездок от 30 сентября 2026 года. Редакции отдельных наблюдений не идентифицированы.',
      requirement: 'Сверить определение, охват, единицу и статус первой либо уточнённой оценки. Проверить возможность перехода к месячным потокам.',
      source_ids: ['methodology', 'trips']
    },
    {
      id: 'confounding', name: 'Иные меры и перетоки', state: 'pending', label: 'Данные не подключены',
      evidence: 'Изменения транспорта, календаря мероприятий, доходов и соседних направлений пока не связаны с проектным реестром.',
      requirement: 'Собрать факторы отбора и динамики спроса. Задать географию возможного замещения поездок и отдельную проверку соседних территорий.',
      source_ids: []
    }
  ];
  return {
    schema_version: '1.0.0', protocol_id: PROTOCOL_ID, protocol_version: PROTOCOL_VERSION, platform_release: TOURISM_RESEARCH_VERSION,
    prepared_on: REVIEWED_ON, project_id: 'tourism', status: 'protocol_data_acquisition',
    question: 'Увеличивает ли назначение поддержки модульных средств размещения число ночёвок в принимающей территории?',
    measure: 'Государственная поддержка инвестиционных проектов по созданию модульных некапитальных средств размещения в 2025–2027 годах',
    assignment_unit: 'investment_project', analysis_unit: 'municipality_month',
    treatment: {
      definition: 'Первое документально подтверждённое назначение поддержки проекту в территории с проверенной историей участия.',
      start_event: 'Дата решения или соглашения, юридически закрепляющего назначение поддержки. Выбор события фиксируется после сверки процедур.',
      intensity: ['Назначенная и выплаченная сумма', 'Число поддержанных и фактически открытых номеров'],
      timing_checks: ['Дата заявки', 'Дата решения', 'Дата соглашения', 'Дата платежа', 'Начало строительных работ', 'Дата ввода', 'Начало приёма гостей'],
      repeated_support: 'Территории с прежней поддержкой и повторными выплатами требуют отдельной спецификации. Стандартный дизайн первого воздействия к ним автоматически не применяется.'
    },
    outcomes: [
      {id: 'overnights', role: 'primary', label: 'Число ночёвок в средствах размещения муниципалитета за календарный месяц', unit: 'ночёвки', availability: 'not_connected'},
      {id: 'available_room_nights', role: 'mechanism', label: 'Фактически доступные номеро-сутки', unit: 'номеро-сутки', availability: 'not_connected'},
      {id: 'tourism_trips', role: 'context', label: 'Региональные накопительные оценки поездок', source_id: '62900', availability: coverage ? 'available_descriptive' : 'not_loaded'}
    ],
    estimand: 'Средний эффект назначения поддержки на ночёвки у территорий с поддержанными проектами относительно их возможного состояния без такого назначения, по группе и периоду ATT(g,t).',
    design: {
      status: 'conditional_on_data_and_identification',
      candidate: 'Групповые и временные оценки разности изменений при разновременном назначении поддержки.',
      comparison: 'Сопоставимые заявители и территории, не получившие либо ещё не получившие поддержку, после проверки прежних раундов.',
      assumptions: ['Обоснованная параллельная динамика без поддержки', 'Учитываемая опережающая реакция на заявку и решение', 'Стабильное определение исхода и состав наблюдений', 'Достаточное пересечение характеристик', 'Контроль иных мер и оценка перетоков'],
      diagnostics: ['Предшествующие траектории по полным сезонным циклам', 'Баланс исходных характеристик и причины отбора', 'Календарь поддержки и начала работы', 'Стабильность состава и методики измерения', 'Проверки альтернативной группы и временного окна', 'Анализ соседних территорий'],
      inference: 'Уровень кластеризации и способ построения интервалов выбираются по фактическому механизму назначения поддержки и числу независимых групп.'
    },
    data_snapshot: {statistical_as_of: packet.statistical_as_of || statistics.statistical_as_of || null, snapshot_id: packet.snapshot_id || null, source_sha256: packet.source_sha256 || null, regional_trips: coverage},
    readiness,
    result: {status: 'not_estimated', estimate: null, standard_error: null, confidence_interval: null, units: 'ночёвки'},
    limitations: [
      'Наблюдаемая динамика поездок и сумма финансирования не идентифицируют эффект меры.',
      'Календарный месяц из накопительных публикаций можно получить только после проверки их редакций и охвата.',
      'Ввод номеров является промежуточным результатом. Регистрация объекта и фактическое начало приёма гостей могут расходиться.',
      'Повышение местного потока может включать перераспределение поездок между территориями.',
      'Протокол является авторским предложением исследования. Он не зарегистрирован как завершённая предварительная спецификация.'
    ],
    sources: SOURCES.map(item => ({...item, reviewed_on: REVIEWED_ON}))
  };
}

function dateLabel(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return value || 'дата не установлена';
  return new Intl.DateTimeFormat('ru-RU', {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(new Date(value));
}

function mechanism() {
  const description = 'Предшествующий спрос и транспортная доступность влияют на отбор и ночёвки. Назначение поддержки может увеличить доступную мощность, а она – использование размещения. Иные меры влияют на ночёвки. Рост мощности может перераспределить поездки между территориями. Все связи являются исследовательскими предположениями.';
  const chart = svg('svg', {
    viewBox: '0 0 920 360', width: '920', height: '360', role: 'img',
    'aria-labelledby': 'v3-causal-mechanism-title v3-causal-mechanism-description',
    class: 'v3-mechanism-svg', style: 'display:block;width:100%;min-width:700px;height:auto'
  },
  svg('title', {id: 'v3-causal-mechanism-title'}, 'Предполагаемый механизм поддержки модульного размещения'),
  svg('desc', {id: 'v3-causal-mechanism-description'}, description),
  svg('defs', {}, svg('marker', {id: 'v3-causal-arrow', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse'}, svg('path', {d: 'M0 0L8 4L0 8Z', fill: '#596876'}))));
  function edge(path, dashed = false) {
    chart.append(svg('path', {d: path, fill: 'none', stroke: '#596876', 'stroke-width': 1.7, 'stroke-dasharray': dashed ? '6 5' : null, 'marker-end': 'url(#v3-causal-arrow)'}));
  }
  edge('M146 85V142', true);
  edge('M276 48H554Q603 48 603 92V152Q603 172 636 172', true);
  edge('M276 182H326');
  edge('M586 182H636');
  edge('M766 85V142', true);
  edge('M456 222V282', true);
  function box(x, y, title, detail, primary = false) {
    chart.append(svg('rect', {x, y, width: 260, height: 76, rx: 9, fill: primary ? '#eef6f5' : '#f4f6f8', stroke: primary ? '#4a807c' : '#c8d0d7'}));
    chart.append(svg('text', {x: x + 16, y: y + 29, fill: '#18342f', 'font-size': 16, 'font-weight': 600}, title));
    chart.append(svg('text', {x: x + 16, y: y + 54, fill: '#465664', 'font-size': 13}, detail));
  }
  box(16, 10, 'Предшествующие условия', 'Спрос, транспорт, сезонность');
  box(636, 10, 'Другие воздействия', 'Дороги, события, иные льготы');
  box(16, 144, 'Назначение поддержки', 'Решение, соглашение, сумма', true);
  box(326, 144, 'Доступная мощность', 'Открытые номеро-сутки', true);
  box(636, 144, 'Использование', 'Ночёвки за календарный месяц', true);
  box(326, 282, 'Перетоки поездок', 'Изменение потоков соседей');
  return h('div', {},
    h('div', {class: 'v3-chart-scroll', style: 'max-width:100%;overflow-x:auto', tabindex: '0', 'aria-label': 'Схема механизма, доступна горизонтальная прокрутка'}, chart),
    para('Сплошные стрелки показывают предполагаемый механизм меры. Пунктир обозначает факторы отбора, иные воздействия и возможные перетоки. Наличие стрелки не подтверждает величину или существование эффекта.', 'small muted'),
    h('details', {class: 'v3-details'}, h('summary', {}, 'Текстовое описание связей'), para(description))
  );
}

function readinessTable(items) {
  return h('div', {class: 'table-scroll v3-readiness-scroll', tabindex: '0', 'aria-label': 'Готовность данных для оценки'},
    h('table', {class: 'v3-readiness-table'},
      h('caption', {class: 'sr-only'}, 'Готовность восьми элементов исследования, их основания и следующие действия'),
      h('thead', {}, h('tr', {}, h('th', {scope: 'col'}, 'Элемент'), h('th', {scope: 'col'}, 'Состояние и основание'), h('th', {scope: 'col'}, 'Что необходимо'))),
      h('tbody', {}, items.map(item => h('tr', {},
        h('th', {scope: 'row'}, item.name),
        h('td', {}, status(item.label, item.state), para(item.evidence), item.source_ids.length ? h('div', {class: 'small'}, item.source_ids.map((id, index) => {
          const source = SOURCES.find(source => source.id === id);
          return [index ? ' · ' : '', externalLink(source.publisher, source.url)];
        })) : null),
        h('td', {}, item.requirement)
      )))
    )
  );
}

function passport(item) {
  const fields = [
    ['Мера', item.measure],
    ['Единица наблюдения', 'Муниципалитет × календарный месяц. Реестр назначения поддержки составляется по инвестиционным проектам.'],
    ['Основной исход', 'Число ночёвок в средствах размещения муниципалитета. Региональные поездки используются для описания общего положения.'],
    ['Воздействие', item.treatment.definition],
    ['Начало отсчёта', item.treatment.start_event],
    ['Оцениваемая величина', item.estimand]
  ];
  return h('dl', {class: 'v3-passport'}, fields.map(([label, value]) => h('div', {class: 'v3-passport-row'}, h('dt', {}, label), h('dd', {}, value))));
}

function stages() {
  const stages = [
    ['01', 'Собрать реестр воздействия', 'Проверить заявки, решения и соглашения. Отдельно установить перечисления, ввод и начало приёма гостей. Учесть поддержку предыдущих лет.'],
    ['02', 'Проверить предысторию', 'Согласовать месячные ночёвки, состав объектов и сезонные циклы. Изучить причины отбора и доступные территории сравнения.'],
    ['03', 'Зафиксировать спецификацию', 'До оценивания определить исход, период, группу сравнения, предпосылки, исключения и правила проверки устойчивости. Зарегистрировать версию протокола.'],
    ['04', 'Оценить и проверить', 'При допустимом дизайне рассчитать групповые и временные эффекты с интервалами. Проверить альтернативные периоды, группы и соседние территории. Опубликовать данные и код.']
  ];
  return h('div', {class: 'v3-stage-grid'}, stages.map(([number, title, text]) => h('article', {class: 'v3-stage'}, h('span', {class: 'v3-stage-number', 'aria-hidden': 'true'}, number), h('h3', {}, title), para(text))));
}

/** A real measure-specific protocol. No causal estimate is manufactured from aggregate trends. */
export function tourismCausalV3(ctx) {
  const item = protocol(ctx);
  const coverage = item.data_snapshot.regional_trips;
  const navigation = Object.fromEntries(Object.entries({
    period: ctx?.state?.period, region: ctx?.state?.region, regions: ctx?.state?.regions,
    edition: ctx?.state?.edition || ctx?.tourism?.snapshot_id
  }).filter(([, value]) => value));
  const root = h('div', {
    class: 'tourism-page tourism-v3 v3-causal',
    dataset: {tourismPage: 'causal', routeState: JSON.stringify(ctx?.state || {}), protocolId: PROTOCOL_ID, protocolVersion: PROTOCOL_VERSION}
  });
  root.append(
    heading('Поддержка размещения и число ночёвок', 'Исследование дополнительного результата субсидий на модульные средства размещения.'),
    researchNav(ctx),
    h('section', {class: 'v3-research-status', 'aria-label': 'Статус исследования'},
      h('div', {}, status('Протокол · подготовка данных', 'partial'), h('h2', {}, 'Какую часть изменения можно связать с поддержкой?'),
        para('Исследование связывает решение о субсидии с работой конкретных объектов и ночёвками в принимающей территории. Сейчас определены вопрос, измеряемый результат и условия оценки.')),
      h('div', {class: 'v3-result-state'}, h('strong', {}, 'Эффект не оценён'), para('Реестр воздействия и сопоставимая история исхода ещё не собраны.', 'small'),
        button('Скачать протокол JSON', () => download('tourism-causal-protocol-v3-stage1.json', JSON.stringify(item, null, 2), 'application/json;charset=utf-8'), 'button', 'download'))
    ),
    panel('Предполагаемый механизм', 'От назначения поддержки к работе размещения и территориальному результату', mechanism()),
    panel('Паспорт исследования', 'Авторский протокол от 31 октября 2026 года. Статистическая оценка пока не выполнена.', passport(item)),
    panel('Готовность данных', 'Основания, доступность и необходимые дополнения для каждого элемента исследования', readinessTable(item.readiness)),
    panel('Что уже можно исследовать', 'Доступный статистический материал', h('div', {class: 'v3-context-note'},
      para(coverage ? `В сохранённом срезе ЕМИСС 62900 доступны накопительные оценки поездок для ${fmt(coverage.regional_count, 0)} территорий. Период: ${dateLabel(coverage.first_period)} – ${dateLabel(coverage.last_period)}. Распределение и траектории позволяют описать географию поездок. Привязки к отдельным получателям поддержки в этом ряду нет.` : 'Региональный ряд поездок не загружен в текущем представлении. Доступность наблюдений можно проверить в исследователе данных.'),
      h('div', {class: 'v3-inline-links'}, internalLink('Распределение поездок', 'map', navigation), h('span', {'aria-hidden': 'true'}, ' · '), internalLink('Наблюдения и источники', 'explorer', navigation))
    )),
    panel('Дизайн и пределы интерпретации', 'Выбор оценивателя следует за проверкой данных и механизма отбора', h('div', {class: 'v3-method-content'},
      h('h3', {}, 'Разновременное назначение поддержки'),
      para('При наличии подходящего сравнения можно оценивать ATT(g,t): средний эффект для территорий, впервые получивших поддержку в период g, в каждом последующем периоде t. Группы с прежней поддержкой и повторными выплатами требуют отдельной спецификации. Стандартная регрессия с фиксированными эффектами может смешивать разные эффекты и сроки воздействия.'),
      h('h3', {}, 'Условия, которые необходимо обосновать'),
      para('Сопоставимые предшествующие траектории, отсутствие неучтённой опережающей реакции, устойчивое определение исхода и достаточное пересечение характеристик определяют допустимость сравнения. Отсутствие статистически значимого различия до воздействия само по себе не доказывает параллельную динамику.'),
      h('h3', {}, 'Назначение, выплата и ввод'),
      para('Соглашение, перевод средств, завершение строительства и начало приёма гостей могут приходиться на разные месяцы. При возмещении затрат объект мог начать работу до выплаты. Объединение таких случаев без проверки изменяет смысл оцениваемого воздействия.'),
      h('h3', {}, 'Местный результат и общий прирост'),
      para('Рост ночёвок в принимающей территории может сопровождаться снижением потока у соседей. Оценка местного эффекта требует отдельной проверки замещения. Вывод об общем приросте туризма в стране из местной оценки не следует.'),
      externalLink('Методическая основа: Каллауэй и Сант’Анна', SOURCES.find(source => source.id === 'did').url)
    )),
    panel('Порядок исследования', 'Переход к оцениванию возможен после проверки предыдущих этапов', stages()),
    panel('Источники и основания', 'Проверка источников: 31 октября 2026 года. Статус доступа сохранён вместе с протоколом.',
      h('div', {class: 'v3-source-grid'}, SOURCES.map(source => h('article', {class: 'v3-source-item'}, h('h3', {}, externalLink(source.title, source.url)), para(source.publisher, 'small muted'), para(source.evidence), h('details', {class: 'v3-details'}, h('summary', {}, 'Условия использования'), para(source.limitation, 'small')))))
    ),
    h('div', {class: 'source-foot'}, h('span', {}, 'Полная экспертиза, документы и статистические материалы'), internalLink('Открыть источники проекта', 'library', navigation))
  );
  return root;
}
