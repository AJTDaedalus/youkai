#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fmt::Display;
use std::path::PathBuf;

use anyhow::{Context, Result};
use tracing_appender::rolling::Rotation;
use tracing_subscriber::prelude::*;
use tracing_subscriber::{EnvFilter, reload};

mod scan;
mod ui;

pub use scan::{ScanConfig, ScanHandle, ScanMode};

const APP_ID: &str = "youkai";

#[derive(Clone, Debug)]
pub struct PhaseCounts {
    pub engines: Option<PhaseResult>,
    pub discs: Option<PhaseResult>,
    pub agents: Option<PhaseResult>,
}

impl PhaseCounts {
    pub fn empty() -> Self {
        Self {
            engines: None,
            discs: None,
            agents: None,
        }
    }
}

#[derive(Clone, Debug)]
pub struct PhaseResult {
    pub count: u32,
    pub issues: u32,
}

#[derive(Clone, Debug)]
pub struct Summary {
    pub agents: u32,
    pub discs: u32,
    pub engines: u32,
    pub issues: u32,
}

#[derive(Clone, Debug)]
pub enum ScanPhase {
    Engines,
    Discs,
    Agents,
}

#[derive(Clone, Debug)]
pub enum ScanState {
    Idle,
    Running {
        phase: Option<ScanPhase>,
        scanned: u32,
        total: Option<u32>,
        counts: PhaseCounts,
    },
    Done {
        summary: Summary,
        output: PathBuf,
        run_dir: PathBuf,
        review_path: Option<PathBuf>,
    },
    Failed {
        message: String,
        run_dir: Option<PathBuf>,
    },
}

#[derive(Clone, Copy, Debug, serde::Deserialize, Eq, PartialEq, serde::Serialize, Default)]
pub enum TracingLevel {
    #[default]
    Default,
    VerboseInfo,
    VerboseDebug,
    VerboseTrace,
}

impl Display for TracingLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TracingLevel::Default => write!(f, "Default"),
            TracingLevel::VerboseInfo => write!(f, "Verbose Info"),
            TracingLevel::VerboseDebug => write!(f, "Verbose Debug"),
            TracingLevel::VerboseTrace => write!(f, "Verbose Trace"),
        }
    }
}

impl TracingLevel {
    fn get_filter(&self) -> &'static str {
        match self {
            TracingLevel::Default => {
                if cfg!(debug_assertions) {
                    "info"
                } else {
                    "warn,youkai=info"
                }
            }
            TracingLevel::VerboseInfo => "info",
            TracingLevel::VerboseDebug => "debug",
            TracingLevel::VerboseTrace => "trace",
        }
    }
}

pub struct ReloadHandle(reload::Handle<EnvFilter, tracing_subscriber::Registry>);

impl ReloadHandle {
    pub fn set_filter(&mut self, filter: &str) {
        if let Err(e) = self.0.reload(filter) {
            tracing::warn!("Failed to set tracing filter to \"{filter}\": {e}");
        }
        tracing::info!("Set tracing filter to \"{filter}\"");
    }
}

fn main() -> eframe::Result {
    let (_guard, reload_handle) = tracing_init().unwrap();

    let background_image_size = [1600., 1000.];

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size(background_image_size.map(|v| v * 0.5))
            .with_resizable(false)
            .with_decorations(false)
            .with_icon(
                eframe::icon_data::from_png_bytes(&include_bytes!("../assets/icon-256.png")[..])
                    .expect("Failed to load icon"),
            ),
        persist_window: false,
        ..Default::default()
    };

    eframe::run_native(
        "Youkai",
        native_options,
        Box::new(move |cc| Ok(Box::new(ui::app::YoukaiApp::new(cc, reload_handle)))),
    )
}

fn log_dir() -> Result<PathBuf> {
    let mut dir = eframe::storage_dir(APP_ID).context("Storage dir not found")?;
    dir.push("log");
    Ok(dir)
}

fn open_log_dir() -> Result<()> {
    let dir = log_dir()?;
    open::that(dir)?;
    Ok(())
}

fn tracing_init() -> Result<(tracing_appender::non_blocking::WorkerGuard, ReloadHandle)> {
    let appender = tracing_appender::rolling::Builder::new()
        .filename_prefix("log")
        .rotation(Rotation::DAILY)
        .max_log_files(7)
        .build(log_dir()?)?;
    let (non_blocking_appender, guard) = tracing_appender::non_blocking(appender);

    let filter = EnvFilter::new(TracingLevel::default().get_filter());
    let (filter, reload_handle) = reload::Layer::new(filter);
    let writer = tracing_subscriber::fmt::layer()
        .with_writer(non_blocking_appender)
        .with_ansi(false);
    tracing_subscriber::registry()
        .with(filter)
        .with(writer)
        .init();
    tracing::info!("Tracing initialized and logging to file.");

    Ok((guard, ReloadHandle(reload_handle)))
}
