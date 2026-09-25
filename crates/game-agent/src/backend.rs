//! Windows backend for screen capture, input simulation, and window management.

#[cfg(windows)]
pub mod win {
    use std::sync::atomic::{AtomicI32, Ordering};
    use windows::Win32::Foundation::{BOOL, HWND, LPARAM, RECT};
    use windows::Win32::Graphics::Gdi::{
        BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject, GetDC,
        GetDIBits, GetDeviceCaps, ReleaseDC, SelectObject, SetBrushOrgEx, SetStretchBltMode,
        StretchBlt, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, HALFTONE, HORZRES,
        SRCCOPY, VERTRES,
    };
    use windows::Win32::System::Power::{
        SetThreadExecutionState, ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED,
    };
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        MapVirtualKeyW, SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, INPUT_MOUSE, KEYBDINPUT,
        KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_UNICODE,
        MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEEVENTF_MIDDLEDOWN,
        MOUSEEVENTF_MIDDLEUP, MOUSEEVENTF_MOVE, MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP,
        MOUSEEVENTF_WHEEL, MOUSEINPUT, VIRTUAL_KEY,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        BringWindowToTop, EnumWindows, GetDesktopWindow, GetForegroundWindow, GetWindowRect,
        GetWindowTextLengthW, GetWindowTextW, IsIconic, IsWindowVisible, SetCursorPos,
        SetForegroundWindow, ShowWindow, SW_RESTORE,
    };

    pub fn keep_awake() {
        unsafe {
            let _ = SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
        }
    }

    pub fn screen_size() -> (i32, i32) {
        unsafe {
            let dc = GetDC(None);
            let w = GetDeviceCaps(dc, HORZRES);
            let h = GetDeviceCaps(dc, VERTRES);
            ReleaseDC(None, dc);
            (w, h)
        }
    }

    pub fn capture_rgb(
        x: i32,
        y: i32,
        w: i32,
        h: i32,
        tw: i32,
        th: i32,
    ) -> Result<Vec<u8>, String> {
        unsafe {
            let screen_dc = GetDC(None);
            if screen_dc.is_invalid() {
                return Err("Failed to get screen DC".into());
            }

            let mem_dc = CreateCompatibleDC(screen_dc);
            if mem_dc.is_invalid() {
                ReleaseDC(None, screen_dc);
                return Err("Failed to create memory DC".into());
            }

            let bmp = CreateCompatibleBitmap(screen_dc, tw, th);
            if bmp.is_invalid() {
                let _ = DeleteDC(mem_dc);
                ReleaseDC(None, screen_dc);
                return Err("Failed to create compatible bitmap".into());
            }

            let old_obj = SelectObject(mem_dc, bmp);

            if tw == w && th == h {
                if BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY).is_err() {
                    let _ = SelectObject(mem_dc, old_obj);
                    let _ = DeleteObject(bmp);
                    let _ = DeleteDC(mem_dc);
                    ReleaseDC(None, screen_dc);
                    return Err("BitBlt failed".into());
                }
            } else {
                SetStretchBltMode(mem_dc, HALFTONE);
                let _ = SetBrushOrgEx(mem_dc, 0, 0, None);
                if !StretchBlt(mem_dc, 0, 0, tw, th, screen_dc, x, y, w, h, SRCCOPY).as_bool() {
                    let _ = SelectObject(mem_dc, old_obj);
                    let _ = DeleteObject(bmp);
                    let _ = DeleteDC(mem_dc);
                    ReleaseDC(None, screen_dc);
                    return Err("StretchBlt failed".into());
                }
            }

            let _ = SelectObject(mem_dc, old_obj);

            let mut bmi = BITMAPINFO {
                bmiHeader: BITMAPINFOHEADER {
                    biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                    biWidth: tw,
                    biHeight: -th, // Negative for top-down DIB
                    biPlanes: 1,
                    biBitCount: 32,
                    biCompression: BI_RGB.0,
                    ..Default::default()
                },
                ..Default::default()
            };

            let pixel_count = (tw * th) as usize;
            let mut bgra_buf: Vec<u8> = vec![0u8; pixel_count * 4];

            let lines = GetDIBits(
                mem_dc,
                bmp,
                0,
                th as u32,
                Some(bgra_buf.as_mut_ptr() as *mut _),
                &mut bmi,
                DIB_RGB_COLORS,
            );

            let _ = DeleteObject(bmp);
            let _ = DeleteDC(mem_dc);
            ReleaseDC(None, screen_dc);

            if lines != th {
                return Err("GetDIBits failed to read scanlines".into());
            }

            // High-speed BGRA -> RGB conversion
            let mut rgb_buf = Vec::with_capacity(pixel_count * 3);
            for chunk in bgra_buf.chunks_exact(4) {
                rgb_buf.push(chunk[2]); // R
                rgb_buf.push(chunk[1]); // G
                rgb_buf.push(chunk[0]); // B
            }

            Ok(rgb_buf)
        }
    }

    pub fn mouse_move(x: i32, y: i32) {
        let (w, h) = screen_size();
        let nx = ((x as f64 * 65535.0) / ((w - 1).max(1) as f64)).round() as i32;
        let ny = ((y as f64 * 65535.0) / ((h - 1).max(1) as f64)).round() as i32;

        unsafe {
            let input = INPUT {
                r#type: INPUT_MOUSE,
                Anonymous: INPUT_0 {
                    mi: MOUSEINPUT {
                        dx: nx,
                        dy: ny,
                        mouseData: 0,
                        dwFlags: MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
            let _ = SetCursorPos(x, y);
        }
    }

    pub fn mouse_button(button: &str, down: bool) -> Result<(), String> {
        let flag = match (button, down) {
            ("left", true) => MOUSEEVENTF_LEFTDOWN,
            ("left", false) => MOUSEEVENTF_LEFTUP,
            ("right", true) => MOUSEEVENTF_RIGHTDOWN,
            ("right", false) => MOUSEEVENTF_RIGHTUP,
            ("middle", true) => MOUSEEVENTF_MIDDLEDOWN,
            ("middle", false) => MOUSEEVENTF_MIDDLEUP,
            _ => return Err(format!("Unknown button: {}", button)),
        };

        unsafe {
            let input = INPUT {
                r#type: INPUT_MOUSE,
                Anonymous: INPUT_0 {
                    mi: MOUSEINPUT {
                        dx: 0,
                        dy: 0,
                        mouseData: 0,
                        dwFlags: flag,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
        }
        Ok(())
    }

    pub fn mouse_scroll(clicks: i32) {
        unsafe {
            let input = INPUT {
                r#type: INPUT_MOUSE,
                Anonymous: INPUT_0 {
                    mi: MOUSEINPUT {
                        dx: 0,
                        dy: 0,
                        mouseData: (clicks * 120) as u32,
                        dwFlags: MOUSEEVENTF_WHEEL,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
        }
    }

    pub fn send_key(vk: u16, down: bool) {
        unsafe {
            let scan = MapVirtualKeyW(
                vk as u32,
                windows::Win32::UI::Input::KeyboardAndMouse::MAP_VIRTUAL_KEY_TYPE(0),
            ) as u16;
            let mut flags = if scan != 0 { KEYEVENTF_SCANCODE.0 } else { 0 };
            if !down {
                flags |= KEYEVENTF_KEYUP.0;
            }
            // Check extended keys
            if [0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E].contains(&vk) {
                flags |= KEYEVENTF_EXTENDEDKEY.0;
            }

            let input = INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: INPUT_0 {
                    ki: KEYBDINPUT {
                        wVk: VIRTUAL_KEY(vk),
                        wScan: scan,
                        dwFlags: windows::Win32::UI::Input::KeyboardAndMouse::KEYBD_EVENT_FLAGS(flags),
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };
            SendInput(&[input], std::mem::size_of::<INPUT>() as i32);
        }
    }

    pub fn type_text(text: &str) {
        for ch in text.encode_utf16() {
            unsafe {
                let down = INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(0),
                            wScan: ch,
                            dwFlags: KEYEVENTF_UNICODE,
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                };
                let up = INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(0),
                            wScan: ch,
                            dwFlags: KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                };
                SendInput(&[down, up], std::mem::size_of::<INPUT>() as i32);
            }
            std::thread::sleep(std::time::Duration::from_millis(5));
        }
    }

    pub fn list_windows() -> Vec<serde_json::Value> {
        let mut list = Vec::new();
        unsafe {
            let fg = GetForegroundWindow();
            let list_ptr = &mut list as *mut Vec<serde_json::Value>;

            unsafe extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
                if IsWindowVisible(hwnd).as_bool() {
                    let len = GetWindowTextLengthW(hwnd);
                    if len > 0 {
                        let mut buf = vec![0u16; (len + 1) as usize];
                        GetWindowTextW(hwnd, &mut buf);
                        let title = String::from_utf16_lossy(&buf[..len as usize]);
                        let mut r = RECT::default();
                        let _ = GetWindowRect(hwnd, &mut r);
                        let fg = GetForegroundWindow();

                        let item = serde_json::json!({
                            "title": title,
                            "foreground": hwnd == fg,
                            "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top],
                        });

                        let list_ref = &mut *(lparam.0 as *mut Vec<serde_json::Value>);
                        list_ref.push(item);
                    }
                }
                BOOL(1)
            }

            let _ = EnumWindows(Some(enum_proc), LPARAM(list_ptr as isize));
        }
        list
    }

    pub fn foreground_title() -> String {
        unsafe {
            let hwnd = GetForegroundWindow();
            let len = GetWindowTextLengthW(hwnd);
            if len == 0 {
                return String::new();
            }
            let mut buf = vec![0u16; (len + 1) as usize];
            GetWindowTextW(hwnd, &mut buf);
            String::from_utf16_lossy(&buf[..len as usize])
        }
    }

    pub fn focus_window(title_substring: &str) -> Result<String, String> {
        let needle = title_substring.to_lowercase();
        unsafe {
            let fg = GetForegroundWindow();
            static TARGET_HWND: AtomicI32 = AtomicI32::new(0);
            TARGET_HWND.store(0, Ordering::SeqCst);
            let mut matched_title = String::new();
            let matched_title_ptr = &mut matched_title as *mut String;

            unsafe extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
                if IsWindowVisible(hwnd).as_bool() {
                    let len = GetWindowTextLengthW(hwnd);
                    if len > 0 {
                        let mut buf = vec![0u16; (len + 1) as usize];
                        GetWindowTextW(hwnd, &mut buf);
                        let title = String::from_utf16_lossy(&buf[..len as usize]);

                        let (needle_str, title_out) = &*(lparam.0 as *const (String, *mut String));
                        if title.to_lowercase().contains(needle_str) {
                            TARGET_HWND.store(hwnd.0 as isize as i32, Ordering::SeqCst);
                            unsafe {
                                **title_out = title;
                            }
                            return BOOL(0); // Stop enum
                        }
                    }
                }
                BOOL(1)
            }

            let ctx = (needle, matched_title_ptr);
            let _ = EnumWindows(Some(enum_proc), LPARAM(&ctx as *const _ as isize));

            let hwnd_val = TARGET_HWND.load(Ordering::SeqCst);
            if hwnd_val == 0 {
                return Err(format!("No visible window title contains {:?}", title_substring));
            }

            let target = HWND(hwnd_val as isize as *mut _);
            if IsIconic(target).as_bool() {
                let _ = ShowWindow(target, SW_RESTORE);
            }

            // Tap ALT to lift foreground-lock
            send_key(0x12, true);
            send_key(0x12, false);

            let _ = BringWindowToTop(target);
            let _ = SetForegroundWindow(target);
            Ok(matched_title)
        }
    }
}
