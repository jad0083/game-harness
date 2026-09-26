//! Read-only access to a few named directories (e.g. a game's saves and logs).
//!
//! Roots come from `roots.json` next to the executable, written by the installer:
//! `{"roots": {"stellaris_docs": "C:\\Users\\me\\Documents\\Paradox Interactive\\Stellaris"}}`.
//! Requests name a root and a relative path; anything that resolves outside its root, absolute
//! paths and `..` components are refused. There is no write, delete or execute operation.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Component, Path, PathBuf};
use std::time::UNIX_EPOCH;

/// Largest single read (bytes). Stellaris saves are typically a few MB; late-game ones tens of MB.
pub const MAX_READ: u64 = 128 * 1024 * 1024;

#[derive(Debug, Default, Clone, Deserialize)]
pub struct Roots {
    #[serde(default)]
    pub roots: BTreeMap<String, PathBuf>,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct Entry {
    pub name: String,
    pub is_dir: bool,
    pub size: u64,
    /// Seconds since the Unix epoch.
    pub modified: u64,
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
        let rel_path = Path::new(rel);
        for c in rel_path.components() {
            match c {
                Component::Normal(_) | Component::CurDir => {}
                _ => return Err(format!("path {rel:?} must be relative and must not contain '..'")),
            }
        }
        if rel.contains(':') {
            return Err("drive or stream syntax (':') is not allowed".into());
        }
        let root_c = root.canonicalize().map_err(|e| format!("root {name:?} unavailable: {e}"))?;
        let full = root_c.join(rel_path);
        let full_c = full.canonicalize().map_err(|e| format!("{rel:?}: {e}"))?;
        if !full_c.starts_with(&root_c) {
            return Err(format!("{rel:?} resolves outside root {name:?}"));
        }
        Ok(full_c)
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
