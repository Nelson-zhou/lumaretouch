# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only source support overlay. It is never a deformation input."""
import math
import numpy as np
from .hand_tone_review import display_image
from . import hand_shape_state as S


def overlay(rgb,review,source):
    from PIL import Image,ImageDraw
    from .neck_wrinkle_review import display_rgb,encode_rgb
    # Match the before/after 768px transport ceiling; no source geometry is resized.
    pixels=display_rgb(rgb);h,w=pixels.shape[:2];sw,sh=source['width']-1,source['height']-1
    with Image.fromarray(pixels,'RGB') as picture:
        draw=ImageDraw.Draw(picture)
        for region in review['regions']:
            cx,cy,ux,uy,a,b=S.region_geometry(region,source);nx,ny=-uy,ux
            path=[((cx+a*math.cos(t)*ux+b*math.sin(t)*nx)/sw*(w-1),(cy+a*math.cos(t)*uy+b*math.sin(t)*ny)/sh*(h-1)) for t in (i*2*math.pi/96 for i in range(97))]
            draw.line(path,fill=(40,255,130),width=2)
            for name in ('start','end','negative','positive'):
                x,y=region[name][0]*(w-1),region[name][1]*(h-1);draw.ellipse((x-3,y-3,x+3,y+3),fill=(255,220,0))
        for x0,y0,x1,y1 in review['protect']:
            draw.rectangle((x0*(w-1),y0*(h-1),x1*(w-1),y1*(h-1)),outline=(255,30,180),width=3)
        result=display_image(np.asarray(picture).copy())
    return result
