#!/usr/bin/env python3
"""Repeat a JSON export from the platform's laboratory, with Python's standard library.

    python scripts/lab_reproduce.py new_clusters.json --output repeated.json
    python scripts/lab_reproduce.py correlation_result.json
    python scripts/lab_reproduce.py moran_result.json

This is NEW platform code, not a reconstruction of the initial research training.
Input values and configuration are embedded in the exported JSON. Floating-point
rounding can differ between engines. The PRNG and iteration order mirror stats.js.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from typing import Any


def mean(values):
    return sum(values) / len(values) if values else None


def pearson(x, y):
    if len(x) < 3 or len(x) != len(y):
        return None
    mx, my = mean(x), mean(y)
    xx = sum((v-mx)**2 for v in x)
    yy = sum((v-my)**2 for v in y)
    return sum((a-mx)*(b-my) for a, b in zip(x,y))/math.sqrt(xx*yy) if xx and yy else None


def ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j+1 < len(order) and values[order[j+1]] == values[order[i]]:
            j += 1
        for pos in range(i,j+1):
            result[order[pos]] = (i+j)/2+1
        i = j+1
    return result


class Mulberry32:
    """Same deterministic 32-bit generator as the browser lab."""
    def __init__(self, seed=42): self.state = seed & 0xffffffff
    def __call__(self):
        self.state = (self.state + 0x6D2B79F5) & 0xffffffff
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xffffffff
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xffffffff)) & 0xffffffff
        return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296


def finite_matrix(matrix):
    if not matrix or not matrix[0] or any(len(r)!=len(matrix[0]) for r in matrix):
        raise ValueError('Empty or non-rectangular matrix')
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for r in matrix for v in r):
        raise ValueError('Matrix values must be finite numbers')
    return matrix


def standardize(matrix):
    finite_matrix(matrix)
    means = [mean(list(col)) for col in zip(*matrix)]
    std = [math.sqrt(mean([(r[j]-means[j])**2 for r in matrix])) or 1 for j in range(len(means))]
    return [[(v-means[j])/std[j] for j,v in enumerate(r)] for r in matrix], means, std


def kmeans(matrix, k=3, seed=42):
    finite_matrix(matrix)
    if not isinstance(k,int) or not 2 <= k <= len(matrix): raise ValueError('Invalid k')
    if len({tuple(r) for r in matrix}) < k: raise ValueError('Too few distinct profiles')
    random=Mulberry32(seed); n=len(matrix); p=len(matrix[0])
    def dist(a,b): return sum((a[j]-b[j])**2 for j in range(p))
    centres=[list(matrix[int(random()*n)])]
    while len(centres)<k:
        ds=[min(dist(r,c) for c in centres) for r in matrix]
        pick=random()*sum(ds); i=0
        while i<n-1:
            pick-=ds[i]
            if pick<=0: break
            i+=1
        centres.append(list(matrix[i]))
    labels=[-1]*n; iterations=0
    while iterations<150:
        nxt=[min(range(k),key=lambda j:dist(r,centres[j])) for r in matrix]
        if nxt==labels: break
        labels=nxt
        new=[]
        for group in range(k):
            rows=[r for j,r in enumerate(matrix) if labels[j]==group]
            new.append([mean(list(col)) for col in zip(*rows)] if rows else list(matrix[int(random()*n)]))
        centres=new; iterations+=1
    inertia=sum(dist(r,centres[labels[i]]) for i,r in enumerate(matrix))
    scores=[]
    for i,r in enumerate(matrix):
        own=[v for j,v in enumerate(matrix) if j!=i and labels[j]==labels[i]]
        if not own: scores.append(0); continue
        a=mean([math.sqrt(dist(r,v)) for v in own])
        bs=[mean([math.sqrt(dist(r,v)) for j,v in enumerate(matrix) if labels[j]==g]) for g in range(k) if g!=labels[i]]
        b=min(x for x in bs if x is not None)
        scores.append((b-a)/max(a,b) if max(a,b) else 0)
    return dict(labels=[x+1 for x in labels], centres=centres, inertia=inertia, silhouette=mean(scores), iterations=iterations)


def moran(values, adjacency, permutations=999, seed=42):
    # JSON written by the browser already preserves its Object.keys order.
    ids=[k for k,v in values.items() if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)]
    n=len(ids)
    if n<5: raise ValueError('At least five regions are required')
    index={r:i for i,r in enumerate(ids)}; W=[[0.0]*n for _ in ids]
    for a,b in adjacency:
        if a in index and b in index:
            W[index[a]][index[b]]=W[index[b]][index[a]]=1.0
    for i,row in enumerate(W):
        s=sum(row)
        if s: W[i]=[v/s for v in row]
    S0=sum(sum(r) for r in W); x=[values[k] for k in ids]; m=mean(x); z=[v-m for v in x]; den=sum(v*v for v in z)
    if not S0 or not den: raise ValueError('No variation or no adjacency')
    # Keep the same summation order as the JavaScript implementation.
    def calc(q): return n/S0*sum(v*sum(w*q[j] for j,w in enumerate(W[i])) for i,v in enumerate(q))/den
    I=calc(z); random=Mulberry32(seed); nulls=[]
    for _ in range(permutations):
        q=z[:]
        for j in range(n-1,0,-1):
            k=int(random()*(j+1)); q[k],q[j]=q[j],q[k]
        nulls.append(calc(q))
    expected=mean(nulls)
    p=(1+sum(abs(v-expected)>=abs(I-expected) for v in nulls))/(permutations+1)
    return dict(I=I,p=p,n=n,permutations=permutations,expected=expected,islands=sum(not any(r) for r in W))


def repeat(document:dict[str,Any]):
    config=document.get('config',{})
    if 'values' in document and 'adjacency' in document:
        return moran(document['values'],document['adjacency'],int(config.get('permutations',999)),int(config.get('seed',42)))
    rows=document.get('input',[])
    if rows and 'values' in rows[0]:
        z,means,std=standardize([r['values'] for r in rows])
        return {**kmeans(z,int(config.get('k',3)),int(config.get('seed',42))),'means':means,'std':std}
    if rows and 'x' in rows[0] and 'y' in rows[0]:
        x=[r['x'] for r in rows]; y=[r['y'] for r in rows]; finite_matrix(list(zip(x,y)))
        return dict(pearson=pearson(x,y),spearman=pearson(ranks(x),ranks(y)),n=len(rows))
    raise ValueError('Unknown or empty platform laboratory export')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.input.stat().st_size>20*1024*1024: parser.error('Input exceeds 20 MB')
    doc=json.loads(args.input.read_text(encoding='utf-8'))
    result=repeat(doc)
    payload={'config':doc.get('config',{}),'repeated_result':result,'reference_result':doc.get('result'),
             'provenance':'NEW platform laboratory implementation; original expertise is not retrained'}
    text=json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)
    if args.output: args.output.write_text(text,encoding='utf-8')
    else: print(text)

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,KeyError,TypeError) as exc: raise SystemExit(f'Cannot reproduce the input: {exc}')
