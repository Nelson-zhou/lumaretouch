//! Persistent bounded binary worker: one frame per tile, no whole-image RGB copy.
mod raster;
mod wire;
use std::io::{self, Read, Write};
fn run() -> Result<(), String> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    let mut frames = 0usize;
    let mut pixels = 0usize;
    let mut work = 0u64;
    loop {
        let mut size = [0u8;4];
        match input.read(&mut size[..1]) {
            Ok(0) => break,
            Ok(_) => (),
            Err(e) => return Err(e.to_string()),
        }
        input.read_exact(&mut size[1..]).map_err(|e|e.to_string())?;
        let size = u32::from_le_bytes(size) as usize;
        frames += 1;
        if size > wire::MAX_BYTES || frames > 4096 { return Err("local mask transport budget exceeded".into()); }
        let mut bytes = vec![0u8;size];
        input.read_exact(&mut bytes).map_err(|e|e.to_string())?;
        let request = wire::decode(&bytes).map_err(str::to_owned)?;
        pixels += request.tile.cw*request.tile.ch;
        if pixels > 64_000_000 { return Err("local mask output budget exceeded".into()); }
        let result = raster::render(&request,&mut work).map_err(str::to_owned)?;
        output.write_all(&(result.len() as u32).to_le_bytes()).map_err(|e|e.to_string())?;
        output.write_all(&result).map_err(|e|e.to_string())?;
        output.flush().map_err(|e|e.to_string())?;
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() { eprintln!("{error}"); std::process::exit(2); }
}
