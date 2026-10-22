"""Derive ONE fixed ASCII task from pinned official CLIP vocabulary/merges.

This is not a general tokenizer. For the exact string below, official Unicode
letter matching, lowercasing, whitespace cleanup and byte encoding reduce to
these four ASCII words. No regex library or approximation is involved.
"""
import json

TASK = 'the task is semantic'


def derive(model_directory):
    vocab = json.loads((model_directory / 'vocab.json').read_text())
    lines = (model_directory / 'merges.txt').read_text().splitlines()
    # Official CLIP vocabulary: 49,152 - 256 - 2 ranked BPE merges.
    ranks = {tuple(line.split()): index for index, line in enumerate(lines[1:49152 - 256 - 2 + 1])}
    encoded = [vocab['<|startoftext|>']]
    pieces = []
    for token in TASK.split(' '):
        word = tuple(token[:-1]) + (token[-1] + '</w>',)
        while len(word) > 1:
            pairs = set(zip(word, word[1:]))
            pair = min(pairs, key=lambda item: ranks.get(item, float('inf')))
            if pair not in ranks:
                break
            merged, i = [], 0
            while i < len(word):
                if i + 1 < len(word) and (word[i], word[i + 1]) == pair:
                    merged.append(word[i] + word[i + 1]); i += 2
                else:
                    merged.append(word[i]); i += 1
            word = tuple(merged)
        pieces.extend(word)
        encoded.extend(vocab[piece] for piece in word)
    encoded.append(vocab['<|endoftext|>'])
    if len(encoded) > 77:
        raise ValueError('固定语义任务超过官方任务序列长度')
    # OneFormerProcessor multiplies CLIP input_ids by its attention_mask.
    # The tokenizer's EOS padding is therefore zeroed, not fed as 49407.
    mask = [1] * len(encoded) + [0] * (77 - len(encoded))
    padded = encoded + [vocab['<|endoftext|>']] * (77 - len(encoded))
    return {'task': TASK, 'pieces': pieces, 'attention_mask': mask,
            'token_ids': [token * valid for token, valid in zip(padded, mask)]}
