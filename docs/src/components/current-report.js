import {h, icon} from '../core/dom.js';

const url = path => path.startsWith('./') ? path : './' + path;
const edition = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') ? value.split('-').reverse().join('.') : value;
const megabytes = value => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1}).format(value / 1000000);

export function currentReportButton(report) {
  return h('a', {
    class: 'button subtle current-report-button', href: url(report.pdf.url),
    target: '_blank', rel: 'noopener',
    title: 'Экспертиза в PDF · редакция ' + edition(report.edition_date),
    'aria-label': 'Открыть актуальную экспертизу в PDF'
  }, icon('download', 16), 'PDF');
}

export function currentReportCard(report) {
  return h('section', {class: 'current-report-card', 'aria-label': 'Актуальная редакция экспертизы'},
    h('div', {class: 'current-report-copy'},
      h('h2', {}, 'Полный текст экспертизы'),
      h('p', {}, 'Редакция от ', h('time', {datetime: report.edition_date}, edition(report.edition_date)),
        ' · ', report.pdf.pages, ' стр.')),
    h('div', {class: 'current-report-actions'},
      h('a', {class: 'button primary', href: url(report.pdf.url), target: '_blank', rel: 'noopener'},
        icon('download', 16), 'Открыть PDF', h('span', {class: 'report-size'}, megabytes(report.pdf.bytes) + ' МБ')),
      h('a', {class: 'button subtle', href: url(report.docx.url), download: report.docx.filename},
        'Скачать DOCX'),
      h('a', {class: 'text-link current-report-directory', href: './research/reports.html'}, 'Все 12 экспертиз')));
}
