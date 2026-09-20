import { h, button, select, para, note, fmt, download, esc } from '../core/dom.js';
import { json, rawPath } from '../core/data.js';
import { heading, panel, toolbar, stats, table, methodBox, evidence, sourceFoot, figure, tabs } from '../components/ui.js';
import { heatmap, bars, C } from '../components/charts.js';
import { sections, frameNames } from '../content/sections.js';
export async function textsPage(ctx) {
    const { state, set } = ctx, s = sections.find(x => x.id === 'texts'), root = h('div', {}, heading(s.title, s.description)), data = await json('data/texts.json'), tab = state.tab || 'frames', docs = data.nlp_document_texts_extracted, shorts = ['Презентация', 'Паспорт', 'Стратегия–2036', 'Старшее поколение'];
    root.append(tabs([['frames', 'Смысловые темы'], ['similarity', 'Сходство документов'], ['corpus', 'Текст и контекст'], ['narrative', 'Нарративные блоки']], tab, v => set({ tab: v })));
    if (tab === 'frames') {
        const frames = Object.keys(frameNames), values = data.nlp_frame_scores_by_document.map(r => frames.map(f => r[f + '_per_1000_words']));
        root.append(stats(data.nlp_frame_scores_by_document.map((r, i) => [shorts[i], fmt(r.n_tokens, 0), 'Токенов в исходном расчёте'])));
        root.append(panel('Фреймы на 1000 слов', 'Одна шкала для всех документов. Полные значения и определения — ниже.', figure(heatmap(shorts, ['Рождения', 'Доходы', 'Здоровье', 'Услуги', 'Ценности', 'Уход', 'Управление', 'Права', 'Труд'], values, { left: 190, width: 1120, cellHeight: 68, label: 'Частота фреймов на 1000 слов', onSelect: (j, i) => set({ frame: frames[i], doc: docs[j].document_id }) }), { name: 'text_frames', title: 'Фреймовый профиль документов', source: 'Авторские словари и извлечённые PDF-тексты' })));
        const frame = frames.includes(state.frame) ? state.frame : 'healthcare_reproductive';
        root.append(panel('Словарь выбранной темы', 'Проверяемый набор основ слов и выражений, использованный в анализе.', h('div', {}, toolbar(select('Тема', frames.map(k => [k, frameNames[k]]), frame, v => set({ frame: v }))), h('div', { class: 'dictionary' }, data.frame_dictionary[frame].map(word => h('button', { onClick: () => set({ tab: 'corpus', query: word }) }, word))), note('Например, 0 совпадений по теме «Здоровье и репродукция» в паспорте означает результат конкретного словаря на конкретном извлечённом тексте, а не отсутствие медицинских мероприятий.', 'warning'))));
        root.append(panel('Частоты без округления', 'Число совпадений, знаменатель и частота выбранной темы.', table(data.nlp_frame_scores_by_document.map((r, i) => ({ document: shorts[i], tokens: r.n_tokens, count: r[frame + '_count'], frequency: r[frame + '_per_1000_words'] })), [{ key: 'document', label: 'Документ' }, { key: 'tokens', label: 'Токенов', numeric: true, decimals: 0 }, { key: 'count', label: 'Совпадений', numeric: true, decimals: 0 }, { key: 'frequency', label: 'На 1000 слов', numeric: true, decimals: 5 }], { pageSize: 4, search: false, filename: 'frame_frequencies.csv' })));
    }
    else if (tab === 'similarity') {
        const rows = data.nlp_document_similarity_tfidf, values = rows.map(r => docs.map(d => r[d.file_name]));
        root.append(panel('Косинусное сходство TF–IDF', '1 на диагонали — документ сравнивается сам с собой. Коэффициенты не являются оценками качества документов.', figure(heatmap(shorts, shorts, values, { left: 210, width: 920, cellHeight: 78, min: 0, max: 1, label: 'Матрица тематического сходства' }), { name: 'tfidf', title: 'TF–IDF: косинусное сходство', source: 'Сохранённая матрица корпуса из четырёх документов' })), note('Различия жанра, длины, токенизации и извлечения PDF влияют на сходство. Значение 0,49 не означает «49% общего смысла».'));
        root.append(panel('Слова корпуса', 'Сохранённые частоты. Частое слово не обязательно раскрывает смысловую позицию документа.', table(data.nlp_top_terms_all_documents, [{ key: 'term', label: 'Слово / форма' }, { key: 'count', label: 'Упоминаний', numeric: true, decimals: 0 }], { pageSize: 12, filename: 'corpus_terms.csv' })));
    }
    else if (tab === 'corpus') {
        const doc = docs.find(d => d.document_id === state.doc) || docs[1], query = state.query || '', input = h('input', { type: 'search', value: query, placeholder: 'Слово, основа или выражение', 'aria-label': 'Искомое выражение' }), hits = h('div', { class: 'concordance' }), count = h('span', { class: 'small muted' });
        function draw() { const q = input.value.trim(), text = doc.text, lower = text.toLocaleLowerCase('ru'), needle = q.toLocaleLowerCase('ru'); hits.replaceChildren(); if (needle.length < 2) {
            count.textContent = 'Введите не менее двух символов';
            return;
        } let pos = 0, n = 0; while ((pos = lower.indexOf(needle, pos)) !== -1) {
            n++;
            if (n <= 80) {
                let before = text.slice(Math.max(0, pos - 140), pos), after = text.slice(pos + q.length, Math.min(text.length, pos + q.length + 210));
                hits.append(h('p', {}, h('span', { class: 'hit-number' }, String(n).padStart(2, '0')), before, h('mark', {}, text.slice(pos, pos + q.length)), after));
            }
            pos += Math.max(needle.length, 1);
        } count.textContent = `Найдено: ${n}. Показаны ${Math.min(n, 80)} контекстов.`; if (!n)
            hits.append(para('Совпадений нет. Проверьте словоформу и извлечение текста.')); }
        input.addEventListener('input', draw);
        draw();
        root.append(toolbar(select('Документ', docs.map((d, i) => [d.document_id, shorts[i]]), doc.document_id, v => set({ doc: v })), h('a', { class: 'button subtle', href: './downloads/documents/' + encodeURIComponent(doc.file_name), download: true }, 'Исходный PDF'), button('Извлечённый TXT', () => download(doc.document_id + '.txt', doc.text), 'button subtle', 'download')));
        root.append(panel('Поиск контекстов', doc.file_name, h('div', {}, toolbar(input, button('Сохранить поиск в ссылке', () => set({ query: input.value }), 'button subtle')), count, hits)));
        root.append(h('details', { class: 'method-box' }, h('summary', {}, 'Полный извлечённый текст'), h('pre', { class: 'corpus-text' }, doc.text)));
    }
    else {
        const rows = data.nlp_narrative_blocks_dictionary, doc = docs.find(d => d.document_id === state.doc) || docs[0], part = rows.filter(r => r.document_id === doc.document_id);
        root.append(note('Отдельный сохранённый расчёт: иная словарная группировка и иной знаменатель. Не сопоставляйте его числа напрямую с вкладкой девяти фреймов.', 'warning'), toolbar(select('Документ', docs.map((d, i) => [d.document_id, shorts[i]]), doc.document_id, v => set({ doc: v }))), panel('Нарративные блоки', 'Все исходные категории и частоты выбранного документа.', table(part, [{ key: 'narrative_block', label: 'Блок' }, { key: 'count', label: 'Совпадений', numeric: true, decimals: 0 }, { key: 'share_per_1000_tokens', label: 'На 1000 токенов', numeric: true, decimals: 4 }], { pageSize: 10, filename: 'narrative_blocks.csv' })), panel('Совместная встречаемость на страницах', 'Два понятия встретились на одной странице. Связь не доказывает причинного или оценочного отношения.', table(data.nlp_concept_cooccurrence_by_page, [{ key: 'concept_a', label: 'Понятие A' }, { key: 'concept_b', label: 'Понятие B' }, { key: 'page_cooccurrence_count', label: 'Страниц', numeric: true, decimals: 0 }], { pageSize: 10, filename: 'concept_cooccurrence.csv' })));
    }
    root.append(sourceFoot('Словари, извлечённые тексты и вычисленные таблицы доступны в библиотеке.', rawPath('nlp_frame_scores_by_document')), methodBox(s.method), evidence(s.finding + ' ' + s.proposal, 'Полная экспертиза от 14.05.2026', `раздел 9, с. ${s.pages}`));
    return root;
}
