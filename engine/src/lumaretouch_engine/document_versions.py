"""Runtime document identities and conservative mutation fences, outside undo state.

A fence is not a count of changed recipes. Admitted mutation attempts may invalidate
preflight even if a later guard rejects them. It never rewinds on undo/redo.
"""
from dataclasses import dataclass
import uuid

KEY='_lrt_runtime_version'
MAX_REVISION=(1<<64)-1

@dataclass(frozen=True)
class Version:
    document_id:str
    revision:int

class DocumentVersions:
    def __init__(self):
        self.owner=uuid.uuid4().hex
        self.workspace=uuid.uuid4().hex

    def version(self,row):
        value=row.get(KEY)
        # A copied/reconstructed row is not the retained original document.
        if not isinstance(value,dict) or value.get('owner')!=self.owner or value.get('object')!=id(row):
            value={'owner':self.owner,'object':id(row),'id':uuid.uuid4().hex,'revision':0}
            row[KEY]=value
        revision=value.get('revision')
        if type(revision) is not int or not 0<=revision<=MAX_REVISION:raise ValueError('invalid document mutation fence')
        return Version(value['id'],revision)

    def check_advance(self,row):
        version=self.version(row)
        if version.revision==MAX_REVISION:raise RuntimeError('document mutation fence exhausted; reopen workspace')
        return version

    def advance(self,row):
        version=self.check_advance(row)
        row[KEY]['revision']=version.revision+1
        return self.version(row)

    def new_workspace(self):
        self.workspace=uuid.uuid4().hex

    def find(self,rows,document_id):
        return next(((index,row) for index,row in enumerate(rows) if self.version(row).document_id==document_id),None)


def fences_current_document(name,p,edit_commands):
    """Read-only commands/selection never become accidental edit fences.

    Batch owns its individual target writes. Load/recovery lifecycle is handled at
    admitted recipe/recovery mutation points, not by bumping the previously selected row.
    """
    action=p.get('action','')
    if name in ('batch','people') or p.get('people_context') is not None:return False
    # Reviewed local preset claims validate the old revision before advancing
    # their own fence. Ordinary preset applies keep the existing dispatcher path.
    if name=='preset':return action=='apply' and p.get('preflight_token') is None
    if name=='history':return action in ('undo','redo','clear')
    if action in ('state','list','get','limits','preflight','validate'):return False
    return name in edit_commands or name in ('precompute','set_device')
