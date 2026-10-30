/** Shared project registry. Family retains its existing research and palette. */
export const projects = [
  ['family','Семья','Семья','#2947A0'],
  ['long_active_life','Продолжительная и активная жизнь','Здоровье','#D9124A'],
  ['youth_children','Молодёжь и дети','Молодёжь','#8265CB'],
  ['tourism','Туризм и гостеприимство','Туризм','#208076'],
  ['personnel','Кадры','Кадры','#CF4520'],
  ['life_infrastructure','Инфраструктура для жизни','Инфраструктура','#45B97C'],
  ['efficient_transport','Эффективная транспортная система','Транспорт','#DCAA44'],
  ['environment','Экологическое благополучие','Экология','#87C879'],
  ['international_export','Международная кооперация и экспорт','Экспорт','#2B3847'],
  ['data_economy','Экономика данных и цифровая трансформация государства','Цифровизация','#4224FD'],
  ['competitive_economy','Эффективная и конкурентная экономика','Экономика','#D86464'],
  ['health_technologies','Новые технологии сбережения здоровья','Технологии здоровья','#0A8BBF']
].map(([id,name,short,color])=>Object.freeze({id,name,short,color,logo:`./assets/brand/${id}.svg`,hasAuthors:id==='family'}));
export const foundationPages = [
  {id:'overview',title:'Обзор проекта',icon:'grid'},
  {id:'structure',title:'Структура экспертизы',icon:'table'},
  {id:'methods',title:'Методы и ограничения',icon:'code'},
  {id:'explorer',title:'Исследователь данных',icon:'search'},
  {id:'library',title:'Данные и источники',icon:'download'}
];
/** Full research navigation for completed national-project studies. */
export const youthPages = [
  ['overview','Обзор исследования','grid','overview'],
  ['framework','Методология','code','research'],
  ['logic','Логика проекта','network','research'],
  ['audit','Аудит показателей','table','research'],
  ['targets','Цели и динамика','trend','research'],
  ['map','Территориальные различия','map','research'],
  ['regions','Региональные профили','map','research'],
  ['finance','Финансовая экспертиза','chart','research'],
  ['network','Сеть мер и результатов','network','research'],
  ['texts','Документы и смыслы','search','research'],
  ['domains','Предметные направления','grid','research'],
  ['causal','Причинная оценка','network','research'],
  ['proposals','Предложения авторов','table','research'],
  ['projections','Целевые сценарии','trend','scenarios'],
  ['population','Целевые группы и переходы','population','scenarios'],
  ['structure','Структура экспертизы','grid','tools'],
  ['methods','Методы и ограничения','code','tools'],
  ['lab','Вычислительная лаборатория','code','tools'],
  ['explorer','Исследователь данных','table','tools'],
  ['library','Данные, документы и код','download','tools'],
  ['updates','Обновление ЕМИСС','reset','tools']
].map(([id,title,icon,group])=>Object.freeze({id,title,icon,group}));
export const personnelPages = youthPages.map(page=>Object.freeze({...page,title:({
  map:'Региональный контекст',
  regions:'Профили рынка труда',
  population:'Трудовые траектории',
  structure:'Сопряжение направлений политики'
})[page.id]||page.title}));
export const longlifePages = youthPages.map(page=>Object.freeze({...page,title:({
  regions:'Региональные профили здравоохранения',
  population:'Продолжительность жизни, здоровье и активность',
  structure:'Архитектура и непрерывность помощи',
  projections:'Сценарии и расстояние до цели'
})[page.id]||page.title}));
export const healthtechPages = youthPages.map(page=>Object.freeze({...page,title:({
  map:'Территориальные границы данных',
  regions:'Готовность к внедрению',
  population:'Доступность для пациентов',
  structure:'От разработки к применению',
  projections:'Плановые траектории',
  network:'Переходы и доказательства',
  domains:'Технологические направления'
})[page.id]||page.title}));
export const infrastructurePages = youthPages.map(page=>Object.freeze({...page,title:({
  domains:'Инфраструктурные направления',
  proposals:'Предложения экспертизы',
  population:'Жители и доступность услуг',
  structure:'Жильё, сети и связность'
})[page.id]||page.title}));
export const environmentPages = youthPages.map(page=>Object.freeze({...page,title:({
  domains:'Экологические направления',
  proposals:'Предложения экспертизы',
  regions:'Региональные экологические профили',
  population:'Территории воздействия и население',
  structure:'Материальные потоки и экосистемы',
  projections:'Плановые траектории'
})[page.id]||page.title}));
export const competitivePages = youthPages.map(page=>Object.freeze({...page,title:({
  logic:'Механизмы экономического развития',
  regions:'Региональные экономические профили',
  domains:'Семь федеральных направлений',
  proposals:'Предложения экспертизы',
  population:'Занятость и качество общественных услуг',
  structure:'Производительность, доход и капитал',
  projections:'Плановые траектории'
})[page.id]||page.title}));
export const dataeconomyPages = youthPages.map(page=>Object.freeze({...page,title:({
  framework:'Предмет и методология',
  logic:'Механизмы цифровой трансформации',
  regions:'Региональные цифровые профили',
  finance:'Финансирование и стоимость результатов',
  domains:'Девять федеральных направлений',
  proposals:'Предложения экспертизы',
  population:'Цифровое неравенство и доступность',
  structure:'Доступ, использование и результат',
  projections:'Плановые траектории'
})[page.id]||page.title}));
export const tourismPages = youthPages.map(page=>Object.freeze({...page,title:({
  framework:'Предмет и методология',
  logic:'Механизмы туристического развития',
  targets:'Цели и наблюдаемые результаты',
  regions:'Региональные профили туризма',
  finance:'Финансирование и стоимость результатов',
  domains:'Пять федеральных направлений',
  proposals:'Предложения экспертизы',
  population:'Участие в отдыхе и доступность',
  structure:'Мощность, использование и результат',
  projections:'Плановые траектории'
})[page.id]||page.title}));
export const efficientTransportPages = youthPages.map(page=>Object.freeze({...page,title:({
  overview:'Эффективная транспортная система',
  framework:'Предмет и критерии оценки',
  logic:'Логика транспортного проекта',
  targets:'Цели и наблюдаемые результаты',
  map:'География транспортных потоков',
  regions:'Территории и доступность',
  finance:'Финансирование и обязательства',
  network:'Связи мер и показателей',
  texts:'Тексты и согласованность',
  domains:'Федеральные направления',
  causal:'Дополнительный эффект',
  proposals:'Направления совершенствования',
  projections:'Плановые траектории',
  population:'Транспортная доступность населения',
  structure:'Мощность и использование сети',
  lab:'Исследовательские расчёты',
  explorer:'Обозреватель данных',
  library:'Источники и материалы',
  updates:'Обновление данных'
})[page.id]||page.title}));
export const internationalExportPages = youthPages.map(page=>Object.freeze({...page,title:({
  overview:"Обзор исследования",
  framework:"Предмет и критерии оценки",
  logic:"Механизмы экспортного результата",
  audit:"Аудит показателей",
  targets:"Цели и наблюдаемые результаты",
  map:"Территориальная концентрация экспорта",
  regions:"Региональные профили и охват",
  finance:"Финансирование и стоимость поддержки",
  network:"Связи мероприятий и показателей",
  texts:"Документы и межпроектные связи",
  domains:"Четыре федеральных направления",
  causal:"Дополнительность поддержки",
  proposals:"Предложения экспертизы",
  projections:"Условия достижения целей",
  population:"Занятость и доходы",
  structure:"Структура и устойчивость экспорта",
  methods:"Методы и ограничения",
  lab:"Вычислительная лаборатория",
  explorer:"Исследователь данных",
  library:"Данные, документы и код",
  updates:"Версии источников и методик",
})[page.id]||page.title}));
export const completeProjectPages = Object.freeze({youth_children:youthPages,personnel:personnelPages,long_active_life:longlifePages,health_technologies:healthtechPages,life_infrastructure:infrastructurePages,environment:environmentPages,competitive_economy:competitivePages,data_economy:dataeconomyPages,tourism:tourismPages,efficient_transport:efficientTransportPages,international_export:internationalExportPages});
export const expertiseBlueprint = [
  ['framework','Методология','Какие вопросы ставит экспертиза и по каким критериям оценивается проект?'],
  ['logic','Логическая модель','Как связаны цели, мероприятия, ресурсы и ожидаемые результаты?'],
  ['audit','Аудит показателей','Какие результаты измеряет система мониторинга и чего в ней недостаёт?'],
  ['targets','Цели и динамика','Что показывают сопоставимые ряды и насколько обоснованы ориентиры?'],
  ['map','Территориальные различия','Как различаются ситуации в субъектах России?'],
  ['regions','Региональные профили','Какие устойчивые сочетания условий и результатов можно выделить?'],
  ['finance','Финансовая экспертиза','Как расходы соотносятся с задачами, результатами и территориальными потребностями?'],
  ['network','Сеть мер и результатов','Какие направления связаны между собой и где возникают разрывы?'],
  ['texts','Документы и смыслы','Как сформулированы задачи и что остаётся за пределами языка документов?'],
  ['domains','Предметные направления','Какие содержательные механизмы требуют отдельной проверки?'],
  ['causal','Причинная оценка','Какие данные и сравнения позволят оценить вклад конкретных мер?'],
  ['proposals','Предложения авторов','Какие изменения следуют из проверенных результатов и как оценить их последствия?']
].map(([id,title,question],i)=>({id,title,question,order:i+1}));
export const getProject = id => projects.find(p=>p.id===id) || projects[0];
export function projectHref(projectId, page='overview', params={}) {
  const project=getProject(projectId);
  const route=project.id==='family' ? `#/${page}` : `#/projects/${project.id}/${page}`;
  const clean=Object.entries(params).filter(([key,value])=>!['mode','page','nationalProject'].includes(key)&&value!==null&&value!==undefined&&value!=='');
  const query=new URLSearchParams(clean);
  return route+(query.size?'?'+query:'');
}
