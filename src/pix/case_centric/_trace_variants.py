"""Shared deterministic grouping of recorded activity sequences."""

from collections import defaultdict


def ranked_activity_variants(traces_by_id, case_ids):
    variants = defaultdict(list)
    for cid in case_ids:
        variants[tuple(e.activity for e in traces_by_id[cid].events)].append(cid)
    return tuple(
        (word, tuple(sorted(members)))
        for word, members in sorted(
            variants.items(), key=lambda item: (-len(item[1]), item[0])
        )
    )
