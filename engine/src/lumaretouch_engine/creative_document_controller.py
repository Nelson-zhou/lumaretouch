"""Creative command ownership and return transactions, with ONE host history owner.

Host ports run under its command-thread exclusion. No UI optimistic state, hidden
undo stack, array mutation, automatic source overwrite or generated-image claim.
"""
from __future__ import annotations
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
import uuid
from . import creative_document_state as S


@dataclass(frozen=True)
class CreativePorts:
    read_document: Callable[[], dict | None]
    ownership_token: Callable[[], str]
    guard: Callable[[str], str | None]
    # Must atomically publish doc + one unified history step, or leave both intact.
    # None label means selection-only, no history/dirty mark, but revision changes.
    commit_document: Callable[[dict, dict, str | None], None]
    # Must atomically publish returned pixels + reset sliders + one history step
    # or create the new independent image. No original source bytes may be changed.
    commit_return: Callable[[dict], dict]
    history_recoverable: Callable[[], bool]


class CreativeController:
    def __init__(self, ports: CreativePorts, assets, *, receipt_limit=256):
        if type(receipt_limit) is not int or not 1 <= receipt_limit <= 4096:
            raise ValueError('Invalid creative receipt budget')
        self.ports, self.assets = ports, assets
        self.receipts = OrderedDict()
        self.receipt_limit = receipt_limit
        self.pending = None
        self._rendered = None

    def _check(self, envelope, operation):
        required = {'request_id','document_id','source_uid','expected_revision','ownership_token'}
        if type(envelope) is not dict or set(envelope) != required:
            raise ValueError('Malformed creative ownership envelope')
        if any(type(envelope[k]) is not str or not envelope[k] or len(envelope[k]) > 256
               for k in required-{'expected_revision'}):
            raise ValueError('Invalid creative command identity')
        if type(envelope['expected_revision']) is not int:
            raise ValueError('Invalid creative expected revision')
        document = self.ports.read_document()
        if document is None: raise ValueError('No creative document is open')
        S.validate(document,self.assets)
        if any(envelope[k] != document[k] for k in ('document_id','source_uid')):
            raise ValueError('Creative source/document changed')
        if envelope['expected_revision'] != document['revision']:
            raise ValueError('Creative revision changed; refresh before editing')
        if envelope['ownership_token'] != self.ports.ownership_token():
            raise ValueError('Creative edit ownership expired')
        reason = self.ports.guard(operation)
        if reason: raise ValueError(reason)
        return document

    def _receipt(self, envelope, status, revision, error=None):
        result = {**deepcopy(envelope),'status':status,'revision':revision}
        if error: result['message'] = error
        return result

    def _cache(self, envelope, payload, result):
        key = (envelope['ownership_token'],envelope['request_id'])
        self.receipts[key] = (deepcopy(envelope),deepcopy(payload),deepcopy(result))
        while len(self.receipts) > self.receipt_limit: self.receipts.popitem(last=False)
        return result

    def _existing(self, envelope, payload):
        key = (envelope.get('ownership_token'),envelope.get('request_id'))
        record = self.receipts.get(key)
        if record is None: return None
        if record[0] != envelope or record[1] != payload:
            raise ValueError('Creative request ID reused for another operation')
        return deepcopy(record[2])

    def command(self, envelope, command):
        existing = self._existing(envelope,command)
        if existing is not None: return existing
        document = self._check(envelope,'command')
        if self.pending is not None: raise ValueError('Creative render/return is pending')
        if command.get('action') == 'delete' and not self.ports.history_recoverable():
            raise ValueError('Recoverable unified history is required for layer deletion')
        after = S.apply(document,command,self.assets)
        if after == document:
            return self._cache(envelope,command,self._receipt(envelope,'no_change',document['revision']))
        label = None if command['action'] == 'select' else 'creative:' + command['action']
        try:
            self.ports.commit_document(deepcopy(after),deepcopy(document),label)
        except Exception as exc:
            self._cache(envelope,command,self._receipt(envelope,'unknown',document['revision'],'Commit requires authoritative reconciliation'))
            raise RuntimeError('Creative commit outcome requires reconciliation; do not retry') from exc
        # Do not report success if a defective adapter did not publish the state.
        if self.ports.read_document() != after:
            self._cache(envelope,command,self._receipt(envelope,'unknown',document['revision'],'Commit state mismatch'))
            raise RuntimeError('Creative commit outcome unknown; reload authoritative state, do not retry')
        return self._cache(envelope,command,self._receipt(envelope,'applied',after['revision']))

    def begin_return(self, envelope, mode):
        if mode not in ('new_image','update_original'): raise ValueError('Unknown creative return mode')
        if self._existing(envelope,{'return_mode':mode}) is not None:
            raise ValueError('Creative return request already has a receipt; do not repeat it')
        document = self._check(envelope,'return')
        if self.pending is not None: raise ValueError('Creative operation already pending')
        if mode == 'update_original' and not self.ports.history_recoverable():
            raise ValueError('Original update requires recoverable unified history')
        ticket = {'ticket_id':uuid.uuid4().hex,'envelope':deepcopy(envelope),
                  'mode':mode,'document':deepcopy(document)}
        self.pending = deepcopy(ticket)
        self._rendered = None
        return ticket

    def cancel_return(self, ticket_id):
        if self.pending is not None and self.pending['ticket_id'] == ticket_id:
            self.pending = None
            self._rendered = None

    def render_return(self, ticket, *, max_bytes=512_000_000):
        from .creative_document_render import CreativeRenderer
        if self.pending is None or ticket != self.pending:
            raise ValueError('Creative return ticket expired')
        envelope = ticket['envelope']
        self._check(envelope,'return_render')
        def cancelled():
            return self.pending != ticket or self.ports.ownership_token() != envelope['ownership_token'] or self.ports.read_document() != ticket['document']
        renderer = CreativeRenderer(ticket['document'],self.assets,max_bytes=max_bytes,cancelled=cancelled)
        record = renderer.render_asset()
        if cancelled(): raise ValueError('Creative return changed during rendering')
        identity = self.assets.intern(record)
        self._rendered = (ticket['ticket_id'],identity)
        return identity

    def complete_return(self, ticket, rendered_asset_id):
        """Commit only an exact current snapshot; renderer supplies real full pixels.

        The host must preserve its pre-return snapshot including active effects.
        Resetting sliders on the new baked baseline cannot recover the old image;
        unified undo/history can, because immutable original bytes remain retained.
        """
        if self.pending is None or ticket != self.pending:
            raise ValueError('Creative return ticket expired')
        envelope = ticket['envelope']; document = self._check(envelope,'return_commit')
        if document != ticket['document']: raise ValueError('Creative return snapshot changed')
        if self._rendered != (ticket['ticket_id'],rendered_asset_id):
            raise ValueError('Creative return must use the exact completed native render, not an arbitrary asset')
        rendered = self.assets.get(rendered_asset_id,'rgba')
        if (rendered['width'],rendered['height']) != (document['canvas']['width'],document['canvas']['height']):
            raise ValueError('Creative return is not the full-resolution canvas')
        plan = {'schema':1,'request_id':envelope['request_id'],'mode':ticket['mode'],
                'source_uid':document['source_uid'],'creative_document':deepcopy(document),
                'rendered_asset':rendered_asset_id,'unmodified_source_asset':document['source_asset'],
                'reset_sliders':True,'preserve_history':True,'provenance':'creative_composite'}
        # commit_return is the sole mutation boundary. If it raises after changing
        # host state the adapter must surface unknown outcome, never blindly retry.
        try:
            result = self.ports.commit_return(deepcopy(plan))
        except Exception as exc:
            self._cache(envelope,{'return_mode':ticket['mode']},self._receipt(envelope,'unknown',document['revision'],'Return requires reconciliation'))
            raise RuntimeError('Creative return outcome requires reconciliation; do not retry') from exc
        finally:
            self.pending = None
            self._rendered = None
        if type(result) is not dict or result.get('status') != 'applied' or not result.get('document_id'):
            self._cache(envelope,{'return_mode':ticket['mode']},self._receipt(envelope,'unknown',document['revision'],'Return state mismatch'))
            raise RuntimeError('Creative return outcome unknown; verify host state before retry')
        receipt = self._receipt(envelope,'applied',document['revision'])
        receipt['returned_document_id'] = result['document_id']
        return self._cache(envelope,{'return_mode':ticket['mode']},receipt)
