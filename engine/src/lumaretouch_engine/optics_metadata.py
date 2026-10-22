"""Optional, bounded ExifTool metadata read; never installs or writes source tags."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time


def read(path):
    binary = os.environ.get('LRT_EXIFTOOL') or shutil.which('exiftool')
    if not binary or not Path(binary).is_file(): raise RuntimeError('RAW 镜头元数据读取需要显式安装 ExifTool；未自动下载')
    # -config '' disables executable per-user config. Only whitelisted camera
    # calibration tags leave the helper; GPS, owner, serial and paths are ignored.
    command = [str(Path(binary).resolve()),'-config','','-j','-n','-Make','-Model','-LensMake','-LensModel',
               '-FocalLength','-FNumber','-SubjectDistance','-Orientation','--',str(Path(path).resolve())]
    process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,cwd='/')
    output,errors = bytearray(),bytearray(); selector = selectors.DefaultSelector(); deadline = time.monotonic()+15
    try:
        for handle,target in ((process.stdout,output),(process.stderr,errors)):
            os.set_blocking(handle.fileno(),False); selector.register(handle,selectors.EVENT_READ,target)
        while selector.get_map():
            remaining = deadline-time.monotonic()
            if remaining<=0: raise RuntimeError('RAW 镜头元数据读取超时')
            for key,_ in selector.select(min(remaining,.1)):
                data = os.read(key.fileobj.fileno(),4096)
                if not data: selector.unregister(key.fileobj); continue
                key.data.extend(data)
                if len(output)+len(errors)>32768: raise ValueError('RAW 镜头元数据超过预算')
        if process.wait(timeout=max(.01,deadline-time.monotonic()))!=0: raise ValueError('ExifTool 无法读取此文件的镜头元数据')
        values = json.loads(output)
        if type(values) is not list or len(values)!=1 or type(values[0]) is not dict: raise ValueError('ExifTool 镜头元数据格式无效')
        fields = {'Make','Model','LensMake','LensModel','FocalLength','FNumber','SubjectDistance','Orientation'}
        return {k:v for k,v in values[0].items() if k in fields}
    finally:
        selector.close()
        if process.poll() is None: process.kill(); process.wait()
        for handle in (process.stdout,process.stderr): handle.close()
