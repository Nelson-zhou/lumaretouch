"""Persist identity and independently owned history without rewriting recipe provenance."""
from copy import deepcopy
from .virtual_copy_host import IDENTITY_KEYS


def save_row(project, runtime, stored, codec):
    stored.update({k:runtime[k] for k in IDENTITY_KEYS})
    stored['document_revision'] = runtime.get('document_revision',0)
    stored['source_relocation_aliases'] = deepcopy(runtime.get('_source_relocation_aliases',{}))
    stored['library_metadata'] = deepcopy(runtime.get('_library_metadata',{}))
    stored['library_edit_time_ns'] = runtime.get('_library_edit_time_ns')
    from .virtual_copy_people import encode
    context = encode(runtime)
    if context is not None: stored['people_context'] = context
    dropped = []
    # Precompute outputs are not history-owned; preserve their exact recipes and
    # accepted support assets while avoiding duplicate inferred model tensors.
    stacks = {key:[{k:v for k,v in state.items() if k not in ('_precompute',)} for state in runtime.get(key,[])]
              for key in ('undo','redo')}
    stored['document_history'] = codec.encode(stacks,project['assets'],dropped,'document_history.'+runtime['document_id'])
    if dropped: raise ValueError('文档历史不能无损保存：'+str(dropped[:3]))


def restore_row(project, stored, runtime, codec, dc_types):
    runtime.update({k:stored[k] for k in IDENTITY_KEYS})
    from .virtual_copy_people import decode
    decode(runtime,stored)
    runtime['fingerprint'] = deepcopy(project['source_assets'][stored['source_asset_id']]['fingerprint'])
    runtime['document_revision'] = stored.get('document_revision',0)
    runtime['_project_version_id'] = stored.get('active_version') or runtime['recipe_version_id']
    runtime.pop('_lrt_runtime_version',None)
    runtime['_source_relocation_aliases'] = deepcopy(stored.get('source_relocation_aliases',{}))
    runtime['_library_metadata'] = deepcopy(stored.get('library_metadata',{}))
    runtime['_library_edit_time_ns'] = stored.get('library_edit_time_ns')
    if 'document_history' in stored:
        dropped = []
        stacks = codec.decode(stored['document_history'],project['assets'],dropped,'document_history.'+runtime['document_id'],dc_types=dc_types)
        if dropped or not isinstance(stacks,dict) or set(stacks)!={'undo','redo'}:
            raise ValueError('文档历史不能无损恢复')
        for key,stack in stacks.items():
            if not isinstance(stack,list) or len(stack)>64 or any(not isinstance(x,dict) for x in stack):
                raise ValueError('文档历史格式无效')
            runtime[key] = stack
        runtime['_history_owned'] = True


def save_receipts(engine, project):
    controller = getattr(engine,'_virtual_copy_controller',None)
    previous = (engine._project or {}).get('virtual_copy_receipts',{})
    receipts = deepcopy(previous)
    if controller:
        workspace = engine._document_versions().workspace
        for (epoch,rid),entry in controller.receipts.items():
            if epoch == workspace:
                receipts[rid] = {k:deepcopy(v) for k,v in entry['result'].items() if k!='state'}
    project['virtual_copy_receipts'] = dict(list(receipts.items())[-256:])
