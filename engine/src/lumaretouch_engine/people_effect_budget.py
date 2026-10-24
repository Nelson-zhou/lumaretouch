# SPDX-License-Identifier: GPL-3.0-or-later
"""Remaining resident budget before allocating another owned source effect."""
import numpy as np


def remaining(total, analyses, fields, current_field, effects, local, *banks):
    seen = set()
    owned = 0
    for row in analyses.values():
        for array in row.values():
            if isinstance(array, np.ndarray) and id(array) not in seen:
                seen.add(id(array))
                owned += array.nbytes
    owned += sum(field.resident_bytes() for field in fields) + current_field.resident_bytes()
    owned += sum(array.nbytes for record in (*effects, *local)
                 for array in (record.delta, record.weights, record.chroma_shift, record.log_gain)
                 if array is not None)
    for bank in banks:
        for row in (bank or {}).values():
            if not isinstance(row, dict):
                continue
            for array in row.values():
                if isinstance(array, np.ndarray) and id(array) not in seen:
                    seen.add(id(array))
                    owned += array.nbytes
    return total - owned
