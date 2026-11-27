from __future__ import annotations

from . import event_logger

MAX_BATCH_CHARS = 30_000


def doc_to_conllu(doc) -> str:
    conllu_lines: list[str] = []
    for sent in doc.sentences:
        for word in sent.words:
            line = (
                f"{word.id}\t{word.text}\t{word.lemma}\t{word.upos}\t"
                f"{word.xpos if word.xpos else '_'}\t"
                f"{word.feats if word.feats else '_'}\t"
                f"{word.head}\t{word.deprel}\t_\t_"
            )
            conllu_lines.append(line)
        conllu_lines.append("")
    return "\n".join(conllu_lines)


def text_to_conllu(text: str, nlp) -> str:
    try:
        doc = nlp(text)
    except Exception as exc:
        event_logger.error(
            "STANZA_PARSE_FAILED",
            "Stanza parsing failed",
            str(exc),
            "Check the Stanza model and input text encoding.",
        )
        return ""
    return doc_to_conllu(doc)


def texts_to_conllu_batch(
    texts: list[str],
    nlp,
    max_batch_chars: int = MAX_BATCH_CHARS,
    max_batch_docs: int = 32,
) -> list[str]:
    """Parses texts with Stanza bulk_process, bounded by document and char budgets."""
    results = [""] * len(texts)
    non_empty = [(idx, text) for idx, text in enumerate(texts) if text]
    if not non_empty:
        return results

    import stanza

    sub_batches: list[list[tuple[int, str]]] = []
    current_batch: list[tuple[int, str]] = []
    current_chars = 0
    for item in non_empty:
        text_len = len(item[1])
        if current_batch and (
            len(current_batch) >= max_batch_docs or current_chars + text_len > max_batch_chars
        ):
            sub_batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(item)
        current_chars += text_len
    if current_batch:
        sub_batches.append(current_batch)

    for sub in sub_batches:
        if len(sub) == 1:
            idx, text = sub[0]
            results[idx] = text_to_conllu(text, nlp)
            continue
        try:
            docs = [stanza.Document([], text=text) for _, text in sub]
            parsed_docs = nlp.bulk_process(docs)
            for (idx, _), doc in zip(sub, parsed_docs):
                results[idx] = doc_to_conllu(doc)
        except Exception:
            for idx, text in sub:
                results[idx] = text_to_conllu(text, nlp)
    return results


def parse_conllu(conllu_str: str) -> list[list[list[str]]]:
    sentences: list[list[list[str]]] = []
    current_sent: list[list[str]] = []
    for line in conllu_str.strip().split("\n"):
        line = line.strip()
        if not line:
            if current_sent:
                sentences.append(current_sent)
                current_sent = []
        elif not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) == 10 and parts[0].isdigit() and parts[6].isdigit():
                current_sent.append(parts)
    if current_sent:
        sentences.append(current_sent)
    return sentences
