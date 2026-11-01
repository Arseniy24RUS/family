"""Apply the versioned infrastructure review without changing calculated fields.

Edit infrastructure_method_review.json to update an editorial status or limitation.
The Python analytics and JavaScript publication steps consume that same source.
"""

FIELDS = ('current_status', 'current_status_label', 'current_limitations')


def apply_method_review(methods, review):
    if (review.get('schema_version') != 1
            or review.get('project_id') != 'life_infrastructure'
            or methods.get('project_id') != review['project_id']):
        raise ValueError('Infrastructure method review has an unsupported schema or project')
    basis = review.get('current_review_basis')
    if not isinstance(basis, str) or not basis.strip():
        raise ValueError('Infrastructure method review needs a review basis')
    if not isinstance(review.get('items'), list) or not isinstance(methods.get('items'), list):
        raise ValueError('Infrastructure method review and catalogue need item arrays')
    editorial = {}
    for item in review['items']:
        method_id = item.get('method_id')
        if not isinstance(method_id, str) or not method_id.strip() or method_id in editorial:
            raise ValueError('Infrastructure method review has a missing or duplicate method id')
        if set(item) != {'method_id', *FIELDS} or any(
                not isinstance(item[field], str) or not item[field].strip() for field in FIELDS):
            raise ValueError('Infrastructure method review needs exactly three nonempty editorial fields: ' + method_id)
        editorial[method_id] = item
    ids = set()
    for item in methods['items']:
        method_id = item.get('method_id')
        if method_id in ids or method_id not in editorial:
            raise ValueError('Infrastructure method catalogue has a duplicate or unreviewed method: ' + str(method_id))
        ids.add(method_id)
    if ids != set(editorial):
        raise ValueError('Infrastructure method review contains methods absent from the catalogue')
    # Validate all entries before mutation. Numeric metadata and historical fields
    # in the inherited catalogue remain the responsibility of their data builders.
    for item in methods['items']:
        item.update({field: editorial[item['method_id']][field] for field in FIELDS})
    methods['current_review_basis'] = basis
    return methods
