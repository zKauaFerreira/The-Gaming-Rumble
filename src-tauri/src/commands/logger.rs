use std::fmt::Display;
use std::sync::atomic::{AtomicU64, Ordering};

static START_MS: AtomicU64 = AtomicU64::new(0);

fn get_timestamp() -> String {
    let start = START_MS.load(Ordering::Relaxed);
    if start == 0 {
        use std::time::SystemTime;
        let ms = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_millis() as u64;
        START_MS.store(ms, Ordering::Relaxed);
    }
    let elapsed_ms = {
        use std::time::SystemTime;
        let now = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).unwrap().as_millis() as u64;
        now - start
    };
    let secs = (elapsed_ms / 1000) % 60;
    let mins = (elapsed_ms / 60000) % 60;
    let hrs = elapsed_ms / 3600000;
    format!("{:02}:{:02}:{:02}", hrs, mins, secs)
}

#[derive(Debug, Clone, Copy)]
pub enum LogLevel { INFO, SUCCESS, WARN, ERROR, DEBUG }

impl LogLevel {
    fn symbol(&self) -> &'static str {
        match self {
            Self::INFO    => " 📡",
            Self::SUCCESS => " ✅",
            Self::WARN    => " ⚠️ ",
            Self::ERROR   => " ❌",
            Self::DEBUG   => " 🔍",
        }
    }
}

pub fn log(level: LogLevel, msg: impl Display) {
    println!("[{}{}] {}", level.symbol(), get_timestamp(), msg);
}

pub fn log_tag(level: LogLevel, tag: impl Display, msg: impl Display) {
    println!("[{}{}] [{}] {}", level.symbol(), get_timestamp(), tag, msg);
}
