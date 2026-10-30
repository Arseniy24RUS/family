#!/usr/bin/env python3
"""Parse pinned Data Economy passports without merging repeated HTML IDs.

The shared parser preserves exact XPath identity. Task membership is resolved
within the same document from an explicit hyperlink or a unique exact title.
Membership is documentary evidence and is never labelled a causal effect.
"""
from extract_healthtech_passports import (parse_passport as parse_base, decimal,
                                        norm, ws, TOKEN_RE)
import hashlib
from lxml import html


def parse_passport(raw, meta):
    result = parse_base(raw, meta)
    if meta['project_id'] != 'data_economy':
        return result
    # HTML text-node boundaries separate source fragments. text_content() alone
    # joins adjacent list/paragraph fragments and changes tokens and bigrams.
    separated = html.fromstring(raw)
    for br in separated.xpath('//br'):
        br.tail = ' ' + (br.tail or '')
    separated_root = separated.getroottree()
    by_id = {n['node_id']: n for n in result['nodes']}
    for unit in result['units']:
        if unit['kind'] == 'result_description':
            element = separated_root.xpath(unit['source_locator'])[0]
            unit['text'] = ws(' '.join(element.itertext()))
            unit['n_tokens'] = len(TOKEN_RE.findall(norm(unit['text'])))
            by_id[unit['node_id']]['description'] = unit['text']
    result['document']['profile_token_count'] = sum(u['n_tokens'] for u in result['units'])
    result['document']['n_tokens'] = result['document']['profile_token_count']
    result['document']['profile_text_sha256'] = hashlib.sha256('\n'.join(u['text'] for u in result['units']).encode()).hexdigest()
    tasks = [n for n in result['nodes'] if n['kind'] == 'task']
    for task in tasks:
        task['record_scope'] = 'standalone_task_card'
        task['membership_eligible'] = True
    for node in result['nodes']:
        if node['kind'] not in ['result', 'indicator']:
            continue
        ref = node.get('task_href')
        if ref:
            matches = [t for t in tasks if ref == '#' + t['source_card_id']]
            basis = 'explicit_same_document_hyperlink'
        else:
            matches = [t for t in tasks if norm(t['title']) == norm(node.get('task_text'))]
            basis = 'unique_exact_task_title_in_same_document'
        node['task_node_id'] = matches[0]['node_id'] if len(matches) == 1 else None
        node['task_source_locator'] = matches[0]['source_locator'] if len(matches) == 1 else None
        node['task_assignment_basis'] = basis if len(matches) == 1 else 'unresolved_or_ambiguous'
    if meta['project_id'] != 'data_economy':
        return result
    tree = html.fromstring(raw)
    root = tree.getroottree()
    doc = result['document']

    def add_record(kind, value, element, scope, value_element=None):
        path = root.getpath(element)
        suffix = hashlib.sha256(path.encode()).hexdigest()[:16]
        node_id = f"{doc['document_id']}:{kind}:{suffix}"
        result['nodes'].append({'node_id':node_id, 'id':node_id,
            'document_id':doc['document_id'], 'project_id':doc['project_id'],
            'fp':doc['code'], 'kind':kind, 'title':value, 'description':'',
            'source_locator':path, 'source_xpath':path,
            'source_value_locator':root.getpath(value_element) if value_element is not None else path,
            'source_card_id':element.get('id'), 'source_sha256':doc['sha256'],
            'source_url':doc['url'], 'metadata':{}, 'record_scope':scope,
            'membership_eligible':False})

    for dt in tree.xpath('//dt'):
        label = ws(dt.text_content())
        if label == 'Цель проекта' and not any(a.tag == 'details' for a in dt.iterancestors()):
            add_record('goal', ws(dt.getnext().text_content()), dt,
                       'document_goal', dt.getnext())
        elif label == 'Задача' and any(a.tag == 'article' for a in dt.iterancestors()):
            card = next((a for a in dt.iterancestors() if a.tag == 'details'), None)
            if card is not None and not (card.get('id') or '').startswith('passport-task-'):
                add_record('task', ws(dt.getnext().text_content()), card,
                           'national_structure_federal_task_restatement', dt.getnext())
    return result
