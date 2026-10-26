"""Frozen per-document Original policy decisions, not another codec or renderer.

Only admission calls the Rust resolver. Retry/worker validate the retained
decision and exact recipe/source identity; they never choose a replacement
format, precision, name or recipe. This envelope lives inside destination v1's
settings_json so the existing destination plan digest covers every decision.
"""
from copy import deepcopy
import json
import re

from .export_destination_policy import canonical, digest

SCHEMA = 'lrt.export-format-plan.v1'
DECISION_SCHEMA = 'lrt.export-format-decision.v1'
_OPTIONS = {'quality', 'tiff_compression', 'metadata_include_gps', 'target_size', 'output_profile', 'output_profile_asset_id'}
_APPLICABLE = {'quality', 'tiff_compression', 'gps', 'target_size'}
_DECISION = {'schema', 'item_id', 'document_id', 'source_asset_id', 'recipe_version_id',
             'recipe_sha256', 'fact_id', 'source_facts', 'effective_asset', 'codec', 'bits',
             'extension', 'applicable_options', 'options', 'decision_id'}


def _sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('original_invalid_identity')
    return value


def require_intent(command, *, preview):
    """Client supplies intent only, never source facts or policy resolutions."""
    if 'bit_depth' in command:
        raise ValueError('Original 按每个来源保留受支持的编码位深；请移除 bit_depth 参数')
    ids = command.get('document_ids')
    if (type(ids) is not list or not ids or any(type(v) is not str or not v for v in ids)
            or len(ids) != len(set(ids)) or 'images' in command):
        raise ValueError('Original 需要明确的文档身份，不接受旧式 images 路径导出')
    if type(command.get('destination_policy')) is not dict:
        raise ValueError('Original 需要冻结的逐文档目录预览；不接受旧式 out_dir 导出')
    if not preview:
        _sha(command.get('destination_plan_id'))


def freeze(entry_ids, entries, snapshots, *, quality, tiff_compression,
           metadata_include_gps, target_size, output_profile):
    from .export_format_native import resolve
    from .export_source_facts import capabilities, validate as validate_facts
    from .optics_candidate_identity import fingerprint
    from .export_format_profile import freeze as freeze_profile
    profile_asset = freeze_profile(output_profile)
    available = capabilities()
    decisions = {}
    # Resolve every source before even building a directory plan or queue item.
    for key in entry_ids:
        entry = entries[key]
        facts = validate_facts(entry['source_facts'])
        resolved = resolve(facts, available)
        applicable = resolved['applicable_options']
        if target_size is not None and not applicable['target_size']:
            raise ValueError('Original 近似目标大小要求整批全部为 JPEG8；不会改变格式或丢弃大小请求')
        if metadata_include_gps and not applicable['gps']:
            raise ValueError('Original 批次含 RGB16；现有 16-bit 写入器不支持 GPS，请显式关闭 GPS')
        compression = None
        if applicable['tiff_compression']:
            compression = tiff_compression or ('none' if resolved['bits'] == 16 else 'deflate')
        options = {'quality': quality if applicable['quality'] and target_size is None else None,
                   'tiff_compression': compression, 'metadata_include_gps': metadata_include_gps,
                   'target_size': deepcopy(target_size), 'output_profile': output_profile,
                   'output_profile_asset_id':profile_asset['sha256'] if profile_asset else None}
        snapshot, for_document = snapshots[key]
        if not for_document or any(not entry.get(k) for k in ('document_id', 'source_asset_id', 'recipe_version_id')):
            raise ValueError('original_missing_authenticated_document_recipe')
        body = {'schema': DECISION_SCHEMA, 'item_id': key,
                **{k: entry[k] for k in ('document_id', 'source_asset_id', 'recipe_version_id')},
                'recipe_sha256': fingerprint(snapshot, exact=True),
                'fact_id': facts['fact_id'], 'source_facts': deepcopy(facts),
                'effective_asset': deepcopy(facts['effective_asset']),
                **resolved, 'options': options}
        decision = {**body, 'decision_id': digest(body)}
        decisions[key] = decision
    envelope = {'schema': SCHEMA, 'requested_format': 'original', 'entries': decisions,
                'output_profile_asset':profile_asset, 'selection_order':list(entry_ids)}
    validate(envelope)
    for key, decision in decisions.items():
        entries[key]['format_decision'] = deepcopy(decision)
    return envelope


def validate(value):
    """Structural/integrity validation only: no filesystem or policy re-resolution."""
    from .export_source_facts import validate as validate_facts
    if (type(value) is not dict or set(value) != {'schema', 'requested_format', 'entries', 'output_profile_asset', 'selection_order'}
            or value['schema'] != SCHEMA or value['requested_format'] != 'original'
            or type(value['entries']) is not dict or not 1 <= len(value['entries']) <= 100000):
        raise ValueError('original_invalid_format_plan')
    order = value['selection_order']
    if (type(order) is not list or any(type(key) is not str for key in order)
            or len(order) != len(set(order)) or set(order) != set(value['entries'])):
        raise ValueError('original_selection_order_mismatch')
    from .export_format_profile import validate as validate_profile
    validate_profile(value['output_profile_asset'])
    for key, decision in value['entries'].items():
        if type(key) is not str or type(decision) is not dict or set(decision) != _DECISION:
            raise ValueError('original_invalid_format_decision')
        if decision['schema'] != DECISION_SCHEMA or decision['item_id'] != key:
            raise ValueError('original_decision_item_mismatch')
        for field in ('document_id', 'source_asset_id', 'recipe_version_id'):
            if type(decision[field]) is not str or not decision[field]:
                raise ValueError('original_invalid_document_identity')
        _sha(decision['recipe_sha256']); _sha(decision['fact_id']); _sha(decision['decision_id'])
        if key != 'document:' + digest_document_id(decision['document_id']):
            raise ValueError('original_document_item_mismatch')
        facts = validate_facts(decision['source_facts'])
        if facts['fact_id'] != decision['fact_id'] or facts['effective_asset'] != decision['effective_asset']:
            raise ValueError('original_source_facts_mismatch')
        codec, bits = decision['codec'], decision['bits']
        if (codec not in ('jpg', 'png', 'tif', 'webp') or type(bits) is not int
                or bits not in (8, 16) or bits == 16 and codec not in ('png', 'tif')
                or decision['extension'] != codec):
            raise ValueError('original_invalid_codec_precision')
        # Invariants on an already retained result, NOT a Python resolver or a
        # fallback. Only Rust creates decisions; retries never call it again.
        from .export_format_native import CONTAINERS, CODECS
        if (facts['source_kind'] != 'bitmap' or not facts['single_frame']
                or facts['variant'] not in ('encoded','creative') or bits != facts['precision']
                or CODECS.get(CONTAINERS[facts['container']]) != codec):
            raise ValueError('original_decision_source_inconsistent')
        applicable, options = decision['applicable_options'], decision['options']
        if (type(applicable) is not dict or set(applicable) != _APPLICABLE
                or any(type(v) is not bool for v in applicable.values())
                or type(options) is not dict or set(options) != _OPTIONS):
            raise ValueError('original_invalid_options')
        if (applicable['quality'] != (bits == 8 and codec != 'tif')
                or applicable['tiff_compression'] != (codec == 'tif')
                or applicable['gps'] != (bits == 8)
                or applicable['target_size'] != (codec == 'jpg' and bits == 8)):
            raise ValueError('original_decision_applicability_inconsistent')
        if type(options['metadata_include_gps']) is not bool or not isinstance(options['output_profile'], str):
            raise ValueError('original_invalid_metadata_options')
        profile = value['output_profile_asset']
        if profile is None:
            if options['output_profile_asset_id'] is not None or options['output_profile'] not in ('srgb','source','none'):
                raise ValueError('original_missing_frozen_profile')
        elif options['output_profile_asset_id'] != profile['sha256'] or options['output_profile'] != profile['path']:
            raise ValueError('original_frozen_profile_mismatch')
        if options['metadata_include_gps'] and not applicable['gps']:
            raise ValueError('original_unsupported_gps')
        if options['quality'] is not None and (not applicable['quality'] or type(options['quality']) is not int or not 1 <= options['quality'] <= 100):
            raise ValueError('original_invalid_quality')
        if applicable['tiff_compression']:
            if options['tiff_compression'] not in ('none', 'deflate', 'lzw'):
                raise ValueError('original_invalid_tiff_compression')
        elif options['tiff_compression'] is not None:
            raise ValueError('original_inapplicable_tiff_compression')
        if options['target_size'] is not None:
            from .export_target_size_policy import parse_target_size
            if not applicable['target_size'] or options['quality'] is not None:
                raise ValueError('original_inapplicable_target_size')
            parse_target_size(options['target_size'], format=codec, bit_depth=bits)
        if digest({k:v for k,v in decision.items() if k != 'decision_id'}) != decision['decision_id']:
            raise ValueError('original_decision_integrity')
    return value


def digest_document_id(document_id):
    from hashlib import sha256
    return sha256(document_id.encode('utf-8')).hexdigest()


def validate_settings(settings, destination_entries=None):
    if type(settings) is not dict:
        raise ValueError('invalid_destination_settings')
    envelope = settings.get('format_plan')
    if settings.get('format') != 'original':
        if envelope is not None:
            raise ValueError('original_plan_on_explicit_export')
        return None
    if 'bit_depth' in settings:
        raise ValueError('original_batch_bit_depth_forbidden')
    validate(envelope)
    if destination_entries is not None:
        expected = set(envelope['entries'])
        seen = set()
        for entry in destination_entries:
            key = entry.item_id
            if key.startswith('layout::'):
                continue  # Layout owns its independent PNG/PDF8 contract.
            primary = key[:-7] if key.endswith('::clean') else key
            if primary not in expected:
                raise ValueError('original_destination_item_mismatch')
            decision = envelope['entries'][primary]
            if not entry.target.endswith('.' + decision['extension']):
                raise ValueError('original_destination_extension_mismatch')
            if key == primary:
                seen.add(primary)
        if seen != expected:
            raise ValueError('original_destination_selection_mismatch')
    return envelope


def worker_decision(opts, key, entry, snapshot, *, source_stamp=None):
    """Retained settings/recipe only; full source hashing is owned by verify_entry."""
    from .export_destination_policy import restore
    from .optics_candidate_identity import fingerprint
    plan = restore(opts['destination_plan'])
    envelope = validate_settings(json.loads(plan.settings_json), plan.entries)
    if envelope is None or canonical(envelope) != canonical(opts.get('format_plan')):
        raise ValueError('original_retained_format_plan_mismatch')
    decision = envelope['entries'][key]
    if decision != entry.get('format_decision') or decision['source_facts'] != entry.get('source_facts'):
        raise ValueError('original_retained_decision_mismatch')
    if any(decision[k] != entry.get(k) for k in ('document_id', 'source_asset_id', 'recipe_version_id')):
        raise ValueError('original_retained_document_mismatch')
    if decision['source_facts']['fingerprint'] != entry.get('fingerprint'):
        raise ValueError('original_retained_fingerprint_mismatch')
    if entry.get('path') != decision['source_facts']['fingerprint']['path']:
        raise ValueError('original_retained_source_path_mismatch')
    if source_stamp is not None and list(source_stamp) != decision['source_facts']['decoder_stamp']['file_stamp']:
        raise ValueError('original_frozen_source_stamp_changed')
    if fingerprint(snapshot, exact=True) != decision['recipe_sha256']:
        raise ValueError('original_frozen_recipe_changed')
    return decision


def receipt_fields(decision):
    return {'requested_format': 'original', 'resolved_format': decision['codec'],
            'bits': decision['bits'], 'decision_id': decision['decision_id'],
            'fact_id': decision['fact_id'], 'effective_asset': deepcopy(decision['effective_asset'])}
