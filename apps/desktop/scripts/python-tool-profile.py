"""Build-time inventory; remove only the obsolete voice dependency closure.

Keep optional non-voice distributions: their absence from pip's dependency graph
alone does not prove that a Skill never imports them. No user environment changes.
"""
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root=Path(sys.argv[1]).resolve(strict=True)
absolute=lambda path:Path(os.path.abspath(path))
requirements=Path(sys.argv[2]).read_text(encoding='utf-8')
installed={canonicalize_name(d.metadata['Name']):d for d in metadata.distributions() if d.metadata.get('Name')}
roots=[Requirement(line.split('#',1)[0].strip()) for line in requirements.splitlines() if line.split('#',1)[0].strip()]

def closure(pending):
    found={};expanded=set()
    while pending:
        requirement=pending.pop();name=canonicalize_name(requirement.name)
        if requirement.marker and not requirement.marker.evaluate():continue
        identity=(name,tuple(sorted(requirement.extras)))
        if identity in expanded:continue
        distribution=installed.get(name)
        if not distribution or not requirement.specifier.contains(distribution.version,prereleases=True):
            raise RuntimeError('Native dependency missing or incompatible: '+str(requirement))
        found[name]=distribution
        expanded.add(identity)
        for item in distribution.requires or []:
            child=Requirement(item)
            if not child.marker or any(child.marker.evaluate({'extra':extra}) for extra in ['',*requirement.extras]):
                child.marker=None
                pending.append(child)
    return found

required=closure(roots.copy())
voice=closure([Requirement('edge-tts')]) if 'edge-tts' in installed else {}
removed={name:d for name,d in voice.items() if name not in required}
retained_files={absolute(d.locate_file(item)) for d in required.values() for item in d.files or []}
other_files={absolute(d.locate_file(item)) for name,d in installed.items() if name not in removed for item in d.files or []}
excluded=[];directories=set();checked_directories=set()
for distribution in removed.values():
    for item in distribution.files or []:
        file=absolute(distribution.locate_file(item))
        if file.is_relative_to(root) and file not in retained_files:
            excluded.append(file.relative_to(root).as_posix())
            site=absolute(distribution.locate_file(''))
            if file.is_relative_to(site):
                candidate=site/file.relative_to(site).parts[0]
                if candidate not in checked_directories:
                    checked_directories.add(candidate)
                    if candidate.is_dir() and not any(p.is_relative_to(candidate) for p in other_files):
                        directories.add(candidate.relative_to(root).as_posix())
print(json.dumps({'schema':1,'removed_voice_distributions':sorted(removed),
    'required_distributions':{name:d.version for name,d in sorted(required.items())},
    'excluded_directories':sorted(directories),'excluded_files':sorted(set(excluded))}))
