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
        "win" | "lwin" | "super" => Some(0x5B),
        "rwin" => Some(0x5C),
        "apps" | "contextmenu" => Some(0x5D),
        "printscreen" | "prtsc" => Some(0x2C),
        "numlock" => Some(0x90),
        "scrolllock" => Some(0x91),
        "multiply" | "num*" => Some(0x6A),
        "add" | "num+" | "numplus" => Some(0x6B),
        "subtract" | "num-" | "numminus" => Some(0x6D),
        "decimal" | "num." => Some(0x6E),
        "divide" | "num/" => Some(0x6F),
        // the main-keyboard =/+ key (VK_OEM_PLUS); "+" alone is handled by parse_combo
        "plus" => Some(0xBB),
        "minus" => Some(0xBD),
        // num0..num9 (also numpad0..numpad9, the old Python agent's names)
        s if s.strip_prefix("numpad").or_else(|| s.strip_prefix("num")).is_some_and(|d| d.len() == 1 && d.as_bytes()[0].is_ascii_digit()) => {
            Some(0x60 + (s.as_bytes()[s.len() - 1] - b'0') as u16)
        }
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
    // "+" is the separator, so a literal plus key is "+" alone or a trailing "++" ("shift++")
    if combo.trim() == "+" {
        return Ok(vec![0xBB]);
    }
    let mut vks = Vec::new();
    let (combo, trailing_plus) = match combo.trim().strip_suffix("++") {
        Some(rest) => (rest, true),
        None => (combo, false),
    };
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
    if trailing_plus {
        vks.push(0xBB);
    }
    if vks.is_empty() {
        return Err("Empty key combo".into());
    }
    Ok(vks)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn named_keys_and_characters() {
        assert_eq!(parse_key("Esc"), Some(0x1B));
        assert_eq!(parse_key("a"), Some(0x41));
        assert_eq!(parse_key("9"), Some(0x39));
        assert_eq!(parse_key("`"), Some(0xC0));
        assert_eq!(parse_key("="), Some(0xBB));
        assert_eq!(parse_key("nosuchkey"), None);
    }

    #[test]
    fn windows_numpad_and_plus_keys() {
        assert_eq!(parse_key("win"), Some(0x5B));
        assert_eq!(parse_key("num0"), Some(0x60));
        assert_eq!(parse_key("num9"), Some(0x69));
        assert_eq!(parse_key("numpad7"), Some(0x67));
        assert_eq!(parse_key("num10"), None);
        assert_eq!(parse_key("num+"), Some(0x6B));
        assert_eq!(parse_key("num-"), Some(0x6D));
        assert_eq!(parse_key("plus"), Some(0xBB));
        assert_eq!(parse_combo("win+r").unwrap(), vec![0x5B, 0x52]);
        assert_eq!(parse_combo("+").unwrap(), vec![0xBB]);
        assert_eq!(parse_combo("shift++").unwrap(), vec![0x10, 0xBB]);
        assert_eq!(parse_combo("ctrl+num+").unwrap_err(), "Unknown key in combo: \"num\"");
    }

    #[test]
    fn combos_reject_unknown_and_empty() {
        assert_eq!(parse_combo("shift+alt+c").unwrap(), vec![0x10, 0x12, 0x43]);
        assert!(parse_combo("ctrl+bogus").is_err());
        assert!(parse_combo("").is_err());
    }
}
