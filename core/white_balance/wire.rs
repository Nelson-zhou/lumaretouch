//! Bounded scalar request adapter for the existing packaged math helper.
use super::white_balance;

pub fn handle(tokens: &mut std::str::SplitWhitespace<'_>) -> Result<String, String> {
    let action = tokens.next().ok_or("missing WB action")?;
    let count = match action { "manual" => 3, "neutral" => 6, _ => return Err("unknown WB action".into()) };
    let mut values = [0.0; 6];
    for value in &mut values[..count] {
        *value = tokens.next().ok_or("missing WB scalar")?.parse::<f64>().map_err(|_| "invalid WB scalar")?;
        if !value.is_finite() { return Err("nonfinite WB scalar".into()); }
    }
    if tokens.next().is_some() { return Err("unexpected trailing WB input".into()); }
    let gains = match action {
        "manual" => white_balance::manual_gains(values[0], values[1], values[2]),
        _ => white_balance::neutral_gains([values[0], values[1], values[2]], [values[3], values[4], values[5]]),
    }.map_err(|e| format!("WB scalar rejected: {e:?}"))?;
    Ok(format!("{{\"version\":1,\"action\":\"{}\",\"gains\":[{:e},{:e},{:e}]}}", action, gains[0], gains[1], gains[2]))
}
