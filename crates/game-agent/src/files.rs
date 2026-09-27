//! Read-only access to a few named directories (e.g. a game's saves and logs).
//!
//! Roots come from `roots.json` next to the executable, written by the installer:
//! `{"roots": {"stellaris_docs": "C:\\Users\\me\\Documents\\Paradox Interactive\\Stellaris"}}`.
//! Requests name a root and a relative path; anything that resolves outside its root, absolute
//! paths and `..` components are refused. There is no delete or execute operation.
//!
//! Writing is possible only under `write_roots`, and only to the paths each one allows
//! (`"dir/"` = anything under that folder, otherwise one exact file), e.g. a game's mod folder:
//! `{"write_roots": {"stellaris_mods": {"path": "…\\Stellaris", "allow": ["mod/governor_bridge/",
//! "mod/governor_bridge.mod", "dlc_load.json"]}}}`.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};
use std::time::UNIX_EPOCH;

/// Largest single read (bytes). Stellaris saves are typically a few MB; late-game ones tens of MB.
pub const MAX_READ: u64 = 128 * 1024 * 1024;
/// Largest single write (bytes): mod scripts and small config files.
pub const MAX_WRITE: usize = 4 * 1024 * 1024;

#[derive(Debug, Default, Clone, Deserialize)]
pub struct WriteRoot {
    pub path: PathBuf,
    /// Relative paths that may be written: "dir/" allows anything under dir, otherwise an exact file.
    #[serde(default)]
    pub allow: Vec<String>,
}

#[derive(Debug, Default, Clone, Deserialize)]
pub struct Roots {
    #[serde(default)]
    pub roots: BTreeMap<String, PathBuf>,
    #[serde(default)]
    pub write_roots: BTreeMap<String, WriteRoot>,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct Entry {
    pub name: String,
    pub is_dir: bool,
    pub size: u64,
    /// Seconds since the Unix epoch.
    pub modified: u64,
}

/// Windows device names: opening one (with any extension, e.g. `nul.txt`) reaches the device,
/// not a file in the folder.
const DEVICE_NAMES: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "COM\u{b9}", "COM\u{b2}", "COM\u{b3}", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8",
    "LPT9", "LPT\u{b9}", "LPT\u{b2}", "LPT\u{b3}",
];

/// Check a request's relative path by name, on every OS (so tests on Linux cover the Windows
/// rules): no drive, stream (`:`), UNC or `\\?\` syntax, no `..`, no Windows device name, and no
/// name ending in a dot or a space (Windows strips those, so `x.` would name `x`).
pub fn check_rel(rel: &str) -> Result<(), String> {
    if rel.contains(':') {
        return Err(format!("{rel:?}: drive or stream syntax (':') is not allowed"));
    }
    if rel.starts_with(['/', '\\']) || rel.contains("//") || rel.contains("\\\\") {
        return Err(format!("{rel:?}: absolute, UNC and device paths are not allowed"));
    }
    for seg in rel.split(['/', '\\']) {
        if seg.is_empty() || seg == "." {
            continue;
        }
        if seg == ".." {
            return Err(format!("path {rel:?} must be relative and must not contain '..'"));
        }
        if seg.ends_with(['.', ' ']) {
            return Err(format!("{rel:?}: a name must not end in a dot or a space"));
        }
        let stem = seg.split('.').next().unwrap_or(seg).trim_end_matches(' ');
        if DEVICE_NAMES.iter().any(|d| d.to_uppercase() == stem.to_uppercase()) {
            return Err(format!("{rel:?}: {stem:?} is a Windows device name"));
        }
    }
    Ok(())
}

impl Roots {
    /// Load roots; a missing file means no roots. A BOM (Windows PowerShell 5.1 writes one) is
    /// accepted; an unparsable file is reported on stderr and yields no roots.
    pub fn load(path: &Path) -> Roots {
        let Ok(text) = std::fs::read_to_string(path) else {
            return Roots::default();
        };
        match serde_json::from_str(text.trim_start_matches('\u{feff}')) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("ignoring {path:?}: {e}");
                Roots::default()
            }
        }
    }

    /// Resolve `rel` inside root `name`, refusing anything that could escape it.
    pub fn resolve(&self, name: &str, rel: &str) -> Result<PathBuf, String> {
        let root = self.roots.get(name).ok_or_else(|| format!("unknown root {name:?}"))?;
        check_rel(rel)?;
        let rel_path = Path::new(rel);
        for c in rel_path.components() {
            match c {
                Component::Normal(_) | Component::CurDir => {}
                _ => return Err(format!("path {rel:?} must be relative and must not contain '..'")),
            }
        }
        let root_c = root.canonicalize().map_err(|e| format!("root {name:?} unavailable: {e}"))?;
        let full = root_c.join(rel_path);
        let full_c = full.canonicalize().map_err(|e| format!("{rel:?}: {e}"))?;
        if !full_c.starts_with(&root_c) {
            return Err(format!("{rel:?} resolves outside root {name:?}"));
        }
        Ok(full_c)
    }

    /// Write `data` to `rel` inside write root `name` (atomically: temp file + rename). Returns bytes written.
    ///
    /// The path is checked by name and against the allowlist first. Then each missing directory is
    /// created one level at a time, after checking that the level above is a real directory (not a
    /// link or junction), so no directory is ever created outside the root.
    pub fn write(&self, name: &str, rel: &str, data: &[u8]) -> Result<usize, String> {
        let wr = self.write_roots.get(name).ok_or_else(|| format!("{name:?} is not a writable root"))?;
        if data.len() > MAX_WRITE {
            return Err(format!("too large: {} bytes (max {MAX_WRITE})", data.len()));
        }
        check_rel(rel)?;
        let rel_path = Path::new(rel);
        let mut parts = Vec::new();
        for c in rel_path.components() {
            match c {
                Component::Normal(p) => parts.push(p.to_string_lossy().into_owned()),
                _ => return Err(format!("path {rel:?} must be relative and must not contain '..'")),
            }
        }
        if parts.is_empty() {
            return Err("an empty path is not allowed".into());
        }
        let norm = parts.join("/");
        let allowed = wr.allow.iter().any(|a| {
            if let Some(dir) = a.strip_suffix('/') {
                norm.starts_with(&format!("{dir}/"))
            } else {
                norm == *a
            }
        });
        if !allowed {
            return Err(format!("{norm:?} is not writable (allowed: {})", wr.allow.join(", ")));
        }
        let root_c = wr.path.canonicalize().map_err(|e| format!("root {name:?} unavailable: {e}"))?;
        let (file_name, dirs) = parts.split_last().ok_or("no file name")?;
        let mut parent = root_c.clone();
        for d in dirs {
            parent.push(d);
            if std::fs::symlink_metadata(&parent).is_err() {
                // One level only (never create_dir_all): every level above was checked already.
                if let Err(e) = std::fs::create_dir(&parent) {
                    if e.kind() != std::io::ErrorKind::AlreadyExists {
                        return Err(e.to_string());
                    }
                }
            }
            // On Windows, is_symlink() is also true for junctions (name-surrogate reparse points).
            let meta = std::fs::symlink_metadata(&parent).map_err(|e| e.to_string())?;
            if meta.file_type().is_symlink() {
                return Err(format!("{norm:?}: {d:?} is a link or junction"));
            }
            if !meta.is_dir() {
                return Err(format!("{norm:?}: {d:?} is not a directory"));
            }
        }
        let parent_c = parent.canonicalize().map_err(|e| e.to_string())?;
        if !parent_c.starts_with(&root_c) {
            return Err(format!("{norm:?} resolves outside root {name:?}"));
        }
        let final_path = parent_c.join(file_name);
        if let Ok(meta) = std::fs::symlink_metadata(&final_path) {
            if meta.file_type().is_symlink() || meta.is_dir() {
                return Err(format!("{norm:?} is a link or a directory"));
            }
        }
        let tmp = parent_c.join(format!(".{file_name}.tmp"));
        std::fs::write(&tmp, data).map_err(|e| e.to_string())?;
        std::fs::rename(&tmp, &final_path).map_err(|e| {
            let _ = std::fs::remove_file(&tmp);
            e.to_string()
        })?;
        Ok(data.len())
    }

    pub fn list(&self, name: &str, rel: &str) -> Result<Vec<Entry>, String> {
        let dir = self.resolve(name, rel)?;
        let mut out = Vec::new();
        for e in std::fs::read_dir(&dir).map_err(|e| e.to_string())?.flatten() {
            let Ok(meta) = e.metadata() else { continue };
            out.push(Entry {
                name: e.file_name().to_string_lossy().into_owned(),
                is_dir: meta.is_dir(),
                size: if meta.is_dir() { 0 } else { meta.len() },
                modified: meta
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                    .map(|d| d.as_secs())
                    .unwrap_or(0),
            });
        }
        out.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(out)
    }

    /// Read up to `max` bytes starting at `offset`. Returns (bytes, total file size).
    pub fn read(&self, name: &str, rel: &str, offset: u64, max: u64) -> Result<(Vec<u8>, u64), String> {
        let path = self.resolve(name, rel)?;
        let mut f = std::fs::File::open(&path).map_err(|e| e.to_string())?;
        let size = f.metadata().map_err(|e| e.to_string())?.len();
        if !f.metadata().map(|m| m.is_file()).unwrap_or(false) {
            return Err(format!("{rel:?} is not a file"));
        }
        let start = offset.min(size);
        f.seek(SeekFrom::Start(start)).map_err(|e| e.to_string())?;
        let mut buf = Vec::new();
        f.take(max.min(MAX_READ)).read_to_end(&mut buf).map_err(|e| e.to_string())?;
        Ok((buf, size))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> (tempdir::TempDirLite, Roots) {
        let dir = tempdir::TempDirLite::new("roots");
        std::fs::create_dir_all(dir.path().join("game/save games/empire")).unwrap();
        std::fs::write(dir.path().join("game/save games/empire/autosave.sav"), b"0123456789").unwrap();
        std::fs::write(dir.path().join("secret.txt"), b"outside").unwrap();
        let mut roots = Roots::default();
        roots.roots.insert("game".into(), dir.path().join("game"));
        (dir, roots)
    }

    #[test]
    fn lists_and_reads_inside_the_root() {
        let (_d, r) = fixture();
        let entries = r.list("game", "save games/empire").unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "autosave.sav");
        assert_eq!(entries[0].size, 10);
        let (bytes, size) = r.read("game", "save games/empire/autosave.sav", 0, 1000).unwrap();
        assert_eq!((bytes.as_slice(), size), (&b"0123456789"[..], 10));
        let (tail, _) = r.read("game", "save games/empire/autosave.sav", 7, 1000).unwrap();
        assert_eq!(tail, b"789", "offset reads support following a growing log");
        let (past, _) = r.read("game", "save games/empire/autosave.sav", 50, 1000).unwrap();
        assert!(past.is_empty());
        assert_eq!(r.list("game", "").unwrap()[0].name, "save games");
    }

    #[test]
    fn refuses_escapes_absolute_paths_and_unknown_roots() {
        let (d, r) = fixture();
        assert!(r.read("game", "../secret.txt", 0, 100).unwrap_err().contains(".."));
        assert!(r.read("game", "save games/../../secret.txt", 0, 100).is_err());
        let abs = d.path().join("secret.txt");
        assert!(r.read("game", abs.to_str().unwrap(), 0, 100).is_err());
        assert!(r.read("other", "x", 0, 100).unwrap_err().contains("unknown root"));
        assert!(r.read("game", "save games", 0, 100).unwrap_err().contains("not a file"));
        assert!(r.read("game", "c:secret.txt", 0, 100).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn refuses_symlinks_that_leave_the_root() {
        let (d, r) = fixture();
        std::os::unix::fs::symlink(d.path().join("secret.txt"), d.path().join("game/link.txt")).unwrap();
        assert!(r.read("game", "link.txt", 0, 100).unwrap_err().contains("outside"));
    }

    #[test]
    fn loads_roots_json_and_tolerates_a_missing_file() {
        let d = tempdir::TempDirLite::new("json");
        let p = d.path().join("roots.json");
        std::fs::write(&p, r#"{"roots": {"a": "/tmp"}}"#).unwrap();
        assert_eq!(Roots::load(&p).roots["a"], PathBuf::from("/tmp"));
        assert!(Roots::load(&d.path().join("missing.json")).roots.is_empty());
    }

    #[test]
    fn loads_roots_json_with_a_utf8_bom() {
        // Windows PowerShell 5.1 `Set-Content -Encoding UTF8` prefixes a BOM.
        let d = tempdir::TempDirLite::new("bom");
        let p = d.path().join("roots.json");
        std::fs::write(&p, "\u{feff}{\"roots\": {\"a\": \"/tmp\"}}").unwrap();
        assert_eq!(Roots::load(&p).roots["a"], PathBuf::from("/tmp"));
    }

    fn write_roots(dir: &Path) -> Roots {
        let mut r = Roots::default();
        r.write_roots.insert(
            "w".into(),
            WriteRoot { path: dir.to_path_buf(), allow: vec!["mod/bridge/".into(), "mod/bridge.mod".into(), "dlc_load.json".into()] },
        );
        r
    }

    #[test]
    fn writes_only_allowed_paths_inside_write_roots() {
        let d = tempdir::TempDirLite::new("write");
        let r = write_roots(d.path());
        assert_eq!(r.write("w", "mod/bridge/common/ai_budget/x.txt", b"a = 1").unwrap(), 5);
        assert_eq!(std::fs::read(d.path().join("mod/bridge/common/ai_budget/x.txt")).unwrap(), b"a = 1");
        r.write("w", "mod/bridge.mod", b"name=\"x\"").unwrap();
        r.write("w", "dlc_load.json", b"{}").unwrap();
        r.write("w", "dlc_load.json", b"{\"enabled_mods\":[]}").unwrap(); // overwrite
        assert_eq!(std::fs::read(d.path().join("dlc_load.json")).unwrap(), b"{\"enabled_mods\":[]}");
        for bad in ["settings.txt", "mod/other/x.txt", "mod/bridge", "mod/bridgeX/x", "../x", "mod/bridge/../../x", "/etc/x", "C:x", ""] {
            assert!(r.write("w", bad, b"x").is_err(), "{bad:?} must be refused");
        }
        assert!(r.write("nope", "dlc_load.json", b"x").is_err(), "unknown root");
        assert!(r.write("w", "dlc_load.json", &vec![0u8; MAX_WRITE + 1]).is_err(), "too large");
        // read roots are never writable
        let mut ro = Roots::default();
        ro.roots.insert("r".into(), d.path().to_path_buf());
        assert!(ro.write("r", "dlc_load.json", b"x").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn write_refuses_symlink_escapes() {
        let d = tempdir::TempDirLite::new("wlink");
        let outside = tempdir::TempDirLite::new("wout");
        std::fs::create_dir_all(d.path().join("mod")).unwrap();
        std::os::unix::fs::symlink(outside.path(), d.path().join("mod/bridge")).unwrap();
        let r = write_roots(d.path());
        assert!(r.write("w", "mod/bridge/x.txt", b"x").is_err(), "directory link out of the root");
        std::os::unix::fs::symlink(outside.path().join("f"), d.path().join("dlc_load.json")).unwrap();
        assert!(r.write("w", "dlc_load.json", b"x").is_err(), "file link");
        assert!(!outside.path().join("x.txt").exists() && !outside.path().join("f").exists());
    }

    #[test]
    fn windows_special_names_are_refused_on_read_and_write() {
        let (_d, r) = fixture();
        let w = tempdir::TempDirLite::new("wspecial");
        let wr = write_roots(w.path());
        let bad = [
            "CON", "con.txt", "save games/NUL", "nul.sav", "Aux.log", "PRN", "COM1", "com9.txt", "LPT1",
            "lpt9.x.y", "COM\u{b9}", "CONIN$", "conout$.txt", "NUL .txt", "save games./x", "save games /x",
            "x.", "x ", "save games\\..\\..\\secret.txt", "\\\\?\\C:\\x", "\\\\server\\share\\x", "//server/share/x",
            "\\\\.\\pipe\\x", "a:b", "autosave.sav:stream", "save games/empire/autosave.sav::$DATA",
        ];
        for rel in bad {
            assert!(check_rel(rel).is_err(), "{rel:?} must be refused");
            assert!(r.read("game", rel, 0, 10).is_err(), "read {rel:?}");
            let in_allowed = format!("mod/bridge/{rel}");
            assert!(wr.write("w", &in_allowed, b"x").is_err(), "write {in_allowed:?}");
        }
        for ok in ["save games/empire/autosave.sav", "console.txt", "com10.txt", "lpt.txt", "nullable.txt", "CONFIG", "a.b.c", "./x"] {
            assert!(check_rel(ok).is_ok(), "{ok:?} must be accepted");
        }
        // Nothing was created by the refused writes.
        assert!(!w.path().join("mod").exists(), "refused writes must not create directories");
    }

    #[test]
    fn write_creates_no_directory_for_a_refused_path() {
        let d = tempdir::TempDirLite::new("wnodir");
        let r = write_roots(d.path());
        for bad in ["mod/other/deep/x.txt", "mod/bridge/NUL/x.txt", "mod/bridge/sub./x.txt"] {
            assert!(r.write("w", bad, b"x").is_err(), "{bad:?}");
        }
        assert!(!d.path().join("mod").exists());
    }

    #[cfg(unix)]
    #[test]
    fn write_creates_nothing_outside_through_a_linked_parent() {
        let d = tempdir::TempDirLite::new("wlink2");
        let outside = tempdir::TempDirLite::new("wout2");
        std::fs::create_dir_all(d.path().join("mod")).unwrap();
        std::os::unix::fs::symlink(outside.path(), d.path().join("mod/bridge")).unwrap();
        let r = write_roots(d.path());
        assert!(r.write("w", "mod/bridge/new/deeper/x.txt", b"x").unwrap_err().contains("link"));
        assert!(!outside.path().join("new").exists(), "no directory may be created outside the root");
    }

    #[test]
    fn write_roots_load_from_json() {
        let d = tempdir::TempDirLite::new("wjson");
        let p = d.path().join("roots.json");
        std::fs::write(&p, r#"{"roots": {}, "write_roots": {"m": {"path": "/tmp", "allow": ["mod/x/"]}}}"#).unwrap();
        assert_eq!(Roots::load(&p).write_roots["m"].allow, vec!["mod/x/".to_string()]);
    }

    /// Minimal temp dir (no extra dependency).
    mod tempdir {
        use std::path::{Path, PathBuf};
        pub struct TempDirLite(PathBuf);
        impl TempDirLite {
            pub fn new(tag: &str) -> Self {
                let p = std::env::temp_dir().join(format!(
                    "agent-files-{tag}-{}-{:?}",
                    std::process::id(),
                    std::thread::current().id()
                ));
                let _ = std::fs::remove_dir_all(&p);
                std::fs::create_dir_all(&p).unwrap();
                TempDirLite(p)
            }
            pub fn path(&self) -> &Path {
                &self.0
            }
        }
        impl Drop for TempDirLite {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
    }
}
