//! Strict bounded LMR2 tile protocol. Geometry is decoded independently of Python.
pub const MAX_BYTES: usize = 128*1024*1024;
pub const MAX_WORK: u64 = 512_000_000;
const MAX_TILE: usize = 2_000_000;
#[derive(Clone, Copy)]
pub struct Shape { pub w: usize, pub h: usize }
#[derive(Clone, Copy)]
pub struct Tile { pub x: usize, pub y: usize, pub w: usize, pub h: usize,
    pub cx: usize, pub cy: usize, pub cw: usize, pub ch: usize }
pub enum Object {
    Full,
    Brush { points: Vec<[f64;2]>, axes: [[f64;2];2] },
    Linear { start: [f64;2], end: [f64;2], cross: [f64;2] },
    Radial { center: [f64;2], axes: [[f64;2];2] },
    Color { color: [f64;3], tolerance: f64, invert: bool },
    Luminance { low: f64, high: f64 },
    Semantic { index: usize },
}
pub struct Entry { pub operation: u8, pub opacity: f64, pub radius: usize, pub kind: Object }
pub struct Request<'a> { pub shape: Shape, pub tile: Tile, pub objects: Vec<Entry>,
    pub bytes: &'a [u8], pub rgb: Option<usize>, pub semantic: Vec<usize> }
struct Reader<'a> { bytes: &'a [u8], offset: usize }
impl<'a> Reader<'a> {
    fn take(&mut self, size: usize) -> Result<&'a [u8], &'static str> {
        let end = self.offset.checked_add(size).ok_or("tile length overflow")?;
        let value = self.bytes.get(self.offset..end).ok_or("truncated local mask tile")?;
        self.offset = end;
        Ok(value)
    }
    fn u8(&mut self) -> Result<u8, &'static str> { Ok(self.take(1)?[0]) }
    fn u32(&mut self) -> Result<usize, &'static str> { Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()) as usize) }
    fn f64(&mut self, low: f64, high: f64) -> Result<f64, &'static str> {
        let value = f64::from_le_bytes(self.take(8)?.try_into().unwrap());
        if !value.is_finite() || value < low || value > high { return Err("invalid local mask numeric parameter"); }
        Ok(value)
    }
    fn point(&mut self) -> Result<[f64;2], &'static str> { Ok([self.f64(0.,1.)?,self.f64(0.,1.)?]) }
    fn vector(&mut self) -> Result<[f64;2], &'static str> { Ok([self.f64(-4.,4.)?,self.f64(-4.,4.)?]) }
    fn basis(&mut self) -> Result<[[f64;2];2], &'static str> {
        let value = [self.vector()?, self.vector()?];
        basis(value)?;
        Ok(value)
    }
}
fn basis(value: [[f64;2];2]) -> Result<(), &'static str> {
    if (value[0][0]*value[1][1]-value[0][1]*value[1][0]).abs() < 1e-12 { Err("degenerate local mask axes") } else { Ok(()) }
}
pub fn decode(bytes: &[u8]) -> Result<Request<'_>, &'static str> {
    if bytes.len() > MAX_BYTES { return Err("local mask packet exceeds budget"); }
    let mut r = Reader { bytes, offset: 0 };
    if r.take(4)? != b"LMR2" { return Err("unsupported local mask wire version"); }
    let shape = Shape { w: r.u32()?, h: r.u32()? };
    if shape.w == 0 || shape.h == 0 || shape.w > 65536 || shape.h > 65536 || shape.w*shape.h > 64_000_000 {
        return Err("local mask source exceeds pixel budget");
    }
    let tile = Tile { x:r.u32()?, y:r.u32()?, w:r.u32()?, h:r.u32()?, cx:r.u32()?, cy:r.u32()?, cw:r.u32()?, ch:r.u32()? };
    if tile.w == 0 || tile.h == 0 || tile.w > shape.w || tile.h > shape.h
        || tile.x > shape.w-tile.w || tile.y > shape.h-tile.h
        || tile.w*tile.h > MAX_TILE || tile.cw == 0 || tile.ch == 0
        || tile.cw > 512 || tile.ch > 512 || tile.cw > tile.w || tile.ch > tile.h
        || tile.cx > tile.w-tile.cw || tile.cy > tile.h-tile.ch { return Err("invalid local mask tile bounds"); }
    let count = r.u32()?;
    let rgb_flag = r.u32()?;
    let channels = r.u32()?;
    if count > 64 || rgb_flag > 1 || channels > 16 { return Err("local mask stack exceeds wire budget"); }
    let mut objects = Vec::with_capacity(count);
    let mut total_points = 0;
    let mut full = false;
    for _ in 0..count {
        let kind = r.u8()?;
        let operation = r.u8()?;
        let opacity = r.f64(0.,1.)?;
        let radius = r.u32()?;
        if operation > 2 || radius > (shape.w.min(shape.h) as f64*0.05).ceil() as usize { return Err("invalid mask operation or feather radius"); }
        // A tile core must have the full required halo unless it touches the source edge.
        let gx = tile.x+tile.cx;
        let gy = tile.y+tile.cy;
        if tile.x > gx.saturating_sub(radius) || tile.y > gy.saturating_sub(radius)
            || tile.x+tile.w < (gx+tile.cw+radius).min(shape.w)
            || tile.y+tile.h < (gy+tile.ch+radius).min(shape.h) { return Err("insufficient local mask feather halo"); }
        let kind = match kind {
            0 => { if full || operation != 0 || opacity != 1. || radius != 0 { return Err("invalid protected full-image mask"); } full = true; Object::Full },
            1 => {
                let n = r.u32()?;
                total_points += n;
                if n == 0 || n > 1024 || total_points > 8192 { return Err("brush exceeds point budget"); }
                let mut points = Vec::with_capacity(n);
                for _ in 0..n { points.push(r.point()?); }
                Object::Brush { points, axes:r.basis()? }
            },
            2 => {
                let start = r.point()?;
                let end = r.point()?;
                let cross = r.vector()?;
                basis([[end[0]-start[0],end[1]-start[1]],cross])?;
                Object::Linear { start,end,cross }
            },
            3 => Object::Radial { center:r.point()?, axes:r.basis()? },
            4 => {
                if rgb_flag != 1 { return Err("missing immutable source RGB"); }
                let color = [r.f64(0.,1.)?,r.f64(0.,1.)?,r.f64(0.,1.)?];
                let tolerance = r.f64(0.,1.)?;
                let invert = match r.u8()? {
                    0 => false,
                    1 => true,
                    _ => return Err("invalid colour range inversion"),
                };
                Object::Color { color,tolerance,invert }
            },
            5 => {
                if rgb_flag != 1 { return Err("missing immutable source RGB"); }
                let low = r.f64(0.,1.)?;
                let high = r.f64(0.,1.)?;
                if low > high { return Err("reversed luminance range"); }
                Object::Luminance {low,high}
            },
            6 => {
                let index = r.u32()?;
                if index >= channels { return Err("missing semantic operand"); }
                Object::Semantic { index }
            },
            _ => return Err("unsupported local mask kind"),
        };
        objects.push(Entry { operation,opacity,radius,kind });
    }
    let area = tile.w*tile.h;
    let rgb = if rgb_flag == 1 { let offset = r.offset; r.take(area*12)?; Some(offset) } else { None };
    let mut semantic = Vec::with_capacity(channels);
    for _ in 0..channels { semantic.push(r.offset); r.take(area*4)?; }
    if r.offset != bytes.len() { return Err("trailing local mask tile data"); }
    Ok(Request { shape,tile,objects,bytes,rgb,semantic })
}
