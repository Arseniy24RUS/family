"""Replay the author's fixed TF-IDF vocabulary without CPU-dependent tie cuts.

NumPy's unstable argsort selects different terms with equal frequency at the
20,000-feature boundary on AVX2 and AVX512 processors. The pinned vocabularies
were exported only after reproducing the original author vocabulary, IDF and
both sets of independent cosine references. Fitting still recomputes TF-IDF
from all 137 original profiles; it never substitutes stored comparison scores.
"""
import gzip
import hashlib
import json
from pathlib import Path


MODEL_PATH = Path(__file__).resolve().parents[1] / 'inputs/text_models/author_tfidf_vocabularies.json.gz'
MODEL_SHA256 = '536b4e93c1c38a53b38fa621b0b8e0d7ff36b9185845ac8de2131c1fddafb4ab'
SOURCE_PROFILES_SHA256 = '45af856c235b152dcbcae7daf112198af8b020a959eb89e556d9edea962d6265'


def read_pinned_models(path=MODEL_PATH, expected_sha256=MODEL_SHA256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Author TF-IDF vocabulary checksum mismatch')
    result = json.loads(gzip.decompress(raw))
    if (result.get('schema') != 'national-projects.author-tfidf-vocabularies/1' or
            result.get('source_profiles_sha256') != SOURCE_PROFILES_SHA256):
        raise ValueError('Author TF-IDF vocabulary source mismatch')
    for variant in ['surface', 'stemming']:
        model = result[variant]
        terms, idf = model['terms'], model['idf']
        if (len(terms) != 20000 or len(set(terms)) != 20000 or
                terms != sorted(terms) or len(idf) != len(terms)):
            raise ValueError('Invalid author TF-IDF vocabulary: ' + variant)
    return result


def fit_author_tfidf(texts, params, variant):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    if len(texts) != 137:
        raise ValueError('Author TF-IDF requires the fixed 137-document corpus')
    if variant not in ['surface', 'stemming']:
        raise ValueError('Unknown author TF-IDF variant: ' + str(variant))
    model = read_pinned_models()[variant]
    vectorizer = TfidfVectorizer(**params, vocabulary={term: index for index, term in enumerate(model['terms'])})
    matrix = vectorizer.fit_transform(texts)
    # This verifies the fit, including tokenization and document frequencies,
    # against the author model instead of merely trusting a fixed feature list.
    error = float(np.max(np.abs(vectorizer.idf_ - np.asarray(model['idf']))))
    if not np.isfinite(error) or error > 1e-12:
        raise AssertionError({'metric': variant + '_idf_max_error', 'difference': error, 'tolerance': 1e-12})
    return vectorizer, matrix
