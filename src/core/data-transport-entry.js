/** Exact JSON downloads from standalone research pages in compact publication. */
import {installSeriesTransport} from './series-transport.js';

installSeriesTransport().catch(error=>{
 console.error(error);
 const note=document.createElement('aside');
 note.className='note';note.setAttribute('role','alert');
 note.textContent='Загрузка данных временно недоступна. Обновите страницу и повторите скачивание. '+error.message;
 (document.querySelector('main')||document.body).prepend(note);
});
