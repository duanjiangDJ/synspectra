from __future__ import annotations


def text_to_conllu(text: str, nlp) -> str:
    try:
        doc = nlp(text)
    except Exception as exc:
        print(f"Stanza parsing failed: {exc}")
        return ""

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