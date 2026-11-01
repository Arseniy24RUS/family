"""Deterministic packaging and exact-tie ordering for generated publications.

These helpers do not round computed values or rewrite original source files.
Archive timestamps describe the generated container, not the dated evidence
inside it; observation and publication dates remain in the source manifests.
"""
import gzip
import io
import zipfile


def gzip_bytes(content, compresslevel=9):
    """Use a zero timestamp, no filename, and OS=255 on every Python platform."""
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, filename='', mode='wb',
                       compresslevel=compresslevel, mtime=0) as stream:
        stream.write(content)
    return output.getvalue()


def write_zip_entry(archive, name, content):
    """Preserve content bytes with fixed ZIP metadata independent of checkout."""
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(entry, content, compresslevel=9)


def descending_term_indices(values, terms):
    """Sort by exact descending weight, then by Unicode term for exact ties.

    No tolerance is used: numerically close but distinct weights keep their
    mathematical order, and original floating-point values are not altered.
    """
    if len(values) != len(terms):
        raise ValueError('Every TF-IDF weight needs its term')
    return sorted(range(len(values)), key=lambda index: (-values[index], str(terms[index])))
