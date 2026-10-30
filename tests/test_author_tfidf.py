"""Author cosine replay stays exact without CPU-dependent feature selection."""
import gzip
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from nltk.stem.snowball import RussianStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from author_tfidf import MODEL_PATH, fit_author_tfidf, read_pinned_models


class AuthorTfidfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profiles = json.loads(gzip.decompress((ROOT / 'inputs/personnel/documentary_inputs.json.gz').read_bytes()))['profiles']
        cls.documents = profiles['documents']
        cls.texts = [document['text'] for document in cls.documents]
        norm = lambda value: re.sub(r'\s+', ' ', str(value or '')).strip().lower().replace('ё', 'е')
        stops = profiles['dictionary']['stopwords']
        cls.params = dict(lowercase=True, token_pattern=r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',
                          ngram_range=(1, 2), max_features=20000, min_df=1, max_df=.98,
                          sublinear_tf=True, norm='l2', smooth_idf=True, dtype=np.float64)
        cls.surface_params = {**cls.params, 'preprocessor': norm, 'stop_words': stops}
        stemmer, stopset = RussianStemmer(), set(stops)
        tokens = re.compile(r'[а-яёa-z]{2,}(?:-[а-яёa-z]{2,})?', re.I)
        stemtexts = [' '.join(stemmer.stem(token) for token in tokens.findall(norm(text))
                              if token not in stopset) for text in cls.texts]
        # A fixed vocabulary must not reach sklearn's platform-dependent
        # max_features argsort even on a CPU with a different SIMD dispatcher.
        with patch.object(TfidfVectorizer, '_limit_features', side_effect=AssertionError('CPU-dependent vocabulary selection was used')):
            cls.surface, cls.surface_matrix = fit_author_tfidf(cls.texts, cls.surface_params, 'surface')
            cls.stemming, cls.stem_matrix = fit_author_tfidf(stemtexts, cls.params, 'stemming')

    def test_all_author_surface_and_stemming_cosines_are_recomputed_exactly(self):
        references = json.loads((ROOT / 'inputs/competitive/documentary/author_reference_tables.json').read_text())
        projects = sorted({document['project_id'] for document in self.documents
                           if document['source_kind'] == 'secondary_epbs_rendering'})
        for matrix, table, value in [
            (self.surface_matrix, 'project_similarity', 'cosine_similarity'),
            (self.stem_matrix, 'stemming_project_sensitivity', 'russian_snowball_cosine'),
        ]:
            vectors = normalize(np.vstack([
                np.asarray(matrix[[i for i, document in enumerate(self.documents)
                                   if document['project_id'] == project and
                                   document['source_kind'] == 'secondary_epbs_rendering']].mean(axis=0)).ravel()
                for project in projects]))
            scores = vectors @ vectors[projects.index('competitive_economy')]
            for index, project in enumerate(projects):
                if project == 'competitive_economy':
                    continue
                reference = next(item for item in references[table]
                                 if {item['project_a'], item['project_b']} == {'competitive_economy', project})
                with self.subTest(variant=table, project=project):
                    self.assertLessEqual(abs(float(scores[index]) - float(reference[value])), 1e-12)

    def test_changed_corpus_cannot_silently_reuse_author_idf(self):
        changed = list(self.texts)
        changed[0] = ''
        with self.assertRaisesRegex(AssertionError, 'idf_max_error'):
            fit_author_tfidf(changed, self.surface_params, 'surface')

    def test_vocabulary_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'model.json.gz'
            original = MODEL_PATH.read_bytes()
            path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                read_pinned_models(path)


if __name__ == '__main__':
    unittest.main()
