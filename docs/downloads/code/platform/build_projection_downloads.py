#!/usr/bin/env python3
"""Publish all current indicator results, input manifests, portable Python and Colab notebook."""
import csv,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(root=ROOT):
    out=root/'public/downloads/projections';out.mkdir(parents=True,exist_ok=True)
    index=json.loads((root/'public/data/projections/indicators/manifest.json').read_text(encoding='utf-8'));rows=[];models=[]
    for e in index['series']:
        if not e.get('file'):continue
        obj=json.loads((root/'public'/e['file']).read_text(encoding='utf-8'))
        for status,key in [('observation','observations'),('model','forecast')]:
            for r in obj[key]:
                rows.append({'region_id':obj['region_id'],'region_name':obj['region_name'],'indicator':obj['indicator_id'],'date':r['date'],'status':status,'value':r['value'],'lo80':r.get('lo80'),'hi80':r.get('hi80'),'lo95':r.get('lo95'),'hi95':r.get('hi95'),**{k:r.get('members',{}).get(k) for k in ['last','local_damped','holt_damped','harmonic_ridge','quasiperiodic_gp']},**{k:r.get(k) for k in ['trend_value','cycle_factor','local_factor','cycle_percent','prediction_log_sd']},'source_as_of':obj['source_as_of'],'model_version':obj['model_version'],'input_sha256':obj['input_sha256']})
        models.extend({'region_id':e['region_id'],'indicator_id':e['indicator_id'],**{k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,dict) else v) for k,v in m.items()}} for m in obj['models'])
    for filename,data in [('monthly_indicators.csv',rows),('model_weights_validation.csv',models)]:
        with (out/filename).open('w',encoding='utf-8-sig',newline='') as f:
            keys=list(dict.fromkeys(k for row in data for k in row))
            w=csv.DictWriter(f,fieldnames=keys,delimiter=';');w.writeheader();w.writerows(data)
    (out/'indicator_manifest.json').write_text(json.dumps(index,ensure_ascii=False,indent=2), encoding='utf-8')
    (out/'population_manifest.json').write_bytes((root/'public/data/projections/population/manifest.json').read_bytes())
    files={f'demography/{fn}':(root/f'scripts/demography/{fn}').read_text(encoding='utf-8') for fn in ['cohort.py','indicator.py','indicator_v11.py']};files['demography/__init__.py']='';files['reproduce_projection.py']=(root/'scripts/reproduce_projection.py').read_text(encoding='utf-8')
    readme='Новые алгоритмы платформы 1.2.1. Нужен Python 3.11+ и NumPy.\npython -m pip install -r requirements.txt\npython reproduce_projection.py indicator forecast.json\npython reproduce_projection.py cohort cohort_package.json\n\nПример example_synthetic.json полностью синтетический; к России и регионам не относится.\n'
    with zipfile.ZipFile(out/'projections_python.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items():z.writestr(name,text)
        z.writestr('requirements.txt','numpy==2.3.5\n');z.writestr('README.txt',readme);z.write(root/'public/data/projections/demo_input.json','example_synthetic.json')
    cells=[]
    def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(keepends=True)})
    def code(s):cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(keepends=True)})
    md('# Воспроизведение прогнозов платформы «Экспертиза национального проекта „Семья“»\n\nНовая реализация 1.2.1. Для моделей показателей необходим NumPy; в первой ячейке установлена проверенная версия. Гармоника и квазипериодический GP оценивают изгибы по исходным наблюдениям; период 12 месяцев задан, а не доказан. Старые сохранённые результаты 1.1.1 повторяются отдельной реализацией. Загрузите JSON, скачанный с прогнозной страницы. Код ниже самодостаточен и не обращается к ЕМИСС; он воспроизводит именно сохранённый вход. Никакой ряд не переобозначается как наблюдение. Исходники соответствуют текущей версии пакета; при смене версии модели нужен новый блокнот.')
    code('import sys, subprocess\nsubprocess.run([sys.executable, "-m", "pip", "install", "numpy==2.3.5"], check=True)\n')
    code('from pathlib import Path\nimport json, subprocess, sys\nFILES = '+repr(files)+'\nfor name, text in FILES.items():\n    path = Path(name)\n    path.parent.mkdir(parents=True, exist_ok=True)\n    path.write_text(text, encoding="utf-8")\nprint("Алгоритмы подготовлены")\n')
    md('## Загрузка сохранённого расчёта\n\nВ Google Colab выберите файл `forecast_…json` или `cohort_…json`. Для запуска вне Colab укажите локальный путь.')
    code('try:\n    from google.colab import files\n    uploaded = files.upload()\n    filename = next(iter(uploaded))\nexcept ImportError:\n    filename = input("Путь к JSON: ").strip()\nobj = json.loads(Path(filename).read_text(encoding="utf-8-sig"))\nschema = obj.get("schema", "")\nif schema == "semya.indicator-projection/1":\n    kind = "indicator"\nelif schema in {"semya.cohort-package/1", "semya.cohort-input/1"}:\n    kind = "cohort"\nelse:\n    raise ValueError("Неизвестная схема файла: " + schema)\nprint("Тип расчёта:", kind)\n')
    code('result = subprocess.run([sys.executable, "reproduce_projection.py", kind, filename, "--output", "reproduced.json"], capture_output=True, text=True)\nprint(result.stdout)\nif result.returncode:\n    raise RuntimeError(result.stderr)\nprint("Расчёт сохранён в reproduced.json")\n')
    code('try:\n    from google.colab import files\n    files.download("reproduced.json")\nexcept ImportError:\n    print(Path("reproduced.json").resolve())\n')
    md('## Ограничения\n\nУсловные интервалы ансамбля не являются подтверждёнными частотными интервалами и не дают вероятности воздействия нацпроекта. Передвижка зависит от наблюдаемой базы и заданных возрастных/временных предпосылок. Модельная таблица смертности из ОПЖ не равна наблюдаемой возрастной таблице. Месячный шаг не означает ежемесячное наблюдение всех компонент.')
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'}},'cells':cells}
    (out/'projections_colab.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2), encoding='utf-8')
    print(f'Выгрузки новых прогнозов: {len(rows)} значений, {len(models)} записей по моделям; Python ZIP и Colab.')
if __name__=='__main__':run()
