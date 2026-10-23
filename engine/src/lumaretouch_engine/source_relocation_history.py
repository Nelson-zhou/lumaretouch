"""Operational aliases for retained histories, never rewritten provenance records.

Caller first finds the original canonical runtime document ID. A path alias alone
is never sufficient: the current full source digest must still match the digest
recorded by the completed relocation transaction.
"""
from .source_relocation_io import Budget, hash_file
from .source_relocation_transaction import expected


def matches(row, historical_path):
    if row['path'] == historical_path:
        return True  # Preserve the pre-existing non-relocation restore policy.
    aliases = row.get('_source_relocation_aliases')
    if not isinstance(aliases, dict) or historical_path not in aliases:
        return False
    try:
        fp = expected(row)
        if aliases[historical_path] != fp['sha256']: return False
        actual = hash_file(row['path'], Budget(lambda: False), fp['bytes'])
        return actual['sha256'] == fp['sha256']
    except (OSError, ValueError):
        return False
