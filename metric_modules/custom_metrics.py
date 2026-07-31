from __future__ import annotations

import math
from collections import deque

from .stanza_conllu import parse_conllu


def get_valid_node_info(sent_tokens: list[list[str]]) -> tuple[int, list[int]]:
    n_total = len(sent_tokens)
    if n_total <= 1:
        return 0, []

    id_to_idx = {int(token[0]): i for i, token in enumerate(sent_tokens)}
    root_idx = next((i for i, token in enumerate(sent_tokens) if int(token[6]) == 0), None)
    if root_idx is None:
        return 0, []

    children = [[] for _ in range(n_total)]
    for i, token in enumerate(sent_tokens):
        head = int(token[6])
        if head != 0 and head in id_to_idx:
            children[id_to_idx[head]].append(i)

    depths = [-1] * n_total
    depths[root_idx] = 0
    queue = deque([root_idx])
    while queue:
        current = queue.popleft()
        for child in children[current]:
            if depths[child] == -1:
                depths[child] = depths[current] + 1
                queue.append(child)

    valid_indices = [
        i for i, token in enumerate(sent_tokens)
        if token[3] not in ("PUNCT", "SYM", "X") and depths[i] != -1
    ]
    valid_depths = [depths[i] for i in valid_indices]
    return len(valid_indices), valid_depths


def compute_alpha_deplength(n_valid: int, valid_depths: list[int]) -> float:
    if n_valid <= 1:
        return 0.0
    sum_depth = sum(depth for depth in valid_depths if depth > 0)
    mhl = sum_depth / (n_valid - 1)
    return (n_valid - 1) / mhl if mhl > 0 else 0.0


def compute_mhdd(n_valid: int, valid_depths: list[int]) -> float:
    if n_valid <= 1:
        return 0.0
    maxhl = max(valid_depths) + 1 if valid_depths else 0
    return (n_valid - 1) / maxhl if maxhl > 0 else 0.0


def compute_mdd(sent_tokens: list[list[str]]) -> float:
    valid_tokens = [token for token in sent_tokens if token[3] not in ("PUNCT", "SYM", "X")]
    total_dist = 0
    n_rel = 0
    for token in valid_tokens:
        head = int(token[6])
        if head == 0:
            continue
        idx = int(token[0])
        total_dist += abs(idx - head)
        n_rel += 1
    if n_rel == 0:
        return 0.0
    return total_dist / n_rel


def compute_ndd(mdd: float, root_distance: int, sentence_length: int) -> float:
    if mdd <= 0 or root_distance <= 0 or sentence_length <= 0:
        return 0.0
    denominator = math.sqrt(root_distance * sentence_length)
    if denominator == 0:
        return 0.0
    return abs(math.log(mdd / denominator))


def compute_custom_metrics(conllu_str: str) -> dict[str, float]:
    sentences = parse_conllu(conllu_str)
    alpha_list: list[float] = []
    mhdd_list: list[float] = []
    mdd_list: list[float] = []
    ndd_list: list[float] = []

    for sent in sentences:
        valid_tokens = [token for token in sent if token[3] not in ("PUNCT", "SYM", "X")]
        if len(valid_tokens) <= 1:
            continue

        root_tokens = [token for token in valid_tokens if int(token[6]) == 0]
        if not root_tokens:
            continue
        root_distance = int(root_tokens[0][0])
        n_valid, valid_depths = get_valid_node_info(sent)
        n_rel = sum(1 for token in valid_tokens if int(token[6]) != 0)

        alpha = compute_alpha_deplength(n_valid, valid_depths)
        mhdd = compute_mhdd(n_valid, valid_depths)
        mdd = compute_mdd(sent)
        ndd = compute_ndd(mdd, root_distance, n_rel)

        if alpha > 0:
            alpha_list.append(alpha)
        if mhdd > 0:
            mhdd_list.append(mhdd)
        if mdd > 0:
            mdd_list.append(mdd)
        if ndd > 0:
            ndd_list.append(ndd)

    avg = lambda values: sum(values) / len(values) if values else 0.0
    return {
        "MHDD": round(avg(mhdd_list), 4),
        "AlphaDepLength": round(avg(alpha_list), 4),
        "MDD": round(avg(mdd_list), 4),
        "NDD": round(avg(ndd_list), 4),
    }