"""Strict local-workflow owner wire contract; no editor or filesystem effects.

Rust graph/command fingerprints use serde field order, NOT alphabetic JSON.
The explicitly ordered dictionaries below mirror core/local_workflow DTOs.
"""
from copy import deepcopy
import hashlib
import json
import re
from . import ingest_session_protocol as I

PROTOCOL = 1
MAX_REQUESTS = 256
IDENTITY = ('workflow_id', 'workflow_revision', 'graph_sha256', 'run_id',
            'input_occurrence_id', 'source_sha256', 'project_id', 'document_id',
            'node_id', 'operation_id')
DOCUMENT = ('project_id', 'document_id', 'document_revision', 'source_sha256', 'receipt_id')
PLAN = ('plan_id', 'plan_sha256', 'document_revision', 'output_root', 'recipe_sha256', 'targets')
NODE_FIELDS = {
    'profile': set(),
    'directory_source': ('root', 'recursive', 'include_existing', 'extensions', 'settle_ms'),
    'managed_import': ('project_id', 'project_path', 'managed_root'),
    'path_labels': ('rules',),
    'compatible_preset': ('preset_id', 'preset_sha256', 'when_all_labels'),
    'automatic_preset': ('preset_id', 'preset_sha256', 'when_all_labels', 'intent'),
    'export': ('output_root', 'recipe_sha256'),
}
AUTOMATIC_INTENT = {'schema': 'lrt.automatic-batch-intent.v1', 'mode': 'automatic',
                    'scope': 'directory_originals', 'source_mode': 'captured_file_list', 'originals': 'managed_copy_only',
                    'save': 'target_recipe', 'collision': 'fail_no_overwrite', 'unattended': True}
AUTOMATIC_PORTRAIT_INTENT = {**AUTOMATIC_INTENT,
    'portrait_scope': 'all_verified_detected_faces'}

AUTOMATIC_REFERENCE_INTENT = {**AUTOMATIC_INTENT,
    'reference_scope': 'stored_reference_per_target_fit',
    'reference_source_policy': 'reject_same_source'}

def automatic_intent(value):
    """Three exact declarations; neither substitutes for fresh job-start consent."""
    expected = (AUTOMATIC_REFERENCE_INTENT if type(value) is dict and 'reference_scope' in value
                else AUTOMATIC_PORTRAIT_INTENT if type(value) is dict and
                'portrait_scope' in value else AUTOMATIC_INTENT)
    intent = record(value, tuple(expected))
    if intent != expected or intent['unattended'] is not True:
        raise ValueError('Unsupported explicit automatic job intent')
    return intent


FIELDS = {
    'profile': set(),
    'preflight': {'graph', 'graph_sha256'},
    'execute': {'command'},
    'query': {'original_request_id', 'operation_id'},
    'open_review': {'operation_id', 'review_id'},
    'review_step': {'operation_id', 'step', 'payload'},
    'review_image': {'operation_id', 'review_id', 'review_sha256', 'side', 'sha256', 'page'},
}
# This is a declared, pinned v1 product profile, not an imitation image recipe.
# Each document's actual saved image recipe is frozen separately by cmd_export.
RECIPE_PROFILE = {
    'profile': 'lrt.workflow-export.jpeg-srgb.v1',
    'export_options': {'format': 'jpg', 'quality': 95, 'tile': 1024, 'bit_depth': 8,
                       'scale': 1, 'upscale_backend': 'lanczos3', 'sharpen': 0.0,
                       'output_profile': 'srgb', 'metadata_include_gps': False,
                       'conflict_policy': 'skip_and_report', 'tiff_compression': 'deflate'},
    'destination': {'mode': 'chosen_root', 'retain_hierarchy': False,
                    'conflict': 'ask', 'create_missing': False},
    'watermark': None, 'layout': None,
}


def encoded(value, *, sorted_keys=False):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      sort_keys=sorted_keys, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value, sorted_keys=True)).hexdigest()


RECIPE_SHA256 = digest(RECIPE_PROFILE)


def export_profiles():
    """Finite immutable choices; legacy profile identity and digest never change.

    This catalogue is not codec availability evidence. cmd_export still performs
    canonical validation and full-source/native16 checks for every document.
    """
    profiles = [deepcopy(RECIPE_PROFILE)]
    for name, fmt, quality, bits, compression in (
            ('jpeg80', 'jpg', 80, 8, 'deflate'),
            ('jpeg100', 'jpg', 100, 8, 'deflate'),
            ('png8', 'png', 95, 8, 'deflate'),
            ('tiff16', 'tif', 95, 16, 'none')):
        profile = deepcopy(RECIPE_PROFILE)
        profile['profile'] = 'lrt.workflow-export.' + name + '-srgb.v1'
        profile['export_options'].update(format=fmt, quality=quality,
                                         bit_depth=bits, tiff_compression=compression)
        profiles.append(profile)
    return [{'recipe_sha256': digest(profile), 'recipe_profile': profile} for profile in profiles]


def resolve_export_profile(recipe_sha256, *, automatic=False):
    for entry in export_profiles() if automatic else export_profiles()[:1]:
        if entry['recipe_sha256'] == recipe_sha256:
            return entry['recipe_profile']
    raise ValueError('Unsupported export profile/settings; select a returned immutable profile '
                     '(expanded formats require an automatic job). No format fallback is permitted')



def record(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Workflow owner fields are missing or unknown')
    return {key: deepcopy(value[key]) for key in keys}


def token(value):
    I.token(value)
    if not re.fullmatch('[A-Za-z0-9._:-]+', value):
        raise ValueError('Invalid workflow identity')
    return value


def text(value, maximum):
    if (type(value) is not str or not value or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Invalid bounded workflow text')
    return value


def envelope(value):
    if type(value) is not dict or len(encoded(value)) > 1024 * 1024:
        raise ValueError('Workflow owner request exceeds 1 MiB')
    action = value.get('action')
    if not isinstance(action, str) or action not in FIELDS:
        raise ValueError('Unknown workflow owner action')
    record(value, {'cmd', 'protocol', 'action', 'request_id'} | ({'session_id'} if action != 'profile' else set()) | FIELDS[action])
    if value['cmd'] != 'workflow_owner' or type(value['protocol']) is not int or value['protocol'] != PROTOCOL:
        raise ValueError('Unsupported workflow owner protocol')
    I.identity(value['request_id'])
    if action != 'profile': I.identity(value['session_id'])
    if action == 'preflight': I.digest(value['graph_sha256'])
    if action == 'query': I.identity(value['original_request_id'])
    if action in ('query', 'open_review', 'review_step', 'review_image'): I.digest(value['operation_id'])
    if action == 'open_review': text(value['review_id'], 256)
    if action == 'review_step':
        if value['step'] not in ('open_target', 'prepare_skin', 'approve', 'save_project', 'return_target') or type(value['payload']) is not dict:
            raise ValueError('Unknown preset handoff step')
    if action == 'review_image':
        text(value['review_id'], 256); I.digest(value['review_sha256']); I.digest(value['sha256'])
        if value['side'] not in ('before', 'after') or type(value['page']) is not int or not 0 <= value['page'] < 128:
            raise ValueError('Invalid exact review image page')
    return deepcopy(value)


def graph(value, expected_sha256):
    graph = record(value, ('schema_version', 'workflow_id', 'revision', 'nodes', 'edges'))
    if type(graph['schema_version']) is not int or graph['schema_version'] != 1:
        raise ValueError('Unsupported graph schema')
    token(graph['workflow_id'])
    if type(graph['revision']) is not int or not 1 <= graph['revision'] <= 9007199254740991:
        raise ValueError('Invalid graph revision')
    if type(graph['nodes']) is not list or not 3 <= len(graph['nodes']) <= 5:
        raise ValueError('Workflow requires a bounded source/import/export chain')
    nodes = {}
    for index, raw in enumerate(graph['nodes']):
        node = record(raw, ('id', 'error_policy', 'operation'))
        token(node['id'])
        if node['id'] in nodes or node['error_policy'] not in ('stop', 'skip', 'keep_continue'):
            raise ValueError('Invalid or repeated workflow node')
        kind = node['operation'].get('kind') if type(node['operation']) is dict else None
        if kind not in NODE_FIELDS: raise ValueError('Unsupported workflow node kind')
        operation = record(node['operation'], ('kind',) + NODE_FIELDS[kind])
        if node['error_policy'] == 'keep_continue' and kind != 'compatible_preset':
            raise ValueError('keep_continue requires a retained preset document')
        if kind == 'directory_source':
            I.path(operation['root'])
            if node['error_policy'] != 'stop': raise ValueError('Source errors must stop')
            if type(operation['recursive']) is not bool or type(operation['include_existing']) is not bool:
                raise ValueError('Source flags must be booleans')
            extensions = operation['extensions']
            if (type(extensions) is not list or not 1 <= len(extensions) <= 32
                    or any(type(x) is not str or not re.fullmatch('[a-z0-9]{1,10}', x) for x in extensions)
                    or len(set(extensions)) != len(extensions)):
                raise ValueError('Invalid explicit source extensions')
            if type(operation['settle_ms']) is not int or not 250 <= operation['settle_ms'] <= 300000:
                raise ValueError('Invalid source settle interval')
        elif kind == 'managed_import':
            token(operation['project_id']); I.path(operation['project_path']); I.path(operation['managed_root'])
        elif kind == 'path_labels':
            if type(operation['rules']) is not list or not 1 <= len(operation['rules']) <= 64:
                raise ValueError('Invalid label rule bound')
            rules = []
            for raw_rule in operation['rules']:
                rule = record(raw_rule, ('target', 'contains', 'label'))
                if rule['target'] not in ('filename', 'relative_path'): raise ValueError('Invalid label target')
                text(rule['contains'], 256); text(rule['label'], 128); rules.append(rule)
            operation['rules'] = rules
        elif kind in ('compatible_preset', 'automatic_preset'):
            token(operation['preset_id']); I.digest(operation['preset_sha256'])
            labels = operation['when_all_labels']
            if type(labels) is not list or len(labels) > 64: raise ValueError('Invalid preset labels')
            for label in labels: text(label, 128)
            if len(set(labels)) != len(labels): raise ValueError('Repeated preset label')
            if kind == 'automatic_preset':
                operation['intent'] = automatic_intent(operation['intent'])
        else:
            I.path(operation['output_root']); I.digest(operation['recipe_sha256'])
        node['operation'] = operation
        graph['nodes'][index] = node
        nodes[node['id']] = node
    if type(graph['edges']) is not list or len(graph['edges']) != len(nodes) - 1:
        raise ValueError('Workflow must be one linear chain')
    incoming, outgoing, edges = {key: 0 for key in nodes}, {}, []
    for raw in graph['edges']:
        edge = record(raw, ('from', 'to')); a, b = edge['from'], edge['to']
        if a not in nodes or b not in nodes or a == b or a in outgoing:
            raise ValueError('Invalid workflow edge or branching')
        incoming[b] += 1
        if incoming[b] > 1: raise ValueError('Workflow fan-in is unsupported')
        outgoing[a] = b; edges.append(edge)
    graph['edges'] = edges
    starts = [key for key, count in incoming.items() if count == 0]
    if len(starts) != 1: raise ValueError('Disconnected or cyclic workflow')
    ordered, cursor, seen = [], starts[0], set()
    while cursor is not None:
        if cursor in seen: raise ValueError('Cyclic workflow')
        seen.add(cursor); ordered.append(nodes[cursor]); cursor = outgoing.get(cursor)
    kinds = [node['operation']['kind'] for node in ordered]
    if (len(ordered) != len(nodes) or kinds[:2] != ['directory_source', 'managed_import']
            or kinds[-1] != 'export' or kinds[2:-1] not in ([], ['path_labels'], ['compatible_preset'], ['path_labels', 'compatible_preset'],
                                                         ['automatic_preset'], ['path_labels', 'automatic_preset'])):
        raise ValueError('Unsupported workflow order')
    if 'automatic_preset' in kinds and ordered[0]['operation']['include_existing'] is not True:
        raise ValueError('Automatic captured-file-list jobs require include_existing:true')
    if len(encoded(graph)) > 256 * 1024 or hashlib.sha256(encoded(graph)).hexdigest() != expected_sha256:
        raise ValueError('Graph SHA-256 differs from the exact Rust DTO')
    return graph, ordered


def document(value):
    value = record(value, DOCUMENT)
    token(value['project_id']); token(value['document_id'])
    text(value['document_revision'], 256); I.digest(value['source_sha256']); text(value['receipt_id'], 256)
    return value


def frozen(value):
    value = record(value, PLAN)
    text(value['plan_id'], 256); I.digest(value['plan_sha256']); text(value['document_revision'], 256)
    I.path(value['output_root']); I.digest(value['recipe_sha256'])
    if type(value['targets']) is not list or not 1 <= len(value['targets']) <= 64:
        raise ValueError('Invalid frozen output count')
    for path in value['targets']: I.path(path)
    if len(set(value['targets'])) != len(value['targets']): raise ValueError('Repeated output target')
    return value


def command(value):
    value = record(value, ('schema_version', 'identity', 'operation'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported owner command schema')
    identity = record(value['identity'], IDENTITY)
    for key in ('workflow_id', 'run_id', 'project_id', 'node_id'): token(identity[key])
    for key in ('graph_sha256', 'input_occurrence_id', 'source_sha256', 'operation_id'): I.digest(identity[key])
    token(identity['document_id'])
    if type(identity['workflow_revision']) is not int or not 1 <= identity['workflow_revision'] <= 9007199254740991:
        raise ValueError('Invalid command revision')
    operation = value['operation']
    kind = operation.get('kind') if type(operation) is dict else None
    if kind == 'freeze_export':
        operation = record(operation, ('kind', 'document', 'output_root', 'recipe_sha256'))
        I.path(operation['output_root']); I.digest(operation['recipe_sha256'])
    elif kind == 'start_export':
        operation = record(operation, ('kind', 'document', 'plan'))
        operation['plan'] = frozen(operation['plan'])
    elif kind == 'preflight_preset':
        operation = record(operation, ('kind', 'document', 'preset_id', 'preset_sha256', 'labels'))
        token(operation['preset_id']); I.digest(operation['preset_sha256'])
        if type(operation['labels']) is not list or len(operation['labels']) > 64:
            raise ValueError('Invalid preset label set')
        for label in operation['labels']: text(label, 128)
        if len(set(operation['labels'])) != len(operation['labels']): raise ValueError('Repeated preset label')
    elif kind == 'apply_preset':
        operation = record(operation, ('kind', 'document', 'preset_id', 'assessment'))
        token(operation['preset_id'])
        assessment = record(operation['assessment'], ('report_id', 'report_sha256', 'document_revision', 'preset_sha256', 'requires_review', 'review'))
        text(assessment['report_id'], 256); text(assessment['document_revision'], 256)
        I.digest(assessment['report_sha256']); I.digest(assessment['preset_sha256'])
        if type(assessment['requires_review']) is not bool:
            raise ValueError('Preset assessment mode must be explicit')
        if assessment['requires_review']:
            review = record(assessment['review'], ('receipt_id', 'report_sha256', 'document_id', 'document_revision', 'preset_sha256'))
            text(review['receipt_id'], 256); token(review['document_id']); text(review['document_revision'], 256)
            I.digest(review['report_sha256']); I.digest(review['preset_sha256'])
            assessment['review'] = review
        elif assessment['review'] is not None:
            raise ValueError('Automatic assessments cannot claim a human review')
        # Structural decoding is not authority: _bound checks this against the
        # actual preflight graph and the retained owner assessment before apply.
        operation['assessment'] = assessment
    else:
        raise ValueError('Unsupported workflow owner port; imports remain ingestion-owned')
    operation['document'] = document(operation['document'])
    empty_identity = {**identity, 'operation_id': ''}
    if hashlib.sha256(encoded([empty_identity, operation])).hexdigest() != identity['operation_id']:
        raise ValueError('Operation identity differs from the exact original core command')
    return {**value, 'identity': identity, 'operation': operation}
