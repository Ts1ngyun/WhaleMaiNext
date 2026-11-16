"""Decode image bytes only; never fetch URLs or open model-provided paths."""
import base64
import hashlib
import io
from PIL import Image

def save(segment, directory):
    encoded=segment.get('binary_data_base64','')
    if not isinstance(encoded,str) or not encoded or len(encoded)>12*1024*1024:
        raise ValueError('表情包缺少图片数据或超过 8 MiB')
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)>8*1024*1024:raise ValueError('表情包超过 8 MiB')
    with Image.open(io.BytesIO(raw)) as image:
        ext={'PNG':'.png','JPEG':'.jpg','GIF':'.gif','WEBP':'.webp'}.get(image.format)
        if not ext or image.width*image.height>16000000:raise ValueError('不支持的表情包格式或尺寸')
        image.verify()
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(hashlib.sha256(raw).hexdigest()+ext)
    if not target.exists():target.write_bytes(raw)
    return str(target.resolve())
