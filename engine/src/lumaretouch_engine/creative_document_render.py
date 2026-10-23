"""Full-source, bounded-tile creative compositor. Native Rust only, no placeholders.

One-pixel bilinear source halos are naturally read from immutable full assets.
Group tiles use isolated composition; masks are source-local coverage. Canvas
resize changes the output domain without cropping the retained source pixels.
"""
from copy import deepcopy
from . import creative_document_state as S
from .creative_document_assets import make_asset

DEFAULT_RENDER_BYTES = 512_000_000
TILE_EDGE = 256


class CreativeRenderer:
    def __init__(self, document, assets, *, max_bytes=DEFAULT_RENDER_BYTES, cancelled=lambda:False):
        S.validate(document,assets)
        if type(max_bytes) is not int or not 1_048_576 <= max_bytes <= 4_000_000_000:
            raise ValueError('Invalid creative render memory budget')
        self.document = deepcopy(document)
        self.assets = assets
        self.max_bytes = max_bytes
        self.cancelled = cancelled
        self.frozen = {}
        self._frozen_bytes = 0
        self._output_reserve = 0
        # At each nesting level: backdrop/output/native staging/immutable group.
        by_id = {x['id']:x for x in self.document['layers']}
        depth = 1
        for layer in self.document['layers']:
            count = 1; parent = layer['parent_id']
            while parent is not None:
                count += 1; parent = by_id[parent]['parent_id']
            depth = max(depth,count)
        self._tile_reserve = (depth + 2) * TILE_EDGE * TILE_EDGE * 16 * 5
        if self._tile_reserve > self.max_bytes:
            raise ValueError('Creative render budget cannot cover bounded nested group tiles')
        self.children = {}
        for layer in self.document['layers']:
            self.children.setdefault(layer['parent_id'],[]).append(layer)

    def _check(self):
        if self.cancelled(): raise InterruptedError('Creative document render cancelled')

    def _source(self, identity, kind):
        self._check()
        if identity in self.frozen: return self.frozen[identity]
        import numpy as np
        from . import creative_layer_native as N
        asset = self.assets.get(identity,kind)
        size = len(asset['content'])
        # Reserve 2× input for endian conversion/ownership copies, even when an
        # immutable little-endian view can use the bridge's zero-copy path.
        needed = self._frozen_bytes + 2*size + self._tile_reserve + self._output_reserve
        if needed > self.max_bytes:
            raise ValueError('Creative full-source render exceeds memory budget')
        shape = (asset['height'],asset['width'],4) if kind == 'rgba' else (asset['height'],asset['width'])
        pixels = np.frombuffer(asset['content'],dtype='<f4').reshape(shape)
        if not pixels.dtype.isnative: pixels = pixels.astype(np.float32)
        frozen = N.freeze_rgba(pixels,cancelled=self.cancelled) if kind == 'rgba' else N.freeze_mask(pixels,cancelled=self.cancelled)
        self.frozen[identity] = frozen; self._frozen_bytes += size
        return frozen

    def _group_mask(self, identity, x, y, width, height):
        import numpy as np
        from . import creative_layer_native as N
        asset = self.assets.get(identity,'mask')
        # Crop canvas-space mask directly from immutable storage, zero outside.
        source = np.frombuffer(asset['content'],dtype='<f4').reshape(asset['height'],asset['width'])
        out = np.zeros((height,width),dtype=np.float32)
        right,bottom = min(x+width,asset['width']),min(y+height,asset['height'])
        if right > x and bottom > y: out[:bottom-y,:right-x] = source[y:bottom,x:right]
        return N.freeze_mask(out,cancelled=self.cancelled)

    def _compose(self, parent_id, x, y, width, height):
        import numpy as np
        from . import creative_layer_native as N
        backdrop = np.zeros((height,width,4),dtype=np.float32)
        for layer in self.children.get(parent_id,[]):
            self._check()
            if not layer['visible'] or layer['opacity'] == 0: continue
            if layer['kind'] == 'group':
                group = self._compose(layer['id'],x,y,width,height)
                source = N.freeze_rgba(group,cancelled=self.cancelled)
                inverse = (1.0,0.0,-float(x),0.0,1.0,-float(y))
                mask = self._group_mask(layer['mask_id'],x,y,width,height) if layer['mask_id'] else None
            else:
                source = self._source(layer['asset_id'],'rgba')
                inverse = S.inverse(layer['transform'],source.width,source.height)
                mask = self._source(layer['mask_id'],'mask') if layer['mask_id'] else None
            backdrop = N.composite_tile(backdrop,source,inverse_affine=inverse,
                         canvas_origin=(x,y),opacity=layer['opacity'],blend_mode=layer['blend'],
                         mask=mask,cancelled=self.cancelled)
        return backdrop

    def tiles(self):
        """Yield (x,y,RGBA-f32 tile). Consumer must release tiles, not collect them."""
        canvas = self.document['canvas']
        for y in range(0,canvas['height'],TILE_EDGE):
            for x in range(0,canvas['width'],TILE_EDGE):
                self._check()
                yield x,y,self._compose(None,x,y,min(TILE_EDGE,canvas['width']-x),min(TILE_EDGE,canvas['height']-y))

    def render_asset(self):
        """Concrete full-canvas result for return; no generation provenance.

        The tile iterator is a future streaming-writer port, not an exposed
        streaming export feature. In-memory return above budget fails early.
        """
        import numpy as np
        canvas = self.document['canvas']; w,h = canvas['width'],canvas['height']
        self._output_reserve = w*h*16*3  # array, immutable bytes and bounded validation overlap
        if self._output_reserve + self._tile_reserve + self._frozen_bytes > self.max_bytes:
            raise ValueError('Creative return output exceeds available memory budget')
        try:
            output = np.empty((h,w,4),dtype='<f4')
            for x,y,tile in self.tiles(): output[y:y+tile.shape[0],x:x+tile.shape[1]] = tile
            self._check()
            return make_asset('rgba',w,h,output.tobytes(order='C'))
        finally:
            self._output_reserve = 0

    def preview_png(self, *, max_pixels=1_048_576):
        """Display-only nearest sampling of actual full-resolution rendered tiles.

        Source pixels and recipe are never downsampled. Preview sampling is an
        explicit display policy, not an export/return quality or speed claim.
        """
        import numpy as np
        from io import BytesIO
        from PIL import Image
        from .creative_layer_native import display_rgba
        if type(max_pixels) is not int or not 1 <= max_pixels <= 4_194_304:
            raise ValueError('Invalid creative display pixel budget')
        c = self.document['canvas']; factor = min(1.0,(max_pixels/(c['width']*c['height']))**.5)
        width,height = max(1,int(c['width']*factor)),max(1,int(c['height']*factor))
        self._output_reserve = width*height*64
        if self._output_reserve+self._tile_reserve+self._frozen_bytes > self.max_bytes:
            raise ValueError('Creative display exceeds memory budget')
        try:
            xs = np.minimum(c['width']-1,((np.arange(width)+.5)*c['width']/width).astype(np.int64))
            ys = np.minimum(c['height']-1,((np.arange(height)+.5)*c['height']/height).astype(np.int64))
            sampled = np.empty((height,width,4),dtype=np.float32)
            for x,y,tile in self.tiles():
                ix = np.flatnonzero((xs>=x)&(xs<x+tile.shape[1])); iy = np.flatnonzero((ys>=y)&(ys<y+tile.shape[0]))
                if len(ix) and len(iy): sampled[np.ix_(iy,ix)] = tile[np.ix_(ys[iy]-y,xs[ix]-x)]
            alpha = sampled[:,:,3].copy()
            np.divide(sampled[:,:,:3],alpha[:,:,None],out=sampled[:,:,:3],where=alpha[:,:,None]>0)
            sampled[:,:,3] = 1
            rgb = display_rgba(sampled,matte=(0.0,0.0,0.0),cancelled=self.cancelled)
            rgba = np.empty((height,width,4),dtype=np.uint8); rgba[:,:,:3] = rgb
            rgba[:,:,3] = np.rint(alpha*255).astype(np.uint8)
            buffer = BytesIO(); Image.fromarray(rgba,'RGBA').save(buffer,format='PNG')
            self._check()
            return buffer.getvalue(),width,height
        finally:
            self._output_reserve = 0
