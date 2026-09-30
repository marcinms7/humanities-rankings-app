"""Describe recorded evidence without promoting eligibility to verification."""

def source_provenance(source):
    metadata = source.metadata or {}
    if metadata.get('locally_verified') is True:
        origin = 'local_verification_recorded'
    elif metadata.get('owner_supplied') or metadata.get('report_type') or metadata.get('incoming_report_records'):
        origin = 'supplied_report'
    else:
        origin = 'origin_not_recorded'
    return {'consultation_origin': origin,
            'access_extent': metadata.get('access_level') or 'not_recorded',
            'evidence_role': metadata.get('evidence_role') or metadata.get('report_role') or 'not_recorded',
            'dependencies': metadata.get('depends_on_source_ids') or [],
            'underlying_source_id': source.underlying_source_id or metadata.get('underlying_source_id'),
            'independent_judgment_verified': None}


def order_status(ranking):
    editorial = ranking.scope.get('editorial') or {}
    orders = editorial.get('orders') or {}
    standing = (orders.get('standing') or {}).get('item_ids')
    reading = (orders.get('reading') or {}).get('item_ids')
    if not standing or not reading:
        return ''
    if standing == reading:
        return 'Both perspectives currently use the same order. A separate reading-value judgment is not established by these positions.'
    return 'Separate orders are saved. Their explanations and source limitations describe the evidence supporting each perspective.'
