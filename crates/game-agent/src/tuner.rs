//! Relay to Civilization VI's FireTuner Lua console.
//!
//! With `EnableTuner 1` in the game's options, Civ VI listens on 127.0.0.1:4318 (loopback only),
//! so the controller cannot reach it directly; the agent holds one connection and relays Lua.
//!
//! Wire format, both ways: `[u32 LE length][i32 LE tag][payload + NUL]`, where `length` counts the
//! payload including its NUL. Handshake: tag 4 `APP:` (reply: the game's identity), tag 4 `LSQ:`
//! (reply: the Lua state names, NUL- or newline-separated; a state's index is its position).
//! Execute: tag 3 `CMD:<state index>:<lua>`; the first message back is the result, and `print()`
//! output may follow as further messages, collected for a short quiet window.
//!
//! The game accepts one tuner client at a time, so every request goes through one connection
//! behind a mutex. The connection is only ever made to 127.0.0.1.

use std::net::{Ipv4Addr, SocketAddr};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::Mutex;
use tokio::time::Instant;

pub const DEFAULT_PORT: u16 = 4318;
/// Environment variable that overrides the tuner port.
pub const PORT_ENV: &str = "GAME_AGENT_TUNER_PORT";
pub const TAG_COMMAND: i32 = 3;
pub const TAG_HANDSHAKE: i32 = 4;
/// Largest Lua chunk accepted.
pub const MAX_CODE: usize = 64 * 1024;
/// Largest total reply (result plus extra messages) of one request; also caps one frame.
pub const MAX_REPLY: usize = 4 * 1024 * 1024;
pub const DEFAULT_TIMEOUT_MS: u64 = 5_000;
pub const MAX_TIMEOUT_MS: u64 = 30_000;
const HEADER: usize = 8;

/// The tuner port: `GAME_AGENT_TUNER_PORT` when set to a valid port, else 4318.
pub fn port_from_env() -> u16 {
    std::env::var(PORT_ENV).ok().and_then(|v| v.trim().parse().ok()).filter(|p| *p != 0).unwrap_or(DEFAULT_PORT)
}

#[derive(Debug, Clone, PartialEq)]
pub enum TunerError {
    /// The request itself is invalid (unknown state, code too large). HTTP 400.
    BadRequest(String),
    /// Nothing listens on the tuner port (game not running, or tuner disabled). HTTP 502.
    Unavailable(String),
    /// The game did not answer in time. HTTP 504.
    Timeout(String),
    /// The game sent something unusable (oversized reply). HTTP 502.
    Protocol(String),
    /// The connection dropped. HTTP 502 (after one reconnect attempt).
    Broken(String),
}

impl TunerError {
    pub fn message(&self) -> &str {
        match self {
            Self::BadRequest(m) | Self::Unavailable(m) | Self::Timeout(m) | Self::Protocol(m) | Self::Broken(m) => m,
        }
    }
    pub fn kind(&self) -> &'static str {
        match self {
            Self::BadRequest(_) => "bad_request",
            Self::Unavailable(_) => "unavailable",
            Self::Timeout(_) => "timeout",
            Self::Protocol(_) => "protocol",
            Self::Broken(_) => "broken",
        }
    }
}

/// A Lua state named by the caller: its name from LSQ, or its index.
#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
#[serde(untagged)]
pub enum StateSel {
    Index(usize),
    Name(String),
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct LuaReply {
    pub ok: bool,
    pub state: String,
    pub result: String,
    pub extra: Vec<String>,
}

/// One framed message.
pub fn encode(tag: i32, payload: &str) -> Vec<u8> {
    let len = payload.len() as u32 + 1;
    let mut out = Vec::with_capacity(HEADER + payload.len() + 1);
    out.extend_from_slice(&len.to_le_bytes());
    out.extend_from_slice(&tag.to_le_bytes());
    out.extend_from_slice(payload.as_bytes());
    out.push(0);
    out
}

/// Take one complete message off the front of `buf`: `Ok(None)` while it is incomplete.
/// Trailing NULs are stripped; inner NULs are kept (LSQ may separate names with them).
pub fn take_frame(buf: &mut Vec<u8>, max: usize) -> Result<Option<(i32, String)>, TunerError> {
    if buf.len() < HEADER {
        return Ok(None);
    }
    let len = u32::from_le_bytes(buf[0..4].try_into().unwrap()) as usize;
    let tag = i32::from_le_bytes(buf[4..8].try_into().unwrap());
    if len > max {
        return Err(TunerError::Protocol(format!("tuner message of {len} bytes exceeds the {max}-byte reply limit")));
    }
    if buf.len() < HEADER + len {
        return Ok(None);
    }
    let body: Vec<u8> = buf.drain(..HEADER + len).skip(HEADER).collect();
    let end = body.iter().rposition(|b| *b != 0).map_or(0, |i| i + 1);
    Ok(Some((tag, String::from_utf8_lossy(&body[..end]).into_owned())))
}

/// State names from an LSQ reply, NUL-separated or (if that yields one entry) newline-separated.
pub fn parse_states(raw: &str) -> Vec<String> {
    let split = |sep: char| raw.split(sep).map(str::trim).filter(|s| !s.is_empty()).map(str::to_string).collect::<Vec<_>>();
    let states = split('\0');
    if states.len() <= 1 && raw.contains('\n') {
        split('\n')
    } else {
        states
    }
}

/// The index of the chosen state: an index in range, an exact name (any case), or else the one
/// name that starts with it (e.g. "GameCore" → "GameCore_Tuner" when no "GameCore" exists).
pub fn resolve_state(states: &[String], sel: &StateSel) -> Result<usize, TunerError> {
    let listed = || format!("available: {}", if states.is_empty() { "none".to_string() } else { states.join(", ") });
    match sel {
        StateSel::Index(i) if *i < states.len() => Ok(*i),
        StateSel::Index(i) => Err(TunerError::BadRequest(format!("no Lua state with index {i} ({})", listed()))),
        StateSel::Name(name) => {
            let want = name.trim().to_lowercase();
            if let Some(i) = states.iter().position(|s| s.to_lowercase() == want) {
                return Ok(i);
            }
            let prefixed: Vec<usize> = (0..states.len()).filter(|&i| !want.is_empty() && states[i].to_lowercase().starts_with(&want)).collect();
            match prefixed.as_slice() {
                [i] => Ok(*i),
                [] => Err(TunerError::BadRequest(format!("no Lua state named {name:?} ({})", listed()))),
                _ => Err(TunerError::BadRequest(format!("Lua state {name:?} is ambiguous ({})", listed()))),
            }
        }
    }
}

/// Waiting times; tests shorten them.
#[derive(Debug, Clone, Copy)]
pub struct Timings {
    pub connect: Duration,
    /// Wait for each handshake reply.
    pub handshake: Duration,
    /// Quiet period that ends the collection of extra messages (and the initial drain).
    pub drain: Duration,
    /// Longest collection of extra messages, however chatty the game is.
    pub drain_max: Duration,
}

impl Default for Timings {
    fn default() -> Self {
        Self {
            connect: Duration::from_secs(3),
            handshake: Duration::from_secs(5),
            drain: Duration::from_millis(300),
            drain_max: Duration::from_secs(3),
        }
    }
}

struct Conn {
    stream: TcpStream,
    buf: Vec<u8>,
    app: String,
    states: Vec<String>,
}

impl Conn {
    async fn open(port: u16, t: &Timings) -> Result<Conn, TunerError> {
        let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
        let not_listening = |why: String| {
            TunerError::Unavailable(format!(
                "Civilization VI tuner not reachable on {addr} ({why}); is the game running with EnableTuner 1?"
            ))
        };
        let stream = match tokio::time::timeout(t.connect, TcpStream::connect(addr)).await {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => return Err(not_listening(e.to_string())),
            Err(_) => return Err(not_listening("connect timed out".into())),
        };
        let _ = stream.set_nodelay(true);
        let mut c = Conn { stream, buf: Vec::new(), app: String::new(), states: Vec::new() };
        // The game may greet with unsolicited messages; drop them before asking anything.
        let mut budget = MAX_REPLY;
        while c.recv(Instant::now() + t.drain, &mut budget).await?.is_some() {}
        c.app = c.ask(TAG_HANDSHAKE, "APP:", t.handshake).await?;
        c.refresh_states(t).await?;
        Ok(c)
    }

    async fn refresh_states(&mut self, t: &Timings) -> Result<(), TunerError> {
        self.states = parse_states(&self.ask(TAG_HANDSHAKE, "LSQ:", t.handshake).await?);
        Ok(())
    }

    /// Send a handshake query and return the first message back.
    async fn ask(&mut self, tag: i32, payload: &str, wait: Duration) -> Result<String, TunerError> {
        self.discard_pending()?;
        self.send(tag, payload).await?;
        let mut budget = MAX_REPLY;
        match self.recv(Instant::now() + wait, &mut budget).await? {
            Some((_, text)) => Ok(text),
            None => Err(TunerError::Timeout(format!(
                "no reply to {payload} within {wait:?} (is another tuner client, e.g. FireTuner, connected?)"
            ))),
        }
    }

    async fn send(&mut self, tag: i32, payload: &str) -> Result<(), TunerError> {
        self.stream
            .write_all(&encode(tag, payload))
            .await
            .map_err(|e| TunerError::Broken(format!("sending to the tuner failed: {e}")))
    }

    /// The next message, or `None` at `deadline`. Reads are cancel-safe: partial frames stay in
    /// `buf`, so a timeout never desynchronises the stream.
    async fn recv(&mut self, deadline: Instant, budget: &mut usize) -> Result<Option<(i32, String)>, TunerError> {
        let mut chunk = [0u8; 16 * 1024];
        loop {
            if let Some((tag, text)) = take_frame(&mut self.buf, *budget)? {
                *budget = budget.saturating_sub(text.len() + 1);
                return Ok(Some((tag, text)));
            }
            match tokio::time::timeout_at(deadline, self.stream.read(&mut chunk)).await {
                Err(_) => return Ok(None),
                Ok(Ok(0)) => return Err(TunerError::Broken("the game closed the tuner connection".into())),
                Ok(Ok(n)) => self.buf.extend_from_slice(&chunk[..n]),
                Ok(Err(e)) => return Err(TunerError::Broken(format!("reading from the tuner failed: {e}"))),
            }
        }
    }

    /// Drop whatever the game sent unasked since the last request; notice a closed connection
    /// before sending anything on it.
    fn discard_pending(&mut self) -> Result<(), TunerError> {
        let mut chunk = [0u8; 16 * 1024];
        loop {
            match self.stream.try_read(&mut chunk) {
                Ok(0) => return Err(TunerError::Broken("the game closed the tuner connection".into())),
                Ok(n) => self.buf.extend_from_slice(&chunk[..n]),
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(e) => return Err(TunerError::Broken(format!("reading from the tuner failed: {e}"))),
            }
        }
        while take_frame(&mut self.buf, usize::MAX)?.is_some() {}
        Ok(())
    }

    /// Run `code` in state `index`. On failure, `bool` tells whether any reply had arrived (a
    /// command that may have run must not be sent again).
    async fn execute(&mut self, index: usize, code: &str, timeout: Duration, t: &Timings) -> Result<(String, Vec<String>), (TunerError, bool)> {
        self.discard_pending().map_err(|e| (e, false))?;
        self.send(TAG_COMMAND, &format!("CMD:{index}:{code}")).await.map_err(|e| (e, false))?;
        let mut budget = MAX_REPLY;
        let result = match self.recv(Instant::now() + timeout, &mut budget).await {
            Ok(Some((_, text))) => text,
            Ok(None) => return Err((TunerError::Timeout(format!("no reply from the game within {} ms", timeout.as_millis())), true)),
            Err(e) => return Err((e, false)),
        };
        let mut extra = Vec::new();
        let stop = Instant::now() + t.drain_max;
        loop {
            let quiet = (Instant::now() + t.drain).min(stop);
            match self.recv(quiet, &mut budget).await.map_err(|e| (e, true))? {
                Some((_, text)) => extra.push(text),
                None => break,
            }
        }
        Ok((result, extra))
    }
}

pub struct Tuner {
    port: u16,
    timings: Timings,
    conn: Mutex<Option<Conn>>,
}

impl Tuner {
    pub fn new(port: u16) -> Self {
        Self::with_timings(port, Timings::default())
    }

    pub fn with_timings(port: u16, timings: Timings) -> Self {
        Self { port, timings, conn: Mutex::new(None) }
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    /// The game identity and its current Lua states (re-queried each call: the list changes
    /// between the main menu and a loaded game). Connects and handshakes when needed.
    pub async fn states(&self) -> Result<(String, Vec<String>), TunerError> {
        let mut guard = self.conn.lock().await;
        for attempt in 0..2 {
            let fresh = guard.is_none();
            if fresh {
                *guard = Some(Conn::open(self.port, &self.timings).await?);
            }
            let conn = guard.as_mut().unwrap();
            let refreshed = if fresh { Ok(()) } else { conn.refresh_states(&self.timings).await };
            match refreshed {
                Ok(()) => return Ok((conn.app.clone(), conn.states.clone())),
                Err(e) => {
                    *guard = None;
                    if !(matches!(e, TunerError::Broken(_)) && attempt == 0) {
                        return Err(e);
                    }
                }
            }
        }
        unreachable!("the loop returns on its second attempt")
    }

    /// Run Lua in the chosen state. A connection found broken before the game replied is
    /// re-opened (with a new handshake) and the command sent once more.
    pub async fn lua(&self, sel: &StateSel, code: &str, timeout: Duration) -> Result<LuaReply, TunerError> {
        if code.len() > MAX_CODE {
            return Err(TunerError::BadRequest(format!("code is {} bytes; the limit is {MAX_CODE}", code.len())));
        }
        if code.contains('\0') {
            return Err(TunerError::BadRequest("code must not contain NUL characters".into()));
        }
        let mut guard = self.conn.lock().await;
        for attempt in 0..2 {
            if guard.is_none() {
                *guard = Some(Conn::open(self.port, &self.timings).await?);
            }
            let conn = guard.as_mut().unwrap();
            // An unknown name may be a state that appeared since the last LSQ (a game was loaded).
            let index = match resolve_state(&conn.states, sel) {
                Ok(i) => i,
                Err(_) => match conn.refresh_states(&self.timings).await {
                    Ok(()) => resolve_state(&conn.states, sel)?,
                    Err(e) => {
                        *guard = None;
                        if matches!(e, TunerError::Broken(_)) && attempt == 0 {
                            continue;
                        }
                        return Err(e);
                    }
                },
            };
            let state = conn.states[index].clone();
            match conn.execute(index, code, timeout, &self.timings).await {
                Ok((result, extra)) => return Ok(LuaReply { ok: true, state, result, extra }),
                Err((e, replied)) => {
                    // After a timeout a late reply could be mistaken for the next command's.
                    *guard = None;
                    if matches!(e, TunerError::Broken(_)) && !replied && attempt == 0 {
                        continue;
                    }
                    return Err(e);
                }
            }
        }
        unreachable!("the loop returns on its second attempt")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;
    use tokio::net::TcpListener;

    fn fast() -> Timings {
        Timings {
            connect: Duration::from_secs(2),
            handshake: Duration::from_secs(2),
            drain: Duration::from_millis(60),
            drain_max: Duration::from_millis(500),
        }
    }

    async fn read_msg(s: &mut TcpStream) -> Option<(i32, String)> {
        let mut h = [0u8; 8];
        s.read_exact(&mut h).await.ok()?;
        let len = u32::from_le_bytes(h[0..4].try_into().unwrap()) as usize;
        let tag = i32::from_le_bytes(h[4..8].try_into().unwrap());
        let mut body = vec![0u8; len];
        s.read_exact(&mut body).await.ok()?;
        assert_eq!(body.last(), Some(&0), "payload must end with NUL");
        body.pop();
        Some((tag, String::from_utf8(body).unwrap()))
    }

    async fn write_msg(s: &mut TcpStream, tag: i32, payload: &str) {
        s.write_all(&encode(tag, payload)).await.unwrap();
    }

    /// Answer APP:/LSQ: with `lsq` as the raw state list; returns the first non-handshake
    /// message (or None when the client went away).
    async fn serve_handshake(s: &mut TcpStream, lsq: &str) -> Option<(i32, String)> {
        loop {
            let (tag, msg) = read_msg(s).await?;
            match msg.as_str() {
                "APP:" => write_msg(s, TAG_HANDSHAKE, "Civilization VI").await,
                "LSQ:" => write_msg(s, TAG_HANDSHAKE, lsq).await,
                _ => return Some((tag, msg)),
            }
        }
    }

    const LSQ_NUL: &str = "Main State\0GameCore_Tuner\0InGame\0GameCore";

    #[test]
    fn encode_frames_length_tag_and_nul() {
        let f = encode(3, "CMD:0:x");
        assert_eq!(&f[0..4], &8u32.to_le_bytes());
        assert_eq!(&f[4..8], &3i32.to_le_bytes());
        assert_eq!(&f[8..], b"CMD:0:x\0");
    }

    #[test]
    fn take_frame_waits_for_whole_messages_and_strips_trailing_nuls() {
        let mut stream = encode(4, "a\0b");
        stream.extend(encode(3, "second"));
        let mut buf = stream[..5].to_vec();
        assert_eq!(take_frame(&mut buf, MAX_REPLY).unwrap(), None);
        buf = stream[..10].to_vec();
        assert_eq!(take_frame(&mut buf, MAX_REPLY).unwrap(), None);
        buf = stream.clone();
        assert_eq!(take_frame(&mut buf, MAX_REPLY).unwrap(), Some((4, "a\0b".into())));
        assert_eq!(take_frame(&mut buf, MAX_REPLY).unwrap(), Some((3, "second".into())));
        assert!(buf.is_empty());
        let mut padded = encode(3, "x\0\0");
        assert_eq!(take_frame(&mut padded, MAX_REPLY).unwrap(), Some((3, "x".into())));
    }

    #[test]
    fn take_frame_refuses_an_oversized_length() {
        let mut buf = Vec::new();
        buf.extend_from_slice(&((MAX_REPLY + 1) as u32).to_le_bytes());
        buf.extend_from_slice(&3i32.to_le_bytes());
        assert!(matches!(take_frame(&mut buf, MAX_REPLY), Err(TunerError::Protocol(_))));
    }

    #[test]
    fn states_parse_from_nul_or_newline_lists() {
        assert_eq!(parse_states("Main State\0GameCore\0\0InGame"), vec!["Main State", "GameCore", "InGame"]);
        assert_eq!(parse_states("Main State\r\nGameCore\n\nInGame\n"), vec!["Main State", "GameCore", "InGame"]);
        assert_eq!(parse_states("Only"), vec!["Only"]);
        assert!(parse_states("").is_empty());
    }

    #[test]
    fn state_names_resolve_by_index_exact_name_or_unique_prefix() {
        let s: Vec<String> = parse_states(LSQ_NUL);
        assert_eq!(resolve_state(&s, &StateSel::Name("gamecore".into())), Ok(3));
        assert_eq!(resolve_state(&s, &StateSel::Name("INGAME".into())), Ok(2));
        assert_eq!(resolve_state(&s, &StateSel::Index(1)), Ok(1));
        assert_eq!(resolve_state(&s, &StateSel::Name("main".into())), Ok(0));
        assert!(matches!(resolve_state(&s, &StateSel::Index(4)), Err(TunerError::BadRequest(_))));
        let e = resolve_state(&s, &StateSel::Name("Lobby".into())).unwrap_err();
        assert!(e.message().contains("InGame"), "{e:?}");
        let tuner_only: Vec<String> = parse_states("Main State\0GameCore_Tuner\0InGame");
        assert_eq!(resolve_state(&tuner_only, &StateSel::Name("GameCore".into())), Ok(1));
        let two = parse_states("GameCore_A\0GameCore_B");
        assert!(resolve_state(&two, &StateSel::Name("GameCore".into())).unwrap_err().message().contains("ambiguous"));
    }

    #[test]
    fn state_selector_accepts_a_name_or_an_index_in_json() {
        assert_eq!(serde_json::from_str::<StateSel>("2").unwrap(), StateSel::Index(2));
        assert_eq!(serde_json::from_str::<StateSel>("\"InGame\"").unwrap(), StateSel::Name("InGame".into()));
    }

    #[tokio::test]
    async fn handshake_skips_greetings_and_lists_newline_separated_states() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut s, _) = listener.accept().await.unwrap();
            write_msg(&mut s, 1, "welcome, unsolicited").await;
            serve_handshake(&mut s, "Main State\nGameCore\nInGame\n").await;
        });
        let t = Tuner::with_timings(port, fast());
        let (app, states) = t.states().await.unwrap();
        assert_eq!(app, "Civilization VI");
        assert_eq!(states, vec!["Main State", "GameCore", "InGame"]);
    }

    #[tokio::test]
    async fn lua_runs_in_the_named_state_and_collects_printed_output() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut s, _) = listener.accept().await.unwrap();
            let (tag, cmd) = serve_handshake(&mut s, LSQ_NUL).await.unwrap();
            assert_eq!((tag, cmd.as_str()), (TAG_COMMAND, "CMD:2:print('hi') return 7"));
            write_msg(&mut s, TAG_COMMAND, "7").await;
            write_msg(&mut s, 7, "hi").await;
            write_msg(&mut s, 7, "more").await;
            let _ = read_msg(&mut s).await;
        });
        let t = Tuner::with_timings(port, fast());
        let r = t.lua(&StateSel::Name("ingame".into()), "print('hi') return 7", Duration::from_secs(2)).await.unwrap();
        assert_eq!(r, LuaReply { ok: true, state: "InGame".into(), result: "7".into(), extra: vec!["hi".into(), "more".into()] });
    }

    #[tokio::test]
    async fn a_dropped_connection_is_reopened_and_the_command_sent_once() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let accepted = Arc::new(AtomicUsize::new(0));
        let commands = Arc::new(AtomicUsize::new(0));
        let (a, c) = (accepted.clone(), commands.clone());
        tokio::spawn(async move {
            // First connection: handshake, then the game "restarts" and drops it.
            let (mut s, _) = listener.accept().await.unwrap();
            a.fetch_add(1, Ordering::SeqCst);
            // Serve APP: and LSQ:, then close before any command.
            for _ in 0..2 {
                let (_, m) = read_msg(&mut s).await.unwrap();
                let reply = if m == "APP:" { "Civilization VI".to_string() } else { LSQ_NUL.to_string() };
                s.write_all(&encode(TAG_HANDSHAKE, &reply)).await.unwrap();
            }
            drop(s);
            let (mut s, _) = listener.accept().await.unwrap();
            a.fetch_add(1, Ordering::SeqCst);
            let (_, cmd) = serve_handshake(&mut s, LSQ_NUL).await.unwrap();
            c.fetch_add(1, Ordering::SeqCst);
            assert_eq!(cmd, "CMD:3:return 1");
            write_msg(&mut s, TAG_COMMAND, "1").await;
            let _ = read_msg(&mut s).await;
        });
        let t = Tuner::with_timings(port, fast());
        t.states().await.unwrap();
        tokio::time::sleep(Duration::from_millis(50)).await;
        let r = t.lua(&StateSel::Name("GameCore".into()), "return 1", Duration::from_secs(2)).await.unwrap();
        assert_eq!(r.result, "1");
        assert_eq!(accepted.load(Ordering::SeqCst), 2);
        assert_eq!(commands.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn a_silent_game_times_out_and_the_next_request_reconnects() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let accepted = Arc::new(AtomicUsize::new(0));
        let a = accepted.clone();
        tokio::spawn(async move {
            loop {
                let (mut s, _) = listener.accept().await.unwrap();
                a.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    // Never answers commands.
                    let _ = serve_handshake(&mut s, LSQ_NUL).await;
                    tokio::time::sleep(Duration::from_secs(5)).await;
                });
            }
        });
        let t = Tuner::with_timings(port, fast());
        let started = std::time::Instant::now();
        let e = t.lua(&StateSel::Index(0), "while true do end", Duration::from_millis(200)).await.unwrap_err();
        assert!(matches!(e, TunerError::Timeout(_)), "{e:?}");
        assert!(started.elapsed() < Duration::from_secs(2));
        let _ = t.states().await.unwrap();
        assert_eq!(accepted.load(Ordering::SeqCst), 2, "a timed-out connection must not be reused");
    }

    #[tokio::test]
    async fn no_game_listening_is_unavailable() {
        let port = {
            let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        let t = Tuner::with_timings(port, fast());
        let e = t.states().await.unwrap_err();
        assert!(matches!(e, TunerError::Unavailable(_)), "{e:?}");
        assert!(e.message().contains("EnableTuner"));
    }

    #[tokio::test]
    async fn oversized_code_and_replies_are_refused() {
        let t = Tuner::with_timings(1, fast());
        let big = "x".repeat(MAX_CODE + 1);
        assert!(matches!(t.lua(&StateSel::Index(0), &big, Duration::from_secs(1)).await, Err(TunerError::BadRequest(_))));
        assert!(matches!(t.lua(&StateSel::Index(0), "a\0b", Duration::from_secs(1)).await, Err(TunerError::BadRequest(_))));

        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut s, _) = listener.accept().await.unwrap();
            serve_handshake(&mut s, LSQ_NUL).await.unwrap();
            let mut h = Vec::new();
            h.extend_from_slice(&((MAX_REPLY + 1) as u32).to_le_bytes());
            h.extend_from_slice(&3i32.to_le_bytes());
            s.write_all(&h).await.unwrap();
            tokio::time::sleep(Duration::from_secs(2)).await;
        });
        let t = Tuner::with_timings(port, fast());
        let e = t.lua(&StateSel::Index(0), "return 1", Duration::from_secs(1)).await.unwrap_err();
        assert!(matches!(e, TunerError::Protocol(_)), "{e:?}");
    }

    #[test]
    fn port_defaults_to_4318() {
        assert_eq!(DEFAULT_PORT, 4318);
    }
}
