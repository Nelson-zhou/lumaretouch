"""Levels recipe ownership and command transaction, independent from Engine."""
from dataclasses import dataclass
from typing import Callable
from .ops import levels as L

@dataclass(frozen=True)
class LevelsPorts:
    guard:Callable[[str],str|None]
    document_id:Callable[[],str]
    install_pipeline:Callable[[dict],object]
    render_frame:Callable[[str],dict]
    status:Callable[[],dict]

class LevelsController:
    def __init__(self,ports:LevelsPorts,emit:Callable[[dict],None]):
        self.ports=ports;self.emit=emit;self._spec=L.default_levels()

    def snapshot(self):return L.check_levels(self._spec)

    def restore_spec(self,value):self._spec=L.check_levels(value)

    def handle_command(self,p:dict):
        success=False;failure=None
        request=p.get('request_id')
        if type(request) is not str or len(request)>128:request=None
        try:
            why=self.ports.guard('levels')
            if why:raise ValueError(why)
            if set(p)-{'cmd','action','spec','gesture_id','request_id','document_id'}:raise ValueError('levels unknown fields')
            document=p.get('document_id')
            if type(document) is not str or not document or len(document)>64 or document!=self.ports.document_id():
                raise ValueError('levels document changed; retry on the current photo')
            action=p.get('action','set');gesture=p.get('gesture_id','')
            if action not in ('set','clear') or type(gesture) is not str or len(gesture)>128:
                raise ValueError('levels action/gesture_id invalid')
            if 'request_id' in p and request is None:raise ValueError('levels request_id invalid')
            if action=='set' and type(p.get('spec')) is not dict:raise ValueError('levels set requires complete spec')
            spec=L.check_levels(p['spec'] if action=='set' else None)
            previous=self.snapshot()
            try:
                self.ports.install_pipeline(spec);self._spec=spec
                frame=self.ports.render_frame('levels')
                frame['doc_state']=self.ports.status()
            except Exception:
                self._spec=previous
                try:
                    self.ports.install_pipeline(previous)
                    self.emit(self.ports.render_frame('levels_rollback'))
                except Exception as rollback:
                    self.emit({'event':'engine_warn','warn':f'色阶回滚帧失败，请重新导入：{rollback}'})
                raise
            self.emit(frame);success=True
        except Exception as error:
            failure=str(error)[:2000]
            self.emit({'event':'error','error':f'色阶未提交，已保留上一配方：{failure}'})
        finally:
            self.emit({'event':'levels_result','request_id':request,'success':success,
                       'spec':self.snapshot(),'error':failure,'document_id':self.ports.document_id()})
