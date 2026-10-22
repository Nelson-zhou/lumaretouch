"""Inverse the existing crop/rotate/fixed-proxy projection for repair selections."""
import math
from .ops import geometry as G
from .ops.source_patch import check_recipe, VERSION


def inverse_recipe(spec, polygon, offset):
    raw=check_recipe({'version':VERSION,'polygon':polygon,'offset':offset})
    if G.is_identity(spec.rect,spec.rotation):
        return raw
    xa,ya,xb,yb=spec.integer_crop
    cw,ch=xb-xa,yb-ya;rw,rh=spec.rotated
    k=G._snapped_quarter_turn(spec.rotation)
    ca,sa=math.cos(math.radians(-spec.rotation)),math.sin(math.radians(-spec.rotation))
    def inverse(point):
        # UI coordinates are image-edge fractions; pixel centers are (i+.5)/N.
        # Undo align_corners=False resize in that same convention.
        rx=point[0]*rw-.5
        ry=point[1]*rh-.5
        if k==0: x,y=rx,ry
        elif k==1: x,y=ry,ch-1-rx
        elif k==2: x,y=cw-1-rx,ch-1-ry
        elif k==3: x,y=cw-1-ry,rx
        else:
            dx,dy=rx-(rw-1)/2,ry-(rh-1)/2
            x,y=ca*dx-sa*dy+(cw-1)/2,sa*dx+ca*dy+(ch-1)/2
        # Never clamp a black rotation corner to a different source pixel.
        if not -.5<=x<=cw-.5 or not -.5<=y<=ch-.5:
            raise ValueError('Patch selection/source crosses the cropped image boundary')
        return [(x+xa+.5)/spec.width,(y+ya+.5)/spec.height]
    target=[inverse(p) for p in raw['polygon']]
    donor=[inverse([p[0]+raw['offset'][0],p[1]+raw['offset'][1]]) for p in raw['polygon']]
    delta=[donor[0][i]-target[0][i] for i in (0,1)]
    if any(abs((s[i]-t[i])-delta[i])>1e-10 for s,t in zip(donor,target) for i in (0,1)):
        raise ValueError('Patch source transform is not a translation')
    return check_recipe({'version':VERSION,'polygon':target,'offset':delta})
