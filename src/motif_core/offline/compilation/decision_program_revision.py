"""Apply model-authored revisions to the decision program's intermediate representation."""

import copy

from src.motif_core.reuse.experience_registry import digest


def apply_model_tree_edits(program,answer,component):
    """Apply disjoint, model-authored replacements verbatim; never infer a repair."""
    if component not in ('guard','request','bind') or answer.get('component')!=component:
        raise ValueError('tree revision component mismatch')
    if answer.get('base_program_sha256')!=digest(program):raise ValueError('tree revision base changed')
    if answer.get('moves'):
        if answer.get('replacements'):raise ValueError('one tree edit representation required')
        revised=copy.deepcopy(program)
        def parent_of(path):
            if not isinstance(path,list) or not path:raise ValueError('nonempty tree move path required')
            node=revised
            for k in path[:-1]:
                if isinstance(node,list) and type(k)is int and 0<=k<len(node):node=node[k]
                elif isinstance(node,dict) and type(k)is str and k in node:node=node[k]
                else:raise ValueError('invalid tree move path')
            return node,path[-1]
        for move in answer['moves']:
            source,target=move['from'],move['path']
            if target[:len(source)]==source:raise ValueError('tree move into own descendant')
            parent,index=parent_of(source)
            if not isinstance(parent,list) or type(index)is not int or not 0<=index<len(parent):
                raise ValueError('tree move source must be an existing array member')
            value=parent.pop(index)
            parent,index=parent_of(target)
            if not isinstance(parent,list) or type(index)is not int or not 0<=index<=len(parent):
                raise ValueError('tree move target must be an array insertion')
            parent.insert(index,value)
        return revised
    edits=answer.get('replacements')
    if not isinstance(edits,list) or not edits:raise ValueError('nonempty tree revision required')
    paths=[]
    for edit in edits:
        path=edit.get('path')
        if not isinstance(path,list) or not path or any(type(k) not in (int,str) for k in path):
            raise ValueError('invalid tree revision path')
        if not isinstance(edit.get('replacement'),list):raise ValueError('program subtree required')
        for prior in paths:
            if path[:len(prior)]==prior or prior[:len(path)]==path:
                raise ValueError('overlapping tree revisions')
        node=program
        for k in path:
            if isinstance(node,list) and type(k)is int and 0<=k<len(node):node=node[k]
            elif isinstance(node,dict) and type(k)is str and k in node:node=node[k]
            else:raise ValueError('tree revision path does not identify an existing node')
        if not isinstance(node,list):raise ValueError('existing program subtree required')
        paths.append(path)
    revised=copy.deepcopy(program)
    for edit in edits:
        parent=revised
        for k in edit['path'][:-1]:parent=parent[k]
        parent[edit['path'][-1]]=copy.deepcopy(edit['replacement'])
    return revised
