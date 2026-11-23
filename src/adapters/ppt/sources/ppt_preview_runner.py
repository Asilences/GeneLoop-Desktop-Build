"""Read a version-bound exported PNG and write one host-owned preview only."""
from pathlib import Path
import base64
import hashlib
import json
import sys
from PIL import Image


def preview_region(request, *, workspace=Path('/work')):
    def fixed(logical, *, new=False):
        if not isinstance(logical, str) or not logical.startswith('/work/outputs/') or '\\' in logical:
            raise ValueError('preview_path_invalid')
        relative = Path(logical.removeprefix('/work/'))
        if '..' in relative.parts:
            raise ValueError('preview_path_invalid')
        target = workspace / relative
        for item in [target, *target.parents]:
            if item == workspace:
                break
            if item.is_symlink() or item.exists() and item.resolve() != item:
                raise ValueError('preview_path_changed')
        if not new and (not target.is_file() or target.stat().st_nlink != 1):
            raise ValueError('preview_path_changed')
        return target

    source = fixed(request['path'])
    output = fixed(request['output'], new=True)
    if output.parent != workspace / 'outputs' or not output.name.startswith('ppt-preview-') or output.suffix != '.png':
        raise ValueError('preview_output_invalid')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if digest(source) != request['source_sha256']:
        raise ValueError('preview_source_changed')
    scale = request.get('scale', 2)
    if type(scale) is not int or not 1 <= scale <= 4:
        raise ValueError('preview_scale_invalid')
    with Image.open(source) as image:
        if image.format != 'PNG' or image.width * image.height > 16_000_000:
            raise ValueError('preview_image_invalid')
        crop = request.get('crop')
        if crop is None:
            crop = {'left': 0, 'top': 0, 'right': image.width, 'bottom': image.height}
        if not isinstance(crop, dict) or set(crop) != {'left', 'top', 'right', 'bottom'}:
            raise ValueError('preview_crop_invalid')
        if any(type(value) is not int for value in crop.values()):
            raise ValueError('preview_crop_invalid')
        left, top, right, bottom = [crop[key] for key in ('left', 'top', 'right', 'bottom')]
        if not 0 <= left < right <= image.width or not 0 <= top < bottom <= image.height:
            raise ValueError('preview_crop_invalid')
        size = ((right - left) * scale, (bottom - top) * scale)
        if size[0] * size[1] > 16_000_000:
            raise ValueError('preview_area_too_large')
        result = image.crop((left, top, right, bottom)).resize(size, getattr(Image, 'Resampling', Image).LANCZOS)
        with output.open('xb') as stream:
            result.save(stream, format='PNG')
    if digest(source) != request['source_sha256']:
        output.unlink()
        raise ValueError('preview_source_changed')
    return {'path': request['output'], 'source_sha256': request['source_sha256'],
            'sha256': digest(output), 'bytes': output.stat().st_size, 'width': size[0], 'height': size[1],
            'crop': crop, 'scale': scale, 'source_modified': False, 'model_requests_inside': 0}


def prepare_asset(request, *, workspace=Path('/work'),scratch=Path('/tmp')):
    """Image-only source preparation; no page edits, Shell, or network access."""
    logical=request['source']
    if not isinstance(logical,str) or '\\' in logical or '..' in logical.split('/'):
        raise ValueError('asset_source_invalid')
    if logical.startswith('/work/'):
        source=workspace/logical[len('/work/'):]
    elif logical.startswith('/tmp/'):
        source=scratch/logical[len('/tmp/'):]
    else:raise ValueError('asset_source_invalid')
    if source.resolve()!=source.absolute() or source.is_symlink() or not source.is_file() or source.stat().st_nlink!=1 or source.stat().st_size>30_000_000:
        raise ValueError('asset_source_changed')
    project=request['project']
    if not isinstance(project,str) or not project.startswith('/work/projects/') or '..' in project.split('/') or '\\' in project:
        raise ValueError('asset_project_invalid')
    folder=workspace/project[len('/work/'):]/'images'
    if folder.resolve()!=folder.absolute() or not folder.is_dir() or folder.is_symlink():raise ValueError('asset_project_changed')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=digest(source)
    with Image.open(source) as picture:
        if picture.format not in ('PNG','JPEG','WEBP') or picture.width*picture.height>32_000_000:raise ValueError('asset_image_invalid')
        image=picture.convert('RGB')
        crop=request.get('crop')
        if crop is not None:
            if not isinstance(crop,dict) or set(crop)!={'left','top','right','bottom'} or any(type(v) is not int for v in crop.values()):raise ValueError('asset_crop_invalid')
            left,top,right,bottom=(crop[k] for k in ('left','top','right','bottom'))
            if not 0<=left<right<=image.width or not 0<=top<bottom<=image.height:raise ValueError('asset_crop_outside_image')
            image=image.crop((left,top,right,bottom))
        width=request.get('width',min(image.width,4096))
        if type(width) is not int or not 1<=width<=4096:raise ValueError('asset_width_invalid')
        height=max(1,round(image.height*width/image.width))
        if width*height>16_000_000:raise ValueError('asset_output_too_large')
        image=image.resize((width,height),getattr(Image,'Resampling',Image).LANCZOS)
        target=folder/('asset-'+request['id']+'.png')
        if not __import__('re').fullmatch('[a-f0-9-]{36}',request['id']):raise ValueError('asset_id_invalid')
        with target.open('xb') as stream:image.save(stream,format='PNG')
    if digest(source)!=original:raise ValueError('asset_source_changed')
    return {'path':project+'/images/'+target.name,'sha256':digest(target),'bytes':target.stat().st_size,
      'source':logical,'source_sha256':original,'width':width,'height':height,'source_modified':False,'model_requests_inside':0}


def source_preview(request, *, workspace=Path('/work')):
    """Render one approved PDF page at a bounded resolution for model inspection."""
    import fitz
    logical = request['path']
    output = request['output']
    if (not logical.startswith('/work/inputs/') or logical != '/work/inputs/' + Path(logical).name
            or not logical.lower().endswith('.pdf') or not output.startswith('/work/outputs/ppt-source-')
            or output != '/work/outputs/' + Path(output).name or not output.endswith('.jpg')):
        raise ValueError('ppt_source_preview_path_invalid')
    source = workspace / 'inputs' / Path(logical).name
    target = workspace / 'outputs' / Path(output).name
    if (source.resolve() != source.absolute() or not source.is_file() or source.stat().st_nlink != 1
            or target.parent.resolve() != target.parent.absolute()):
        raise ValueError('ppt_source_preview_path_changed')
    raw = source.read_bytes()
    version = hashlib.sha256(raw).hexdigest()
    if version != request['source_sha256']:
        raise ValueError('ppt_source_preview_version_changed')
    number = request['page']
    with fitz.open(stream=raw, filetype='pdf') as document:
        if document.needs_pass or type(number) is not int or not 1 <= number <= len(document):
            raise ValueError('ppt_source_preview_page_invalid')
        page = document[number - 1]
        scale = min(2, 1440 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = pix.tobytes('jpeg', jpg_quality=84)
    with target.open('xb') as stream:
        stream.write(image)
    return {'path': output, 'page': number, 'source_sha256': version, 'sha256': hashlib.sha256(image).hexdigest(),
            'bytes': len(image), 'width': pix.width, 'height': pix.height, 'model_requests_inside': 0}


if __name__ == '__main__':
    request=json.loads(base64.b64decode(sys.argv[1]))
    operation=request.get('operation')
    print(json.dumps(prepare_asset(request) if operation=='asset' else source_preview(request) if operation=='source_preview' else preview_region(request)))
