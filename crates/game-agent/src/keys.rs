//! Key combination parsing and virtual key codes.

pub fn parse_key(name: &str) -> Option<u16> {
    let lower = name.trim().to_lowercase();
    match lower.as_str() {
        "backspace" | "bksp" => Some(0x08),
        "tab" => Some(0x09),
        "enter" | "return" => Some(0x0D),
        "shift" => Some(0x10),
        "ctrl" | "control" => Some(0x11),
        "alt" | "menu" => Some(0x12),
        "pause" => Some(0x13),
        "capslock" => Some(0x14),
        "esc" | "escape" => Some(0x1B),
        "space" => Some(0x20),
        "pageup" | "pgup" => Some(0x21),
        "pagedown" | "pgdn" => Some(0x22),
        "end" => Some(0x23),
        "home" => Some(0x24),
        "left" => Some(0x25),
        "up" => Some(0x26),
        "right" => Some(0x27),
        "down" => Some(0x28),
        "insert" | "ins" => Some(0x2D),
        "delete" | "del" => Some(0x2E),
        "f1" => Some(0x70),
        "f2" => Some(0x71),
        "f3" => Some(0x72),
        "f4" => Some(0x73),
        "f5" => Some(0x74),
        "f6" => Some(0x75),
        "f7" => Some(0x76),
        "f8" => Some(0x77),
        "f9" => Some(0x78),
        "f10" => Some(0x79),
        "f11" => Some(0x7A),
        "f12" => Some(0x7B),
        // single characters
        s if s.len() == 1 => {
            let c = s.chars().next().unwrap();
            match c {
                'a'..='z' => Some((c as u16) - ('a' as u16) + 0x41),
                '0'..='9' => Some((c as u16) - ('0' as u16) + 0x30),
                ' ' => Some(0x20),
                '-' => Some(0xBD),
                '=' => Some(0xBB),
                '[' => Some(0xDB),
                ']' => Some(0xDD),
                '\\' => Some(0xDC),
                ';' => Some(0xBA),
                '\'' => Some(0xDE),
                ',' => Some(0xBC),
                '.' => Some(0xBE),
                '/' => Some(0xBF),
                '`' => Some(0xC0),
                _ => None,
            }
        }
        _ => None,
    }
}

pub fn parse_combo(combo: &str) -> Result<Vec<u16>, String> {
    let mut vks = Vec::new();
    for part in combo.split('+') {
        let trimmed = part.trim();
        if trimmed.is_empty() {
            continue;
        }
        match parse_key(trimmed) {
            Some(vk) => vks.push(vk),
            None => return Err(format!("Unknown key in combo: {:?}", trimmed)),
        }
    }
    if vks.is_empty() {
        return Err("Empty key combo".into());
    }
    Ok(vks)
}
