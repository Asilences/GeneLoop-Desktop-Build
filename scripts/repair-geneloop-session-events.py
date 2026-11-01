"""Repair only GeneLoop audit envelopes; retain immutable backups and native guards.

Linux JSONL v3 only. Preview is the default. A write requires an explicit private
backup directory, the same kernel session lock as DSH, an unchanged source hash,
and a successful read through the installed DSH persistence implementation.
No task states, event data, sequence numbers, timestamps or budgets are changed.
"""
import argparse,ctypes,ctypes.util,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path

LIMIT=128*1024*1024
AUDITS={'geneloop/presented-proof','geneloop/file-compaction'}
sha=lambda b:hashlib.sha256(b).hexdigest()

def fixed(path):
    path=Path(path).absolute()
    if path.resolve()!=path:raise ValueError('symlink or non-canonical path')
    current=path
    while current!=current.parent:
        if current.is_symlink():raise ValueError('symlink parent')
        current=current.parent
    return path

class Zstd:
    def __init__(self):
        name=ctypes.util.find_library('zstd')
        if not name:raise RuntimeError('system libzstd required')
        self.lib=ctypes.CDLL(name)
        for name,args,ret in [
            ('ZSTD_findFrameCompressedSize',[ctypes.c_void_p,ctypes.c_size_t],ctypes.c_size_t),
            ('ZSTD_getErrorName',[ctypes.c_size_t],ctypes.c_char_p),
            ('ZSTD_decompress',[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t],ctypes.c_size_t),
            ('ZSTD_compressBound',[ctypes.c_size_t],ctypes.c_size_t),
            ('ZSTD_compress',[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int],ctypes.c_size_t),
            ('ZSTD_isError',[ctypes.c_size_t],ctypes.c_uint)]:
            fn=getattr(self.lib,name);fn.argtypes=args;fn.restype=ret
    def checked(self,n):
        if self.lib.ZSTD_isError(n):raise ValueError('invalid Zstandard frame')
        return n
    def frames(self,raw):
        buf=ctypes.create_string_buffer(raw);offset=0;total=0
        while offset<len(raw):
            ptr=ctypes.byref(buf,offset)
            size=self.checked(self.lib.ZSTD_findFrameCompressedSize(ptr,len(raw)-offset))
            if not 0<size<=len(raw)-offset:raise ValueError('invalid frame size')
            bound=65536
            while True:
                out=ctypes.create_string_buffer(bound)
                length=self.lib.ZSTD_decompress(out,bound,ptr,size)
                if not self.lib.ZSTD_isError(length):break
                reason=self.lib.ZSTD_getErrorName(length).decode().lower()
                if 'buffer is too small' not in reason or bound>=LIMIT:raise ValueError('invalid or oversized Zstandard frame: '+reason)
                bound=min(LIMIT,bound*2)
            total+=length
            if total>LIMIT:raise ValueError('decoded log exceeds maintenance limit')
            yield raw[offset:offset+size],out.raw[:length]
            offset+=size
    def compress(self,raw):
        buf=ctypes.create_string_buffer(raw);size=self.lib.ZSTD_compressBound(len(raw))
        out=ctypes.create_string_buffer(size)
        length=self.checked(self.lib.ZSTD_compress(out,size,buf,len(raw),3))
        return out.raw[:length]

def valid_audit(row):
    data=row.get('data')
    if not isinstance(data,dict) or not isinstance(row.get('seq'),int) or row['seq']<0 or not isinstance(row.get('time'),int):
        return False
    if 'surfaceOp' in row or 'sourceEventSeqs' in row:return False
    if row['type']=='geneloop/presented-proof':
        return isinstance(data.get('callId'),str) and isinstance(data.get('files'),list) and all(
            isinstance(f,dict) and isinstance(f.get('path'),str) and isinstance(f.get('name'),str) and
            isinstance(f.get('bytes'),int) and 0<=f['bytes']<=30*1024*1024 and
            bool(re.fullmatch('[0-9a-f]{64}',str(f.get('sha256','')))) for f in data['files'])
    return (data.get('phase')=='summary' and isinstance(data.get('compactionId'),str) and
            isinstance(data.get('projectedSurface'),bool) and isinstance(data.get('turn'),int))

def transform(raw,compressed=True):
    z=Zstd() if compressed else None
    frames=z.frames(raw) if z else [(raw,raw)]
    output=[];changed=0;header=None
    for original,decoded in frames:
        lines=[];frame_changed=False
        for line in decoded.splitlines(keepends=True):
            if not line.strip():lines.append(line);continue
            row=json.loads(line)
            if header is None:
                if row.get('type')!='session' or row.get('version')!=3:raise ValueError('only native session format v3 is supported')
                header=row
            if row.get('type') in AUDITS and row.get('ignorable') is not True:
                if not valid_audit(row):raise ValueError('invalid GeneLoop audit envelope')
                before=json.loads(json.dumps(row));row['ignorable']=True
                after=dict(row);after.pop('ignorable')
                if after!=before:raise ValueError('audit data changed')
                line=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode()
                changed+=1;frame_changed=True
            lines.append(line)
        output.append(z.compress(b''.join(lines)) if frame_changed and z else b''.join(lines) if frame_changed else original)
    if header is None:raise ValueError('missing session header')
    return b''.join(output),changed,header

def atomic(path,raw):
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.geneloop-envelope-',delete=False) as f:
        temporary=Path(f.name);os.chmod(temporary,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def native_check(path,raw,header,checker,node):
    with tempfile.TemporaryDirectory(prefix='geneloop-cold-read-') as folder:
        os.chmod(folder,0o700);root=Path(folder)
        target=root/path.parent.parent.name/path.parent.name/path.name
        target.parent.mkdir(parents=True,mode=0o700);target.write_bytes(raw);target.chmod(0o600)
        result=subprocess.run([node,str(checker),str(root),header['id']],capture_output=True,text=True,timeout=60)
        if result.returncode:raise RuntimeError('native cold-read validation refused repaired copy: '+result.stderr[-1200:])

def repair(path,backup,write,checker,node):
    path=fixed(path)
    st=path.stat()
    if not path.is_file() or st.st_nlink!=1 or st.st_uid!=os.getuid() or st.st_size>32*1024*1024:
        raise ValueError('log must be an owned, single-link bounded regular file')
    original=path.read_bytes();updated,count,header=transform(original,path.suffix=='.zstd')
    if header['id']!=path.parent.name:raise ValueError('owning session identity mismatch')
    if not count:return None
    native_check(path,updated,header,checker,node)
    row={'path':str(path),'session_id':header['id'],'audit_envelopes':count,'before_sha256':sha(original),'after_sha256':sha(updated),'native_read_passed':True,'written':False}
    if not write:return row
    import fcntl
    lock=fixed(path.parent/'session.lock')
    fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
    try:
        held=os.fstat(fd)
        if held.st_nlink!=1 or held.st_uid!=os.getuid():raise ValueError('invalid native session lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (lock.stat().st_dev,lock.stat().st_ino)!=(held.st_dev,held.st_ino):raise ValueError('session lock changed')
        current=path.stat()
        if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns)!=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns) or path.read_bytes()!=original:raise ValueError('source changed; do not repair a running session')
        folder=backup/sha(str(path).encode());folder.mkdir(mode=0o700)
        copy=folder/path.name;copy.write_bytes(original);copy.chmod(0o600)
        row['backup']=str(copy)
        atomic(path,updated);row['written']=True
        receipt=folder/'receipt.json';receipt.write_text(json.dumps(row,ensure_ascii=False,indent=2));receipt.chmod(0o600)
    finally:os.close(fd)
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-root',type=Path,action='append',required=True)
    parser.add_argument('--backup-root',type=Path)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--node',default='node')
    args=parser.parse_args()
    if os.name!='posix':parser.error('Linux maintenance only')
    backup=fixed(args.backup_root) if args.backup_root else None
    if args.write:
        if backup is None:parser.error('--write requires --backup-root')
        backup.mkdir(mode=0o700,parents=False,exist_ok=False)
    checker=Path(__file__).with_name('check-native-session-log.mjs')
    records=[];errors=[]
    for root in args.session_root:
        root=fixed(root)
        for path in sorted(root.glob('*/session-*/session.v3.jsonl*')):
            if path.name not in {'session.v3.jsonl','session.v3.jsonl.zstd'}:continue
            try:
                row=repair(path,backup,args.write,checker,args.node)
                if row:records.append(row)
            except Exception as error:errors.append({'path':str(path),'error':str(error)})
    report={'write_requested':args.write,'records':records,'errors':errors}
    if args.write:
        p=backup/'report.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2));p.chmod(0o600)
    print(json.dumps({'repaired_or_previewed':len(records),'audit_envelopes':sum(r['audit_envelopes'] for r in records),'errors':len(errors),'written':sum(r['written'] for r in records),'backup':str(backup) if backup else None}))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
