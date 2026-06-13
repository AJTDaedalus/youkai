use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;

use serde::{Deserialize, Serialize};

use crate::{PhaseCounts, PhaseResult, ScanPhase, ScanState, Summary};

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScanMode {
    #[default]
    Full,
    DiscsOnly,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ScanConfig {
    #[serde(default)]
    pub mode: ScanMode,
    #[serde(default = "ScanConfig::default_output")]
    pub output: PathBuf,
    #[serde(default)]
    pub debug_overlays: bool,
}

impl Default for ScanConfig {
    fn default() -> Self {
        Self {
            mode: ScanMode::Full,
            output: Self::default_output(),
            debug_overlays: false,
        }
    }
}

impl ScanConfig {
    fn default_output() -> PathBuf {
        PathBuf::from("export/youkai_export.json")
    }
}

pub struct ScanHandle {
    state: Arc<Mutex<ScanState>>,
    child: Arc<Mutex<Option<Child>>>,
}

impl ScanHandle {
    pub fn start(config: ScanConfig, ctx: Option<egui::Context>) -> Self {
        let (program, args) = build_command(&config);
        Self::spawn_with_command(&program, &args, ctx)
    }

    fn spawn_with_command(program: &str, args: &[String], ctx: Option<egui::Context>) -> Self {
        let mut cmd = Command::new(program);
        cmd.args(args).stdout(Stdio::piped()).stderr(Stdio::piped());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                tracing::error!("failed to spawn scanner: {e}");
                let state = Arc::new(Mutex::new(ScanState::Failed {
                    message: format!("failed to spawn scanner: {e}"),
                    run_dir: None,
                }));
                if let Some(c) = &ctx {
                    c.request_repaint();
                }
                return ScanHandle { state, child: Arc::new(Mutex::new(None)) };
            }
        };

        let stdout = child.stdout.take().expect("piped stdout");
        let stderr = child.stderr.take().expect("piped stderr");
        let state: Arc<Mutex<ScanState>> = Arc::new(Mutex::new(ScanState::Idle));
        let child = Arc::new(Mutex::new(Some(child)));

        let stderr_lines: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        {
            let buf = stderr_lines.clone();
            thread::spawn(move || {
                for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                    let mut v = buf.lock().unwrap();
                    v.push(line);
                    if v.len() > 50 {
                        v.remove(0);
                    }
                }
            });
        }

        {
            let state = state.clone();
            thread::spawn(move || {
                reader_thread(stdout, state, stderr_lines, ctx);
            });
        }

        ScanHandle { state, child }
    }

    pub fn state(&self) -> ScanState {
        self.state.lock().unwrap().clone()
    }

    pub fn kill(&self) {
        if let Some(c) = self.child.lock().unwrap().as_mut() {
            let _ = c.kill();
        }
    }
}

fn build_command(config: &ScanConfig) -> (String, Vec<String>) {
    let (program, mut args) = resolve_command();
    args.push("scan-all".into());
    args.push("--porcelain".into());
    args.push("--output".into());
    args.push(config.output.to_string_lossy().into_owned());
    if config.mode == ScanMode::DiscsOnly {
        args.push("--phases".into());
        args.push("discs".into());
    }
    if config.debug_overlays {
        args.push("--debug-overlays".into());
    }
    (program, args)
}

fn resolve_command() -> (String, Vec<String>) {
    if let Ok(exe) = std::env::current_exe() {
        let exe_dir = match exe.parent() {
            Some(d) => d.to_path_buf(),
            None => return ("python".into(), vec!["-m".into(), "youkai_ocr".into()]),
        };

        // Portable layout: youkai-ocr/youkai-ocr.exe beside youkai.exe
        let mut subdir = exe_dir.join("youkai-ocr");
        #[cfg(windows)]
        subdir.push("youkai-ocr.exe");
        #[cfg(not(windows))]
        subdir.push("youkai-ocr");
        if subdir.exists() {
            return (subdir.to_string_lossy().into_owned(), vec![]);
        }

        // Flat sibling fallback (dev / non-onedir layout)
        #[cfg(windows)]
        let sibling = exe_dir.join("youkai-ocr.exe");
        #[cfg(not(windows))]
        let sibling = exe_dir.join("youkai-ocr");
        if sibling.exists() {
            return (sibling.to_string_lossy().into_owned(), vec![]);
        }
    }
    ("python".into(), vec!["-m".into(), "youkai_ocr".into()])
}

#[derive(Deserialize)]
#[serde(tag = "event", rename_all = "snake_case")]
enum ScanEvent {
    RunStart { run_dir: String, output: String, phases: Vec<String> },
    PhaseStart { phase: String, total: Option<u32> },
    Progress { phase: String, scanned: u32, total: Option<u32> },
    PhaseDone { phase: String, count: u32, issues: u32, elapsed: f64, resumed: bool },
    Warning { message: String },
    Done { output: String, run_dir: String, summary: EventSummary, review_path: Option<String> },
    Error { message: String },
}

#[derive(Deserialize)]
struct EventSummary {
    agents: u32,
    discs: u32,
    engines: u32,
    issues: u32,
}

fn parse_phase(s: &str) -> Option<ScanPhase> {
    match s {
        "engines" => Some(ScanPhase::Engines),
        "discs" => Some(ScanPhase::Discs),
        "agents" => Some(ScanPhase::Agents),
        _ => None,
    }
}

fn reader_thread(
    stdout: std::process::ChildStdout,
    state: Arc<Mutex<ScanState>>,
    stderr_lines: Arc<Mutex<Vec<String>>>,
    ctx: Option<egui::Context>,
) {
    let repaint = || {
        if let Some(c) = &ctx {
            c.request_repaint();
        }
    };

    let mut terminal = false;
    let mut run_dir: Option<String> = None;
    let mut cur_phase: Option<ScanPhase> = None;
    let mut cur_scanned: u32 = 0;
    let mut cur_total: Option<u32> = None;
    let mut counts = PhaseCounts::empty();

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        let event: ScanEvent = match serde_json::from_str(&line) {
            Ok(e) => e,
            Err(_) => {
                tracing::warn!("scanner: ignoring unparseable line: {line:?}");
                continue;
            }
        };

        match event {
            ScanEvent::RunStart { run_dir: rd, .. } => {
                run_dir = Some(rd);
                *state.lock().unwrap() = ScanState::Running {
                    phase: None,
                    scanned: 0,
                    total: None,
                    counts: PhaseCounts::empty(),
                };
            }
            ScanEvent::PhaseStart { phase, total } => {
                cur_phase = parse_phase(&phase);
                cur_scanned = 0;
                cur_total = total;
                *state.lock().unwrap() = ScanState::Running {
                    phase: cur_phase.clone(),
                    scanned: 0,
                    total: cur_total,
                    counts: counts.clone(),
                };
            }
            ScanEvent::Progress { scanned, total, .. } => {
                cur_scanned = scanned;
                if total.is_some() {
                    cur_total = total;
                }
                *state.lock().unwrap() = ScanState::Running {
                    phase: cur_phase.clone(),
                    scanned: cur_scanned,
                    total: cur_total,
                    counts: counts.clone(),
                };
            }
            ScanEvent::PhaseDone { phase, count, issues, .. } => {
                match phase.as_str() {
                    "engines" => counts.engines = Some(PhaseResult { count, issues }),
                    "discs" => counts.discs = Some(PhaseResult { count, issues }),
                    "agents" => counts.agents = Some(PhaseResult { count, issues }),
                    _ => {}
                }
                cur_phase = None;
                cur_scanned = 0;
                cur_total = None;
                *state.lock().unwrap() = ScanState::Running {
                    phase: None,
                    scanned: 0,
                    total: None,
                    counts: counts.clone(),
                };
            }
            ScanEvent::Done { output, run_dir: rd, summary, review_path } => {
                terminal = true;
                *state.lock().unwrap() = ScanState::Done {
                    summary: Summary {
                        agents: summary.agents,
                        discs: summary.discs,
                        engines: summary.engines,
                        issues: summary.issues,
                    },
                    output: PathBuf::from(output),
                    run_dir: PathBuf::from(rd),
                    review_path: review_path.map(PathBuf::from),
                };
            }
            ScanEvent::Error { message } => {
                terminal = true;
                *state.lock().unwrap() = ScanState::Failed {
                    message,
                    run_dir: run_dir.as_deref().map(PathBuf::from),
                };
            }
            ScanEvent::Warning { .. } => {}
        }

        repaint();
        if terminal {
            break;
        }
    }

    if !terminal {
        let tail = stderr_lines.lock().unwrap().join("\n");
        let message = if tail.is_empty() {
            "scanner exited without a terminal event".to_string()
        } else {
            format!("scanner exited unexpectedly:\n{tail}")
        };
        *state.lock().unwrap() = ScanState::Failed {
            message,
            run_dir: run_dir.map(PathBuf::from),
        };
        repaint();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;
    use std::thread;
    use std::time::{Duration, Instant};

    fn python3() -> &'static str {
        if Command::new("python3").arg("--version").output().is_ok() {
            "python3"
        } else {
            "python"
        }
    }

    fn wait_terminal(handle: &ScanHandle, timeout: Duration) -> ScanState {
        let deadline = Instant::now() + timeout;
        loop {
            let s = handle.state();
            if matches!(s, ScanState::Done { .. } | ScanState::Failed { .. }) {
                return s;
            }
            assert!(Instant::now() < deadline, "timed out waiting for terminal state");
            thread::sleep(Duration::from_millis(20));
        }
    }

    fn run_script(script: &str) -> ScanHandle {
        ScanHandle::spawn_with_command(
            python3(),
            &["-c".to_string(), script.to_string()],
            None,
        )
    }

    #[test]
    fn test_good_run_reaches_done() {
        let script = r#"
import sys, json
events = [
    {"event":"run_start","v":1,"run_dir":"/tmp/r1","output":"/tmp/out.json","phases":["engines"]},
    {"event":"phase_start","phase":"engines","total":2},
    {"event":"progress","phase":"engines","scanned":1,"total":2},
    {"event":"progress","phase":"engines","scanned":2,"total":2},
    {"event":"phase_done","phase":"engines","count":2,"issues":0,"elapsed":0.5,"resumed":False},
    {"event":"done","output":"/tmp/out.json","run_dir":"/tmp/r1",
     "summary":{"agents":0,"discs":0,"engines":2,"issues":0},"review_path":None},
]
for e in events:
    print(json.dumps(e), flush=True)
"#;
        let h = run_script(script);
        match wait_terminal(&h, Duration::from_secs(10)) {
            ScanState::Done { summary, .. } => {
                assert_eq!(summary.engines, 2);
                assert_eq!(summary.issues, 0);
            }
            other => panic!("expected Done, got {other:?}"),
        }
    }

    #[test]
    fn test_early_exit_failed_with_stderr_tail() {
        let script = r#"
import sys
print("scan crashed hard", file=sys.stderr, flush=True)
sys.exit(1)
"#;
        let h = run_script(script);
        match wait_terminal(&h, Duration::from_secs(10)) {
            ScanState::Failed { message, .. } => {
                assert!(
                    message.contains("scan crashed hard"),
                    "expected stderr in message, got: {message}",
                );
            }
            other => panic!("expected Failed, got {other:?}"),
        }
    }

    #[test]
    fn test_garbage_and_unknown_events_ignored() {
        let script = r#"
import json
lines = [
    "not json at all",
    json.dumps({"event":"future_event","data":"whatever"}),
    json.dumps({"event":"done","output":"/o","run_dir":"/r",
                "summary":{"agents":1,"discs":2,"engines":3,"issues":0},"review_path":None}),
]
for l in lines:
    print(l, flush=True)
"#;
        let h = run_script(script);
        match wait_terminal(&h, Duration::from_secs(10)) {
            ScanState::Done { summary, .. } => {
                assert_eq!(summary.agents, 1);
                assert_eq!(summary.discs, 2);
                assert_eq!(summary.engines, 3);
            }
            other => panic!("expected Done, got {other:?}"),
        }
    }

    #[test]
    fn test_config_args_full_mode() {
        let config = ScanConfig {
            mode: ScanMode::Full,
            output: PathBuf::from("/tmp/out.json"),
            debug_overlays: false,
        };
        let (_, args) = build_command(&config);
        assert!(args.contains(&"scan-all".to_string()));
        assert!(args.contains(&"--porcelain".to_string()));
        assert!(!args.contains(&"--phases".to_string()), "Full mode must not emit --phases");
    }

    #[test]
    fn test_config_args_discs_only() {
        let config = ScanConfig {
            mode: ScanMode::DiscsOnly,
            output: PathBuf::from("/tmp/out.json"),
            debug_overlays: false,
        };
        let (_, args) = build_command(&config);
        let phases_idx = args.iter().position(|a| a == "--phases").expect("--phases missing");
        assert_eq!(args[phases_idx + 1], "discs");
    }

    #[test]
    fn test_config_round_trip() {
        let config = ScanConfig {
            mode: ScanMode::DiscsOnly,
            output: PathBuf::from("/custom/out.json"),
            debug_overlays: true,
        };
        let json = serde_json::to_string(&config).unwrap();
        let decoded: ScanConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(decoded.mode, ScanMode::DiscsOnly);
        assert_eq!(decoded.output, PathBuf::from("/custom/out.json"));
        assert!(decoded.debug_overlays);
    }

    #[test]
    fn test_config_empty_json_falls_back_to_default() {
        let decoded: ScanConfig = serde_json::from_str("{}").unwrap();
        assert_eq!(decoded.mode, ScanMode::Full);
        assert_eq!(decoded.output, ScanConfig::default_output());
        assert!(!decoded.debug_overlays);
    }

    #[test]
    fn test_kill_leads_to_failed_no_hang() {
        let script = r#"
import time
time.sleep(60)
"#;
        let h = run_script(script);
        thread::sleep(Duration::from_millis(150));
        h.kill();
        let state = wait_terminal(&h, Duration::from_secs(5));
        assert!(
            matches!(state, ScanState::Failed { .. }),
            "expected Failed after kill, got {state:?}",
        );
    }
}
