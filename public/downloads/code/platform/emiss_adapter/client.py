"""Transport and query planning adapted from the user-supplied CDO connector.
The endpoint is the website's export contract, not a guaranteed public API.
No browser challenge bypass, credentials in published files, or guessed category default.
"""
from __future__ import annotations
import hashlib,json,math,os,re,time
from urllib.parse import urljoin,urlsplit,urlencode
import httpx
from lxml import html
from .errors import EmissConnectorError
from .metadata import parse_indicator_metadata,infer_field_map
from .catalog import parse_organizations_catalog
from .sdmx import parse_sdmx

def title_key(value):
    return re.sub(r'[\s\u00a0«»"“”.,:;–—()\-]+','',str(value).casefold().replace('ё','е')).strip()

def resolve_indicator(items,titles):
    # Try exact source title first; lower-priority aliases cannot override an exact match.
    for title in titles:
        matched=[i for i in items if i.status!='excluded' and title_key(i.title)==title_key(title)]
        active=[i for i in matched if i.status=='actual']
        pool=active or matched
        unique={i.indicator_id:i for i in pool}
        if len(unique)==1:return next(iter(unique.values()))
        if len(unique)>1:raise EmissConnectorError('Несколько источников с одинаковым названием; требуется подтверждение ID.',category='ambiguous_mapping')
    raise EmissConnectorError('Точное название не найдено в каталоге. Укажите подтверждённый ID и допустимый заголовок в emiss_sources.json.',category='unresolved_mapping')

def redact(text):
    text=re.sub(r'(https?|socks5h?)://[^\s/@]+(?::[^\s/@]*)?@',r'\1://***@',str(text))
    proxy=os.environ.get('EMISS_PROXY_URL','')
    if proxy:text=text.replace(proxy,'[proxy]')
    return text[:600]

class Client:
    def __init__(self,config,transport=None):
        self.config=config;self.base=config['base_url'].rstrip('/')
        self._download_tokens={};self._token_required=set()
        self.allowed=set(config['allowed_hosts']);self.last_request=0;self.last_download=None
        timeout=float(config.get('timeout_seconds',35))
        proxy=os.environ.get('EMISS_PROXY_URL') or None
        self.http=httpx.Client(timeout=httpx.Timeout(timeout,connect=min(timeout,15)),follow_redirects=False,proxy=proxy,transport=transport,trust_env=False,headers={
            'User-Agent':'Mozilla/5.0 SemyaResearch/1.0 (academic statistical monitoring)',
            'Accept':'text/html,application/xml,text/xml;q=0.9,*/*;q=0.8',
            'Accept-Language':'ru-RU,ru;q=0.9,en;q=0.5','Accept-Encoding':'identity'})
    def close(self):self.http.close()
    def request(self,method,path,form=None):
        url=urljoin(self.base+'/',path);last=None
        # POST download tokens are single-use. Retry a failed POST only at the
        # export level, after obtaining a fresh token in the same session.
        retries=int(self.config.get('retries',2)) if method=='GET' else 0
        for attempt in range(retries+1):
            try:
                for redirect in range(5):
                    parsed=urlsplit(url)
                    if parsed.scheme!='https' or parsed.hostname not in self.allowed or parsed.username or parsed.password:
                        raise EmissConnectorError('Запрещённый адрес или перенаправление источника.',category='unsafe_url')
                    wait=float(self.config.get('min_interval_seconds',1))-(time.monotonic()-self.last_request)
                    if method=='POST' and self.last_download is not None:
                        wait=max(wait,float(self.config.get('min_download_interval_seconds',0))-(time.monotonic()-self.last_download))
                    if wait>0:time.sleep(wait)
                    self.last_request=time.monotonic()
                    if method=='POST':self.last_download=self.last_request
                    kwargs={'content':urlencode(form).encode(),'headers':{'Content-Type':'application/x-www-form-urlencoded','Referer':self.base+'/indicator/'+dict(form).get('id','')}} if form is not None else {}
                    with self.http.stream(method,url,**kwargs) as r:
                        if r.status_code in (301,302,303,307,308):
                            if method!='GET':raise EmissConnectorError('Неожиданное перенаправление POST.',category='source_redirect')
                            url=urljoin(url,r.headers.get('location',''));continue
                        if r.status_code in (429,500,502,503,504):
                            delay=min(30,float(r.headers.get('retry-after','2')) if r.headers.get('retry-after','').isdigit() else 2**attempt)
                            time.sleep(delay);raise EmissConnectorError('Источник временно недоступен: HTTP '+str(r.status_code),category='temporary_http')
                        if r.status_code>=400:raise EmissConnectorError('Источник вернул HTTP '+str(r.status_code),category='http_error')
                        chunks=[];size=0
                        for chunk in r.iter_bytes():
                            size+=len(chunk)
                            if size>60*1024*1024:raise EmissConnectorError('Ответ превышает 60 МБ.',category='payload_too_large')
                            chunks.append(chunk)
                        body=b''.join(chunks)
                        if any(s in body[:12000].lower() for s in [b'access denied',b'captcha',b'cf-chl-',b'verify you are human']):
                            raise EmissConnectorError('Источник требует дополнительной проверки доступа; данные не заменены.',category='access_challenge')
                        return body
                raise EmissConnectorError('Слишком много перенаправлений.',category='source_redirect')
            except (httpx.HTTPError,EmissConnectorError) as exc:
                last=exc
                if isinstance(exc,EmissConnectorError) and exc.category not in {'temporary_http'}:raise
                if attempt<retries:time.sleep(2**attempt)
        raise EmissConnectorError('Сетевая ошибка '+method+' '+urlsplit(url).path+': '+redact(last),category='network_error')
    def catalog(self):
        body=self.request('GET','/organizations/')
        items=parse_organizations_catalog(body.decode('utf-8',errors='replace'))
        if not items:raise EmissConnectorError('Каталог не содержит распознаваемых источников.',category='catalog_schema_changed')
        return items
    def metadata(self,indicator_id):
        if not re.fullmatch(r'\d{1,12}',str(indicator_id)):raise EmissConnectorError('Некорректный ID',category='invalid_id')
        page=self.request('GET','/indicator/'+str(indicator_id)).decode('utf-8',errors='replace')
        # Ordinary one-use download form token, bound to this HTTP cookie
        # session. Never include it in the published metadata/provenance.
        fields={e.get('name'):e.get('value','') for e in html.fromstring(page).xpath('//*[@id="downloadTokenHolder"]//input[@name]')}
        tokens={k:v for k,v in fields.items() if k in {'struts.token.name','token'} and v}
        if tokens:self._download_tokens[str(indicator_id)]=tokens;self._token_required.add(str(indicator_id))
        return parse_indicator_metadata(page,str(indicator_id))
    def export(self,meta,selected):
        for attempt in range(int(self.config.get('retries',2))+1):
            try:return self._export_once(meta,selected)
            except EmissConnectorError as exc:
                if exc.category not in {'network_error','temporary_http','source_redirect'} or attempt>=int(self.config.get('retries',2)):raise
                time.sleep(float(self.config.get('export_retry_delay_seconds',1))*2**attempt)
                fresh=self.metadata(str(meta['indicator_id']))
                if fresh!=meta:raise EmissConnectorError('Метаданные изменились между попытками выгрузки.',category='metadata_contract_changed')

    def _export_once(self,meta,selected):
        form=[('id',str(meta['indicator_id'])),('filterObjectIds','0')]
        iid=str(meta['indicator_id'])
        if iid in self._token_required and iid not in self._download_tokens:self.metadata(iid)
        form.extend(self._download_tokens.pop(iid,{}).items())
        form.append(('title',meta['indicator_title']))
        for f in meta['filters']:
            field=str(f['field_id'])
            if field!='0':form.append((f.get('object_parameter') or 'lineObjectIds',field))
            for value in selected.get(field,[]):form.append(('selectedFilterIds',field+'_'+str(value['id'])))
        # This is the download action used by fedstat's FGrid.downloadFile.
        # /indicator/data.do renders HTML and is not the SDMX export endpoint.
        raw=self.request('POST','/indicator/downloadData?format=sdmx',form)
        observations,structure=parse_sdmx(raw)
        if not observations:raise EmissConnectorError('Пустая SDMX-выгрузка.',category='empty_export')
        return observations,structure,hashlib.sha256(raw).hexdigest(),raw

def query_plan(meta,source,max_cells=300000):
    if not any(title_key(meta['indicator_title'])==title_key(t) for t in source['titles']):
        raise EmissConnectorError('Заголовок страницы не совпадает с подтверждённым названием источника.',category='title_mismatch')
    roles=infer_field_map(meta,source.get('field_overrides'))
    if 'year' not in roles:raise EmissConnectorError('Не определено поле года.',category='unresolved_period')
    if source.get('min_regional_count',0) and 'territory' not in roles:
        raise EmissConnectorError('Не определено территориальное измерение.',category='unresolved_territory')
    selected={}; defaults=source.get('dimension_defaults',{})
    for f in meta['filters']:
        fid=str(f['field_id']);values=f['values']
        if fid=='0':selected[fid]=[v for v in values if str(v['id'])==str(meta['indicator_id'])] or [{'id':str(meta['indicator_id']),'title':meta['indicator_title']}]
        elif fid==roles.get('year'):
            selected[fid]=[v for v in values if re.fullmatch(r'(19|20|21)\d{2}',str(v['title'])) and int(v['title'])>=source['first_year']]
        elif fid in defaults or f['title'] in defaults:
            ids=[str(x) for x in defaults.get(fid,defaults.get(f['title'],[]))]
            selected[fid]=[v for v in values if str(v['id']) in ids]
            if len(selected[fid])!=len(ids):raise EmissConnectorError('Подтверждённая категория исчезла из метаданных.',category='dimension_schema_changed')
        elif fid in roles.values():selected[fid]=values
        elif len(values)==1:selected[fid]=values
        else:
            raise EmissConnectorError(f"Требуется явный выбор измерения «{f['title']}» ({len(values)} категорий). Первая категория автоматически не выбирается.",category='dimension_requires_confirmation')
        if not selected[fid]:raise EmissConnectorError('Пустой выбор фильтра '+f['title'],category='empty_filter')
    cells=math.prod(len(v) for k,v in selected.items() if k!='0')
    if cells>max_cells:raise EmissConnectorError(f'Запрос содержит до {cells} ячеек; нужна явная разбивка.',category='query_too_large')
    return roles,selected
