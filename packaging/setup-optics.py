#!/usr/bin/env python3
"""Explicit release source acquisition/build, artifact staging and offline install.

Nothing executes at import. Normal app startup never invokes this program.
No compilers or source download are needed on the end user's machine.
"""
import argparse,base64,csv,hashlib,io,json,os,platform,shutil,subprocess,sys,tarfile,tempfile,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
LOCK=next((p for p in (HERE/'optics-sources.lock.json',HERE/'runtime/optics-sources.lock.json') if p.is_file()),None)

def fail(message):raise SystemExit('Optics: '+message)
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(data):return hashlib.sha256(data).hexdigest()
def run(args,**kw):
    print('→ '+' '.join(str(x) for x in args),flush=True)
    return subprocess.run([str(x) for x in args],check=True,**kw)
def capture(args,**kw):return subprocess.check_output([str(x) for x in args],text=True,**kw).strip()
def lock():
    if LOCK is None:fail('source lock is missing next to this packaged installer')
    return read(LOCK)
def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def clean_git_env():
    env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0')
    return env

def fetch(cache):
    """The ONLY network-enabled action. Exact three official Git commits, no deps."""
    cache.mkdir(parents=True,exist_ok=True)
    for name in ('lensfun','lensfunpy','lensfun_database'):
        item=lock()[name];repo=cache/(name+'.git')
        if repo.exists():
            if repo.is_symlink() or capture(['git','-C',repo,'rev-parse','--is-bare-repository'],env=clean_git_env())!='true' or capture(['git','-C',repo,'rev-parse',item['commit']+'^{commit}'],env=clean_git_env())!=item['commit']:fail('existing source cache does not match pinned bare repository')
            print('Verified existing source object: '+name);continue
        run(['git','init','--bare',repo],env=clean_git_env())
        run(['git','-C',repo,'-c','protocol.allow=never','-c','protocol.https.allow=always','fetch','--depth=1',item['repository'],item['commit']],env=clean_git_env())
        if capture(['git','-C',repo,'rev-parse','FETCH_HEAD'],env=clean_git_env())!=item['commit']:fail('official source commit mismatch')
    print('Sources acquired only. No build, installation, database update or model download occurred.')

def unpack_source(cache,name,destination,archive):
    item=lock()[name];repo=cache/(name+'.git')
    if not repo.is_dir() or repo.is_symlink():fail(f'missing explicit source cache {repo}; run fetch separately')
    if capture(['git','-C',repo,'rev-parse',item['commit']+'^{commit}'],env=clean_git_env())!=item['commit']:fail('source object mismatch')
    with archive.open('wb') as out:run(['git','-C',repo,'archive','--format=tar',item['commit']],stdout=out,env=clean_git_env())
    destination.mkdir()
    with tarfile.open(archive) as tar:
        members=tar.getmembers()
        for member in members:
            parts=Path(member.name).parts
            if Path(member.name).is_absolute() or '..' in parts or not (member.isfile() or member.isdir()):fail('unsafe or unsupported source archive member')
        tar.extractall(destination,members=members,filter='data')
    return sha(archive.read_bytes())

def db_digest(files):
    digest=hashlib.sha256()
    for path in sorted(files):digest.update(path.name.encode());digest.update(b'\0');digest.update(path.read_bytes())
    return digest.hexdigest()

def build(cache,output,python):
    if sys.platform!='linux':fail('this release builder supports Linux only')
    if output.exists():fail('output must be a new directory; no existing bundle is overwritten')
    for executable in ('git','cmake','pkg-config','cc','c++','readelf'):
        if shutil.which(executable) is None:fail('missing release build prerequisite: '+executable)
    run(['pkg-config','--exists','glib-2.0'])
    # Explicit prerequisites, no resolver/build-isolation dependency downloads.
    run([python,'-c','import setuptools,numpy,Cython,wheel,lxml; import sys; assert sys.version_info[:2] == (3,12), "release runtime requires CPython 3.12"'])
    cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='optics-build-',dir=cache) as tmp:
        work=Path(tmp);sources={};sources_hash={}
        for name in ('lensfun','lensfunpy','lensfun_database'):
            sources[name]=work/name
            sources_hash[name]=unpack_source(cache,name,sources[name],work/(name+'.tar'))
        prefix=work/'prefix';native_build=work/'native-build'
        run(['cmake','-S',sources['lensfun'],'-B',native_build,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_POLICY_VERSION_MINIMUM=3.5',
             '-DBUILD_STATIC=OFF','-DBUILD_TESTS=OFF','-DBUILD_DOC=OFF','-DBUILD_LENSTOOL=OFF','-DINSTALL_HELPER_SCRIPTS=OFF','-DINSTALL_PYTHON_MODULE=OFF',
             '-DCMAKE_INSTALL_LIBDIR=lib','-DCMAKE_INSTALL_PREFIX='+str(prefix)])
        run(['cmake','--build',native_build,'--parallel',str(min(4,os.cpu_count() or 1))]);run(['cmake','--install',native_build])
        # Independent modern calibration snapshot, converted by the OFFICIAL
        # converter rather than rewriting calibration math or freezing 2023 XML.
        db_source=sources['lensfun_database'];converter=db_source/lock()['lensfun_database']['converter']
        converter_blob=capture(['git','-C',cache/'lensfun_database.git','rev-parse',lock()['lensfun_database']['commit']+':'+lock()['lensfun_database']['converter']],env=clean_git_env())
        if converter_blob!=lock()['lensfun_database']['converter_git_blob']:fail('official database converter identity mismatch')
        timestamp=int(capture(['git','-C',cache/'lensfun_database.git','show','-s','--format=%ct',lock()['lensfun_database']['commit']],env=clean_git_env()))
        converted=work/'converted';database=work/'database';database.mkdir()
        run([python,'-c',
             'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import xml_converter as c; c.generate_database_tarballs([c.XMLFile(str(p)) for p in sorted(Path(sys.argv[2]).glob("*.xml"))],int(sys.argv[3]),sys.argv[4])',
             converter.parent,db_source/'data/db',timestamp,converted])
        with tarfile.open(converted/'version_1.tar.bz2') as archive:
            members=archive.getmembers()
            if not members or len(members)>4096 or sum(m.size for m in members)>32*1024*1024:fail('converted database budget exceeded')
            for member in members:
                if not member.isfile() or Path(member.name).name!=member.name or not member.name.endswith('.xml'):fail('invalid official conversion output')
            archive.extractall(database,members=members,filter='data')
        xml=sorted(database.glob('*.xml'))
        if not xml or len(xml)>4096 or sum(p.stat().st_size for p in xml)>32*1024*1024:fail('invalid released database')
        wrapper=sources['lensfunpy'];db_target=wrapper/'lensfunpy/db_files';db_target.mkdir(exist_ok=True)
        for path in xml:shutil.copyfile(path,db_target/path.name)
        env=os.environ.copy();env.update(PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',PYTHONNOUSERSITE='1',
            PKG_CONFIG_PATH=str(prefix/'lib/pkgconfig'),LD_LIBRARY_PATH=str(prefix/'lib'),LDFLAGS='-Wl,-rpath,$ORIGIN/_native')
        wheels=work/'wheels';wheels.mkdir()
        run([python,'-m','pip','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',wheels,wrapper],env=env)
        built=list(wheels.glob('lensfunpy-*.whl'))
        if len(built)!=1:fail('expected exactly one built wrapper wheel')
        with zipfile.ZipFile(built[0]) as wheel:contents={info.filename:wheel.read(info) for info in wheel.infolist() if not info.is_dir()}
        extensions=[data for name,data in contents.items() if Path(name).name.startswith('_lensfun') and name.endswith('.so')]
        if len(extensions)!=1:fail('compiled wrapper library missing or ambiguous')
        extension=work/'wrapper.so';extension.write_bytes(extensions[0])
        linkage=capture(['readelf','-d',extension])
        if '$ORIGIN/_native' not in linkage or 'liblensfun.so.1' not in linkage:fail('wrapper does not use the replaceable bundled library')
        records=[name for name in contents if name.endswith('.dist-info/RECORD')]
        if len(records)!=1:fail('invalid wrapper wheel record')
        record=records[0];del contents[record]
        # Real replaceable shared library, not a static proprietary-link claim.
        libs=list((prefix/'lib').glob('liblensfun.so*'))
        if not libs:fail('shared Lensfun library was not produced')
        for lib in libs:
            if lib.resolve().parent!=(prefix/'lib').resolve():fail('library link escaped staging')
            contents['lensfunpy/_native/'+lib.name]=lib.read_bytes()
        for name in sources:
            contents['lensfunpy/optics_sources/'+name+'.tar']=(work/(name+'.tar')).read_bytes()
            license_files=[p for p in sources[name].rglob('*') if p.is_file() and (p.name.lower().startswith(('copying','license')) or p.name.lower() in ('gpl-3.0.txt','lgpl-3.0.txt','cc-by-sa-3.0.txt'))]
            if not license_files:fail('corresponding license text missing: '+name)
            if name=='lensfun' and not all(any(p.name.lower()==required for p in license_files) for required in ('gpl-3.0.txt','lgpl-3.0.txt')):fail('full GPL/LGPL license texts missing from Lensfun source')
            if name=='lensfun_database' and not any(p.name=='COPYING.CC_BY-SA_3.0' for p in license_files):fail('database CC-BY-SA license text missing')
            for license_file in license_files:contents['lensfunpy/optics_licenses/'+name+'/'+str(license_file.relative_to(sources[name]))]=license_file.read_bytes()
        notice=('Lensfun '+lock()['lensfun']['version']+' by the Lensfun contributors; library LGPL-3.0-or-later.\n'
                'Modern camera/lens XML database CC-BY-SA-3.0; converted by official v2-to-v1 converter, original author attributions retained. ACM-only calibrations are not available in Lensfun 0.3.4.\n'
                'https://lensfun.github.io/manual/latest/license.html\nhttps://creativecommons.org/licenses/by-sa/3.0/\n'
                'lensfunpy 1.18.0 by Maik Riechert, MIT. Exact corresponding source archives and licenses are included.\n'
                'System GLib and C/C++ runtimes remain dynamic distribution dependencies, not included in this wheel.\n'
                'Rebuild or replace lensfunpy/_native/liblensfun.so.1 under the LGPL; source builder and pins accompany the app.\n')
        contents['lensfunpy/optics_licenses/NOTICE.txt']=notice.encode()
        facts={'version':1,'sources':{name:{**lock()[name],'archive_sha256':sources_hash[name]} for name in sources},
               'database_sha256':db_digest(xml),'database_files':len(xml),'database_directory':'db_files',
               'database_format':1,'database_source_sha256':db_digest((db_source/'data/db').glob('*.xml')),
               'database_converter_sha256':sha(converter.read_bytes()),'database_source_epoch':timestamp,
               'libc':list(platform.libc_ver()),
               'python':capture([python,'-c','import sys; print(sys.version)']),'python_tag':'cp312','machine':platform.machine(),'platform':platform.platform(),
               'application_commit':capture(['git','-C',HERE.parent,'rev-parse','HEAD']),
               'build_python_dependencies':capture([python,'-m','pip','freeze','--all']),
               'wrapper_linkage':linkage,
               'glib':capture(['pkg-config','--modversion','glib-2.0']),'compiler':capture(['cc','--version']),
               'cmake':capture(['cmake','--version']),'status':'built-not-product-accepted'}
        contents['lensfunpy/optics-provenance.json']=json.dumps(facts,sort_keys=True,indent=2).encode()
        buffer=io.StringIO();writer=csv.writer(buffer,lineterminator='\n')
        for name,data in sorted(contents.items()):writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='),len(data)])
        writer.writerow([record,'','']);contents[record]=buffer.getvalue().encode()
        output.mkdir(parents=True);final=output/built[0].name
        with zipfile.ZipFile(final,'w',compression=zipfile.ZIP_DEFLATED) as wheel:
            for name,data in sorted(contents.items()):wheel.writestr(name,data)
        write(output/'BUNDLE.json',{'version':1,'wheel':final.name,'wheel_sha256':sha(final.read_bytes()),'provenance':facts})
    print('Built release bundle with library, database, source and license records. Product/platform acceptance is still required.')

def verify_bundle(bundle):
    manifest=bundle/'BUNDLE.json'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>256*1024:fail('missing/oversized bundle manifest')
    value=read(manifest);name=value.get('wheel')
    if value.get('version')!=1 or not isinstance(name,str) or Path(name).name!=name or not name.startswith('lensfunpy-1.18.0-') or not name.endswith('.whl'):fail('invalid bundle wheel identity')
    wheel=bundle/name
    if wheel.is_symlink() or not wheel.is_file() or wheel.stat().st_size>256*1024*1024 or sha(wheel.read_bytes())!=value.get('wheel_sha256'):fail('bundle wheel checksum mismatch')
    facts=value.get('provenance',{})
    tags=wheel.name[:-4].rsplit('-',3)[-3:]
    if facts.get('machine')!=platform.machine() or facts.get('python_tag')!='cp312' or tags!=['cp312','cp312','linux_'+platform.machine()]:fail('bundle architecture/CPython ABI does not match this supported Linux target')
    libc=platform.libc_ver();built_libc=facts.get('libc',[])
    if len(built_libc)!=2 or libc[0]!=built_libc[0] or tuple(map(int,libc[1].split('.')))<tuple(map(int,built_libc[1].split('.'))):fail('bundle requires '+str(built_libc)+'; rebuild on the supported oldest target distribution')
    if facts.get('database_format')!=1:fail('unsupported database runtime format')
    expected_commit=os.environ.get('LRT_OPTICS_APPLICATION_COMMIT')
    if expected_commit and facts.get('application_commit')!=expected_commit:fail('bundle producer used a different application commit')
    for name in ('lensfun','lensfunpy','lensfun_database'):
        if any(facts.get('sources',{}).get(name,{}).get(key)!=lock()[name][key] for key in ('repository','commit','version','license')):fail('bundle official source pin mismatch')
    with zipfile.ZipFile(wheel) as z:
        entries=z.infolist()
        if len({i.filename for i in entries})!=len(entries) or len(entries)>10000 or sum(i.file_size for i in entries)>512*1024*1024:fail('bundle archive budget exceeded')
        for entry in entries:
            if '\\' in entry.filename or Path(entry.filename).is_absolute() or '..' in Path(entry.filename).parts or (entry.external_attr>>16)&0o170000==0o120000:fail('unsafe bundle member')
        if json.loads(z.read('lensfunpy/optics-provenance.json'))!=facts:fail('wheel provenance differs from bundle')
        for name in ('lensfun','lensfunpy','lensfun_database'):
            if sha(z.read('lensfunpy/optics_sources/'+name+'.tar'))!=facts['sources'][name]['archive_sha256']:fail('corresponding source archive checksum mismatch')
        digest=hashlib.sha256();xml=sorted(n for n in z.namelist() if n.startswith('lensfunpy/db_files/') and n.endswith('.xml'))
        if not xml or len(xml)!=facts.get('database_files') or sum(z.getinfo(n).file_size for n in xml)>32*1024*1024:fail('invalid staged database')
        for name in xml:digest.update(Path(name).name.encode());digest.update(b'\0');digest.update(z.read(name))
        if digest.hexdigest()!=facts.get('database_sha256'):fail('staged database checksum mismatch')
        if not any(n.startswith('lensfunpy/_native/liblensfun.so.') for n in z.namelist()) or 'lensfunpy/optics_licenses/NOTICE.txt' not in z.namelist():fail('library/notice missing from bundle')
    return value,wheel

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('fetch','build','verify','stage','install'))
    parser.add_argument('--cache',type=Path,default=HERE.parent/'build/optics/cache');parser.add_argument('--bundle',type=Path,default=HERE.parent/'build/optics/bundle')
    parser.add_argument('--python',default=sys.executable);parser.add_argument('--destination',type=Path)
    args=parser.parse_args();lock()
    if args.action=='fetch':fetch(args.cache.resolve());return
    if args.action=='build':build(args.cache.resolve(),args.bundle.resolve(),args.python);return
    value,wheel=verify_bundle(args.bundle.resolve())
    if args.action=='stage':
        if args.destination is None:fail('stage requires --destination')
        dest=args.destination;dest.mkdir(parents=True,exist_ok=True)
        if any(p.name not in ('BUNDLE.json',wheel.name) or p.is_symlink() for p in dest.iterdir()):fail('stage destination contains unexpected old files')
        shutil.copyfile(wheel,dest/wheel.name);write(dest/'BUNDLE.json',value)
    elif args.action=='install':
        # Explicit runtime setup, OFFLINE only; never compile or resolve deps here.
        run([args.python,'-c','import sys,platform; assert sys.implementation.name=="cpython" and sys.version_info[:2]==(3,12), "Bundled optics requires the normal CPython 3.12 runtime"; assert platform.machine()=='+repr(value['provenance']['machine'])])
        run([args.python,'-m','pip','install','--no-index','--no-deps','--force-reinstall',wheel],env={**os.environ,'PIP_NO_INDEX':'1','PIP_DISABLE_PIP_VERSION_CHECK':'1'})
        run([args.python,'-c','import lensfunpy; assert tuple(lensfunpy.lensfun_version[:3])==(0,3,4); print("Lensfun runtime linked:",lensfunpy.lensfun_version)'])
    print('Optics '+args.action+' completed; no claim of product acceptance.')

if __name__=='__main__':main()
